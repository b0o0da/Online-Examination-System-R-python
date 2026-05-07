import sys
import json
from loguru import logger as _loguru


def _json_sink(message):
    record = message.record
    entry = {
        "timestamp": record["time"].isoformat().replace("+00:00", "Z"),
        "level":     record["level"].name,
        "logger":    record["extra"].get("logger", record["name"]),
        "message":   record["message"],
    }
    for k, v in record["extra"].items():
        if k != "logger":
            entry[k] = v
    if record["exception"]:
        entry["exception"] = str(record["exception"])
    sys.stdout.write(json.dumps(entry, default=str) + "\n")
    sys.stdout.flush()


def setup_logging():
    _loguru.remove()
    _loguru.add(_json_sink, level="DEBUG")


def get_logger(name: str):
    return _loguru.bind(logger=name)
