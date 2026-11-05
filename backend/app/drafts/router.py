from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.admission.service import run_ai
from app.bookings.router import DatabaseSession, lock_booking, require_booking
from app.drafts.models import DraftVersion
from app.drafts.provider import GeminiExtractor, get_extractor
from app.drafts.schemas import DraftCreate, DraftRead
from app.drafts.service import fingerprint, source_snapshot, validate_and_classify
from app.evidence.models import EvidenceSource

router = APIRouter(prefix="/api/bookings/{booking_id}/drafts", tags=["drafts"])


@router.post("", response_model=DraftRead, status_code=201)
def create_draft(
    booking_id: UUID,
    body: DraftCreate,
    session: DatabaseSession,
    extractor: Annotated[GeminiExtractor, Depends(get_extractor)],
) -> DraftVersion:
    require_booking(session, booking_id)
    sources = list(
        session.scalars(
            select(EvidenceSource)
            .where(
                EvidenceSource.booking_id == booking_id,
                EvidenceSource.id.in_(body.source_ids),
            )
            .options(selectinload(EvidenceSource.pages))
            .order_by(EvidenceSource.id)
        )
    )
    if len(sources) != len(body.source_ids):
        raise HTTPException(
            422, "Every input source must exist and belong to this booking."
        )
    if sum(len(source.original_text) for source in sources) > 200000:
        raise HTTPException(413, "Extraction input exceeds 200,000 characters.")
    snapshots = [source_snapshot(source) for source in sources]
    session.rollback()  # No database lock/transaction during network inference.
    result = run_ai(
        session,
        "extraction",
        snapshots,
        lambda: extractor.extract(snapshots),
        booking_id=booking_id,
    )
    content = validate_and_classify(result.extraction, snapshots)
    # Serialize version allocation on the booking row, only after valid inference.
    lock_booking(session, booking_id)
    next_version = session.scalar(
        select(func.coalesce(func.max(DraftVersion.version), 0) + 1).where(
            DraftVersion.booking_id == booking_id
        )
    )
    draft = DraftVersion(
        booking_id=booking_id,
        version=next_version,
        status="draft",
        input_source_ids=[source["source_id"] for source in snapshots],
        source_fingerprints={s["source_id"]: fingerprint(s) for s in snapshots},
        content=content.model_dump(mode="json"),
        model_metadata=result.metadata.model_dump(mode="json"),
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


@router.get("", response_model=list[DraftRead])
def list_drafts(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DraftVersion]:
    require_booking(session, booking_id)
    return list(
        session.scalars(
            select(DraftVersion)
            .where(DraftVersion.booking_id == booking_id)
            .order_by(DraftVersion.version.desc())
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/{draft_id}", response_model=DraftRead)
def get_draft(
    booking_id: UUID, draft_id: UUID, session: DatabaseSession
) -> DraftVersion:
    require_booking(session, booking_id)
    draft = session.scalar(
        select(DraftVersion).where(
            DraftVersion.id == draft_id, DraftVersion.booking_id == booking_id
        )
    )
    if draft is None:
        raise HTTPException(404, "Draft not found for this booking")
    return draft
