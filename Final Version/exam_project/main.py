import time
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import (
    create_access_token,
    get_token_payload,
    hash_password,
    require_role,
    verify_password,
)
from cache import delete_cache, delete_cache_pattern, get_cache, set_cache
from database import SessionLocal
from logger import logger
from metrics import get_metrics, record_auth_event, record_error, record_request
from models import (
    AttemptStatus,
    Exam,
    ExamAttempt,
    Question,
    QuestionType,
    Result,
    StudentAnswer,
    User,
)

app = FastAPI(title="Online Examination System")


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────── Middleware ────────────────────────────

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start = time.time()
    method = request.method
    path = request.url.path

    logger.info(f"Incoming request: {method} {path}")

    response = await call_next(request)

    duration = time.time() - start
    status = response.status_code

    record_request(method, path, status, duration)

    log_msg = f"{method} {path} → {status} ({duration * 1000:.1f}ms)"
    if status >= 500:
        logger.error(log_msg)
        record_error(method, path, status, "Internal Server Error")
    elif status >= 400:
        logger.warning(log_msg)
        record_error(method, path, status, "Client Error")
    else:
        logger.info(log_msg)

    return response


# ─────────────────────────── DB Dependency ──────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────── Schemas ────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ExamCreateRequest(BaseModel):
    title: str
    description: str | None = None
    duration_minutes: int


class ExamUpdateRequest(BaseModel):
    title: str
    description: str | None = None
    duration_minutes: int


class QuestionCreateRequest(BaseModel):
    exam_id: int
    question_text: str
    question_type: QuestionType
    choices: list[str] | None = None
    correct_answer: str | None = None
    score: int = 1


class QuestionUpdateRequest(BaseModel):
    exam_id: int
    question_text: str
    question_type: QuestionType
    choices: list[str] | None = None
    correct_answer: str | None = None
    score: int = 1


class StartExamRequest(BaseModel):
    exam_id: int


class AnswerItem(BaseModel):
    question_id: int
    answer: str


class SubmitExamRequest(BaseModel):
    exam_id: int
    answers: list[AnswerItem]


# ─────────────────────────── Helpers ────────────────────────────────

def validate_question_payload(data):
    if data.score <= 0:
        raise HTTPException(status_code=400, detail="Score must be greater than 0")

    if data.question_type == QuestionType.MCQ:
        if not data.choices or len(data.choices) < 2:
            raise HTTPException(status_code=400, detail="MCQ questions must have at least 2 choices")
        if not data.correct_answer:
            raise HTTPException(status_code=400, detail="MCQ questions must have a correct answer")
        if data.correct_answer not in data.choices:
            raise HTTPException(status_code=400, detail="Correct answer must be one of the provided choices")

    elif data.question_type == QuestionType.TRUE_FALSE:
        allowed_answers = ["true", "false"]
        if data.choices is not None and data.choices != ["true", "false"]:
            raise HTTPException(status_code=400, detail='True/false choices must be ["true", "false"]')
        if not data.correct_answer or data.correct_answer.strip().lower() not in allowed_answers:
            raise HTTPException(status_code=400, detail='True/false correct answer must be "true" or "false"')

    elif data.question_type == QuestionType.SHORT_ANSWER:
        if data.choices:
            raise HTTPException(status_code=400, detail="Short answer questions must not have choices")
        if not data.correct_answer:
            raise HTTPException(status_code=400, detail="Short answer questions must have a correct answer")


def validate_exam_duration(duration_minutes: int):
    if duration_minutes <= 0:
        raise HTTPException(status_code=400, detail="Exam duration must be greater than 0")


def invalidate_exam_cache(exam_id: int):
    delete_cache("exams:all")
    delete_cache(f"exam:{exam_id}")
    delete_cache_pattern(f"exam:{exam_id}:questions:*")


def get_current_user(
    payload: dict = Depends(get_token_payload),
    db: Session = Depends(get_db)
):
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(
    _: dict = Depends(require_role("admin")),
    current_user: User = Depends(get_current_user)
):
    return current_user


def require_student(
    _: dict = Depends(require_role("student")),
    current_user: User = Depends(get_current_user)
):
    return current_user


# ─────────────────────────── Auth Routes ────────────────────────────

@app.post("/auth/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    logger.info(f"Register attempt: username={data.username}, email={data.email}")

    existing_user = db.query(User).filter(
        (User.username == data.username) | (User.email == data.email)
    ).first()

    if existing_user:
        logger.warning(f"Registration failed - duplicate: username={data.username}")
        raise HTTPException(status_code=400, detail="Username or email already exists")

    new_user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role="student"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"User registered successfully: username={data.username}")
    record_auth_event("register", data.username, True)

    return {"message": "User registered successfully"}


@app.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    logger.info(f"Login attempt: username={form_data.username}")

    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Login failed: username={form_data.username}")
        record_auth_event("login", form_data.username, False)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": user.username, "role": user.role})

    logger.info(f"Login successful: username={form_data.username}, role={user.role}")
    record_auth_event("login", form_data.username, True)

    return {"access_token": token, "token_type": "bearer"}


@app.get("/profile")
def profile(current_user: User = Depends(get_current_user)):
    logger.debug(f"Profile accessed: username={current_user.username}")
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role
    }


# ─────────────────────────── Exam Routes ────────────────────────────

@app.post("/exams")
def create_exam(
    data: ExamCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    validate_exam_duration(data.duration_minutes)

    new_exam = Exam(
        title=data.title,
        description=data.description,
        duration_minutes=data.duration_minutes,
        created_by=current_user.id
    )
    db.add(new_exam)
    db.commit()
    db.refresh(new_exam)
    invalidate_exam_cache(new_exam.id)

    logger.info(f"Exam created: id={new_exam.id}, title={new_exam.title}, by={current_user.username}")

    return {
        "message": "Exam created successfully",
        "exam": {
            "id": new_exam.id,
            "title": new_exam.title,
            "description": new_exam.description,
            "duration_minutes": new_exam.duration_minutes,
            "created_by": new_exam.created_by
        }
    }


@app.get("/exams")
def get_exams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        cached_data = get_cache("exams:all")
        if cached_data:
            logger.debug("GET /exams → cache hit")
            return {"source": "cache", "data": cached_data}
    except Exception:
        pass

    exams_from_db = db.query(Exam).all()
    exams = [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "duration_minutes": e.duration_minutes,
            "created_by": e.created_by,
            "created_at": e.created_at.isoformat() if e.created_at else None
        }
        for e in exams_from_db
    ]

    try:
        set_cache("exams:all", exams)
    except Exception:
        pass

    logger.debug(f"GET /exams → database, count={len(exams)}")
    return {"source": "database", "data": exams}


@app.get("/exams/{exam_id}")
def get_exam_by_id(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cache_key = f"exam:{exam_id}"
    try:
        cached_data = get_cache(cache_key)
        if cached_data:
            logger.debug(f"GET /exams/{exam_id} → cache hit")
            return {"source": "cache", "data": cached_data}
    except Exception:
        pass

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        logger.warning(f"Exam not found: id={exam_id}")
        raise HTTPException(status_code=404, detail="Exam not found")

    exam_data = {
        "id": exam.id,
        "title": exam.title,
        "description": exam.description,
        "duration_minutes": exam.duration_minutes,
        "created_by": exam.created_by,
        "created_at": exam.created_at.isoformat() if exam.created_at else None
    }
    try:
        set_cache(cache_key, exam_data)
    except Exception:
        pass

    logger.debug(f"GET /exams/{exam_id} → database")
    return {"source": "database", "data": exam_data}


@app.put("/exams/{exam_id}")
def update_exam(
    exam_id: int,
    data: ExamUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    validate_exam_duration(data.duration_minutes)

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        logger.warning(f"Update exam failed - not found: id={exam_id}")
        raise HTTPException(status_code=404, detail="Exam not found")

    exam.title = data.title
    exam.description = data.description
    exam.duration_minutes = data.duration_minutes
    db.commit()
    db.refresh(exam)
    invalidate_exam_cache(exam_id)

    logger.info(f"Exam updated: id={exam_id}, by={current_user.username}")

    return {
        "message": "Exam updated successfully",
        "exam": {
            "id": exam.id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "created_by": exam.created_by,
            "created_at": exam.created_at.isoformat() if exam.created_at else None
        }
    }


@app.delete("/exams/{exam_id}")
def delete_exam(
    exam_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        logger.warning(f"Delete exam failed - not found: id={exam_id}")
        raise HTTPException(status_code=404, detail="Exam not found")

    db.delete(exam)
    db.commit()
    invalidate_exam_cache(exam_id)

    logger.info(f"Exam deleted: id={exam_id}, by={current_user.username}")
    return {"message": "Exam deleted successfully"}


# ─────────────────────────── Question Routes ────────────────────────

@app.post("/questions")
def create_question(
    data: QuestionCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == data.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    validate_question_payload(data)

    new_question = Question(
        exam_id=data.exam_id,
        question_text=data.question_text,
        question_type=data.question_type,
        choices=data.choices,
        correct_answer=data.correct_answer,
        score=data.score
    )
    db.add(new_question)
    db.commit()
    db.refresh(new_question)
    invalidate_exam_cache(data.exam_id)

    logger.info(f"Question created: id={new_question.id}, exam_id={data.exam_id}, by={current_user.username}")

    return {
        "message": "Question created successfully",
        "question": {
            "id": new_question.id,
            "exam_id": new_question.exam_id,
            "question_text": new_question.question_text,
            "question_type": new_question.question_type.value,
            "choices": new_question.choices,
            "correct_answer": new_question.correct_answer,
            "score": new_question.score
        }
    }


@app.get("/exams/{exam_id}/questions")
def get_exam_questions(
    exam_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    cache_key = f"exam:{exam_id}:questions:admin"
    cached_data = get_cache(cache_key)
    if cached_data:
        logger.debug(f"GET /exams/{exam_id}/questions → cache hit")
        return {"source": "cache", "data": cached_data}

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = db.query(Question).filter(Question.exam_id == exam_id).all()
    data = [
        {
            "id": q.id,
            "exam_id": q.exam_id,
            "question_text": q.question_text,
            "question_type": q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type),
            "choices": q.choices,
            "correct_answer": q.correct_answer,
            "score": q.score
        }
        for q in questions
    ]
    payload = {"exam_id": exam_id, "questions": data}
    set_cache(cache_key, payload)

    logger.debug(f"GET /exams/{exam_id}/questions → database")
    return {"source": "database", "data": payload}


@app.get("/student/exams/{exam_id}/questions")
def get_student_exam_questions(
    exam_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    cache_key = f"exam:{exam_id}:questions:student"
    cached_data = get_cache(cache_key)
    if cached_data:
        return {"source": "cache", "data": cached_data}

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = db.query(Question).filter(Question.exam_id == exam_id).all()
    data = [
        {
            "id": q.id,
            "exam_id": q.exam_id,
            "question_text": q.question_text,
            "question_type": q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type),
            "choices": q.choices
        }
        for q in questions
    ]
    payload = {"exam_id": exam_id, "questions": data}
    set_cache(cache_key, payload)

    return {"source": "database", "data": payload}


@app.get("/questions/{question_id}")
def get_question_by_id(
    question_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    return {
        "id": question.id,
        "exam_id": question.exam_id,
        "question_text": question.question_text,
        "question_type": question.question_type.value,
        "choices": question.choices,
        "correct_answer": question.correct_answer,
        "score": question.score
    }


@app.put("/questions/{question_id}")
def update_question(
    question_id: int,
    data: QuestionUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    old_exam_id = question.exam_id
    exam = db.query(Exam).filter(Exam.id == data.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    validate_question_payload(data)

    question.exam_id = data.exam_id
    question.question_text = data.question_text
    question.question_type = data.question_type
    question.choices = data.choices
    question.correct_answer = data.correct_answer
    question.score = data.score

    db.commit()
    db.refresh(question)

    invalidate_exam_cache(old_exam_id)
    if data.exam_id != old_exam_id:
        invalidate_exam_cache(data.exam_id)

    logger.info(f"Question updated: id={question_id}, by={current_user.username}")

    return {
        "message": "Question updated successfully",
        "question": {
            "id": question.id,
            "exam_id": question.exam_id,
            "question_text": question.question_text,
            "question_type": question.question_type.value,
            "choices": question.choices,
            "correct_answer": question.correct_answer,
            "score": question.score
        }
    }


@app.delete("/questions/{question_id}")
def delete_question(
    question_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    exam_id = question.exam_id
    db.delete(question)
    db.commit()
    invalidate_exam_cache(exam_id)

    logger.info(f"Question deleted: id={question_id}, by={current_user.username}")
    return {"message": "Question deleted successfully"}


# ─────────────────────────── Student Exam Routes ────────────────────

@app.post("/student/exams/start")
def start_exam(
    data: StartExamRequest,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == data.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    existing_attempt = db.query(ExamAttempt).filter(
        ExamAttempt.student_id == current_user.id,
        ExamAttempt.exam_id == data.exam_id,
        ExamAttempt.status == AttemptStatus.IN_PROGRESS
    ).first()

    if existing_attempt:
        logger.info(f"Exam already started: student={current_user.username}, exam_id={data.exam_id}")
        return {
            "message": "Exam attempt already started",
            "attempt_id": existing_attempt.id,
            "exam_id": existing_attempt.exam_id,
            "status": existing_attempt.status
        }

    new_attempt = ExamAttempt(
        student_id=current_user.id,
        exam_id=data.exam_id,
        status=AttemptStatus.IN_PROGRESS
    )
    db.add(new_attempt)
    db.commit()
    db.refresh(new_attempt)

    logger.info(f"Exam started: student={current_user.username}, exam_id={data.exam_id}, attempt_id={new_attempt.id}")

    return {
        "message": "Exam started successfully",
        "attempt_id": new_attempt.id,
        "exam_id": new_attempt.exam_id,
        "status": new_attempt.status,
        "started_at": new_attempt.started_at.isoformat() if new_attempt.started_at else None
    }


@app.post("/student/exams/submit")
def submit_exam(
    data: SubmitExamRequest,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == data.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    attempt = db.query(ExamAttempt).filter(
        ExamAttempt.student_id == current_user.id,
        ExamAttempt.exam_id == data.exam_id,
        ExamAttempt.status == AttemptStatus.IN_PROGRESS
    ).first()

    if not attempt:
        raise HTTPException(status_code=404, detail="No active exam attempt found")

    exam_end_time = attempt.started_at + timedelta(minutes=exam.duration_minutes)
    if datetime.utcnow() > exam_end_time:
        attempt.status = AttemptStatus.SUBMITTED
        attempt.submitted_at = datetime.utcnow()
        db.commit()
        logger.warning(f"Exam submission rejected - time over: student={current_user.username}, exam_id={data.exam_id}")
        raise HTTPException(status_code=400, detail="Exam time is over")

    questions = db.query(Question).filter(Question.exam_id == data.exam_id).all()
    if not questions:
        raise HTTPException(status_code=400, detail="This exam has no questions")

    question_map = {q.id: q for q in questions}
    max_score = sum(q.score for q in questions)
    total_score = 0

    for item in data.answers:
        question = question_map.get(item.question_id)
        if not question:
            raise HTTPException(
                status_code=400,
                detail=f"Question {item.question_id} does not belong to this exam"
            )

        existing_answer = db.query(StudentAnswer).filter(
            StudentAnswer.attempt_id == attempt.id,
            StudentAnswer.question_id == item.question_id
        ).first()
        if existing_answer:
            raise HTTPException(status_code=400, detail=f"Question {item.question_id} already answered")

        is_correct = False
        if question.correct_answer is not None:
            is_correct = item.answer.strip().lower() == question.correct_answer.strip().lower()

        if is_correct:
            total_score += question.score

        db.add(StudentAnswer(
            attempt_id=attempt.id,
            question_id=item.question_id,
            answer=item.answer,
            is_correct=is_correct
        ))

    attempt.status = AttemptStatus.SUBMITTED
    attempt.submitted_at = datetime.utcnow()

    percentage = (total_score / max_score) * 100 if max_score > 0 else 0

    existing_result = db.query(Result).filter(Result.attempt_id == attempt.id).first()
    if existing_result:
        raise HTTPException(status_code=400, detail="Result already exists for this attempt")

    result = Result(
        attempt_id=attempt.id,
        student_id=current_user.id,
        exam_id=data.exam_id,
        total_score=total_score,
        max_score=max_score,
        percentage=percentage
    )
    db.add(result)
    db.commit()
    db.refresh(attempt)
    db.refresh(result)

    set_cache(
        f"result:student:{current_user.id}:exam:{data.exam_id}",
        {
            "attempt_id": result.attempt_id,
            "student_id": result.student_id,
            "exam_id": result.exam_id,
            "total_score": result.total_score,
            "max_score": result.max_score,
            "percentage": result.percentage,
            "created_at": result.created_at.isoformat() if result.created_at else None
        }
    )

    logger.info(
        f"Exam submitted: student={current_user.username}, exam_id={data.exam_id}, "
        f"score={total_score}/{max_score} ({percentage:.1f}%)"
    )

    return {
        "message": "Exam submitted successfully",
        "result": {
            "attempt_id": result.attempt_id,
            "student_id": result.student_id,
            "exam_id": result.exam_id,
            "total_score": result.total_score,
            "max_score": result.max_score,
            "percentage": result.percentage
        }
    }


@app.get("/student/exams/{exam_id}/result")
def get_student_result(
    exam_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    cache_key = f"result:student:{current_user.id}:exam:{exam_id}"
    cached_data = get_cache(cache_key)
    if cached_data:
        logger.debug(f"Result cache hit: student={current_user.username}, exam_id={exam_id}")
        return cached_data

    result = db.query(Result).filter(
        Result.student_id == current_user.id,
        Result.exam_id == exam_id
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    payload = {
        "attempt_id": result.attempt_id,
        "student_id": result.student_id,
        "exam_id": result.exam_id,
        "total_score": result.total_score,
        "max_score": result.max_score,
        "percentage": result.percentage,
        "created_at": result.created_at.isoformat() if result.created_at else None
    }
    set_cache(cache_key, payload)
    return payload


# ─────────────────────────── Admin Results ──────────────────────────

@app.get("/results")
def get_all_results(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    results = db.query(Result).all()
    data = [
        {
            "attempt_id": r.attempt_id,
            "student_id": r.student_id,
            "exam_id": r.exam_id,
            "total_score": r.total_score,
            "max_score": r.max_score,
            "percentage": r.percentage,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in results
    ]
    logger.info(f"Admin fetched all results: count={len(data)}, by={current_user.username}")
    return {"results": data}


@app.get("/results/student/{student_id}")
def get_results_by_student(
    student_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    results = db.query(Result).filter(Result.student_id == student_id).all()
    data = [
        {
            "attempt_id": r.attempt_id,
            "exam_id": r.exam_id,
            "total_score": r.total_score,
            "max_score": r.max_score,
            "percentage": r.percentage,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in results
    ]
    logger.info(f"Admin fetched results for student_id={student_id}, by={current_user.username}")
    return {"student_id": student_id, "username": student.username, "results": data}


# ─────────────────────────── Analytics ──────────────────────────────

@app.get("/analytics")
def get_analytics(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Basic analytics: scores and averages per exam."""
    exams = db.query(Exam).all()
    analytics = []

    for exam in exams:
        results = db.query(Result).filter(Result.exam_id == exam.id).all()
        total_attempts = len(results)

        if total_attempts == 0:
            avg_score = 0
            avg_percentage = 0
            pass_rate = 0
        else:
            avg_score = round(sum(r.total_score for r in results) / total_attempts, 2)
            avg_percentage = round(sum(r.percentage for r in results) / total_attempts, 2)
            pass_rate = round(len([r for r in results if r.percentage >= 50]) / total_attempts * 100, 2)

        analytics.append({
            "exam_id": exam.id,
            "exam_title": exam.title,
            "total_attempts": total_attempts,
            "average_score": avg_score,
            "average_percentage": avg_percentage,
            "pass_rate_percent": pass_rate,
            "max_possible_score": results[0].max_score if results else None
        })

    total_students = db.query(User).filter(User.role == "student").count()
    total_exams = len(exams)
    total_results = db.query(Result).count()

    logger.info(f"Analytics fetched by={current_user.username}")

    return {
        "summary": {
            "total_students": total_students,
            "total_exams": total_exams,
            "total_submissions": total_results
        },
        "per_exam": analytics
    }


# ─────────────────────────── Monitoring ─────────────────────────────

@app.get("/metrics")
def get_system_metrics(current_user: User = Depends(require_admin)):
    """JSON metrics endpoint."""
    return get_metrics()


@app.get("/dashboard", response_class=HTMLResponse)
def monitoring_dashboard(current_user: User = Depends(require_admin)):
    """Live monitoring dashboard — auto-refreshes every 5 seconds."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Online Exam – Dashboard</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:24px}
    h1{font-size:1.6rem;font-weight:700;color:#f8fafc;margin-bottom:4px}
    .subtitle{color:#94a3b8;font-size:.85rem;margin-bottom:24px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px}
    .card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
    .card .label{font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}
    .card .value{font-size:2rem;font-weight:700;color:#38bdf8}
    .card .sub{font-size:.8rem;color:#64748b;margin-top:4px}
    .card.warn .value{color:#fb923c}
    .card.good .value{color:#34d399}
    .section{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155;margin-bottom:20px}
    .section h2{font-size:1rem;font-weight:600;color:#cbd5e1;margin-bottom:14px;border-bottom:1px solid #334155;padding-bottom:10px}
    table{width:100%;border-collapse:collapse;font-size:.82rem}
    th{text-align:left;color:#64748b;font-weight:600;padding:6px 10px;border-bottom:1px solid #334155}
    td{padding:8px 10px;border-bottom:1px solid #0f172a;color:#cbd5e1}
    tr:hover td{background:#0f172a}
    .badge{display:inline-block;padding:2px 8px;border-radius:9999px;font-size:.72rem;font-weight:600}
    .badge.ok{background:#14532d;color:#4ade80}
    .badge.err{background:#7f1d1d;color:#f87171}
    .badge.warn{background:#78350f;color:#fbbf24}
    .status-bar{display:flex;align-items:center;gap:8px;margin-bottom:20px;font-size:.82rem;color:#64748b}
    .dot{width:8px;height:8px;border-radius:50%;background:#34d399;animation:pulse 2s infinite}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    .two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    @media(max-width:700px){.two-col{grid-template-columns:1fr}}
    code{background:#0f172a;padding:2px 6px;border-radius:4px;font-size:.78rem}
  </style>
</head>
<body>
  <h1>🖥️ Online Exam — Monitoring Dashboard</h1>
  <p class="subtitle">Real-time application metrics &amp; logs</p>
  <div class="status-bar">
    <div class="dot"></div>
    <span>System Online</span>&nbsp;|&nbsp;
    <span id="last-updated">Auto-refreshes every 5s</span>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Total Requests</div><div class="value" id="total-req">–</div></div>
    <div class="card warn"><div class="label">Total Errors</div><div class="value" id="total-err">–</div></div>
    <div class="card"><div class="label">Error Rate</div><div class="value" id="error-rate">–</div><div class="sub">% of all requests</div></div>
    <div class="card good"><div class="label">Avg Response</div><div class="value" id="avg-resp">–</div><div class="sub">ms</div></div>
    <div class="card"><div class="label">Max Response</div><div class="value" id="max-resp">–</div><div class="sub">ms</div></div>
  </div>

  <div class="two-col">
    <div class="section">
      <h2>📊 Status Code Breakdown</h2>
      <table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody id="status-table"></tbody></table>
    </div>
    <div class="section">
      <h2>🔥 Top Endpoints</h2>
      <table><thead><tr><th>Endpoint</th><th>Hits</th></tr></thead><tbody id="endpoints-table"></tbody></table>
    </div>
  </div>

  <div class="two-col">
    <div class="section">
      <h2>🚨 Recent Errors</h2>
      <table><thead><tr><th>Time</th><th>Method</th><th>Path</th><th>Status</th></tr></thead><tbody id="errors-table"></tbody></table>
    </div>
    <div class="section">
      <h2>🔑 Recent Auth Events</h2>
      <table><thead><tr><th>Time</th><th>Event</th><th>User</th><th>Result</th></tr></thead><tbody id="auth-table"></tbody></table>
    </div>
  </div>

  <script>
    const token = new URLSearchParams(window.location.search).get('token') || localStorage.getItem('dash_token');
    if(token) localStorage.setItem('dash_token', token);

    function badge(code){
      if(code<300) return `<span class="badge ok">${code}</span>`;
      if(code<400) return `<span class="badge warn">${code}</span>`;
      return `<span class="badge err">${code}</span>`;
    }

    async function refresh(){
      try{
        const res = await fetch('/metrics',{headers:{Authorization:'Bearer '+token}});
        if(!res.ok){document.getElementById('last-updated').textContent='⚠ Auth error – add ?token=YOUR_ADMIN_TOKEN to URL';return;}
        const d = await res.json();

        document.getElementById('total-req').textContent = d.total_requests;
        document.getElementById('total-err').textContent = d.total_errors;
        document.getElementById('error-rate').textContent = d.error_rate_percent+'%';
        document.getElementById('avg-resp').textContent = d.avg_response_ms;
        document.getElementById('max-resp').textContent = d.max_response_ms;

        document.getElementById('status-table').innerHTML =
          Object.entries(d.status_counts).sort((a,b)=>b[1]-a[1])
            .map(([c,n])=>`<tr><td>${badge(+c)}</td><td>${n}</td></tr>`).join('');

        document.getElementById('endpoints-table').innerHTML =
          Object.entries(d.top_endpoints)
            .map(([ep,n])=>`<tr><td><code>${ep}</code></td><td>${n}</td></tr>`).join('');

        const errs = d.recent_errors;
        document.getElementById('errors-table').innerHTML = errs.length
          ? errs.slice().reverse().map(e=>{
              const t=e.time.split('T')[1].split('.')[0];
              return `<tr><td>${t}</td><td>${e.method}</td><td>${e.path}</td><td>${badge(e.status_code)}</td></tr>`;
            }).join('')
          : '<tr><td colspan="4" style="color:#475569">No errors yet 🎉</td></tr>';

        const auths = d.recent_auth_events;
        document.getElementById('auth-table').innerHTML = auths.length
          ? auths.slice().reverse().map(a=>{
              const t=a.time.split('T')[1].split('.')[0];
              const b=a.success?'<span class="badge ok">success</span>':'<span class="badge err">failed</span>';
              return `<tr><td>${t}</td><td>${a.event}</td><td>${a.username}</td><td>${b}</td></tr>`;
            }).join('')
          : '<tr><td colspan="4" style="color:#475569">No auth events yet</td></tr>';

        document.getElementById('last-updated').textContent='Last updated: '+new Date().toLocaleTimeString();
      }catch(e){
        document.getElementById('last-updated').textContent='⚠ Error fetching metrics';
      }
    }

    refresh();
    setInterval(refresh,5000);
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)

@app.get("/users")
def get_all_students(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    students = db.query(User).filter(User.role == "student").all()
    data = [
        {
            "id": s.id,
            "username": s.username,
            "email": s.email,
            "role": s.role
        }
        for s in students
    ]
    logger.info(f"Admin fetched all students: count={len(data)}, by={current_user.username}")
    return {"users": data}
