import os, time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.logging_config import setup_logging, get_logger
from app.metrics import metrics
from app.middleware import LoggingMiddleware

setup_logging()
logger = get_logger("app.main")

app = FastAPI(title="Online Examination System")
app.add_middleware(LoggingMiddleware)

users_db = {}
exams_db = {}
results  = []

class UserBase(BaseModel):
    username: str
    password: str

class RegisterReq(UserBase):
    role: str = "student"

class LoginReq(UserBase):
    pass

class ExamReq(BaseModel):
    title: str
    description: str = ""
    duration_minutes: int = 30

class AnswerReq(BaseModel):
    exam_id: int
    answer:  str

def db(op: str, table: str, start: float):
    ms = (time.time() - start) * 1000
    logger.debug(f"DB {op} '{table}' — {ms:.1f}ms")
    logger.bind(db_op=op, table=table).info(f"DB {op} {table} ({ms:.0f}ms)")
    metrics.record_db(op, table, ms)

def require_exam(eid: int):
    if eid not in exams_db:
        raise HTTPException(404, f"Exam {eid} not found")
    return exams_db[eid]

def monitor_list(key: str, attr: str = None, limit: int = 100):
    return {key: getattr(metrics, attr or key)[-limit:]}

@app.post("/auth/register")
def register(req: RegisterReq):
    t = time.time()
    if req.username in users_db:
        raise HTTPException(400, "Username exists")
    users_db[req.username] = req.model_dump()
    db("INSERT", "users", t)
    logger.info(f"Registered: {req.username} (role={req.role})")
    return {"message": "Registered"}

@app.post("/auth/login")
def login(req: LoginReq):
    t    = time.time()
    user = users_db.get(req.username)
    if not user or user["password"] != req.password:
        logger.warning(f"Login FAIL: '{req.username}'")
        raise HTTPException(401, "Invalid credentials")
    db("SELECT", "users", t)
    logger.info(f"Login OK: {req.username}")
    return {"message": "Logged in", "role": user["role"]}

@app.post("/exams")
def create_exam(req: ExamReq):
    t   = time.time()
    eid = len(exams_db) + 1
    exams_db[eid] = {
        "id": eid, **req.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    db("INSERT", "exams", t)
    logger.info(f"Exam created: '{req.title}' id={eid}")
    return {"exam_id": eid}

@app.get("/exams")
def list_exams():
    db("SELECT", "exams", time.time())
    return {"exams": list(exams_db.values())}

@app.get("/exams/{eid}")
def get_exam(eid: int):
    t    = time.time()
    exam = require_exam(eid)
    db("SELECT", "exams", t)
    return exam

@app.put("/exams/{eid}")
def update_exam(eid: int, req: ExamReq):
    t = time.time()
    require_exam(eid).update(req.model_dump())
    db("UPDATE", "exams", t)
    logger.info(f"Exam updated: id={eid}")
    return {"message": "Updated"}

@app.delete("/exams/{eid}")
def delete_exam(eid: int):
    t = time.time()
    require_exam(eid)
    del exams_db[eid]
    db("DELETE", "exams", t)
    logger.info(f"Exam deleted: id={eid}")
    return {"message": "Deleted"}

@app.post("/answers")
def submit_answer(req: AnswerReq):
    t    = time.time()
    exam = require_exam(req.exam_id)
    correct = req.answer.strip().lower() == exam["title"][0].lower()
    score   = 10 if correct else 0
    results.append({"exam_id": req.exam_id, "correct": correct, "score": score})
    db("INSERT", "answers", t)
    logger.info(f"Answer: exam={req.exam_id} correct={correct} score={score}")
    return {"correct": correct, "score": score}

@app.get("/analytics")
def analytics():
    t       = time.time()
    total   = len(results)
    correct = sum(1 for r in results if r["correct"])
    avg     = sum(r["score"] for r in results) / total if total else 0
    db("SELECT", "results", t)
    return {
        "total": total, "correct": correct,
        "accuracy_pct": round(correct/total*100, 1) if total else 0,
        "avg_score": round(avg, 1),
    }

@app.get("/demo/debug")
def demo_debug():
    logger.debug("Demo DEBUG: internal detail")
    return {"level": "DEBUG"}

@app.get("/demo/error")
def demo_error():
    logger.error("Demo ERROR: intentional 500")
    raise HTTPException(500, "Demo error")

@app.get("/demo/crash")
def demo_crash():
    raise RuntimeError("Demo CRITICAL: unhandled crash!")

@app.get("/monitoring/health")
def health():
    return metrics.get_health()

@app.get("/monitoring/metrics")
def get_metrics():
    return metrics.get_summary()

@app.get("/monitoring/requests")
def recent_requests(limit: int = 100):
    return monitor_list("requests", limit=limit)

@app.get("/monitoring/errors")
def recent_errors(limit: int = 50):
    return monitor_list("errors", limit=limit)

@app.get("/monitoring/auth-events")
def auth_events(limit: int = 100):
    return monitor_list("auth_events", limit=limit)

@app.get("/monitoring/db-operations")
def db_operations(limit: int = 100):
    return monitor_list("db_operations", "db_ops", limit)

@app.get("/monitoring/dashboard", response_class=HTMLResponse)
def dashboard():
    path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(path, encoding="utf-8") as f:
        return f.read()
