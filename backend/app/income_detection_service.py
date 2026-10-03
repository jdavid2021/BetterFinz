import hashlib
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.categorization_service import normalize_description
from app.models import FinancialAccount, IncomeEvent, Transaction

INCOME_WORDS=("payroll","salary","social security","ssa","pension","benefit","paycheck")

def income_candidates(db:Session,household_id:str,as_of:date|None=None)->list[dict]:
    as_of=as_of or date.today()
    rows=db.execute(select(Transaction,FinancialAccount).join(FinancialAccount,FinancialAccount.id==Transaction.account_id).where(Transaction.household_id==household_id,FinancialAccount.household_id==household_id,FinancialAccount.kind.in_({"checking","cash_management"}),FinancialAccount.is_active,Transaction.direction=="credit",Transaction.category=="Income",Transaction.pending.is_(False)).order_by(Transaction.posted_date)).all()
    existing=list(db.scalars(select(IncomeEvent).where(IncomeEvent.household_id==household_id,IncomeEvent.data_source!="seed")))
    groups=defaultdict(list)
    for transaction,account in rows:
        key=normalize_description(transaction.original_description) or normalize_description(transaction.merchant)
        if key:groups[(account.id,key)].append((transaction,account))
    candidates=[]
    for (account_id,key),items in groups.items():
        if any(item.account_id==account_id and normalize_description(item.name)==key for item in existing):continue
        transactions=[item[0] for item in items];account=items[0][1];amounts=[Decimal(item.amount) for item in transactions];dates=[item.posted_date for item in transactions]
        gaps=[(right-left).days for left,right in zip(dates,dates[1:]) if right>left];typical_gap=round(median(gaps)) if gaps else None
        recurring=typical_gap is not None and 5<=typical_gap<=40 and len(transactions)>=3
        keyword=any(word in " ".join(item.original_description.lower() for item in transactions) for word in INCOME_WORDS)
        typical_amount=sum(amounts,Decimal("0"))/len(amounts)
        meaningful=typical_amount>=Decimal("50")
        reliability="guaranteed" if recurring and meaningful else "high_confidence" if keyword and meaningful else "uncertain"
        next_date=dates[-1]+timedelta(days=typical_gap) if recurring else max(dates[-1],as_of)
        while recurring and next_date<as_of:next_date+=timedelta(days=typical_gap)
        candidates.append({"id":hashlib.sha256(f"{account_id}|{key}".encode()).hexdigest()[:20],"name":transactions[-1].merchant,"account_id":account_id,"account_name":account.name,"amount":str(typical_amount.quantize(Decimal("0.01"))),"next_date":next_date.isoformat(),"reliability":reliability,"occurrences":len(transactions),"frequency_days":typical_gap,"last_received":dates[-1].isoformat(),"last_amount":str(amounts[-1])})
    return sorted(candidates,key=lambda item:(item["reliability"]=="uncertain",item["next_date"],item["name"]))
