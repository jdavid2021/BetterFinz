from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AccountDeletionRequest, Household, HouseholdMember, User
from app.privacy_tasks import celery_app, purge_due_deletion, scan_due_deletions


def test_scheduler_queues_only_due_deletions(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine)
    household = Household(name="Deletion")
    user = User(email="due@example.com", password_hash="unused", display_name="Due")
    future_user = User(
        email="future@example.com", password_hash="unused", display_name="Future"
    )
    db.add_all([household, user, future_user])
    db.flush()
    db.add_all(
        [
            HouseholdMember(user_id=user.id, household_id=household.id),
            AccountDeletionRequest(
                user_id=user.id,
                household_id=household.id,
                status="pending",
                execute_after=datetime.now(timezone.utc) - timedelta(minutes=1),
            ),
            AccountDeletionRequest(
                user_id=future_user.id,
                household_id=household.id,
                status="pending",
                execute_after=datetime.now(timezone.utc) + timedelta(days=1),
            ),
        ]
    )
    db.commit()

    @contextmanager
    def session_scope():
        yield db

    queued: list[str] = []
    monkeypatch.setattr("app.privacy_tasks.SessionLocal", session_scope)
    monkeypatch.setattr(purge_due_deletion, "delay", queued.append)
    assert scan_due_deletions()["queued"] == 1
    assert len(queued) == 1
    assert (
        celery_app.conf.beat_schedule["scan-due-account-deletions"]["task"]
        == "finleash.privacy.scan_due_deletions"
    )
