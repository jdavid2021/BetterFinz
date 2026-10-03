import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import current_user, household_id
from app.db import get_db
from app.legal_service import accept_current, acceptance_status, legal_documents
from app.models import User
from app.privacy_service import (
    cancel_deletion,
    confirm_deletion,
    deletion_status,
    export_household_zip,
    request_deletion,
)
from app.rate_limit import privacy_rate_limit
from app.schemas import (
    DeletionConfirmationRequest,
    DeletionRequestRequest,
    LegalAcceptanceRequest,
    ReauthenticationRequest,
)


router = APIRouter(prefix="/api/v1")


@router.get("/legal")
def public_legal_configuration():
    return legal_documents()


@router.get("/legal/status")
def legal_status(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return acceptance_status(db, user.id)


@router.post("/legal/accept")
def accept_legal(
    body: LegalAcceptanceRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not body.accept_terms or not body.accept_privacy:
        raise HTTPException(422, "Accept both documents to continue.")
    try:
        return accept_current(
            db, user, body.terms_version, body.privacy_version
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(
    "/privacy/export",
    dependencies=[Depends(privacy_rate_limit)],
)
def privacy_export(
    body: ReauthenticationRequest,
    user: User = Depends(current_user),
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    try:
        content = export_household_zip(db, user, hid, body.password)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=FinLeash-data-export.zip",
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/privacy/deletion/request",
    dependencies=[Depends(privacy_rate_limit)],
    status_code=202,
)
def deletion_request(
    body: DeletionRequestRequest,
    user: User = Depends(current_user),
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    try:
        request, development_url = request_deletion(
            db, user, hid, body.password
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "status": request.status,
        "development_confirmation_url": development_url,
    }


@router.post(
    "/privacy/deletion/confirm",
    dependencies=[Depends(privacy_rate_limit)],
)
def deletion_confirm(
    body: DeletionConfirmationRequest, db: Session = Depends(get_db)
):
    try:
        return confirm_deletion(db, body.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post(
    "/privacy/deletion/cancel",
    dependencies=[Depends(privacy_rate_limit)],
)
def deletion_cancel(
    body: DeletionConfirmationRequest, db: Session = Depends(get_db)
):
    try:
        return cancel_deletion(db, body.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/privacy/deletion")
def get_deletion_status(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return deletion_status(db, user.id)
