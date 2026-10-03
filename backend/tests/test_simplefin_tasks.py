from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import FinancialConnection, Household
from app.simplefin_tasks import (
    celery_app,
    scan_due_connections,
    sync_simplefin_connection,
)


def test_scheduler_queues_only_due_connections(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    household = Household(name="Scheduled sync")
    db.add(household)
    db.flush()
    due = FinancialConnection(
        household_id=household.id,
        provider="simplefin",
        encrypted_access_url="encrypted",
        status="active",
        next_sync_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    future = FinancialConnection(
        household_id=household.id,
        provider="simplefin",
        encrypted_access_url="encrypted",
        status="active",
        next_sync_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add_all([due, future])
    db.commit()

    @contextmanager
    def session_scope():
        yield db

    queued: list[str] = []
    monkeypatch.setattr("app.simplefin_tasks.SessionLocal", session_scope)
    monkeypatch.setattr(sync_simplefin_connection, "delay", queued.append)

    assert scan_due_connections()["queued"] == 1
    assert queued == [due.id]
    assert (
        celery_app.conf.beat_schedule["scan-due-simplefin-connections"]["task"]
        == "finleash.simplefin.scan_due"
    )
