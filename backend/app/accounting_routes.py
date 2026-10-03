from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.accounting_service import (
    AccountingError,
    balance_sheet,
    create_category,
    create_entity,
    list_entities,
    segment_settings,
    update_entity,
    update_segment_settings,
    update_transaction_segments,
    profit_and_loss,
    public_categories,
    trial_balance,
    update_category,
    update_workspace,
    workspace,
)
from app.auth import household_id
from app.db import get_db
from app.schemas import (
    AccountingSegmentCreate,
    AccountingSegmentUpdate,
    AccountingWorkspaceUpdate,
    SegmentSettingsUpdate,
    TransactionSegmentUpdate,
    LedgerCategoryCreate,
    LedgerCategoryUpdate,
)

router = APIRouter(prefix="/api/v1/accounting", tags=["Accounting"])


def handled(action):
    try:
        return action()
    except AccountingError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/workspace")
def get_workspace(hid: str = Depends(household_id), db: Session = Depends(get_db)):
    return handled(lambda: workspace(db, hid))


@router.patch("/workspace")
def patch_workspace(
    body: AccountingWorkspaceUpdate,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(lambda: update_workspace(db, hid, body.workspace_type))


@router.get("/segments")
def segments(hid: str = Depends(household_id), db: Session = Depends(get_db)):
    return handled(lambda: list_entities(db, hid))


@router.post("/segments", status_code=201)
def add_segment(
    body: AccountingSegmentCreate,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(lambda: create_entity(db, hid, body.name))


@router.get("/categories")
def categories(
    include_inactive: bool = False,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(lambda: public_categories(db, hid, include_inactive))


@router.post("/categories", status_code=201)
def add_category(
    body: LedgerCategoryCreate,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(
        lambda: create_category(db, hid, body.name, body.parent_id, body.account_type)
    )


@router.patch("/categories/{category_id}")
def patch_category(
    category_id: str,
    body: LedgerCategoryUpdate,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(
        lambda: update_category(
            db,
            hid,
            category_id,
            body.name,
            body.parent_id,
            body.is_active,
        )
    )
@router.patch("/segments/{segment_id}")
def patch_segment(segment_id: str, body: AccountingSegmentUpdate, hid: str = Depends(household_id), db: Session = Depends(get_db)):
    return handled(lambda: update_entity(db, hid, segment_id, body.name, body.is_active))


@router.get("/segment-settings")
def get_segment_settings(hid: str = Depends(household_id), db: Session = Depends(get_db)):
    return handled(lambda: segment_settings(db, hid))


@router.patch("/segment-settings")
def patch_segment_settings(body: SegmentSettingsUpdate, hid: str = Depends(household_id), db: Session = Depends(get_db)):
    return handled(lambda: update_segment_settings(db, hid, body.label))


@router.patch("/transaction-segments")
def patch_transaction_segments(body: TransactionSegmentUpdate, hid: str = Depends(household_id), db: Session = Depends(get_db)):
    return handled(lambda: update_transaction_segments(db, hid, body.transaction_ids, body.segment_id))


@router.get("/reports/profit-loss")
def pnl(
    date_from: date,
    date_to: date,
    segment_id: str | None = None,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(lambda: profit_and_loss(db, hid, date_from, date_to, segment_id))


@router.get("/reports/trial-balance")
def tb(
    as_of: date,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(lambda: trial_balance(db, hid, as_of, None))


@router.get("/reports/balance-sheet")
def bs(
    as_of: date,
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    return handled(lambda: balance_sheet(db, hid, as_of, None))
