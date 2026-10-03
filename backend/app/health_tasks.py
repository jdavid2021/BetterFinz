from app.celery_app import celery_app
from app.health import record_scheduler_heartbeat


@celery_app.task(name="finleash.health.scheduler_heartbeat")
def scheduler_heartbeat() -> dict[str, str]:
    record_scheduler_heartbeat()
    return {"status": "ok"}
