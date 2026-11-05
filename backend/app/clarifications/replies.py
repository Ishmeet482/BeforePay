"""Append merchant statements; never interpret them as resolution or approval."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.agreements.service import reject
from app.bookings.router import DatabaseSession, lock_booking
from app.clarifications.models import ClarificationSuggestion, MerchantReply
from app.clarifications.schemas import ReplyCreate, ReplyRead, SuggestionRead
from app.clarifications.service import require_current, suggestion_read
from app.comparisons.service import digest

router = APIRouter(
    prefix="/api/bookings/{booking_id}", tags=["provisional merchant responses"]
)


def scoped_suggestion(session, booking_id, comparison_id, suggestion_id):
    suggestion = session.scalar(
        select(ClarificationSuggestion).where(
            ClarificationSuggestion.id == suggestion_id,
            ClarificationSuggestion.booking_id == booking_id,
            ClarificationSuggestion.comparison_id == comparison_id,
        )
    )
    if suggestion is None:
        raise HTTPException(404, "Suggestion not found for this booking and comparison")
    return suggestion


def reply_read(session, reply, suggestion):
    state = suggestion_read(session, suggestion)
    fields = {
        name: getattr(reply, name)
        for name in ReplyRead.model_fields
        if name not in {"stale", "stale_reasons"}
    }
    return ReplyRead(**fields, stale=state.stale, stale_reasons=state.stale_reasons)


@router.get("/clarifications", response_model=list[SuggestionRead])
def booking_questions(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    records = session.scalars(
        select(ClarificationSuggestion)
        .where(
            ClarificationSuggestion.booking_id == booking_id,
        )
        .order_by(ClarificationSuggestion.created_at.desc(), ClarificationSuggestion.id)
        .limit(limit)
        .offset(offset)
    )
    return [suggestion_read(session, record) for record in records]


REPLIES = "/comparisons/{comparison_id}/clarifications/{suggestion_id}/replies"


@router.post(REPLIES, response_model=ReplyRead, status_code=201)
def create_reply(
    booking_id: UUID,
    comparison_id: UUID,
    suggestion_id: UUID,
    body: ReplyCreate,
    session: DatabaseSession,
):
    lock_booking(session, booking_id)
    suggestion = scoped_suggestion(session, booking_id, comparison_id, suggestion_id)
    require_current(session, booking_id, comparison_id, body.comparison_fingerprint)
    if (
        suggestion.fingerprint != body.suggestion_fingerprint
        or suggestion.comparison_fingerprint != body.comparison_fingerprint
        or suggestion.proposal_id != body.proposal_id
        or suggestion.proposal_fingerprint != body.proposal_fingerprint
        or suggestion_read(session, suggestion).stale
    ):
        reject("stale_clarification_reply_context")
    if suggestion.output["status"] != "suggested" or not suggestion.output["question"]:
        raise HTTPException(
            422, "Only a saved clarification question can receive replies"
        )
    record = MerchantReply(
        id=uuid4(),
        booking_id=booking_id,
        suggestion_id=suggestion.id,
        suggestion_fingerprint=suggestion.fingerprint,
        comparison_id=suggestion.comparison_id,
        comparison_fingerprint=suggestion.comparison_fingerprint,
        proposal_id=suggestion.proposal_id,
        proposal_fingerprint=suggestion.proposal_fingerprint,
        merchant_label=body.merchant_label,
        response=body.response,
        identity_provisional=True,
    )
    record.fingerprint = digest(
        {
            "id": record.id,
            "booking_id": booking_id,
            "suggestion_id": suggestion.id,
            "comparison_id": comparison_id,
            **body.model_dump(mode="json"),
            "identity_provisional": True,
        }
    )
    session.add(record)
    session.flush()
    response = reply_read(session, record, suggestion)
    session.commit()
    return response


@router.get(REPLIES, response_model=list[ReplyRead])
def list_replies(
    booking_id: UUID,
    comparison_id: UUID,
    suggestion_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    suggestion = scoped_suggestion(session, booking_id, comparison_id, suggestion_id)
    rows = session.scalars(
        select(MerchantReply)
        .where(
            MerchantReply.booking_id == booking_id,
            MerchantReply.suggestion_id == suggestion_id,
        )
        .order_by(MerchantReply.created_at.desc(), MerchantReply.id)
        .limit(limit)
        .offset(offset)
    )
    return [reply_read(session, row, suggestion) for row in rows]
