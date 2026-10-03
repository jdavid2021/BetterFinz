from calendar import monthrange
from datetime import date
from decimal import Decimal
import re
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models import BillProfile, FinancialAccount, IncomeEvent, LiabilityStatement, ScheduledPayment
from app.biller_directory import get_biller, match_biller, public_biller

LIABILITY_KINDS={"credit_card","mortgage","auto_loan","buy_now_pay_later","loan","other"}

def normalized(value):return " ".join(re.sub(r"[^a-z0-9]+"," ",value.lower()).split())

def group_for(kind):
    if kind=="mortgage":return "Mortgage"
    if kind=="credit_card":return "Credit Cards"
    if kind in {"auto_loan","buy_now_pay_later","loan"}:return "Loans"
    return "Taxes and Other Debt"

def monthly_plan(db:Session,hid:str,year:int,month:int):
    if month<1 or month>12:raise ValueError("Month must be between 1 and 12.")
    start=date(year,month,1);end=date(year,month,monthrange(year,month)[1])
    accounts=list(db.scalars(select(FinancialAccount).where(FinancialAccount.household_id==hid,FinancialAccount.is_active)))
    liabilities=[a for a in accounts if a.kind in LIABILITY_KINDS]
    statements=list(db.scalars(select(LiabilityStatement).where(LiabilityStatement.household_id==hid).order_by(LiabilityStatement.statement_date.desc())))
    latest={}
    for statement in statements:
        if statement.account_id not in latest:latest[statement.account_id]=statement
    payments=list(db.scalars(select(ScheduledPayment).where(ScheduledPayment.household_id==hid,ScheduledPayment.data_source!="seed",or_(ScheduledPayment.due_date.between(start,end),ScheduledPayment.scheduled_date.between(start,end)))))
    bills={bill.id:bill for bill in db.scalars(select(BillProfile).where(BillProfile.household_id==hid,BillProfile.is_active))}
    unmatched=list(payments);rows=[]
    for account in liabilities:
        account_biller,_=match_biller(account.name,account.institution_name or "")
        account_key=normalized(account.name);payment_index=next((i for i,p in enumerate(unmatched) if p.obligation_account_id==account.id or account_key in normalized(p.payee) or normalized(p.payee) in account_key),None)
        payment=unmatched.pop(payment_index) if payment_index is not None else None
        statement=latest.get(account.id);statement_balance=statement.new_balance if statement else account.balance
        payment_amount=payment.amount if payment else Decimal("0");balance_after=max(account.balance-payment_amount,Decimal("0"))
        rows.append({"id":account.id,"group":group_for(account.kind),"account_name":account.name,"account_kind":account.kind,"due_date":(payment.due_date if payment else statement.due_date if statement else None),"paid_status":("awaiting_confirmation" if payment and payment.status in {"scheduled","planned","scheduled_at_biller"} and payment.scheduled_date<=date.today() else payment.status if payment else "not_planned"),"current_balance":str(account.balance),"statement_balance":str(statement_balance),"statement_date":(statement.statement_date.isoformat() if statement else account.balance_as_of_date.isoformat() if account.balance_as_of_date else None),"minimum_payment":str(statement.minimum_payment if statement else payment.minimum_amount if payment else Decimal("0")),"scheduled_date":payment.scheduled_date.isoformat() if payment else None,"paid_date":payment.paid_date.isoformat() if payment and payment.paid_date else None,"status_source":payment.status_source if payment else None,"payment_amount":str(payment_amount),"balance_after_payment":str(balance_after),"funding_account_id":payment.account_id if payment else None,"payment_id":payment.id if payment else None,"biller_contact":public_biller(account_biller,"high") if account_biller else None})
    for payment in unmatched:
        bill=bills.get(payment.bill_id)
        directory_biller=get_biller(bill.biller_directory_id) if bill and bill.biller_directory_id else None
        rows.append({"id":bill.id if bill else payment.id,"group":"Household Bills" if bill else "Monthly Expenses","account_name":payment.payee,"account_kind":"bill" if bill else "expense","due_date":payment.due_date,"paid_status":("awaiting_confirmation" if payment.status in {"scheduled","planned","scheduled_at_biller"} and payment.scheduled_date<=date.today() else payment.status),"current_balance":str(bill.remaining_balance) if bill and bill.remaining_balance is not None else None,"statement_balance":None,"statement_date":None,"minimum_payment":str(payment.minimum_amount),"scheduled_date":payment.scheduled_date.isoformat(),"paid_date":payment.paid_date.isoformat() if payment.paid_date else None,"status_source":payment.status_source,"payment_amount":str(payment.amount),"balance_after_payment":str(max(bill.remaining_balance-payment.amount,Decimal("0"))) if bill and bill.remaining_balance is not None else None,"funding_account_id":payment.account_id,"payment_id":payment.id,"biller_website_url":bill.website_url if bill else None,"biller_contact":public_biller(directory_biller) if directory_biller else None,"bill_payment_method":bill.payment_method if bill else None})
    order={"Mortgage":0,"Credit Cards":1,"Loans":2,"Household Bills":3,"Monthly Expenses":4,"Taxes and Other Debt":5}
    rows.sort(key=lambda row:(order.get(row["group"],9),row["due_date"] or end,row["account_name"]))
    cash=sum((a.available_balance for a in accounts if a.kind in {"checking","savings","money_market","cash_management"}),Decimal("0"))
    planned=sum((Decimal(row["payment_amount"]) for row in rows),Decimal("0"));debt=sum((Decimal(row["current_balance"]) for row in rows if row["current_balance"] is not None),Decimal("0"))
    income=list(db.scalars(select(IncomeEvent).where(IncomeEvent.household_id==hid,IncomeEvent.data_source!="seed",IncomeEvent.expected_date.between(start,end)).order_by(IncomeEvent.expected_date)))
    return {"month":f"{year:04d}-{month:02d}","starting_available_cash":str(cash),"planned_payments":str(planned),"outstanding_debt":str(debt),"unscheduled_count":sum(row["paid_status"] in {"not_planned","not_scheduled"} for row in rows),"accounts":[{"id":a.id,"name":a.name,"kind":a.kind,"institution_name":a.institution_name,"bank_login_url":a.bank_login_url} for a in accounts],"income":[{"id":item.id,"name":item.name,"date":item.expected_date.isoformat(),"amount":str(item.amount),"reliability":item.reliability,"account_id":item.account_id} for item in income],"rows":rows}
