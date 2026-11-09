"""Synthetic legacy versions only; no hosted records or provider calls."""

import copy
from uuid import UUID

import pytest
from sqlalchemy.orm import Session
from test_booking_comparisons import compare, save
from test_cancellation_preview import approve, create, preview
from test_customer_review import confirm
from test_drafts import metadata
from test_paypal_sandbox import settings as sandbox_settings_fixture

from app.agreements.schemas import ReviewContent
from app.agreements.service import evidence, save_version
from app.cancellations.schemas import Rules
from app.cancellations.service import money_context, rule_blockers
from app.comparisons.models import BookingComparison
from app.comparisons.service import canonical, digest, plan_comparison
from app.drafts.corroboration import corroborate_typed
from app.drafts.models import DraftVersion
from app.drafts.schemas import Extraction
from app.drafts.service import validate_and_classify

EARLY = (
    "Cancellation at least 48 hours before pickup: "
    "refund rental USD 60 and deposit USD 40."
)
LATE = (
    "Cancellation less than 48 hours before pickup: "
    "refund rental USD 0 and deposit USD 40."
)
DEPOSIT = (
    "The USD 40 deposit is refundable on cancellation "
    "according to the cancellation clauses."
)


@pytest.fixture
def sandbox_config(monkeypatch):
    return sandbox_settings_fixture.__wrapped__(monkeypatch)


def rules():
    return {
        "cutoff_hours": "48",
        "early_includes_boundary": True,
        "early": {
            "rental_refund": {"mode": "percent", "value": "100"},
            "deposit_refund": {"mode": "percent", "value": "100"},
            "clause": EARLY,
        },
        "late": {
            "rental_refund": {"mode": "percent", "value": "0"},
            "deposit_refund": {"mode": "percent", "value": "100"},
            "clause": LATE,
        },
        "deposit_clause": DEPOSIT,
        "needs_clarification": False,
        "clarification_note": "",
    }


def raw_claims():
    values = {
        "equipment": [{"name": "camera", "quantity": 1}],
        "included_items": [
            {"name": "batteries", "quantity": 2},
            {"name": "microphone", "quantity": 1},
        ],
        "pickup": [
            {"value": {"local_datetime": "2026-11-20T09:00:00", "timezone": "UTC"}}
        ],
        "return_time": [
            {"value": {"local_datetime": "2026-11-22T09:00:00", "timezone": "UTC"}}
        ],
        "currency": [{"value": "USD"}],
        "amounts": [
            {"kind": kind, "label": label, "amount": amount, "currency": "USD"}
            for kind, label, amount in (
                ("rental_total", "Rental fee", "60"),
                ("deposit", "Refundable security deposit", "40"),
                ("total_payable", "Total payable", "100"),
            )
        ],
        "deposit_conditions": [{"value": DEPOSIT}],
        "cancellation_conditions": [{"value": EARLY}, {"value": LATE}],
    }
    text = (
        "camera quantity 1. batteries quantity 2. microphone quantity 1. "
        "Pickup 20 November 2026 09:00 UTC. Return 22 November 2026 09:00 UTC. "
        "Rental fee USD 60; deposit USD 40; total USD 100.\n"
        + "\n".join((DEPOSIT, EARLY, LATE))
    )
    data = {category: [] for category in Extraction.model_fields}
    for source_index in (1, 2):
        source_id = f"00000000-0000-0000-0000-{source_index:012d}"
        for category, claims in values.items():
            for claim in claims:
                claim = copy.deepcopy(claim)
                if source_index == 2 and category == "amounts":
                    claim["label"] = (
                        "total"
                        if claim["kind"] == "total_payable"
                        else claim["label"].lower()
                    )
                data[category].append(
                    {
                        **claim,
                        "ambiguous": False,
                        "citations": [
                            {
                                "source_id": source_id,
                                "quotation": text,
                                "page_number": None,
                            }
                        ],
                    }
                )
    return data, text


def test_legacy_values_match_without_rewriting_original_terms():
    data, _ = raw_claims()
    extraction = Extraction.model_validate(data)
    original = extraction.model_dump(mode="json")
    for category in Extraction.model_fields:
        if category.endswith("conditions"):
            continue  # Policy meaning uses plan_comparison, not typed canonical.
        claims = getattr(extraction, category)
        assert canonical(category, claims) is not None
    amounts, blockers = money_context(
        {
            category: getattr(extraction, category)
            for category in Extraction.model_fields
        }
    )
    assert not blockers
    assert {k: str(v) for k, v in amounts.items()} == {
        "rental_total": "60",
        "deposit": "40",
        "total_payable": "100",
    }
    assert not rule_blockers(
        Rules.model_validate(rules()),
        {
            category: getattr(extraction, category)
            for category in Extraction.model_fields
        },
    )
    assert extraction.model_dump(mode="json") == original
    assert [c.label for c in corroborate_typed("amounts", extraction.amounts)] == [
        "Rental fee",
        "Refundable security deposit",
        "Total payable",
    ]


@pytest.mark.parametrize("change", ["flag", "quantity", "same_source", "uncited"])
def test_included_item_conflicts_and_authored_duplicates_still_block(change):
    data, _ = raw_claims()
    claims = data["included_items"]
    if change == "flag":
        claims[2]["ambiguous"] = True
    elif change == "quantity":
        claims[2]["quantity"] = 3
    elif change == "same_source":
        claims[2]["citations"] = copy.deepcopy(claims[0]["citations"])
    else:
        from app.agreements.schemas import CustomerEquipment

        assert (
            canonical(
                "included_items",
                [
                    CustomerEquipment.model_validate({**c, "citations": []})
                    for c in claims
                ],
            )
            is None
        )
        return
    assert (
        canonical("included_items", Extraction.model_validate(data).included_items)
        is None
    )


@pytest.mark.parametrize(
    "field,value", [("amount", "99"), ("currency", "EUR"), ("ambiguous", True)]
)
def test_summary_label_variants_do_not_hide_financial_conflicts(field, value):
    data, _ = raw_claims()
    data["amounts"][3][field] = value
    extraction = Extraction.model_validate(data)
    assert canonical("amounts", extraction.amounts) is None
    assert money_context(
        {"amounts": extraction.amounts, "currency": extraction.currency}
    )[1]


@pytest.mark.parametrize(
    "index,label",
    [
        (3, "Rental fee including delivery"),
        (4, "Non-refundable security deposit"),
        (5, "Total before taxes"),
    ],
)
def test_qualifying_summary_wording_is_not_a_label_alias(index, label):
    data, _ = raw_claims()
    data["amounts"][index]["label"] = label
    extraction = Extraction.model_validate(data)
    assert canonical("amounts", extraction.amounts) is None
    assert (
        "duplicate_amount_kind"
        in money_context(
            {"amounts": extraction.amounts, "currency": extraction.currency}
        )[1]
    )


@pytest.mark.parametrize(
    "category,change",
    [
        (
            "pickup",
            {"value": {"local_datetime": "2026-11-20T10:00:00", "timezone": "UTC"}},
        ),
        (
            "pickup",
            {"value": {"local_datetime": "2026-11-20T09:00:00", "timezone": None}},
        ),
        ("pickup", {"ambiguous": True}),
        ("currency", {"value": "EUR"}),
        ("currency", {"ambiguous": True}),
    ],
)
def test_further_refund_steps_keep_real_source_conflicts_blocked(category, change):
    data, _ = raw_claims()
    data[category][1].update(change)
    extraction = Extraction.model_validate(data)
    claims = {key: getattr(extraction, key) for key in Extraction.model_fields}
    assert canonical(category, claims[category]) is None
    assert rule_blockers(Rules.model_validate(rules()), claims)


def test_legacy_comparison_through_separate_rule_and_checkout_approvals(
    api, postgres_engine, sandbox_config
):
    data, text = raw_claims()
    booking = api.post(
        "/api/bookings", json={"title": "Synthetic legacy corroboration"}
    ).json()["id"]
    base = f"/api/bookings/{booking}"
    sources = [
        api.post(
            base + "/sources/text", json={"source_type": kind, "original_text": text}
        ).json()["id"]
        for kind in ("quotation", "message")
    ]
    for claims in data.values():
        for claim in claims:
            original_source = int(claim["citations"][0]["source_id"][-1]) - 1
            claim["citations"][0]["source_id"] = sources[original_source]
    extraction = Extraction.model_validate(data)
    with Session(postgres_engine, expire_on_commit=False) as db:
        snapshots, fingerprints = evidence(db, UUID(booking))
        content = validate_and_classify(extraction, snapshots).model_dump(mode="json")
        content["extraction"] = extraction.model_dump(mode="json")  # Pre-fix snapshot.
        draft = DraftVersion(
            booking_id=UUID(booking),
            version=1,
            status="draft",
            input_source_ids=sources,
            source_fingerprints=fingerprints,
            content=content,
            model_metadata=metadata().model_dump(mode="json"),
        )
        db.add(draft)
        db.commit()
        saved = save_version(
            db,
            UUID(booking),
            draft.id,
            None,
            ReviewContent(
                extraction={
                    category: [
                        {"origin": "source_supported", "claim": c} for c in claims
                    ]
                    for category, claims in data.items()
                }
            ),
            fingerprints,
            sources,
            {"kind": "synthetic_legacy_review", "customer_label": "Offline reviewer"},
        )
        agreement_id = str(saved.id)
    agreement = api.get(base + "/agreements/" + agreement_id).json()
    context = {"booking": booking, "agreement": agreement}
    confirmation = confirm(api, context)
    assert confirmation.status_code == 201, confirmation.text
    # One merchant-authored row per actual component/item; labels need not match.
    proposal_data = {
        category: [
            {**claim.model_dump(mode="json"), "citations": []}
            for claim in corroborate_typed(category, getattr(extraction, category))
        ]
        for category in Extraction.model_fields
    }
    proposal_data["included_items_none"] = False
    proposal = save(api, context, proposal_data).json()
    old_results, pending = plan_comparison(agreement["content"], proposal["content"])
    assert not pending
    for result in old_results:
        if result["category"] not in {"deposit_conditions", "cancellation_conditions"}:
            result.update(
                status="needs_clarification", reason="missing_or_ambiguous_terms"
            )
    with Session(postgres_engine, expire_on_commit=False) as db:
        old = BookingComparison(
            booking_id=UUID(booking),
            agreement_id=UUID(agreement_id),
            agreement_fingerprint=agreement["fingerprint"],
            confirmation_id=UUID(confirmation.json()["id"]),
            proposal_id=UUID(proposal["id"]),
            proposal_fingerprint=proposal["fingerprint"],
            fingerprint=digest(old_results),
            results=old_results,
            model_metadata=None,
        )
        db.add(old)
        db.commit()
        old_id = str(old.id)
    assert (
        "comparison_has_differences_or_clarification"
        in api.get(base + "/checkout/eligibility").json()["blockers"]
    )
    fresh = compare(api, context, proposal)
    assert fresh.status_code == 201, fresh.text
    assert all(r["status"] == "matches" for r in fresh.json()["results"])
    items = next(
        r for r in fresh.json()["results"] if r["category"] == "included_items"
    )
    assert len(items["agreement_terms"]) == 4  # Exact saved citation/index bindings.
    assert len(items["proposal_terms"]) == 2
    assert api.get(base + "/agreements/" + agreement_id).json() == agreement
    assert api.get(base + "/comparisons/" + old_id).json()["results"] == old_results
    blockers = api.get(base + "/checkout/eligibility").json()["blockers"]
    assert "agreement_reviewed_cancellation_rules_required" in blockers
    assert "proposal_reviewed_cancellation_rules_required" in blockers
    buyer_rule = create(api, context, rules()).json()
    assert not buyer_rule["approved_current"] and not buyer_rule["blockers"]
    assert approve(api, context, buyer_rule).json()["approved_current"]
    assert not api.get(base + "/checkout/eligibility").json()["eligible"]
    merchant_rule = create(api, context, rules(), proposal=proposal).json()
    assert approve(api, context, merchant_rule).json()["approved_current"]
    for local, refund, retained in (
        ("2026-11-18T09:00:00", "100.00", "0.00"),
        ("2026-11-18T09:01:00", "40.00", "60.00"),
    ):
        response = preview(api, context, [buyer_rule, merchant_rule], local=local)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ready"
        assert all(
            p["refund"] == refund and p["retained"] == retained
            for p in response.json()["previews"]
        )
    eligibility = api.get(base + "/checkout/eligibility").json()
    assert eligibility["eligible"] and eligibility["context"]["amount"] == "100.00"
    assert eligibility["context"]["agreement_fingerprint"] == agreement["fingerprint"]
    assert api.get(base + "/checkout/attempts").json() == []
    assert api.get(base + "/checkout/receipt").status_code == 404
    assert (
        api.post(
            base + "/checkout/approvals",
            json={
                "customer_label": "Offline reviewer",
                "acknowledged": True,
                "expected_context_fingerprint": eligibility["fingerprint"],
            },
        ).status_code
        == 201
    )
    assert api.get(base + "/checkout/attempts").json() == []
