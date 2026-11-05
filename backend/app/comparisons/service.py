import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.agreements.schemas import ReviewContent
from app.agreements.service import (
    explicit_instant,
    latest_agreement,
    policy_conflicts,
    review_state,
)
from app.comparisons.models import ProposalVersion
from app.comparisons.schemas import ComparisonRead, ProposalContent
from app.drafts.schemas import Extraction

POLICIES = {"deposit_conditions", "cancellation_conditions"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def latest_proposal(session, booking_id):
    return session.scalar(
        select(ProposalVersion)
        .where(ProposalVersion.booking_id == booking_id)
        .order_by(ProposalVersion.version.desc())
        .limit(1)
    )


def require_proposal(session, booking_id, proposal_id):
    record = session.scalar(
        select(ProposalVersion).where(
            ProposalVersion.booking_id == booking_id, ProposalVersion.id == proposal_id
        )
    )
    if record is None:
        raise HTTPException(404, "Merchant booking version not found for this booking")
    return record


def normalized(value):
    return " ".join(value.casefold().split())


def canonical(category, claims):
    """Only deterministic typed values; no money arithmetic or inferred terms."""
    values = {}
    for c in claims:
        if c.ambiguous:
            return None
        if category in {"equipment", "included_items"}:
            key, value = normalized(c.name), c.quantity
            if value is None:
                return None
        elif category in {"pickup", "return_time"}:
            if c.value.local_datetime is None or c.value.timezone is None:
                return None
            try:
                key, value = category, explicit_instant(c.value).isoformat()
            except ValueError, OverflowError:
                return None
        elif category == "amounts":
            if c.currency is None:
                return None
            key = c.kind if c.kind != "other" else f"other:{normalized(c.label)}"
            value = (Decimal(c.amount), c.currency)
        else:
            key, value = category, c.value
        # Duplicate identities are ambiguous; never sum quantities or totals.
        if key in values:
            return None
        values[key] = value
    return values


def plan_comparison(agreement_content: dict, proposal_content: dict):
    baseline = ReviewContent.model_validate(agreement_content)
    proposal = ProposalContent.model_validate(proposal_content)
    results, pending = [], []
    for category in Extraction.model_fields:
        left = [e.claim for e in getattr(baseline.extraction, category)]
        right = getattr(proposal, category)
        result = {
            "category": category,
            "status": "needs_clarification",
            "basis": "deterministic",
            "reason": "missing_or_ambiguous_terms",
            "agreement_terms": [c.model_dump(mode="json") for c in left],
            "proposal_terms": [c.model_dump(mode="json") for c in right],
            "agreement_quote": None,
            "proposal_quote": None,
        }
        left_none = (
            category == "included_items"
            and category in baseline.explicit_none_categories
        )
        right_none = category == "included_items" and proposal.included_items_none
        if (left_none and left) or (right_none and right):
            pass
        elif category == "included_items" and left_none and right_none:
            result.update(status="matches", reason="explicitly_no_included_items")
        elif category == "included_items" and (
            (left_none and right) or (right_none and left)
        ):
            result.update(status="differs", reason="included_items_differ")
        elif not left or not right:
            pass
        elif category in POLICIES:
            if (
                policy_conflicts(left)
                or policy_conflicts(right)
                or any(
                    normalized(c.value).rstrip(".")
                    in {
                        "unknown",
                        "tbd",
                        "not specified",
                        "unspecified",
                        "not provided",
                        "to be confirmed",
                        "needs clarification",
                        "n/a",
                    }
                    for c in [*left, *right]
                )
            ):
                result["reason"] = "unresolved_policy"
            elif [c.value for c in left] == [c.value for c in right]:
                result.update(
                    status="matches",
                    reason="identical_policy_text",
                    agreement_quote=left[0].value,
                    proposal_quote=right[0].value,
                )
            else:
                pending.append(
                    {
                        "category": category,
                        "agreement_text": "\n\n".join(c.value for c in left),
                        "proposal_text": "\n\n".join(c.value for c in right),
                    }
                )
        else:
            left_values, right_values = (
                canonical(category, left),
                canonical(category, right),
            )
            if left_values is not None and right_values is not None:
                if category == "amounts" and (set(left_values) != set(right_values)):
                    # A missing stated monetary component is unknown, not zero.
                    result["reason"] = "missing_amount_kind"
                else:
                    result.update(
                        status="matches" if left_values == right_values else "differs",
                        reason="typed_values_equal"
                        if left_values == right_values
                        else "typed_values_differ",
                    )
        results.append(result)
    if sum(len(p["agreement_text"]) + len(p["proposal_text"]) for p in pending) > 40000:
        raise HTTPException(413, "Policy comparison input exceeds 40,000 characters")
    return results, pending


def apply_policies(results, pending, output):
    expected = {p["category"]: p for p in pending}
    seen = set()
    for judgment in output.results:
        item = expected.get(judgment.category)
        if item is None or judgment.category in seen:
            raise ValueError("Invalid policy category coverage")
        seen.add(judgment.category)
        if (
            not judgment.agreement_quote.strip()
            or not judgment.proposal_quote.strip()
            or judgment.agreement_quote not in item["agreement_text"]
            or judgment.proposal_quote not in item["proposal_text"]
        ):
            raise ValueError("Policy quotation is unsupported")
        target = next(r for r in results if r["category"] == judgment.category)
        target.update(
            status=judgment.status,
            basis="gemini_policy",
            reason="policy_meaning_comparison",
            agreement_quote=judgment.agreement_quote,
            proposal_quote=judgment.proposal_quote,
        )
    if seen != set(expected):
        raise ValueError("Missing policy results")


def comparison_read(session, record):
    current = latest_agreement(session, record.booking_id)
    proposal = latest_proposal(session, record.booking_id)
    state = review_state(session, record.booking_id)
    reasons = []
    if (
        current is None
        or current.id != record.agreement_id
        or current.fingerprint != record.agreement_fingerprint
    ):
        reasons.append("agreement_changed")
    if (
        proposal is None
        or proposal.id != record.proposal_id
        or proposal.fingerprint != record.proposal_fingerprint
    ):
        reasons.append("merchant_booking_changed")
    if (
        not state.confirmation_current
        or state.confirmation.id != record.confirmation_id
    ):
        reasons.append("confirmation_no_longer_current")
    fields = {
        name: getattr(record, name)
        for name in ComparisonRead.model_fields
        if name not in {"stale", "stale_reasons"}
    }
    return ComparisonRead(**fields, stale=bool(reasons), stale_reasons=reasons)
