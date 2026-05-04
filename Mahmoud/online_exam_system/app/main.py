from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        raise HTTPException(
            status_code=400,
            detail="Exam duration must be greater than 0"
        )


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


@app.post("/auth/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(
        (User.username == data.username) | (User.email == data.email)
    ).first()

    if existing_user:
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

    return {"message": "User registered successfully"}


@app.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({
        "sub": user.username,
        "role": user.role
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@app.get("/profile")
def profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role
    }


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
            return {
                "source": "cache",
                "data": cached_data
            }
    except Exception:
        pass

    exams_from_db = db.query(Exam).all()

    exams = []
    for exam in exams_from_db:
        exams.append({
            "id": exam.id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "created_by": exam.created_by,
            "created_at": exam.created_at.isoformat() if exam.created_at else None
        })

    try:
        set_cache("exams:all", exams)
    except Exception:
        pass

    return {
        "source": "database",
        "data": exams
    }

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
            return {
                "source": "cache",
                "data": cached_data
            }
    except Exception:
        pass

    exam = db.query(Exam).filter(Exam.id == exam_id).first()

    if not exam:
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

    return {
        "source": "database",
        "data": exam_data
    }




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
        raise HTTPException(status_code=404, detail="Exam not found")

    exam.title = data.title
    exam.description = data.description
    exam.duration_minutes = data.duration_minutes

    db.commit()
    db.refresh(exam)

    invalidate_exam_cache(exam_id)

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
        raise HTTPException(status_code=404, detail="Exam not found")

    db.delete(exam)
    db.commit()

    invalidate_exam_cache(exam_id)

    return {
        "message": "Exam deleted successfully"
    }






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
        return {
            "source": "cache",
            "data": cached_data
        }

    exam = db.query(Exam).filter(Exam.id == exam_id).first()

    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = db.query(Question).filter(Question.exam_id == exam_id).all()

    data = []
    for question in questions:
        data.append({
            "id": question.id,
            "exam_id": question.exam_id,
            "question_text": question.question_text,
            "question_type": question.question_type.value if hasattr(question.question_type, "value") else str(question.question_type),
            "choices": question.choices,
            "correct_answer": question.correct_answer,
            "score": question.score
        })

    payload = {
        "exam_id": exam_id,
        "questions": data
    }

    set_cache(cache_key, payload)

    return {
        "source": "database",
        "data": payload
    }




@app.get("/student/exams/{exam_id}/questions")
def get_student_exam_questions(
    exam_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    cache_key = f"exam:{exam_id}:questions:student"

    cached_data = get_cache(cache_key)
    if cached_data:
        return {
            "source": "cache",
            "data": cached_data
        }

    exam = db.query(Exam).filter(Exam.id == exam_id).first()

    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = db.query(Question).filter(Question.exam_id == exam_id).all()

    data = []
    for question in questions:
        data.append({
            "id": question.id,
            "exam_id": question.exam_id,
            "question_text": question.question_text,
            "question_type": question.question_type.value if hasattr(question.question_type, "value") else str(question.question_type),
            "choices": question.choices
        })

    payload = {
        "exam_id": exam_id,
        "questions": data
    }

    set_cache(cache_key, payload)

    return {
        "source": "database",
        "data": payload
    }



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

    return {
        "message": "Question deleted successfully"
    }



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
            raise HTTPException(
                status_code=400,
                detail=f"Question {item.question_id} already answered"
            )

        is_correct = False
        if question.correct_answer is not None:
            is_correct = item.answer.strip().lower() == question.correct_answer.strip().lower()

        if is_correct:
            total_score += question.score

        student_answer = StudentAnswer(
            attempt_id=attempt.id,
            question_id=item.question_id,
            answer=item.answer,
            is_correct=is_correct
        )
        db.add(student_answer)

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



@app.get("/results")
def get_all_results(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    results = db.query(Result).all()

    data = []
    for result in results:
        data.append({
            "attempt_id": result.attempt_id,
            "student_id": result.student_id,
            "exam_id": result.exam_id,
            "total_score": result.total_score,
            "max_score": result.max_score,
            "percentage": result.percentage,
            "created_at": result.created_at.isoformat() if result.created_at else None
        })

    return {
        "results": data
    }



#http://127.0.0.1:8000/docs
#python -m uvicorn app.main:app --reload
#cd "D:\codes\Online-Examination-System-R-python\Mahmoud\online_exam_system\app"
#uvicorn main:app --reload