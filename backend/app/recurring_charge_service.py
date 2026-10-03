from calendar import monthrange
from collections import defaultdict
from datetime import date,timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorization_service import normalize_description
from app.models import BillProfile,FinancialAccount,RecurringChargeSeries,Transaction

ACCOUNT_KINDS={"checking","savings","money_market","cash_management","credit_card"}
EXCLUDED_CATEGORIES={"income","transfer","mortgage payment","loan payment","credit card payment"}
EXCLUDED_WORDS={"payment thank","card payment","loan payment","mortgage payment","cash advance","balance transfer"}
SUBSCRIPTION_WORDS={"subscription","membership","netflix","spotify","hulu","disney","paramount","peacock","adobe","dropbox","icloud","microsoft","youtube","audible","patreon","gym"}


def _add_months(value:date,count:int)->date:
    index=value.month-1+count;year=value.year+index//12;month=index%12+1
    return date(year,month,min(value.day,monthrange(year,month)[1]))


def _frequency(gap:int)->tuple[str,int,int]|None:
    if 5<=gap<=10:return "weekly",7,3
    if 20<=gap<=45:return "monthly",30,8
    if 70<=gap<=120:return "quarterly",91,18
    if 300<=gap<=400:return "annual",365,35
    return None


def detected_recurring_charges(db:Session,household_id:str,as_of:date|None=None)->list[dict]:
    del as_of
    rows=db.execute(select(Transaction,FinancialAccount).join(FinancialAccount,FinancialAccount.id==Transaction.account_id).where(Transaction.household_id==household_id,Transaction.direction=="debit",Transaction.pending.is_(False),Transaction.is_transfer.is_(False),FinancialAccount.is_active,FinancialAccount.kind.in_(ACCOUNT_KINDS)).order_by(Transaction.posted_date)).all()
    bill_patterns=set(db.scalars(select(BillProfile.merchant_pattern).where(BillProfile.household_id==household_id,BillProfile.is_active)))
    groups:dict[tuple[str,str],list[tuple[Transaction,FinancialAccount]]]=defaultdict(list)
    for transaction,account in rows:
        combined=normalize_description(f"{transaction.merchant} {transaction.original_description}")
        if transaction.category.lower() in EXCLUDED_CATEGORIES or any(word in combined for word in EXCLUDED_WORDS):continue
        pattern=normalize_description(transaction.merchant) or normalize_description(transaction.original_description)
        if pattern and pattern not in bill_patterns:groups[(account.id,pattern)].append((transaction,account))
    candidates=[]
    for (account_id,pattern),items in groups.items():
        if len(items)<2:continue
        transactions=[item[0] for item in items];dates=[item.posted_date for item in transactions]
        gaps=[(right-left).days for left,right in zip(dates,dates[1:]) if right>left]
        if not gaps:continue
        typical_gap=round(median(gaps));frequency_data=_frequency(typical_gap)
        if not frequency_data:continue
        frequency,expected_gap,tolerance=frequency_data
        consistent=max(abs(gap-expected_gap) for gap in gaps)<=tolerance
        amounts=[abs(Decimal(item.amount)) for item in transactions]
        typical_amount=(sum(amounts,Decimal("0"))/len(amounts)).quantize(Decimal("0.01"))
        variation=((max(amounts)-min(amounts))/typical_amount).quantize(Decimal("0.0001")) if typical_amount else Decimal("1")
        text=f"{pattern} {transactions[-1].category}".lower();explicit=any(word in text for word in SUBSCRIPTION_WORDS) or "recurring" in normalize_description(transactions[-1].original_description)
        if not consistent or variation>Decimal("0.15") or (len(items)<3 and not explicit):continue
        suggested_type="subscription" if any(word in text for word in SUBSCRIPTION_WORDS) else "recurring_bill"
        next_date=dates[-1]+timedelta(days=7) if frequency=="weekly" else _add_months(dates[-1],{"monthly":1,"quarterly":3,"annual":12}[frequency])
        multiplier={"weekly":Decimal("52"),"monthly":Decimal("12"),"quarterly":Decimal("4"),"annual":Decimal("1")}[frequency]
        candidates.append({"id":f"{account_id}:{pattern}","name":transactions[-1].merchant,"merchant_pattern":pattern,"account_id":account_id,"account_name":items[0][1].name,"account_kind":items[0][1].kind,"typical_amount":str(typical_amount),"last_amount":str(amounts[-1]),"last_charge":dates[-1].isoformat(),"next_expected":next_date.isoformat(),"frequency":frequency,"occurrences":len(items),"confidence":"high" if len(items)>=3 and variation<=Decimal("0.05") else "medium","amount_variation":str(variation),"annual_cost":str((typical_amount*multiplier).quantize(Decimal("0.01"))),"suggested_type":suggested_type,"reason":f"{len(items)} similar charges, about every {typical_gap} days"})
    return sorted(candidates,key=lambda item:(item["confidence"]!="high",item["next_expected"],item["name"].lower()))


def recurring_charge_overview(db:Session,household_id:str,as_of:date|None=None)->dict:
    detected=detected_recurring_charges(db,household_id,as_of);by_key={(item["account_id"],item["merchant_pattern"]):item for item in detected}
    stored=list(db.scalars(select(RecurringChargeSeries).where(RecurringChargeSeries.household_id==household_id)))
    decisions={(row.account_id,row.merchant_pattern):row for row in stored}
    candidates=[item for item in detected if (item["account_id"],item["merchant_pattern"]) not in decisions]
    confirmed=[]
    for row in stored:
        if row.status!="confirmed":continue
        live=by_key.get((row.account_id,row.merchant_pattern))
        confirmed.append(live|{"id":row.id,"series_type":row.series_type,"status":row.status} if live else {"id":row.id,"name":row.name,"merchant_pattern":row.merchant_pattern,"account_id":row.account_id,"account_name":db.scalar(select(FinancialAccount.name).where(FinancialAccount.id==row.account_id)) or "Account","typical_amount":str(row.typical_amount),"last_charge":row.last_charge_date.isoformat(),"next_expected":row.next_expected_date.isoformat(),"frequency":row.frequency,"occurrences":row.occurrence_count,"confidence":row.confidence,"annual_cost":str(_annual_cost(row.typical_amount,row.frequency)),"series_type":row.series_type,"status":row.status})
    annual=sum((Decimal(item["annual_cost"]) for item in confirmed if item["series_type"]=="subscription"),Decimal("0"))
    return {"candidates":candidates,"confirmed":sorted(confirmed,key=lambda item:(item["next_expected"],item["name"].lower())),"annual_subscription_cost":str(annual.quantize(Decimal("0.01"))),"review_count":len(candidates)}


def _annual_cost(amount:Decimal,frequency:str)->Decimal:
    return (amount*{"weekly":Decimal("52"),"monthly":Decimal("12"),"quarterly":Decimal("4"),"annual":Decimal("1")}.get(frequency,Decimal("1"))).quantize(Decimal("0.01"))


def decide_recurring_charge(db:Session,household_id:str,body)->RecurringChargeSeries:
    account=db.scalar(select(FinancialAccount).where(FinancialAccount.id==body.account_id,FinancialAccount.household_id==household_id,FinancialAccount.is_active))
    if not account:raise LookupError("Account not found.")
    pattern=normalize_description(body.merchant_pattern)
    candidate=next((item for item in detected_recurring_charges(db,household_id) if item["account_id"]==body.account_id and item["merchant_pattern"]==pattern),None)
    if not candidate:raise ValueError("This recurring-charge suggestion is no longer available.")
    row=db.scalar(select(RecurringChargeSeries).where(RecurringChargeSeries.household_id==household_id,RecurringChargeSeries.account_id==body.account_id,RecurringChargeSeries.merchant_pattern==pattern))
    if not row:
        row=RecurringChargeSeries(household_id=household_id,account_id=body.account_id,merchant_pattern=pattern,name=candidate["name"],typical_amount=Decimal(candidate["typical_amount"]),frequency=candidate["frequency"],last_charge_date=date.fromisoformat(candidate["last_charge"]),next_expected_date=date.fromisoformat(candidate["next_expected"]),confidence=candidate["confidence"],occurrence_count=candidate["occurrences"],amount_variation=Decimal(candidate["amount_variation"]),data_source="user_review")
        db.add(row)
    row.status="dismissed" if body.decision=="dismissed" else "confirmed"
    row.series_type="subscription" if body.decision=="subscription" else "recurring_bill"
    db.commit();db.refresh(row);return row


def upcoming_confirmed_charges(db:Session,household_id:str,start:date,end:date)->list[dict]:
    return [item for item in recurring_charge_overview(db,household_id,start)["confirmed"] if start<=date.fromisoformat(item["next_expected"])<=end]
