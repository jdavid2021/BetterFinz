from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.audit_service import public_detail,record_audit
from app.auth import current_user,household_id
from app.db import get_db
from app.models import AuditEvent,Notification,User
from app.notification_service import data,generate_notifications,preference
from app.schemas import NotificationPreferencesUpdate
router=APIRouter(prefix="/api/v1",tags=["Activity"])
@router.get("/notifications")
def notifications(hid:str=Depends(household_id),user:User=Depends(current_user),db:Session=Depends(get_db)):
 generate_notifications(db,hid,user.id);rows=list(db.scalars(select(Notification).where(Notification.household_id==hid,Notification.user_id==user.id,Notification.dismissed_at.is_(None)).order_by(Notification.created_at.desc()).limit(100)))
 return {"unread":sum(row.read_at is None for row in rows),"items":[data(row) for row in rows]}
@router.patch("/notifications/{notification_id}/read")
def read_notification(notification_id:str,hid:str=Depends(household_id),user:User=Depends(current_user),db:Session=Depends(get_db)):
 row=db.scalar(select(Notification).where(Notification.id==notification_id,Notification.household_id==hid,Notification.user_id==user.id))
 if not row:raise HTTPException(404,"Notification not found.")
 row.read_at=datetime.now(timezone.utc);db.commit();return {"status":"read"}
@router.delete("/notifications/{notification_id}",status_code=204)
def dismiss_notification(notification_id:str,hid:str=Depends(household_id),user:User=Depends(current_user),db:Session=Depends(get_db)):
 row=db.scalar(select(Notification).where(Notification.id==notification_id,Notification.household_id==hid,Notification.user_id==user.id))
 if not row:raise HTTPException(404,"Notification not found.")
 row.dismissed_at=datetime.now(timezone.utc);record_audit(db,hid,user.id,"notification_dismissed",label=row.kind);db.commit();return Response(status_code=204)
@router.get("/notification-preferences")
def get_preferences(hid:str=Depends(household_id),user:User=Depends(current_user),db:Session=Depends(get_db)):
 row=preference(db,hid,user.id);db.commit();return {"low_balance":row.low_balance,"upcoming_payments":row.upcoming_payments,"missing_income":row.missing_income,"upcoming_days":row.upcoming_days}
@router.put("/notification-preferences")
def put_preferences(body:NotificationPreferencesUpdate,hid:str=Depends(household_id),user:User=Depends(current_user),db:Session=Depends(get_db)):
 row=preference(db,hid,user.id)
 for key,value in body.model_dump().items():setattr(row,key,value)
 record_audit(db,hid,user.id,"notification_preferences_updated");db.commit();return body.model_dump()
@router.get("/audit-events")
def audit_events(page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),action:str|None=None,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 allowed={"user_signed_up","login_succeeded","password_reset","payment_matched","notification_preferences_updated","notification_dismissed","privacy_export_created","account_deletion_requested","account_deletion_confirmed","account_deletion_cancelled"};base=select(AuditEvent).where(AuditEvent.household_id==hid,AuditEvent.action.in_(allowed))
 if action:base=base.where(AuditEvent.action==action)
 total=db.scalar(select(func.count()).select_from(base.subquery())) or 0;rows=db.scalars(base.order_by(AuditEvent.occurred_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
 return {"items":[{"id":row.id,"action":row.action,"occurred_at":row.occurred_at.isoformat(),"detail":public_detail(row)} for row in rows],"page":page,"page_size":page_size,"total":total}
