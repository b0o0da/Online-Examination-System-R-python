import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ===== AUTH TESTS =====

def test_register_student():
    response = client.post("/auth/register", json={
        "username": "student1",
        "password": "123456",
        "role": "student"
    })
    assert response.status_code == 200
    assert response.json()["message"] == "User registered successfully"


def test_register_admin():
    response = client.post("/auth/register", json={
        "username": "admin1",
        "password": "123456",
        "role": "admin"
    })
    assert response.status_code == 200


def test_register_duplicate():
    client.post("/auth/register", json={"username": "user2", "password": "123", "role": "student"})
    response = client.post("/auth/register", json={"username": "user2", "password": "123", "role": "student"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists"


def test_login_success():
    client.post("/auth/register", json={"username": "user3", "password": "123456", "role": "student"})
    response = client.post("/auth/login", data={"username": "user3", "password": "123456"})
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_login_wrong_password():
    client.post("/auth/register", json={"username": "user4", "password": "123456", "role": "student"})
    response = client.post("/auth/login", data={"username": "user4", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_login_invalid_token():
    response = client.get("/profile", headers={"Authorization": "Bearer invalidtoken"})
    assert response.status_code == 401


def test_access_without_token():
    response = client.get("/profile")
    assert response.status_code == 401


# ===== ROLE-BASED TESTS =====

def get_token(username, password):
    r = client.post("/auth/login", data={"username": username, "password": password})
    return r.json()["access_token"]


def test_student_cannot_create_exam():
    client.post("/auth/register", json={"username": "stu5", "password": "123", "role": "student"})
    token = get_token("stu5", "123")
    response = client.post("/exams",
        json={"title": "Math", "description": "test", "duration_minutes": 30},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_student_cannot_delete_exam():
    client.post("/auth/register", json={"username": "stu6", "password": "123", "role": "student"})
    token = get_token("stu6", "123")
    response = client.delete("/exams/1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


# ===== CRUD TESTS =====

def test_admin_create_exam():
    client.post("/auth/register", json={"username": "adm2", "password": "123", "role": "admin"})
    token = get_token("adm2", "123")
    response = client.post("/exams",
        json={"title": "Math Exam", "description": "Basic math", "duration_minutes": 60},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["exam"]["title"] == "Math Exam"


def test_get_all_exams():
    client.post("/auth/register", json={"username": "stu7", "password": "123", "role": "student"})
    token = get_token("stu7", "123")
    response = client.get("/exams", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "exams" in response.json()


def test_get_exam_by_id():
    client.post("/auth/register", json={"username": "adm3", "password": "123", "role": "admin"})
    token = get_token("adm3", "123")
    create = client.post("/exams",
        json={"title": "Science", "description": "", "duration_minutes": 45},
        headers={"Authorization": f"Bearer {token}"}
    )
    exam_id = create.json()["exam"]["id"]
    response = client.get(f"/exams/{exam_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["id"] == exam_id


def test_update_exam():
    client.post("/auth/register", json={"username": "adm4", "password": "123", "role": "admin"})
    token = get_token("adm4", "123")
    create = client.post("/exams",
        json={"title": "Old Title", "description": "", "duration_minutes": 30},
        headers={"Authorization": f"Bearer {token}"}
    )
    exam_id = create.json()["exam"]["id"]
    response = client.put(f"/exams/{exam_id}",
        json={"title": "New Title", "description": "updated", "duration_minutes": 60},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["exam"]["title"] == "New Title"


def test_delete_exam():
    client.post("/auth/register", json={"username": "adm5", "password": "123", "role": "admin"})
    token = get_token("adm5", "123")
    create = client.post("/exams",
        json={"title": "To Delete", "description": "", "duration_minutes": 30},
        headers={"Authorization": f"Bearer {token}"}
    )
    exam_id = create.json()["exam"]["id"]
    response = client.delete(f"/exams/{exam_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["message"] == "Exam deleted successfully"


# ===== EDGE CASES =====

def test_get_nonexistent_exam():
    client.post("/auth/register", json={"username": "stu8", "password": "123", "role": "student"})
    token = get_token("stu8", "123")
    response = client.get("/exams/9999", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Exam not found"


def test_delete_nonexistent_exam():
    client.post("/auth/register", json={"username": "adm6", "password": "123", "role": "admin"})
    token = get_token("adm6", "123")
    response = client.delete("/exams/9999", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404