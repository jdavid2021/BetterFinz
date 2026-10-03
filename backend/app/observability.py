import contextvars
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.types import Event

from app.config import settings


request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

_SECRET_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "set_cookie",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "client_secret",
    "api_key",
    "encrypted_access_url",
    "sql_params",
    "params",
    "parameters",
}
_IDENTITY_KEYS = {"household_id", "householdid", "user_id", "userid"}
_TOKEN_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|token|password|secret|api[_-]?key)\b"
    r"(\s*[=:]\s*)([^\s,;]+)"
)
_ACCOUNT_NUMBER_PATTERN = re.compile(r"(?<![\w-])\d{8,17}(?![\w-])")
_UUID_PATTERN = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
_SQL_PARAMS_PATTERN = re.compile(
    r"(?is)(\[(?:parameters|params):).*?(?=\]\s*(?:\(|$))"
)


def _pseudonym(value: Any) -> str:
    digest = hashlib.sha256(
        f"{settings.secret_key}:{value}".encode("utf-8")
    ).hexdigest()[:16]
    return f"redacted-id:{digest}"


def scrub_text(value: str) -> str:
    value = _TOKEN_PATTERN.sub(r"\1\2[Filtered]", value)
    value = _SQL_PARAMS_PATTERN.sub(r"\1 [Filtered]", value)
    value = _ACCOUNT_NUMBER_PATTERN.sub("[Filtered account number]", value)
    return _UUID_PATTERN.sub("[Filtered id]", value)


def scrub_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if not parts.query:
            return scrub_text(value)
        query = [
            (key, "[Filtered]" if key.lower() in _SECRET_KEYS else scrub_text(item))
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    except ValueError:
        return scrub_text(value)


def scrub(value: Any, key: str = "") -> Any:
    normalized = key.lower().replace("-", "_")
    if normalized in _SECRET_KEYS:
        return "[Filtered]"
    if normalized in _IDENTITY_KEYS:
        return _pseudonym(value)
    if isinstance(value, dict):
        return {str(item_key): scrub(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return scrub_url(value) if value.startswith(("http://", "https://")) else scrub_text(value)
    return value


def before_send(event: Event, _hint: dict[str, Any]) -> Event:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request["headers"] = scrub(request.get("headers", {}))
        request["data"] = "[Filtered]" if request.get("data") is not None else None
        if isinstance(request.get("url"), str):
            request["url"] = scrub_url(request["url"])
    user = event.get("user")
    if isinstance(user, dict):
        user.pop("email", None)
        if "id" in user:
            user["id"] = _pseudonym(user["id"])
    breadcrumbs = event.get("breadcrumbs")
    breadcrumb_values = breadcrumbs.get("values", []) if isinstance(breadcrumbs, dict) else []
    for breadcrumb in breadcrumb_values:
        if breadcrumb.get("category") in {"query", "sqlalchemy"}:
            breadcrumb.pop("data", None)
            breadcrumb["message"] = scrub_text(str(breadcrumb.get("message", "")))
    return cast(Event, scrub(event))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_text(record.getMessage()),
            "request_id": request_id_context.get(),
        }
        if record.exc_info:
            payload["exception"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)
    for logger_name in ("uvicorn.access", "uvicorn.error", "celery"):
        logging.getLogger(logger_name).handlers.clear()
        logging.getLogger(logger_name).propagate = True


def initialize_sentry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        release=settings.sentry_release or None,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=before_send,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
    )


configure_logging()
initialize_sentry()
