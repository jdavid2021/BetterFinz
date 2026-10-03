import hashlib
import hmac
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth import password_hash
from app.config import settings
from app.db import Base
from app.login_service import (
    create_auth_token,
    deletion_cancel_url,
    deletion_confirmation_url,
    redeem_auth_token,
    send_deletion_confirmation_email,
    send_deletion_scheduled_email,
)
from app.models import (
    AccountDeletionRequest,
    AuditEvent,
    DeletionTombstone,
    FinancialConnection,
    HouseholdMember,
    User,
)


EXCLUDED_EXPORT_TABLES = {
    "account_deletion_requests",
    "audit_events",
    "deletion_tombstones",
    "login_tokens",
    "social_accounts",
    "webauthn_credentials",
}
EXCLUDED_EXPORT_COLUMNS = {
    "encrypted_access_url",
    "password_hash",
    "public_key",
    "provider_account_id",
    "token_hash",
}


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def verify_password(user: User, supplied: str) -> None:
    if not password_hash.verify(supplied, user.password_hash):
        raise ValueError("Reauthentication failed.")


def export_household_zip(db: Session, user: User, household_id: str, password: str) -> bytes:
    verify_password(user, password)
    files: dict[str, object] = {
        "profile.json": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat(),
        }
    }
    for table in Base.metadata.sorted_tables:
        if (
            table.name in EXCLUDED_EXPORT_TABLES
            or "household_id" not in table.c
            or table.name == "households"
        ):
            continue
        columns = [
            column
            for column in table.c
            if column.name not in EXCLUDED_EXPORT_COLUMNS
        ]
        rows = db.execute(
            select(*columns).where(table.c.household_id == household_id)
        ).mappings()
        files[f"data/{table.name}.json"] = [
            {key: _json_value(value) for key, value in row.items()} for row in rows
        ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.txt",
            "FinLeash household export. Authentication secrets and provider access "
            "credentials are intentionally excluded.\n",
        )
        for filename, value in files.items():
            archive.writestr(filename, json.dumps(value, indent=2, sort_keys=True))
    db.add(
        AuditEvent(
            user_id=user.id,
            household_id=household_id,
            action="privacy_export_created",
            detail="ZIP export generated; secrets excluded",
        )
    )
    db.commit()
    return buffer.getvalue()


def request_deletion(
    db: Session, user: User, household_id: str, password: str | None
) -> tuple[AccountDeletionRequest, str | None]:
    if password:
        verify_password(user, password)
    member_count = db.scalar(
        select(func.count(HouseholdMember.id)).where(
            HouseholdMember.household_id == household_id
        )
    )
    if member_count != 1:
        raise ValueError(
            "Account deletion is only available when you are the household's sole member."
        )
    request = db.scalar(
        select(AccountDeletionRequest).where(
            AccountDeletionRequest.user_id == user.id
        )
    )
    if request and request.status == "pending":
        return request, None
    if request is None:
        request = AccountDeletionRequest(
            user_id=user.id,
            household_id=household_id,
        )
        db.add(request)
    else:
        request.status = "awaiting_confirmation"
        request.requested_at = datetime.now(timezone.utc)
        request.confirmed_at = None
        request.execute_after = None
        request.cancelled_at = None
    secret = create_auth_token(db, user.email, "account_deletion_confirm", 30)
    db.add(
        AuditEvent(
            user_id=user.id,
            household_id=household_id,
            action="account_deletion_requested",
        )
    )
    url = deletion_confirmation_url(secret)
    delivery = send_deletion_confirmation_email(user.email, url)
    db.commit()
    return request, url if delivery == "development" else None


def confirm_deletion(db: Session, secret: str) -> dict:
    email = redeem_auth_token(db, secret, "account_deletion_confirm")
    user = (
        db.scalar(select(User).where(func.lower(User.email) == email))
        if email
        else None
    )
    request = (
        db.scalar(
            select(AccountDeletionRequest).where(
                AccountDeletionRequest.user_id == user.id,
                AccountDeletionRequest.status == "awaiting_confirmation",
            )
        )
        if user
        else None
    )
    if not user or not request:
        db.commit()
        raise ValueError("That deletion confirmation link is invalid or has expired.")
    now = datetime.now(timezone.utc)
    request.status = "pending"
    request.confirmed_at = now
    request.execute_after = now + timedelta(days=settings.deletion_grace_days)
    user.auth_version += 1
    db.execute(
        update(FinancialConnection)
        .where(FinancialConnection.household_id == request.household_id)
        .values(status="deletion_pending", next_sync_at=None, sync_started_at=None)
    )
    cancel_secret = create_auth_token(
        db,
        user.email,
        "account_deletion_cancel",
        settings.deletion_grace_days * 24 * 60,
    )
    db.add(
        AuditEvent(
            user_id=user.id,
            household_id=request.household_id,
            action="account_deletion_confirmed",
            detail=f"Grace period: {settings.deletion_grace_days} days",
        )
    )
    cancel_url = deletion_cancel_url(cancel_secret)
    delivery = send_deletion_scheduled_email(user.email, cancel_url)
    db.commit()
    return {
        "status": request.status,
        "execute_after": request.execute_after.isoformat(),
        "grace_days": settings.deletion_grace_days,
        "development_cancel_url": cancel_url if delivery == "development" else None,
    }


def cancel_deletion(db: Session, secret: str) -> dict:
    email = redeem_auth_token(db, secret, "account_deletion_cancel")
    user = (
        db.scalar(select(User).where(func.lower(User.email) == email))
        if email
        else None
    )
    request = (
        db.scalar(
            select(AccountDeletionRequest).where(
                AccountDeletionRequest.user_id == user.id,
                AccountDeletionRequest.status == "pending",
            )
        )
        if user
        else None
    )
    if not user or not request:
        db.commit()
        raise ValueError("That cancellation link is invalid or has already been used.")
    request.status = "cancelled"
    request.cancelled_at = datetime.now(timezone.utc)
    user.auth_version += 1
    db.execute(
        update(FinancialConnection)
        .where(
            FinancialConnection.household_id == request.household_id,
            FinancialConnection.status == "deletion_pending",
        )
        .values(status="active", next_sync_at=datetime.now(timezone.utc))
    )
    db.add(
        AuditEvent(
            user_id=user.id,
            household_id=request.household_id,
            action="account_deletion_cancelled",
        )
    )
    db.commit()
    return {"status": "cancelled"}


def deletion_status(db: Session, user_id: str) -> dict:
    request = db.scalar(
        select(AccountDeletionRequest).where(
            AccountDeletionRequest.user_id == user_id
        )
    )
    if request is None:
        return {"status": "none", "execute_after": None}
    return {
        "status": request.status,
        "execute_after": request.execute_after.isoformat()
        if request.execute_after
        else None,
    }


def _subject_hash(user: User, household_id: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        f"{user.email.lower()}|{user.id}|{household_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def purge_deletion(db: Session, request_id: str, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    request = db.get(AccountDeletionRequest, request_id)
    if request is None:
        return "completed" if db.get(DeletionTombstone, request_id) else "missing"
    execute_after = request.execute_after
    if execute_after and execute_after.tzinfo is None:
        execute_after = execute_after.replace(tzinfo=timezone.utc)
    if request.status != "pending" or not execute_after or execute_after > current:
        return "not_due"
    user = db.get(User, request.user_id)
    if user is None:
        return "missing"
    household_id = request.household_id
    user_id = user.id
    subject_hash = _subject_hash(user, household_id)
    if db.scalar(
        select(DeletionTombstone).where(
            DeletionTombstone.subject_hash == subject_hash
        )
    ):
        return "completed"
    requested_at = request.requested_at
    db.execute(
        delete(AuditEvent).where(
            (AuditEvent.household_id == household_id)
            | (AuditEvent.user_id == user_id)
        )
    )
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in {
            "account_deletion_requests",
            "audit_events",
            "deletion_tombstones",
            "households",
            "users",
        }:
            continue
        if "household_id" in table.c:
            db.execute(
                delete(table).where(table.c.household_id == household_id)
            )
        elif "user_id" in table.c:
            db.execute(delete(table).where(table.c.user_id == user_id))
        elif table.name == "login_tokens":
            db.execute(
                delete(table).where(func.lower(table.c.email) == user.email.lower())
            )
    db.execute(
        delete(AccountDeletionRequest).where(AccountDeletionRequest.id == request.id)
    )
    db.execute(delete(User).where(User.id == user_id))
    households = Base.metadata.tables["households"]
    db.execute(delete(households).where(households.c.id == household_id))
    db.add(
        DeletionTombstone(
            id=request_id,
            subject_hash=subject_hash,
            requested_at=requested_at,
            completed_at=current,
        )
    )
    db.commit()
    db.expire_all()
    return "completed"
