from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import HouseholdMember
from app.notification_service import generate_notifications
from sqlalchemy import select
@celery_app.task(name="finleash.notifications.scan",ignore_result=True)
def scan_notifications()->dict:
 generated=0
 with SessionLocal() as db:
  members=list(db.scalars(select(HouseholdMember)))
  for member in members:
   generate_notifications(db,member.household_id,member.user_id);generated+=1
 return {"households_scanned":generated}
