from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.accounting_service import ensure_household_accounting
from app.auth import household_id
from app.db import get_db
from app.transaction_export_service import (
    export_filename,
    transaction_csv,
    transaction_export_records,
    transaction_print_html,
)
from app.transaction_query_service import TransactionQuery, TransactionQueryError


router = APIRouter(prefix="/api/v1/transactions", tags=["Transactions"])


def export_query(
    q: str = Query("", max_length=255),
    account_id: str = "",
    category: str = Query("", max_length=80),
    category_id: str = "",
    segment_id: str = "",
    amount: Decimal | None = None,
    selected_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
) -> TransactionQuery:
    return TransactionQuery(
        q=q,
        account_id=account_id,
        category=category,
        category_id=category_id,
        segment_id=segment_id,
        amount=amount,
        selected_date=selected_date,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


def export_data(db: Session, hid: str, query: TransactionQuery):
    try:
        ensure_household_accounting(db, hid)
        db.commit()
        return transaction_export_records(db, hid, query)
    except TransactionQueryError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/export.csv")
def download_transactions(
    query: TransactionQuery = Depends(export_query),
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    records, meta = export_data(db, hid, query)
    return Response(
        content=transaction_csv(records, meta),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(meta, "csv")}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/print", response_class=HTMLResponse)
def print_transactions(
    query: TransactionQuery = Depends(export_query),
    hid: str = Depends(household_id),
    db: Session = Depends(get_db),
):
    records, meta = export_data(db, hid, query)
    return HTMLResponse(
        content=transaction_print_html(records, meta),
        headers={
            "Content-Disposition": f'inline; filename="{export_filename(meta, "html")}"',
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
