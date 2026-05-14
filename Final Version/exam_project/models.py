from datetime import datetime
from enum import Enum as PyEnum

from database import Base
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime,
    Boolean,
    Float,
    JSON,
    UniqueConstraint,
    CheckConstraint,
    Enum,
)
from sqlalchemy.orm import relationship


class UserRole(str, PyEnum):
    ADMIN = "admin"
    STUDENT = "student"


class QuestionType(str, PyEnum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


class AttemptStatus(str, PyEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)

    created_exams = relationship("Exam", back_populates="creator")
    attempts = relationship("ExamAttempt", back_populates="student")
    results = relationship("Result", back_populates="student")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    duration_minutes = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="check_exam_duration_positive"),
    )

    creator = relationship("User", back_populates="created_exams")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")
    attempts = relationship("ExamAttempt", back_populates="exam", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="exam", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(Enum(QuestionType), nullable=False)
    choices = Column(JSON)
    correct_answer = Column(String)
    score = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        CheckConstraint("score > 0", name="check_question_score_positive"),
    )

    exam = relationship("Exam", back_populates="questions")
    answers = relationship("StudentAnswer", back_populates="question", cascade="all, delete-orphan")


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime)
    status = Column(Enum(AttemptStatus), default=AttemptStatus.IN_PROGRESS, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "exam_id", "status", name="unique_student_exam_status"),
    )

    student = relationship("User", back_populates="attempts")
    exam = relationship("Exam", back_populates="attempts")
    answers = relationship("StudentAnswer", back_populates="attempt", cascade="all, delete-orphan")
    result = relationship("Result", back_populates="attempt", uselist=False, cascade="all, delete-orphan")


class StudentAnswer(Base):
    __tablename__ = "student_answers"

    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer = Column(String)
    is_correct = Column(Boolean)
    answered_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="unique_answer_per_attempt"),
    )

    attempt = relationship("ExamAttempt", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False, unique=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    total_score = Column(Integer, nullable=False)
    max_score = Column(Integer, nullable=False)
    percentage = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("total_score >= 0", name="check_total_score_non_negative"),
        CheckConstraint("max_score >= 0", name="check_max_score_non_negative"),
        CheckConstraint("percentage >= 0 AND percentage <= 100", name="check_percentage_range"),
    )

    attempt = relationship("ExamAttempt", back_populates="result")
    student = relationship("User", back_populates="results")
    exam = relationship("Exam", back_populates="results")