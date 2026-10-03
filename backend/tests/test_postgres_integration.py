import os
import uuid
from decimal import Decimal

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import FinancialAccount, Household


pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


def test_postgres_16_schema_is_at_alembic_head(postgres_engine):
    expected_head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    with postgres_engine.connect() as connection:
        assert connection.dialect.name == "postgresql"
        assert connection.scalar(text("SHOW server_version_num")).startswith("16")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == expected_head

    tables = set(inspect(postgres_engine).get_table_names())
    assert {"users", "households", "financial_accounts", "financial_connections"} <= tables


def test_money_round_trip_and_household_foreign_key(postgres_engine):
    household_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())

    with Session(postgres_engine) as session:
        session.add(Household(id=household_id, name="PostgreSQL integration"))
        session.add(
            FinancialAccount(
                id=account_id,
                household_id=household_id,
                name="Checking",
                kind="checking",
                mask="1234",
                balance=Decimal("1234.56"),
                available_balance=Decimal("1200.01"),
                investment_balance=Decimal("0.00"),
                reserve=Decimal("50.00"),
            )
        )
        session.flush()

        account = session.scalar(select(FinancialAccount).where(FinancialAccount.id == account_id))
        assert account is not None
        assert account.balance == Decimal("1234.56")
        assert account.available_balance == Decimal("1200.01")
        session.rollback()

    with Session(postgres_engine) as session:
        session.add(
            FinancialAccount(
                household_id=str(uuid.uuid4()),
                name="Orphan",
                kind="checking",
                mask="9999",
                balance=Decimal("1.00"),
                available_balance=Decimal("1.00"),
                investment_balance=Decimal("0.00"),
                reserve=Decimal("0.00"),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
