from decimal import Decimal
from app.account_onboarding_service import identify_institution, identify_kind, identify_mask
from app.statement_service import detected_cash_management_balance
from app.institution_directory import match_institution


def test_mission_lane_statement_identity_is_detected_generically():
    text="""MISSION LANE LLC
    Account Number: #### #### #### 8456
    Credit Limit $6,000.00
    Minimum Payment Warning
    Interest Charge Calculation
    Annual Percentage Rate (APR)
    """
    assert identify_institution(text)==("Mission Lane","high")
    assert identify_kind(text,"pdf")==("credit_card","high")
    assert identify_mask(text)==("8456","high")


def test_ofx_account_identity_uses_account_type_and_last_four():
    text="<OFX><FI><ORG>Example Credit Union</FI><BANKACCTFROM><ACCTID>00001234\n<ACCTTYPE>CHECKING\n"
    assert identify_institution(text)==("Example Credit Union","medium")
    assert identify_kind(text,"ofx")==("checking","high")
    assert identify_mask(text)==("1234","high")


def test_ofx_structured_account_type_wins_over_transaction_descriptions():
    text = "<OFX><BANKACCTFROM><ACCTTYPE>CHECKING<STMTTRN><NAME>TD AUTO FINANCE PAYMENT"
    assert identify_kind(text, "qfx") == ("checking", "high")


def test_fidelity_cash_management_identity_and_balances():
    text=("FIDELITY CASH MANAGEMENT ACCOUNT\nAccount Number: Z26-166540\nINVESTMENT REPORT\n"
        "Ending Account Value $85.57\n100% Core Account ($85)\nTotal Core Account $95.49 $85.57")
    assert identify_institution(text)==("Fidelity","high")
    assert identify_kind(text,"pdf")==("cash_management","high")
    assert identify_mask(text)==("6540","high")
    assert detected_cash_management_balance(text,Decimal("85.57"))==Decimal("85.57")


def test_directory_matches_detected_statement_name_to_trusted_url():
    institution, confidence, source = match_institution("PNC BANK statement", "PNC Bank")
    assert institution is not None
    assert institution.id == "pnc"
    assert institution.login_url == "https://www.pnc.com/"
    assert confidence == "high"
    assert source == "statement institution name"


def test_unknown_institution_does_not_create_a_guessed_url():
    institution, confidence, _ = match_institution("Example Community Bank statement", "Example Community Bank")
    assert institution is None
    assert confidence == "low"
