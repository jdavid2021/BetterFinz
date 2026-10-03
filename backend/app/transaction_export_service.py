import csv
import html
import io
import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountingEntity, FinancialAccount, Household, LedgerAccount
from app.transaction_query_service import TransactionQuery, transaction_statement


def _signed_amount(direction: str, amount: Decimal) -> Decimal:
    if direction == "debit":
        return -amount
    return amount


def _category_paths(accounts: list[LedgerAccount]) -> dict[str, str]:
    by_id = {row.id: row for row in accounts}
    result: dict[str, str] = {}
    for row in accounts:
        names = [row.name]
        parent = by_id.get(row.parent_id or "")
        seen = {row.id}
        while parent and parent.id not in seen:
            seen.add(parent.id)
            names.insert(0, parent.name)
            parent = by_id.get(parent.parent_id or "")
        result[row.id] = " › ".join(names)
    return result


def transaction_export_records(
    db: Session, household_id: str, query: TransactionQuery
) -> tuple[list[dict], dict]:
    transactions = list(db.scalars(transaction_statement(household_id, query)))
    accounts = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.household_id == household_id
            )
        )
    )
    segments = list(
        db.scalars(
            select(AccountingEntity).where(
                AccountingEntity.household_id == household_id
            )
        )
    )
    ledger_accounts = list(
        db.scalars(
            select(LedgerAccount).where(LedgerAccount.household_id == household_id)
        )
    )
    account_map = {row.id: row for row in accounts}
    segment_map = {row.id: row for row in segments}
    category_paths = _category_paths(ledger_accounts)

    records = []
    for transaction in transactions:
        account = account_map.get(transaction.account_id)
        segment = segment_map.get(transaction.entity_id or "")
        records.append(
            {
                "date": transaction.posted_date.isoformat(),
                "account": account.name if account else "Unavailable account",
                "institution": account.institution_name if account else None,
                "mask": account.mask if account else "",
                "merchant": transaction.merchant,
                "description": transaction.original_description,
                "category": category_paths.get(
                    transaction.category_id or "", transaction.category
                ),
                "segment": segment.name if segment else "Unassigned",
                "status": "Pending" if transaction.pending else "Posted",
                "direction": transaction.direction.title(),
                "amount": _signed_amount(transaction.direction, transaction.amount),
                "notes": transaction.notes,
                "pending": transaction.pending,
            }
        )

    household = db.get(Household, household_id)
    selected_account = account_map.get(query.account_id)
    selected_segment = segment_map.get(query.segment_id)
    selected_category = category_paths.get(query.category_id)
    filters = []
    if selected_account:
        filters.append(f"Account: {selected_account.name} •••• {selected_account.mask}")
    if query.q:
        filters.append(f"Search: {query.q}")
    if selected_category:
        filters.append(f"Category: {selected_category}")
    if selected_segment:
        label = household.segment_label if household else "Segment"
        filters.append(f"{label}: {selected_segment.name}")
    if query.amount is not None:
        filters.append(f"Amount: {abs(query.amount):.2f}")
    if query.selected_date:
        filters.append(f"Date: {query.selected_date.isoformat()}")
    else:
        if query.date_from:
            filters.append(f"From: {query.date_from.isoformat()}")
        if query.date_to:
            filters.append(f"To: {query.date_to.isoformat()}")

    settled = [row for row in records if not row["pending"]]
    credits = sum(
        (row["amount"] for row in settled if row["amount"] > 0), Decimal("0")
    )
    debits = -sum(
        (row["amount"] for row in settled if row["amount"] < 0), Decimal("0")
    )
    meta = {
        "title": selected_account.name if selected_account else "All transactions",
        "filters": filters,
        "count": len(records),
        "pending_count": sum(bool(row["pending"]) for row in records),
        "credits": credits,
        "debits": debits,
        "net": credits - debits,
        "generated_at": datetime.now(timezone.utc),
        "segment_label": household.segment_label if household else "Segment",
        "account_slug": _slug(selected_account.name) if selected_account else "all-accounts",
    }
    return records, meta


def _spreadsheet_safe(value: object) -> str:
    text = str(value or "").replace("\x00", "")
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def transaction_csv(records: list[dict], meta: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Date",
            "Account",
            "Institution",
            "Last Four",
            "Merchant",
            "Description",
            "Category",
            meta["segment_label"],
            "Status",
            "Direction",
            "Amount",
            "Notes",
        ]
    )
    for row in records:
        writer.writerow(
            [
                row["date"],
                _spreadsheet_safe(row["account"]),
                _spreadsheet_safe(row["institution"]),
                _spreadsheet_safe(row["mask"]),
                _spreadsheet_safe(row["merchant"]),
                _spreadsheet_safe(row["description"]),
                _spreadsheet_safe(row["category"]),
                _spreadsheet_safe(row["segment"]),
                row["status"],
                row["direction"],
                f'{row["amount"]:.2f}',
                _spreadsheet_safe(row["notes"]),
            ]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _money(value: Decimal) -> str:
    sign = "−" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:50] or "transactions"


def export_filename(meta: dict, extension: str) -> str:
    stamp = meta["generated_at"].date().isoformat()
    return f'FinLeash-transactions-{meta["account_slug"]}-{stamp}.{extension}'


def transaction_print_html(records: list[dict], meta: dict) -> str:
    def escaped(value: object) -> str:
        return html.escape(str(value or ""), quote=True)

    filter_html = "".join(f"<span>{escaped(item)}</span>" for item in meta["filters"])
    if not filter_html:
        filter_html = "<span>All accounts · All dates · All categories</span>"
    rows = []
    for row in records:
        account = escaped(row["account"])
        if row["mask"]:
            account += f'<small>•••• {escaped(row["mask"])}</small>'
        description = escaped(row["merchant"])
        if row["description"] and row["description"] != row["merchant"]:
            description += f'<small>{escaped(row["description"])}</small>'
        rows.append(
            "<tr>"
            f'<td>{escaped(row["date"])}</td>'
            f"<td>{account}</td>"
            f"<td>{description}</td>"
            f'<td>{escaped(row["category"])}</td>'
            f'<td>{escaped(row["segment"])}</td>'
            f'<td>{escaped(row["status"])}</td>'
            f'<td class="amount">{escaped(_money(row["amount"]))}</td>'
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="7" class="empty">No transactions match this view.</td></tr>')

    generated = meta["generated_at"].strftime("%b %d, %Y at %H:%M UTC")
    pending_note = (
        f' · {meta["pending_count"]} pending excluded from totals'
        if meta["pending_count"]
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>{escaped(meta['title'])} transactions · FinLeash</title>
<style>
@page{{size:landscape;margin:.45in}}*{{box-sizing:border-box}}body{{font:12px Arial,sans-serif;color:#14242d;margin:24px;background:#fff}}header{{display:flex;justify-content:space-between;gap:24px;border-bottom:2px solid #087d70;padding-bottom:14px}}h1{{font-size:22px;margin:2px 0 5px}}p{{margin:0;color:#65757d}}button{{border:0;border-radius:7px;background:#087d70;color:#fff;padding:9px 14px;font-weight:700;cursor:pointer}}.filters{{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}}.filters span{{background:#edf5f2;border-radius:12px;padding:5px 8px;color:#31574f}}.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:13px 0 17px}}.summary div{{border:1px solid #dfe5e2;border-radius:8px;padding:10px}}.summary small{{display:block;color:#65757d;text-transform:uppercase;font-size:9px;margin-bottom:4px}}.summary strong{{font-size:15px}}table{{width:100%;border-collapse:collapse}}thead{{display:table-header-group}}th{{background:#f1f5f3;color:#516169;text-align:left;text-transform:uppercase;font-size:9px;letter-spacing:.04em}}th,td{{border-bottom:1px solid #e2e7e5;padding:8px 7px;vertical-align:top}}td small{{display:block;color:#68777e;font-size:9px;margin-top:2px}}.amount{{text-align:right;white-space:nowrap;font-weight:700}}.empty{{text-align:center;padding:35px;color:#68777e}}footer{{margin-top:15px;color:#68777e;font-size:9px}}@media print{{body{{margin:0}}button{{display:none}}tr{{break-inside:avoid}}}}
</style></head><body>
<header><div><p>FINLEASH TRANSACTION REPORT</p><h1>{escaped(meta['title'])}</h1><p>Generated {escaped(generated)}</p></div><button onclick="window.print()">Print / Save PDF</button></header>
<div class="filters">{filter_html}</div>
<section class="summary"><div><small>Transactions</small><strong>{meta['count']}</strong></div><div><small>Posted inflows</small><strong>{escaped(_money(meta['credits']))}</strong></div><div><small>Posted outflows</small><strong>{escaped(_money(meta['debits']))}</strong></div><div><small>Posted net</small><strong>{escaped(_money(meta['net']))}</strong></div></section>
<table><thead><tr><th>Date</th><th>Account</th><th>Transaction</th><th>Category</th><th>{escaped(meta['segment_label'])}</th><th>Status</th><th class="amount">Amount</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<footer>Only the filtered transaction view is shown{escaped(pending_note)}. Account numbers are limited to the last four characters.</footer>
<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),150));</script></body></html>"""
