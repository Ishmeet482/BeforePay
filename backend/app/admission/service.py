import hashlib
import json
from contextvars import ContextVar
from datetime import UTC, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.admission.models import Admission, AdmissionControl
from app.core.config import get_settings
from app.demo_sessions.service import current_owner

_admitted = ContextVar("public_ai_admitted", default=False)


def require_ai_admission():
    if get_settings().public_demo_mode and not _admitted.get():
        raise HTTPException(
            503,
            {
                "code": "demo_ai_admission_required",
                "message": "Public AI requires an admitted, session-owned request.",
            },
        )
    if get_settings().public_demo_mode:
        _admitted.set(False)  # One adapter invocation per committed reservation.


def deny(code, message):
    raise HTTPException(
        429,
        {
            "code": code,
            "message": message
            + " No automatic retry or fallback. Saved work remains available.",
        },
    )


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def reserve(caller, kind, action, context, *, units=0, booking_id=None):
    settings = get_settings()
    if not settings.public_demo_mode:
        return None
    with Session(
        caller.info.get("admission_bind", caller.get_bind()), expire_on_commit=False
    ) as db:
        db.info.update(caller.info)
        owner = None if kind == "session" else current_owner(db)
        # One database-wide lock: every instance sees committed reservations.
        db.execute(text("SELECT pg_advisory_xact_lock(18632871, 2)"))
        if owner is not None:
            current_owner(db)
        now = db.scalar(select(func.clock_timestamp()))
        rows = list(db.scalars(select(Admission).where(Admission.kind == kind)))
        own = [row for row in rows if row.session_id == owner]

        def limit(used, cap, code, explanation):
            if used >= cap:
                deny(code, explanation)

        def bytes_limit(used, cap, explanation, code="demo_storage_limit"):
            if used + units > cap:
                deny(code, explanation)

        if kind == "ai":
            control = db.get(AdmissionControl, 1)
            if control is None or control.circuit_reason:
                deny(
                    "demo_ai_paused",
                    "AI paused after quota/access failure or missing setup. "
                    "Ask the organiser to review it.",
                )
            daily = [
                r
                for r in rows
                if r.created_at.astimezone(UTC).date() == now.astimezone(UTC).date()
            ]
            minute = [r for r in rows if r.created_at > now - timedelta(minutes=1)]
            limit(
                len(daily),
                settings.demo_ai_calls_per_day,
                "demo_ai_budget_exhausted",
                "Shared daily AI allowance exhausted or disabled. "
                "Continue manual review; ask the organiser about availability.",
            )
            limit(
                len(own),
                settings.demo_ai_calls_per_session,
                "demo_ai_budget_exhausted",
                "This workspace has used its AI allowance. Continue manual review.",
            )
            limit(
                len(minute),
                settings.demo_ai_calls_per_minute,
                "demo_ai_rate_limit",
                "Shared AI request rate reached. Wait before an explicit new request.",
            )
            bytes_limit(
                sum(r.units for r in own),
                settings.demo_ai_tokens_per_session,
                "Workspace reserved AI token allowance reached.",
                "demo_ai_token_limit",
            )
            bytes_limit(
                sum(r.units for r in daily),
                settings.demo_ai_tokens_per_day,
                "Shared daily reserved AI token allowance reached or disabled.",
                "demo_ai_token_limit",
            )
            bytes_limit(
                sum(r.units for r in minute),
                settings.demo_ai_tokens_per_minute,
                "Shared minute reserved AI token allowance reached or disabled.",
                "demo_ai_token_limit",
            )
            active = [r for r in rows if r.finished_at is None]
            input_hash = fingerprint(context)
            if any(
                r.session_id == owner
                and r.action == action
                and r.input_hash == input_hash
                for r in active
            ):
                deny(
                    "demo_ai_in_flight",
                    "This exact saved input already has an AI request in progress.",
                )
            limit(
                len(active),
                settings.demo_ai_concurrent_global,
                "demo_ai_busy",
                "Shared AI capacity is busy. Wait for the current request to finish.",
            )
            limit(
                sum(r.session_id == owner for r in active),
                settings.demo_ai_concurrent_session,
                "demo_ai_busy",
                "This workspace already has an AI request in progress.",
            )
            if rows and max(r.created_at for r in rows) > now - timedelta(
                seconds=settings.demo_ai_cooldown_seconds
            ):
                deny(
                    "demo_ai_cooldown",
                    "Shared AI cooldown is active. "
                    "Wait before an explicit new request.",
                )
        elif kind == "session":
            limit(
                len(rows),
                settings.demo_max_sessions,
                "demo_session_limit",
                "Shared demo session allowance reached. "
                "New sessions cannot bypass resource limits.",
            )
            limit(
                sum(r.created_at > now - timedelta(hours=1) for r in rows),
                settings.demo_sessions_per_hour,
                "demo_session_limit",
                "Shared hourly demo entry allowance reached.",
            )
        elif kind in {"booking", "source", "write"}:
            global_cap = getattr(
                settings,
                {
                    "booking": "demo_max_bookings",
                    "source": "demo_max_sources",
                    "write": "demo_max_writes",
                }[kind],
            )
            own_cap = getattr(
                settings,
                {
                    "booking": "demo_bookings_per_session",
                    "source": "demo_sources_per_session",
                    "write": "demo_writes_per_session",
                }[kind],
            )
            limit(
                len(rows),
                global_cap,
                "demo_resource_limit",
                f"Shared {kind} allowance reached. "
                "Ask the organiser; changing sessions does not reset it.",
            )
            limit(
                len(own),
                own_cap,
                "demo_resource_limit",
                f"This workspace has reached its {kind} allowance.",
            )
            if kind == "source":
                bytes_limit(
                    sum(r.units for r in rows),
                    settings.demo_source_bytes,
                    "Shared evidence storage allowance reached.",
                )
                bytes_limit(
                    sum(r.units for r in own),
                    settings.demo_source_bytes_per_session,
                    "Workspace evidence storage allowance reached.",
                )
        elif kind == "upload":
            bytes_limit(
                sum(r.units for r in rows),
                settings.demo_upload_bytes,
                "Shared upload allowance reached.",
            )
            bytes_limit(
                sum(r.units for r in own),
                settings.demo_upload_bytes_per_session,
                "Workspace upload allowance reached.",
            )
        else:
            raise ValueError("Unknown admission kind")
        record = Admission(
            session_id=owner,
            booking_id=booking_id,
            kind=kind,
            action=action,
            input_hash=fingerprint(context),
            units=units,
            finished_at=None if kind == "ai" else now,
        )
        db.add(record)
        db.commit()  # Charges survive caller rollback, failure or disconnect.
        return record.id


def run_ai(session, action, context, call, *, booking_id):
    # Conservative reservation: UTF-8 JSON bytes + system/schema overhead + the
    # largest existing provider output cap (16k). No evidence truncation.
    units = len(json.dumps(context, default=str).encode()) + 32768 + 16000
    ident = reserve(session, "ai", action, context, units=units, booking_id=booking_id)
    reason = None
    marker = _admitted.set(ident is not None)
    try:
        return call()
    except HTTPException as error:
        if isinstance(error.detail, dict) and error.detail.get("code") in {
            "ai_rate_limited",
            "ai_credentials_rejected",
        }:
            reason = error.detail["code"]
        raise
    finally:
        _admitted.reset(marker)
        if ident is not None:
            with Session(session.info.get("admission_bind", session.get_bind())) as db:
                db.execute(text("SELECT pg_advisory_xact_lock(18632871, 2)"))
                record = db.get(Admission, ident)
                record.finished_at = db.scalar(select(func.clock_timestamp()))
                if reason:
                    db.get(AdmissionControl, 1).circuit_reason = reason
                db.commit()


def deny_public_payment():
    if get_settings().public_demo_mode:
        raise HTTPException(
            403,
            {
                "code": "public_demo_payment_disabled",
                "message": (
                    "Payments and provider reconciliation are disabled in the "
                    "public demo. Review terms and isolated history only; "
                    "no payment was initiated."
                ),
            },
        )
