from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.auth import household_id
from app.db import get_db
from app.reconciliation_service import ReconciliationError,add_missing_transaction,complete_reconciliation,merge_duplicate,preview_reconciliation,reconciliation_history,review_duplicates
from app.schemas import AccountReconciliationRequest,ReconciliationTransactionCreate,TransactionMergeRequest

router=APIRouter(prefix="/api/v1/reconciliations",tags=["Reconciliation"])

def handled(action):
 try:return action()
 except ReconciliationError as error:raise HTTPException(422,str(error)) from error

@router.post("/preview")
def preview(body:AccountReconciliationRequest,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 return handled(lambda:preview_reconciliation(db,hid,body))

@router.post("",status_code=201)
def complete(body:AccountReconciliationRequest,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 return handled(lambda:complete_reconciliation(db,hid,body))

@router.get("/duplicates/review")
def duplicates(account_id:str|None=None,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 return handled(lambda:review_duplicates(db,hid,account_id))

@router.get("/{account_id}")
def history(account_id:str,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 return handled(lambda:reconciliation_history(db,hid,account_id))

@router.post("/transactions",status_code=201)
def add_transaction(body:ReconciliationTransactionCreate,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 return handled(lambda:add_missing_transaction(db,hid,body))

@router.post("/merge")
def merge(body:TransactionMergeRequest,hid:str=Depends(household_id),db:Session=Depends(get_db)):
 return handled(lambda:merge_duplicate(db,hid,body.keep_transaction_id,body.duplicate_transaction_id))
