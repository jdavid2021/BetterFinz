import time

from celery import Celery
from celery.signals import task_postrun, task_prerun

from app.config import settings
from app.metrics import CELERY_TASK_LATENCY, CELERY_TASKS
from app.observability import request_id_context


celery_app = Celery(
    "finleash",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.simplefin_tasks", "app.privacy_tasks", "app.health_tasks", "app.notification_tasks"],
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=settings.simplefin_sync_lock_seconds,
    task_soft_time_limit=max(settings.simplefin_sync_lock_seconds - 15, 1),
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "scan-due-simplefin-connections": {
            "task": "finleash.simplefin.scan_due",
            "schedule": settings.simplefin_sync_scan_seconds,
        },
        "scan-due-account-deletions": {
            "task": "finleash.privacy.scan_due_deletions",
            "schedule": settings.deletion_scan_seconds,
        },
        "scan-household-notifications": {
            "task": "finleash.notifications.scan",
            "schedule": 900,
        },
        "scheduler-health-heartbeat": {
            "task": "finleash.health.scheduler_heartbeat",
            "schedule": settings.scheduler_heartbeat_seconds,
        },
    },
)


@task_prerun.connect
def observe_task_start(task_id=None, task=None, **_kwargs):
    if task is not None:
        task.request._observability_started = time.monotonic()
    request_id_context.set(str(task_id or "-"))


@task_postrun.connect
def observe_task_finish(task=None, state=None, **_kwargs):
    if task is None:
        return
    task_name = task.name or "unknown"
    started = getattr(task.request, "_observability_started", None)
    if started is not None:
        CELERY_TASK_LATENCY.labels(task=task_name).observe(time.monotonic() - started)
    CELERY_TASKS.labels(task=task_name, outcome=(state or "unknown").lower()).inc()
    request_id_context.set("-")
