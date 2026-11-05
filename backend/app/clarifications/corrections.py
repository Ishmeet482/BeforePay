"""Human review of exact saved corrections; no provider or checkout dependency."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.agreements.models import AgreementVersion
from app.agreements.service import reject
from app.bookings.router import DatabaseSession, lock_booking
from app.clarifications.correction_schemas import (
    CorrectionCreate,
    CorrectionRead,
    ReviewBindings,
)
from app.clarifications.models import (
    ClarificationSuggestion,
    CorrectionReview,
    MerchantReply,
)
from app.clarifications.replies import reply_read
from app.clarifications.service import scoped_comparison, stale_reasons, term_context
from app.comparisons.models import BookingComparison
from app.comparisons.schemas import PolicyOutput, ProposalRead
from app.comparisons.service import (
    apply_policies,
    comparison_read,
    digest,
    plan_comparison,
    require_proposal,
)
from app.drafts.schemas import Extraction

router = APIRouter(
    prefix="/api/bookings/{booking_id}/clarifications/{suggestion_id}",
    tags=["provisional correction reviews"],
)


def question_for(session, booking_id, suggestion_id):
    question = session.scalar(
        select(ClarificationSuggestion).where(
            ClarificationSuggestion.id == suggestion_id,
            ClarificationSuggestion.booking_id == booking_id,
        )
    )
    if question is None:
        raise HTTPException(404, "Clarification not found for this booking")
    return question


def review_context(session, booking_id, question, reply_id=None):
    """Only persisted versions and results; never derive meaning from reply text."""
    original = scoped_comparison(session, booking_id, question.comparison_id)
    agreement = session.get(AgreementVersion, question.agreement_id)
    old_proposal = require_proposal(session, booking_id, question.proposal_id)
    if (
        agreement is None
        or agreement.booking_id != booking_id
        or original.fingerprint != question.comparison_fingerprint
        or original.agreement_id != question.agreement_id
        or original.agreement_fingerprint != question.agreement_fingerprint
        or agreement.fingerprint != question.agreement_fingerprint
        or original.confirmation_id != question.confirmation_id
        or original.proposal_id != question.proposal_id
        or original.proposal_fingerprint != question.proposal_fingerprint
        or old_proposal.fingerprint != question.proposal_fingerprint
    ):
        reject("correction_original_bindings_invalid")
    # Confirms the original category is a real discrepancy with exact version terms.
    term_context(session, original, question.category)
    blockers = []
    if question.output.get("status") != "suggested" or not question.output.get(
        "question"
    ):
        blockers.append("saved_clarification_question_required")
    replies = list(
        session.scalars(
            select(MerchantReply)
            .where(
                MerchantReply.booking_id == booking_id,
                MerchantReply.suggestion_id == question.id,
            )
            .order_by(MerchantReply.created_at.desc(), MerchantReply.id)
        )
    )
    selected = (
        next((r for r in replies if r.id == reply_id), None)
        if reply_id
        else replies[0]
        if len(replies) == 1
        else None
    )
    if reply_id and selected is None:
        raise HTTPException(404, "Reply not found for this clarification")
    if selected is None:
        blockers.append(
            "select_one_saved_merchant_reply"
            if replies
            else "saved_merchant_reply_required"
        )
    elif any(
        (
            selected.suggestion_fingerprint != question.fingerprint,
            selected.comparison_id != original.id,
            selected.comparison_fingerprint != original.fingerprint,
            selected.proposal_id != old_proposal.id,
            selected.proposal_fingerprint != old_proposal.fingerprint,
        )
    ):
        reject("correction_reply_bindings_invalid")
    current = session.scalar(
        select(BookingComparison)
        .where(BookingComparison.booking_id == booking_id)
        .order_by(BookingComparison.created_at.desc(), BookingComparison.id)
        .limit(1)
    )
    proposal = (
        require_proposal(session, booking_id, current.proposal_id) if current else None
    )
    if current is None:
        blockers.append("fresh_saved_comparison_required")
    else:
        blockers.extend(stale_reasons(session, current))
        if current.id == original.id or proposal.version <= old_proposal.version:
            blockers.append("newer_merchant_proposal_and_comparison_required")
        if proposal.content[question.category] == old_proposal.content[
            question.category
        ] and (
            question.category != "included_items"
            or proposal.content.get("included_items_none")
            == old_proposal.content.get("included_items_none")
        ):
            blockers.append("affected_proposal_terms_unchanged")
        if (
            current.agreement_id != question.agreement_id
            or current.agreement_fingerprint != question.agreement_fingerprint
            or current.confirmation_id != question.confirmation_id
        ):
            blockers.append("unchanged_buyer_baseline_and_confirmation_required")
        if proposal.fingerprint != current.proposal_fingerprint:
            blockers.append("corrected_proposal_binding_invalid")
        # Validate coverage, exact terms and deterministic completeness even if a
        # stored result were malformed. Policy meaning uses existing saved judgment.
        categories = set(Extraction.model_fields)
        rows = current.results
        if (
            len(rows) != len(categories)
            or {r.get("category") for r in rows} != categories
            or any(r.get("status") != "matches" for r in rows)
        ):
            blockers.append("all_comparison_terms_must_match")
        expected, pending = plan_comparison(agreement.content, proposal.content)
        by_category = {r.get("category"): r for r in rows}
        for row in expected:
            saved = by_category.get(row["category"], {})
            if (
                saved.get("agreement_terms") != row["agreement_terms"]
                or saved.get("proposal_terms") != row["proposal_terms"]
            ):
                blockers.append("comparison_terms_do_not_match_versions")
        if pending:
            try:
                output = PolicyOutput(
                    results=[
                        {
                            "category": p["category"],
                            "status": by_category[p["category"]]["status"],
                            "agreement_quote": by_category[p["category"]].get(
                                "agreement_quote"
                            ),
                            "proposal_quote": by_category[p["category"]].get(
                                "proposal_quote"
                            ),
                        }
                        for p in pending
                    ]
                )
                if any(
                    by_category[p["category"]].get("basis") != "gemini_policy"
                    for p in pending
                ):
                    raise ValueError("Saved policy judgment required")
                apply_policies(expected, pending, output)
            except ValueError, KeyError:
                blockers.append("supported_saved_policy_comparison_required")
        if any(r["status"] != "matches" for r in expected):
            blockers.append("missing_ambiguous_or_differing_terms")
    bindings = None
    if current and selected:
        bindings = ReviewBindings(
            suggestion_id=question.id,
            suggestion_fingerprint=question.fingerprint,
            original_comparison_id=original.id,
            original_comparison_fingerprint=original.fingerprint,
            agreement_id=question.agreement_id,
            agreement_fingerprint=question.agreement_fingerprint,
            confirmation_id=question.confirmation_id,
            original_proposal_id=old_proposal.id,
            original_proposal_fingerprint=old_proposal.fingerprint,
            proposal_id=proposal.id,
            proposal_fingerprint=proposal.fingerprint,
            comparison_id=current.id,
            comparison_fingerprint=current.fingerprint,
            reply_id=selected.id,
            reply_fingerprint=selected.fingerprint,
        ).model_dump(mode="json")
    return {
        "eligible": not blockers,
        "blockers": sorted(set(blockers)),
        "bindings": bindings,
        "context_fingerprint": digest(bindings) if bindings else None,
        "category": question.category,
        "original": {
            "question": question.output,
            "supporting_terms": question.supporting_terms,
            "comparison": comparison_read(session, original).model_dump(mode="json"),
            "proposal_version": old_proposal.version,
        },
        "replies": [
            reply_read(session, r, question).model_dump(mode="json") for r in replies
        ],
        "selected_reply_id": str(selected.id) if selected else None,
        "corrected_proposal": ProposalRead.model_validate(proposal).model_dump(
            mode="json"
        )
        if proposal
        else None,
        "comparison": comparison_read(session, current).model_dump(mode="json")
        if current
        else None,
    }


def read_review(session, record):
    bindings = record.context["bindings"]
    current = scoped_comparison(session, record.booking_id, record.comparison_id)
    reasons = stale_reasons(session, current)
    if current.fingerprint != bindings["comparison_fingerprint"]:
        reasons.append("comparison_fingerprint_changed")
    return CorrectionRead(
        **{
            name: getattr(record, name)
            for name in CorrectionRead.model_fields
            if name not in {"stale", "stale_reasons"}
        },
        stale=bool(reasons),
        stale_reasons=reasons,
    )


@router.get("/correction")
def get_context(
    booking_id: UUID,
    suggestion_id: UUID,
    session: DatabaseSession,
    reply_id: UUID | None = None,
):
    lock_booking(session, booking_id)
    return review_context(
        session, booking_id, question_for(session, booking_id, suggestion_id), reply_id
    )


@router.post("/correction-reviews", response_model=CorrectionRead, status_code=201)
def record_review(
    booking_id: UUID,
    suggestion_id: UUID,
    body: CorrectionCreate,
    session: DatabaseSession,
):
    lock_booking(session, booking_id)
    question = question_for(session, booking_id, suggestion_id)
    context = review_context(session, booking_id, question, body.bindings.reply_id)
    if not context["eligible"]:
        reject("correction_review_blocked", blockers=context["blockers"])
    if (
        context["bindings"] != body.bindings.model_dump(mode="json")
        or context["context_fingerprint"] != body.context_fingerprint
    ):
        reject("correction_review_context_changed")
    existing = session.scalar(
        select(CorrectionReview).where(
            CorrectionReview.suggestion_id == suggestion_id,
            CorrectionReview.comparison_id == body.bindings.comparison_id,
        )
    )
    # Exact transport retry reuses the statement only after current-version checks.
    # Changed note/label/bindings cannot overwrite or silently reuse that statement.
    if existing:
        if (
            existing.context["bindings"] != body.bindings.model_dump(mode="json")
            or existing.context_fingerprint != body.context_fingerprint
            or existing.reviewer_label != body.reviewer_label
            or existing.note != body.note
        ):
            reject("correction_already_reviewed_for_comparison")
        return read_review(session, existing)
    record = CorrectionReview(
        booking_id=booking_id,
        suggestion_id=suggestion_id,
        reply_id=body.bindings.reply_id,
        comparison_id=body.bindings.comparison_id,
        agreement_id=body.bindings.agreement_id,
        confirmation_id=body.bindings.confirmation_id,
        original_proposal_id=body.bindings.original_proposal_id,
        proposal_id=body.bindings.proposal_id,
        context_fingerprint=context["context_fingerprint"],
        context=context,
        reviewer_label=body.reviewer_label,
        note=body.note,
        identity_provisional=True,
    )
    record.fingerprint = digest(
        {"booking_id": booking_id, **body.model_dump(mode="json")}
    )
    session.add(record)
    session.flush()
    response = read_review(session, record)
    session.commit()
    return response


@router.get("/correction-reviews", response_model=list[CorrectionRead])
def list_reviews(
    booking_id: UUID,
    suggestion_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    lock_booking(session, booking_id)
    question_for(session, booking_id, suggestion_id)
    rows = session.scalars(
        select(CorrectionReview)
        .where(
            CorrectionReview.booking_id == booking_id,
            CorrectionReview.suggestion_id == suggestion_id,
        )
        .order_by(CorrectionReview.created_at.desc(), CorrectionReview.id)
        .limit(limit)
        .offset(offset)
    )
    return [read_review(session, r) for r in rows]
