from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from app.models import FinancialAccount, IncomeEvent, ScheduledPayment

@dataclass
class Coverage:
    payment_id: str; status: str; balance_before: Decimal; balance_after: Decimal
    reason: str; income_dependency: str | None = None

RELIABLE = {"guaranteed", "high_confidence"}


def forecast_events(payments, incomes, include_uncertain=False):
    events=[]
    for payment in payments:
        if payment.status not in {"paid","cleared","cancelled","skipped","failed"}:
            events.append((payment.earliest_withdrawal_date,1,str(getattr(payment,"payee",payment.id)).lower(),"payment",payment))
    for income in incomes:
        eligible = getattr(income, "include_in_forecast", True)
        if eligible and (income.reliability in RELIABLE or (include_uncertain and income.reliability!="received_only")):
            events.append((income.expected_date,0,str(getattr(income,"name",getattr(income,"id",""))).lower(),"income",income))
    return sorted(events,key=lambda event:(event[0],event[1],event[2]))

def calculate_coverage(account: FinancialAccount, payments: list[ScheduledPayment], incomes: list[IncomeEvent], tight_threshold: Decimal = Decimal("150"), include_uncertain: bool = False, balance_as_of_date: date | None = None, starting_balance: Decimal | None = None) -> list[Coverage]:
    """Account-specific forecast: reliable dated income is available before same-day payments."""
    balance = Decimal(account.available_balance if starting_balance is None else starting_balance)
    results: list[Coverage] = []
    future_income_dates = {i.expected_date for i in incomes if i.reliability in RELIABLE and getattr(i, "include_in_forecast", True)}
    uncertain_dates = {i.expected_date for i in incomes if i.reliability not in RELIABLE and getattr(i, "include_in_forecast", True)}
    for _,_,_,kind,item in forecast_events(payments,incomes,include_uncertain):
        if kind == "income": balance += Decimal(item.amount); continue
        payment = item
        if balance_as_of_date and payment.earliest_withdrawal_date <= balance_as_of_date:
            reason = f"Confirm or match {payment.payee}; its payment date has passed and {account.name}'s current balance is newer."
            results.append(Coverage(payment.id, "needs_confirmation", balance, balance, reason))
            continue
        before, after = balance, balance - Decimal(payment.amount)
        if after < 0:
            later_reliable = any(payment.earliest_withdrawal_date <= d for d in future_income_dates)
            later_uncertain = any(payment.earliest_withdrawal_date <= d for d in uncertain_dates)
            if later_reliable:
                status, dependency, reason = "depends_on_future_income", "future_income", f"This depends on incoming money. {account.name} is projected to be short by ${abs(after):,.2f} first."
            elif later_uncertain:
                status, dependency, reason = "depends_on_uncertain_income", "uncertain_income", f"This would need uncertain income; {account.name} is short by ${abs(after):,.2f}."
            else:
                status, dependency, reason = "insufficient_funds", None, f"{account.name} is projected to be short by ${abs(after):,.2f}."
        elif after < Decimal(account.reserve):
            status, dependency, reason = "would_breach_reserve", None, f"It can clear, but {account.name} would fall below your ${account.reserve:,.2f} protected reserve."
        elif after - Decimal(account.reserve) < tight_threshold:
            status, dependency, reason = "covered_but_tight", None, f"Covered, but {account.name} may fall to ${after:,.2f}."
        else:
            status, dependency, reason = "covered", None, f"Covered. About ${after:,.2f} should remain afterward."
        results.append(Coverage(payment.id, status, before, after, reason, dependency))
        balance = after
    return results


def projected_income_balances(account, payments, incomes, include_uncertain=False, balance_as_of_date: date | None = None, starting_balance: Decimal | None = None):
    balance=Decimal(account.available_balance if starting_balance is None else starting_balance);result={}
    for _,_,_,kind,item in forecast_events(payments,incomes,include_uncertain):
        if kind=="income":
            balance+=Decimal(item.amount);result[item.id]=balance
        elif not balance_as_of_date or item.earliest_withdrawal_date > balance_as_of_date:
            balance-=Decimal(item.amount)
    return result


def forecast_message(payments: list[dict]) -> tuple[str, str]:
    active = [
        payment for payment in payments
        if payment["status"] not in {"paid", "cleared", "cancelled", "skipped", "failed"}
    ]
    if not active:
        return "All scheduled payments are covered", "Every scheduled payment stays above its account reserve."

    unfunded = {"insufficient_funds", "funding_account_not_selected"}
    dependencies = {"depends_on_pending_deposit", "depends_on_future_income", "depends_on_uncertain_income"}
    tight = {"covered_but_tight", "would_breach_reserve"}
    statuses = {payment["coverage_status"] for payment in active}
    if statuses & unfunded:
        headline = "Some scheduled payments are not currently funded"
    elif "needs_confirmation" in statuses:
        headline = "Some past payments need confirmation"
    elif statuses & dependencies:
        headline = "Some payments depend on incoming money"
    elif statuses & tight:
        headline = "Covered, but cash will be tight"
    else:
        headline = "All scheduled payments are covered"

    priority = {
        "insufficient_funds": 50,
        "funding_account_not_selected": 50,
        "needs_confirmation": 40,
        "depends_on_pending_deposit": 30,
        "depends_on_future_income": 30,
        "depends_on_uncertain_income": 30,
        "would_breach_reserve": 20,
        "covered_but_tight": 10,
    }
    most_important = max(active, key=lambda payment: priority.get(payment["coverage_status"], 0))
    reason = most_important["reason"] if priority.get(most_important["coverage_status"], 0) else "Every scheduled payment stays above its account reserve."
    return headline, reason
