import secrets
import urllib.parse
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.auth import clear_cookie, current_user, password_hash, set_cookie
from app.config import settings
from app.db import get_db
from app.login_service import (
    create_login_token,
    create_auth_token,
    ensure_user,
    google_authorization_url,
    google_enabled,
    google_fetch_userinfo,
    magic_link_delivery,
    magic_link_url,
    parse_transient,
    record_login,
    redeem_auth_token,
    redeem_login_token,
    send_magic_link,
    send_password_reset_email,
    send_verification_email,
    sign_transient,
    upsert_google_user,
    reset_url,
    verification_url,
    webauthn_authentication_options,
    webauthn_registration_options,
    webauthn_store_registration,
    webauthn_verify_login,
)
from app.models import AuditEvent, Household, HouseholdMember, LoginToken, User, WebAuthnCredential
from app.legal_service import accept_current, acceptance_status
from app.rate_limit import auth_rate_limit
from app.schemas import EmailRequest, LoginRequest, PasswordResetRequest, SignupRequest, TokenRequest

router = APIRouter(prefix="/api/v1/auth")
logger = logging.getLogger("finleash.auth")

OAUTH_COOKIE = "bf_oauth_state"
REGISTER_COOKIE = "bf_webauthn_register"
LOGIN_COOKIE = "bf_webauthn_login"


class MagicLinkRequest(BaseModel):
    email: EmailStr


class PasskeyRegisterFinish(BaseModel):
    credential: dict
    label: str = ""


class PasskeyLoginFinish(BaseModel):
    credential: dict


def transient_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=settings.is_secure_environment,
        samesite="lax",
        max_age=600,
        path="/",
    )

def clear_transient_cookie(response: Response, name: str) -> None:
    response.delete_cookie(
        name,
        path="/",
        httponly=True,
        secure=settings.is_secure_environment,
        samesite="lax",
    )


def login_error_redirect(message: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_origin}/?auth_error={urllib.parse.quote(message)}")


def development_link(delivery: str, url: str) -> str | None:
    if settings.environment == "development" and delivery == "development":
        return url
    return None


@router.get("/methods")
def methods():
    return {"google": google_enabled(), "magic_link": True, "magic_link_delivery": magic_link_delivery(), "passkeys": True}


@router.get("/google/start", dependencies=[Depends(auth_rate_limit)])
def google_start():
    if not google_enabled():
        return login_error_redirect("Google sign-in is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to the backend .env.")
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(google_authorization_url(state))
    transient_cookie(response, OAUTH_COOKIE, sign_transient("google_state", state))
    return response


@router.get("/google/callback")
def google_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db), oauth_state: str | None = Cookie(None, alias=OAUTH_COOKIE)):
    if error or not code:
        return login_error_redirect("Google sign-in was cancelled.")
    expected_state = parse_transient(oauth_state or "", "google_state")
    if not expected_state or expected_state != state:
        return login_error_redirect("The sign-in request expired. Please try again.")
    try:
        userinfo = google_fetch_userinfo(code)
        user = upsert_google_user(db, userinfo)
    except ValueError as exc:
        return login_error_redirect(str(exc))
    except Exception:
        return login_error_redirect("Google could not confirm your account. Please try again.")
    record_login(db, user, "google")
    db.commit()
    response = RedirectResponse(f"{settings.frontend_origin}/setup")
    clear_transient_cookie(response, OAUTH_COOKIE)
    set_cookie(response, user.id, user.auth_version)
    return response


@router.post("/magic/start", dependencies=[Depends(auth_rate_limit)])
def magic_start(body: MagicLinkRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    recent = db.scalar(
        select(LoginToken).where(
            LoginToken.email == email,
            LoginToken.purpose == "magic_login",
            LoginToken.created_at
            > datetime.now(timezone.utc) - timedelta(seconds=60),
        )
    )
    if recent:
        return {"delivery": magic_link_delivery(), "throttled": True}
    secret = create_login_token(db, email)
    db.commit()
    try:
        url = magic_link_url(secret)
        delivery = send_magic_link(email, url)
    except Exception:
        raise HTTPException(502, "The sign-in email could not be sent. Please try again shortly.")
    return {
        "delivery": delivery,
        "throttled": False,
        "development_url": development_link(delivery, url),
    }


@router.get("/magic/verify")
def magic_verify(token: str = "", db: Session = Depends(get_db)):
    email = redeem_login_token(db, token) if token else None
    if not email:
        db.commit()
        return login_error_redirect("That sign-in link is invalid or has expired. Request a new one.")
    user = ensure_user(db, email, verified=True)
    record_login(db, user, "magic_link")
    db.commit()
    response = RedirectResponse(f"{settings.frontend_origin}/setup")
    set_cookie(response, user.id, user.auth_version)
    return response


@router.post("/webauthn/register/start")
def webauthn_register_start(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from webauthn.helpers import bytes_to_base64url
    options_json, challenge = webauthn_registration_options(db, user)
    response = Response(content=options_json, media_type="application/json")
    transient_cookie(response, REGISTER_COOKIE, sign_transient("webauthn_register", bytes_to_base64url(challenge)))
    return response


@router.post("/webauthn/register/finish")
def webauthn_register_finish(body: PasskeyRegisterFinish, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db), challenge_cookie: str | None = Cookie(None, alias=REGISTER_COOKIE)):
    from webauthn.helpers import base64url_to_bytes
    challenge = parse_transient(challenge_cookie or "", "webauthn_register")
    if not challenge:
        raise HTTPException(400, "The passkey setup expired. Please try again.")
    try:
        record = webauthn_store_registration(db, user, body.credential, base64url_to_bytes(challenge), body.label)
    except Exception:
        raise HTTPException(400, "The passkey could not be verified. Please try again.")
    db.commit()
    clear_transient_cookie(response, REGISTER_COOKIE)
    return {"id": record.id, "label": record.label, "created_at": record.created_at.isoformat()}


@router.get("/webauthn/credentials")
def webauthn_credentials(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id).order_by(WebAuthnCredential.created_at)).all()
    return [{"id": item.id, "label": item.label, "created_at": item.created_at.isoformat(), "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None} for item in items]


@router.delete("/webauthn/credentials/{credential_id}", status_code=204)
def webauthn_delete(credential_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = db.scalar(select(WebAuthnCredential).where(WebAuthnCredential.id == credential_id, WebAuthnCredential.user_id == user.id))
    if not record:
        raise HTTPException(404, "That passkey was not found.")
    db.delete(record)
    db.commit()


@router.post("/webauthn/login/start", dependencies=[Depends(auth_rate_limit)])
def webauthn_login_start():
    from webauthn.helpers import bytes_to_base64url
    options_json, challenge = webauthn_authentication_options()
    response = Response(content=options_json, media_type="application/json")
    transient_cookie(response, LOGIN_COOKIE, sign_transient("webauthn_login", bytes_to_base64url(challenge)))
    return response


@router.post("/webauthn/login/finish", dependencies=[Depends(auth_rate_limit)])
def webauthn_login_finish(body: PasskeyLoginFinish, response: Response, db: Session = Depends(get_db), challenge_cookie: str | None = Cookie(None, alias=LOGIN_COOKIE)):
    from webauthn.helpers import base64url_to_bytes
    challenge = parse_transient(challenge_cookie or "", "webauthn_login")
    if not challenge:
        raise HTTPException(401, "The passkey sign-in expired. Please try again.")
    try:
        user = webauthn_verify_login(db, body.credential, base64url_to_bytes(challenge))
    except Exception:
        user = None
    if not user:
        raise HTTPException(401, "That passkey could not be verified on this device.")
    record_login(db, user, "passkey")
    db.commit()
    clear_transient_cookie(response, LOGIN_COOKIE)
    set_cookie(response, user.id, user.auth_version)
    return {"user": {"id": user.id, "email": user.email, "name": user.display_name}}


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
def password_login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(func.lower(User.email) == body.email.strip().lower())
    )
    if not user or not password_hash.verify(body.password, user.password_hash):
        db.add(AuditEvent(action="login_failed", detail="Invalid credentials"))
        db.commit()
        raise HTTPException(401, "Email or password is incorrect.")
    if user.email_verified_at is None:
        raise HTTPException(403, "Verify your email before signing in.")
    record_login(db, user, "password")
    db.commit()
    set_cookie(response, user.id, user.auth_version)
    return {"user": {"id": user.id, "email": user.email, "name": user.display_name}}


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_cookie(response)


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    member = db.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    household = db.get(Household, member.household_id) if member else None
    return {
        "id": user.id,
        "email": user.email,
        "name": user.display_name,
        "household": household.name if household else "",
        "legal": acceptance_status(db, user.id),
    }


@router.post("/signup", status_code=202, dependencies=[Depends(auth_rate_limit)])
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    if not body.accept_terms or not body.accept_privacy:
        raise HTTPException(422, "Accept the Terms and Privacy Notice to create an account.")
    email = body.email.strip().lower()
    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing is None:
        user = ensure_user(db, email, body.name)
        user.password_hash = password_hash.hash(body.password)
        try:
            accept_current(
                db,
                user,
                body.terms_version,
                body.privacy_version,
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(409, str(exc)) from exc
        secret = create_auth_token(
            db,
            email,
            "email_verify",
            settings.email_verification_ttl_minutes,
        )
        db.commit()
        try:
            url = verification_url(secret)
            delivery = send_verification_email(email, url)
        except Exception as exc:
            raise HTTPException(
                502, "The verification email could not be sent. Please try again shortly."
            ) from exc
        return {
            "message": "If the address can be registered, a verification email has been sent.",
            "development_url": development_link(delivery, url),
        }
    return {
        "message": "If the address can be registered, a verification email has been sent.",
        "development_url": None,
    }


@router.post("/resend-verification", status_code=202, dependencies=[Depends(auth_rate_limit)])
def resend_verification(body: EmailRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    development_url = None
    if user and user.email_verified_at is None:
        secret = create_auth_token(
            db,
            email,
            "email_verify",
            settings.email_verification_ttl_minutes,
        )
        db.commit()
        try:
            url = verification_url(secret)
            delivery = send_verification_email(email, url)
            development_url = development_link(delivery, url)
        except Exception as exc:
            logger.error("Verification email delivery failed: %s", type(exc).__name__)
    return {
        "message": "If the account needs verification, an email has been sent.",
        "development_url": development_url,
    }


@router.post("/verify-email", dependencies=[Depends(auth_rate_limit)])
def verify_email(
    body: TokenRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = redeem_auth_token(db, body.token, "email_verify")
    user = (
        db.scalar(select(User).where(func.lower(User.email) == email))
        if email
        else None
    )
    if not user:
        db.commit()
        raise HTTPException(400, "That verification link is invalid or has expired.")
    user.email_verified_at = datetime.now(timezone.utc)
    user.dml_flag = "U"
    record_login(db, user, "email_verification")
    db.commit()
    set_cookie(response, user.id, user.auth_version)
    return {"verified": True}


@router.post("/forgot-password", status_code=202, dependencies=[Depends(auth_rate_limit)])
def forgot_password(body: EmailRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    development_url = None
    if user and user.email_verified_at is not None:
        secret = create_auth_token(
            db,
            email,
            "password_reset",
            settings.password_reset_ttl_minutes,
        )
        db.commit()
        try:
            url = reset_url(secret)
            delivery = send_password_reset_email(email, url)
            development_url = development_link(delivery, url)
        except Exception as exc:
            logger.error("Password reset email delivery failed: %s", type(exc).__name__)
    return {
        "message": "If an account exists, a password reset email has been sent.",
        "development_url": development_url,
    }


@router.post("/reset-password", dependencies=[Depends(auth_rate_limit)])
def reset_password(body: PasswordResetRequest, db: Session = Depends(get_db)):
    email = redeem_auth_token(db, body.token, "password_reset")
    user = (
        db.scalar(select(User).where(func.lower(User.email) == email))
        if email
        else None
    )
    if not user:
        db.commit()
        raise HTTPException(400, "That reset link is invalid or has expired.")
    user.password_hash = password_hash.hash(body.password)
    user.auth_version += 1
    user.dml_flag = "U"
    db.add(AuditEvent(user_id=user.id, action="password_reset"))
    db.commit()
    return {"reset": True}
