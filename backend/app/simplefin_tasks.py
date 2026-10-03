import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.metrics import SIMPLEFIN_SYNCS
from app.models import FinancialConnection
from app.simplefin_service import SimpleFinBusy, sync_connection


logger = logging.getLogger("finleash.simplefin.tasks")
@celery_app.task(name="finleash.simplefin.scan_due")
def scan_due_connections() -> dict:
    now = datetime.now(timezone.utc)
    abandoned_before = now - timedelta(seconds=settings.simplefin_sync_lock_seconds)
    with SessionLocal() as db:
        connection_ids = list(
            db.scalars(
                select(FinancialConnection.id).where(
                    FinancialConnection.provider == "simplefin",
                    FinancialConnection.status != "pending",
                    or_(
                        and_(
                            FinancialConnection.status.in_({"active", "error"}),
                            or_(
                                FinancialConnection.next_sync_at.is_(None),
                                FinancialConnection.next_sync_at <= now,
                            ),
                        ),
                        and_(
                            FinancialConnection.status == "syncing",
                            FinancialConnection.sync_started_at <= abandoned_before,
                        ),
                    ),
                )
            )
        )
    for connection_id in connection_ids:
        sync_simplefin_connection.delay(connection_id)
    return {"queued": len(connection_ids)}


@celery_app.task(
    bind=True,
    name="finleash.simplefin.sync_connection",
    max_retries=3,
)
def sync_simplefin_connection(self, connection_id: str) -> dict:
    with SessionLocal() as db:
        connection = db.get(FinancialConnection, connection_id)
        if connection is None or connection.provider != "simplefin":
            SIMPLEFIN_SYNCS.labels(outcome="missing").inc()
            return {"status": "missing"}
        if connection.status == "pending":
            SIMPLEFIN_SYNCS.labels(outcome="pending").inc()
            return {"status": "pending"}
        try:
            result = sync_connection(
                db,
                connection.household_id,
                connection,
            )
            SIMPLEFIN_SYNCS.labels(outcome="synchronized").inc()
            return {"status": "synchronized", **result}
        except SimpleFinBusy:
            SIMPLEFIN_SYNCS.labels(outcome="already_running").inc()
            return {"status": "already_running"}
        except Exception as exc:
            SIMPLEFIN_SYNCS.labels(outcome="failed").inc()
            retry_number = self.request.retries
            countdown = 60 * settings.simplefin_sync_retry_base_minutes * (
                2**retry_number
            )
            logger.warning(
                "SimpleFIN synchronization failed for connection %s; retry %s",
                connection_id,
                retry_number + 1,
            )
            raise self.retry(
                exc=RuntimeError("SimpleFIN synchronization failed."),
                countdown=countdown,
            ) from exc
