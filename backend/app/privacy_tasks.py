from datetime import datetime, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import AccountDeletionRequest
from app.privacy_service import purge_deletion


@celery_app.task(name="finleash.privacy.scan_due_deletions")
def scan_due_deletions() -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        request_ids = list(
            db.scalars(
                select(AccountDeletionRequest.id).where(
                    AccountDeletionRequest.status == "pending",
                    AccountDeletionRequest.execute_after <= now,
                )
            )
        )
    for request_id in request_ids:
        purge_due_deletion.delay(request_id)
    return {"queued": len(request_ids)}


@celery_app.task(name="finleash.privacy.purge_due_deletion")
def purge_due_deletion(request_id: str) -> dict:
    with SessionLocal() as db:
        return {"status": purge_deletion(db, request_id)}
