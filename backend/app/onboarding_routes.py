from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import household_id
from app.db import get_db
from app.onboarding_service import dismiss_onboarding, onboarding_status

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


@router.get("")
@router.get("/status", include_in_schema=False)
def status(
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    try:
        return onboarding_status(db, hid)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/dismiss")
def dismiss(
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    try:
        return dismiss_onboarding(db, hid)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
