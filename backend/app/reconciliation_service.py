import json
from datetime import date
from decimal import Decimal,ROUND_HALF_UP
from itertools import combinations
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.accounting_service import ensure_household_accounting,rebuild_opening_balances
from app.models import AccountReconciliation,FinancialAccount,PaymentMatch,Transaction,TransactionMerge
from app.simplefin_service import cross_source_descriptions_similar

CENT=Decimal("0.01")
ASSET_KINDS={"checking","savings","money_market","cash_management","investment"}

class ReconciliationError(ValueError):pass

def money(value):return Decimal(value).quantize(CENT,rounding=ROUND_HALF_UP)

def account_for(db,hid,account_id):
 account=db.scalar(select(FinancialAccount).where(FinancialAccount.id==account_id,FinancialAccount.household_id==hid,FinancialAccount.is_active))
 if not account:raise ReconciliationError("Account not found.")
 return account

def public_transaction(row):
 return {"id":row.id,"account_id":row.account_id,"description":row.original_description,"merchant":row.merchant,"amount":str(row.amount),"direction":row.direction,"date":row.posted_date.isoformat(),"pending":row.pending,"category":row.category,"data_source":row.data_source,"is_transfer":row.is_transfer}

def duplicate_candidates(transactions):
 grouped: dict[tuple[str, date, Decimal, str], list[Transaction]] = {}
 for row in transactions:
  if not row.is_transfer:grouped.setdefault((row.account_id,row.posted_date,row.amount,row.direction),[]).append(row)
 result=[]
 for key,rows in grouped.items():
  if len(rows)<2:continue
  if not any(cross_source_descriptions_similar(left.original_description,right.original_description) for left,right in combinations(rows,2)):continue
  result.append({"key":"|".join((key[0],key[1].isoformat(),str(key[2]),key[3])),"transactions":[public_transaction(row) for row in rows]})
 return result

def review_duplicates(db:Session,hid:str,account_id:str|None=None):
 stmt=select(Transaction).where(Transaction.household_id==hid,Transaction.pending.is_(False)).order_by(Transaction.posted_date.desc(),Transaction.created_at.desc()).limit(2500)
 if account_id:
  account_for(db,hid,account_id);stmt=stmt.where(Transaction.account_id==account_id)
 groups=duplicate_candidates(list(db.scalars(stmt)))
 return {"count":len(groups),"groups":groups[:100]}

def preview_reconciliation(db:Session,hid:str,body):
 account=account_for(db,hid,body.account_id)
 transactions=list(db.scalars(select(Transaction).where(Transaction.household_id==hid,Transaction.account_id==account.id,Transaction.posted_date>=body.period_start,Transaction.posted_date<=body.period_end).order_by(Transaction.posted_date.desc(),Transaction.created_at.desc())))
 settled=[row for row in transactions if not row.pending];pending=[row for row in transactions if row.pending]
 credits=money(sum((row.amount for row in settled if row.direction=="credit"),Decimal("0")));debits=money(sum((row.amount for row in settled if row.direction=="debit"),Decimal("0")))
 opening=money(body.opening_balance);closing=money(body.closing_balance);asset=account.kind in ASSET_KINDS
 calculated=money(opening+credits-debits if asset else opening+debits-credits);difference=money(closing-calculated)
 if difference==0:explanation="The settled transactions reconcile exactly."
 elif asset and difference>0:explanation="Look for a missing credit or a duplicate debit."
 elif asset:explanation="Look for a missing debit or a duplicate credit."
 elif difference>0:explanation="Look for a missing charge or a duplicate payment."
 else:explanation="Look for a missing payment or a duplicate charge."
 return {"account":{"id":account.id,"name":account.name,"kind":account.kind,"mask":account.mask},"period_start":body.period_start.isoformat(),"period_end":body.period_end.isoformat(),"opening_balance":str(opening),"closing_balance":str(closing),"credits_total":str(credits),"debits_total":str(debits),"calculated_closing_balance":str(calculated),"difference":str(difference),"balanced":difference==0,"balance_mode":"asset" if asset else "liability","formula":"Opening + credits - debits" if asset else "Opening + debits - credits","difference_explanation":explanation,"transaction_count":len(settled),"pending_count":len(pending),"duplicate_candidates":duplicate_candidates(settled),"transactions":[public_transaction(row) for row in transactions]}

def complete_reconciliation(db:Session,hid:str,body):
 result=preview_reconciliation(db,hid,body)
 if not result["balanced"]:raise ReconciliationError("The difference must be $0.00 before this period can be reconciled.")
 existing=db.scalar(select(AccountReconciliation).where(AccountReconciliation.household_id==hid,AccountReconciliation.account_id==body.account_id,AccountReconciliation.period_start<=body.period_end,AccountReconciliation.period_end>=body.period_start))
 if existing:raise ReconciliationError("This account period overlaps a period that has already been reconciled.")
 row=AccountReconciliation(household_id=hid,account_id=body.account_id,period_start=body.period_start,period_end=body.period_end,opening_balance=body.opening_balance,closing_balance=body.closing_balance,credits_total=Decimal(result["credits_total"]),debits_total=Decimal(result["debits_total"]),calculated_closing_balance=Decimal(result["calculated_closing_balance"]),difference=Decimal(result["difference"]),transaction_count=result["transaction_count"],pending_count=result["pending_count"],notes=body.notes.strip(),data_source="reconciliation")
 db.add(row);db.commit();db.refresh(row);return public_reconciliation(row)

def public_reconciliation(row):
 return {"id":row.id,"account_id":row.account_id,"period_start":row.period_start.isoformat(),"period_end":row.period_end.isoformat(),"opening_balance":str(row.opening_balance),"closing_balance":str(row.closing_balance),"credits_total":str(row.credits_total),"debits_total":str(row.debits_total),"calculated_closing_balance":str(row.calculated_closing_balance),"difference":str(row.difference),"transaction_count":row.transaction_count,"pending_count":row.pending_count,"reconciled_at":row.reconciled_at.isoformat(),"notes":row.notes}

def reconciliation_history(db:Session,hid:str,account_id:str):
 account_for(db,hid,account_id);rows=db.scalars(select(AccountReconciliation).where(AccountReconciliation.household_id==hid,AccountReconciliation.account_id==account_id).order_by(AccountReconciliation.period_end.desc())).all()
 return [public_reconciliation(row) for row in rows]

def add_missing_transaction(db:Session,hid:str,body):
 account=account_for(db,hid,body.account_id);description=body.description.strip()
 row=Transaction(household_id=hid,account_id=account.id,provider_id=None,original_description=description,merchant=description[:120].title(),amount=money(body.amount),direction=body.direction,posted_date=body.posted_date,pending=False,category="Uncategorized",classification_source="manual",classification_confidence=Decimal("1"),is_transfer=False,notes="Added explicitly during account reconciliation.",data_source="reconciliation")
 db.add(row);db.flush();ensure_household_accounting(db,hid);db.commit();db.refresh(row);return public_transaction(row)

def merge_duplicate(db:Session,hid:str,keep_id:str,duplicate_id:str):
 if keep_id==duplicate_id:raise ReconciliationError("Choose two different transactions.")
 rows=list(db.scalars(select(Transaction).where(Transaction.household_id==hid,Transaction.id.in_([keep_id,duplicate_id]))))
 if len(rows)!=2:raise ReconciliationError("One or both transactions are unavailable.")
 by_id={row.id:row for row in rows};keep=by_id[keep_id];duplicate=by_id[duplicate_id]
 if (keep.account_id,keep.posted_date,keep.amount,keep.direction)!=(duplicate.account_id,duplicate.posted_date,duplicate.amount,duplicate.direction):raise ReconciliationError("Only transactions from the same account, date, amount, and direction can be merged.")
 keep_match=db.scalar(select(PaymentMatch).where(PaymentMatch.transaction_id==keep.id));duplicate_match=db.scalar(select(PaymentMatch).where(PaymentMatch.transaction_id==duplicate.id))
 if keep_match and duplicate_match:raise ReconciliationError("Both transactions are linked to scheduled payments and require manual review.")
 snapshot=json.dumps({"id":duplicate.id,"description":duplicate.original_description,"merchant":duplicate.merchant,"amount":str(duplicate.amount),"direction":duplicate.direction,"date":duplicate.posted_date.isoformat(),"pending":duplicate.pending,"category":duplicate.category,"data_source":duplicate.data_source,"had_provider_id":bool(duplicate.provider_id),"provider_id":duplicate.provider_id},sort_keys=True)
 if duplicate_match:duplicate_match.transaction_id=keep.id
 prior_merges=list(db.scalars(select(TransactionMerge).where(TransactionMerge.survivor_transaction_id==duplicate.id)))
 for prior_merge in prior_merges:prior_merge.survivor_transaction_id=keep.id
 provider_id=keep.provider_id if keep.data_source=="simplefin" else duplicate.provider_id if duplicate.data_source=="simplefin" else keep.provider_id
 duplicate.provider_id=None
 if not keep.fingerprint and duplicate.fingerprint:keep.fingerprint=duplicate.fingerprint;duplicate.fingerprint=None
 db.flush();keep.provider_id=provider_id;keep.pending=keep.pending and duplicate.pending;keep.is_transfer=keep.is_transfer or duplicate.is_transfer
 if keep.category=="Uncategorized" and duplicate.category!="Uncategorized":keep.category=duplicate.category;keep.classification_source=duplicate.classification_source;keep.classification_confidence=duplicate.classification_confidence
 if not keep.notes and duplicate.notes:keep.notes=duplicate.notes
 db.add(TransactionMerge(household_id=hid,account_id=keep.account_id,survivor_transaction_id=keep.id,removed_transaction_id=duplicate.id,removed_snapshot=snapshot,data_source="reconciliation"));db.delete(duplicate);db.flush();rebuild_opening_balances(db,hid,[keep.account_id]);db.commit();return {"kept_transaction_id":keep.id,"removed_transaction_id":duplicate_id}
