# Backend guidance

- Organize request flow as route -> service -> repository -> SQLAlchemy model.
- APIs live under `/api/v1`; health endpoints remain at the root.
- Never trust household IDs from requests. Derive household access from the authenticated session.
- Money uses `Decimal` and `Numeric`, never float. Responses serialize money as strings.
- Forecast scheduled withdrawals conservatively by account and event time.
