import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FinancialAccount
from app.institution_directory import match_institution, public_institution
from app.statement_service import (
    detected_available_balance,
    detected_closing_balance,
    detected_cash_management_balance,
    detected_file_format,
    liability_statement_values,
    parse_csv,
    parse_ofx,
    parse_pdf,
    statement_balance_date,
)

LIABILITY_KINDS={"credit_card","mortgage","auto_loan","buy_now_pay_later","loan","other"}


def first(patterns, text):
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if match:return " ".join(match.group(1).split()).strip(" :-")
    return None


def identify_kind(text, ext):
    lowered=text.lower()
    if ext in {"ofx","qfx","qbo","qbx"}:
        account_type=(first((r"<ACCTTYPE>([^<\r\n]+)",),text) or "").upper()
        return ({"CHECKING":"checking","SAVINGS":"savings","MONEYMRKT":"money_market","CREDITLINE":"credit_card","CD":"savings"}.get(account_type,"checking"),"high" if account_type else "medium")
    if "cash management account" in lowered or ("investment report" in lowered and "core account" in lowered):return "cash_management","high"
    if any(term in lowered for term in ("credit limit","minimum payment warning","annual percentage rate (apr)","cash advances")):return "credit_card","high"
    if any(term in lowered for term in ("mortgage statement","escrow balance","principal and interest")):return "mortgage","high"
    if any(term in lowered for term in ("auto finance","vehicle identification number","vin:")):return "auto_loan","high"
    if "installment" in lowered or "buy now pay later" in lowered:return "buy_now_pay_later","medium"
    if "loan account statement" in lowered or "principal balance" in lowered:return "loan","medium"
    return "checking","low"


def identify_institution(text):
    known=(("Fidelity",r"\bfidelity(?:®| investments)?\b"),("Mission Lane",r"mission\s+lane"),("Capital One",r"capital\s+one"),("PNC Bank",r"\bpnc\b"),("PayPal",r"\bpaypal\b"),("Best Buy",r"best\s+buy"),("TD Bank",r"td\s+(?:auto\s+finance|bank)"),("Suncoast Credit Union",r"suncoast"),("Best Egg",r"best\s+egg"),("Affirm",r"\baffirm\b"))
    for name,pattern in known:
        if re.search(pattern,text,re.I):return name,"high"
    org=first((r"<ORG>([^<\r\n]+)",r"<FI>.*?<ORG>([^<\r\n]+)"),text)
    return (org,"medium") if org else ("","low")


def identify_mask(text):
    account=first((r"account\s+(?:number|no\.?|#)\s*[:\-]?\s*(?:[#*X\s-]*)(\d{4})\b",r"<ACCTID>[^<\r\n]*?(\d{4})\s*(?:<|\r|\n)"),text)
    if not account:
        full=first((r"account\s+(?:number|no\.?|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9-]{3,})",),text)
        normalized=re.sub(r"[^A-Z0-9]","",full.upper()) if full else ""
        account=normalized[-4:] if len(normalized)>=4 else None
    return (account,"high") if account else ("", "low")


def preview_account_statement(db:Session,household_id:str,filename:str,content:bytes):
    ext,_=detected_file_format(filename,content);text="";diagnostics=[]
    if ext=="csv":rows=parse_csv(content)
    elif ext in {"ofx","qfx","qbo","qbx"}:rows=parse_ofx(content);text=content.decode("utf-8",errors="ignore")
    else:rows,text,diagnostics=parse_pdf(content)
    balance=detected_closing_balance(ext,content,text)
    available=detected_available_balance(ext,content,text)
    as_of=statement_balance_date(ext,content,text,rows)
    kind,kind_confidence=identify_kind(text,ext)
    institution,institution_confidence=identify_institution(text)
    directory_match,directory_confidence,directory_source=match_institution(text,institution)
    institution_suggestion=public_institution(directory_match,directory_confidence,directory_source) if directory_match else None
    if directory_match:
        institution=directory_match.name
        institution_confidence=directory_confidence
    mask,mask_confidence=identify_mask(text)
    if kind=="cash_management":available=detected_cash_management_balance(text,balance)
    if kind in {"checking","savings","money_market","cash_management"} and available is None:available=balance
    investment=max((balance or Decimal("0"))-(available or Decimal("0")),Decimal("0")) if kind=="cash_management" else Decimal("0")
    placeholder=type("PreviewAccount",(),{"id":"preview","kind":kind})()
    liability=liability_statement_values(placeholder,ext,text,as_of,balance) if kind in LIABILITY_KINDS else None
    suggested_name=(institution+" "+kind.replace("_"," ").title()).strip() or "New Account"
    duplicate=None
    if mask:
        match=db.scalar(select(FinancialAccount).where(FinancialAccount.household_id==household_id,FinancialAccount.mask==mask,FinancialAccount.kind==kind,FinancialAccount.is_active))
        if match:duplicate={"id":match.id,"name":match.name,"institution_name":match.institution_name}
    fields={
        "name":suggested_name,"institution_name":institution,"kind":kind,"mask":mask,
        "balance":str(abs(balance or Decimal("0"))),"available_balance":str(abs(available or Decimal("0"))),"investment_balance":str(investment),
        "original_balance":"","balance_as_of_date":as_of.isoformat() if as_of else None,
        "statement_date":liability["statement_date"].isoformat() if liability else (as_of.isoformat() if as_of else None),
        "due_date":liability["due_date"].isoformat() if liability else None,
        "minimum_payment":str(liability["minimum_payment"]) if liability else None,
        "interest_rate":str(liability["interest_rate"]) if liability and liability["interest_rate"] is not None else None,
        "interest_paid":str(liability["interest_paid"]) if liability else None,
        "payments_and_credits":str(liability["new_payments"]) if liability else None,
    }
    confidence={"name":institution_confidence,"institution_name":institution_confidence,"kind":kind_confidence,"mask":mask_confidence,"balance":"high" if balance is not None else "low","available_balance":"high" if available is not None else "low","balance_as_of_date":"high" if as_of else "low"}
    return {"detected_format":ext,"filename":filename,"transaction_count":len(rows),"fields":fields,"confidence":confidence,"duplicate_account":duplicate,"institution_suggestion":institution_suggestion,"diagnostics":diagnostics}
