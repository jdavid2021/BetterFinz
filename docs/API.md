# API

Interactive docs are available at `/docs` outside production. Probes are at
`/health` and `/ready`, and application APIs are versioned under `/api/v1`.
Resources cover verified authentication and recovery, onboarding, Today,
accounts, income, payments, reconciliation, what-if scenarios, transactions,
imports, SimpleFIN, accounting, and exports. Money is serialized as decimal
strings and errors use a consistent `error` envelope.
