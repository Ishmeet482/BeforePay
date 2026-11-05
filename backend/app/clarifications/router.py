from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy import select

from app.admission.service import run_ai
from app.bookings.router import DatabaseSession, lock_booking
from app.clarifications.models import ClarificationSuggestion
from app.clarifications.provider import GeminiClarifier, get_clarifier
from app.clarifications.schemas import (
    Category,
    SuggestCreate,
    SuggestionOutput,
    SuggestionRead,
)
from app.clarifications.service import (
    require_current,
    scoped_comparison,
    suggestion_read,
    term_context,
    validate_references,
)
from app.comparisons.service import digest
from app.drafts.provider import provider_error

router = APIRouter(
    prefix="/api/bookings/{booking_id}/comparisons/{comparison_id}/clarifications",
    tags=["advisory clarification"],
)


@router.post("", response_model=SuggestionRead, status_code=201)
def suggest(
    booking_id: UUID,
    comparison_id: UUID,
    body: SuggestCreate,
    session: DatabaseSession,
    clarifier: Annotated[GeminiClarifier, Depends(get_clarifier)],
):
    comparison = require_current(
        session, booking_id, comparison_id, body.comparison_fingerprint
    )
    context, sufficient = term_context(session, comparison, body.category)
    binding = {
        key: getattr(comparison, key)
        for key in (
            "agreement_id",
            "agreement_fingerprint",
            "proposal_id",
            "proposal_fingerprint",
            "confirmation_id",
        )
    }
    session.rollback()  # No database lock or transaction across inference.
    metadata = None
    if sufficient:
        result = run_ai(
            session,
            "clarification",
            {
                "comparison_id": comparison_id,
                "binding": body.model_dump(mode="json"),
                "context": context,
            },
            lambda: clarifier.suggest(context),
            booking_id=booking_id,
        )
        try:
            output = SuggestionOutput.model_validate(result.output.model_dump())
            supporting = validate_references(output, context["terms"])
        except (ValueError, ValidationError) as error:
            raise provider_error(
                "ai_invalid_output",
                "Clarification output or saved-term references are invalid.",
            ) from error
        metadata = {
            k: v
            for k, v in result.metadata.items()
            if k
            in {
                "provider",
                "requested_model",
                "response_model",
                "response_id",
                "sdk_version",
                "prompt_version",
            }
        }
    else:
        output = SuggestionOutput(
            status="needs_more_information",
            question=None,
            explanation=(
                "Needs more information: complete, unambiguous terms from "
                "both saved versions are required. Review the missing or "
                "uncertain fields first."
            ),
            references=[],
        )
        supporting = []
    session.expire_all()
    current = require_current(
        session, booking_id, comparison_id, body.comparison_fingerprint
    )
    if any(getattr(current, k) != v for k, v in binding.items()):
        from app.agreements.service import reject

        reject("clarification_inputs_changed_during_generation")
    # Rebuild from saved data, never use model-provided evidence or provenance.
    current_context, _ = term_context(session, current, body.category)
    supporting = validate_references(output, current_context["terms"])
    record = ClarificationSuggestion(
        id=uuid4(),
        booking_id=booking_id,
        comparison_id=comparison_id,
        comparison_fingerprint=body.comparison_fingerprint,
        category=body.category,
        **binding,
        output=output.model_dump(mode="json"),
        supporting_terms=supporting,
        model_metadata=metadata,
    )
    record.fingerprint = digest(
        {
            "id": record.id,
            "booking_id": booking_id,
            "comparison_id": comparison_id,
            "comparison_fingerprint": body.comparison_fingerprint,
            **binding,
            "category": body.category,
            "output": record.output,
            "supporting_terms": supporting,
            "model_metadata": metadata,
        }
    )
    session.add(record)
    session.flush()
    response = suggestion_read(session, record)
    session.commit()
    return response


@router.get("", response_model=list[SuggestionRead])
def list_suggestions(
    booking_id: UUID,
    comparison_id: UUID,
    session: DatabaseSession,
    category: Category | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    scoped_comparison(session, booking_id, comparison_id)
    statement = select(ClarificationSuggestion).where(
        ClarificationSuggestion.booking_id == booking_id,
        ClarificationSuggestion.comparison_id == comparison_id,
    )
    if category is not None:
        statement = statement.where(ClarificationSuggestion.category == category)
    records = session.scalars(
        statement.order_by(
            ClarificationSuggestion.created_at.desc(), ClarificationSuggestion.id
        )
        .limit(limit)
        .offset(offset)
    )
    return [suggestion_read(session, record) for record in records]
