import json

from fastapi import HTTPException
from sqlalchemy import select

from app.agreements.service import reject
from app.bookings.router import lock_booking
from app.comparisons.service import latest_proposal, require_proposal
from app.policy_consistency.models import PolicyConsistencyCheck
from app.policy_consistency.schemas import CheckRead

CATEGORIES = ("deposit_conditions", "cancellation_conditions")


def require_current(session, booking_id, proposal_id, fingerprint):
    lock_booking(session, booking_id)
    proposal = require_proposal(session, booking_id, proposal_id)
    latest = latest_proposal(session, booking_id)
    if latest.id != proposal.id or proposal.fingerprint != fingerprint:
        reject("policy_consistency_proposal_stale")
    return proposal


def clause_context(proposal):
    clauses = [
        {
            "clause_id": f"{category}:{i}",
            "category": category,
            "text": c["value"],
            "ambiguous": c.get("ambiguous", False),
        }
        for category in CATEGORIES
        for i, c in enumerate(proposal.content[category])
    ]
    if len(clauses) > 100 or len(json.dumps(clauses, ensure_ascii=False)) > 40000:
        raise HTTPException(
            413, "Policy consistency context exceeds 100 clauses or 40,000 characters"
        )
    complete = {c["category"] for c in clauses} == set(CATEGORIES) and all(
        not c["ambiguous"]
        and c["text"].strip().casefold().rstrip(".")
        not in {
            "",
            "unknown",
            "tbd",
            "not specified",
            "unspecified",
            "not provided",
            "to be confirmed",
            "needs clarification",
            "n/a",
        }
        for c in clauses
    )
    return clauses, complete


def validate_references(output, clauses):
    available = {c["clause_id"]: c for c in clauses}
    for finding in output.findings:
        seen = set()
        for ref in finding.references:
            clause = available.get(ref.clause_id)
            if (
                clause is None
                or ref.clause_id in seen
                or ref.quotation != clause["text"]
            ):
                raise ValueError("Unsupported or duplicate saved-clause reference")
            seen.add(ref.clause_id)
        if {available[key]["category"] for key in seen} != set(CATEGORIES):
            raise ValueError(
                "Each provider finding needs exact support from both policy groups"
            )
        if finding.status == "no_contradiction_found" and seen != set(available):
            raise ValueError("A clean finding must cover every saved clause")


def blocking_findings(session, booking_id, proposal):
    # A later clean inference cannot silently erase a current unresolved finding.
    exists = session.scalar(
        select(PolicyConsistencyCheck.id)
        .where(
            PolicyConsistencyCheck.booking_id == booking_id,
            PolicyConsistencyCheck.proposal_id == proposal.id,
            PolicyConsistencyCheck.proposal_fingerprint == proposal.fingerprint,
            PolicyConsistencyCheck.status != "no_contradiction_found",
        )
        .limit(1)
    )
    return ["merchant_policy_consistency_requires_clarification"] if exists else []


def check_read(session, record):
    proposal = latest_proposal(session, record.booking_id)
    stale = (
        proposal is None
        or proposal.id != record.proposal_id
        or proposal.fingerprint != record.proposal_fingerprint
    )
    fields = {
        name: getattr(record, name)
        for name in CheckRead.model_fields
        if name not in {"stale", "stale_reasons"}
    }
    return CheckRead(
        **fields,
        stale=stale,
        stale_reasons=["merchant_booking_changed"] if stale else [],
    )
