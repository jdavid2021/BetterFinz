from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.accounting_service import ensure_household_accounting
from app.db import Base
from app.models import FinancialAccount, Household, Transaction
from app.statement_service import classify_rule, import_statement, parse_csv, parse_ofx


def statement_db():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_connected_statement_review_does_not_persist_missing_transactions():
    db=statement_db();household=Household(name="Household");db.add(household);db.flush()
    account=FinancialAccount(household_id=household.id,name="Online Checking",kind="checking",mask="1234",balance=Decimal("100"),available_balance=Decimal("100"),investment_balance=Decimal("0"),reserve=Decimal("0"),connection_mode="automatic",data_source="simplefin")
    db.add(account);db.flush();ensure_household_accounting(db,household.id)
    db.add(Transaction(household_id=household.id,account_id=account.id,original_description="GROCERY STORE",merchant="Grocery Store",amount=Decimal("12.00"),direction="debit",posted_date=date(2026,8,1),category="Groceries",classification_source="rules",classification_confidence=Decimal("1"),data_source="simplefin"));db.commit()
    content=b"Date,Description,Amount\n08/01/2026,GROCERY STORE,-12.00\n08/02/2026,UTILITY BILL,-45.00\n"

    result=import_statement(db,household.id,account,"statement.csv",content,None,import_transactions=False)

    assert result["review_only"] is True
    assert result["duplicates"]==1
    assert result["missing_transactions"]==1
    assert result["added"]==0
    assert db.scalar(select(func.count(Transaction.id)))==1


def test_approved_statement_import_adds_only_missing_transactions():
    db=statement_db();household=Household(name="Household");db.add(household);db.flush()
    account=FinancialAccount(household_id=household.id,name="Online Checking",kind="checking",mask="1234",balance=Decimal("100"),available_balance=Decimal("100"),investment_balance=Decimal("0"),reserve=Decimal("0"),connection_mode="automatic",data_source="simplefin")
    db.add(account);db.flush();ensure_household_accounting(db,household.id)
    db.add(Transaction(household_id=household.id,account_id=account.id,original_description="GROCERY STORE",merchant="Grocery Store",amount=Decimal("12.00"),direction="debit",posted_date=date(2026,8,1),category="Groceries",classification_source="rules",classification_confidence=Decimal("1"),data_source="simplefin"));db.commit()
    content=b"Date,Description,Amount\n08/01/2026,GROCERY STORE,-12.00\n08/02/2026,UTILITY BILL,-45.00\n"

    result=import_statement(db,household.id,account,"statement.csv",content,None,import_transactions=True)

    assert result["review_only"] is False
    assert result["duplicates"]==1
    assert result["added"]==1
    assert db.scalar(select(func.count(Transaction.id)))==2

def test_csv_parser_reads_common_statement_columns():
    rows=parse_csv(b"Date,Description,Amount\n08/01/2026,ACME PAYROLL,-1200.00\n")
    assert rows[0]["amount"]==Decimal("-1200.00")
    assert rows[0]["description"]=="ACME PAYROLL"


def test_fidelity_csv_skips_blank_preamble_and_legal_footer():
    content=(b"\xef\xbb\xbf\n\nRun Date,Account,Action,Description,Amount ($),Settlement Date\n"
        b"08/03/2026,Cash Management,BILL PAYMENT WATER,No Description,-35,\n\n"
        b'"The data in this spreadsheet is informational only."\n'
        b"Date downloaded 08/05/2026 09:39 am\n")
    rows=parse_csv(content)
    assert len(rows)==1
    assert rows[0]["description"]=="BILL PAYMENT WATER"
    assert rows[0]["amount"]==Decimal("-35.00")

def test_ofx_parser_reads_transactions():
    rows=parse_ofx(b"<STMTTRN><DTPOSTED>20260801<TRNAMT>-45.12<NAME>UTILITY BILL</STMTTRN>")
    assert rows[0]["amount"]==Decimal("-45.12")

def test_ofx_parser_accepts_timestamped_transaction_dates():
    from datetime import date
    rows=parse_ofx(b"<STMTTRN><DTPOSTED>20260803000000.000<TRNAMT>125.00<NAME>DIRECT DEPOSIT</STMTTRN>")
    assert rows[0]["date"]==date(2026,8,3)

def test_rules_identify_essential_debt_and_income_categories():
    assert classify_rule("ACME PAYROLL DIRECT DEP")[0]=="Income"
    assert classify_rule("HOME MORTGAGE ACH")[0]=="Mortgage Payment"
    assert classify_rule("AFFIRM LOAN PAYMENT")[0]=="Loan Payment"

def test_unknown_rule_falls_back_to_uncategorized():
    category,confidence,source=classify_rule("MYSTERY 81819")
    assert category=="Uncategorized"
    assert confidence==0
    assert source=="unclassified"

def test_ofx_detects_ledger_closing_balance():
    from app.statement_service import detected_closing_balance
    content=b"<LEDGERBAL><BALAMT>1234.56<DTASOF>20260801</LEDGERBAL>"
    assert detected_closing_balance("ofx",content)==Decimal("1234.56")

def test_csv_detects_last_running_balance():
    from app.statement_service import detected_closing_balance
    content=b"Date,Description,Amount,Balance\n08/01/2026,STORE,-12.00,988.00\n"
    assert detected_closing_balance("csv",content)==Decimal("988.00")

def test_ai_candidate_text_redacts_identifiers_and_keeps_transaction_lines():
    from app.statement_service import redact_transaction_text
    text="Account number: 123456789\nFor the period 04/01/2026 to 04/30/2026\n04/20 42.18 MERCHANT REFERENCE 123456789\nCall 888-555-1212"
    redacted=redact_transaction_text(text)
    assert "123456789" not in redacted
    assert "888-555-1212" not in redacted
    assert "04/20" in redacted
    assert "42.18" in redacted

def test_learned_pattern_removes_variable_references():
    from app.categorization_service import learnable_pattern
    first=learnable_pattern("WEB PMT DUKEENERGYCORP 302612345")
    second=learnable_pattern("Web Payment DukeEnergyCorp 998877665")
    assert first==second=="dukeenergycorp"

def test_vague_payment_does_not_create_learning_pattern():
    from app.categorization_service import learnable_pattern
    assert learnable_pattern("WEB PMT ONLINE PAYMENT 123456") is None

def test_pdf_statement_period_sets_balance_date():
    from datetime import date
    from app.statement_service import statement_balance_date
    rows=[{"date":date(2026,5,18),"description":"STORE","amount":Decimal("-1.00")}]
    assert statement_balance_date("pdf",b"","For the period 04/21/2026 to 05/20/2026",rows)==date(2026,5,20)


def test_ofx_statement_end_date_is_preferred_over_transaction_date():
    from datetime import date
    from app.statement_service import statement_balance_date
    content=b"<DTEND>20260831<STMTTRN><DTPOSTED>20260820"
    rows=[{"date":date(2026,8,20),"description":"STORE","amount":Decimal("-1.00")}]
    assert statement_balance_date("ofx",content,"",rows)==date(2026,8,31)


def test_csv_uses_newest_transaction_as_balance_date_fallback():
    from datetime import date
    from app.statement_service import statement_balance_date
    rows=[{"date":date(2026,7,2)},{"date":date(2026,7,29)}]
    assert statement_balance_date("csv",b"","",rows)==date(2026,7,29)


def test_qbo_uses_ofx_statement_end_date():
    from datetime import date
    from app.statement_service import parse_ofx, statement_balance_date
    content=b"<DTSTART>20260701<DTEND>20260731<STMTTRN><DTPOSTED>20260729<TRNAMT>-7.50<NAME>STORE</STMTTRN>"
    rows=parse_ofx(content)
    assert statement_balance_date("qbo",content,"",rows)==date(2026,7,31)


def test_cross_format_descriptions_ignore_reference_noise():
    from app.statement_service import descriptions_similar
    assert descriptions_similar("POS PURCHASE DUKE ENERGY REF 302612345","Duke Energy Online Payment 998877665")


def test_different_merchants_are_not_cross_format_duplicates():
    from app.statement_service import descriptions_similar
    assert not descriptions_similar("TARGET STORE 1234","WALMART SUPERCENTER 5678")


def test_csv_parser_captures_bank_transaction_id():
    rows=parse_csv(b"Date,Description,Amount,Transaction ID\n08/01/2026,STORE,-12.00,bank-123\n")
    assert rows[0]["external_id"]=="bank-123"


def test_ofx_parser_captures_fitid():
    rows=parse_ofx(b"<STMTTRN><DTPOSTED>20260801<TRNAMT>-45.12<NAME>UTILITY<FITID>fit-456</STMTTRN>")
    assert rows[0]["external_id"]=="fit-456"


def test_file_format_is_detected_from_content_not_extension():
    from app.statement_service import detected_file_format
    assert detected_file_format("wrong.csv",b"%PDF-1.7\n")== ("pdf","csv")
    assert detected_file_format("download.dat",b"OFXHEADER:100\n<OFX><STMTTRN>")== ("ofx","dat")


def test_semicolon_csv_is_recovered_automatically():
    rows=parse_csv(b"Date;Description;Amount\n08/01/2026;STORE;-12.00\n")
    assert rows[0]["description"]=="STORE"
    assert rows[0]["amount"]==Decimal("-12.00")


def test_available_balance_is_extracted_only_when_explicit():
    from app.statement_service import detected_available_balance
    assert detected_available_balance("ofx",b"<AVAILBAL><BALAMT>987.65<DTASOF>20260801</AVAILBAL>")==Decimal("987.65")
    assert detected_available_balance("pdf",b"","Available Credit: $1,234.56")==Decimal("1234.56")
    assert detected_available_balance("pdf",b"","Ending Balance: $500.00") is None

def test_ofx_ledger_balance_is_available_cash_fallback_for_depository_accounts_only():
    from app.statement_service import imported_available_balance
    closing=Decimal("4097.73")
    assert imported_available_balance("checking","qfx",None,closing)==closing
    assert imported_available_balance("savings","ofx",None,closing)==closing
    assert imported_available_balance("credit_card","qfx",None,closing) is None
    assert imported_available_balance("checking","pdf",None,closing) is None
    assert imported_available_balance("checking","qfx",Decimal("3900.00"),closing)==Decimal("3900.00")


def test_implausibly_long_statement_range_is_rejected():
    from datetime import date
    from app.statement_service import validate_statement_rows
    import pytest
    with pytest.raises(ValueError,match="more than 400 days"):
        validate_statement_rows([{"date":date(2024,1,1),"description":"A"},{"date":date(2026,1,1),"description":"B"}])


def test_liability_statement_fields_are_captured_conservatively():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import liability_statement_values
    account=SimpleNamespace(id="credit-card-123",kind="credit_card")
    text="Previous Balance $1,100.00 New Balance $950.00 Payment Due Date 08/24/2026 Minimum Payment Due $45.00 Payments and Other Credits $150.00 Purchase APR 24.99% Interest Charged $18.25"
    values=liability_statement_values(account,"pdf",text,date(2026,8,3),Decimal("950.00"))
    assert values["account_id"]=="credit-card-123"
    assert values["due_date"]==date(2026,8,24)
    assert values["minimum_payment"]==Decimal("45.00")
    assert values["interest_rate"]==Decimal("24.99")


def test_liability_statement_is_not_created_when_due_fields_are_missing():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import liability_statement_values
    assert liability_statement_values(SimpleNamespace(id="credit-card-123",kind="credit_card"),"pdf","New Balance $950.00",date(2026,8,3),Decimal("950.00")) is None


def test_portal_activity_blocks_inherit_date_and_ignore_zero_amounts():
    from datetime import date
    from app.statement_service import parse_pdf_activity_blocks
    currency=chr(36)
    text=f"""A c c o u n t   A c t i v i t y
J  U  L  1  0  , 2  0  2  6
INTEREST CHARGE ON CASH ADVANCES     {currency} 0 .0 0
INTEREST CHARGE ON PURCHASES         {currency} 2 1 .7 9
J U L 0 4 , 2 0 2 6
LATE FEE                             {currency} 3 0 .0 0
CONTACT"""
    rows=parse_pdf_activity_blocks(text)
    assert [(row["date"],row["description"],row["amount"]) for row in rows]==[
        (date(2026,7,10),"INTEREST CHARGE ON PURCHASES",Decimal("21.79")),
        (date(2026,7,4),"LATE FEE",Decimal("30.00")),
    ]


def test_portal_date_due_label_is_supported():
    from datetime import date
    from app.statement_service import liability_statement_values
    from types import SimpleNamespace
    currency=chr(36)
    text=f"STATEMENT BALANCE {currency}876.04 MINIMUM PAYMENT DUE {currency}0.00 DATE DUE Aug 04, 2026"
    values=liability_statement_values(SimpleNamespace(id="best-buy",kind="credit_card"),"pdf",text,date(2026,7,10),Decimal("876.04"))
    assert values["due_date"]==date(2026,8,4)
    assert values["minimum_payment"]==Decimal("0.00")


def test_month_name_table_uses_post_date_and_explicit_sign():
    from datetime import date
    from app.statement_service import parse_pdf_named_table_rows
    currency=chr(36)
    text=f"Jul 7   Jul 7   CAPITAL ONE ONLINE PYMT   - {currency}198.00"
    rows=parse_pdf_named_table_rows(text,2026,7)
    assert rows==[{"date":date(2026,7,7),"description":"CAPITAL ONE ONLINE PYMT","amount":Decimal("-198.00")}]


def test_month_name_table_handles_year_rollover():
    from datetime import date
    from app.statement_service import parse_pdf_named_table_rows
    currency=chr(36)
    rows=parse_pdf_named_table_rows(f"Dec 30 Dec 31 YEAR END FEE {currency}12.00",2026,1)
    assert rows[0]["date"]==date(2025,12,31)


def test_pdf_billing_period_precedes_upcoming_closing_date():
    from datetime import date
    from app.statement_service import statement_balance_date
    text="Jun 13, 2026 - Jul 13, 2026 | Upcoming statement closing date: August 13, 2026"
    assert statement_balance_date("pdf",b"",text,[])==date(2026,7,13)


def test_capital_one_current_interest_and_purchase_apr_are_extracted():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import liability_statement_values
    currency=chr(36)
    text=f"Previous Balance {currency}5,392.90 New Balance {currency}5,314.24 Payment Due Date Aug 07, 2026 Minimum Payment Due {currency}172.00 Interest Charged + {currency}119.34 Total Interest charged {currency}767.06\nPurchases 25.99% P {currency}5,406.09 {currency}119.34"
    values=liability_statement_values(SimpleNamespace(id="capital-one",kind="credit_card"),"pdf",text,date(2026,7,13),Decimal("5314.24"))
    assert values["interest_paid"]==Decimal("119.34")
    assert values["interest_rate"]==Decimal("25.99")


def test_pdf_with_bounded_processing_preamble_is_detected_and_normalized():
    from app.statement_service import detected_file_format, pdf_payload
    content=b"%%E MEDIA: PROCESSOR.PASS:4471\n%PDF-1.3\nbody"
    assert detected_file_format("cfna.pdf",content)==("pdf","pdf")
    assert pdf_payload(content).startswith(b"%PDF-1.3")


def test_full_date_reference_table_parses_transaction_not_payment_coupon():
    from datetime import date
    from app.statement_service import parse_pdf_full_date_table_rows
    currency=chr(36)
    text=f"07/02/2026 8271742J73JMQ13AX BILLPAY ACH PMT-THANK YOU -{currency}200.00\n08/03/2026 {currency}182.53 6443 {currency}29.00 {currency}_______"
    rows=parse_pdf_full_date_table_rows(text)
    assert rows==[{"date":date(2026,7,2),"description":"BILLPAY ACH PMT-THANK YOU","amount":Decimal("-200.00")}]


def test_multi_column_detail_rows_do_not_import_a_trailing_balance_as_the_amount():
    from datetime import date
    from app.statement_service import parse_pdf_full_date_table_rows
    currency=chr(36)
    text=(f"07/02/2026 8271742J73JMQ13AX THE LAKES AT SABLE RIDG P ******7212 -{currency}75.00 525.00\n"
        f"07/17/2026 9912837K21LLQ04BZ NVIDIA CORPORATION COM 67066G104 You Sold -1.000 {currency}210.16000 209.10\n"
        "07/02/2026 8271742J73JMQ14AX BILL PAYMENT THE LAKES AT SABLE RIDG (Cash) -75.00")
    rows=parse_pdf_full_date_table_rows(text)
    assert rows==[{"date":date(2026,7,2),"description":"BILL PAYMENT THE LAKES AT SABLE RIDG (Cash)","amount":Decimal("-75.00")}]


def test_cfna_promotional_apr_is_extracted():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import liability_statement_values
    currency=chr(36)
    text=f"New Balance {currency}182.53 Payment Due Date 08/03/2026 Minimum Payment Due {currency}29.00\n6-Month Promo Purchase 01/24/26 34.990% {currency}457.85"
    values=liability_statement_values(SimpleNamespace(id="cfna",kind="credit_card"),"pdf",text,date(2026,7,8),Decimal("182.53"))
    assert values["interest_rate"]==Decimal("34.990")


def test_mortgage_ocr_summary_labels_are_extracted():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import detected_closing_balance, liability_statement_values, statement_balance_date
    currency=chr(36)
    text=f"Statement Date 07/15/2026\nTotal Payment Amount: {currency}3,996.64\nPayment Date* 08/01/2026\nOutstanding Principal Balance {currency}396,803.72"
    balance=detected_closing_balance("pdf",b"",text)
    statement_date=statement_balance_date("pdf",b"",text,[])
    values=liability_statement_values(SimpleNamespace(id="mortgage",kind="mortgage"),"pdf",text,statement_date,balance)
    assert balance==Decimal("396803.72")
    assert statement_date==date(2026,7,15)
    assert values["due_date"]==date(2026,8,1)
    assert values["minimum_payment"]==Decimal("3996.64")
    assert values["interest_rate"] is None


def test_best_egg_loan_summary_labels_are_extracted():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import detected_closing_balance, liability_statement_values, statement_balance_date
    currency=chr(36)
    text=f"Statement Date: July 21, 2026\nTotal Amount Due: {currency}510.17\nPayment Due By: September 18, 2026\nLast Payment Amount: {currency}255.09\nPrincipal Applied: {currency}185.63\nInterest Applied: {currency}69.46\nCurrent Balance: {currency}17,887.34"
    balance=detected_closing_balance("pdf",b"",text)
    statement_date=statement_balance_date("pdf",b"",text,[])
    values=liability_statement_values(SimpleNamespace(id="best-egg",kind="loan"),"pdf",text,statement_date,balance)
    assert balance==Decimal("17887.34")
    assert statement_date==date(2026,7,21)
    assert values["due_date"]==date(2026,9,18)
    assert values["minimum_payment"]==Decimal("510.17")
    assert values["new_payments"]==Decimal("255.09")
    assert values["interest_paid"]==Decimal("69.46")


def test_suncoast_auto_loan_summary_labels_are_extracted():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import detected_closing_balance, liability_statement_values, statement_balance_date
    text="Member Number: redacted 06/15/2026 - 07/14/2026\n2021 NISSAN ROGUE **Annual Percentage Rate** 6.500%\n06/15/2026 Balance Subject to Interest Rate 18,047.63\n06/29/2026 06/29/2026 Payments By Mail # 83.56 -290.08 373.64 17,757.55\nInterest Charge this Period 83.56\nCurrent Payment 373.64 Past Due 0.00 Total 373.64 Due Date 08/24/2026"
    balance=detected_closing_balance("pdf",b"",text)
    statement_date=statement_balance_date("pdf",b"",text,[])
    values=liability_statement_values(SimpleNamespace(id="suncoast",kind="auto_loan"),"pdf",text,statement_date,balance)
    assert balance==Decimal("17757.55")
    assert statement_date==date(2026,7,14)
    assert values["opening_balance"]==Decimal("18047.63")
    assert values["due_date"]==date(2026,8,24)
    assert values["minimum_payment"]==Decimal("373.64")
    assert values["new_payments"]==Decimal("373.64")
    assert values["interest_paid"]==Decimal("83.56")
    assert values["interest_rate"]==Decimal("6.500")


def test_short_date_reference_table_drops_leading_reference_ids():
    from datetime import date
    from app.statement_service import parse_pdf_short_date_table_rows
    currency=chr(36)
    text=(f"07/03  8141021JA00XS6H15         ONLINE PAYMENT THANK YOU                           -{currency}35.53\n"
        f"06/21   8141021HX00XTMJG5         WALMART 000988 LUTZ  FL                              {currency}54.52\n"
        f"07/17                 INTEREST CHARGE ON PURCHASES                         {currency}0.00")
    rows=parse_pdf_short_date_table_rows(text,2026,7)
    assert rows==[
        {"date":date(2026,7,3),"description":"ONLINE PAYMENT THANK YOU","amount":Decimal("-35.53")},
        {"date":date(2026,6,21),"description":"WALMART 000988 LUTZ FL","amount":Decimal("54.52")},
    ]


def test_short_date_table_uses_post_date_and_drops_trailing_reference():
    from datetime import date
    from app.statement_service import parse_pdf_short_date_table_rows
    currency=chr(36)
    text=(f"07/05     07/05     Payment Received -- Thank You         01210000        -{currency}139.63\n"
        f"06/09     06/08    Firmoo             Firmoo.Com DE        46930440         {currency}84.43\n"
        f"07/08    07/08     Monthly Account Fee                                        {currency}4.99")
    rows=parse_pdf_short_date_table_rows(text,2026,7)
    assert rows==[
        {"date":date(2026,7,5),"description":"Payment Received -- Thank You","amount":Decimal("-139.63")},
        {"date":date(2026,6,9),"description":"Firmoo Firmoo.Com DE","amount":Decimal("84.43")},
        {"date":date(2026,7,8),"description":"Monthly Account Fee","amount":Decimal("4.99")},
    ]


def test_short_date_table_handles_year_rollover():
    from datetime import date
    from app.statement_service import parse_pdf_short_date_table_rows
    rows=parse_pdf_short_date_table_rows(f"12/28  HOLIDAY STORE  {chr(36)}12.00",2026,1)
    assert rows[0]["date"]==date(2025,12,28)


def test_billing_cycle_end_sets_pdf_balance_date():
    from datetime import date
    from app.statement_service import statement_balance_date
    assert statement_balance_date("pdf",b"","31 day billing cycle from 06/20/2026 to 07/20/2026",[])==date(2026,7,20)
    assert statement_balance_date("pdf",b"","New Balance as of 07/17/2026",[])==date(2026,7,17)


def test_synchrony_summary_with_as_of_labels_and_na_apr_column():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import liability_statement_values
    currency=chr(36)
    text=(f"Previous balance as of 06/20/2026 {currency}843.01 Payments - 200.00 New balance as of 07/20/2026 {currency}1,140.12 "
        f"Minimum payment due {currency}35.00 Payment due date 08/12/2026\nPurchases & Balance Transfers N/A 30.24% (v)")
    values=liability_statement_values(SimpleNamespace(id="paypal",kind="credit_card"),"pdf",text,date(2026,7,20),Decimal("1140.12"))
    assert values["opening_balance"]==Decimal("843.01")
    assert values["due_date"]==date(2026,8,12)
    assert values["minimum_payment"]==Decimal("35.00")
    assert values["new_payments"]==Decimal("200.00")
    assert values["interest_rate"]==Decimal("30.24")


def test_mercury_summary_uses_singular_purchase_apr_row():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import liability_statement_values
    currency=chr(36)
    text=(f"Previous Balance {currency}3,891.56 Payments - {currency}139.63 New Balance {currency}4,072.52 "
        f"Minimum Payment Due {currency}141.26 Payment Due Date 08/05/2026\n   Purchase                30.24%   (v)")
    values=liability_statement_values(SimpleNamespace(id="mercury",kind="credit_card"),"pdf",text,date(2026,7,8),Decimal("4072.52"))
    assert values["opening_balance"]==Decimal("3891.56")
    assert values["due_date"]==date(2026,8,5)
    assert values["minimum_payment"]==Decimal("141.26")
    assert values["new_payments"]==Decimal("139.63")
    assert values["interest_rate"]==Decimal("30.24")


def test_horizontal_interest_table_distinguishes_periodic_rate_from_apr():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import liability_statement_values
    text=("Previous Balance $3,745.75 New Balance $3,992.45 Total Minimum Payment Due $175.03 "
        "Payment Due Date 08/04/26 Interest Charged $105.03\nInterest Charge Calculation\n"
        "Type Balance  Balance Subject to Interest Rate  Periodic Rate  Annual Percentage Rate (APR)  Interest Charge\n"
        "PURCHASES G $4,525.19 0.07737% (D) 28.24% (V) N/A $105.03")
    values=liability_statement_values(SimpleNamespace(id="card",kind="credit_card"),"pdf",text,date(2026,7,7),Decimal("3992.45"))
    assert values["interest_rate"]==Decimal("28.24")


def test_td_auto_loan_summary_labels_are_extracted():
    from datetime import date
    from types import SimpleNamespace
    from app.statement_service import detected_closing_balance, liability_statement_values, statement_balance_date
    currency=chr(36)
    text=f"Statement Date 07/11/2026 Payment Due Date 07/30/2026 Amount of Payments {currency}389.39 Current Amount Due {currency}366.24 Current Principal Balance {currency}4,945.65 Payment Received - Thank You {currency}206.00 Interest Charged Since Last Payment {currency}11.79"
    balance=detected_closing_balance("pdf",b"",text)
    statement_date=statement_balance_date("pdf",b"",text,[])
    values=liability_statement_values(SimpleNamespace(id="td-auto",kind="auto_loan"),"pdf",text,statement_date,balance)
    assert balance==Decimal("4945.65")
    assert statement_date==date(2026,7,11)
    assert values["due_date"]==date(2026,7,30)
    assert values["minimum_payment"]==Decimal("366.24")
    assert values["new_payments"]==Decimal("206.00")
    assert values["interest_paid"]==Decimal("11.79")

def test_service_charges_receive_specific_accounting_categories():
    assert classify_rule("DUKE ENERGY AUTOPAY")[0] == "Electricity & Gas"
    assert classify_rule("CITY WATER AUTOPAY")[0] == "Water & Sewer"
    assert classify_rule("WASTE CONNECTIONS")[0] == "Waste & Recycling"
    assert classify_rule("FRONTIER COMMU INTERNET")[0] == "Phone & Internet"
    assert classify_rule("NETFLIX.COM MONTHLY")[0] == "Software & Subscriptions"
