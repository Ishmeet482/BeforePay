from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import pytest
from google.genai import types
from pydantic import SecretStr
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_booking_comparisons import content, save
from test_customer_review import confirm, revise, seed_review, state

from app.cancellations.models import CancellationRuleApproval, CancellationRuleVersion
from app.cancellations.provider import get_rule_proposer
from app.cancellations.schemas import Rules
from app.comparisons.provider import PolicyResult
from app.core.config import Settings
from app.drafts import provider as gemini
from app.main import app

EARLY = "Cancellation at least 48 hours before pickup gives a full refund of USD 200."
LATE = (
    "Cancellation less than 48 hours before pickup refunds the deposit USD 80 "
    "and retains the rental fee USD 120."
)
DEPOSIT = (
    "The USD 80 deposit is refunded on cancellation "
    "according to the cancellation clauses."
)


@pytest.fixture
def context(api, postgres_engine):
    ctx = seed_review(api, postgres_engine)
    amounts = [
        {
            "kind": kind,
            "label": kind,
            "amount": amount,
            "currency": "USD",
            "ambiguous": False,
        }
        for kind, amount in [
            ("rental_total", "120.00"),
            ("deposit", "80.00"),
            ("total_payable", "200.00"),
        ]
    ]
    changes = [
        {"category": "amounts", "reason": "Explicit component split", "items": amounts},
        {
            "category": "deposit_conditions",
            "reason": "Reviewed deposit rule",
            "items": [{"value": DEPOSIT, "ambiguous": False}],
        },
        {
            "category": "cancellation_conditions",
            "reason": "Reviewed both cutoff clauses",
            "items": [{"value": v, "ambiguous": False} for v in (EARLY, LATE)],
        },
    ]
    agreement = revise(api, ctx, changes).json()
    assert confirm(api, ctx, agreement).status_code == 201
    return {**ctx, "agreement": agreement}


def rules():
    def band(rental, deposit, clause):
        return {
            "rental_refund": {"mode": "percent", "value": rental},
            "deposit_refund": {"mode": "percent", "value": deposit},
            "clause": clause,
        }

    return {
        "cutoff_hours": "48",
        "early_includes_boundary": True,
        "early": band("100", "100", EARLY),
        "late": band("0", "100", LATE),
        "deposit_clause": DEPOSIT,
        "needs_clarification": False,
        "clarification_note": "",
    }


def target(context, proposal=None):
    source = proposal or context["agreement"]
    return {
        "kind": "proposal" if proposal else "agreement",
        "id": source["id"],
        "fingerprint": source["fingerprint"],
    }


def create(api, context, data=None, proposal=None, expected=None):
    return api.post(
        f"/api/bookings/{context['booking']}/cancellation/rules",
        json={
            "target": target(context, proposal),
            "expected_latest_rule_id": expected,
            "customer_label": "Reviewer",
            "reason": "Reviewed complete pre-pickup policy",
            "rules": data or rules(),
        },
    )


def approve(api, context, record, **overrides):
    return api.post(
        f"/api/bookings/{context['booking']}/cancellation/rules/{record['id']}/confirm",
        json={
            "customer_label": "Reviewer",
            "expected_fingerprint": record["fingerprint"],
            "acknowledged": True,
            "complete_pre_pickup_policy": True,
            "no_unresolved_contradictions": True,
            "review_note": "Both policies and boundaries checked",
            **overrides,
        },
    )


def preview(api, context, records, local="2026-10-30T09:00:00", zone="UTC"):
    return api.post(
        f"/api/bookings/{context['booking']}/cancellation/preview",
        json={
            "rule_ids": [r["id"] for r in records],
            "cancellation": {"local_datetime": local, "timezone": zone},
        },
    )


@pytest.mark.parametrize(
    "when,refund,retained,band",
    [
        ("2026-10-30T08:59:59.999999", "200.00", "0.00", "early"),
        ("2026-10-30T09:00:00", "200.00", "0.00", "early"),
        ("2026-10-30T09:00:00.000001", "80.00", "120.00", "late"),
    ],
)
def test_exact_boundary_and_either_side(api, context, when, refund, retained, band):
    original = state(api, context)
    record = create(api, context).json()
    assert record["blockers"] == []
    assert not record["approved_current"]
    assert approve(api, context, record).json()["approved_current"]
    response = preview(api, context, [record], when)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready"
    p = result["previews"][0]
    assert (p["refund"], p["retained"], p["band"]) == (refund, retained, band)
    assert p["total_payable"] == "200.00"  # never add total to its components
    assert p["applied_clause"] == (EARLY if band == "early" else LATE)
    assert (
        p["target"] == target(context)
        and p["source_version"] == context["agreement"]["version"]
    )
    assert state(api, context) == original


@pytest.mark.parametrize(
    "zone,local",
    [("+05:30", "2026-10-30T14:30:00"), ("Asia/Kolkata", "2026-10-30T14:30:00")],
)
def test_timezone_equivalence(api, context, zone, local):
    record = create(api, context).json()
    approve(api, context, record)
    result = preview(api, context, [record], local, zone).json()
    assert result["previews"][0]["refund"] == "200.00"
    assert result["cancellation_at"] == "2026-10-30T09:00:00+00:00"


def test_unapproved_and_incomplete_rules_never_calculate(api, context):
    record = create(api, context).json()
    assert preview(api, context, [record]).json()["previews"] == []
    data = rules()
    data["needs_clarification"] = True
    next_rule = create(api, context, data, expected=record["id"]).json()
    assert approve(api, context, next_rule).status_code == 409
    assert preview(api, context, [next_rule]).json()["status"] == "needs_clarification"


@pytest.mark.parametrize("when", ["2026-11-01T09:00:00", "2026-11-01T09:00:01"])
def test_only_pre_pickup_supported(api, context, when):
    record = create(api, context).json()
    approve(api, context, record)
    result = preview(api, context, [record], when).json()
    assert result["previews"] == [] and result["status"] == "needs_clarification"
    assert "only_pre_pickup_cancellation_supported" in result["blockers"]


def test_dst_ambiguous_cancellation_requires_clarification(api, context):
    record = create(api, context).json()
    approve(api, context, record)
    result = preview(
        api, context, [record], "2026-11-01T01:30:00", "America/New_York"
    ).json()
    assert (
        result["previews"] == []
        and "cancellation_timezone_requires_clarification" in result["blockers"]
    )


@pytest.mark.parametrize("change", ["evidence", "agreement", "rules"])
def test_stale_approvals_cannot_calculate(api, context, change):
    record = create(api, context).json()
    approve(api, context, record)
    if change == "evidence":
        api.post(
            f"/api/bookings/{context['booking']}/sources/text",
            json={"source_type": "message", "original_text": "New relevant evidence"},
        )
    elif change == "agreement":
        assert revise(api, context).status_code == 201
    else:
        assert create(api, context, expected=record["id"]).status_code == 201
    result = preview(api, context, [record]).json()
    assert result["status"] == "needs_clarification" and result["previews"] == []


def test_proposal_changes_stale_rules_without_altering_agreement_confirmation(
    api, context
):
    original = state(api, context)
    proposal = save(api, context).json()
    record = create(api, context, proposal=proposal).json()
    approve(api, context, record)
    assert save(api, context, expected=proposal["id"]).status_code == 201
    assert not api.get(
        f"/api/bookings/{context['booking']}/cancellation/rules/{record['id']}"
    ).json()["approved_current"]
    assert state(api, context) == original
    assert preview(api, context, [record]).json()["previews"] == []


def test_side_by_side_requires_both_reviewed(api, context):
    proposal = save(api, context).json()
    left = create(api, context).json()
    right = create(api, context, proposal=proposal).json()
    approve(api, context, left)
    assert preview(api, context, [left, right]).json()["previews"] == []
    approve(api, context, right)
    assert len(preview(api, context, [left, right]).json()["previews"]) == 2


def test_contradictory_nonrefundable_deposit_blocks_despite_human_ack(api, context):
    data = content(context)
    data["deposit_conditions"][0]["value"] = "The USD 80 deposit is non-refundable."
    proposal = save(api, context, data).json()
    r = rules()
    r["deposit_clause"] = data["deposit_conditions"][0]["value"]
    record = create(api, context, r, proposal).json()
    assert "deposit_cancellation_policy_conflict" in record["blockers"]
    assert approve(api, context, record).status_code == 409
    assert preview(api, context, [record]).json()["previews"] == []


def test_consistent_nonrefundable_proposal_can_have_reviewed_rules(api, context):
    data = content(context)
    dep = "The USD 80 deposit is non-refundable."
    early = (
        "Cancellation at least 48 hours before pickup refunds rental fee "
        "USD 120 only; deposit USD 80 is retained."
    )
    late = (
        "Cancellation less than 48 hours before pickup retains rental fee "
        "USD 120 and deposit USD 80; refund USD 0."
    )
    data["deposit_conditions"][0]["value"] = dep
    data["cancellation_conditions"] = [
        {"value": v, "ambiguous": False} for v in (early, late)
    ]
    proposal = save(api, context, data).json()
    r = rules()
    r["deposit_clause"] = dep
    r["early"]["clause"] = early
    r["late"]["clause"] = late
    r["early"]["deposit_refund"]["value"] = r["late"]["deposit_refund"]["value"] = "0"
    record = create(api, context, r, proposal).json()
    assert record["blockers"] == []
    assert approve(api, context, record).json()["approved_current"]
    assert preview(api, context, [record]).json()["previews"][0]["refund"] == "120.00"


@pytest.mark.parametrize(
    "case",
    ["quote", "cutoff", "boundary", "over_percent", "over_amount", "fractional_cent"],
)
def test_unsupported_rules_block_approval(api, context, case):
    r = rules()
    if case == "quote":
        r["early"]["clause"] = "Invented clause"
    elif case == "cutoff":
        r["cutoff_hours"] = "24"
    elif case == "boundary":
        r["early_includes_boundary"] = False
    elif case == "over_percent":
        r["early"]["deposit_refund"]["value"] = "101"
    elif case == "over_amount":
        r["early"]["deposit_refund"] = {"mode": "amount", "value": "81"}
    else:
        r["late"]["rental_refund"] = {"mode": "amount", "value": "0.001"}
    record = create(api, context, r).json()
    assert record["blockers"] and approve(api, context, record).status_code == 409
    assert preview(api, context, [record]).json()["previews"] == []


def test_explicit_amount_refunds(api, context):
    r = rules()
    r["early"]["rental_refund"] = {"mode": "amount", "value": "120.00"}
    r["early"]["deposit_refund"] = r["late"]["deposit_refund"] = {
        "mode": "amount",
        "value": "80.00",
    }
    record = create(api, context, r).json()
    approve(api, context, record)
    assert preview(api, context, [record]).json()["previews"][0]["refund"] == "200.00"


@pytest.mark.parametrize("case", ["missing_total", "total_mismatch", "extra_charge"])
def test_financial_basis_needs_clarification(api, context, case):
    data = content(context)
    if case == "missing_total":
        data["amounts"] = data["amounts"][:-1]
    elif case == "total_mismatch":
        data["amounts"][-1]["amount"] = "400.00"
    else:
        data["amounts"].append(
            {
                "kind": "tax",
                "label": "tax",
                "amount": "20",
                "currency": "USD",
                "ambiguous": False,
            }
        )
    proposal = save(api, context, data).json()
    record = create(api, context, proposal=proposal).json()
    assert record["blockers"] and approve(api, context, record).status_code == 409


def test_exact_fingerprints_cross_booking_and_explicit_ack(api, context):
    record = create(api, context).json()
    assert (
        approve(api, context, record, expected_fingerprint="0" * 64).status_code == 409
    )
    assert (
        approve(api, context, record, no_unresolved_contradictions=False).status_code
        == 422
    )
    assert create(api, context).status_code == 409
    other = api.post("/api/bookings", json={"title": "Other"}).json()["id"]
    assert (
        api.get(f"/api/bookings/{other}/cancellation/rules/{record['id']}").status_code
        == 404
    )


@pytest.mark.parametrize("table", [CancellationRuleVersion, CancellationRuleApproval])
@pytest.mark.parametrize("mutation", ["update", "delete"])
def test_rule_records_immutable(api, context, postgres_engine, table, mutation):
    record = create(api, context).json()
    approved = approve(api, context, record).json()
    ident = (
        record["id"] if table == CancellationRuleVersion else approved["approval"]["id"]
    )
    with Session(postgres_engine) as session:
        statement = (
            delete(table) if mutation == "delete" else update(table).values(id=uuid4())
        )
        with pytest.raises(DBAPIError):
            session.execute(statement.where(table.id == UUID(ident)))
        session.rollback()


def test_ai_rules_are_proposals_only_and_transport_never_calculates_money(
    api, context, monkeypatch
):
    monkeypatch.setattr(
        gemini,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=SecretStr("test-only-key")),
    )
    client = Mock()
    client.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason="STOP",
                content=types.Content(
                    parts=[
                        types.Part(text=Rules.model_validate(rules()).model_dump_json())
                    ]
                ),
            )
        ]
    )
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(gemini.genai, "Client", factory)
    response = api.post(
        f"/api/bookings/{context['booking']}/cancellation/rules/propose",
        json={
            "target": target(context),
            "expected_latest_rule_id": None,
            "customer_label": "Reviewer",
        },
    )
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["origin"] == "gemini" and not record["approved_current"]
    assert preview(api, context, [record]).json()["previews"] == []
    assert (
        "AI MUST NEVER calculate money"
        in client.models.generate_content.call_args.kwargs["config"].system_instruction
    )
    assert (
        '"amounts"'
        not in client.models.generate_content.call_args.kwargs["contents"].parts[0].text
    )
    client.models.generate_content.assert_called_once()


def test_source_change_during_ai_rejects_publication(api, context):
    fake = Mock()

    def call(_):
        assert revise(api, context).status_code == 201
        return PolicyResult(
            Rules.model_validate(rules()), {"provider": "gemini", "mock": True}
        )

    fake.compare.side_effect = call
    app.dependency_overrides[get_rule_proposer] = lambda: fake
    response = api.post(
        f"/api/bookings/{context['booking']}/cancellation/rules/propose",
        json={
            "target": target(context),
            "expected_latest_rule_id": None,
            "customer_label": "Reviewer",
        },
    )
    assert response.status_code == 409


def test_explicit_exclusive_boundary_belongs_to_late_band(api, context):
    data = content(context)
    early = (
        "Cancellation more than 48 hours before pickup gives a full refund of USD 200."
    )
    late = (
        "Cancellation 48 hours or less before pickup refunds the deposit "
        "USD 80 and retains the rental fee USD 120."
    )
    data["cancellation_conditions"] = [
        {"value": value, "ambiguous": False} for value in (early, late)
    ]
    proposal = save(api, context, data).json()
    r = rules()
    r["early_includes_boundary"] = False
    r["early"]["clause"] = early
    r["late"]["clause"] = late
    record = create(api, context, r, proposal).json()
    assert record["blockers"] == []
    assert approve(api, context, record).json()["approved_current"]
    result = preview(api, context, [record]).json()["previews"][0]
    assert result["band"] == "late" and result["refund"] == "80.00"


def test_missing_support_is_saved_as_unknown_but_cannot_be_approved(api, context):
    r = rules()
    r["early"]["clause"] = ""
    r["deposit_clause"] = ""
    # Even a mistaken false flag cannot bypass server evidence checks.
    record = create(api, context, r).json()
    assert "early_clause_not_supported_by_source_version" in record["blockers"]
    assert "deposit_clause_not_supported_by_source_version" in record["blockers"]
    assert approve(api, context, record).status_code == 409
    assert preview(api, context, [record]).json()["previews"] == []
