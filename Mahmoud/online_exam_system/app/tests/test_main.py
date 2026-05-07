import os
import sys

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

CURRENT_DIR = os.path.dirname(__file__)
APP_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from main import app, get_db
from database import Base
from models import User, Exam, Question, ExamAttempt, StudentAnswer, Result
from auth import create_access_token, hash_password

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_online_exam.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_admin_and_student():
    db = TestingSessionLocal()

    admin = User(
        username="admin",
        email="admin@test.com",
        hashed_password=hash_password("123"),
        role="admin"
    )

    student = User(
        username="student1",
        email="student1@test.com",
        hashed_password=hash_password("123"),
        role="student"
    )

    db.add_all([admin, student])
    db.commit()
    db.close()


def login_user(username: str, password: str):
    response = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": password
        }
    )
    return response


def get_token(username: str, password: str) -> str:
    response = login_user(username, password)
    return response.json()["access_token"]


def create_exam_as_admin():
    admin_token = get_token("admin", "123")

    response = client.post(
        "/exams",
        json={
            "title": "Math Exam",
            "description": "Test Exam",
            "duration_minutes": 30
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    return response


def create_question_for_exam(exam_id: int):
    admin_token = get_token("admin", "123")

    response = client.post(
        "/questions",
        json={
            "exam_id": exam_id,
            "question_text": "2 + 2 = ?",
            "question_type": "mcq",
            "choices": ["3", "4", "5", "6"],
            "correct_answer": "4",
            "score": 1
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    return response




def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def build_fake_cache():
    store = {}

    def fake_get(key):
        return store.get(key)

    def fake_set(key, value, expire=120):
        store[key] = value

    def fake_delete(key):
        store.pop(key, None)

    def fake_delete_pattern(pattern):
        prefix = pattern.replace("*", "")
        keys_to_delete = [k for k in store if k.startswith(prefix)]
        for key in keys_to_delete:
            store.pop(key, None)

    return store, fake_get, fake_set, fake_delete, fake_delete_pattern




def test_register():
    response = client.post(
        "/auth/register",
        json={
            "username": "newstudent",
            "email": "newstudent@test.com",
            "password": "123"
        }
    )

    assert response.status_code == 200
    assert response.json()["message"] == "User registered successfully"


def test_login():
    create_admin_and_student()

    response = client.post(
        "/auth/login",
        data={
            "username": "student1",
            "password": "123"
        }
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_invalid_login():
    create_admin_and_student()

    response = client.post(
        "/auth/login",
        data={
            "username": "student1",
            "password": "wrong-password"
        }
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_access_without_token():
    response = client.get("/profile")

    assert response.status_code == 401


def test_student_cannot_create_exam():
    create_admin_and_student()
    student_token = get_token("student1", "123")

    response = client.post(
        "/exams",
        json={
            "title": "Physics Exam",
            "description": "Student should not create this",
            "duration_minutes": 20
        },
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_can_create_exam():
    create_admin_and_student()

    response = create_exam_as_admin()

    assert response.status_code == 200
    assert response.json()["message"] == "Exam created successfully"
    assert response.json()["exam"]["title"] == "Math Exam"


def test_admin_can_update_exam():
    create_admin_and_student()
    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    admin_token = get_token("admin", "123")

    response = client.put(
        f"/exams/{exam_id}",
        json={
            "title": "Updated Math Exam",
            "description": "Updated Description",
            "duration_minutes": 45
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Exam updated successfully"
    assert response.json()["exam"]["title"] == "Updated Math Exam"


def test_admin_can_delete_exam():
    create_admin_and_student()
    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    admin_token = get_token("admin", "123")

    response = client.delete(
        f"/exams/{exam_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Exam deleted successfully"


def test_exam_not_found():
    create_admin_and_student()
    admin_token = get_token("admin", "123")

    response = client.get(
        "/exams/999",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Exam not found"


def test_submit_exam():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    start_response = client.post(
        "/student/exams/start",
        json={"exam_id": exam_id},
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert start_response.status_code == 200

    submit_response = client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": [
                {
                    "question_id": question_id,
                    "answer": "4"
                }
            ]
        },
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert submit_response.status_code == 200
    assert submit_response.json()["message"] == "Exam submitted successfully"
    assert submit_response.json()["result"]["total_score"] == 1
    assert submit_response.json()["result"]["max_score"] == 1


def test_result_retrieval():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    client.post(
        "/student/exams/start",
        json={"exam_id": exam_id},
        headers={"Authorization": f"Bearer {student_token}"}
    )

    client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": [
                {
                    "question_id": question_id,
                    "answer": "4"
                }
            ]
        },
        headers={"Authorization": f"Bearer {student_token}"}
    )

    result_response = client.get(
        f"/student/exams/{exam_id}/result",
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert result_response.status_code == 200
    assert result_response.json()["exam_id"] == exam_id
    assert result_response.json()["total_score"] == 1


def test_submit_exam_without_starting():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    submit_response = client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": [
                {
                    "question_id": question_id,
                    "answer": "4"
                }
            ]
        },
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert submit_response.status_code == 404
    assert submit_response.json()["detail"] == "No active exam attempt found"


def test_submit_exam_with_question_not_belonging_to_exam():
    create_admin_and_student()

    exam1 = create_exam_as_admin().json()["exam"]
    exam2 = create_exam_as_admin().json()["exam"]

    exam1_question_response = create_question_for_exam(exam1["id"])
    assert exam1_question_response.status_code == 200

    exam2_question_response = create_question_for_exam(exam2["id"])
    assert exam2_question_response.status_code == 200

    wrong_question_id = exam2_question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    start_response = client.post(
        "/student/exams/start",
        json={"exam_id": exam1["id"]},
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert start_response.status_code == 200

    submit_response = client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam1["id"],
            "answers": [
                {
                    "question_id": wrong_question_id,
                    "answer": "4"
                }
            ]
        },
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert submit_response.status_code == 400
    assert "does not belong to this exam" in submit_response.json()["detail"]


def test_duplicate_answer_in_same_attempt():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    client.post(
        "/student/exams/start",
        json={"exam_id": exam_id},
        headers={"Authorization": f"Bearer {student_token}"}
    )

    first_submit = client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": [
                {
                    "question_id": question_id,
                    "answer": "4"
                }
            ]
        },
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert first_submit.status_code == 200

    second_submit = client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": [
                {
                    "question_id": question_id,
                    "answer": "4"
                }
            ]
        },
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert second_submit.status_code == 404
    assert second_submit.json()["detail"] == "No active exam attempt found"




def test_access_with_invalid_token():
    create_admin_and_student()

    response = client.get(
        "/profile",
        headers=auth_header("this-is-not-a-valid-token")
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_access_with_expired_token():
    create_admin_and_student()

    expired_token = create_access_token(
        {"sub": "student1", "role": "student"},
        expires_delta=timedelta(minutes=-5)
    )

    response = client.get(
        "/profile",
        headers=auth_header(expired_token)
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_admin_can_get_question_by_id():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    admin_token = get_token("admin", "123")

    response = client.get(
        f"/questions/{question_id}",
        headers=auth_header(admin_token)
    )

    assert response.status_code == 200
    assert response.json()["id"] == question_id
    assert response.json()["question_type"] == "mcq"


def test_admin_can_update_question():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    admin_token = get_token("admin", "123")

    response = client.put(
        f"/questions/{question_id}",
        json={
            "exam_id": exam_id,
            "question_text": "3 + 3 = ?",
            "question_type": "mcq",
            "choices": ["5", "6", "7"],
            "correct_answer": "6",
            "score": 2
        },
        headers=auth_header(admin_token)
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Question updated successfully"
    assert response.json()["question"]["question_text"] == "3 + 3 = ?"
    assert response.json()["question"]["score"] == 2


def test_admin_can_delete_question():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    admin_token = get_token("admin", "123")

    delete_response = client.delete(
        f"/questions/{question_id}",
        headers=auth_header(admin_token)
    )

    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Question deleted successfully"

    get_response = client.get(
        f"/questions/{question_id}",
        headers=auth_header(admin_token)
    )

    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Question not found"


def test_student_cannot_get_admin_question_details():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    response = client.get(
        f"/questions/{question_id}",
        headers=auth_header(student_token)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_invalid_exam_duration():
    create_admin_and_student()
    admin_token = get_token("admin", "123")

    response = client.post(
        "/exams",
        json={
            "title": "Bad Exam",
            "description": "Invalid duration",
            "duration_minutes": 0
        },
        headers=auth_header(admin_token)
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Exam duration must be greater than 0"


def test_invalid_mcq_question_payload():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    admin_token = get_token("admin", "123")

    response = client.post(
        "/questions",
        json={
            "exam_id": exam_id,
            "question_text": "Choose one",
            "question_type": "mcq",
            "choices": ["A", "B"],
            "correct_answer": "C",
            "score": 1
        },
        headers=auth_header(admin_token)
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Correct answer must be one of the provided choices"


def test_exam_without_questions_cannot_be_submitted():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    student_token = get_token("student1", "123")

    start_response = client.post(
        "/student/exams/start",
        json={"exam_id": exam_id},
        headers=auth_header(student_token)
    )

    assert start_response.status_code == 200

    submit_response = client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": []
        },
        headers=auth_header(student_token)
    )

    assert submit_response.status_code == 400
    assert submit_response.json()["detail"] == "This exam has no questions"


def test_submit_exam_after_time_over():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    start_response = client.post(
        "/student/exams/start",
        json={"exam_id": exam_id},
        headers=auth_header(student_token)
    )

    assert start_response.status_code == 200

    db = TestingSessionLocal()
    attempt = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam_id
    ).first()
    attempt.started_at = datetime.utcnow() - timedelta(minutes=31)
    db.commit()
    db.close()

    submit_response = client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": [
                {
                    "question_id": question_id,
                    "answer": "4"
                }
            ]
        },
        headers=auth_header(student_token)
    )

    assert submit_response.status_code == 400
    assert submit_response.json()["detail"] == "Exam time is over"


def test_get_exams_uses_cache(monkeypatch):
    create_admin_and_student()

    store, fake_get, fake_set, fake_delete, fake_delete_pattern = build_fake_cache()

    monkeypatch.setattr("main.get_cache", fake_get)
    monkeypatch.setattr("main.set_cache", fake_set)
    monkeypatch.setattr("main.delete_cache", fake_delete)
    monkeypatch.setattr("main.delete_cache_pattern", fake_delete_pattern)

    create_exam_as_admin()
    admin_token = get_token("admin", "123")

    first_response = client.get("/exams", headers=auth_header(admin_token))
    second_response = client.get("/exams", headers=auth_header(admin_token))

    assert first_response.status_code == 200
    assert first_response.json()["source"] == "database"

    assert second_response.status_code == 200
    assert second_response.json()["source"] == "cache"

    assert "exams:all" in store


def test_get_exam_by_id_uses_cache(monkeypatch):
    create_admin_and_student()

    store, fake_get, fake_set, fake_delete, fake_delete_pattern = build_fake_cache()

    monkeypatch.setattr("main.get_cache", fake_get)
    monkeypatch.setattr("main.set_cache", fake_set)
    monkeypatch.setattr("main.delete_cache", fake_delete)
    monkeypatch.setattr("main.delete_cache_pattern", fake_delete_pattern)

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]
    admin_token = get_token("admin", "123")

    first_response = client.get(
        f"/exams/{exam_id}",
        headers=auth_header(admin_token)
    )
    second_response = client.get(
        f"/exams/{exam_id}",
        headers=auth_header(admin_token)
    )

    assert first_response.status_code == 200
    assert first_response.json()["source"] == "database"

    assert second_response.status_code == 200
    assert second_response.json()["source"] == "cache"

    assert f"exam:{exam_id}" in store


def test_exam_cache_invalidated_after_update(monkeypatch):
    create_admin_and_student()

    store, fake_get, fake_set, fake_delete, fake_delete_pattern = build_fake_cache()

    monkeypatch.setattr("main.get_cache", fake_get)
    monkeypatch.setattr("main.set_cache", fake_set)
    monkeypatch.setattr("main.delete_cache", fake_delete)
    monkeypatch.setattr("main.delete_cache_pattern", fake_delete_pattern)

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]
    admin_token = get_token("admin", "123")

    client.get(f"/exams/{exam_id}", headers=auth_header(admin_token))
    client.get("/exams", headers=auth_header(admin_token))

    assert f"exam:{exam_id}" in store
    assert "exams:all" in store

    update_response = client.put(
        f"/exams/{exam_id}",
        json={
            "title": "Updated Cache Exam",
            "description": "Updated",
            "duration_minutes": 50
        },
        headers=auth_header(admin_token)
    )

    assert update_response.status_code == 200
    assert f"exam:{exam_id}" not in store
    assert "exams:all" not in store



def test_register_duplicate_username_or_email():
    create_admin_and_student()

    response = client.post(
        "/auth/register",
        json={
            "username": "student1",
            "email": "student1@test.com",
            "password": "123"
        }
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Username or email already exists"


def test_student_can_get_exam_questions_without_answers():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    create_question_for_exam(exam_id)

    student_token = get_token("student1", "123")

    response = client.get(
        f"/student/exams/{exam_id}/questions",
        headers=auth_header(student_token)
    )

    assert response.status_code == 200
    assert response.json()["data"]["exam_id"] == exam_id
    assert "correct_answer" not in response.text


def test_admin_can_get_exam_questions_with_answers():
    create_admin_and_student()

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    create_question_for_exam(exam_id)

    admin_token = get_token("admin", "123")

    response = client.get(
        f"/exams/{exam_id}/questions",
        headers=auth_header(admin_token)
    )

    assert response.status_code == 200
    assert response.json()["data"]["exam_id"] == exam_id
    assert "correct_answer" in response.text


def test_result_retrieval_uses_cache(monkeypatch):
    create_admin_and_student()

    store, fake_get, fake_set, fake_delete, fake_delete_pattern = build_fake_cache()

    monkeypatch.setattr("main.get_cache", fake_get)
    monkeypatch.setattr("main.set_cache", fake_set)
    monkeypatch.setattr("main.delete_cache", fake_delete)
    monkeypatch.setattr("main.delete_cache_pattern", fake_delete_pattern)

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]

    question_response = create_question_for_exam(exam_id)
    question_id = question_response.json()["question"]["id"]

    student_token = get_token("student1", "123")

    client.post(
        "/student/exams/start",
        json={"exam_id": exam_id},
        headers=auth_header(student_token)
    )

    client.post(
        "/student/exams/submit",
        json={
            "exam_id": exam_id,
            "answers": [
                {
                    "question_id": question_id,
                    "answer": "4"
                }
            ]
        },
        headers=auth_header(student_token)
    )

    first_response = client.get(
        f"/student/exams/{exam_id}/result",
        headers=auth_header(student_token)
    )

    second_response = client.get(
        f"/student/exams/{exam_id}/result",
        headers=auth_header(student_token)
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert f"result:student:2:exam:{exam_id}" in store


def test_exam_cache_invalidated_after_delete(monkeypatch):
    create_admin_and_student()

    store, fake_get, fake_set, fake_delete, fake_delete_pattern = build_fake_cache()

    monkeypatch.setattr("main.get_cache", fake_get)
    monkeypatch.setattr("main.set_cache", fake_set)
    monkeypatch.setattr("main.delete_cache", fake_delete)
    monkeypatch.setattr("main.delete_cache_pattern", fake_delete_pattern)

    exam_response = create_exam_as_admin()
    exam_id = exam_response.json()["exam"]["id"]
    admin_token = get_token("admin", "123")

    client.get(f"/exams/{exam_id}", headers=auth_header(admin_token))
    client.get("/exams", headers=auth_header(admin_token))

    assert f"exam:{exam_id}" in store
    assert "exams:all" in store

    delete_response = client.delete(
        f"/exams/{exam_id}",
        headers=auth_header(admin_token)
    )

    assert delete_response.status_code == 200
    assert f"exam:{exam_id}" not in store
    assert "exams:all" not in store