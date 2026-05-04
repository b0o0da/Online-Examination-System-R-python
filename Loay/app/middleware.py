import time
import traceback
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_config import get_logger
from app.metrics import metrics

logger = get_logger("app.middleware")

AUTH_PATHS = {"/auth/login", "/auth/register"}
DEMO_PATHS = {"/demo/error", "/demo/crash"}


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        method = request.method
        path   = request.url.path
        start  = time.time()

        logger.info(f"--> {method} {path}")

        try:
            response = await call_next(request)
        except Exception as exc:
            duration = (time.time() - start) * 1000
            logger.bind(
                error_type=type(exc).__name__,
                traceback=traceback.format_exc(),
            ).critical(f"CRASH {method} {path}: {exc}")
            metrics.record_request(method, path, 500, duration)
            if path not in DEMO_PATHS:
                metrics.record_error(type(exc).__name__, str(exc), path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})

        duration = (time.time() - start) * 1000
        status   = response.status_code

        if status >= 500:
            logger.error(f"<-- {method} {path} {status} ({duration:.0f}ms)")
        elif status >= 400:
            logger.warning(f"<-- {method} {path} {status} ({duration:.0f}ms)")
        else:
            logger.info(f"<-- {method} {path} {status} ({duration:.0f}ms)")

        metrics.record_request(method, path, status, duration)

        if status >= 400 and path not in DEMO_PATHS:
            metrics.record_error(f"HTTP{status}", f"{method} {path}", path)

        if path in AUTH_PATHS:
            event   = "login" if "login" in path else "register"
            success = status < 400
            (logger.info if success else logger.warning)(
                f"Auth {'OK' if success else 'FAIL'}: {event}"
            )
            metrics.record_auth(event, "-", success)

        return response
