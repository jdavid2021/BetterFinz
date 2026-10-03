import csv
import hashlib
import io
import json
import re
import urllib.request
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.accounting_service import rebuild_opening_balances
from app.models import CategorizationRule, FinancialAccount, LiabilityStatement, Transaction
from app.categorization_service import learned_classification, normalize_description

CATEGORIES={"Income","Mortgage Payment","Loan Payment","Credit Card Payment","Bill","Utilities","Electricity & Gas","Water & Sewer","Waste & Recycling","Phone & Internet","Software & Subscriptions","Transfer","Groceries","Transportation","Healthcare","Dining","Shopping","Uncategorized"}
RULES=[("Income",("payroll","direct dep","salary","deposit ach","social security")),("Mortgage Payment",("mortgage","home loan")),("Loan Payment",("auto loan","student loan","affirm","klarna","afterpay","loan payment")),("Credit Card Payment",("card payment","credit card payment","payment thank you")),("Water & Sewer",("water bill","water utility","city water","county water","water autopay","sewer")),("Waste & Recycling",("waste management","waste connections","trash service","sanitation","garbage","recycling service")),("Phone & Internet",("internet","broadband","fiber","phone bill","spectrum","frontier commu","comcast","xfinity","verizon wireless","at&t mobility")),("Electricity & Gas",("electric","duke energy","power bill","natural gas utility","energy autopay")),("Software & Subscriptions",("netflix","spotify","adobe","microsoft 365","office 365","dropbox","hulu","disney plus","youtube premium","github","openai","quickbooks","intuit subscription")),("Utilities",("utility","utilities")),("Bill",("insurance","irs","tax payment")),("Transfer",("transfer","zelle","venmo","cash app")),("Groceries",("grocery","supermarket")),("Transportation",("fuel","gas station","uber","lyft")),("Healthcare",("pharmacy","medical","dental")),("Dining",("restaurant","cafe","doordash"))]

def money(value):
    text=str(value or "0").replace("$","").replace(",","").strip(); negative=text.startswith("(") and text.endswith(")")
    try: amount=Decimal(text.strip("()") or "0").quantize(Decimal("0.01"))
    except InvalidOperation: amount=Decimal("0")
    return -amount if negative else amount

def parsed_date(value):
    raw=str(value).strip()
    text=raw[:8] if re.match(r"^\d{8}(?:\d{6}(?:\.\d+)?)?(?:\[[^]]+\])?$",raw) else raw[:10]
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%y","%Y%m%d"):
        try: return datetime.strptime(text,fmt).date()
        except ValueError: pass
    raise ValueError(f"Unsupported transaction date: {value}")

def statement_balance_date(ext, content, pdf_text, rows):
    candidates=[]
    if ext == "pdf":
        patterns=(
            r"\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})",
            r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}\s*-\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
            r"for\s+the\s+period\s+\d{1,2}/\d{1,2}/\d{2,4}\s+to\s+(\d{1,2}/\d{1,2}/\d{2,4})",
            r"statement\s+date\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
            r"statement\s+closing\s+date\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
            r"closing\s+date\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
            r"billing\s+cycle\s+from\s+\d{1,2}/\d{1,2}/\d{2,4}\s+to\s+(\d{1,2}/\d{1,2}/\d{2,4})",
            r"new\s+balance\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{2,4})",
        )
        for pattern in patterns:
            match=re.search(pattern,pdf_text,re.I)
            if match:
                value=match.group(1).replace(",","")
                for fmt in ("%m/%d/%Y","%m/%d/%y","%B %d %Y","%b %d %Y"):
                    try: return datetime.strptime(value,fmt).date()
                    except ValueError: pass
    elif ext in {"ofx","qfx","qbo","qbx"}:
        text=content.decode("utf-8",errors="ignore")
        for value in re.findall(r"<(?:DTEND|DTASOF)>(\d{8})",text,re.I):
            candidates.append(datetime.strptime(value,"%Y%m%d").date())
    if candidates: return max(candidates)
    return max((row["date"] for row in rows),default=None)

def decode_tabular(content):
    last_error=None
    for encoding in ("utf-8-sig","utf-16","cp1252"):
        try:
            text=content.decode(encoding).lstrip("\r\n \t")
            table_lines=[line for line in text.splitlines() if max((line.count(delimiter) for delimiter in ",;\t|"),default=0)>=2]
            sample="\n".join(table_lines[:100]) or text[:8192]
            dialect=csv.Sniffer().sniff(sample,delimiters=",;\t|")
            return text,dialect
        except (UnicodeDecodeError,csv.Error) as exc:last_error=exc
    raise ValueError("The CSV encoding or delimiter could not be recognized. Export it as UTF-8 CSV, QBO, QFX, or OFX.") from last_error

def pdf_payload(content):
    offset=content[:1024].find(b"%PDF-")
    return content[offset:] if offset>=0 else content

def detected_file_format(filename,content):
    declared=filename.lower().rsplit(".",1)[-1] if "." in filename else ""
    head=content[:8192].lstrip();upper=head.upper();pdf_offset=content[:1024].find(b"%PDF-")
    if pdf_offset>=0:actual="pdf"
    elif b"<OFX" in upper or b"<STMTTRN" in upper:actual="qbo" if declared in {"qbo","qbx"} else "ofx"
    else:
        try:decode_tabular(content);actual="csv"
        except ValueError:
            if declared=="qbx":raise ValueError("This is a QuickBooks binary/company file, not a bank transaction export. Export QBO, QFX, OFX, or CSV from the bank instead.")
            raise ValueError("The uploaded file is corrupted or its contents do not match a supported PDF, CSV, QBO, QFX, OFX, or compatible QBX file.")
    return actual,declared

def ocr_pdf(content):
    try:
        import pypdfium2 as pdfium
        import pytesseract
        document=pdfium.PdfDocument(content)
        if len(document)>60:raise ValueError("The scanned PDF has more than 60 pages. Upload a monthly statement or transaction export instead.")
        pages=[]
        for page in document:
            image=page.render(scale=2).to_pil()
            pages.append(pytesseract.image_to_string(image,config="--psm 6"))
            image.close()
        return "\n".join(pages)
    except ValueError:raise
    except Exception as exc:raise ValueError("This appears to be a scanned PDF, but local OCR could not read it. Try a higher-quality scan or export QBO, QFX, OFX, or CSV.") from exc

def validate_statement_rows(rows):
    if not rows:return
    dates=[row["date"] for row in rows]
    if (max(dates)-min(dates)).days>400:raise ValueError("Parsed transaction dates span more than 400 days, so the import was stopped for review. Upload a monthly or annual statement export.")
    if any(not str(row.get("description","")).strip() for row in rows):raise ValueError("One or more parsed transactions has no description, so nothing was imported.")

def parse_csv(content):
    rows=[]
    text,dialect=decode_tabular(content)
    for raw in csv.DictReader(io.StringIO(text),dialect=dialect):
        item={re.sub(r"[^a-z0-9]+","_",str(k).strip().lower()).strip("_"):v for k,v in raw.items() if k is not None}
        when=item.get("date") or item.get("run_date") or item.get("posted_date") or item.get("transaction_date")
        description=item.get("action") or item.get("description") or item.get("merchant") or item.get("name") or "Unknown"
        amount=item.get("amount")
        if amount in (None,""): amount=money(item.get("debit"))-money(item.get("credit"))
        if when in (None,"") and (amount in (None,"") or money(amount)==0):continue
        try: transaction_date=parsed_date(when)
        except ValueError:
            if money(amount)==0:continue
            raise
        external_id=item.get("transaction_id") or item.get("transactionid") or item.get("fitid") or item.get("id") or ""
        rows.append({"date":transaction_date,"description":str(description).strip(),"amount":money(amount),"external_id":str(external_id).strip()})
    return rows

def parse_ofx(content):
    text=content.decode("utf-8",errors="ignore"); rows=[]
    for block in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>))",text,re.I|re.S):
        def field(name):
            found=re.search(fr"<{name}>([^<\r\n]+)",block,re.I)
            return found.group(1).strip() if found else ""
        rows.append({"date":parsed_date(field("DTPOSTED")),"description":field("NAME") or field("MEMO") or "Unknown","amount":money(field("TRNAMT")),"external_id":field("FITID")})
    return rows

def is_multi_column_detail(description):
    """Brokerage and bill-payment detail rows carry quantity, price, amount, and balance
    columns, so the trailing number is not the transaction amount."""
    return bool(re.search(r"\x24\s?\d",description or ""))

def parse_pdf_full_date_table_rows(layout_text):
    rows=[]
    pattern=re.compile(r"\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+(\S+)\s+(.+?)\s+(-?\s*\x24?\s*[0-9,]+\.\d{2})\s*")
    for line in layout_text.splitlines():
        match=pattern.fullmatch(" ".join(line.split()))
        if not match:continue
        description=" ".join(match.group(3).split());reference=match.group(2)
        if not (len(reference)>=6 and re.search(r"\d",reference)):description=f"{reference} {description}"
        raw_amount=re.sub(r"\s+","",match.group(4))
        if not description or is_multi_column_detail(description) or re.search(r"minimum payment|amount enclosed|account ending|current amount due|total amount due|balance forward|balance subject to interest rate",description,re.I):continue
        amount=money(raw_amount)
        if re.search(r"\b(payment|credit|refund)\b",description,re.I):amount=-abs(amount)
        if amount==0:continue
        rows.append({"date":parsed_date(match.group(1)),"description":description,"amount":amount})
    return rows

def parse_pdf_activity_blocks(layout_text):
    """Parse portal PDFs where a date heading owns the activity lines below it."""
    rows=[];active_date=None;in_activity=False
    for raw_line in layout_text.splitlines():
        line=raw_line.strip();compact=re.sub(r"\s+","",line)
        if re.search(r"account\s+activity",line,re.I) or compact.lower()=="accountactivity":in_activity=True;continue
        if in_activity and re.fullmatch(r"(?:CONTACT|PAYMENTADDRESSES)",compact,re.I):break
        date_match=re.fullmatch(r"([A-Za-z]{3,9})(\d{1,2}),(\d{4})",compact)
        if in_activity and date_match:
            try:active_date=datetime.strptime(" ".join(date_match.groups()),"%b %d %Y").date()
            except ValueError:
                try:active_date=datetime.strptime(" ".join(date_match.groups()),"%B %d %Y").date()
                except ValueError:active_date=None
            continue
        if not in_activity or active_date is None or chr(36) not in line:continue
        description,raw_amount=line.rsplit(chr(36),1);amount_text=re.sub(r"\s+","",raw_amount)
        if not re.fullmatch(r"\(?[0-9,]+\.\d{2}\)?",amount_text):continue
        amount=money(amount_text)
        if amount==0:continue
        description=" ".join(description.split()).strip(" :-")
        if not description or is_multi_column_detail(description):continue
        direction=Decimal("-1") if re.search(r"\b(payment|credit|refund)\b",description,re.I) else Decimal("1")
        rows.append({"date":active_date,"description":description,"amount":direction*abs(amount)})
    return rows

def parse_pdf_short_date_table_rows(text,statement_year,statement_end_month=None):
    """Parse card tables whose dates omit the year: MM/DD [MM/DD] [reference] description [reference] amount."""
    rows=[]
    pattern=re.compile(r"\s*(\d{1,2})/(\d{1,2})\s+(?:\d{1,2}/\d{1,2}\s+)?(.+?)\s+(-?\s*\x24?\s*-?[0-9,]+\.\d{2})\s*")
    for line in text.splitlines():
        match=pattern.fullmatch(" ".join(line.split()))
        if not match:continue
        month,day=int(match.group(1)),int(match.group(2))
        words=" ".join(match.group(3).split()).split(" ")
        if len(words)>1 and re.fullmatch(r"[A-Za-z0-9]{6,}",words[0]) and re.search(r"\d",words[0]):words=words[1:]
        if len(words)>1 and re.fullmatch(r"\d{6,}",words[-1]):words=words[:-1]
        description=" ".join(words).strip(" :-&")
        if not re.search(r"[A-Za-z]",description):continue
        if is_multi_column_detail(description) or re.search(r"minimum payment|amount enclosed|account ending|current amount due|total amount due|balance forward|balance subject to interest rate",description,re.I):continue
        year=statement_year-1 if statement_end_month and month>statement_end_month else statement_year
        try:when=date(year,month,day)
        except ValueError:continue
        amount=money(re.sub(r"\s+","",match.group(4)))
        if amount==0:continue
        if re.search(r"\b(payment|credit|refund)\b",description,re.I):amount=-abs(amount)
        rows.append({"date":when,"description":description,"amount":amount})
    return rows

def pdfium_text(content):
    """Recover the text layer with pdfium for pages whose fonts pypdf cannot decode."""
    try:
        import pypdfium2 as pdfium
        document=pdfium.PdfDocument(content)
        if len(document)>60:return ""
        return "\n".join(page.get_textpage().get_text_bounded() for page in document)
    except Exception:return ""

def parse_pdf_named_table_rows(layout_text,statement_year,statement_end_month=None):
    rows=[]
    pattern=re.compile(r"\s*([A-Za-z]{3,9})\s+(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{1,2})\s+(.+?)\s+(-?\s*\x24?\s*[0-9,]+\.\d{2})\s*")
    for line in layout_text.splitlines():
        match=pattern.fullmatch(" ".join(line.split()))
        if not match:continue
        month_name,day=match.group(3),int(match.group(4));description=" ".join(match.group(5).split());raw_amount=re.sub(r"\s+","",match.group(6))
        try:month=datetime.strptime(month_name[:3],"%b").month
        except ValueError:continue
        year=statement_year-1 if statement_end_month and month>statement_end_month else statement_year
        amount=money(raw_amount)
        if amount==0 or not description or is_multi_column_detail(description):continue
        rows.append({"date":date(year,month,day),"description":description,"amount":amount})
    return rows

def parse_pdf(content):
    from pypdf import PdfReader
    content=pdf_payload(content)
    diagnostics=[]
    try:
        reader=PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:unlocked=reader.decrypt("")
            except Exception:unlocked=0
            if not unlocked:raise ValueError("This PDF is password-protected. Download an unlocked statement copy from the bank and upload it again.")
        default_text="\n".join(page.extract_text() or "" for page in reader.pages)
        layout_text="\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    except ValueError:raise
    except Exception as exc:raise ValueError("The PDF is incomplete or corrupted and could not be opened. Download it again from the bank.") from exc
    if len(default_text.strip())<80:
        default_text=ocr_pdf(content);layout_text="";diagnostics.append("Scanned PDF detected; local OCR was used.")
    text=default_text+"\n"+layout_text
    if "Best Egg Loan Account Statement" in text:
        value=r"(\x24[0-9,]+\.\d{2})";dated=r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"
        summary=re.search(dated+r"\s+"+value+r"\s+"+dated+r"\s+"+value+r"\s+"+value+r"\s+"+dated+r"\s+"+value+r"\s+"+value+r"\s+"+value+r"\s+"+value+r"\s+"+value+r"\s+"+value+r"\s+"+value,text)
        if summary:
            fields=("Statement Date","Total Amount Due","Payment Due By","Scheduled Payment","Past Due Payments","Last Payment Received","Last Payment Amount","Principal Applied","Late Fees","Interest Applied","Other","Current Balance","Total Interest Paid")
            text+="\n"+"\n".join(f"{label}: {summary.group(index)}" for index,label in enumerate(fields,1))
    period=re.search(r"For the period\s+\d{1,2}/\d{1,2}/(\d{4})\s+to\s+\d{1,2}/\d{1,2}/(\d{4})",text,re.I)
    year=int(period.group(2)) if period else datetime.now().year
    named_period=re.search(r"-\s*([A-Za-z]{3,9})\s+\d{1,2},\s*(\d{4})",text)
    statement_end_month=None
    if named_period:
        year=int(named_period.group(2))
        try:statement_end_month=datetime.strptime(named_period.group(1)[:3],"%b").month
        except ValueError:pass
    if statement_end_month is None:
        cycle=re.search(r"billing\s+cycle\s+from\s+\d{1,2}/\d{1,2}/\d{4}\s+to\s+(\d{1,2})/\d{1,2}/(\d{4})",text,re.I)
        if cycle:statement_end_month=int(cycle.group(1));year=int(cycle.group(2))
    rows=[];direction=Decimal("1")
    for line in default_text.splitlines():
        heading=line.strip().lower()
        if heading.startswith("deposits and other additions"):direction=Decimal("1");continue
        if "withdrawals and purchases" in heading or "banking deductions" in heading:direction=Decimal("-1");continue
        match=re.match(r"^\s*(\d{1,2}/\d{1,2})(?:/(\d{2,4}))?\s+(\(?\$?(?:[0-9,]+)?\.\d{2}\)?)\s+(.+?)\s*$",line)
        if not match:continue
        date_year=int(match.group(2)) if match.group(2) else year
        if date_year<100:date_year+=2000
        when=datetime.strptime(f"{match.group(1)}/{date_year}","%m/%d/%Y").date()
        amount=money(match.group(3));description=match.group(4).strip()
        if chr(36) in description or re.search(r"minimum payment|amount enclosed|account ending",description,re.I):continue
        rows.append({"date":when,"description":description,"amount":direction*abs(amount)})
    if not rows:rows=parse_pdf_full_date_table_rows(default_text)
    if not rows:rows=parse_pdf_activity_blocks(layout_text)
    if not rows:rows=parse_pdf_named_table_rows(layout_text,year,statement_end_month)
    if not rows:rows=parse_pdf_short_date_table_rows(layout_text,year,statement_end_month)
    if not rows:rows=parse_pdf_short_date_table_rows(default_text,year,statement_end_month)
    if not rows:
        alternate=pdfium_text(content)
        if alternate:
            rows=(parse_pdf_full_date_table_rows(alternate) or parse_pdf_activity_blocks(alternate)
                or parse_pdf_named_table_rows(alternate,year,statement_end_month)
                or parse_pdf_short_date_table_rows(alternate,year,statement_end_month))
            if rows:
                text+="\n"+alternate
                diagnostics.append("The embedded PDF text layer could not be decoded directly; an alternate extraction engine recovered it.")
    return rows,text,diagnostics

def detected_closing_balance(ext,content,pdf_text=""):
    if ext=="csv":
        text,dialect=decode_tabular(content)
        parsed=list(csv.DictReader(io.StringIO(text),dialect=dialect))
        if parsed:
            row={str(k).strip().lower().replace(" ","_"):v for k,v in parsed[-1].items()}
            for key in ("ending_balance","closing_balance","running_balance","balance"):
                if row.get(key) not in (None,""):return money(row[key])
    elif ext in {"ofx","qfx","qbo","qbx"}:
        text=content.decode("utf-8",errors="ignore")
        match=re.search(r"<LEDGERBAL>.*?<BALAMT>([^<\r\n]+)",text,re.I|re.S)
        if match:return money(match.group(1))
    elif ext=="pdf":
        loan_payment=re.search(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}/\d{1,2}/\d{2,4}\s*Payments?\b.*?([0-9,]+\.\d{2})\s*$",pdf_text,re.I|re.M)
        if loan_payment:return money(loan_payment.group(1))
        for label in (r"ending\s+account\s+value",r"account\s+value",r"total\s+holdings",r"ending\s+balance",r"closing\s+balance",r"new\s+balance",r"statement\s+balance",r"current\s+principal\s+balance\d*",r"outstanding\s+principal\s+balance",r"current\s+balance\*?"):
            match=re.search(label+r"\s*[:=+\-]?\s*\x24?\s*([0-9,]+\.\d{2})",pdf_text,re.I)
            if match:return money(match.group(1))
        period=re.search(r"For the period\s+\d{1,2}/\d{1,2}/\d{4}\s+to\s+(\d{1,2}/\d{1,2})/(\d{4})",pdf_text,re.I)
        if period:
            matches=re.findall(rf"(?:^|\s){re.escape(period.group(1))}\s+((?:[0-9,]+)?\.\d{{2}})(?=\s|$)",pdf_text,re.M)
            if matches:return money(matches[-1])
    return None

def detected_available_balance(ext,content,pdf_text=""):
    if ext=="csv":
        text,dialect=decode_tabular(content);parsed=list(csv.DictReader(io.StringIO(text),dialect=dialect))
        if parsed:
            row={str(k).strip().lower().replace(" ","_"):v for k,v in parsed[-1].items()}
            for key in ("available_balance","available_credit","credit_available"):
                if row.get(key) not in (None,""):return money(row[key])
    elif ext in {"ofx","qfx","qbo","qbx"}:
        text=content.decode("utf-8",errors="ignore")
        for pattern in (r"<AVAILBAL>.*?<BALAMT>([^<\r\n]+)",r"<AVAILCASH>([^<\r\n]+)",r"<AVAILCREDIT>([^<\r\n]+)"):
            match=re.search(pattern,text,re.I|re.S)
            if match:return money(match.group(1))
    elif ext=="pdf":
        for label in (r"available\s+balance",r"available\s+credit",r"credit\s+available"):
            match=re.search(label+r"\s*[:=+\-]?\s*\x24?\s*([0-9,]+\.\d{2})",pdf_text,re.I)
            if match:return money(match.group(1))
    return None

def imported_available_balance(account_kind,ext,explicit_available,closing_balance):
    if explicit_available is not None:return explicit_available
    if ext in {"ofx","qfx","qbo","qbx"} and account_kind in {"checking","savings","money_market"}:return closing_balance
    return None

def detected_cash_management_balance(text,closing_balance):
    for line in text.splitlines():
        if re.search(r"total\s+core\s+account",line,re.I):
            values=re.findall(r"\x24?\s*([0-9,]+\.\d{2})",line)
            if values:return money(values[-1])
    if closing_balance is not None and re.search(r"100%\s+core\s+account",text,re.I):return closing_balance
    return None

def liability_statement_values(account,ext,text,statement_date,closing_balance):
    if account.kind not in {"credit_card","mortgage","auto_loan","buy_now_pay_later","loan","other"} or ext!="pdf" or not statement_date or closing_balance is None:return None
    def amount(labels,default=None):
        for label in labels:
            match=re.search(label+r"\s*[:=+\-]?\s*\x24?\s*([0-9,]+\.\d{2})",text,re.I)
            if match:return money(match.group(1))
        return default
    def dated(labels):
        for label in labels:
            match=re.search(label+r"\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",text,re.I)
            if match:
                value=match.group(1).replace(",","")
                for fmt in ("%B %d %Y","%b %d %Y","%m/%d/%Y","%m/%d/%y"):
                    try:return datetime.strptime(value,fmt).date()
                    except ValueError:pass
        return None
    due=dated((r"payment\s+due\s+date",r"payment\s+due\s+by",r"payment\s+date\*?",r"due\s+date",r"date\s+due"));minimum=amount((r"minimum\s+payment\s+due",r"minimum\s+payment",r"current\s+payment",r"total\s+payment\s+amount(?:\*\*)?",r"amount\s+due",r"current\s+amount\s+due",r"total\s+amount\s+due"))
    if due is None or minimum is None:return None
    apr=None
    match=re.search(r"(?:purchase\s+apr|annual\s+percentage\s+rate|interest\s+rate)(?:\*\*)?\s*[:\-]?\s*([0-9]+(?:\.\d+)?)\s*%",text,re.I)
    if match:apr=Decimal(match.group(1))
    if apr is None:
        match=re.search(r"(?:^|\n)\s*(?:Purchases?(?:\s*&\s*Balance\s+Transfers)?(?:\s+N/A)?|R\s*evolving|\d+-Month\s+Promo\s+Purchase\s+\d{1,2}/\d{1,2}/\d{2,4})\s+([0-9]+(?:\.\d+)?)\s*%",text,re.I)
        if match:apr=Decimal(match.group(1))
    if apr is None:
        for purchase_row in re.findall(r"^\s*purchases?\b([^\n]+)",text,re.I|re.M):
            percentages=re.findall(r"([0-9]+(?:\.\d+)?)\s*%",purchase_row)
            if len(percentages)>=2:
                apr=Decimal(percentages[-1]);break
    payment=amount((r"payment\s+received\s*-\s*thank\s+you",r"payments\s+received",r"last\s+payment\s+amount",r"payments(?:\s+and\s+other\s+credits)?"),Decimal("0"))
    loan_payment_details=re.search(r"Payments?\s+By\s+Mail\s*#?\s*([0-9,]+\.\d{2})\s+-?([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})",text,re.I)
    if loan_payment_details:payment=money(loan_payment_details.group(3))
    return {"account_id":account.id,"opening_balance":abs(amount((r"previous\s+balance\s+as\s+of\s+\d{1,2}/\d{1,2}/\d{2,4}",r"previous\s+balance",r"opening\s+balance",r"balance\s+subject\s+to\s+interest\s+rate"),closing_balance)),"new_balance":abs(closing_balance),"new_payments":abs(payment),"statement_date":statement_date,"due_date":due,"minimum_payment":abs(minimum),"interest_rate":apr,"interest_paid":abs(amount((r"interest\s+charged\s+since\s+last\s+payment\d*",r"interest\s+applied",r"interest\s+charge\s+this\s+period",r"interest\s+charged",r"interest\s+paid",r"finance\s+charge"),Decimal("0")))}

def redact_transaction_text(text):
    lines=[]
    period_pattern=re.compile(r"(?:statement period|for the period|from)\s+.*?\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",re.I)
    transaction_pattern=re.compile(r"(?:^|\s)\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?(?:\s|$)")
    amount_pattern=re.compile(r"(?:\$?\d[\d,]*\.\d{2}|\$?\.\d{2})")
    source=text.splitlines()
    for index,line in enumerate(source):
        if period_pattern.search(line) or (transaction_pattern.search(line) and amount_pattern.search(line)):
            lines.extend(source[max(0,index-1):min(len(source),index+3)])
    cleaned=[]
    for line in lines:
        line=re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}","[REDACTED_EMAIL]",line,flags=re.I)
        line=re.sub(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}","[REDACTED_PHONE]",line)
        line=re.sub(r"(?i)(account|acct|member|customer|routing)(\s*(?:number|no\.?|#|:)?\s*)[A-Z0-9X*-]{4,}",r"\1\2[REDACTED]",line)
        line=re.sub(r"\b[A-Z0-9]{8,}\b","[REDACTED_ID]",line)
        normalized=" ".join(line.split())
        if normalized and normalized not in cleaned:cleaned.append(normalized)
    return "\n".join(cleaned)[:24000]

def parse_pdf_ai(text):
    if not settings.openai_api_key:return [],None
    candidate_text=redact_transaction_text(text)
    if not candidate_text:return [],None
    row_schema={"type":"object","properties":{"date":{"type":"string"},"description":{"type":"string"},"amount":{"type":"number"}},"required":["date","description","amount"],"additionalProperties":False}
    schema={"type":"object","properties":{"transactions":{"type":"array","items":row_schema},"closing_balance":{"type":["number","null"]}},"required":["transactions","closing_balance"],"additionalProperties":False}
    instructions=("Extract bank-statement transactions from the redacted text. Return dates as YYYY-MM-DD. "
        "Use the statement period to infer omitted years. Deposits are positive; withdrawals, purchases, fees, and payments are negative. "
        "Do not invent transactions or balances. Ignore summaries, daily-balance tables, notices, page headers, and totals. "
        "Return closing_balance only when explicitly shown as the ending, closing, new, or statement balance.")
    body={"model":settings.openai_transaction_model,"input":instructions+"\n\nREDACTED STATEMENT LINES:\n"+candidate_text,"reasoning":{"effort":"low"},"text":{"format":{"type":"json_schema","name":"statement_transactions","strict":True,"schema":schema}}}
    request=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {settings.openai_api_key}","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(request,timeout=45) as response:payload=json.load(response)
        output_text=next(part["text"] for output in payload["output"] for part in output.get("content",[]) if part.get("type")=="output_text")
        result=json.loads(output_text);rows=[]
        for item in result["transactions"]:
            description=str(item["description"]).strip()
            if description:rows.append({"date":parsed_date(item["date"]),"description":description,"amount":money(item["amount"])})
        closing=result.get("closing_balance")
        return rows,money(closing) if closing is not None else None
    except Exception:return [],None

def classify_rule(description):
    lowered=description.lower()
    for category,needles in RULES:
        if any(needle in lowered for needle in needles): return category,Decimal("0.95"),"rules"
    return "Uncategorized",Decimal("0"),"unclassified"

def classify_ai(descriptions):
    if not settings.openai_api_key or not descriptions: return {}
    schema={"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"index":{"type":"integer"},"category":{"type":"string","enum":sorted(CATEGORIES)},"confidence":{"type":"number","minimum":0,"maximum":1}},"required":["index","category","confidence"],"additionalProperties":False}}},"required":["items"],"additionalProperties":False}
    body={"model":settings.openai_transaction_model,"input":"Classify each bank transaction description. Use Uncategorized whenever evidence is insufficient.\n"+"\n".join(f"{i}: {d}" for i,d in enumerate(descriptions)),"reasoning":{"effort":"low"},"text":{"format":{"type":"json_schema","name":"transaction_categories","strict":True,"schema":schema}}}
    request=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {settings.openai_api_key}","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(request,timeout=30) as response: payload=json.load(response)
        text=next(part["text"] for output in payload["output"] for part in output.get("content",[]) if part.get("type")=="output_text")
        result={}
        for item in json.loads(text)["items"]:
            category=item["category"] if item["category"] in CATEGORIES and item["confidence"]>=0.72 else "Uncategorized"
            result[item["index"]]=(category,Decimal(str(item["confidence"])),"ai" if category!="Uncategorized" else "unclassified")
        return result
    except Exception: return {}

def dedupe_description(description):
    normalized=normalize_description(description)
    if normalized:return normalized
    return " ".join(re.sub(r"[^a-z0-9]+"," ",description.lower()).split())[:180]

def descriptions_similar(left,right):
    left_key=dedupe_description(left);right_key=dedupe_description(right)
    if left_key==right_key:return True
    if min(len(left_key),len(right_key))>=6 and (left_key in right_key or right_key in left_key):return True
    left_words=set(left_key.split());right_words=set(right_key.split())
    return bool(left_words and right_words) and len(left_words&right_words)/len(left_words|right_words)>=0.75

def qualified_provider_id(household_id,account_id,external_id):
    if not external_id:return None
    return hashlib.sha256(f"{household_id}|{account_id}|{external_id}".encode()).hexdigest()

def import_statement(db:Session,household_id:str,account:FinancialAccount,filename:str,content:bytes,ending_balance:Decimal|None,import_transactions:bool=True):
    ext,declared_ext=detected_file_format(filename,content)
    diagnostics=[]
    format_family={"ofx","qfx","qbo","qbx"}
    if declared_ext and declared_ext!=ext and not {declared_ext,ext}.issubset(format_family):diagnostics.append(f"File contents detected as {ext.upper()} despite the .{declared_ext} filename.")
    pdf_text=""
    if ext=="csv":rows=parse_csv(content)
    elif ext in {"ofx","qfx","qbo","qbx"}:
        if ext=="qbx" and b"<STMTTRN" not in content.upper(): raise ValueError("This QBX file is not an OFX-style bank transaction export. Export the account as QBO, QFX, OFX, or CSV instead.")
        rows=parse_ofx(content)
    elif ext=="pdf":
        rows,pdf_text,pdf_diagnostics=parse_pdf(content);diagnostics.extend(pdf_diagnostics)
    else:raise ValueError("Upload a PDF, CSV, OFX, QFX, QBO, or OFX-style QBX statement.")
    detected_balance=detected_closing_balance(ext,content,pdf_text)
    detected_available=detected_available_balance(ext,content,pdf_text)
    if account.kind=="cash_management" and ext=="pdf":detected_available=detected_cash_management_balance(pdf_text,detected_balance)
    if not rows and ext=="pdf" and not re.search(r"insufficient funds notice",pdf_text,re.I):
        rows,ai_balance=parse_pdf_ai(pdf_text)
        if rows:diagnostics.append("Deterministic PDF parsing found no rows; the sanitized AI fallback recovered transactions.")
        if detected_balance is None:detected_balance=ai_balance
    if not rows:
        if ext=="pdf" and re.search(r"insufficient funds notice",pdf_text,re.I):raise ValueError("This PDF is an Insufficient Funds Notice, not an account statement. Download the monthly account statement or transaction export from your bank and upload that file instead.")
        balance_date=statement_balance_date(ext,content,pdf_text,rows)
        liability_values=liability_statement_values(account,ext,pdf_text,balance_date,detected_balance)
        if liability_values:
            applied_balance=ending_balance if ending_balance is not None else detected_balance
            balance_updated=applied_balance is not None and (account.balance_as_of_date is None or (balance_date is not None and balance_date >= account.balance_as_of_date) or (account.balance==0 and account.data_source=="manual"))
            if balance_updated:
                account.balance=applied_balance;account.balance_as_of_date=balance_date
            liability_statement_captured=False
            if not db.scalar(select(LiabilityStatement.id).where(LiabilityStatement.household_id==household_id,LiabilityStatement.account_id==account.id,LiabilityStatement.statement_date==liability_values["statement_date"])):
                db.add(LiabilityStatement(household_id=household_id,**liability_values,data_source="statement"));liability_statement_captured=True
            db.commit()
            reason="updated" if balance_updated else "older_statement" if applied_balance is not None and account.balance_as_of_date and balance_date and balance_date < account.balance_as_of_date else "no_closing_balance"
            return {"detected_format":ext,"diagnostics":diagnostics+["No transaction table was present; the liability statement summary was imported."],"liability_statement_captured":liability_statement_captured,"added":0,"duplicates":0,"missing_transactions":0,"review_only":not import_transactions,"uncategorized":0,"balance":str(account.balance),"balance_updated":balance_updated,"balance_as_of_date":account.balance_as_of_date.isoformat() if account.balance_as_of_date else None,"available_balance":str(account.available_balance),"available_balance_updated":False,"statement_end_date":balance_date.isoformat() if balance_date else None,"balance_update_reason":reason,"balance_source":"manual" if balance_updated and ending_balance is not None else "statement" if balance_updated and detected_balance is not None else "unchanged"}
        raise ValueError("No transactions could be identified locally or with the AI fallback. Try CSV, OFX, or QFX, or upload a text-based monthly statement PDF.")
    validate_statement_rows(rows)
    applied_balance=ending_balance if ending_balance is not None else detected_balance
    import_available=imported_available_balance(account.kind,ext,detected_available,applied_balance)
    balance_date=statement_balance_date(ext,content,pdf_text,rows)
    rules=list(db.scalars(select(CategorizationRule).where(CategorizationRule.household_id==household_id,CategorizationRule.is_active)))
    classified=[learned_classification(row["description"],rules) or classify_rule(row["description"]) for row in rows]
    unresolved=[(i,row["description"]) for i,row in enumerate(rows) if classified[i][0]=="Uncategorized"]
    ai=classify_ai([description for _,description in unresolved])
    for ai_index,(row_index,_) in enumerate(unresolved): classified[row_index]=ai.get(ai_index,classified[row_index])
    added=duplicates=missing_transactions=uncategorized=0
    first_date=min(row["date"] for row in rows);last_date=max(row["date"] for row in rows)
    existing=list(db.scalars(select(Transaction).where(Transaction.household_id==household_id,Transaction.account_id==account.id,Transaction.posted_date>=first_date,Transaction.posted_date<=last_date)))
    unmatched_existing=list(existing)
    known_provider_ids=set(db.scalars(select(Transaction.provider_id).where(Transaction.household_id==household_id,Transaction.account_id==account.id,Transaction.provider_id.is_not(None))))
    new_occurrences: dict[tuple[date, Decimal, str, str], int] = {}
    for row,(category,confidence,source) in zip(rows,classified):
        provider_id=qualified_provider_id(household_id,account.id,row.get("external_id"))
        if provider_id and provider_id in known_provider_ids:
            duplicates+=1;continue
        match_index=next((index for index,candidate in enumerate(unmatched_existing) if candidate.posted_date==row["date"] and candidate.amount==abs(row["amount"]) and descriptions_similar(candidate.original_description,row["description"])),None)
        if match_index is not None:
            unmatched_existing.pop(match_index);duplicates+=1
            if provider_id:known_provider_ids.add(provider_id)
            continue
        normalized=dedupe_description(row["description"])
        direction="credit" if row["amount"]>=0 else "debit"
        occurrence_key=(row["date"],abs(row["amount"]),normalized,direction)
        prior_count=sum(1 for candidate in existing if candidate.posted_date==row["date"] and candidate.amount==abs(row["amount"]) and descriptions_similar(candidate.original_description,row["description"]))
        occurrence=prior_count+new_occurrences.get(occurrence_key,0)+1
        new_occurrences[occurrence_key]=new_occurrences.get(occurrence_key,0)+1
        fingerprint=hashlib.sha256(f"v2|{household_id}|{account.id}|{row['date']}|{abs(row['amount'])}|{normalized}|{direction}|{occurrence}".encode()).hexdigest()
        if not import_transactions:
            missing_transactions+=1;uncategorized+=category=="Uncategorized";continue
        db.add(Transaction(household_id=household_id,account_id=account.id,provider_id=provider_id,original_description=row["description"],merchant=row["description"][:120].title(),amount=abs(row["amount"]),direction=direction,posted_date=row["date"],category=category,classification_source=source,classification_confidence=confidence,fingerprint=fingerprint,data_source="statement"))
        if provider_id:known_provider_ids.add(provider_id)
        added+=1;uncategorized+=category=="Uncategorized"
    balance_updated=applied_balance is not None and (account.balance_as_of_date is None or (balance_date is not None and balance_date >= account.balance_as_of_date) or (account.balance==0 and account.data_source=="manual"))
    if balance_updated:
        account.balance=applied_balance
        account.balance_as_of_date=balance_date
        if import_available is not None:account.available_balance=import_available
        if account.kind=="cash_management":account.investment_balance=max(account.balance-account.available_balance,Decimal("0"))
    liability_statement_captured=False
    liability_values=liability_statement_values(account,ext,pdf_text,balance_date,detected_balance)
    if liability_values and not db.scalar(select(LiabilityStatement.id).where(LiabilityStatement.household_id==household_id,LiabilityStatement.account_id==account.id,LiabilityStatement.statement_date==liability_values["statement_date"])):
        db.add(LiabilityStatement(household_id=household_id,**liability_values,data_source="statement"));liability_statement_captured=True
    db.flush()
    rebuild_opening_balances(db, household_id, [account.id])
    db.commit()
    reason="updated" if balance_updated else "older_statement" if applied_balance is not None and account.balance_as_of_date and balance_date and balance_date < account.balance_as_of_date else "no_closing_balance"
    available_balance_updated=balance_updated and import_available is not None
    return {"detected_format":ext,"diagnostics":diagnostics,"liability_statement_captured":liability_statement_captured,"added":added,"duplicates":duplicates,"missing_transactions":missing_transactions,"review_only":not import_transactions,"uncategorized":uncategorized,"balance":str(account.balance),"balance_updated":balance_updated,"balance_as_of_date":account.balance_as_of_date.isoformat() if account.balance_as_of_date else None,"available_balance":str(account.available_balance),"available_balance_updated":available_balance_updated,"statement_end_date":balance_date.isoformat() if balance_date else None,"balance_update_reason":reason,"balance_source":"manual" if balance_updated and ending_balance is not None else "statement" if balance_updated and detected_balance is not None else "unchanged"}
