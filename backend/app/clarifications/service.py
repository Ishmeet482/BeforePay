import json

from fastapi import HTTPException
from sqlalchemy import select

from app.agreements.models import AgreementVersion
from app.agreements.service import reject
from app.bookings.router import lock_booking
from app.clarifications.schemas import SuggestionRead
from app.comparisons.models import BookingComparison, ProposalVersion
from app.comparisons.service import canonical, comparison_read

MAX_CONTEXT = 40000


def scoped_comparison(session, booking_id, comparison_id):
    record = session.scalar(
        select(BookingComparison).where(
            BookingComparison.id == comparison_id,
            BookingComparison.booking_id == booking_id,
        )
    )
    if record is None:
        raise HTTPException(404, "Comparison not found for this booking")
    return record


def stale_reasons(session, comparison):
    reasons = comparison_read(session, comparison).stale_reasons
    latest = session.scalar(
        select(BookingComparison)
        .where(
            BookingComparison.booking_id == comparison.booking_id,
        )
        .order_by(BookingComparison.created_at.desc(), BookingComparison.id)
        .limit(1)
    )
    if latest.id != comparison.id:
        reasons.append("comparison_superseded")
    return reasons


def require_current(session, booking_id, comparison_id, fingerprint):
    lock_booking(session, booking_id)
    comparison = scoped_comparison(session, booking_id, comparison_id)
    if comparison.fingerprint != fingerprint:
        reject("stale_comparison_fingerprint")
    reasons = stale_reasons(session, comparison)
    if reasons:
        reject("clarification_comparison_stale", blockers=reasons)
    return comparison


def term_context(session, comparison, category):
    result = [r for r in comparison.results if r["category"] == category]
    if len(result) != 1 or result[0]["status"] not in {
        "differs",
        "needs_clarification",
    }:
        raise HTTPException(422, "Choose a saved discrepancy, not a matching section")
    agreement = session.get(AgreementVersion, comparison.agreement_id)
    proposal = session.get(ProposalVersion, comparison.proposal_id)
    entries = agreement.content["extraction"][category]
    left = [e["claim"] for e in entries]
    right = proposal.content[category]
    if left != result[0]["agreement_terms"] or right != result[0]["proposal_terms"]:
        reject("comparison_terms_do_not_match_versions")
    terms = []
    for side, claims in (("agreement", left), ("proposal", right)):
        for index, claim in enumerate(claims):
            # Canonical typed fields for non-policy terms; no arithmetic or inference.
            text = (
                claim.get("value")
                if category.endswith("conditions")
                else json.dumps(
                    {
                        k: v
                        for k, v in claim.items()
                        if k not in {"citations", "ambiguous"}
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            terms.append(
                {
                    "term_id": f"{side}:{index}",
                    "side": side,
                    "text": text,
                    "origin": entries[index]["origin"]
                    if side == "agreement"
                    else "merchant_entered",
                    "citations": claim.get("citations", [])
                    if side == "agreement"
                    else [],
                }
            )
    context = {
        "category": category,
        "status": result[0]["status"],
        "reason": result[0]["reason"],
        "terms": terms,
    }
    if len(json.dumps(context, ensure_ascii=False)) > MAX_CONTEXT:
        raise HTTPException(
            413, "Relevant clarification context exceeds 40,000 characters"
        )
    sufficient = bool(left and right) and all(
        not c.get("ambiguous")
        and (
            c.get("quantity") is not None
            if category in {"equipment", "included_items"}
            else bool(c.get("value"))
            if category.endswith("conditions")
            else True
        )
        for c in left + right
    )
    if not category.endswith("conditions"):
        from app.comparisons.schemas import ProposalContent

        parsed = ProposalContent.model_validate(
            {category: [{**c, "citations": []} for c in left]}
        )
        proposed = ProposalContent.model_validate(
            {category: [{**c, "citations": []} for c in right]}
        )
        sufficient = (
            sufficient
            and canonical(category, getattr(parsed, category)) is not None
            and canonical(category, getattr(proposed, category)) is not None
        )
    sufficient = sufficient and result[0]["reason"] not in {
        "unresolved_policy",
        "missing_amount_kind",
        "missing_or_ambiguous_terms",
    }
    return context, sufficient


def validate_references(output, terms):
    available = {t["term_id"]: t for t in terms}
    seen, resolved = set(), []
    for ref in output.references:
        term = available.get(ref.term_id)
        if term is None or ref.term_id in seen or ref.quotation != term["text"]:
            raise ValueError("Unsupported saved-term reference")
        seen.add(ref.term_id)
        resolved.append(term)
    if output.status == "suggested" and {t["side"] for t in resolved} != {
        "agreement",
        "proposal",
    }:
        raise ValueError("Both saved sides must support the suggestion")
    return resolved


def suggestion_read(session, record):
    comparison = scoped_comparison(session, record.booking_id, record.comparison_id)
    reasons = stale_reasons(session, comparison)
    if comparison.fingerprint != record.comparison_fingerprint:
        reasons.append("comparison_changed")
    fields = {
        name: getattr(record, name)
        for name in SuggestionRead.model_fields
        if name not in {"stale", "stale_reasons"}
    }
    return SuggestionRead(**fields, stale=bool(reasons), stale_reasons=reasons)
