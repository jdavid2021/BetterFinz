import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, settings
from app.main import app
from app.observability import JsonFormatter, before_send


def test_observability_configuration_is_validated():
    with pytest.raises(ValidationError, match="SENTRY_TRACES_SAMPLE_RATE"):
        Settings(sentry_traces_sample_rate=1.1)
    with pytest.raises(ValidationError, match="SCHEDULER_STALE_SECONDS"):
        Settings(scheduler_heartbeat_seconds=30, scheduler_stale_seconds=30)


def test_sentry_scrubber_removes_financial_and_identity_data():
    event = {
        "request": {
            "cookies": {"session": "secret"},
            "headers": {
                "Authorization": "Bearer abc",
                "Cookie": "session=secret",
            },
            "data": {"token": "abc"},
            "url": "https://example.test/path?token=abc",
        },
        "user": {
            "id": "8c50d55b-5541-438e-a0b6-b4b7c7d3f875",
            "email": "person@example.test",
        },
        "extra": {
            "household_id": "315d65fd-5db4-4ea2-a8f0-412e67ba3451",
            "account": "123456789012",
            "params": ("sensitive",),
        },
    }
    scrubbed = before_send(event, {})
    encoded = json.dumps(scrubbed)
    assert "abc" not in encoded
    assert "person@example.test" not in encoded
    assert "315d65fd-5db4-4ea2-a8f0-412e67ba3451" not in encoded
    assert "123456789012" not in encoded
    assert scrubbed["request"]["headers"]["Authorization"] == "[Filtered]"


def test_json_logs_include_request_id_without_account_numbers():
    record = logging.LogRecord(
        "finleash.test",
        logging.INFO,
        __file__,
        1,
        "account=%s",
        ("123456789012",),
        None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "-"
    assert "123456789012" not in payload["message"]


def test_request_ids_are_validated_and_returned():
    client = TestClient(app)
    generated = client.get("/health", headers={"x-request-id": "bad value"})
    supplied = client.get("/health", headers={"x-request-id": "request-1234"})
    assert generated.status_code == 200
    assert generated.headers["x-request-id"] != "bad value"
    assert supplied.headers["x-request-id"] == "request-1234"


def test_metrics_endpoint_requires_bearer_token(monkeypatch):
    original_token = settings.metrics_auth_token
    original_enabled = settings.metrics_enabled
    settings.metrics_enabled = True
    settings.metrics_auth_token = "a" * 32
    monkeypatch.setattr("app.main.refresh_health_metrics", lambda _db: None)
    try:
        client = TestClient(app)
        assert client.get("/metrics").status_code == 401
        response = client.get(
            "/metrics", headers={"authorization": f"Bearer {settings.metrics_auth_token}"}
        )
        assert response.status_code == 200
        assert "finleash_api_request_duration_seconds" in response.text
    finally:
        settings.metrics_auth_token = original_token
        settings.metrics_enabled = original_enabled
