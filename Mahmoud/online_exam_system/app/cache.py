import json
import os

import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
CACHE_EXPIRE_SECONDS = int(os.getenv("CACHE_EXPIRE_SECONDS", "120"))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)


def get_cache(key: str):
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception:
        return None


def set_cache(key: str, value, expire: int = CACHE_EXPIRE_SECONDS):
    try:
        redis_client.setex(key, expire, json.dumps(value))
    except Exception:
        pass


def delete_cache(key: str):
    try:
        redis_client.delete(key)
    except Exception:
        pass


def delete_cache_pattern(pattern: str):
    try:
        keys = list(redis_client.scan_iter(match=pattern))
        if keys:
            redis_client.delete(*keys)
    except Exception:
        pass