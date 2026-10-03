# Development

Copy `.env.example` to `.env`, replace `SECRET_KEY`, then run
`docker compose up --build`. Backend startup applies Alembic migrations and
starts with an empty database. Create an account through the FinLeash signup
flow. Use the Makefile for tests, lint, type checks, and E2E.

SMTP is required in staging and production. Development without SMTP returns
authentication delivery as development-only and must not be exposed publicly.
Accounts can be added from statements, manually, or through SimpleFIN. Monthly
Plan exports a normalized workbook.

Docker Compose also starts `sync-scheduler` and `sync-worker`. The scheduler
queues due SimpleFIN connections every minute; each active connection syncs
every six hours by default. Redis locks prevent overlapping imports, and failed
attempts use bounded exponential retries. Configure the cadence with the
`SIMPLEFIN_SYNC_*` environment variables.

## Observability

Backend and frontend Sentry projects use separate DSNs. Configure
`SENTRY_DSN` for FastAPI/Celery and `NEXT_PUBLIC_SENTRY_DSN` for Next.js, plus
the matching environment, release, and trace sample-rate variables in
`.env.example`. Events and JSON logs redact authentication material, cookies,
request bodies, SQL parameters, account numbers, and raw user/household IDs.
Keep `SENTRY_AUTH_TOKEN` in CI only. Set the `SENTRY_ORG`, `SENTRY_PROJECT`, and
`FRONTEND_SENTRY_DSN` GitHub variables to enable source-map upload during the
frontend build.

`/health` is a liveness check. `/ready` returns only a generic status and checks
both PostgreSQL and Redis. The frontend equivalent is `/api/health`; Compose
also checks the Celery worker and scheduler heartbeat. Do not add dependency
details to these public responses.

Prometheus metrics are available at the backend `/metrics` endpoint only when
`METRICS_ENABLED=true` and a bearer token is configured. In staging and
production, `METRICS_AUTH_TOKEN` must contain at least 32 characters. Scrapers
must send `Authorization: Bearer <token>`. Metrics cover API latency/errors,
Celery task outcomes and duration, SimpleFIN synchronization, connection
states, and scheduler heartbeat age; labels intentionally exclude household,
user, account, and connection identifiers.
