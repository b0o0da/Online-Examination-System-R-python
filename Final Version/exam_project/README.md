# 📚 Online Examination System — Project 7

A full-stack online examination system built with **FastAPI**, **SQLite**, **Redis**, and a **vanilla JS frontend**.

---

## 👥 Team & Roles

| Member | Branch | Responsibility |
|--------|--------|----------------|
| Member 1 | `feature/auth` | Authentication & JWT |
| Member 2 | `feature/exams` | Exam & Question CRUD |
| Member 3 | `feature/grading` | Grading & Results |
| Member 4 | `feature/caching` | Redis Caching |
| Member 5 | `feature/logging` | Logging & Monitoring |

---

## 🚀 Features

### Mandatory
- ✅ JWT Authentication (Register / Login)
- ✅ Role-Based Access Control (Admin / Student)
- ✅ Full CRUD for Exams and Questions
- ✅ Timed Exam with Auto-Submit
- ✅ Automatic Grading (MCQ, True/False, Short Answer)
- ✅ Student Results & Analytics
- ✅ Redis Caching with Cache-Aside Pattern
- ✅ Structured Logging with Loguru (3 log files)
- ✅ Live Monitoring Dashboard
- ✅ 32 Pytest Tests

### Bonus
- ✅ Frontend (HTML/CSS/JS Single Page App)
- ✅ Docker + docker-compose

---

## 🗂 Project Structure

```
online-exam-system/
├── main.py              # FastAPI app, all routes
├── models.py            # SQLAlchemy models
├── auth.py              # JWT helpers
├── cache.py             # Redis cache helpers
├── database.py          # DB engine & session
├── logger.py            # Loguru configuration
├── metrics.py           # In-memory metrics store
├── init_db.py           # Create tables
├── create_admin.py      # Seed admin user
├── test_main.py         # 32 pytest tests
├── cache_demo.py        # Cache performance demo
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── .env
├── frontend/
│   └── index.html       # Full SPA (Admin + Student UI)
└── logs/                # Auto-created at runtime
    ├── app.log
    └── errors.log
```

---

## ⚙️ Setup — Local (without Docker)

### 1. Prerequisites
- Python 3.11+
- Redis running on `localhost:6379`

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env if needed
```

### 4. Initialize database & create admin
```bash
python init_db.py
python create_admin.py
# Default admin: username=admin, password=123
```

### 5. Run the server
```bash
uvicorn main:app --reload
```

### 6. Open the frontend
Open `frontend/index.html` in your browser (or serve it):
```bash
# Quick serve with Python
python -m http.server 3000 --directory frontend
```

### 7. API Docs
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

---

## 🐳 Setup — Docker

### Run everything with one command:
```bash
docker-compose up --build
```

This starts:
| Service | URL |
|---------|-----|
| FastAPI API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |
| Redis | localhost:6379 |

### Stop everything:
```bash
docker-compose down
```

### Stop and remove volumes (fresh start):
```bash
docker-compose down -v
```

---

## 🌿 Git Branching Strategy

```
main
└── develop
    ├── feature/auth          ← JWT & user registration
    ├── feature/exams         ← Exam & question CRUD
    ├── feature/grading       ← Auto-grading & results
    ├── feature/caching       ← Redis integration
    ├── feature/logging       ← Loguru & monitoring
    ├── feature/frontend      ← HTML/JS SPA
    └── feature/docker        ← Dockerfile & compose
```

**Workflow:**
1. Each member creates their feature branch from `develop`
2. Open a Pull Request → code review → merge to `develop`
3. `develop` → `main` after testing

---

## 📡 API Endpoints

### Auth
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | Public | Register as student |
| POST | `/auth/login` | Public | Login, get JWT token |

### Exams
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| GET | `/exams` | Any | List all exams (cached) |
| GET | `/exams/{id}` | Any | Get exam by ID |
| POST | `/exams` | Admin | Create exam |
| PUT | `/exams/{id}` | Admin | Update exam |
| DELETE | `/exams/{id}` | Admin | Delete exam |

### Questions
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| GET | `/exams/{id}/questions` | Any | Get exam questions |
| POST | `/questions` | Admin | Add question |
| PUT | `/questions/{id}` | Admin | Update question |
| DELETE | `/questions/{id}` | Admin | Delete question |

### Student Exam Flow
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/exams/start` | Student | Start an exam |
| POST | `/exams/submit` | Student | Submit answers |
| GET | `/results/my` | Student | My results |

### Admin
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| GET | `/results/student/{id}` | Admin | Student results |
| GET | `/analytics` | Admin | Score analytics |
| GET | `/users` | Admin | All users |
| GET | `/metrics` | Admin | System metrics JSON |
| GET | `/dashboard` | Admin | Live HTML dashboard |

---

## 🧪 Running Tests

```bash
pytest test_main.py -v
# 32 tests covering auth, CRUD, grading, error handling
```

---

## 📊 Redis Cache Demo

```bash
python cache_demo.py
# Shows first request (from DB) vs second request (from cache) times
```

---

## 🗄️ Data Models

```
User          → id, username, email, hashed_password, role
Exam          → id, title, description, duration_minutes, created_by
Question      → id, exam_id, question_text, type, choices, correct_answer, score
ExamAttempt   → id, student_id, exam_id, started_at, submitted_at, status
StudentAnswer → id, attempt_id, question_id, answer, is_correct
Result        → id, attempt_id, student_id, exam_id, total_score, max_score, percentage
```

---

## 🔐 Default Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `123` |

> ⚠️ Change the admin password and `SECRET_KEY` before deploying to production.

---

## 📝 Environment Variables

```env
SECRET_KEY=dev-secret-key-change-me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
CACHE_EXPIRE_SECONDS=120
```
