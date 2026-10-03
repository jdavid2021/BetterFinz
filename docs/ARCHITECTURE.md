# Architecture

Next.js calls only FastAPI `/api/v1`. FastAPI owns verified identity,
household authorization, onboarding status, and Decimal financial calculations.
SQLAlchemy uses PostgreSQL and Alembic. Redis provides request-rate protection,
Celery job delivery, and per-connection synchronization locks. Celery Beat scans
for due SimpleFIN connections and workers import read-only balance and
transaction updates with bounded retries.
Versioned HTTP-only sessions establish household membership. Statement imports
and optional SimpleFIN provide financial data; scheduled payments remain
planning records and never execute money movement.
