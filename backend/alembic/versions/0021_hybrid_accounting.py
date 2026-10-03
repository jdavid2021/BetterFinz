"""hybrid personal finance and double-entry accounting

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", sa.String(32), nullable=False, server_default="accounting"),
        sa.Column("dml_flag", sa.String(1), nullable=False, server_default="I"),
    ]


def upgrade():
    op.add_column("households", sa.Column("workspace_type", sa.String(30), nullable=False, server_default="individual"))
    op.create_table(
        "accounting_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False, server_default="personal"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *audit_columns(),
        sa.UniqueConstraint("household_id", "name", name="uq_entity_household_name"),
    )
    op.create_index("ix_accounting_entities_household_id", "accounting_entities", ["household_id"])
    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id"), nullable=False),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("accounting_entities.id"), nullable=True),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("ledger_accounts.id"), nullable=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("normal_balance", sa.String(6), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_posting", sa.Boolean(), nullable=False, server_default=sa.true()),
        *audit_columns(),
        sa.UniqueConstraint("household_id", "entity_id", "code", name="uq_ledger_household_entity_code"),
        sa.CheckConstraint("account_type in ('asset','liability','equity','income','expense')", name="ck_ledger_account_type"),
        sa.CheckConstraint("normal_balance in ('debit','credit')", name="ck_ledger_normal_balance"),
    )
    for column in ("household_id", "entity_id", "parent_id"):
        op.create_index(f"ix_ledger_accounts_{column}", "ledger_accounts", [column])
    op.add_column("financial_accounts", sa.Column("entity_id", sa.String(36), sa.ForeignKey("accounting_entities.id"), nullable=True))
    op.add_column("financial_accounts", sa.Column("ledger_account_id", sa.String(36), sa.ForeignKey("ledger_accounts.id"), nullable=True))
    op.add_column("financial_accounts", sa.Column("accounting_initialized", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_financial_accounts_entity_id", "financial_accounts", ["entity_id"])
    op.create_index("ix_financial_accounts_ledger_account_id", "financial_accounts", ["ledger_account_id"])
    op.add_column("transactions", sa.Column("entity_id", sa.String(36), sa.ForeignKey("accounting_entities.id"), nullable=True))
    op.add_column("transactions", sa.Column("category_id", sa.String(36), sa.ForeignKey("ledger_accounts.id"), nullable=True))
    op.create_index("ix_transactions_entity_id", "transactions", ["entity_id"])
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    op.add_column("categorization_rules", sa.Column("category_id", sa.String(36), sa.ForeignKey("ledger_accounts.id"), nullable=True))
    op.create_index("ix_categorization_rules_category_id", "categorization_rules", ["category_id"])
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id"), nullable=False),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("accounting_entities.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True, unique=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="transaction"),
        sa.Column("status", sa.String(20), nullable=False, server_default="posted"),
        *audit_columns(),
    )
    for column in ("household_id", "entity_id", "transaction_id", "entry_date"):
        op.create_index(f"ix_journal_entries_{column}", "journal_entries", [column])
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), sa.ForeignKey("households.id"), nullable=False),
        sa.Column("journal_entry_id", sa.String(36), sa.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ledger_account_id", sa.String(36), sa.ForeignKey("ledger_accounts.id"), nullable=False),
        sa.Column("debit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("memo", sa.String(255), nullable=False, server_default=""),
        *audit_columns(),
        sa.CheckConstraint("debit >= 0 and credit >= 0 and ((debit = 0) <> (credit = 0))", name="ck_journal_line_one_side"),
    )
    for column in ("household_id", "journal_entry_id", "ledger_account_id"):
        op.create_index(f"ix_journal_lines_{column}", "journal_lines", [column])


def downgrade():
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_index("ix_categorization_rules_category_id", table_name="categorization_rules")
    op.drop_column("categorization_rules", "category_id")
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_index("ix_transactions_entity_id", table_name="transactions")
    op.drop_column("transactions", "category_id")
    op.drop_column("transactions", "entity_id")
    op.drop_index("ix_financial_accounts_ledger_account_id", table_name="financial_accounts")
    op.drop_index("ix_financial_accounts_entity_id", table_name="financial_accounts")
    op.drop_column("financial_accounts", "ledger_account_id")
    op.drop_column("financial_accounts", "accounting_initialized")
    op.drop_column("financial_accounts", "entity_id")
    op.drop_table("ledger_accounts")
    op.drop_table("accounting_entities")
    op.drop_column("households", "workspace_type")
