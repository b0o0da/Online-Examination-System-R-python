from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional
from app.auth import hash_password, verify_password, create_access_token, decode_token, oauth2_scheme

app = FastAPI(title="Online Examination System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

users_db = {}
exams_db = []
questions_db = []
results_db = []


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "student"


class ExamRequest(BaseModel):
    title: str
    description: str = ""
    duration_minutes: int = 30


class QuestionRequest(BaseModel):
    exam_id: int
    question_text: str
    choices: list[str]
    correct_answer: str


class AnswerItem(BaseModel):
    question_id: int
    answer: str


class SubmitExamRequest(BaseModel):
    exam_id: int
    answers: list[AnswerItem]


def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    username = payload.get("sub")
    if username is None or username not in users_db:
        raise HTTPException(status_code=401, detail="User not found")
    return users_db[username]


def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_student(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    return current_user


# ===== AUTH =====

@app.post("/auth/register")
def register(data: RegisterRequest):
    if data.username in users_db:
        raise HTTPException(status_code=400, detail="Username already exists")
    users_db[data.username] = {
        "username": data.username,
        "password": hash_password(data.password),
        "role": data.role
    }
    return {"message": "User registered successfully"}


@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({
        "sub": user["username"],
        "role": user["role"]
    })
    return {"access_token": token, "token_type": "bearer"}


@app.get("/profile")
def profile(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "role": current_user["role"]
    }


# ===== EXAMS =====

@app.post("/exams")
def create_exam(data: ExamRequest, current_user: dict = Depends(require_admin)):
    exam = {
        "id": len(exams_db) + 1,
        "title": data.title,
        "description": data.description,
        "duration_minutes": data.duration_minutes,
        "created_by": current_user["username"]
    }
    exams_db.append(exam)
    return {"message": "Exam created successfully", "exam": exam}


@app.get("/exams")
def get_exams(current_user: dict = Depends(get_current_user)):
    return {"exams": exams_db}


@app.get("/exams/{exam_id}")
def get_exam(exam_id: int, current_user: dict = Depends(get_current_user)):
    exam = next((e for e in exams_db if e["id"] == exam_id), None)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


@app.put("/exams/{exam_id}")
def update_exam(exam_id: int, data: ExamRequest, current_user: dict = Depends(require_admin)):
    exam = next((e for e in exams_db if e["id"] == exam_id), None)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    exam["title"] = data.title
    exam["description"] = data.description
    exam["duration_minutes"] = data.duration_minutes
    return {"message": "Exam updated successfully", "exam": exam}


@app.delete("/exams/{exam_id}")
def delete_exam(exam_id: int, current_user: dict = Depends(require_admin)):
    global exams_db
    exam = next((e for e in exams_db if e["id"] == exam_id), None)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    exams_db = [e for e in exams_db if e["id"] != exam_id]
    return {"message": "Exam deleted successfully"}


# ===== QUESTIONS =====

@app.post("/questions")
def create_question(data: QuestionRequest, current_user: dict = Depends(require_admin)):
    exam = next((e for e in exams_db if e["id"] == data.exam_id), None)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if data.correct_answer not in data.choices:
        raise HTTPException(status_code=400, detail="Correct answer must be one of the choices")
    question = {
        "id": len(questions_db) + 1,
        "exam_id": data.exam_id,
        "question_text": data.question_text,
        "choices": data.choices,
        "correct_answer": data.correct_answer
    }
    questions_db.append(question)
    return {"message": "Question created successfully", "question": question}


@app.get("/exams/{exam_id}/questions")
def get_questions(exam_id: int, current_user: dict = Depends(get_current_user)):
    exam = next((e for e in exams_db if e["id"] == exam_id), None)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    questions = [q for q in questions_db if q["exam_id"] == exam_id]
    # Student مش بيشوف الإجابة الصح
    if current_user["role"] == "student":
        questions = [{k: v for k, v in q.items() if k != "correct_answer"} for q in questions]
    return {"exam_id": exam_id, "questions": questions}


@app.delete("/questions/{question_id}")
def delete_question(question_id: int, current_user: dict = Depends(require_admin)):
    global questions_db
    question = next((q for q in questions_db if q["id"] == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    questions_db = [q for q in questions_db if q["id"] != question_id]
    return {"message": "Question deleted successfully"}


# ===== RESULTS =====

@app.post("/exams/submit")
def submit_exam(data: SubmitExamRequest, current_user: dict = Depends(require_student)):
    exam = next((e for e in exams_db if e["id"] == data.exam_id), None)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    # تحقق إن الستيودنت مش بعت نتيجة قبل كده
    existing = next((r for r in results_db
                     if r["exam_id"] == data.exam_id and r["student"] == current_user["username"]), None)
    if existing:
        raise HTTPException(status_code=400, detail="You already submitted this exam")

    questions = [q for q in questions_db if q["exam_id"] == data.exam_id]
    if not questions:
        raise HTTPException(status_code=400, detail="This exam has no questions")

    total = len(questions)
    correct = 0

    for item in data.answers:
        question = next((q for q in questions if q["id"] == item.question_id), None)
        if question and item.answer.strip().lower() == question["correct_answer"].strip().lower():
            correct += 1

    score = round((correct / total) * 100, 1) if total > 0 else 0

    result = {
        "id": len(results_db) + 1,
        "student": current_user["username"],
        "exam_id": data.exam_id,
        "exam_title": exam["title"],
        "correct": correct,
        "total": total,
        "score": score
    }
    results_db.append(result)
    return {"message": "Exam submitted successfully", "result": result}


@app.get("/results/me")
def get_my_results(current_user: dict = Depends(require_student)):
    my_results = [r for r in results_db if r["student"] == current_user["username"]]
    return {"results": my_results}


@app.get("/results")
def get_all_results(current_user: dict = Depends(require_admin)):
    return {"results": results_db}