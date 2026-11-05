"""Authoritative checkout eligibility. Caller retains the booking row lock."""

from decimal import Decimal

from sqlalchemy import select

from app.agreements.service import latest_agreement, require_current_confirmation
from app.cancellations.schemas import Target
from app.cancellations.service import component_refund, latest_rule, read_rule
from app.comparisons.models import BookingComparison
from app.comparisons.schemas import ProposalContent
from app.comparisons.service import (
    comparison_read,
    digest,
    latest_proposal,
    plan_comparison,
)
from app.drafts.schemas import Extraction
from app.payments import provider
from app.payments.models import SandboxReceipt
from app.policy_consistency.service import blocking_findings


def policy_contradictions(data):
    import re

    deposit = "\n".join(c.value for c in data.deposit_conditions)
    cancellation = "\n".join(c.value for c in data.cancellation_conditions)
    return bool(
        re.search(r"\b(?:non[- ]?refundable|not refundable)\b", deposit, re.I)
        and re.search(
            r"\bfull refund\b|\bdeposit (?:is )?(?:refunded|refundable|returned)\b",
            cancellation,
            re.I,
        )
    )


def eligibility(session, booking_id):
    # Mandatory existing confirmation guard also takes the common mutation lock.
    confirmation = require_current_confirmation(session, booking_id)
    agreement = latest_agreement(session, booking_id)
    proposal = latest_proposal(session, booking_id)
    blockers = []
    if session.scalar(
        select(SandboxReceipt.id).where(SandboxReceipt.booking_id == booking_id)
    ):
        blockers.append("sandbox_payment_already_completed")
    if proposal is None:
        return None, blockers + ["merchant_booking_required"]
    blockers += blocking_findings(session, booking_id, proposal)
    comparison = session.scalar(
        select(BookingComparison)
        .where(BookingComparison.booking_id == booking_id)
        .order_by(BookingComparison.created_at.desc(), BookingComparison.id.desc())
        .limit(1)
    )
    if comparison is None:
        blockers.append("current_all_matching_comparison_required")
    else:
        state = comparison_read(session, comparison)
        if (
            state.stale
            or state.agreement_id != agreement.id
            or state.proposal_id != proposal.id
        ):
            blockers.append("comparison_stale")
        if (
            len(state.results) != len(Extraction.model_fields)
            or {r.get("category") for r in state.results}
            != set(Extraction.model_fields)
            or any(r.get("status") != "matches" for r in state.results)
        ):
            blockers.append("comparison_has_differences_or_clarification")
    # Recompute numeric checks; never rely solely on stored model judgment.
    deterministic, pending = plan_comparison(agreement.content, proposal.content)
    if any(
        r["status"] != "matches"
        for r in deterministic
        if r["category"] not in {"deposit_conditions", "cancellation_conditions"}
    ):
        blockers.append("deterministic_terms_not_matching")
    parsed = ProposalContent.model_validate(proposal.content)
    if policy_contradictions(parsed):
        blockers.append("inconsistent_deposit_cancellation_policies")
    rules = []
    for kind, record in (("agreement", agreement), ("proposal", proposal)):
        target = Target(kind=kind, id=record.id, fingerprint=record.fingerprint)
        rule = latest_rule(session, booking_id, target)
        if rule is None:
            blockers.append(f"{kind}_reviewed_cancellation_rules_required")
            continue
        reviewed = read_rule(session, rule)
        if not reviewed.approved_current:
            blockers.append(
                f"{kind}_cancellation_rules_unapproved_stale_or_inconsistent"
            )
        rules.append(reviewed)
    amounts = parsed.amounts
    totals = [c for c in amounts if c.kind == "total_payable"]
    amount = None
    if (
        len(totals) != 1
        or totals[0].ambiguous
        or totals[0].currency != "USD"
        or totals[0].amount <= 0
        or totals[0].amount != totals[0].amount.quantize(Decimal("0.01"))
    ):
        blockers.append("explicit_positive_USD_total_payable_required")
    else:
        amount = format(totals[0].amount, ".2f")
    if len(rules) == 2 and all(r.approved_current for r in rules):
        canonical = []
        by_kind = {c.kind: c.amount for c in amounts}
        for rule in rules:
            values = [rule.rules.cutoff_hours, rule.rules.early_includes_boundary]
            for band in (rule.rules.early, rule.rules.late):
                values.extend(
                    [
                        component_refund(band.rental_refund, by_kind["rental_total"]),
                        component_refund(band.deposit_refund, by_kind["deposit"]),
                    ]
                )
            canonical.append(values)
        if canonical[0] != canonical[1]:
            blockers.append("reviewed_cancellation_refunds_differ")
    if blockers:
        return None, sorted(set(blockers))
    context = {
        "environment": "sandbox",
        "merchant_id": provider.get_settings().paypal_sandbox_merchant_id,
        "agreement_id": str(agreement.id),
        "agreement_fingerprint": agreement.fingerprint,
        "agreement_version": agreement.version,
        "confirmation_id": str(confirmation.id),
        "proposal_id": str(proposal.id),
        "proposal_fingerprint": proposal.fingerprint,
        "proposal_version": proposal.version,
        "comparison_id": str(comparison.id),
        "comparison_fingerprint": comparison.fingerprint,
        "cancellation_rules": [
            {
                "id": str(r.id),
                "fingerprint": r.fingerprint,
                "approval_id": r.approval["id"],
            }
            for r in rules
        ],
        "amount": amount,
        "currency": "USD",
    }
    return {"context": context, "fingerprint": digest(context)}, []
