import re
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import CategorizationRule

VAGUE={"payment","online payment","web payment","purchase","debit","credit","transaction","transfer","deposit","withdrawal","unknown"}

def normalize_description(description:str)->str:
    text=description.lower()
    text=re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b"," ",text)
    text=re.sub(r"\b[a-z0-9]*\d[a-z0-9-]{4,}\b"," ",text)
    text=re.sub(r"\b\d{3,}\b"," ",text)
    text=re.sub(r"\b(?:pos|ach|web|recur|pmt|pymt|payment|online|purchase|debit|credit|transaction|ckf|ref)\b"," ",text)
    text=re.sub(r"[^a-z]+"," ",text)
    return " ".join(text.split())

def learnable_pattern(description:str)->str|None:
    pattern=normalize_description(description)
    meaningful=[word for word in pattern.split() if len(word)>2]
    if len(pattern)<4 or not meaningful or pattern in VAGUE:return None
    return pattern[:180]

def learned_classification(description:str,rules:list[CategorizationRule]):
    pattern=normalize_description(description)
    for rule in rules:
        if rule.is_active and rule.pattern==pattern:
            rule.match_count+=1;rule.last_matched_at=datetime.now(timezone.utc)
            return rule.category,Decimal("1"),"learned_rule"
    return None

def learn_from_transaction(db:Session,household_id:str,description:str,category:str,category_id:str|None=None):
    pattern=learnable_pattern(description)
    if not pattern:return None
    rule=db.scalar(select(CategorizationRule).where(CategorizationRule.household_id==household_id,CategorizationRule.pattern==pattern))
    if rule:
        rule.category=category;rule.is_active=True;rule.sample_description=description[:255];rule.dml_flag="U";rule.category_id=category_id
    else:
        rule=CategorizationRule(household_id=household_id,pattern=pattern,sample_description=description[:255],category=category,category_id=category_id,is_active=True,data_source="manual_learning")
        db.add(rule)
    return rule
