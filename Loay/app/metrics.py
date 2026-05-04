import time
from datetime import datetime, timezone


class MetricsCollector:
    MAX = 2000

    def __init__(self):
        self._start        = time.time()
        self.requests      = []
        self.errors        = []
        self.auth_events   = []
        self.db_ops        = []
        self.endpoint_hits = {}
        self.status_counts = {}

    def _now(self):
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _append(self, lst, item):
        lst.append(item)
        if len(lst) > self.MAX:
            del lst[:-self.MAX]

    def record_request(self, method, endpoint, status, duration_ms):
        self._append(self.requests, {
            "time": self._now(), "method": method,
            "endpoint": endpoint, "status": status,
            "duration_ms": round(duration_ms, 2),
        })
        self.endpoint_hits[f"{method} {endpoint}"] = self.endpoint_hits.get(f"{method} {endpoint}", 0) + 1
        self.status_counts[str(status)] = self.status_counts.get(str(status), 0) + 1

    def record_error(self, error_type, message, endpoint="-"):
        self._append(self.errors, {
            "time": self._now(), "type": error_type,
            "message": message, "endpoint": endpoint,
        })

    def record_auth(self, event, username, success):
        self._append(self.auth_events, {
            "time": self._now(), "event": event,
            "username": username, "success": success,
        })

    def record_db(self, operation, table, duration_ms):
        self._append(self.db_ops, {
            "time": self._now(), "operation": operation,
            "table": table, "duration_ms": round(duration_ms, 2),
        })

    def _rate(self, total, errors):
        return round(errors / total * 100, 2) if total else 0

    def get_summary(self):
        total = len(self.requests)
        errors = len(self.errors)
        return {
            "total_requests":       total,
            "total_errors":         errors,
            "avg_response_time_ms": round(sum(r["duration_ms"] for r in self.requests) / total, 2) if total else 0,
            "error_rate_percent":   self._rate(total, errors),
            "uptime_seconds":       round(time.time() - self._start, 1),
            "endpoint_counts":      self.endpoint_hits,
            "status_counts":        self.status_counts,
        }

    def get_health(self):
        total  = len(self.requests)
        errors = len(self.errors)
        rate   = self._rate(total, errors)
        status = "healthy" if rate < 1 else ("degraded" if rate < 5 else "unhealthy")
        return {
            "status":             status,
            "status_code":        503 if status == "unhealthy" else 200,
            "uptime_seconds":     round(time.time() - self._start, 1),
            "total_requests":     total,
            "total_errors":       errors,
            "error_rate_percent": rate,
            "timestamp":          self._now(),
        }


metrics = MetricsCollector()
