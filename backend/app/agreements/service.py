import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agreements.models import AgreementConfirmation, AgreementVersion
from app.agreements.schemas import ReviewContent, ReviewState
from app.bookings.router import lock_booking
from app.drafts.models import DraftVersion
from app.drafts.schemas import Extraction
from app.drafts.service import (
    fingerprint,
    policy_conflicts,
    source_snapshot,
    validate_and_classify,
)
from app.evidence.models import EvidenceSource


def reject(code: str, **details):
    raise HTTPException(409, {"code": code, **details})


def latest_draft(session, booking_id):
    return session.scalar(
        select(DraftVersion)
        .where(DraftVersion.booking_id == booking_id)
        .order_by(DraftVersion.version.desc())
        .limit(1)
    )


def latest_agreement(session, booking_id):
    return session.scalar(
        select(AgreementVersion)
        .where(AgreementVersion.booking_id == booking_id)
        .order_by(AgreementVersion.version.desc())
        .limit(1)
    )


def evidence(session, booking_id):
    records = session.scalars(
        select(EvidenceSource)
        .where(EvidenceSource.booking_id == booking_id)
        .options(selectinload(EvidenceSource.pages))
        .order_by(EvidenceSource.id)
    )
    snapshots = [source_snapshot(source) for source in records]
    return snapshots, {source["source_id"]: fingerprint(source) for source in snapshots}


def scoped_agreement(session, booking_id, agreement_id):
    record = session.scalar(
        select(AgreementVersion).where(
            AgreementVersion.id == agreement_id,
            AgreementVersion.booking_id == booking_id,
        )
    )
    if record is None:
        raise HTTPException(404, "Agreement version not found for this booking")
    return record


def require_latest(session, booking_id, agreement_id, expected_fingerprint):
    record = scoped_agreement(session, booking_id, agreement_id)
    current = latest_agreement(session, booking_id)
    if current.id != record.id or record.fingerprint != expected_fingerprint:
        reject("stale_agreement")
    draft = latest_draft(session, booking_id)
    if draft is None or draft.id != record.draft_id:
        reject("newer_ai_draft_requires_review")
    return record


def validate_sources(content: ReviewContent, snapshots):
    source_claims = {
        category: [
            entry.claim.model_dump()
            for entry in getattr(content.extraction, category)
            if entry.origin == "source_supported"
        ]
        for category in Extraction.model_fields
    }
    # Original Gemini/Pydantic/citation/financial support validation is unchanged.
    validate_and_classify(Extraction.model_validate(source_claims), snapshots)


def explicit_instant(value):
    local = datetime.fromisoformat(value.local_datetime)
    zone = value.timezone
    if zone.startswith(("+", "-")):
        hours, minutes = map(int, zone[1:].split(":"))
        offset = timedelta(hours=hours, minutes=minutes) * (1 if zone[0] == "+" else -1)
        return local.replace(tzinfo=timezone(offset)).astimezone(UTC)
    tz = ZoneInfo(zone)
    possibilities = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=tz, fold=fold).astimezone(UTC)
        if instant.astimezone(tz).replace(tzinfo=None) == local:
            possibilities.add(instant)
    if len(possibilities) != 1:
        raise ValueError(
            "Ambiguous or nonexistent local time requires explicit UTC offset"
        )
    return possibilities.pop()


def content_blockers(content: ReviewContent) -> list[str]:
    blockers = []
    for category in Extraction.model_fields:
        entries = getattr(content.extraction, category)
        claims = [entry.claim for entry in entries]
        if not claims:
            if category not in content.explicit_none_categories:
                blockers.append(f"{category}_missing")
            continue
        unclear = any(claim.ambiguous for claim in claims)
        if category in {"deposit_conditions", "cancellation_conditions"}:
            unclear |= policy_conflicts(claims)
            unclear |= any(
                " ".join(claim.value.casefold().split()).rstrip(".")
                in {
                    "unknown",
                    "tbd",
                    "not specified",
                    "unspecified",
                    "not provided",
                    "to be confirmed",
                    "needs clarification",
                    "n/a",
                    "none",
                }
                for claim in claims
            )
        groups = defaultdict(set)
        for claim in claims:
            if category in {"equipment", "included_items"}:
                key, value = claim.name.strip().casefold(), claim.quantity
                unclear |= value is None
            elif category in {"pickup", "return_time"}:
                key, value = (
                    category,
                    (claim.value.local_datetime, claim.value.timezone),
                )
                unclear |= None in value
            elif category == "amounts":
                key = (
                    claim.kind
                    if claim.kind != "other"
                    else (claim.kind, claim.label.strip().casefold())
                )
                value = (claim.amount, claim.currency)
                unclear |= claim.currency is None
            elif category in {"deposit_conditions", "cancellation_conditions"}:
                key, value = claim.value, claim.value
            else:
                key, value = category, claim.value
            groups[key].add(value)
        unclear |= any(len(values) != 1 for values in groups.values())
        if unclear:
            blockers.append(f"{category}_unresolved")
    # An inclusive total_payable does not replace the required rental fee or
    # participate as an extra charge. Compare alternatives within each kind
    # above; no unsupported arithmetic or inferred component inclusion here.
    totals = [
        entry.claim
        for entry in content.extraction.amounts
        if entry.claim.kind == "rental_total"
    ]
    if not totals:
        blockers.append("rental_total_missing")
    currencies = {entry.claim.value for entry in content.extraction.currency}
    currencies.update(
        entry.claim.currency
        for entry in content.extraction.amounts
        if entry.claim.currency
    )
    if len(currencies) > 1:
        blockers.append("currency_mismatch")
    if not any(code.startswith(("pickup_", "return_time_")) for code in blockers):
        try:
            pickup = explicit_instant(content.extraction.pickup[0].claim.value)
            returned = explicit_instant(content.extraction.return_time[0].claim.value)
            if returned <= pickup:
                blockers.append("return_must_follow_pickup")
        except ValueError, OverflowError:
            blockers.append("rental_time_requires_clarification")
    return blockers


def save_version(
    session, booking_id, draft_id, parent, content, fingerprints, reviewed_ids, audit
):
    record = AgreementVersion(
        id=uuid4(),
        booking_id=booking_id,
        draft_id=draft_id,
        parent_id=parent.id if parent else None,
        version=parent.version + 1 if parent else 1,
        content=content.model_dump(mode="json"),
        evidence_fingerprints=fingerprints,
        reviewed_source_ids=sorted(str(value) for value in reviewed_ids),
        audit=audit,
    )
    payload = {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in {
            "id": record.id,
            "booking_id": booking_id,
            "draft_id": draft_id,
            "parent_id": record.parent_id,
            "version": record.version,
            "content": record.content,
            "evidence_fingerprints": fingerprints,
            "reviewed_source_ids": record.reviewed_source_ids,
            "audit": audit,
        }.items()
    }
    record.fingerprint = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def review_state(session: Session, booking_id: UUID) -> ReviewState:
    # Caller holds the booking lock throughout this snapshot/decision.
    snapshots, fingerprints = evidence(session, booking_id)
    record, draft = (
        latest_agreement(session, booking_id),
        latest_draft(session, booking_id),
    )
    if record is None:
        return ReviewState(
            agreement_id=None,
            fingerprint=None,
            source_ids=list(fingerprints),
            latest_draft_id=draft.id if draft else None,
            blockers=["agreement_missing"],
            confirmation=None,
            confirmation_current=False,
            requires_review=True,
        )
    content = ReviewContent.model_validate(record.content)
    blockers = content_blockers(content)
    if record.evidence_fingerprints != fingerprints:
        blockers.append("evidence_changed_requires_review")
    if set(record.reviewed_source_ids) != set(fingerprints):
        blockers.append("unreviewed_evidence")
    if draft is None or record.draft_id != draft.id:
        blockers.append("newer_ai_draft_requires_review")
    validate_sources(content, snapshots)
    confirmation = session.scalar(
        select(AgreementConfirmation).where(
            AgreementConfirmation.agreement_id == record.id
        )
    )
    current = (
        confirmation is not None
        and not blockers
        and confirmation.reviewed_fingerprint == record.fingerprint
    )
    return ReviewState(
        agreement_id=record.id,
        fingerprint=record.fingerprint,
        source_ids=list(fingerprints),
        latest_draft_id=draft.id if draft else None,
        blockers=blockers,
        confirmation=confirmation,
        confirmation_current=current,
        requires_review=not current,
    )


def require_current_confirmation(
    session: Session, booking_id: UUID
) -> AgreementConfirmation:
    """Future payment code must call this in its own locked transaction.

    This verifies review only, not comparison, payment authorization or capture.
    The caller must retain the booking lock until its protected state change.
    """
    lock_booking(session, booking_id)
    state = review_state(session, booking_id)
    if not state.confirmation_current:
        reject("current_confirmation_required", blockers=state.blockers)
    return session.get(AgreementConfirmation, state.confirmation.id)
