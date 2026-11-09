"""Bounded pre-pickup preview. All arithmetic is Decimal and aware UTC datetime."""

import re
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.agreements.schemas import ReviewContent
from app.agreements.service import (
    explicit_instant,
    latest_agreement,
    policy_conflicts,
    review_state,
    scoped_agreement,
)
from app.cancellations.models import CancellationRuleApproval, CancellationRuleVersion
from app.cancellations.schemas import RuleRead, Rules, Target
from app.comparisons.schemas import ProposalContent
from app.comparisons.service import latest_proposal, require_proposal
from app.drafts.corroboration import corroborate_typed
from app.policy_consistency.service import blocking_findings


def source(session, booking_id, target):
    if target.kind == "agreement":
        record = scoped_agreement(session, booking_id, target.id)
        content = ReviewContent.model_validate(record.content)
        claims = {
            key: [e.claim for e in getattr(content.extraction, key)]
            for key in (
                "amounts",
                "currency",
                "pickup",
                "deposit_conditions",
                "cancellation_conditions",
            )
        }
        current = latest_agreement(session, booking_id)
        state = review_state(session, booking_id)
        current_ok = current.id == record.id and state.confirmation_current
    else:
        record = require_proposal(session, booking_id, target.id)
        content = ProposalContent.model_validate(record.content)
        claims = {
            key: getattr(content, key)
            for key in (
                "amounts",
                "currency",
                "pickup",
                "deposit_conditions",
                "cancellation_conditions",
            )
        }
        current_ok = latest_proposal(session, booking_id).id == record.id
    blockers = []
    if record.fingerprint != target.fingerprint:
        blockers.append("source_fingerprint_mismatch")
    if not current_ok:
        blockers.append("source_version_or_confirmation_stale")
    return record, claims, blockers


def latest_rule(session, booking_id, target):
    return session.scalar(
        select(CancellationRuleVersion)
        .where(
            CancellationRuleVersion.booking_id == booking_id,
            CancellationRuleVersion.target_kind == target.kind,
            CancellationRuleVersion.target_id == target.id,
        )
        .order_by(CancellationRuleVersion.version.desc())
        .limit(1)
    )


def scoped_rule(session, booking_id, rule_id):
    record = session.scalar(
        select(CancellationRuleVersion).where(
            CancellationRuleVersion.booking_id == booking_id,
            CancellationRuleVersion.id == rule_id,
        )
    )
    if record is None:
        raise HTTPException(404, "Cancellation rule version not found for this booking")
    return record


def target_of(record):
    return Target(
        kind=record.target_kind,
        id=record.target_id,
        fingerprint=record.target_fingerprint,
    )


def money_context(claims):
    blockers, by_kind = [], {}
    currencies = corroborate_typed("currency", claims["currency"])
    if len(currencies) != 1 or currencies[0].ambiguous or currencies[0].value != "USD":
        blockers.append("explicit_unique_USD_currency_required")
    for claim in corroborate_typed("amounts", claims["amounts"]):
        if (
            claim.ambiguous
            or claim.currency != "USD"
            or claim.amount != claim.amount.quantize(Decimal("0.01"))
        ):
            blockers.append("unsupported_or_ambiguous_amounts_USD_cents_required")
        if claim.kind in by_kind:
            blockers.append("duplicate_amount_kind")
        by_kind[claim.kind] = claim.amount
        if (
            claim.kind not in {"rental_total", "deposit", "total_payable"}
            and claim.amount != 0
        ):
            blockers.append("additional_charges_require_clarification")
    if not {"rental_total", "deposit", "total_payable"} <= set(by_kind):
        blockers.append("explicit_rental_deposit_and_total_required")
    elif by_kind["rental_total"] + by_kind["deposit"] != by_kind["total_payable"]:
        blockers.append("inclusive_total_does_not_equal_rental_plus_deposit")
    return by_kind, blockers


def component_refund(component, base):
    if component.mode == "percent":
        if component.value > 100:
            raise ValueError("Refund percentage exceeds 100")
        amount = base * component.value / Decimal(100)
    else:
        amount = component.value
    if amount > base:
        raise ValueError("Refund exceeds component")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Fractional-cent refund requires a rounding policy")
    return amount.quantize(Decimal("0.01"))


def rule_blockers(rules, claims):
    amounts, blockers = money_context(claims)
    if rules.needs_clarification:
        blockers.append("reviewer_flagged_incomplete_or_conflicting_policy")
    if rules.cutoff_hours <= 0 or rules.cutoff_hours > 87600:
        blockers.append("unsupported_cutoff_hours")
    for category in ("deposit_conditions", "cancellation_conditions"):
        values = claims[category]
        if (
            not values
            or policy_conflicts(values)
            or any(
                c.ambiguous
                or c.value.strip().casefold().rstrip(".")
                in {"unknown", "tbd", "not specified", "n/a"}
                for c in values
            )
        ):
            blockers.append(f"{category}_missing_or_conflicting")
    if not any(
        rules.deposit_clause.strip() and rules.deposit_clause in c.value
        for c in claims["deposit_conditions"]
    ):
        blockers.append("deposit_clause_not_supported_by_source_version")
    nonrefundable = any(
        re.search(r"\b(?:non[- ]?refundable|not refundable)\b", c.value, re.I)
        for c in claims["deposit_conditions"]
    )
    if nonrefundable and any(
        re.search(
            r"\bfull refund\b|\bdeposit (?:is )?(?:refunded|refundable|returned)\b",
            c.value,
            re.I,
        )
        for c in claims["cancellation_conditions"]
    ):
        blockers.append("deposit_cancellation_policy_conflict")
    cutoff = re.escape(format(rules.cutoff_hours.normalize(), "f"))
    hour_pattern = rf"(?<![\d.]){cutoff}\s*(?:hours?|h)\b"
    if not any(
        re.search(hour_pattern, band.clause, re.I) for band in (rules.early, rules.late)
    ):
        blockers.append("cutoff_hours_not_explicit_in_cited_clauses")
    if not rules.early_includes_boundary and re.search(
        rf"at least\s+{hour_pattern}", rules.early.clause, re.I
    ):
        blockers.append("cutoff_boundary_conflicts_with_at_least_clause")
    if rules.early_includes_boundary and re.search(
        rf"more than\s+{hour_pattern}", rules.early.clause, re.I
    ):
        blockers.append("cutoff_boundary_conflicts_with_more_than_clause")
    if not rules.early_includes_boundary and re.search(
        rf"less than\s+{hour_pattern}", rules.late.clause, re.I
    ):
        blockers.append("cutoff_boundary_conflicts_with_less_than_clause")
    for name in ("early", "late"):
        band = getattr(rules, name)
        if not any(
            band.clause.strip() and band.clause in c.value
            for c in claims["cancellation_conditions"]
        ):
            blockers.append(f"{name}_clause_not_supported_by_source_version")
        # A quoted aggregate refund does not establish its component allocation.
        # Recognise only universal full/zero outcomes here; do not derive a split
        # by subtraction or silently rewrite a model's or reviewer's values.
        if (
            re.search(r"\brefund\w*\b", band.clause, re.I)
            and not re.search(r"\b(?:rental|deposit)\b", band.clause, re.I)
            and not re.search(
                r"\b(?:full refund|refunds? (?:the )?full (?:amount|total)"
                r"|no refund)\b",
                band.clause,
                re.I,
            )
        ):
            blockers.append(f"{name}_refund_allocation_requires_clarification")
        if {"rental_total", "deposit"} <= set(amounts):
            try:
                rental = component_refund(band.rental_refund, amounts["rental_total"])
                deposit = component_refund(band.deposit_refund, amounts["deposit"])
                if nonrefundable and deposit > 0:
                    blockers.append(
                        f"{name}_deposit_refund_conflicts_with_nonrefundable_policy"
                    )
                # Direct universal no-refund and full-refund claims must agree
                # with the reviewed split. Conditional natural-language exceptions
                # outside this narrow model require human clarification.
                if re.search(
                    r"\b(?:full refund|refunds? (?:the )?full (?:amount|total))\b",
                    band.clause,
                    re.I,
                ) and rental + deposit != amounts.get("total_payable"):
                    blockers.append(f"{name}_full_refund_clause_conflicts_with_split")
                if (
                    re.search(r"\bno refund\b", band.clause, re.I)
                    and rental + deposit > 0
                ):
                    blockers.append(f"{name}_no_refund_clause_conflicts_with_split")
            except ValueError:
                blockers.append(f"{name}_refund_amount_or_precision_unsupported")
    pickups = corroborate_typed("pickup", claims["pickup"])
    if len(pickups) != 1 or pickups[0].ambiguous:
        blockers.append("explicit_unique_pickup_required")
    else:
        time = pickups[0].value
        try:
            if time.local_datetime is None or time.timezone is None:
                raise ValueError()
            explicit_instant(time)
        except ValueError, OverflowError:
            blockers.append("pickup_timezone_or_datetime_unresolved")
    return sorted(set(blockers))


def read_rule(session, record):
    target = target_of(record)
    _, claims, blockers = source(session, record.booking_id, target)
    rules = Rules.model_validate(record.rules)
    blockers += rule_blockers(rules, claims)
    if target.kind == "proposal":
        blockers += blocking_findings(
            session,
            record.booking_id,
            require_proposal(session, record.booking_id, target.id),
        )
    if latest_rule(session, record.booking_id, target).id != record.id:
        blockers.append("newer_rule_version_requires_review")
    approval = session.scalar(
        select(CancellationRuleApproval).where(
            CancellationRuleApproval.rule_id == record.id
        )
    )
    approved = (
        approval is not None
        and approval.reviewed_fingerprint == record.fingerprint
        and not blockers
    )
    return RuleRead(
        id=record.id,
        booking_id=record.booking_id,
        target=target,
        source_version=record.source_version,
        version=record.version,
        fingerprint=record.fingerprint,
        rules=rules,
        origin=record.origin,
        audit=record.audit,
        model_metadata=record.model_metadata,
        created_at=record.created_at,
        blockers=sorted(set(blockers)),
        approved_current=approved,
        approval={
            "id": str(approval.id),
            "audit": approval.audit,
            "created_at": approval.created_at.isoformat(),
        }
        if approval
        else None,
    )


def preview_one(session, record, cancellation):
    state = read_rule(session, record)
    if not state.approved_current:
        return None, state.blockers + ["reviewed_current_rule_approval_required"]
    _, claims, blockers = source(session, record.booking_id, state.target)
    pickup = explicit_instant(corroborate_typed("pickup", claims["pickup"])[0].value)
    if cancellation >= pickup:
        return None, ["only_pre_pickup_cancellation_supported"]
    rules = state.rules
    delta = pickup - cancellation
    seconds = Decimal(delta.days * 86400 + delta.seconds) + Decimal(
        delta.microseconds
    ) / Decimal(1000000)
    cutoff_seconds = rules.cutoff_hours * Decimal(3600)
    early = seconds > cutoff_seconds or (
        seconds == cutoff_seconds and rules.early_includes_boundary
    )
    band = rules.early if early else rules.late
    amounts, _ = money_context(claims)
    rental = component_refund(band.rental_refund, amounts["rental_total"])
    deposit = component_refund(band.deposit_refund, amounts["deposit"])
    refund = rental + deposit
    retained = amounts["total_payable"] - refund
    boundary = pickup - timedelta(microseconds=int(cutoff_seconds * Decimal(1000000)))
    return {
        "rule_id": str(record.id),
        "rule_fingerprint": record.fingerprint,
        "target": state.target.model_dump(mode="json"),
        "source_version": record.source_version,
        "cancellation_at": cancellation.isoformat(),
        "pickup_at": pickup.isoformat(),
        "cutoff_at": boundary.isoformat(),
        "early_includes_boundary": rules.early_includes_boundary,
        "band": "early" if early else "late",
        "applied_clause": band.clause,
        "deposit_clause": rules.deposit_clause,
        "currency": "USD",
        "rental_refund": str(rental),
        "deposit_refund": str(deposit),
        "refund": str(refund),
        "retained": str(retained),
        "total_payable": str(amounts["total_payable"]),
    }, blockers
