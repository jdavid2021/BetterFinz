import json
from sqlalchemy.orm import Session
from app.models import AuditEvent
ALLOWED_ACTIONS={"user_signed_up","login_succeeded","password_reset","payment_matched","notification_preferences_updated","notification_dismissed","privacy_export_created","account_deletion_requested","account_deletion_confirmed","account_deletion_cancelled","accounts_merged"}
def record_audit(db:Session,household_id:str|None,user_id:str|None,action:str,**detail:object)->None:
 if action not in ALLOWED_ACTIONS:raise ValueError("Unsupported audit action")
 safe={k:v for k,v in detail.items() if k in {"label","source","date","method"} and v is not None}
 db.add(AuditEvent(household_id=household_id,user_id=user_id,action=action,detail=json.dumps(safe,sort_keys=True)))
def public_detail(event:AuditEvent)->dict:
 try:value=json.loads(event.detail or "{}")
 except (TypeError,json.JSONDecodeError):value={}
 return {k:str(v) for k,v in value.items() if k in {"label","source","date","method"}}
