from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select

from app.admission.service import run_ai
from app.agreements.service import (
    latest_agreement,
    reject,
    require_current_confirmation,
)
from app.bookings.router import DatabaseSession, lock_booking
from app.comparisons.models import BookingComparison, ProposalVersion
from app.comparisons.provider import GeminiPolicyComparator, get_policy_comparator
from app.comparisons.schemas import (
    ComparisonCreate,
    ComparisonRead,
    PolicyOutput,
    ProposalCreate,
    ProposalRead,
)
from app.comparisons.service import (
    apply_policies,
    comparison_read,
    digest,
    latest_proposal,
    plan_comparison,
    require_proposal,
)
from app.drafts.provider import provider_error

router = APIRouter(prefix="/api/bookings/{booking_id}", tags=["booking comparison"])


@router.post("/merchant-bookings", response_model=ProposalRead, status_code=201)
def create_proposal(booking_id: UUID, body: ProposalCreate, session: DatabaseSession):
    lock_booking(session, booking_id)
    previous = latest_proposal(session, booking_id)
    if (previous.id if previous else None) != body.expected_latest_id:
        reject("stale_merchant_booking")
    if body.content.included_items_none and body.content.included_items:
        raise HTTPException(
            422, "Explicit no included items requires an empty items list"
        )
    record = ProposalVersion(
        id=uuid4(),
        booking_id=booking_id,
        version=previous.version + 1 if previous else 1,
        content=body.content.model_dump(mode="json"),
        audit={
            "merchant_label": body.merchant_label,
            "reason": body.reason,
            "identity_provisional": True,
            "parent_id": str(previous.id) if previous else None,
        },
    )
    record.fingerprint = digest(
        {
            "id": record.id,
            "booking_id": booking_id,
            "version": record.version,
            "content": record.content,
            "audit": record.audit,
        }
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("/merchant-bookings", response_model=list[ProposalRead])
def list_proposals(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    return list(
        session.scalars(
            select(ProposalVersion)
            .where(ProposalVersion.booking_id == booking_id)
            .order_by(ProposalVersion.version.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/merchant-bookings/{proposal_id}", response_model=ProposalRead)
def get_proposal(booking_id: UUID, proposal_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    return require_proposal(session, booking_id, proposal_id)


def require_pair(session, booking_id, body):
    confirmation = require_current_confirmation(session, booking_id)
    agreement = latest_agreement(session, booking_id)
    proposal = require_proposal(session, booking_id, body.proposal_id)
    latest = latest_proposal(session, booking_id)
    if (
        agreement.id != body.agreement_id
        or agreement.fingerprint != body.agreement_fingerprint
    ):
        reject("stale_agreement")
    if latest.id != proposal.id or proposal.fingerprint != body.proposal_fingerprint:
        reject("stale_merchant_booking")
    return agreement, proposal, confirmation


@router.post("/comparisons", response_model=ComparisonRead, status_code=201)
def create_comparison(
    booking_id: UUID,
    body: ComparisonCreate,
    session: DatabaseSession,
    comparator: Annotated[GeminiPolicyComparator, Depends(get_policy_comparator)],
):
    agreement, proposal, confirmation = require_pair(session, booking_id, body)
    results, pending = plan_comparison(agreement.content, proposal.content)
    confirmation_id = confirmation.id
    session.rollback()  # Never hold DB locks during provider inference.
    metadata = None
    if pending:
        result = run_ai(
            session,
            "comparison",
            {"binding": body.model_dump(mode="json"), "policies": pending},
            lambda: comparator.compare(pending),
            booking_id=booking_id,
        )
        try:
            output = PolicyOutput.model_validate(result.output.model_dump())
            apply_policies(results, pending, output)
        except (ValueError, ValidationError) as error:
            raise provider_error(
                "ai_invalid_output",
                "Policy comparison quotes or categories are invalid.",
            ) from error
        metadata = result.metadata
    # Recheck exact versions, confirmation and evidence after the network call.
    _, _, current_confirmation = require_pair(session, booking_id, body)
    if current_confirmation.id != confirmation_id:
        reject("confirmation_changed_during_comparison")
    record = BookingComparison(
        id=uuid4(),
        booking_id=booking_id,
        agreement_id=body.agreement_id,
        agreement_fingerprint=body.agreement_fingerprint,
        confirmation_id=confirmation_id,
        proposal_id=body.proposal_id,
        proposal_fingerprint=body.proposal_fingerprint,
        results=results,
        model_metadata=metadata,
    )
    record.fingerprint = digest(
        {
            "id": record.id,
            "booking_id": booking_id,
            "inputs": body.model_dump(mode="json"),
            "confirmation_id": confirmation_id,
            "results": results,
            "model_metadata": metadata,
        }
    )
    session.add(record)
    session.flush()
    response = comparison_read(session, record)
    session.commit()
    return response


@router.get("/comparisons", response_model=list[ComparisonRead])
def list_comparisons(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    records = session.scalars(
        select(BookingComparison)
        .where(BookingComparison.booking_id == booking_id)
        .order_by(BookingComparison.created_at.desc(), BookingComparison.id)
        .limit(limit)
        .offset(offset)
    )
    return [comparison_read(session, record) for record in records]


@router.get("/comparisons/{comparison_id}", response_model=ComparisonRead)
def get_comparison(booking_id: UUID, comparison_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    record = session.scalar(
        select(BookingComparison).where(
            BookingComparison.id == comparison_id,
            BookingComparison.booking_id == booking_id,
        )
    )
    if record is None:
        raise HTTPException(404, "Comparison not found for this booking")
    return comparison_read(session, record)
