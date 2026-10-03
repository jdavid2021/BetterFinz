import hashlib
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.categorization_service import normalize_description
from app.biller_directory import get_biller, match_biller, public_biller
from app.models import BillProfile, FinancialAccount, IgnoredBillPattern, PaymentMatch, ScheduledPayment, Transaction

EXCLUDED_CATEGORIES = {"Income", "Transfer", "Mortgage Payment", "Loan Payment", "Credit Card Payment"}


def bill_candidates(db: Session, household_id: str, as_of: date | None = None) -> list[dict]:
    as_of = as_of or date.today()
    rows = db.execute(
        select(Transaction, FinancialAccount)
        .join(FinancialAccount, FinancialAccount.id == Transaction.account_id)
        .where(
            Transaction.household_id == household_id,
            Transaction.direction == "debit",
            Transaction.pending.is_(False),
            Transaction.is_transfer.is_(False),
            Transaction.category.not_in(EXCLUDED_CATEGORIES),
            FinancialAccount.kind.in_({"checking", "cash_management"}),
            FinancialAccount.is_active,
        )
        .order_by(Transaction.posted_date)
    ).all()
    existing_patterns = set(db.scalars(select(BillProfile.merchant_pattern).where(BillProfile.household_id == household_id, BillProfile.is_active)))
    existing_patterns.update(db.scalars(select(IgnoredBillPattern.merchant_pattern).where(IgnoredBillPattern.household_id==household_id)))
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for transaction, account in rows:
        key = normalize_description(transaction.original_description) or normalize_description(transaction.merchant)
        if key and key not in existing_patterns:
            groups[(account.id, key)].append((transaction, account))
    candidates = []
    for (account_id, key), items in groups.items():
        if len(items) < 2: continue
        transactions = [item[0] for item in items]
        dates = [item.posted_date for item in transactions]
        gaps = [(right-left).days for left, right in zip(dates, dates[1:]) if right > left]
        typical_gap = round(median(gaps)) if gaps else None
        if typical_gap is None or not 20 <= typical_gap <= 380: continue
        frequency = "monthly" if typical_gap <= 45 else "quarterly" if typical_gap <= 120 else "annual"
        amounts = [Decimal(item.amount) for item in transactions]
        typical_amount = (sum(amounts, Decimal("0"))/len(amounts)).quantize(Decimal("0.01"))
        variation = (max(amounts)-min(amounts))/typical_amount if typical_amount else Decimal("1")
        confidence = "high" if len(items) >= 3 and variation <= Decimal("0.25") else "medium"
        months = 1 if frequency == "monthly" else 3 if frequency == "quarterly" else 12
        # Keep the first unpaid expected date even when it has passed. Advancing
        # repeatedly to a future date hides an overdue bill from the current plan.
        next_date = _add_months(dates[-1], months)
        candidates.append({"id":hashlib.sha256(f"{account_id}|{key}".encode()).hexdigest()[:20],"name":transactions[-1].merchant,"merchant_pattern":key,"account_id":account_id,"account_name":items[0][1].name,"typical_amount":str(typical_amount),"last_amount":str(amounts[-1]),"last_paid":dates[-1].isoformat(),"next_date":next_date.isoformat(),"frequency":frequency,"occurrences":len(items),"confidence":confidence,"amount_type":"fixed" if variation <= Decimal("0.05") else "variable","category":transactions[-1].category,"history_signature":tuple((posted.isoformat(),str(amount)) for posted,amount in zip(dates,amounts))})
        biller,biller_confidence=match_biller(transactions[-1].merchant,key,transactions[-1].original_description)
        candidates[-1]["biller_suggestion"]=public_biller(biller,biller_confidence) if biller else None
    unique: dict[tuple[object, object], dict] = {}
    for candidate in candidates:
        signature=(candidate["account_id"],candidate.pop("history_signature"))
        current=unique.get(signature)
        score=lambda item:(item["category"]=="Bill",any(word in item["merchant_pattern"] for word in ("utilities","insurance","internet","wireless","energy","water","hoa")),"ach tel" not in item["merchant_pattern"])
        if current is None or score(candidate)>score(current):unique[signature]=candidate
    return sorted(unique.values(), key=lambda item: (item["confidence"] != "high", item["next_date"], item["name"]))


def _add_months(value: date, count: int) -> date:
    index=value.month-1+count;year=value.year+index//12;month=index%12+1
    return date(year,month,min(value.day,monthrange(year,month)[1]))


def create_bill(db: Session, household_id: str, body) -> BillProfile:
    if body.default_account_id and not db.scalar(select(FinancialAccount.id).where(FinancialAccount.id==body.default_account_id,FinancialAccount.household_id==household_id,FinancialAccount.kind.in_({"checking","cash_management"}),FinancialAccount.is_active)):
        raise ValueError("Choose an active checking or cash-management account.")
    pattern=normalize_description(body.merchant_pattern)
    if db.scalar(select(BillProfile.id).where(BillProfile.household_id==household_id,BillProfile.merchant_pattern==pattern,BillProfile.is_active)):
        raise ValueError("This bill has already been added.")
    trusted_biller=get_biller(body.biller_id) if body.biller_id else None
    if body.biller_id and not trusted_biller:raise ValueError("The selected company is not in the FinLeash biller directory.")
    website_url=trusted_biller.website_url if trusted_biller else body.website_url
    bill=BillProfile(household_id=household_id,name=body.name.strip(),merchant_pattern=pattern,category=body.category,bill_type=body.bill_type,amount_type=body.amount_type,typical_amount=body.typical_amount,frequency=body.frequency,due_day=body.due_date.day,default_account_id=body.default_account_id,website_url=website_url,biller_directory_id=trusted_biller.id if trusted_biller else None,payment_method=body.payment_method,remaining_balance=body.remaining_balance,installments_remaining=body.installments_remaining,data_source="detected_or_manual")
    db.add(bill);db.flush()
    count=1 if body.bill_type=="one_time" or body.frequency=="one_time" else min(body.installments_remaining or 12,12)
    step={"monthly":1,"quarterly":3,"annual":12,"one_time":0}[body.frequency]
    for index in range(count):
        due=_add_months(body.due_date,index*step) if step else body.due_date
        db.add(ScheduledPayment(household_id=household_id,account_id=body.default_account_id,bill_id=bill.id,payee=bill.name,amount=body.typical_amount,minimum_amount=body.typical_amount,scheduled_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,due_date=due,method=body.payment_method,status="not_planned",status_source="bill_profile",data_source="bill_profile"))
    db.commit();db.refresh(bill);return bill


def update_bill(db:Session,household_id:str,bill_id:str,body)->BillProfile:
    bill=db.scalar(select(BillProfile).where(BillProfile.id==bill_id,BillProfile.household_id==household_id,BillProfile.is_active))
    if not bill:raise ValueError("Bill not found.")
    if body.default_account_id and not db.scalar(select(FinancialAccount.id).where(FinancialAccount.id==body.default_account_id,FinancialAccount.household_id==household_id,FinancialAccount.kind.in_({"checking","cash_management"}),FinancialAccount.is_active)):
        raise ValueError("Choose an active checking or cash-management account.")
    pattern=normalize_description(body.merchant_pattern)
    duplicate=db.scalar(select(BillProfile.id).where(BillProfile.household_id==household_id,BillProfile.merchant_pattern==pattern,BillProfile.is_active,BillProfile.id!=bill.id))
    if duplicate:raise ValueError("Another bill already uses this transaction pattern.")
    trusted_biller=get_biller(body.biller_id) if body.biller_id else None
    if body.biller_id and not trusted_biller:raise ValueError("The selected company is not in the FinLeash biller directory.")
    bill.name=body.name.strip();bill.merchant_pattern=pattern;bill.category=body.category
    bill.bill_type=body.bill_type;bill.amount_type=body.amount_type;bill.typical_amount=body.typical_amount
    bill.frequency=body.frequency;bill.due_day=body.due_date.day;bill.default_account_id=body.default_account_id
    bill.website_url=trusted_biller.website_url if trusted_biller else body.website_url
    bill.biller_directory_id=trusted_biller.id if trusted_biller else None
    bill.payment_method=body.payment_method
    bill.remaining_balance=body.remaining_balance;bill.installments_remaining=body.installments_remaining
    db.execute(delete(ScheduledPayment).where(ScheduledPayment.bill_id==bill.id,ScheduledPayment.status=="not_planned",ScheduledPayment.due_date>=date.today()))
    existing_dates=set(db.scalars(select(ScheduledPayment.due_date).where(ScheduledPayment.bill_id==bill.id)))
    count=1 if body.bill_type=="one_time" or body.frequency=="one_time" else min(body.installments_remaining or 12,12)
    step={"monthly":1,"quarterly":3,"annual":12,"one_time":0}[body.frequency]
    for index in range(count):
        due=_add_months(body.due_date,index*step) if step else body.due_date
        if due in existing_dates:continue
        db.add(ScheduledPayment(household_id=household_id,account_id=body.default_account_id,bill_id=bill.id,payee=bill.name,amount=body.typical_amount,minimum_amount=body.typical_amount,scheduled_date=due,earliest_withdrawal_date=due,latest_withdrawal_date=due,due_date=due,method=body.payment_method,status="not_planned",status_source="bill_profile",data_source="bill_profile"))
    for payment in db.scalars(select(ScheduledPayment).where(ScheduledPayment.bill_id==bill.id,ScheduledPayment.status=="not_planned")):
        payment.payee=bill.name;payment.amount=body.typical_amount;payment.minimum_amount=body.typical_amount;payment.account_id=body.default_account_id;payment.method=body.payment_method
    db.commit();db.refresh(bill);return bill


def ignore_bill_candidate(db:Session,household_id:str,merchant_pattern:str)->None:
    pattern=normalize_description(merchant_pattern)
    if not db.scalar(select(IgnoredBillPattern.id).where(IgnoredBillPattern.household_id==household_id,IgnoredBillPattern.merchant_pattern==pattern)):
        db.add(IgnoredBillPattern(household_id=household_id,merchant_pattern=pattern,data_source="user"));db.commit()


def _payment_transaction_candidate(payment: ScheduledPayment, row: Transaction) -> dict | None:
    ignored_tokens={"ach","bill","check","debit","online","pay","payment","pmt","web"}
    payee=normalize_description(payment.payee);payee_tokens={token for token in payee.split() if token not in ignored_tokens}
    description=normalize_description(f"{row.merchant} {row.original_description}");description_tokens={token for token in description.split() if token not in ignored_tokens}
    overlap=Decimal(len(payee_tokens & description_tokens))/Decimal(len(payee_tokens)) if payee_tokens else Decimal("0")
    description_match=bool(payee and payee in description) or overlap>=Decimal("0.50")
    payment_amount=abs(Decimal(payment.amount));difference=abs(abs(Decimal(row.amount))-payment_amount);days=abs((row.posted_date-payment.due_date).days)
    close_threshold=max(Decimal("5"),payment_amount*Decimal("0.05"));broad_threshold=max(Decimal("5"),payment_amount*Decimal("0.10"))
    amount_points=55 if difference<=Decimal("0.01") else 40 if difference<=close_threshold else 25 if difference<=broad_threshold else 0
    score=min(100,amount_points+max(0,30-days)+(25 if description_match else 0))
    if score<70:return None
    confidence="high" if score>=85 else "medium"
    amount_reason="Exact amount" if difference<=Decimal("0.01") else f"Amount differs by {difference:.2f}"
    reason=amount_reason+" · "+str(days)+" day"+("s" if days!=1 else "")+" from due date"+(" · Payee matches" if description_match else "")
    return {"id":row.id,"merchant":row.merchant,"description":row.original_description,"amount":str(row.amount),"date":row.posted_date.isoformat(),"account_id":row.account_id,"score":score,"confidence":confidence,"reason":reason,"days_from_due":days,"description_match":description_match,"exact_amount":difference<=Decimal("0.01")}

def payment_match_candidates(db: Session, household_id: str, payment_id: str) -> list[dict]:
    payment=db.scalar(select(ScheduledPayment).where(ScheduledPayment.id==payment_id,ScheduledPayment.household_id==household_id))
    if not payment:return []
    start=payment.due_date-date.resolution*30;end=payment.due_date+date.resolution*30
    rows=db.execute(select(Transaction,FinancialAccount).join(FinancialAccount,FinancialAccount.id==Transaction.account_id).where(Transaction.household_id==household_id,Transaction.direction=="debit",Transaction.pending.is_(False),Transaction.is_transfer.is_(False),Transaction.posted_date.between(start,end),~Transaction.id.in_(select(PaymentMatch.transaction_id)),FinancialAccount.is_active,FinancialAccount.kind.in_({"checking","savings","money_market","cash_management"})).order_by(Transaction.posted_date.desc())).all()
    candidates=[]
    for transaction,account in rows:
        candidate=_payment_transaction_candidate(payment,transaction)
        if candidate is None:continue
        candidate["account_name"]=account.name
        candidate["account_matches"]=transaction.account_id==payment.account_id
        candidates.append(candidate)
    return sorted(candidates,key=lambda row:(not row["account_matches"],-row["score"],row["days_from_due"],row["date"]))[:8]


def match_open_scheduled_payments(db: Session, household_id: str) -> int:
    payments=list(db.scalars(select(ScheduledPayment).where(ScheduledPayment.household_id==household_id,ScheduledPayment.account_id.is_not(None),ScheduledPayment.status.in_({"not_planned","planned","scheduled","scheduled_at_biller"}),~ScheduledPayment.id.in_(select(PaymentMatch.payment_id)))))
    matched=0
    for payment in payments:
        candidates=[candidate for candidate in payment_match_candidates(db,household_id,payment.id) if candidate["account_matches"] and candidate["exact_amount"] and candidate["description_match"] and candidate["days_from_due"]<=14]
        if len(candidates)!=1:continue
        candidate=candidates[0]
        db.add(PaymentMatch(household_id=household_id,payment_id=payment.id,transaction_id=candidate["id"],match_type="sync_rule"))
        payment.status="paid";payment.paid_date=date.fromisoformat(candidate["date"]);payment.status_source="matched_transaction";matched+=1
        db.flush()
    return matched


def transaction_payment_contexts(db: Session, household_id: str, transaction_ids: list[str]) -> dict[str,dict]:
    ids=list(dict.fromkeys(transaction_ids));transactions=list(db.scalars(select(Transaction).where(Transaction.household_id==household_id,Transaction.id.in_(ids))))
    by_id={row.id:row for row in transactions};result:dict[str,dict]={row_id:{"matched":None,"suggestions":[],"options":[]} for row_id in ids if row_id in by_id}
    if not by_id:return result
    matched_rows=db.execute(select(PaymentMatch,ScheduledPayment).join(ScheduledPayment,ScheduledPayment.id==PaymentMatch.payment_id).where(PaymentMatch.household_id==household_id,PaymentMatch.transaction_id.in_(by_id))).all()
    for match,payment in matched_rows:
        result[match.transaction_id]["matched"]={"payment_id":payment.id,"payee":payment.payee,"due_date":payment.due_date.isoformat(),"amount":str(payment.amount),"status":payment.status,"match_type":match.match_type}
    account_ids={row.account_id for row in transactions};open_payments=list(db.scalars(select(ScheduledPayment).where(ScheduledPayment.household_id==household_id,ScheduledPayment.account_id.in_(account_ids),ScheduledPayment.status.in_({"not_planned","planned","scheduled","scheduled_at_biller"}),~ScheduledPayment.id.in_(select(PaymentMatch.payment_id)))))
    for transaction in transactions:
        if result[transaction.id]["matched"] or transaction.pending or transaction.direction!="debit" or transaction.is_transfer:continue
        suggestions=[]
        options=[]
        for payment in open_payments:
            if payment.account_id!=transaction.account_id or abs((transaction.posted_date-payment.due_date).days)>30:continue
            candidate=_payment_transaction_candidate(payment,transaction)
            if candidate:
                option={"payment_id":payment.id,"payee":payment.payee,"due_date":payment.due_date.isoformat(),"amount":str(payment.amount),"score":candidate["score"],"confidence":candidate["confidence"],"reason":candidate["reason"]};options.append(option)
                if candidate["description_match"] or (candidate["exact_amount"] and candidate["days_from_due"]<=3):suggestions.append(option)
        result[transaction.id]["suggestions"]=sorted(suggestions,key=lambda item:(-item["score"],item["due_date"],item["payee"]))[:3]
        result[transaction.id]["options"]=sorted(options,key=lambda item:(-item["score"],item["due_date"],item["payee"]))[:5]
    return result

def match_open_bill_payments(db: Session, household_id: str) -> int:
    payments=list(db.scalars(select(ScheduledPayment).where(ScheduledPayment.household_id==household_id,ScheduledPayment.bill_id.is_not(None),ScheduledPayment.status.in_({"not_planned","planned","scheduled","scheduled_at_biller"}))))
    bills={b.id:b for b in db.scalars(select(BillProfile).where(BillProfile.household_id==household_id,BillProfile.is_active))}
    matched=0
    for payment in payments:
        bill=bills.get(payment.bill_id)
        if not bill: continue
        start=payment.due_date.replace(day=1);end=_add_months(start,1)
        transactions=list(db.scalars(select(Transaction).where(Transaction.household_id==household_id,Transaction.direction=="debit",Transaction.posted_date>=start,Transaction.posted_date<end,Transaction.is_transfer.is_(False))))
        candidate=next((t for t in transactions if bill.merchant_pattern in normalize_description(t.original_description) and abs(Decimal(t.amount)-Decimal(payment.amount)) <= max(Decimal("5"),Decimal(payment.amount)*Decimal("0.20")) and not db.scalar(select(PaymentMatch.id).where(PaymentMatch.transaction_id==t.id))),None)
        if candidate:
            db.add(PaymentMatch(household_id=household_id,payment_id=payment.id,transaction_id=candidate.id,match_type="bill_rule"));payment.status="paid";payment.paid_date=candidate.posted_date;payment.amount=candidate.amount;payment.status_source="matched_transaction";matched+=1
    if matched: db.commit()
    return matched
