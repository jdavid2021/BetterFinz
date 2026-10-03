import time
from datetime import datetime, timezone
from typing import cast

from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.metrics import SCHEDULER_HEARTBEAT_AGE, SIMPLEFIN_CONNECTIONS
from app.models import FinancialConnection


SCHEDULER_HEARTBEAT_KEY = "finleash:health:scheduler-heartbeat"


def redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.healthcheck_timeout_seconds,
        socket_timeout=settings.healthcheck_timeout_seconds,
    )


def probe_dependencies(db: Session) -> bool:
    db.execute(text("SELECT 1"))
    return bool(redis_client().ping())


def refresh_health_metrics(db: Session) -> None:
    counts: dict[str, int] = {
        state: count
        for state, count in db.execute(
            select(FinancialConnection.status, func.count(FinancialConnection.id))
            .where(FinancialConnection.provider == "simplefin")
            .group_by(FinancialConnection.status)
        ).all()
    }
    for state in ("pending", "active", "syncing", "error"):
        SIMPLEFIN_CONNECTIONS.labels(state=state).set(counts.get(state, 0))
    heartbeat = cast(bytes | str | None, redis_client().get(SCHEDULER_HEARTBEAT_KEY))
    if heartbeat:
        SCHEDULER_HEARTBEAT_AGE.set(max(0, time.time() - float(heartbeat)))


def record_scheduler_heartbeat() -> None:
    redis_client().set(
        SCHEDULER_HEARTBEAT_KEY,
        datetime.now(timezone.utc).timestamp(),
        ex=settings.scheduler_stale_seconds * 2,
    )


def scheduler_is_healthy() -> bool:
    heartbeat = cast(bytes | str | None, redis_client().get(SCHEDULER_HEARTBEAT_KEY))
    return bool(
        heartbeat
        and time.time() - float(heartbeat) <= settings.scheduler_stale_seconds
    )
