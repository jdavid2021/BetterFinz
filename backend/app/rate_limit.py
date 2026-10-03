import hashlib
import logging
from functools import lru_cache

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger("finleash.rate_limit")


@lru_cache
def redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _client_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(host.encode()).hexdigest()[:24]


def enforce_rate_limit(
    request: Request,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    key = f"finleash:rate:{bucket}:{_client_key(request)}"
    try:
        client = redis_client()
        with client.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, window_seconds, nx=True)
            count, _ = pipeline.execute()
    except RedisError as exc:
        if settings.is_secure_environment:
            raise HTTPException(503, "Request protection is temporarily unavailable.") from exc
        logger.warning("Redis rate limiting unavailable in development: %s", type(exc).__name__)
        return
    if int(count) > limit:
        raise HTTPException(
            429,
            "Too many requests. Please try again later.",
            headers={"Retry-After": str(window_seconds)},
        )


def auth_rate_limit(request: Request) -> None:
    enforce_rate_limit(
        request,
        "auth",
        settings.auth_rate_limit,
        settings.auth_rate_window_seconds,
    )


def upload_rate_limit(request: Request) -> None:
    enforce_rate_limit(
        request,
        "upload",
        settings.upload_rate_limit,
        settings.upload_rate_window_seconds,
    )


def privacy_rate_limit(request: Request) -> None:
    enforce_rate_limit(
        request,
        "privacy",
        settings.privacy_rate_limit,
        settings.privacy_rate_window_seconds,
    )
