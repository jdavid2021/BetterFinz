import hashlib, hmac
from datetime import datetime, timedelta, timezone
from fastapi import Cookie, Depends, HTTPException, Response
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import HouseholdMember, User

password_hash = PasswordHash.recommended()
COOKIE = "betterfinz_session"

def sign(user_id: str, auth_version: int = 0) -> str:
    expires = str(int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp()))
    value = f"{user_id}.{auth_version}.{expires}"
    digest = hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{digest}"

def parse_session(token: str) -> tuple[str, int] | None:
    try:
        parts = token.split(".")
        if len(parts) == 4:
            user_id, version, expires, digest = parts
            value = f"{user_id}.{version}.{expires}"
        elif len(parts) == 3:
            # Accept pre-0023 sessions until their original one-day expiry.
            user_id, expires, digest = parts
            version = "0"
            value = f"{user_id}.{expires}"
        else:
            return None
        expected = hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, expected) or int(expires) < datetime.now(timezone.utc).timestamp(): return None
        return user_id, int(version)
    except (ValueError, TypeError): return None

def parse(token: str) -> str | None:
    parsed = parse_session(token)
    return parsed[0] if parsed else None

def set_cookie(response: Response, user_id: str, auth_version: int = 0) -> None:
    response.set_cookie(
        COOKIE,
        sign(user_id, auth_version),
        httponly=True,
        secure=settings.is_secure_environment,
        samesite="lax",
        max_age=86400,
        path="/",
    )

def clear_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE,
        path="/",
        httponly=True,
        secure=settings.is_secure_environment,
        samesite="lax",
    )

def current_user(session: str | None = Cookie(None, alias=COOKIE), db: Session = Depends(get_db)) -> User:
    parsed = parse_session(session or "")
    if not parsed:
        raise HTTPException(401, "Sign in to continue.")
    user = db.get(User, parsed[0])
    if not user or user.auth_version != parsed[1]:
        raise HTTPException(401, "Sign in to continue.")
    return user

def household_id(user: User = Depends(current_user), db: Session = Depends(get_db)) -> str:
    from app.legal_service import acceptance_status

    if acceptance_status(db, user.id)["required"]:
        raise HTTPException(428, "Review and accept the current Terms and Privacy Notice.")
    member = db.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))
    if not member: raise HTTPException(403, "Household access is required.")
    return member.household_id
