import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LegalAcceptance, User


def legal_documents() -> dict:
    values = {
        "operator": settings.legal_operator_name,
        "contact": settings.legal_contact_email,
        "governing_law": settings.legal_governing_law,
        "effective_date": settings.legal_effective_date,
        "retention_days": settings.legal_retention_days,
        "deletion_grace_days": settings.deletion_grace_days,
    }
    return {
        "terms": {"version": settings.legal_terms_version, **values},
        "privacy": {"version": settings.legal_privacy_version, **values},
    }


def document_digest(document: str, version: str) -> str:
    values = legal_documents()[document]
    canonical = "|".join(
        str(values[key])
        for key in (
            "version",
            "operator",
            "contact",
            "governing_law",
            "effective_date",
            "retention_days",
            "deletion_grace_days",
        )
    )
    if version != values["version"]:
        raise ValueError(f"Accept the current {document} version.")
    return hashlib.sha256(f"{document}|{canonical}".encode()).hexdigest()


def acceptance_status(db: Session, user_id: str) -> dict:
    accepted = {
        (row.document, row.version)
        for row in db.scalars(
            select(LegalAcceptance).where(LegalAcceptance.user_id == user_id)
        )
    }
    documents = legal_documents()
    missing = [
        name
        for name, values in documents.items()
        if (name, values["version"]) not in accepted
    ]
    return {"required": bool(missing), "missing": missing, "documents": documents}


def accept_current(
    db: Session,
    user: User,
    terms_version: str,
    privacy_version: str,
) -> dict:
    now = datetime.now(timezone.utc)
    for document, version in (
        ("terms", terms_version),
        ("privacy", privacy_version),
    ):
        digest = document_digest(document, version)
        existing = db.scalar(
            select(LegalAcceptance).where(
                LegalAcceptance.user_id == user.id,
                LegalAcceptance.document == document,
                LegalAcceptance.version == version,
            )
        )
        if existing is None:
            db.add(
                LegalAcceptance(
                    user_id=user.id,
                    document=document,
                    version=version,
                    document_digest=digest,
                    accepted_at=now,
                )
            )
    db.commit()
    return acceptance_status(db, user.id)
