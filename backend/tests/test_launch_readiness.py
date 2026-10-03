from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import parse_session, password_hash, set_cookie, sign
from app.config import Settings, settings
from app.db import Base
from app.login_service import create_auth_token, redeem_auth_token
from app.login_routes import reset_password
from app.models import (
    FinancialAccount,
    Household,
    HouseholdMember,
    IncomeEvent,
    ScheduledPayment,
    User,
)
from app.onboarding_service import dismiss_onboarding, onboarding_status
from app.rate_limit import enforce_rate_limit
from app.schemas import PasswordResetRequest
from app.main import app
from starlette.requests import Request


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


def test_production_configuration_rejects_development_defaults():
    with pytest.raises(ValidationError, match="Invalid secure deployment configuration"):
        Settings(environment="production")


def test_versioned_session_roundtrip():
    token = sign("8c50d55b-5541-438e-a0b6-b4b7c7d3f875", 4)
    assert parse_session(token) == (
        "8c50d55b-5541-438e-a0b6-b4b7c7d3f875",
        4,
    )


def test_secure_environment_sets_secure_cookie():
    original = settings.environment
    settings.environment = "production"
    try:
        response = Response()
        set_cookie(response, "user-id", 2)
        assert "Secure" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
    finally:
        settings.environment = original


def test_tokens_are_single_use_and_purpose_bound(db):
    first = create_auth_token(db, "person@example.com", "email_verify", 60)
    second = create_auth_token(db, "person@example.com", "email_verify", 60)
    reset = create_auth_token(db, "person@example.com", "password_reset", 30)
    db.commit()
    assert redeem_auth_token(db, first, "email_verify") is None
    assert redeem_auth_token(db, second, "password_reset") is None
    assert redeem_auth_token(db, second, "email_verify") == "person@example.com"
    assert redeem_auth_token(db, second, "email_verify") is None
    assert redeem_auth_token(db, reset, "password_reset") == "person@example.com"


def test_password_reset_changes_password_and_invalidates_sessions(db):
    user = User(
        email="reset@example.com",
        password_hash=password_hash.hash("old-password-value"),
        display_name="Reset",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    old_session = sign(user.id, user.auth_version)
    secret = create_auth_token(db, user.email, "password_reset", 30)
    db.commit()
    assert reset_password(
        PasswordResetRequest(token=secret, password="new-password-value"),
        db,
    ) == {"reset": True}
    assert user.auth_version == 1
    assert password_hash.verify("new-password-value", user.password_hash)
    assert parse_session(old_session) == (user.id, 0)


def test_rate_limit_rejects_requests_over_limit(monkeypatch):
    class Pipeline:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def incr(self, _): return self
        def expire(self, *_args, **_kwargs): return self
        def execute(self): return [3, True]

    class Redis:
        def pipeline(self, transaction=True):
            assert transaction is True
            return Pipeline()

    monkeypatch.setattr("app.rate_limit.redis_client", lambda: Redis())
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )
    with pytest.raises(HTTPException) as error:
        enforce_rate_limit(request, "test", 2, 60)
    assert error.value.status_code == 429


def test_request_security_rejects_untrusted_origin_and_host():
    client = TestClient(app)
    origin_response = client.post(
        "/api/v1/auth/logout",
        headers={"origin": "https://attacker.example"},
    )
    assert origin_response.status_code == 403
    assert origin_response.json()["error"]["code"] == "CSRF_REJECTED"

    host_response = client.get("/health", headers={"host": "attacker.example"})
    assert host_response.status_code == 400


def test_request_security_adds_defensive_headers():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_onboarding_status_is_household_scoped_and_dismissible(db):
    household = Household(name="Primary")
    other = Household(name="Other")
    user = User(
        email="owner@example.com",
        password_hash="not-used",
        display_name="Owner",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add_all([household, other, user])
    db.flush()
    db.add(HouseholdMember(user_id=user.id, household_id=household.id, role="owner"))
    other_account = FinancialAccount(
        household_id=other.id,
        name="Other checking",
        kind="checking",
        mask="1234",
        balance=Decimal("100"),
        available_balance=Decimal("100"),
    )
    db.add(other_account)
    db.commit()
    status = onboarding_status(db, household.id)
    assert status["account_complete"] is False
    assert status["next_step"] == "account"
    assert dismiss_onboarding(db, household.id)["dismissed"] is True

    account = FinancialAccount(
        household_id=household.id,
        name="Checking",
        kind="checking",
        mask="5678",
        balance=Decimal("500"),
        available_balance=Decimal("500"),
    )
    db.add(account)
    db.flush()
    db.add(
        IncomeEvent(
            household_id=household.id,
            account_id=account.id,
            name="Pay",
            expected_date=datetime.now(timezone.utc).date(),
            amount=Decimal("1000"),
            reliability="guaranteed",
        )
    )
    db.add(
        ScheduledPayment(
            household_id=household.id,
            account_id=account.id,
            payee="Rent",
            amount=Decimal("400"),
            minimum_amount=Decimal("400"),
            scheduled_date=datetime.now(timezone.utc).date(),
            earliest_withdrawal_date=datetime.now(timezone.utc).date(),
            latest_withdrawal_date=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
        )
    )
    db.commit()
    assert onboarding_status(db, household.id)["complete"] is True
