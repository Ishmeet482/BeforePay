from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select

from app.admission.service import reserve
from app.bookings.router import DatabaseSession, lock_booking, require_booking
from app.core.config import get_settings
from app.evidence.models import EvidenceSource
from app.evidence.pdf import extract_pdf
from app.evidence.schemas import (
    SourceRead,
    SourceSummary,
    SourceType,
    TextSourceCreate,
)

router = APIRouter(prefix="/api/bookings/{booking_id}/sources", tags=["evidence"])


@router.post("/text", response_model=SourceRead, status_code=201)
def attach_text(
    booking_id: UUID, body: TextSourceCreate, session: DatabaseSession
) -> EvidenceSource:
    lock_booking(session, booking_id)
    settings = get_settings()
    if (
        settings.public_demo_mode
        and len(body.original_text) > settings.demo_source_max_chars
    ):
        raise HTTPException(
            413,
            "Public demo text exceeds the configured character limit; no source saved.",
        )
    reserve(
        session,
        "source",
        "text_source",
        {},
        units=len(body.original_text.encode()),
        booking_id=booking_id,
    )
    source = EvidenceSource(
        booking_id=booking_id,
        source_type=body.source_type,
        medium="pasted_text",
        original_text=body.original_text,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@router.post("/pdf", response_model=SourceRead, status_code=201)
def attach_pdf(
    booking_id: UUID,
    session: DatabaseSession,
    source_type: Annotated[SourceType, Form()],
    file: Annotated[UploadFile, File(description="Text-based PDF; maximum 5 MiB")],
) -> EvidenceSource:
    require_booking(session, booking_id)
    # End the lookup transaction before potentially expensive PDF extraction.
    session.rollback()
    try:
        settings = get_settings()
        if settings.public_demo_mode:
            size = file.size if file.size is not None else settings.demo_pdf_max_bytes
            if size > settings.demo_pdf_max_bytes:
                raise HTTPException(
                    413, "Public demo PDF exceeds the configured byte limit."
                )
            reserve(
                session,
                "source",
                "pdf_source",
                {},
                # UTF-8 worst case, stored both joined text and page text.
                units=settings.demo_source_max_chars * 8,
                booking_id=booking_id,
            )
            reserve(
                session, "upload", "pdf_upload", {}, units=size, booking_id=booking_id
            )
            filename, original_text, pages = extract_pdf(
                file,
                max_file_bytes=settings.demo_pdf_max_bytes,
                max_pages=settings.demo_pdf_max_pages,
                max_text=settings.demo_source_max_chars,
            )
        else:
            filename, original_text, pages = extract_pdf(file)
    finally:
        file.file.close()
    lock_booking(session, booking_id)
    source = EvidenceSource(
        booking_id=booking_id,
        source_type=source_type,
        medium="pdf",
        filename=filename,
        original_text=original_text,
        pages=pages,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@router.get("", response_model=list[SourceSummary])
def list_sources(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EvidenceSource]:
    require_booking(session, booking_id)
    return list(
        session.scalars(
            select(EvidenceSource)
            .where(EvidenceSource.booking_id == booking_id)
            .order_by(EvidenceSource.created_at, EvidenceSource.id)
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    booking_id: UUID, source_id: UUID, session: DatabaseSession
) -> EvidenceSource:
    require_booking(session, booking_id)
    source = session.scalar(
        select(EvidenceSource).where(
            EvidenceSource.id == source_id, EvidenceSource.booking_id == booking_id
        )
    )
    if source is None:
        raise HTTPException(404, "Source not found for this booking")
    return source
