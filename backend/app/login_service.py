"""Identity verification for Google sign-in, email magic links, and passkeys.

Every method ends the same way: a verified email or credential resolves to a User,
and the caller issues the existing signed session cookie. Provider secrets stay in
backend settings and are never sent to the browser.
"""
import hashlib
import hmac
import json
import secrets
import smtplib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.auth import password_hash
from app.config import settings
from app.models import AuditEvent, Household, HouseholdMember, LoginToken, SocialAccount, User, WebAuthnCredential

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def google_enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def magic_link_delivery() -> str:
    return "email" if settings.smtp_host else "development"


# --- Short-lived signed values (OAuth state, WebAuthn challenges) ---

def sign_transient(purpose: str, value: str, ttl_seconds: int = 600) -> str:
    expires = str(int((datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).timestamp()))
    payload = f"{purpose}|{value}|{expires}"
    digest = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{digest}"


def parse_transient(token: str, purpose: str) -> str | None:
    try:
        found_purpose, value, expires, digest = token.split("|")
        payload = f"{found_purpose}|{value}|{expires}"
        expected = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, expected): return None
        if found_purpose != purpose or int(expires) < datetime.now(timezone.utc).timestamp(): return None
        return value
    except (ValueError, TypeError):
        return None


# --- User provisioning shared by every method ---

def ensure_user(
    db: Session, email: str, display_name: str = "", *, verified: bool = False
) -> User:
    normalized = email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == normalized))
    if user:
        if verified and user.email_verified_at is None:
            user.email_verified_at = datetime.now(timezone.utc)
            user.dml_flag = "U"
        return user
    name = display_name.strip() or normalized.split("@")[0].replace(".", " ").title()
    # Social and magic-link users have no password; store an unguessable placeholder.
    user = User(
        email=normalized,
        password_hash=password_hash.hash(secrets.token_urlsafe(32)),
        display_name=name,
        email_verified_at=datetime.now(timezone.utc) if verified else None,
        data_source="signup",
    )
    db.add(user)
    db.flush()
    household = Household(name=f"{name} Household", data_source="signup")
    db.add(household)
    db.flush()
    db.add(HouseholdMember(user_id=user.id, household_id=household.id, role="owner"))
    db.add(AuditEvent(user_id=user.id, household_id=household.id, action="user_signed_up"))
    return user


def record_login(db: Session, user: User, method: str) -> None:
    member = db.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user.id))
    db.add(AuditEvent(user_id=user.id, household_id=member.household_id if member else None, action="login_succeeded", detail=method))


# --- Google OpenID Connect (authorization code flow, confidential client) ---

def google_redirect_uri() -> str:
    return f"{settings.public_api_url}/api/v1/auth/google/callback"


def google_authorization_url(state: str) -> str:
    params = urllib.parse.urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return f"{GOOGLE_AUTH_URL}?{params}"


def google_fetch_userinfo(code: str) -> dict:
    """Exchange the authorization code server-to-server and fetch the verified profile."""
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": google_redirect_uri(),
        "grant_type": "authorization_code",
    }).encode()
    request = urllib.request.Request(GOOGLE_TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=15) as response:
        tokens = json.load(response)
    info_request = urllib.request.Request(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    with urllib.request.urlopen(info_request, timeout=15) as response:
        return json.load(response)


def upsert_google_user(db: Session, userinfo: dict) -> User:
    subject = str(userinfo.get("sub") or "")
    email = str(userinfo.get("email") or "").strip().lower()
    if not subject or not email: raise ValueError("Google did not return a usable account.")
    if not userinfo.get("email_verified"): raise ValueError("This Google account's email address is not verified.")
    linked = db.scalar(select(SocialAccount).where(SocialAccount.provider == "google", SocialAccount.subject == subject))
    if linked:
        user = db.get(User, linked.user_id)
        if user:
            if user.email_verified_at is None:
                user.email_verified_at = datetime.now(timezone.utc)
                user.dml_flag = "U"
            return user
    user = ensure_user(db, email, str(userinfo.get("name") or ""), verified=True)
    if not linked:
        db.add(SocialAccount(user_id=user.id, provider="google", subject=subject, email=email, data_source="signup"))
    return user


# --- Purpose-bound email tokens ---

def _token_hash(secret: str, purpose: str) -> str:
    return hmac.new(
        settings.secret_key.encode(),
        f"{purpose}:{secret}".encode(),
        hashlib.sha256,
    ).hexdigest()


def create_auth_token(
    db: Session,
    email: str,
    purpose: str,
    ttl_minutes: int,
) -> str:
    normalized = email.strip().lower()
    now = datetime.now(timezone.utc)
    for old in db.scalars(
        select(LoginToken).where(
            LoginToken.email == normalized,
            LoginToken.purpose == purpose,
            LoginToken.used_at.is_(None),
        )
    ):
        old.used_at = now
        old.dml_flag = "U"
    secret = secrets.token_urlsafe(32)
    db.add(LoginToken(
        email=normalized,
        token_hash=_token_hash(secret, purpose),
        purpose=purpose,
        expires_at=now + timedelta(minutes=ttl_minutes),
    ))
    return secret


def redeem_auth_token(db: Session, secret: str, purpose: str) -> str | None:
    """Return the email for a valid unused token and burn it, else None."""
    token = db.scalar(
        select(LoginToken).where(
            LoginToken.token_hash == _token_hash(secret, purpose),
            LoginToken.purpose == purpose,
        )
    )
    if not token or token.used_at is not None: return None
    expires = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc): return None
    token.used_at = datetime.now(timezone.utc)
    token.dml_flag = "U"
    return token.email


def create_login_token(db: Session, email: str) -> str:
    return create_auth_token(
        db, email, "magic_login", settings.magic_link_ttl_minutes
    )


def redeem_login_token(db: Session, secret: str) -> str | None:
    return redeem_auth_token(db, secret, "magic_login")


def magic_link_url(secret: str) -> str:
    return f"{settings.public_api_url}/api/v1/auth/magic/verify?token={urllib.parse.quote(secret)}"


def _send_email(email: str, subject: str, content: str) -> str:
    if not settings.smtp_host:
        if settings.is_secure_environment:
            raise RuntimeError("SMTP is not configured.")
        return "development"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(content)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        client.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
    return "email"


def send_magic_link(email: str, link: str) -> str:
    return _send_email(
        email,
        "Your FinLeash sign-in link",
        "Use this link to sign in to FinLeash. It expires in "
        f"{settings.magic_link_ttl_minutes} minutes and can be used once.\n\n{link}\n\n"
        "If you did not request this link, you can ignore this email.",
    )


def verification_url(secret: str) -> str:
    return f"{settings.frontend_origin}/verify-email?token={urllib.parse.quote(secret)}"


def reset_url(secret: str) -> str:
    return f"{settings.frontend_origin}/reset-password?token={urllib.parse.quote(secret)}"

def deletion_confirmation_url(secret: str) -> str:
    return f"{settings.frontend_origin}/privacy/delete?confirm={urllib.parse.quote(secret)}"


def deletion_cancel_url(secret: str) -> str:
    return f"{settings.frontend_origin}/privacy/delete?cancel={urllib.parse.quote(secret)}"


def send_verification_email(email: str, link: str) -> str:
    return _send_email(
        email,
        "Verify your FinLeash email",
        "Verify your email to finish creating your FinLeash account. This link "
        f"expires in {settings.email_verification_ttl_minutes} minutes.\n\n{link}\n\n"
        "If you did not create this account, you can ignore this email.",
    )


def send_password_reset_email(email: str, link: str) -> str:
    return _send_email(
        email,
        "Reset your FinLeash password",
        "Use this link to reset your FinLeash password. This link expires in "
        f"{settings.password_reset_ttl_minutes} minutes and can be used once.\n\n{link}\n\n"
        "If you did not request a reset, you can ignore this email.",
    )


def send_deletion_confirmation_email(email: str, link: str) -> str:
    return _send_email(
        email,
        "Confirm deletion of your FinLeash account",
        "Use this single-use link to confirm account deletion. The link is purpose-bound "
        "and expires shortly. Your account will then enter a "
        f"{settings.deletion_grace_days}-day cancellation period.\n\n{link}\n\n"
        "If you did not request deletion, do not use this link and secure your account.",
    )


def send_deletion_scheduled_email(email: str, cancel_link: str) -> str:
    return _send_email(
        email,
        "FinLeash account deletion scheduled",
        f"Your account is scheduled for deletion in {settings.deletion_grace_days} days. "
        "Use this single-use link before then if you change your mind:\n\n"
        f"{cancel_link}\n\nContact {settings.legal_contact_email} if you need help.",
    )


# --- Passkeys (WebAuthn) ---

def webauthn_registration_options(db: Session, user: User) -> tuple[str, bytes]:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor, ResidentKeyRequirement, UserVerificationRequirement
    existing = list(db.scalars(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)))
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user.id.encode(),
        user_name=user.email,
        user_display_name=user.display_name,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id)) for item in existing],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return options_to_json(options), options.challenge


def webauthn_store_registration(db: Session, user: User, credential: dict, challenge: bytes, label: str) -> WebAuthnCredential:
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_origin=settings.frontend_origin,
        expected_rp_id=settings.webauthn_rp_id,
        require_user_verification=False,
    )
    transports = credential.get("response", {}).get("transports") or []
    record = WebAuthnCredential(
        user_id=user.id,
        credential_id=bytes_to_base64url(verification.credential_id),
        public_key=bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        transports=",".join(transports)[:120],
        label=(label.strip() or "Passkey")[:80],
        data_source="signup",
    )
    db.add(record)
    return record


def webauthn_authentication_options() -> tuple[str, bytes]:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options_to_json(options), options.challenge


def webauthn_verify_login(db: Session, credential: dict, challenge: bytes) -> User | None:
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    credential_id = str(credential.get("id") or "")
    record = db.scalar(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id))
    if not record: return None
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_origin=settings.frontend_origin,
        expected_rp_id=settings.webauthn_rp_id,
        credential_public_key=base64url_to_bytes(record.public_key),
        credential_current_sign_count=record.sign_count,
        require_user_verification=False,
    )
    record.sign_count = verification.new_sign_count
    record.last_used_at = datetime.now(timezone.utc)
    record.dml_flag = "U"
    return db.get(User, record.user_id)
