from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.agreements.models import AgreementConfirmation, AgreementVersion
from app.agreements.schemas import (
    AgreementRead,
    ConfirmationCreate,
    ConfirmationRead,
    FromDraft,
    ReviewContent,
    ReviewState,
    RevisionCreate,
)
from app.agreements.service import (
    evidence,
    latest_agreement,
    latest_draft,
    reject,
    require_latest,
    review_state,
    save_version,
    scoped_agreement,
    validate_sources,
)
from app.bookings.router import DatabaseSession, lock_booking
from app.drafts.corroboration import corroborate_review
from app.drafts.schemas import Extraction
from app.drafts.service import validate_and_classify

router = APIRouter(prefix="/api/bookings/{booking_id}", tags=["customer review"])


@router.post("/agreements/from-draft", response_model=AgreementRead, status_code=201)
def begin_review(booking_id: UUID, body: FromDraft, session: DatabaseSession):
    lock_booking(session, booking_id)
    draft = latest_draft(session, booking_id)
    if draft is None or draft.id != body.draft_id:
        reject("latest_booking_draft_required")
    parent = latest_agreement(session, booking_id)
    if parent is not None and parent.draft_id == draft.id:
        reject("draft_already_under_review", agreement_id=str(parent.id))
    snapshots, fingerprints = evidence(session, booking_id)
    selected = [
        source for source in snapshots if source["source_id"] in draft.input_source_ids
    ]
    if {
        source["source_id"]: fingerprints[source["source_id"]] for source in selected
    } != draft.source_fingerprints:
        reject("draft_evidence_changed")
    extraction = Extraction.model_validate(draft.content["extraction"])
    extraction = validate_and_classify(extraction, selected).extraction
    content = ReviewContent(
        extraction={
            category: [
                {"origin": "source_supported", "claim": claim.model_dump()}
                for claim in getattr(extraction, category)
            ]
            for category in Extraction.model_fields
        }
    )
    return save_version(
        session,
        booking_id,
        draft.id,
        parent,
        content,
        fingerprints,
        draft.input_source_ids,
        {
            "kind": "ai_draft_review",
            "customer_label": body.customer_label,
            "identity_provisional": True,
            "changes": [],
        },
    )


@router.get("/agreements", response_model=list[AgreementRead])
def list_agreements(
    booking_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    return list(
        session.scalars(
            select(AgreementVersion)
            .where(AgreementVersion.booking_id == booking_id)
            .order_by(AgreementVersion.version.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/agreements/{agreement_id}", response_model=AgreementRead)
def get_agreement(booking_id: UUID, agreement_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    return scoped_agreement(session, booking_id, agreement_id)


@router.post(
    "/agreements/{agreement_id}/revisions",
    response_model=AgreementRead,
    status_code=201,
)
def revise_agreement(
    booking_id: UUID, agreement_id: UUID, body: RevisionCreate, session: DatabaseSession
):
    lock_booking(session, booking_id)
    parent = require_latest(
        session, booking_id, agreement_id, body.expected_fingerprint
    )
    snapshots, fingerprints = evidence(session, booking_id)
    if {str(value) for value in body.reviewed_source_ids} != set(fingerprints):
        raise HTTPException(422, "Explicitly review every current booking source ID")
    content = ReviewContent.model_validate(parent.content)
    data = content.model_dump(mode="json")
    for change in body.changes:
        data["extraction"][change.category] = [
            {
                "origin": "customer_entered",
                "claim": item.model_dump(mode="json"),
                "reason": change.reason,
            }
            for item in change.items
        ]
        if change.category == "included_items":
            data["explicit_none_categories"] = (
                ["included_items"] if change.explicit_none else []
            )
    revised = corroborate_review(ReviewContent.model_validate(data))
    validate_sources(revised, snapshots)
    return save_version(
        session,
        booking_id,
        parent.draft_id,
        parent,
        revised,
        fingerprints,
        body.reviewed_source_ids,
        {
            "kind": "customer_revision",
            "customer_label": body.customer_label,
            "identity_provisional": True,
            "review_reason": body.review_reason,
            "changes": [change.model_dump(mode="json") for change in body.changes],
        },
    )


@router.post(
    "/agreements/{agreement_id}/confirmations",
    response_model=ConfirmationRead,
    status_code=201,
)
def confirm_agreement(
    booking_id: UUID,
    agreement_id: UUID,
    body: ConfirmationCreate,
    session: DatabaseSession,
    response: Response,
):
    lock_booking(session, booking_id)
    record = require_latest(
        session, booking_id, agreement_id, body.expected_fingerprint
    )
    state = review_state(session, booking_id)
    if state.blockers:
        reject("agreement_not_complete", blockers=state.blockers)
    if state.confirmation is not None:
        if state.confirmation.customer_label != body.customer_label:
            reject("version_already_confirmed")
        response.status_code = 200
        return session.get(AgreementConfirmation, state.confirmation.id)
    confirmation = AgreementConfirmation(
        booking_id=booking_id,
        agreement_id=record.id,
        reviewed_fingerprint=record.fingerprint,
        customer_label=body.customer_label,
        acknowledged=True,
    )
    session.add(confirmation)
    session.commit()
    session.refresh(confirmation)
    return confirmation


@router.get("/review", response_model=ReviewState)
def get_review_state(booking_id: UUID, session: DatabaseSession):
    lock_booking(session, booking_id)
    return review_state(session, booking_id)
