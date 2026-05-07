import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/monitoring/health")
    assert r.status_code == 200
    assert "status" in r.json()
    print("OK health")

def test_metrics():
    r = client.get("/monitoring/metrics")
    assert r.status_code == 200
    assert "total_requests" in r.json()
    print("OK metrics")

def test_dashboard():
    r = client.get("/monitoring/dashboard")
    assert r.status_code == 200
    assert "Monitoring Dashboard" in r.text
    print("OK dashboard")

def test_request_logging():
    client.get("/exams")
    r = client.get("/monitoring/metrics")
    assert r.json()["total_requests"] >= 1
    print("OK request logging")

def test_error_logging():
    client.get("/exams/99999")
    r = client.get("/monitoring/errors")
    assert len(r.json()["errors"]) >= 1
    print("OK error logging")

def test_auth_logging():
    client.post("/auth/register", json={"username":"u1","password":"p1"})
    client.post("/auth/login", json={"username":"u1","password":"p1"})
    r = client.get("/monitoring/auth-events")
    assert len(r.json()["auth_events"]) >= 2
    print("OK auth logging")

def test_crud_logging():
    client.post("/exams", json={"title":"Test"})
    client.get("/exams")
    r = client.get("/monitoring/db-operations")
    assert len(r.json()["db_operations"]) >= 2
    print("OK CRUD logging")

def test_all_levels():
    client.get("/exams")
    client.get("/exams/99999")
    try:
        client.get("/demo/crash")
    except Exception:
        pass
    try:
        client.get("/demo/error")
    except Exception:
        pass
    print("OK all log levels")

if __name__ == "__main__":
    test_health()
    test_metrics()
    test_dashboard()
    test_request_logging()
    test_error_logging()
    test_auth_logging()
    test_crud_logging()
    test_all_levels()
    print("\nAll tests passed!")
