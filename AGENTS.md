# BetterFinz repository guidance

- Preserve the Next.js/FastAPI boundary; browser code never accesses the database or provider secrets.
- Use Decimal/NUMERIC for money, UUIDs for business records, UTC timestamps, and household-scoped queries.
- Keep routes and UI components thin; financial decisions belong in backend services.
- Demo payments are simulations only. Never add autonomous money movement or credential storage.
- Add migrations for schema changes and tests for financial rules. Never log secrets or full account numbers.
