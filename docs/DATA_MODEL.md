# Data model

The initial migration creates identity, household, account, income, payment, transaction, reconciliation, audit, and import records. IDs are UUID strings, money uses `NUMERIC(14,2)`, timestamps are UTC-aware, and financial rows are household-owned. Provider IDs and import hashes provide idempotency.
