"""Verified notifications are hints to retrieve provider state, never proof of pay."""

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.bookings.router import lock_booking
from app.core.database import get_session
from app.payments.models import PaymentAttempt, PayPalWebhookEvent
from app.payments.provider import PayPalFailure, SandboxPayPal, get_paypal, provider_id
from app.payments.service import attempt_for, reconcile

router = APIRouter(prefix="/api/paypal/sandbox", tags=["PayPal sandbox"])
EVENTS = {
    "CHECKOUT.ORDER.APPROVED",
    "CHECKOUT.ORDER.COMPLETED",
    "PAYMENT.CAPTURE.COMPLETED",
    "PAYMENT.CAPTURE.PENDING",
    "PAYMENT.CAPTURE.DENIED",
}


@router.post("/webhook")
def receive_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    paypal: Annotated[SandboxPayPal, Depends(get_paypal)],
    event: Annotated[dict, Body()],
):
    try:
        paypal.verify_webhook(event, request.headers)
    except PayPalFailure as error:
        raise HTTPException(503, "PayPal webhook verification unavailable") from error

    # Only the verified provider callback may reconcile across demo ownership.
    session.info["verified_paypal_webhook"] = True

    event_id, event_type = event.get("id"), event.get("event_type")
    if (
        not isinstance(event_id, str)
        or not 1 <= len(event_id) <= 128
        or not isinstance(event_type, str)
        or not 1 <= len(event_type) <= 64
    ):
        raise HTTPException(400, "Invalid webhook identity")
    if event_type not in EVENTS:
        return {"status": "ignored"}
    try:
        resource = event["resource"]
        order_id = provider_id(
            resource["id"]
            if event_type.startswith("CHECKOUT.ORDER.")
            else resource["supplementary_data"]["related_ids"]["order_id"]
        )
    except (KeyError, TypeError, PayPalFailure) as error:
        raise HTTPException(400, "Webhook has no valid related order") from error
    attempt = session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == order_id)
    )
    if attempt is None:
        # No event-supplied local IDs or links can attach a new payment.
        return {"status": "ignored"}
    booking_id, attempt_id = attempt.booking_id, attempt.id
    lock_booking(session, booking_id)
    attempt = attempt_for(session, booking_id, attempt_id)
    digest = hashlib.sha256(
        json.dumps(
            event, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    claimed = session.scalar(
        insert(PayPalWebhookEvent)
        .values(
            event_id=event_id,
            digest=digest,
            event_type=event_type,
            attempt_id=attempt.id,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(PayPalWebhookEvent.event_id)
    )
    if claimed is None:
        prior = session.get(PayPalWebhookEvent, event_id)
        if prior.digest != digest or prior.attempt_id != attempt.id:
            raise HTTPException(409, "Webhook event identity conflict")
        return {"status": "duplicate"}
    if attempt.status != "completed":
        # Same booking lock as capture and evidence/version mutations. No POST
        # capture and no eligibility refresh: this can only recognize past pay.
        if reconcile(session, attempt, paypal) is None:
            session.rollback()
            raise HTTPException(
                503, "Payment reconciliation requires redelivery or review"
            )
    session.commit()
    return {"status": "processed"}
