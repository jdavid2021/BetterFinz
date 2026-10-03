from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from app.forecasting import calculate_coverage, forecast_message, projected_income_balances
from app.income import biweekly, weekly

def account(balance="1000",reserve="200"):
    return SimpleNamespace(available_balance=Decimal(balance),reserve=Decimal(reserve),name="Checking")
def payment(amount="500",days=1,pid="p1"):
    d=date(2026,1,1)+timedelta(days=days);return SimpleNamespace(id=pid,amount=Decimal(amount),earliest_withdrawal_date=d,status="planned")
def income(amount="500",days=2,reliability="guaranteed"):
    return SimpleNamespace(amount=Decimal(amount),expected_date=date(2026,1,1)+timedelta(days=days),reliability=reliability)
def test_covered_and_decimal_precision(): assert calculate_coverage(account(),[payment("500")],[])[0].status=="covered"
def test_tight(): assert calculate_coverage(account("800","200"),[payment("500")],[])[0].status=="covered_but_tight"
def test_reserve_breach(): assert calculate_coverage(account("650","200"),[payment("500")],[])[0].status=="would_breach_reserve"
def test_reliable_same_day_income_is_available_before_payment(): assert calculate_coverage(account("100","0"),[payment("500",2)],[income("500",2)])[0].status=="covered_but_tight"
def test_later_income_does_not_hide_a_shortfall(): assert calculate_coverage(account("100","0"),[payment("500",2)],[income("500",3)])[0].status=="depends_on_future_income"
def test_insufficient(): assert calculate_coverage(account("100","0"),[payment("500")],[])[0].status=="insufficient_funds"
def test_account_specific(): assert calculate_coverage(account("1000"),[payment("900")],[])[0].status != calculate_coverage(account("2000"),[payment("900")],[])[0].status
def test_same_day_payments_are_calculated_in_display_name_order():
    first=payment("100",2,"z");first.payee="Zeta"
    second=payment("200",2,"a");second.payee="Alpha"
    rows=calculate_coverage(account("1000","0"),[first,second],[])
    assert [(row.payment_id,row.balance_after) for row in rows]==[("a",Decimal("800")),("z",Decimal("700"))]
def test_paid_payment_is_not_deducted_from_current_balance():
    completed=payment("900",1,"paid");completed.status="paid";completed.payee="Already paid"
    upcoming=payment("200",2,"upcoming");upcoming.payee="Upcoming bill"
    rows=calculate_coverage(account("500","0"),[completed,upcoming],[])
    assert [(row.payment_id,row.balance_after) for row in rows]==[("upcoming",Decimal("300"))]

def test_payment_already_covered_by_current_balance_date_needs_confirmation_without_double_counting():
    past=payment("900",1,"past");past.payee="Past scheduled payment"
    upcoming=payment("200",3,"upcoming");upcoming.payee="Upcoming bill"
    rows=calculate_coverage(account("500","0"),[past,upcoming],[],balance_as_of_date=date(2026,1,2))
    assert [(row.payment_id,row.status,row.balance_after) for row in rows]==[
        ("past","needs_confirmation",Decimal("500")),
        ("upcoming","covered",Decimal("300")),
    ]

def test_forecast_message_uses_highest_severity_reason():
    rows=[
        {"status":"planned","coverage_status":"covered_but_tight","reason":"Tight first."},
        {"status":"planned","coverage_status":"insufficient_funds","reason":"Unfunded later."},
    ]
    assert forecast_message(rows)==("Some scheduled payments are not currently funded","Unfunded later.")

def test_forecast_message_calls_out_past_payments_needing_confirmation():
    rows=[{"status":"scheduled","coverage_status":"needs_confirmation","reason":"Confirm the past payment."}]
    assert forecast_message(rows)==("Some past payments need confirmation","Confirm the past payment.")

def test_paid_payment_does_not_reduce_projected_income_balance():
    completed=payment("900",1,"paid");completed.status="paid";completed.payee="Already paid"
    deposit=income("100",2);deposit.id="income-paid-test";deposit.name="Payroll"
    assert projected_income_balances(account("500","0"),[completed],[deposit])["income-paid-test"]==Decimal("600")

def test_past_unconfirmed_payment_does_not_reduce_projected_income_balance_twice():
    past=payment("900",1,"past");past.payee="Past scheduled payment"
    deposit=income("100",3);deposit.id="income-current-balance-test";deposit.name="Payroll"
    assert projected_income_balances(account("500","0"),[past],[deposit],balance_as_of_date=date(2026,1,2))["income-current-balance-test"]==Decimal("600")

def test_income_row_exposes_balance_immediately_after_deposit():
    deposit=income("500",2);deposit.id="income-1";deposit.name="Payroll"
    before=payment("100",1,"before");before.payee="Earlier bill"
    after=payment("200",3,"after");after.payee="Later bill"
    assert projected_income_balances(account("1000","0"),[before,after],[deposit])["income-1"]==Decimal("1400")
def test_unconfirmed_income_does_not_fund_payments():
    deposit=income("500",2);deposit.id="income-unconfirmed";deposit.name="Payroll";deposit.include_in_forecast=False
    assert calculate_coverage(account("100","0"),[payment("400",3)],[deposit])[0].status=="insufficient_funds"
def test_biweekly_does_not_reset_month(): assert biweekly(date(2026,1,2),date(2026,1,1),date(2026,2,1))==[date(2026,1,2),date(2026,1,16),date(2026,1,30)]
def test_weekly_weekday(): assert all(d.weekday()==4 for d in weekly(4,date(2026,1,1),date(2026,1,31)))
