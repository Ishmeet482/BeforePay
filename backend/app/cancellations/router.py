from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.admission.service import run_ai
from app.agreements.service import explicit_instant, reject
from app.bookings.router import DatabaseSession, lock_booking
from app.cancellations.models import CancellationRuleApproval, CancellationRuleVersion
from app.cancellations.provider import GeminiRuleProposer, get_rule_proposer
from app.cancellations.schemas import (
    PreviewCreate,
    PreviewRead,
    RuleConfirm,
    RuleCreate,
    RulePropose,
    RuleRead,
    Rules,
)
from app.cancellations.service import (
    latest_rule,
    preview_one,
    read_rule,
    scoped_rule,
    source,
)
from app.comparisons.service import digest

router = APIRouter(
    prefix="/api/bookings/{booking_id}/cancellation", tags=["cancellation preview"]
)


def check_source(session, booking_id, body):
    lock_booking(session, booking_id)
    record, claims, blockers = source(session, booking_id, body.target)
    if blockers:
        reject("cancellation_source_requires_review", blockers=blockers)
    latest = latest_rule(session, booking_id, body.target)
    if (latest.id if latest else None) != body.expected_latest_rule_id:
        reject("stale_cancellation_rule")
    return record, claims, latest


def persist(
    session, booking_id, body, source_record, latest, rules, origin, metadata=None
):
    record = CancellationRuleVersion(
        id=uuid4(),
        booking_id=booking_id,
        target_kind=body.target.kind,
        target_id=body.target.id,
        target_fingerprint=body.target.fingerprint,
        source_version=source_record.version,
        version=latest.version + 1 if latest else 1,
        rules=rules.model_dump(mode="json"),
        origin=origin,
        model_metadata=metadata,
        audit={
            "customer_label": body.customer_label,
            "identity_provisional": True,
            "reason": getattr(body, "reason", "Explicit AI proposal request"),
            "parent_id": str(latest.id) if latest else None,
        },
    )
    record.fingerprint = digest(
        {
            "id": record.id,
            "booking_id": booking_id,
            "target": body.target.model_dump(mode="json"),
            "version": record.version,
            "rules": record.rules,
            "origin": origin,
            "audit": record.audit,
            "model_metadata": metadata,
        }
    )
    session.add(record)
    session.flush()
    response = read_rule(session, record)
    session.commit()
    return response


@router.post("/rules", response_model=RuleRead, status_code=201)
def save_rules(booking_id: UUID, body: RuleCreate, session: DatabaseSession):
    record, _, latest = check_source(session, booking_id, body)
    return persist(session, booking_id, body, record, latest, body.rules, "human")


@router.post("/rules/propose", response_model=RuleRead, status_code=201)
def propose_rules(
    booking_id: UUID,
    body: RulePropose,
    session: DatabaseSession,
    proposer: Annotated[GeminiRuleProposer, Depends(get_rule_proposer)],
):
    _, claims, _ = check_source(session, booking_id, body)
    payload = {
        category: [c.model_dump(mode="json") for c in values]
        for category, values in claims.items()
        if category in {"deposit_conditions", "cancellation_conditions"}
    }
    if sum(len(c["value"]) for values in payload.values() for c in values) > 20000:
        raise HTTPException(413, "Rule proposal policy input exceeds 20,000 characters")
    session.rollback()
    result = run_ai(
        session,
        "rules",
        {"binding": body.model_dump(mode="json"), "policies": payload},
        lambda: proposer.compare([payload]),
        booking_id=booking_id,
    )
    rules = Rules.model_validate(result.output.model_dump())
    record, _, latest = check_source(session, booking_id, body)
    return persist(
        session, booking_id, body, record, latest, rules, "gemini", result.metadata
    )


@router.get("/rules", response_model=list[RuleRead])
def list_rules(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    records = list(
        session.scalars(
            select(CancellationRuleVersion)
            .where(CancellationRuleVersion.booking_id == booking_id)
            .order_by(
                CancellationRuleVersion.created_at.desc(),
                CancellationRuleVersion.version.desc(),
                CancellationRuleVersion.id,
            )
            .limit(limit)
            .offset(offset)
        )
    )
    return [read_rule(session, record) for record in records]


@router.get("/rules/{rule_id}", response_model=RuleRead)
def get_rule(booking_id: UUID, rule_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    return read_rule(session, scoped_rule(session, booking_id, rule_id))


@router.post("/rules/{rule_id}/confirm", response_model=RuleRead)
def confirm_rules(
    booking_id: UUID, rule_id: UUID, body: RuleConfirm, session: DatabaseSession
):
    lock_booking(session, booking_id)
    record = scoped_rule(session, booking_id, rule_id)
    if record.fingerprint != body.expected_fingerprint:
        reject("stale_cancellation_rule")
    state = read_rule(session, record)
    if state.blockers:
        reject("cancellation_rules_need_clarification", blockers=state.blockers)
    if state.approval is None:
        session.add(
            CancellationRuleApproval(
                booking_id=booking_id,
                rule_id=rule_id,
                reviewed_fingerprint=record.fingerprint,
                audit={**body.model_dump(mode="json"), "identity_provisional": True},
            )
        )
        session.flush()
    response = read_rule(session, record)
    session.commit()
    return response


@router.post("/preview", response_model=PreviewRead)
def preview(booking_id: UUID, body: PreviewCreate, session: DatabaseSession):
    lock_booking(session, booking_id)
    blockers, previews = [], []
    if len(set(body.rule_ids)) != len(body.rule_ids):
        return PreviewRead(
            status="needs_clarification",
            blockers=["distinct_rule_versions_required"],
            cancellation_at=None,
            previews=[],
        )
    if body.cancellation.local_datetime is None or body.cancellation.timezone is None:
        return PreviewRead(
            status="needs_clarification",
            blockers=["explicit_cancellation_datetime_and_timezone_required"],
            cancellation_at=None,
            previews=[],
        )
    try:
        cancellation = explicit_instant(body.cancellation)
    except ValueError, OverflowError:
        return PreviewRead(
            status="needs_clarification",
            blockers=["cancellation_timezone_requires_clarification"],
            cancellation_at=None,
            previews=[],
        )
    records = [scoped_rule(session, booking_id, rule_id) for rule_id in body.rule_ids]
    if len(records) == 2 and {r.target_kind for r in records} != {
        "agreement",
        "proposal",
    }:
        blockers.append("side_by_side_requires_agreement_and_proposal")
    for record in records:
        result, reasons = preview_one(session, record, cancellation)
        blockers.extend(reasons)
        if result:
            previews.append(result)
    # Atomic side-by-side: never show a definite comparison when either is unreviewed.
    return PreviewRead(
        status="needs_clarification" if blockers else "ready",
        blockers=sorted(set(blockers)),
        cancellation_at=cancellation.isoformat(),
        previews=[] if blockers else previews,
    )
