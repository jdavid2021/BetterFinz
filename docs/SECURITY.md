# Security

Passwords use Argon2. Email verification and password-reset tokens are
purpose-bound, stored as keyed hashes, expire, and are single-use. Authentication
uses a versioned, expiring HMAC-signed HTTP-only SameSite cookie; resetting a
password invalidates earlier sessions.

Household scope comes from membership, never browser input. FinLeash stores no
bank passwords and never initiates money movement. SimpleFIN access URLs are
encrypted with a dedicated key.

`ENVIRONMENT=staging` and `ENVIRONMENT=production` fail startup unless:

- PostgreSQL, Redis, HTTPS frontend/API origins, SMTP, and a dedicated
  `SIMPLEFIN_ENCRYPTION_KEY` are configured.
- `SECRET_KEY` is unique and at least 32 characters.
- WebAuthn and trusted-host settings match the deployed domains.

Secure environments set secure cookies, enforce trusted hosts and exact browser
origins on state-changing API calls, disable interactive API documentation,
apply Redis-backed authentication/upload limits, and send HSTS and defensive
browser headers. Reverse proxies must preserve the real client address and
forward only trusted hosts.

## Legal and privacy launch review

The Terms and Privacy Notice are operational templates, not legal advice. Before
launch, qualified counsel must review the text and the configured operator,
privacy contact, governing law, effective date, version identifiers, retention
period, subprocessors, transfer mechanism, and jurisdiction-specific disclosures.
Changing either legal version forces users to accept that version on their next
authenticated visit; migrations intentionally do not create acceptance records.

Household ZIP exports require password reauthentication, are rate limited and
audited, and exclude authentication/provider secrets. Confirmed deletion
invalidates sessions, pauses SimpleFIN, permits cancellation during the configured
grace period, and is completed by the Celery due-deletion scan. Purges retain only
an anonymized completion tombstone.
