from collections import defaultdict, deque
from datetime import datetime
import threading

_lock = threading.Lock()

# Counters
_request_counts: dict[str, int] = defaultdict(int)          # "METHOD /path" -> count
_status_counts: dict[int, int] = defaultdict(int)           # status_code -> count
_error_counts: dict[str, int] = defaultdict(int)            # "METHOD /path" -> error count

# Response times (keep last 1000)
_response_times: deque = deque(maxlen=1000)   # list of floats (seconds)

# Recent errors (keep last 50)
_recent_errors: deque = deque(maxlen=50)

# Auth events
_auth_events: deque = deque(maxlen=100)


def record_request(method: str, path: str, status_code: int, duration: float):
    key = f"{method} {path}"
    with _lock:
        _request_counts[key] += 1
        _status_counts[status_code] += 1
        _response_times.append(duration)
        if status_code >= 400:
            _error_counts[key] += 1


def record_error(method: str, path: str, status_code: int, detail: str):
    with _lock:
        _recent_errors.append({
            "time": datetime.utcnow().isoformat(),
            "method": method,
            "path": path,
            "status_code": status_code,
            "detail": detail
        })


def record_auth_event(event_type: str, username: str, success: bool):
    with _lock:
        _auth_events.append({
            "time": datetime.utcnow().isoformat(),
            "event": event_type,
            "username": username,
            "success": success
        })


def get_metrics() -> dict:
    with _lock:
        times = list(_response_times)
        avg_response = round(sum(times) / len(times) * 1000, 2) if times else 0
        max_response = round(max(times) * 1000, 2) if times else 0
        min_response = round(min(times) * 1000, 2) if times else 0

        total_requests = sum(_request_counts.values())
        total_errors = sum(_error_counts.values())
        error_rate = round((total_errors / total_requests * 100), 2) if total_requests else 0

        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate_percent": error_rate,
            "avg_response_ms": avg_response,
            "max_response_ms": max_response,
            "min_response_ms": min_response,
            "status_counts": dict(_status_counts),
            "top_endpoints": dict(sorted(_request_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            "recent_errors": list(_recent_errors)[-10:],
            "recent_auth_events": list(_auth_events)[-10:],
        }
