from fastapi import APIRouter,Depends,HTTPException,Response
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import household_id
from app.db import get_db
from app.models import FinancialAccount,FinancialConnection
from app.simplefin_service import SimpleFinBusy,SimpleFinError,connect,status,sync_connection,fetch,decrypt,infer_kind,public_account,preview
router=APIRouter(prefix='/api/v1/integrations/simplefin',tags=['SimpleFIN'])
class Token(BaseModel):setup_token:str=Field(min_length=16,max_length=4096)
class Choice(BaseModel):provider_account_id:str;existing_account_id:str|None=None;include:bool=True;confirm_create_new:bool=False
class Link(BaseModel):accounts:list[Choice]
def connection(db,hid,cid):
 row=db.scalar(select(FinancialConnection).where(FinancialConnection.id==cid,FinancialConnection.household_id==hid,FinancialConnection.provider=='simplefin'))
 if not row:raise HTTPException(404,'SimpleFIN connection not found.')
 return row
@router.get('')
def get_status(hid:str=Depends(household_id),db:Session=Depends(get_db)):return status(db,hid)
@router.post('/connect',status_code=201)
def create(body:Token,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 try:return connect(db,hid,body.setup_token)
 except SimpleFinError as e:raise HTTPException(422,str(e)) from e
@router.post('/{cid}/preview')
def retry_preview(cid:str,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 row=connection(db,hid,cid)
 try:
  payload=fetch(decrypt(row.encrypted_access_url));row.status='pending';row.last_error='';db.commit();return preview(db,hid,row,payload)
 except SimpleFinError as e:
  row.status='error';row.last_error=str(e)[:255];db.commit();raise HTTPException(422,str(e)) from e
@router.post('/{cid}/link')
def link(cid:str,body:Link,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 row=connection(db,hid,cid)
 try:payload=fetch(decrypt(row.encrypted_access_url))
 except SimpleFinError as e:raise HTTPException(422,str(e)) from e
 remote={str(a.get('id')):a for a in payload['accounts']}
 review={item['id']:item for item in preview(db,hid,row,payload)['accounts']}
 selected=[choice for choice in body.accounts if choice.include]
 if not selected:raise HTTPException(422,'Select at least one account to import.')
 if len({choice.provider_account_id for choice in selected})!=len(selected):raise HTTPException(422,'Each SimpleFIN account can only be mapped once.')
 if any(choice.provider_account_id not in remote for choice in selected):raise HTTPException(422,'A selected SimpleFIN account is no longer available.')
 for choice in selected:
  suggested=review.get(choice.provider_account_id,{}).get('suggested_existing_account_id')
  if suggested and not choice.existing_account_id and not choice.confirm_create_new:
   raise HTTPException(422,'Confirm that the provider account is separate from the suggested existing account before creating a duplicate.')
 existing_ids=[choice.existing_account_id for choice in selected if choice.existing_account_id]
 if len(set(existing_ids))!=len(existing_ids):raise HTTPException(422,'Each FinLeash account can only be linked once.')
 for choice in selected:
  a=remote[choice.provider_account_id];public=public_account(a,payload)
  if public['currency']!='USD':raise HTTPException(422,f"{public['name']} uses {public['currency']}. FinLeash currently supports USD accounts only.")
  local=db.scalar(select(FinancialAccount).where(FinancialAccount.id==choice.existing_account_id,FinancialAccount.household_id==hid,FinancialAccount.is_active)) if choice.existing_account_id else None
  linked=db.scalar(select(FinancialAccount).where(FinancialAccount.household_id==hid,FinancialAccount.connection_id==row.id,FinancialAccount.provider_account_id==choice.provider_account_id))
  if linked and local and linked.id!=local.id:raise HTTPException(422,'This SimpleFIN account is already linked to another FinLeash account.')
  if linked:local=linked
  if choice.existing_account_id and not local:raise HTTPException(422,'The selected FinLeash account is unavailable.')
  if local and local.connection_id not in {None,row.id}:raise HTTPException(422,'The selected FinLeash account is already connected.')
  if not local:local=FinancialAccount(household_id=hid,name=public['name'],kind=infer_kind(public['name']),mask=public['mask'],balance=abs(__import__('decimal').Decimal(public['balance'])),available_balance=abs(__import__('decimal').Decimal(public['balance'])),reserve=0,connection_mode='automatic',institution_name=public['institution_name'] or None,data_source='simplefin');db.add(local)
  local.connection_id=row.id;local.provider_account_id=choice.provider_account_id;local.connection_mode='automatic';local.data_source='simplefin'
 db.commit()
 try:return sync_connection(db,hid,row,payload)
 except SimpleFinBusy as e:raise HTTPException(409,str(e)) from e
 except SimpleFinError as e:raise HTTPException(422,str(e)) from e
@router.post('/{cid}/sync')
def run_sync(cid:str,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 try:return sync_connection(db,hid,connection(db,hid,cid))
 except SimpleFinBusy as e:raise HTTPException(409,str(e)) from e
 except SimpleFinError as e:raise HTTPException(422,str(e)) from e
@router.delete('/{cid}',status_code=204)
def disconnect(cid:str,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 row=connection(db,hid,cid)
 for a in db.scalars(select(FinancialAccount).where(FinancialAccount.household_id==hid,FinancialAccount.connection_id==row.id)):a.connection_id=None;a.provider_account_id=None;a.connection_mode='manual'
 db.delete(row);db.commit();return Response(status_code=204)
