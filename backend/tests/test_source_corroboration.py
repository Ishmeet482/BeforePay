import copy
from uuid import UUID

import pytest
from sqlalchemy.orm import Session
from test_customer_review import TEXT, revise, seed_review

from app.agreements.schemas import ReviewContent
from app.agreements.service import evidence, latest_agreement, save_version
from app.cancellations.service import money_context
from app.comparisons.service import canonical, plan_comparison
from app.drafts.corroboration import corroborate_claims, corroborate_review
from app.drafts.schemas import CurrencyClaim, EquipmentClaim, MoneyClaim, TextClaim

S1 = "00000000-0000-0000-0000-000000000001"
S2 = "00000000-0000-0000-0000-000000000002"


def cited(source):
    return {
        "source_id": source,
        "quotation": "Synthetic exact clause",
        "page_number": None,
    }


@pytest.mark.parametrize(
    "model,fields,changed",
    [
        (EquipmentClaim, {"name": "Camera", "quantity": 1}, {"quantity": 2}),
        (
            MoneyClaim,
            {
                "label": "Rental",
                "kind": "rental_total",
                "amount": "60",
                "currency": "USD",
            },
            {"amount": "100"},
        ),
        (
            TextClaim,
            {"value": "Deposit is refundable."},
            {"value": "Deposit may be refundable."},
        ),
    ],
)
def test_only_exact_cross_source_claims_merge(model, fields, changed):
    first = model(**fields, ambiguous=False, citations=[cited(S1)])
    second = model(**fields, ambiguous=False, citations=[cited(S2)])
    before = first.model_dump()
    merged = corroborate_claims([first, second])
    assert len(merged) == 1
    assert [str(c.source_id) for c in merged[0].citations] == [S1, S2]
    assert first.model_dump() == before  # No mutation of immutable input snapshots.
    assert (
        len(
            corroborate_claims(
                [first, model.model_validate({**second.model_dump(), **changed})]
            )
        )
        == 2
    )
    assert len(corroborate_claims([first, first])) == 2  # Same-source multiplicity.
    assert (
        len(corroborate_claims([first, second.model_copy(update={"ambiguous": True})]))
        == 2
    )


def test_same_source_distinct_items_and_evidence_limit_survive():
    first = EquipmentClaim(
        name="Camera", quantity=1, ambiguous=False, citations=[cited(S1)]
    )
    other = first.model_copy(update={"name": "Tripod"})
    second = EquipmentClaim.model_validate(
        {**first.model_dump(), "citations": [cited(S2)]}
    )
    assert [c.name for c in corroborate_claims([first, other, second])] == [
        "Camera",
        "Tripod",
    ]
    assert len(corroborate_claims([first, first, second])) == 2
    full = first.model_copy(update={"citations": [first.citations[0]] * 20})
    assert (
        len(corroborate_claims([full, second])) == 2
    )  # Never discard evidence to fit.


def test_corroborated_money_is_not_summed_and_conflicts_still_block():
    amounts = [
        MoneyClaim(
            label=kind,
            kind=kind,
            amount=value,
            currency="USD",
            ambiguous=False,
            citations=[cited(sid)],
        )
        for sid in (S1, S2)
        for kind, value in (
            ("rental_total", "60"),
            ("deposit", "40"),
            ("total_payable", "100"),
        )
    ]
    currencies = [
        CurrencyClaim(value="USD", ambiguous=False, citations=[cited(sid)])
        for sid in (S1, S2)
    ]
    claims = {
        "amounts": corroborate_claims(amounts),
        "currency": corroborate_claims(currencies),
    }
    values, blockers = money_context(claims)
    assert not blockers
    assert {kind: str(value) for kind, value in values.items()} == {
        "rental_total": "60",
        "deposit": "40",
        "total_payable": "100",
    }
    claims["amounts"] = corroborate_claims(
        [*amounts, amounts[0].model_copy(update={"amount": amounts[1].amount})]
    )
    assert "duplicate_amount_kind" in money_context(claims)[1]


def test_customer_correction_provenance_and_order_are_preserved():
    from app.agreements.schemas import ReviewExtraction

    source = EquipmentClaim(
        name="Camera", quantity=1, ambiguous=False, citations=[cited(S1)]
    )
    content = ReviewContent(
        extraction={category: [] for category in ReviewExtraction.model_fields}
    )
    raw = content.model_dump()
    raw["extraction"]["equipment"] = [
        {"origin": "source_supported", "claim": source.model_dump()},
        {
            "origin": "customer_entered",
            "reason": "Explicit negotiated extra item",
            "claim": {
                "name": "Tripod",
                "quantity": 1,
                "ambiguous": False,
                "citations": [],
            },
        },
        {
            "origin": "source_supported",
            "claim": {**source.model_dump(), "citations": [cited(S2)]},
        },
    ]
    original = ReviewContent.model_validate(raw)
    result = corroborate_review(original)
    assert len(original.extraction.equipment) == 3
    assert len(result.extraction.equipment) == 2
    assert result.extraction.equipment[1] == original.extraction.equipment[1]
    assert len(result.extraction.equipment[0].claim.citations) == 2


def test_secondary_citation_must_validate_before_consolidation():
    from fastapi import HTTPException

    from app.drafts.schemas import Extraction
    from app.drafts.service import validate_and_classify

    data = {category: [] for category in Extraction.model_fields}
    data["equipment"] = [
        {
            "name": "Camera",
            "quantity": 1,
            "ambiguous": False,
            "citations": [
                {
                    "source_id": sid,
                    "quotation": "Camera quantity 1",
                    "page_number": None,
                }
            ],
        }
        for sid in (S1, S2)
    ]
    sources = [
        {"source_id": sid, "medium": "pasted_text", "text": text, "pages": []}
        for sid, text in ((S1, "Camera quantity 1"), (S2, "Different source wording"))
    ]
    with pytest.raises(HTTPException) as raised:
        validate_and_classify(Extraction.model_validate(data), sources)
    assert raised.value.detail["code"] == "ai_invalid_citation"


def test_explicit_review_revision_consolidates_legacy_claims_without_history_rewrite(
    api, postgres_engine
):
    context = seed_review(api, postgres_engine)
    base = f"/api/bookings/{context['booking']}"
    source = api.post(
        base + "/sources/text", json={"source_type": "message", "original_text": TEXT}
    ).json()
    # Simulate an immutable pre-fix version in this disposable database only.
    with Session(postgres_engine, expire_on_commit=False) as db:
        parent = latest_agreement(db, UUID(context["booking"]))
        data = copy.deepcopy(parent.content)
        for entries in data["extraction"].values():
            for entry in list(entries):
                duplicate = copy.deepcopy(entry)
                for citation in duplicate["claim"]["citations"]:
                    citation["source_id"] = source["id"]
                entries.append(duplicate)
        _, fingerprints = evidence(db, UUID(context["booking"]))
        legacy = save_version(
            db,
            UUID(context["booking"]),
            parent.draft_id,
            parent,
            ReviewContent.model_validate(data),
            fingerprints,
            list(fingerprints),
            {"kind": "synthetic_pre_fix_review", "customer_label": "Offline reviewer"},
        )
        legacy_id = str(legacy.id)
    old = api.get(base + "/agreements/" + legacy_id).json()
    response = revise(
        api,
        context,
        agreement=old,
        reviewed_source_ids=[context["source"]["id"], source["id"]],
    )
    assert response.status_code == 201, response.text
    current = response.json()
    assert current["fingerprint"] != old["fingerprint"]
    for category, entries in current["content"]["extraction"].items():
        assert len(entries) * 2 == len(old["content"]["extraction"][category])
        for entry in entries:
            assert len(entry["claim"]["citations"]) == 2
            assert entry["origin"] == "source_supported"
    assert api.get(base + "/agreements/" + legacy_id).json() == old
    assert not api.get(base + "/review").json()["confirmation_current"]
    baseline = ReviewContent.model_validate(current["content"])
    proposal = {
        cat: [
            e.claim.model_dump(mode="json") | {"citations": []}
            for e in getattr(baseline.extraction, cat)
        ]
        for cat in type(baseline.extraction).model_fields
    }
    proposal["included_items_none"] = False
    results, pending = plan_comparison(current["content"], proposal)
    assert not pending
    assert all(r["status"] == "matches" for r in results)
    assert canonical("equipment", [e.claim for e in baseline.extraction.equipment]) == {
        "camera": 1
    }
