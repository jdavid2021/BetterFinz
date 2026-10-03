import pytest
from pydantic import ValidationError
from app.schemas import AccountConnectionUpdate, ManualAccountCreate
from app.account_service import _available_balance, _reserve


def test_manual_bank_link_accepts_public_https_url():
    value = AccountConnectionUpdate(institution_name="Example Bank", bank_login_url="https://bank.example/login")
    assert value.bank_login_url == "https://bank.example/login"
    assert value.connection_mode == "manual"


@pytest.mark.parametrize("url", ["http://bank.example", "javascript:alert(1)", "https://user:pass@bank.example/login"])
def test_manual_bank_link_rejects_unsafe_urls(url):
    with pytest.raises(ValidationError):
        AccountConnectionUpdate(institution_name="Example Bank", bank_login_url=url)


def test_automatic_mode_is_not_available():
    with pytest.raises(ValidationError):
        AccountConnectionUpdate(institution_name="Example Bank", bank_login_url="https://bank.example", connection_mode="automatic")

def test_manual_account_creation_accepts_supported_account_details():
    value = ManualAccountCreate(institution_name="Example Bank", bank_login_url="https://bank.example", name="Household Checking", kind="checking", mask="1234", balance="100.00", available_balance="90.00", reserve="25.00")
    assert value.name == "Household Checking"
    assert str(value.available_balance) == "90.00"

def test_manual_account_creation_rejects_bad_mask_and_type():
    with pytest.raises(ValidationError):
        ManualAccountCreate(institution_name="Example Bank", bank_login_url="https://bank.example", name="Account", kind="unsupported", mask="12345", balance="0", available_balance="0")

def test_credit_card_keeps_available_credit_separate():
    value = ManualAccountCreate(institution_name="Example Bank", bank_login_url="https://bank.example", name="Rewards", kind="credit_card", mask="4501", balance="3892.14", available_balance="6107.86")
    assert _available_balance(value) == value.available_balance

def test_depository_account_keeps_available_balance():
    value = ManualAccountCreate(institution_name="Example Bank", bank_login_url="https://bank.example", name="Checking", kind="checking", mask="2048", balance="100", available_balance="80")
    assert _available_balance(value) == value.available_balance

def test_credit_card_forces_protected_reserve_to_zero():
    value = ManualAccountCreate(institution_name="Example Bank", bank_login_url="https://bank.example", name="Rewards", kind="credit_card", mask="4501", balance="500", available_balance="500", reserve="100")
    assert _reserve(value) == 0

def test_mortgage_requires_original_and_current_balances():
    value = ManualAccountCreate(institution_name="Example Bank", bank_login_url="https://bank.example", name="Home Mortgage", kind="mortgage", mask="9912", original_balance="450000", balance="391500")
    assert value.original_balance == 450000
    assert _available_balance(value) == 0
    assert _reserve(value) == 0

def test_mortgage_rejects_missing_original_balance():
    with pytest.raises(ValidationError):
        ManualAccountCreate(institution_name="Example Bank", bank_login_url="https://bank.example", name="Home Mortgage", kind="mortgage", mask="9912", balance="391500")

@pytest.mark.parametrize("kind", ["auto_loan", "buy_now_pay_later", "loan", "other"])
def test_installment_debt_uses_only_outstanding_balance(kind):
    value = ManualAccountCreate(institution_name="Example Lender", bank_login_url="https://lender.example", name="Installment debt", kind=kind, mask="7788", balance="4200", available_balance="900", reserve="250")
    assert _available_balance(value) == 0
    assert _reserve(value) == 0
