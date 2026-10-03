from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["development", "staging", "production"] = "development"
    database_url: str = "sqlite:///./betterfinz.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "local-development-key-change-before-deploy"
    frontend_origin: str = "http://localhost:3000"
    public_api_url: str = "http://localhost:8000"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    google_client_id: str = ""
    google_client_secret: str = ""
    magic_link_ttl_minutes: int = 15
    email_verification_ttl_minutes: int = 60
    password_reset_ttl_minutes: int = 30
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "FinLeash <no-reply@finleash.local>"
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "FinLeash"
    openai_api_key: str = ""
    openai_transaction_model: str = "gpt-5.6-luna"
    simplefin_encryption_key: str = ""
    simplefin_allowed_hosts: str = "bridge.simplefin.org,beta-bridge.simplefin.org"
    simplefin_sync_interval_minutes: int = 360
    simplefin_sync_scan_seconds: int = 60
    simplefin_sync_lock_seconds: int = 300
    simplefin_sync_stale_hours: int = 12
    simplefin_sync_retry_base_minutes: int = 5
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60
    upload_rate_limit: int = 10
    upload_rate_window_seconds: int = 3600
    privacy_rate_limit: int = 3
    privacy_rate_window_seconds: int = 3600
    legal_operator_name: str = "FinLeash"
    legal_contact_email: str = "privacy@example.com"
    legal_governing_law: str = "the laws of the operator's registered jurisdiction"
    legal_effective_date: str = "2026-08-23"
    legal_terms_version: str = "2026-08-23"
    legal_privacy_version: str = "2026-08-23"
    legal_retention_days: int = 30
    deletion_grace_days: int = 30
    deletion_scan_seconds: int = 3600
    sentry_dsn: str = ""
    sentry_environment: str = ""
    sentry_release: str = ""
    sentry_traces_sample_rate: float = 0.0
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    metrics_enabled: bool = True
    metrics_auth_token: str = ""
    healthcheck_timeout_seconds: float = 2.0
    scheduler_heartbeat_seconds: int = 30
    scheduler_stale_seconds: int = 120

    @property
    def is_secure_environment(self) -> bool:
        return self.environment in {"staging", "production"}

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @model_validator(mode="after")
    def validate_deployment(self):
        for field_name in ("frontend_origin", "public_api_url"):
            value = getattr(self, field_name).rstrip("/")
            parsed = urlparse(value)
            if not parsed.scheme or not parsed.netloc or parsed.path not in {"", "/"}:
                raise ValueError(f"{field_name.upper()} must be an origin without a path.")
            setattr(self, field_name, value)
        if self.auth_rate_limit < 1 or self.auth_rate_window_seconds < 1:
            raise ValueError("Authentication rate limits must be positive.")
        if self.upload_rate_limit < 1 or self.upload_rate_window_seconds < 1:
            raise ValueError("Upload rate limits must be positive.")
        if min(
            self.privacy_rate_limit,
            self.privacy_rate_window_seconds,
            self.legal_retention_days,
            self.deletion_grace_days,
            self.deletion_scan_seconds,
        ) < 1:
            raise ValueError("Privacy workflow settings must be positive.")
        if not all(
            (
                self.legal_operator_name.strip(),
                self.legal_contact_email.strip(),
                self.legal_governing_law.strip(),
                self.legal_effective_date.strip(),
                self.legal_terms_version.strip(),
                self.legal_privacy_version.strip(),
            )
        ):
            raise ValueError("Legal template settings must not be empty.")
        if min(
            self.simplefin_sync_interval_minutes,
            self.simplefin_sync_scan_seconds,
            self.simplefin_sync_lock_seconds,
            self.simplefin_sync_stale_hours,
            self.simplefin_sync_retry_base_minutes,
        ) < 1:
            raise ValueError("SimpleFIN synchronization settings must be positive.")
        if not 0 <= self.sentry_traces_sample_rate <= 1:
            raise ValueError("SENTRY_TRACES_SAMPLE_RATE must be between 0 and 1.")
        if self.sentry_dsn:
            sentry_url = urlparse(self.sentry_dsn)
            if sentry_url.scheme != "https" or not sentry_url.netloc:
                raise ValueError("SENTRY_DSN must be an HTTPS URL.")
            if not (self.sentry_environment or self.environment) or not self.sentry_release.strip():
                raise ValueError(
                    "SENTRY_ENVIRONMENT and SENTRY_RELEASE are required with SENTRY_DSN."
                )
        if self.healthcheck_timeout_seconds <= 0:
            raise ValueError("HEALTHCHECK_TIMEOUT_SECONDS must be positive.")
        if min(self.scheduler_heartbeat_seconds, self.scheduler_stale_seconds) < 1:
            raise ValueError("Scheduler health settings must be positive.")
        if self.scheduler_stale_seconds <= self.scheduler_heartbeat_seconds:
            raise ValueError("SCHEDULER_STALE_SECONDS must exceed the heartbeat interval.")
        if not self.trusted_host_list:
            raise ValueError("TRUSTED_HOSTS must contain at least one host.")
        if self.is_secure_environment:
            errors: list[str] = []
            if len(self.secret_key) < 32 or self.secret_key == "local-development-key-change-before-deploy":
                errors.append("SECRET_KEY must be a unique value of at least 32 characters")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                errors.append("DATABASE_URL must use PostgreSQL")
            if not self.redis_url.startswith(("redis://", "rediss://")):
                errors.append("REDIS_URL must use Redis")
            if not self.frontend_origin.startswith("https://") or not self.public_api_url.startswith("https://"):
                errors.append("FRONTEND_ORIGIN and PUBLIC_API_URL must use HTTPS")
            if not self.smtp_host:
                errors.append("SMTP_HOST is required")
            if bool(self.smtp_username) != bool(self.smtp_password):
                errors.append("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
            if not self.simplefin_encryption_key:
                errors.append("SIMPLEFIN_ENCRYPTION_KEY is required")
            if bool(self.google_client_id) != bool(self.google_client_secret):
                errors.append("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together")
            frontend_host = urlparse(self.frontend_origin).hostname
            api_host = urlparse(self.public_api_url).hostname
            if self.webauthn_rp_id in {"", "localhost"} or (
                frontend_host
                and frontend_host != self.webauthn_rp_id
                and not frontend_host.endswith(f".{self.webauthn_rp_id}")
            ):
                errors.append("WEBAUTHN_RP_ID must match the frontend domain")
            if "*" in self.trusted_host_list:
                errors.append("TRUSTED_HOSTS cannot contain a wildcard")
            if api_host not in self.trusted_host_list:
                errors.append("TRUSTED_HOSTS must include the public API host")
            if self.metrics_enabled and len(self.metrics_auth_token) < 32:
                errors.append("METRICS_AUTH_TOKEN must contain at least 32 characters")
            if errors:
                raise ValueError("Invalid secure deployment configuration: " + "; ".join(errors))
        return self

@lru_cache
def get_settings() -> Settings: return Settings()
settings = get_settings()
