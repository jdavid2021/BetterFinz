# Paid Beta Readiness and Verification Guide

Last audited: 2026-08-23

This is the operational source of truth for the 12 paid-beta requirements. “Implemented” means code and tests exist; it does not mean production infrastructure, credentials, legal approval, alerts, or recovery drills are complete.

## Status summary

| # | Requirement | Status | Important qualification |
|---|---|---|---|
| 1 | Production security configuration and secret validation | Implemented | Must be supplied real deployment secrets and domains |
| 2 | Registration, password recovery, guided onboarding | Implemented | Production SMTP is required |
| 3 | Remove demo and placeholder behavior | Implemented with development-only exceptions | Never expose development configuration publicly |
| 4 | Real status and scheduled SimpleFIN synchronization | Implemented | Requires Redis, worker, scheduler, encryption key, and a real connection |
| 5 | Frontend/API integration, Playwright, CI | Partial | CI and auth E2E exist; financial browser journeys need broader coverage |
| 6 | PostgreSQL backups, monitoring, error reporting | Partial | Monitoring/Sentry exist; automated backup/restore tooling is absent |
| 7 | Privacy, terms, export, deletion | Implemented with blockers | Legal review is required; one due-purge test currently fails |
| 8 | What-if scenario UI | Not implemented | `POST /api/v1/what-if` exists, but no UI calls it |
| 9 | Payment-to-transaction matching UI | Implemented | Household/account scoped and audited |
| 10 | Financial notifications | Implemented | In-app only; scheduled generation requires Celery |
| 11 | Accessible modals, keyboard, mobile filters | Implemented for identified flows | Continue accessibility regression testing |
| 12 | User-facing audit history | Implemented | Only allowlisted, sanitized actions are exposed |

## Baseline verification

From the repository root:

```bash
cp .env.example .env
# Replace SECRET_KEY and any provider values needed for the test.
docker compose up --build -d
docker compose ps
curl -fsS http://localhost:8000/ready
curl -fsS http://localhost:3000/api/health

make lint
make typecheck
make test
make e2e
docker compose run --rm backend alembic heads
git diff --check
```

Expected:

- PostgreSQL, Redis, backend, frontend, worker, and scheduler are healthy.
- Backend returns `{"status":"ready"}`; frontend returns `{"status":"healthy"}`.
- Alembic reports exactly one head.
- A fresh database starts empty; create a user through signup.

At this audit, focused tests and production builds passed. The full backend suite still has one known failure in the due privacy-purge workflow. Release requires fixing it and obtaining a completely green CI run.

## 1. Production security and secrets

Implemented in `backend/app/config.py`, `backend/app/main.py`, `.env.example`, and `docs/SECURITY.md`: Argon2 passwords, expiring purpose-bound tokens, signed sessions, rate limits, trusted hosts, exact origins, security headers, secure cookies, and a separate SimpleFIN encryption key. Staging/production startup validates required secure values.

Verify:

```bash
docker compose run --rm backend pytest -q tests/test_launch_readiness.py tests/test_auth.py tests/test_observability.py
```

In staging, prove startup rejects missing/unsafe values. Confirm HTTPS origins, the public API host in `TRUSTED_HOSTS`, Secure/HttpOnly/SameSite cookies, rejected cross-origin writes, unavailable interactive API docs, and invalidation behavior after secret/password rotation. Store independent random `SECRET_KEY` and `SIMPLEFIN_ENCRYPTION_KEY` values in a secret manager. Never deploy example values.

## 2. Registration, recovery, and onboarding

Implemented in `backend/app/login_routes.py`, the auth pages under `frontend/src/app/`, `frontend/src/app/setup/page.tsx`, and `backend/app/onboarding_service.py`.

Manual verification:

1. Sign up, accept current legal versions, and confirm login is blocked before verification.
2. Verify the email and confirm redirection to guided setup.
3. Add an account, income, and scheduled payment.
4. Reset the password and confirm the old password/session no longer works.
5. Confirm used and expired verification/reset tokens fail safely.

Production dependency: test SMTP delivery, public link domains, SPF, DKIM, DMARC, and bounce handling.

## 3. Demo and placeholder behavior

New installations start empty and use signup. Planning/onboarding exclude legacy `data_source="seed"` rows. Development may expose email verification/reset links when SMTP is absent; production must never do so.

Audit command:

```bash
rg -n "demo|seed|placeholder" backend/app frontend/src --glob '!**/*.css' --glob '!**/*.test.*'
```

Form placeholder attributes and internal preview objects are legitimate. In staging, confirm there are no demo credentials, seeded financial rows, fake sync timestamps, or development email links. All displayed financial data must be entered or imported by the user.

## 4. SimpleFIN synchronization

Implemented in `backend/app/simplefin_service.py`, `simplefin_routes.py`, `simplefin_tasks.py`, `celery_app.py`, `frontend/src/components/simplefin-settings.tsx`, and Compose worker/scheduler services. Includes read-only import, encrypted access URL, mapping review, status, locks, idempotency, scheduling, and bounded retries.

Verify:

```bash
docker compose run --rm backend pytest -q tests/test_simplefin_service.py tests/test_simplefin_tasks.py
docker compose exec sync-worker celery -A app.celery_app.celery_app inspect registered
docker compose logs --tail=100 sync-worker sync-scheduler
```

With a test connection: link and map accounts, sync twice without duplicates, confirm real attempt/success/failure status, wait for scheduled sync, simulate provider failure/retry, and ensure logs never expose the access URL.

## 5. Integration tests, Playwright, and CI

`.github/workflows/ci.yml` contains backend quality/unit tests, PostgreSQL migration/integration tests, frontend lint/type/test/build, and full-stack Playwright. Current browser coverage in `frontend/e2e/auth.smoke.spec.ts` covers auth entry points, verification, signup, and password recovery.

Run `make e2e` against a clean database and require every CI job on pull requests. Playwright artifacts should upload on failure.

Still needed for strong paid-beta coverage:

- onboarding through the first complete plan;
- statement import and categorization;
- controlled SimpleFIN mapping/status;
- what-if UI;
- payment matching;
- notification preferences/read/dismiss;
- privacy export/deletion/cancellation;
- keyboard/focus/mobile behavior.

## 6. Backups, monitoring, and error reporting

Implemented: backend/frontend Sentry with scrubbing, JSON redaction, liveness/readiness endpoints, worker health, scheduler heartbeat, and token-protected Prometheus metrics. See `backend/app/health.py`, `backend/app/metrics.py`, Sentry config, and `docs/DEVELOPMENT.md`.

Not implemented here: scheduled PostgreSQL backups, encrypted off-site retention, automated restore validation, and alert/dashboard provisioning.

Before beta:

1. Enable provider point-in-time recovery.
2. Schedule encrypted backups in a separate account/region with documented retention.
3. Use a restricted backup identity; keep credentials out of Git.
4. Alert on stale/failed backups, health failures, worker/scheduler failure, elevated API errors, SimpleFIN failures, and Sentry regressions.
5. Perform an isolated restore drill before beta and quarterly thereafter.
6. Record RPO, RTO, backup timestamp/checksum, restore duration, and validation.

Example only—adapt to the provider and never restore into production during a drill:

```bash
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" --file=finleash.dump
createdb finleash_restore_test
pg_restore --exit-on-error --no-owner --no-acl --dbname=finleash_restore_test finleash.dump
psql finleash_restore_test -c 'select version_num from alembic_version;'
```

## 7. Privacy, terms, export, and deletion

Implemented in `backend/app/privacy_routes.py`, `privacy_service.py`, `privacy_tasks.py`, legal pages, and `frontend/src/components/privacy-settings.tsx`: versioned acceptance/reacceptance, password-reauthenticated rate-limited ZIP export, deletion confirmation/cancellation/grace period, session invalidation, SimpleFIN pause, scheduled purge, and anonymized tombstone.

Verify:

```bash
docker compose run --rm backend pytest -q tests/test_privacy_workflows.py tests/test_privacy_tasks.py
docker compose run --rm frontend pnpm test -- legal-document
```

Manually inspect an export for expected data and absence of passwords/tokens/provider secrets. Exercise wrong-password/rate limits. In isolation, confirm deletion, cancellation, and due purge remove household data but retain only the tombstone.

Launch blockers: qualified counsel must approve legal text/configuration, and the existing due-purge test must be fixed.

## 8. What-if scenario UI

Not complete. The backend endpoint is `POST /api/v1/what-if` in `backend/app/main.py`, but no frontend caller was found.

Acceptance criteria:

1. Add a Monthly Plan “What if?” action using the accessible `Dialog`.
2. Allow temporary payment/income date and amount changes without persistence.
3. Clearly label output as a simulation.
4. Show affected coverage, projected balances, and before/after differences.
5. Handle validation, loading, empty, and API errors.
6. Add API/service and Playwright tests proving source records do not change.

## 9. Payment-to-transaction matching

Implemented with candidate and reconcile endpoints in `backend/app/main.py`, ranking in `backend/app/bill_service.py`, and the Monthly Plan matching dialog. It rejects wrong household/account, pending, credit, transfer, already-used, or already-paid records and creates an audit event.

Verify:

```bash
docker compose run --rm backend pytest -q tests/test_activity_features.py tests/test_bill_service.py tests/test_monthly_plan_payment.py
```

Create an unpaid payment and nearby same-account settled debit; match it from Monthly Plan. Confirm unrelated candidates are absent, status becomes paid, Activity records it, and reuse is rejected. This records a match only and never moves money.

## 10. Notifications

Migration `0026_notifications.py`, notification models/service/routes/task, the Notifications page, and Settings preferences implement idempotent household/user-scoped low-reserve, upcoming-unpaid-payment, and missing-income notifications.

Create each condition, refresh repeatedly to confirm no duplicates, then test read, dismiss, preference toggles, and cross-household denial. Confirm the worker registers `finleash.notifications.scan`.

```bash
docker compose run --rm backend pytest -q tests/test_activity_features.py
```

Delivery is in-app only; email, SMS, and push are not implemented.

## 11. Accessibility and mobile filters

`frontend/src/components/dialog.tsx` supplies dialog naming/semantics, initial focus, focus trapping, Escape/backdrop close, scroll lock, and focus restoration. Transaction contextual filtering supports Enter/Space, and mobile filters use an explicit expandable control.

```bash
docker compose run --rm frontend pnpm test -- dialog
```

Manually verify every changed dialog with keyboard only; forward/backward focus trap; Escape and focus return; screen-reader name; transaction Enter/Space filtering; 320/375/768 px layouts; 200% zoom; no hidden controls or horizontal overflow. This is not a substitute for a full WCAG audit.

## 12. User-facing audit history

`backend/app/audit_service.py`, `GET /api/v1/audit-events`, and `frontend/src/app/activity/page.tsx` provide a newest-first, household-scoped, sanitized allowlist of important actions.

Perform signup/login/password, payment match, notification preference/dismissal, export, and deletion actions. Confirm they appear with understandable labels; another household cannot read them; and no passwords, tokens, cookies, full account numbers, credentials, or request bodies appear.

## Paid-beta release gate

- [ ] Implement and test the what-if UI.
- [ ] Fix the privacy due-purge test; require completely green CI.
- [ ] Add Playwright coverage for critical financial/privacy journeys.
- [ ] Exercise SMTP and SimpleFIN in staging.
- [ ] Obtain legal approval for terms, privacy, retention, and subprocessors.
- [ ] Run monitored encrypted PostgreSQL backups.
- [ ] Complete and record an isolated restore drill.
- [ ] Confirm Sentry releases/source maps and Prometheus alerts.
- [ ] Store production secrets in a secret manager and assign rotation ownership.
- [ ] Route health, worker, scheduler, backup, sync, and error alerts on-call.
- [ ] Complete mobile, keyboard, and screen-reader regression checks.
- [ ] Document deployment rollback and migration rollback decisions.

## Ongoing maintenance rules

For every change:

1. Add Alembic migrations for schema changes and keep one migration head.
2. Keep financial decisions in backend services, never browser code.
3. Use Decimal/NUMERIC for money, UUIDs for business records, UTC timestamps, and household-scoped queries.
4. Test financial rules, authorization boundaries, and idempotency.
5. Never log secrets, cookies, request bodies, full account numbers, or SimpleFIN URLs.
6. Never add autonomous money movement; payments remain simulations/records.
7. Run lint, type checks, tests, build, and relevant Playwright journeys.
8. After deployment, verify migrations, health, workers, scheduler, Sentry, and metrics.
9. Periodically review dependencies, access, secrets, legal versions, retention, and restore readiness.

Keep incident logs, secret rotation dates, backup checksums, restore-drill evidence, legal approvals, vendor agreements, and production access reviews outside Git in the appropriate secure operational system.
