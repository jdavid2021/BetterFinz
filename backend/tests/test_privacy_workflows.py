import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.auth import household_id, password_hash
from app.config import settings
from app.db import Base
from app.legal_service import accept_current, acceptance_status
from app.models import (
    AccountDeletionRequest,
    DeletionTombstone,
    FinancialAccount,
    FinancialConnection,
    Household,
    HouseholdMember,
    LegalAcceptance,
    User,
)
from app.privacy_service import (
    cancel_deletion,
    confirm_deletion,
    export_household_zip,
    purge_deletion,
    request_deletion,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


def make_user(db, email="owner@example.com"):
    household = Household(name="Private household")
    user = User(
        email=email,
        password_hash=password_hash.hash("correct-password"),
        display_name="Owner",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add_all([household, user])
    db.flush()
    db.add(
        HouseholdMember(
            user_id=user.id, household_id=household.id, role="owner"
        )
    )
    db.commit()
    return user, household


def token_from(url: str, key: str) -> str:
    return parse_qs(urlparse(url).query)[key][0]


def test_existing_users_require_current_legal_versions_without_backfill(db):
    user, household = make_user(db)
    assert db.scalar(select(LegalAcceptance)) is None
    assert acceptance_status(db, user.id)["required"] is True
    with pytest.raises(HTTPException) as error:
        household_id(user, db)
    assert error.value.status_code == 428

    status = accept_current(
        db,
        user,
        settings.legal_terms_version,
        settings.legal_privacy_version,
    )
    assert status["required"] is False
    assert household_id(user, db) == household.id
    assert len(list(db.scalars(select(LegalAcceptance)))) == 2


def test_export_is_household_scoped_and_excludes_secrets(db):
    user, household = make_user(db)
    other = Household(name="Other")
    db.add(other)
    db.flush()
    db.add_all(
        [
            FinancialConnection(
                household_id=household.id,
                provider="simplefin",
                encrypted_access_url="top-secret-access-url",
                status="active",
            ),
            FinancialAccount(
                household_id=household.id,
                name="Mine",
                kind="checking",
                mask="1234",
                balance=Decimal("10"),
                available_balance=Decimal("10"),
            ),
            FinancialAccount(
                household_id=other.id,
                name="Other household secret",
                kind="checking",
                mask="9999",
                balance=Decimal("20"),
                available_balance=Decimal("20"),
            ),
        ]
    )
    db.commit()
    content = export_household_zip(
        db, user, household.id, "correct-password"
    )
    assert b"top-secret-access-url" not in content
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        accounts = json.loads(
            archive.read("data/financial_accounts.json")
        )
        connections = json.loads(
            archive.read("data/financial_connections.json")
        )
    assert [row["name"] for row in accounts] == ["Mine"]
    assert "encrypted_access_url" not in connections[0]


def test_deletion_confirmation_is_purpose_bound_and_cancel_is_single_use(db):
    user, household = make_user(db)
    connection = FinancialConnection(
        household_id=household.id,
        provider="simplefin",
        encrypted_access_url="encrypted",
        status="active",
    )
    db.add(connection)
    db.commit()
    request, confirmation_url = request_deletion(
        db, user, household.id, "correct-password"
    )
    assert request.status == "awaiting_confirmation"
    assert confirmation_url
    confirmation = token_from(confirmation_url, "confirm")
    result = confirm_deletion(db, confirmation)
    assert result["status"] == "pending"
    assert user.auth_version == 1
    assert connection.status == "deletion_pending"
    assert result["development_cancel_url"]

    cancel = token_from(result["development_cancel_url"], "cancel")
    assert cancel_deletion(db, cancel) == {"status": "cancelled"}
    assert connection.status == "active"
    with pytest.raises(ValueError, match="invalid|already"):
        cancel_deletion(db, cancel)


def test_due_purge_is_ordered_idempotent_and_retains_anonymous_tombstone(db):
    user, household = make_user(db)
    account = FinancialAccount(
        household_id=household.id,
        name="Delete me",
        kind="checking",
        mask="1234",
        balance=Decimal("10"),
        available_balance=Decimal("10"),
    )
    request = AccountDeletionRequest(
        user_id=user.id,
        household_id=household.id,
        status="pending",
        confirmed_at=datetime.now(timezone.utc) - timedelta(days=31),
        execute_after=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add_all([account, request])
    db.commit()
    request_id = request.id
    user_id = user.id
    household_id_value = household.id

    assert purge_deletion(db, request_id) == "completed"
    assert purge_deletion(db, request_id) == "completed"
    assert db.get(User, user_id) is None
    assert db.get(Household, household_id_value) is None
    tombstone = db.scalar(select(DeletionTombstone))
    assert tombstone is not None
    assert user.email not in tombstone.subject_hash
    assert household_id_value not in tombstone.subject_hash
