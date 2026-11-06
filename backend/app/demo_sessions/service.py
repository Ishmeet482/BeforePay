import hashlib
import hmac
import re
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.demo_sessions.models import DemoSession

COOKIE = "beforepay_demo_session"
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
SAFE = {"GET", "HEAD", "OPTIONS"}


def token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token(token):
    return hmac.new(
        token.encode("ascii"), b"beforepay-csrf-v1", hashlib.sha256
    ).hexdigest()


def reject_session():
    raise HTTPException(
        401,
        {
            "code": "demo_session_required",
            "message": (
                "Demo session missing, expired or signed out. Enter the demo "
                "explicitly to start a new isolated workspace; unsaved inputs "
                "are retained."
            ),
        },
    )


def check_origin(request, *, required=False):
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        (required and not origin)
        or (origin and origin not in get_settings().demo_allowed_origins)
    ):
        raise HTTPException(403, {"code": "demo_origin_rejected"})


def active_session(session, token):
    if not token or not TOKEN.fullmatch(token):
        return None
    return session.scalar(
        select(DemoSession)
        .where(
            DemoSession.token_hash == token_hash(token),
            DemoSession.expires_at > func.clock_timestamp(),
            DemoSession.revoked_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )


def check_csrf(request, token):
    check_origin(request, required=True)
    supplied = request.headers.get("x-beforepay-csrf", "")
    if not re.fullmatch(r"[a-f0-9]{64}", supplied) or not hmac.compare_digest(
        supplied, csrf_token(token)
    ):
        raise HTTPException(403, {"code": "demo_csrf_rejected"})


def current_owner(session):
    if session.info.get("verified_paypal_webhook") is True:
        return None
    owner = session.info.get("demo_session_id")
    if owner is None:
        reject_session()
    valid = session.scalar(
        select(DemoSession.id).where(
            DemoSession.id == owner,
            DemoSession.revoked_at.is_(None),
            DemoSession.expires_at > func.clock_timestamp(),
        )
    )
    if valid is None:
        reject_session()
    return owner


def owned_session(request: Request, session: Annotated[Session, Depends(get_session)]):
    check_origin(request)
    token = request.cookies.get(COOKIE)
    record = active_session(session, token)
    if record is None:
        reject_session()
    if request.method not in SAFE:
        check_csrf(request, token)
    session.info["demo_session_id"] = record.id
    # Server-derived lock mode, never a caller-supplied role or approval flag.
    # Shared reads still exclude agreement/payment mutations for their lifetime.
    session.info["booking_read_only"] = request.method in SAFE
    # Gate before endpoint logic, provider calls or PDF extraction. FastAPI may
    # already have parsed bounded JSON/multipart bodies while resolving inputs.
    booking_id = request.path_params.get("booking_id")
    if booking_id is not None:
        from app.bookings.models import Booking

        try:
            booking_id = UUID(str(booking_id))
        except ValueError as error:
            raise HTTPException(422, "Invalid booking UUID") from error
        if (
            session.scalar(
                select(Booking.id).where(
                    Booking.id == booking_id, Booking.owner_session_id == record.id
                )
            )
            is None
        ):
            raise HTTPException(404, "Booking not found")
    if request.method not in SAFE:
        from app.admission.service import reserve

        reserve(
            session,
            "write",
            "booking_mutation",
            {"path": request.url.path},
            booking_id=booking_id,
        )
    return session
