import json, urllib.request
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.models import DebtStrategySnapshot, FinancialAccount, LiabilityStatement, ScheduledPayment
from app.schemas import LiabilityStatementCreate, LiabilityScheduleRequest

def create_statement(db:Session,hid:str,body:LiabilityStatementCreate):
    account=db.scalar(select(FinancialAccount).where(FinancialAccount.id==body.account_id,FinancialAccount.household_id==hid,FinancialAccount.is_active))
    if not account:return None
    row=LiabilityStatement(household_id=hid,**body.model_dump(),data_source="statement");account.balance=body.new_balance;db.add(row);db.commit();db.refresh(row);return row

def statement_data(row,account):
    return {"id":row.id,"account_id":row.account_id,"account_name":account.name,"opening_balance":str(row.opening_balance),"new_balance":str(row.new_balance),"new_payments":str(row.new_payments),"statement_date":row.statement_date.isoformat(),"due_date":row.due_date.isoformat(),"minimum_payment":str(row.minimum_payment),"interest_rate":str(row.interest_rate) if row.interest_rate is not None else None,"interest_paid":str(row.interest_paid)}

def latest_statements(db:Session,hid:str):
    accounts={a.id:a for a in db.scalars(select(FinancialAccount).where(FinancialAccount.household_id==hid,FinancialAccount.is_active))};rows=list(db.scalars(select(LiabilityStatement).where(LiabilityStatement.household_id==hid).order_by(LiabilityStatement.statement_date.desc())));latest={}
    for row in rows:
        if row.account_id in accounts and row.account_id not in latest:latest[row.account_id]=statement_data(row,accounts[row.account_id])
    return list(latest.values())

def saved_strategy(db:Session,hid:str):
    row=db.scalar(select(DebtStrategySnapshot).where(DebtStrategySnapshot.household_id==hid).order_by(DebtStrategySnapshot.created_at.desc()))
    if not row:return None
    result=json.loads(row.payload);result["generated_at"]=row.created_at.isoformat();return result

def generate_strategy(db:Session,hid:str):
    debts=latest_statements(db,hid);ordered=sorted(debts,key=lambda d:Decimal(d["interest_rate"] or "-1"),reverse=True);minimum_total=sum(Decimal(d["minimum_payment"]) for d in ordered);summary={"minimum_total":str(minimum_total),"priority":ordered,"method":"highest_interest_first","advice":"Pay every minimum by its due date, then direct extra cash to the highest-APR debt. Avoid new borrowing unless it is essential and improves total cost and cash-flow risk."}
    if settings.openai_api_key and ordered:
        safe=[{"name":d["account_name"],"balance":d["new_balance"],"apr":d["interest_rate"],"interest_paid":d["interest_paid"],"minimum":d["minimum_payment"],"due_date":d["due_date"]} for d in ordered]
        body={"model":settings.openai_transaction_model,"input":"Give concise debt-reduction coaching from this structured profile. Protect all minimums first, prioritize highest APR for extra payments, warn against unnecessary new loans, state uncertainty, and never claim to move money.\n"+json.dumps(safe),"reasoning":{"effort":"low"}}
        request=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {settings.openai_api_key}","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(request,timeout=30) as response:payload=json.load(response)
            summary["advice"]=next(part["text"] for output in payload["output"] for part in output.get("content",[]) if part.get("type")=="output_text")
        except Exception:pass
    row=DebtStrategySnapshot(household_id=hid,payload=json.dumps(summary),data_source="ai" if settings.openai_api_key and ordered else "rules")
    db.add(row);db.commit();db.refresh(row);summary["generated_at"]=row.created_at.isoformat();return summary

def schedule_liability(db:Session,hid:str,liability_id:str,body:LiabilityScheduleRequest):
    liability=db.scalar(select(LiabilityStatement).where(LiabilityStatement.id==liability_id,LiabilityStatement.household_id==hid));checking=db.scalar(select(FinancialAccount).where(FinancialAccount.id==body.checking_account_id,FinancialAccount.household_id==hid,FinancialAccount.kind.in_({"checking","cash_management"}),FinancialAccount.is_active))
    if not liability or not checking:return None
    debt=db.get(FinancialAccount,liability.account_id);payment=ScheduledPayment(household_id=hid,account_id=checking.id,obligation_account_id=liability.account_id,payee=debt.name if debt else "Debt payment",amount=body.amount,minimum_amount=liability.minimum_payment,scheduled_date=body.scheduled_date,earliest_withdrawal_date=body.scheduled_date,latest_withdrawal_date=body.scheduled_date,due_date=liability.due_date,method="manual_external_payment",status="planned",notes="Created from liability statement")
    db.add(payment);db.commit();db.refresh(payment);return payment


def import_liability_pdf(db:Session,hid:str,account:FinancialAccount,content:bytes):
    import io, re
    from datetime import datetime
    from pypdf import PdfReader
    text="\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    def amount(labels,required=True):
        for label in labels:
            match=re.search(label+r"\s*[:\-]?\s*\$?([0-9,]+\.\d{2})",text,re.I)
            if match:return Decimal(match.group(1).replace(",",""))
        if required:raise ValueError("A required statement amount could not be identified. Enter the statement details manually.")
        return Decimal("0")
    def dated(labels):
        for label in labels:
            match=re.search(label+r"\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",text,re.I)
            if match:
                value=match.group(1)
                for fmt in ("%B %d, %Y","%b %d, %Y","%m/%d/%Y","%m/%d/%y"):
                    try:return datetime.strptime(value,fmt).date()
                    except ValueError:pass
        raise ValueError("A required statement date could not be identified. Enter the statement details manually.")
    apr=None
    match=re.search(r"(?:purchase\s+apr|annual percentage rate|interest rate)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%",text,re.I)
    if match:apr=Decimal(match.group(1))
    body=LiabilityStatementCreate(account_id=account.id,opening_balance=amount([r"previous balance",r"opening balance"]),new_balance=amount([r"new balance",r"ending balance"]),new_payments=amount([r"payments(?: and other credits)?",r"payments received"],False),statement_date=dated([r"statement closing date",r"statement date",r"closing date"]),due_date=dated([r"payment due date",r"due date"]),minimum_payment=amount([r"minimum payment due",r"minimum payment"]),interest_rate=apr,interest_paid=amount([r"interest charged",r"interest paid",r"finance charge"],False))
    return create_statement(db,hid,body)
