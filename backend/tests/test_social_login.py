from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.login_service import (
    create_login_token,
    ensure_user,
    parse_transient,
    redeem_login_token,
    sign_transient,
    upsert_google_user,
)
from app.models import HouseholdMember, LoginToken, SocialAccount


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


def test_transient_token_roundtrip_and_tamper_rejection():
    token = sign_transient("google_state", "abc123")
    assert parse_transient(token, "google_state") == "abc123"
    assert parse_transient(token, "webauthn_login") is None
    assert parse_transient(token + "x", "google_state") is None
    assert parse_transient("", "google_state") is None


def test_ensure_user_provisions_household_once(db):
    user = ensure_user(db, "Pat@Example.com")
    db.commit()
    assert user.email == "pat@example.com"
    assert user.display_name == "Pat"
    member = db.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))
    assert member is not None and member.role == "owner"
    again = ensure_user(db, "PAT@example.com")
    assert again.id == user.id


def test_google_login_requires_verified_email(db):
    with pytest.raises(ValueError, match="not verified"):
        upsert_google_user(db, {"sub": "g-1", "email": "a@b.com", "email_verified": False})


def test_google_login_links_subject_and_is_idempotent(db):
    userinfo = {"sub": "g-42", "email": "casey@example.com", "email_verified": True, "name": "Casey Jones"}
    user = upsert_google_user(db, userinfo)
    db.commit()
    linked = db.scalar(select(SocialAccount).where(SocialAccount.provider == "google", SocialAccount.subject == "g-42"))
    assert linked is not None and linked.user_id == user.id
    assert user.email_verified_at is not None
    again = upsert_google_user(db, {**userinfo, "email": "changed@example.com"})
    assert again.id == user.id
    assert db.scalar(select(SocialAccount).where(SocialAccount.subject == "g-42")).user_id == user.id


def test_google_login_attaches_to_existing_email_account(db):
    existing = ensure_user(db, "casey@example.com", "Casey")
    db.commit()
    user = upsert_google_user(db, {"sub": "g-9", "email": "casey@example.com", "email_verified": True})
    assert user.id == existing.id


def test_magic_link_token_is_single_use(db):
    secret = create_login_token(db, "Riley@Example.com")
    db.commit()
    assert redeem_login_token(db, secret) == "riley@example.com"
    db.commit()
    assert redeem_login_token(db, secret) is None
    assert redeem_login_token(db, "not-a-real-token") is None


def test_expired_magic_link_is_rejected(db):
    secret = create_login_token(db, "riley@example.com")
    db.commit()
    token = db.scalar(select(LoginToken))
    token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert redeem_login_token(db, secret) is None
