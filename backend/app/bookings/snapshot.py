"""One coherent, owner-scoped saved read. No provider calls or cached approvals."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.agreements.models import AgreementVersion
from app.agreements.schemas import AgreementRead, ReviewState
from app.agreements.service import review_state
from app.bookings.router import DatabaseSession, lock_booking
from app.cancellations.schemas import RuleRead, Target
from app.cancellations.service import latest_rule, read_rule
from app.comparisons.models import BookingComparison
from app.comparisons.schemas import ComparisonRead, ProposalRead
from app.comparisons.service import comparison_read, latest_proposal
from app.payments.models import PaymentAttempt, SandboxReceipt
from app.payments.router import get_eligibility
from app.payments.schemas import AttemptRead, ReceiptRead

router = APIRouter(prefix="/api/bookings", tags=["saved booking state"])


class SavedState(BaseModel):
    review: ReviewState
    agreement: AgreementRead | None
    proposal: ProposalRead | None
    comparison: ComparisonRead | None
    rules: list[RuleRead]
    attempts: list[AttemptRead]
    receipt: ReceiptRead | None
    eligible: bool
    blockers: list[str]
    sandbox_configured: bool


@router.get("/{booking_id}/saved-state", response_model=SavedState)
def saved_state(booking_id: UUID, session: DatabaseSession):
    # GET's shared booking lock excludes every version/payment mutation for this
    # request. All reads use one session/connection, including readiness/ownership.
    lock_booking(session, booking_id)
    review = review_state(session, booking_id)
    agreement = (
        session.get(AgreementVersion, review.agreement_id)
        if review.agreement_id
        else None
    )
    proposal = latest_proposal(session, booking_id)
    comparison = session.scalar(
        select(BookingComparison)
        .where(BookingComparison.booking_id == booking_id)
        .order_by(BookingComparison.created_at.desc(), BookingComparison.id.desc())
        .limit(1)
    )
    rules = []
    for kind, record in (("agreement", agreement), ("proposal", proposal)):
        if record is not None:
            target = Target(kind=kind, id=record.id, fingerprint=record.fingerprint)
            rule = latest_rule(session, booking_id, target)
            if rule is not None:
                rules.append(read_rule(session, rule))
    eligibility = get_eligibility(booking_id, session)
    attempts = list(
        session.scalars(
            select(PaymentAttempt)
            .where(PaymentAttempt.booking_id == booking_id)
            .order_by(PaymentAttempt.created_at.desc())
            .limit(50)
        )
    )
    receipt = session.scalar(
        select(SandboxReceipt).where(SandboxReceipt.booking_id == booking_id)
    )
    if receipt is None and any(attempt.status == "completed" for attempt in attempts):
        # Preserve the old client's failed receipt GET behaviour: completed
        # status alone must never become a fabricated receipt or readiness signal.
        raise HTTPException(409, {"code": "completed_payment_receipt_missing"})
    return SavedState(
        review=review,
        agreement=agreement,
        proposal=proposal,
        comparison=comparison_read(session, comparison) if comparison else None,
        rules=rules,
        attempts=attempts,
        receipt=receipt,
        eligible=eligibility["eligible"],
        blockers=eligibility["blockers"],
        sandbox_configured=eligibility["sandbox_configured"],
    )
