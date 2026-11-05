from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.agreements.service import reject
from app.bookings.router import lock_booking
from app.core.config import get_settings
from app.payments.eligibility import eligibility
from app.payments.models import (
    CheckoutApproval,
    PaymentAttempt,
    PaymentEvent,
    SandboxReceipt,
)
from app.payments.provider import PayPalFailure, provider_id

ACTIVE = {
    "creating",
    "create_uncertain",
    "awaiting_buyer",
    "capture_uncertain",
    "pending",
}
REPLAY_WINDOW = timedelta(minutes=15)  # Deliberately short local operational guard.


def now():
    return datetime.now(UTC)


def change(session, attempt, status, code=None):
    attempt.status, attempt.error_code = status, code
    session.add(PaymentEvent(attempt_id=attempt.id, status=status, code=code))


def current_context(session, booking_id):
    state, blockers = eligibility(session, booking_id)
    if blockers:
        reject("checkout_blocked", blockers=blockers)
    return state


def approval_for(session, booking_id, approval_id):
    approval = session.scalar(
        select(CheckoutApproval).where(
            CheckoutApproval.id == approval_id,
            CheckoutApproval.booking_id == booking_id,
        )
    )
    if approval is None:
        raise HTTPException(404, "Checkout approval not found for this booking")
    current = current_context(session, booking_id)
    if (
        approval.fingerprint != current["fingerprint"]
        or approval.context != current["context"]
    ):
        reject("checkout_approval_stale")
    return approval


def attempt_for(session, booking_id, attempt_id):
    record = session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.id == attempt_id, PaymentAttempt.booking_id == booking_id)
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise HTTPException(404, "Payment attempt not found for this booking")
    return record


def ensure_no_other_attempt(session, booking_id, approval_id):
    active = session.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.booking_id == booking_id,
            PaymentAttempt.approval_id != approval_id,
            PaymentAttempt.status.in_(ACTIVE),
        )
    )
    if active:
        reject(
            "existing_payment_attempt_requires_resolution", attempt_id=str(active.id)
        )


def create_order(session, booking_id, approval_id, paypal):
    from app.admission.service import deny_public_payment

    deny_public_payment()
    lock_booking(session, booking_id)
    approval = approval_for(session, booking_id, approval_id)
    ensure_no_other_attempt(session, booking_id, approval_id)
    attempt = session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.approval_id == approval_id)
    )
    if attempt is None:
        attempt = PaymentAttempt(
            id=uuid4(),
            booking_id=booking_id,
            approval_id=approval_id,
            amount=approval.context["amount"],
            currency=approval.context["currency"],
            create_key=str(uuid4()),
            capture_key=str(uuid4()),
            status="creating",
        )
        session.add(attempt)
        session.flush()
        change(session, attempt, "creating")
        # Persist stable request keys before the remote action.
        session.commit()
    ident = attempt.id
    lock_booking(session, booking_id)
    attempt = attempt_for(session, booking_id, ident)
    approval_for(session, booking_id, approval_id)
    if attempt.order_id or attempt.status not in {"creating", "create_uncertain"}:
        return attempt
    if now() - attempt.created_at > REPLAY_WINDOW:
        change(session, attempt, "create_uncertain", "manual_reconciliation_required")
        session.commit()
        return attempt
    try:
        data = paypal.create(attempt)
        attempt.order_id = provider_id(data.get("id"))
        if data.get("status") not in {
            "CREATED",
            "PAYER_ACTION_REQUIRED",
            "APPROVED",
            "COMPLETED",
        }:
            raise PayPalFailure("paypal_invalid_order_status")
        change(session, attempt, "awaiting_buyer")
    except PayPalFailure as error:
        change(session, attempt, "create_uncertain", error.code)
    session.commit()
    return attempt


def amount_matches(raw, attempt):
    try:
        return (
            isinstance(raw, dict)
            and raw.get("currency_code") == attempt.currency
            and isinstance(raw.get("value"), str)
            and Decimal(raw["value"]).is_finite()
            and Decimal(raw["value"]) == Decimal(attempt.amount)
        )
    except InvalidOperation, ValueError:
        return False


def validate_order(data, attempt):
    try:
        if data["id"] != attempt.order_id or data["intent"] != "CAPTURE":
            raise ValueError()
        units = data["purchase_units"]
        if len(units) != 1:
            raise ValueError()
        unit = units[0]
        if (
            unit["reference_id"] != str(attempt.id)
            or unit["custom_id"] != str(attempt.id)
            or unit["invoice_id"] != f"contextkey-{attempt.id}"
            or unit["payee"]["merchant_id"] != get_settings().paypal_sandbox_merchant_id
            or not amount_matches(unit["amount"], attempt)
        ):
            raise ValueError()
        payments = unit.get("payments", {})
        captures = payments.get("captures", [])
        if attempt.capture_id is not None and not captures:
            raise ValueError()
        if payments.get("authorizations") or len(captures) > 1:
            raise ValueError()
        if captures:
            cap = captures[0]
            provider_id(cap["id"])
            if not amount_matches(cap["amount"], attempt):
                raise ValueError()
        return captures
    except (KeyError, TypeError, ValueError) as error:
        raise PayPalFailure("paypal_order_or_amount_verification_failed") from error


def record_remote(session, attempt, data):
    # Receipt is historical proof; older notifications cannot undo it.
    if attempt.status == "completed":
        return []
    captures = validate_order(data, attempt)
    if captures:
        capture = captures[0]
        if attempt.capture_id is not None and attempt.capture_id != capture["id"]:
            raise PayPalFailure("paypal_capture_identity_mismatch")
        attempt.capture_id = capture["id"]
        status = capture.get("status")
        if (
            status == "COMPLETED"
            and data.get("status") == "COMPLETED"
            and capture.get("final_capture") is True
        ):
            other = session.scalar(
                select(SandboxReceipt).where(
                    SandboxReceipt.booking_id == attempt.booking_id,
                    SandboxReceipt.attempt_id != attempt.id,
                )
            )
            if other is not None:
                raise PayPalFailure("paypal_other_attempt_already_paid")
            existing = session.scalar(
                select(SandboxReceipt).where(SandboxReceipt.attempt_id == attempt.id)
            )
            if existing is None:
                approval = session.get(CheckoutApproval, attempt.approval_id)
                session.add(
                    SandboxReceipt(
                        booking_id=attempt.booking_id,
                        attempt_id=attempt.id,
                        approval_id=attempt.approval_id,
                        context=approval.context,
                        amount=attempt.amount,
                        currency=attempt.currency,
                        order_id=attempt.order_id,
                        capture_id=capture["id"],
                    )
                )
            change(session, attempt, "completed")
        elif status == "PENDING":
            change(session, attempt, "pending", "paypal_capture_pending")
        elif status in {"DECLINED", "DENIED", "FAILED"}:
            change(session, attempt, "failed", "paypal_capture_declined")
        else:
            raise PayPalFailure("paypal_capture_requires_manual_review")
    elif data.get("status") == "VOIDED":
        change(session, attempt, "failed", "paypal_order_voided")
    elif data.get("status") == "COMPLETED":
        raise PayPalFailure("paypal_completed_without_verified_capture")
    elif data.get("status") in {"CREATED", "PAYER_ACTION_REQUIRED", "APPROVED"}:
        if attempt.status in {"cancelled", "failed", "blocked"}:
            return captures
        change(
            session,
            attempt,
            "capture_uncertain" if attempt.capture_requested_at else "awaiting_buyer",
        )
    else:
        raise PayPalFailure("paypal_unknown_order_state")
    return captures


def reconcile(session, attempt, paypal):
    from app.admission.service import deny_public_payment

    if session.info.get("verified_paypal_webhook") is not True:
        deny_public_payment()
    # Retrieval may recognize a payment already completed under a historical
    # approval. It never authorizes a new capture or rewrites that approval.
    try:
        data = paypal.get(attempt.order_id)
        record_remote(session, attempt, data)
        return data
    except PayPalFailure as error:
        change(
            session,
            attempt,
            "capture_uncertain" if attempt.capture_requested_at else "create_uncertain",
            error.code,
        )
        return None


def capture_order(session, booking_id, attempt_id, paypal, retry_uncertain=False):
    from app.admission.service import deny_public_payment

    deny_public_payment()
    lock_booking(session, booking_id)
    attempt = attempt_for(session, booking_id, attempt_id)
    if attempt.status == "completed":
        return attempt
    if not attempt.order_id or attempt.status in {"cancelled", "failed", "blocked"}:
        reject("payment_attempt_not_capturable")
    # GET before every POST, including retries. Never trust browser approval.
    data = reconcile(session, attempt, paypal)
    if data is None or attempt.status in {"completed", "pending", "failed"}:
        session.commit()
        return attempt
    approval_for(session, booking_id, attempt.approval_id)
    if data.get("status") != "APPROVED":
        change(session, attempt, "awaiting_buyer", "paypal_buyer_approval_required")
        session.commit()
        return attempt
    if attempt.capture_requested_at is not None:
        if not retry_uncertain or now() - attempt.capture_requested_at > REPLAY_WINDOW:
            change(
                session,
                attempt,
                "capture_uncertain",
                "reconcile_or_manual_review_required",
            )
            session.commit()
            return attempt
    else:
        attempt.capture_requested_at = now()
        change(session, attempt, "capture_uncertain", "capture_request_prepared")
        session.commit()  # Crash-safe intent, key and timestamp precede remote action.
        lock_booking(session, booking_id)
        attempt = attempt_for(session, booking_id, attempt_id)
        # A different worker may have captured during the commit/relock gap.
        if attempt.status == "completed":
            return attempt
        if attempt.status in {"cancelled", "failed", "pending", "blocked"}:
            reject("payment_attempt_not_capturable")
        approval_for(session, booking_id, attempt.approval_id)
        # Reconcile again after relinquishing the booking lock.
        data = reconcile(session, attempt, paypal)
        if data is None or attempt.status in {"completed", "pending", "failed"}:
            session.commit()
            return attempt
        if data.get("status") != "APPROVED":
            session.commit()
            return attempt
    # Retain the shared booking lock across remote capture + verification. All
    # evidence/version mutations use the same lock and cannot bypass eligibility.
    try:
        paypal.capture(attempt)
        reconcile(session, attempt, paypal)
    except PayPalFailure as error:
        change(session, attempt, "capture_uncertain", error.code)
    session.commit()
    return attempt
