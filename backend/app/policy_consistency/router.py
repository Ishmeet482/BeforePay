from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.admission.service import run_ai
from app.bookings.router import DatabaseSession, lock_booking
from app.comparisons.service import digest, latest_proposal
from app.drafts.provider import provider_error
from app.policy_consistency.models import PolicyConsistencyCheck
from app.policy_consistency.provider import (
    GeminiConsistencyChecker,
    get_consistency_checker,
)
from app.policy_consistency.schemas import CheckCreate, CheckRead, Output
from app.policy_consistency.service import (
    blocking_findings,
    check_read,
    clause_context,
    require_current,
    validate_references,
)

router = APIRouter(
    prefix="/api/bookings/{booking_id}/policy-consistency",
    tags=["merchant policy consistency"],
)


@router.post("", response_model=CheckRead, status_code=201)
def check(
    booking_id: UUID,
    body: CheckCreate,
    session: DatabaseSession,
    checker: Annotated[GeminiConsistencyChecker, Depends(get_consistency_checker)],
):
    proposal = require_current(
        session, booking_id, body.proposal_id, body.proposal_fingerprint
    )
    clauses, complete = clause_context(proposal)
    version = proposal.version
    session.rollback()  # No booking lock across inference.
    metadata = None
    if complete:
        result = run_ai(
            session,
            "consistency",
            {"binding": body.model_dump(mode="json"), "clauses": clauses},
            lambda: checker.check(clauses),
            booking_id=booking_id,
        )
        try:
            output = Output.model_validate(result.output.model_dump())
            validate_references(output, clauses)
        except ValueError as error:
            raise provider_error(
                "ai_invalid_output",
                "Invalid policy consistency findings or clause references.",
            ) from error
        metadata = {
            key: value
            for key, value in result.metadata.items()
            if key
            in {
                "provider",
                "requested_model",
                "response_model",
                "response_id",
                "sdk_version",
                "prompt_version",
            }
        }
    else:
        output = Output(
            findings=[
                {
                    "status": "needs_clarification",
                    "explanation": (
                        "Complete, unambiguous saved deposit and cancellation clauses "
                        "are required. Missing or placeholder terms cannot "
                        "establish consistency."
                    ),
                    "references": [
                        {"clause_id": c["clause_id"], "quotation": c["text"]}
                        for c in clauses
                        if c["text"].strip()
                    ],
                }
            ]
        )
    session.expire_all()
    current = require_current(
        session, booking_id, body.proposal_id, body.proposal_fingerprint
    )
    saved_clauses, _ = clause_context(current)
    if saved_clauses != clauses:
        from app.agreements.service import reject

        reject("policy_consistency_inputs_changed")
    status = (
        "potential_contradiction"
        if any(f.status == "potential_contradiction" for f in output.findings)
        else "needs_clarification"
        if any(f.status == "needs_clarification" for f in output.findings)
        else "no_contradiction_found"
    )
    record = PolicyConsistencyCheck(
        booking_id=booking_id,
        proposal_id=body.proposal_id,
        proposal_fingerprint=body.proposal_fingerprint,
        proposal_version=version,
        status=status,
        output=output.model_dump(mode="json"),
        clauses=clauses,
        model_metadata=metadata,
    )
    record.fingerprint = digest(
        {
            "booking_id": booking_id,
            **body.model_dump(mode="json"),
            "output": record.output,
            "clauses": clauses,
            "model_metadata": metadata,
        }
    )
    session.add(record)
    session.flush()
    response = check_read(session, record)
    session.commit()
    return response


@router.get("", response_model=list[CheckRead])
def history(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    rows = session.scalars(
        select(PolicyConsistencyCheck)
        .where(PolicyConsistencyCheck.booking_id == booking_id)
        .order_by(PolicyConsistencyCheck.created_at.desc(), PolicyConsistencyCheck.id)
        .limit(limit)
        .offset(offset)
    )
    return [check_read(session, row) for row in rows]


@router.get("/state")
def state(booking_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    proposal = latest_proposal(session, booking_id)
    return {
        "proposal_id": proposal.id if proposal else None,
        "proposal_fingerprint": proposal.fingerprint if proposal else None,
        "blockers": blocking_findings(session, booking_id, proposal)
        if proposal
        else [],
    }
