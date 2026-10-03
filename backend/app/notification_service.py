from datetime import date,timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import FinancialAccount,IncomeEvent,Notification,NotificationPreference,ScheduledPayment
def preference(db:Session,hid:str,uid:str)->NotificationPreference:
 row=db.scalar(select(NotificationPreference).where(NotificationPreference.user_id==uid,NotificationPreference.household_id==hid))
 if row is None:row=NotificationPreference(household_id=hid,user_id=uid);db.add(row);db.flush()
 return row
def add(db:Session,hid:str,uid:str,kind:str,severity:str,title:str,message:str,href:str,key:str)->None:
 dedupe=f"{hid}:{uid}:{key}"
 if not db.scalar(select(Notification.id).where(Notification.dedupe_key==dedupe)):db.add(Notification(household_id=hid,user_id=uid,kind=kind,severity=severity,title=title,message=message,href=href,dedupe_key=dedupe))
def generate_notifications(db:Session,hid:str,uid:str,as_of:date|None=None)->None:
 as_of=as_of or date.today();prefs=preference(db,hid,uid)
 if prefs.low_balance:
  rows=db.scalars(select(FinancialAccount).where(FinancialAccount.household_id==hid,FinancialAccount.is_active,FinancialAccount.kind.in_({"checking","savings","cash_management"}),FinancialAccount.available_balance<=FinancialAccount.reserve))
  for row in rows:add(db,hid,uid,"low_balance","warning","Balance is at or below reserve",f"{row.name} has reached its protected reserve.",f"/accounts?account_id={row.id}",f"low:{row.id}:{row.balance_as_of_date or as_of}")
 if prefs.upcoming_payments:
  end=as_of+timedelta(days=prefs.upcoming_days);rows=db.scalars(select(ScheduledPayment).where(ScheduledPayment.household_id==hid,ScheduledPayment.due_date.between(as_of,end),ScheduledPayment.status.not_in({"paid","cleared","cancelled","skipped"})))
  for row in rows:add(db,hid,uid,"upcoming_payment","info","Payment coming up",f"{row.payee} is due {row.due_date.isoformat()}.","/monthly-plan",f"payment:{row.id}:{row.due_date}")
 if prefs.missing_income:
  cutoff=as_of-timedelta(days=7);rows=db.scalars(select(IncomeEvent).where(IncomeEvent.household_id==hid,IncomeEvent.expected_date<=cutoff,IncomeEvent.status.in_({"estimated","not_confirmed","missing"})))
  for row in rows:add(db,hid,uid,"missing_income","critical","Expected income is missing",f"No matching deposit was found for {row.name}.","/income",f"income:{row.id}:{row.expected_date}")
 db.commit()
def data(row:Notification)->dict:return {"id":row.id,"kind":row.kind,"severity":row.severity,"title":row.title,"message":row.message,"href":row.href,"created_at":row.created_at.isoformat(),"read_at":row.read_at.isoformat() if row.read_at else None}
