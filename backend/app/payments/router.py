from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select

from app.admission.service import deny_public_payment
from app.agreements.service import reject
from app.bookings.router import DatabaseSession, lock_booking
from app.core.config import get_settings
from app.drafts.schemas import StrictModel
from app.payments.eligibility import eligibility
from app.payments.models import CheckoutApproval, PaymentAttempt, SandboxReceipt
from app.payments.provider import (
    SDK,
    SandboxPayPal,
    configured,
    get_paypal,
    require_configured,
)
from app.payments.schemas import AttemptRead, CheckoutApprove, OrderCreate, ReceiptRead
from app.payments.service import (
    approval_for,
    attempt_for,
    capture_order,
    change,
    create_order,
    current_context,
    reconcile,
)

router = APIRouter(
    prefix="/api/bookings/{booking_id}/checkout", tags=["PayPal sandbox"]
)
PayPal = Annotated[SandboxPayPal, Depends(get_paypal)]


class CaptureAction(StrictModel):
    retry_uncertain: bool = Field(default=False, strict=True)


@router.get("/config")
def configuration(booking_id: UUID, session: DatabaseSession):
    deny_public_payment()
    lock_booking(session, booking_id)
    ready = configured()
    return {
        "environment": "sandbox",
        "configured": ready,
        "sdk_url": SDK,
        "client_id": get_settings().paypal_sandbox_client_id if ready else None,
    }


@router.get("/eligibility")
def get_eligibility(booking_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    try:
        state, blockers = eligibility(session, booking_id)
    except HTTPException as error:
        if error.status_code != 409:
            raise
        state, blockers = (
            None,
            [
                error.detail.get("code", "checkout_blocked"),
                *error.detail.get("blockers", []),
            ],
        )
    settings = get_settings()
    execution_allowed = (
        not settings.public_demo_mode or settings.public_sandbox_payments_enabled
    )
    return {
        "eligible": not blockers,
        "blockers": blockers,
        "context": state["context"] if state else None,
        "fingerprint": state["fingerprint"] if state else None,
        "sandbox_configured": configured() and execution_allowed,
        "payment_execution_allowed": execution_allowed,
        "payment_notice": (
            "Payments and provider reconciliation are disabled in "
            "the public demo. Existing records are historical captures only."
        )
        if not execution_allowed
        else None,
    }


@router.post("/approvals", status_code=201)
def approve_checkout(booking_id: UUID, body: CheckoutApprove, session: DatabaseSession):
    lock_booking(session, booking_id)
    state = current_context(session, booking_id)
    if body.expected_context_fingerprint != state["fingerprint"]:
        reject("checkout_context_stale")
    record = CheckoutApproval(
        id=uuid4(),
        booking_id=booking_id,
        fingerprint=state["fingerprint"],
        context=state["context"],
        audit={
            "customer_label": body.customer_label,
            "acknowledged": True,
            "identity_provisional": True,
        },
    )
    session.add(record)
    session.commit()
    return {
        "id": record.id,
        "fingerprint": record.fingerprint,
        "context": record.context,
    }


@router.get("/attempts", response_model=list[AttemptRead])
def list_attempts(booking_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    return list(
        session.scalars(
            select(PaymentAttempt)
            .where(PaymentAttempt.booking_id == booking_id)
            .order_by(PaymentAttempt.created_at.desc())
            .limit(50)
        )
    )


@router.get("/approvals/{approval_id}")
def get_approval(booking_id: UUID, approval_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    record = approval_for(session, booking_id, approval_id)
    return {
        "id": record.id,
        "fingerprint": record.fingerprint,
        "context": record.context,
        "customer_label": record.audit["customer_label"],
    }


@router.post("/orders", response_model=AttemptRead)
def order(
    booking_id: UUID, body: OrderCreate, session: DatabaseSession, paypal: PayPal
):
    deny_public_payment()
    require_configured()
    return create_order(session, booking_id, body.approval_id, paypal)


@router.post("/attempts/{attempt_id}/capture", response_model=AttemptRead)
def capture(
    booking_id: UUID,
    attempt_id: UUID,
    body: CaptureAction,
    session: DatabaseSession,
    paypal: PayPal,
):
    deny_public_payment()
    require_configured()
    return capture_order(session, booking_id, attempt_id, paypal, body.retry_uncertain)


@router.post("/attempts/{attempt_id}/reconcile", response_model=AttemptRead)
def reconcile_attempt(
    booking_id: UUID, attempt_id: UUID, session: DatabaseSession, paypal: PayPal
):
    deny_public_payment()
    require_configured()
    lock_booking(session, booking_id)
    attempt = attempt_for(session, booking_id, attempt_id)
    if attempt.status == "completed":
        return attempt
    if not attempt.order_id:
        reject("order_id_unknown_retry_same_create_request_or_manual_review")
    reconcile(session, attempt, paypal)
    session.commit()
    return attempt


@router.post("/attempts/{attempt_id}/cancel", response_model=AttemptRead)
def cancel_attempt(booking_id: UUID, attempt_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    attempt = attempt_for(session, booking_id, attempt_id)
    if attempt.capture_requested_at is not None or attempt.status in {
        "completed",
        "pending",
    }:
        reject("capture_may_have_occurred_reconcile_required")
    change(session, attempt, "cancelled", "buyer_cancelled")
    session.commit()
    return attempt


@router.get("/receipt", response_model=ReceiptRead)
def receipt(booking_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    record = session.scalar(
        select(SandboxReceipt).where(SandboxReceipt.booking_id == booking_id)
    )
    if record is None:
        raise HTTPException(404, "No verified sandbox capture receipt exists")
    return record
