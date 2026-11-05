import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.drafts.gemini_schema import FIELDS, decode_extraction, extraction_json_schema
from app.drafts.schemas import Extraction
from app.drafts.service import validate_and_classify

SID = "00000000-0000-0000-0000-000000000001"
TEXT = "Camera quantity 1. Camera quantity 2. Rental total USD 200.00."
SOURCES = [{"source_id": SID, "medium": "pasted_text", "text": TEXT, "pages": []}]


def row(category, state="unknown", **values):
    return {**dict.fromkeys(FIELDS, ""), "category": category, "state": state, **values}


def payload(**overrides):
    return {
        "terms": [
            term
            for category in Extraction.model_fields
            for term in overrides.get(category, [row(category)])
        ]
    }


def known_equipment(**values):
    return row(
        "equipment",
        "known",
        name="Camera",
        quantity="1",
        source_id=SID,
        quotation="Camera quantity 1",
        **values,
    )


def test_wire_is_compact_and_contains_no_domain_schema_expansion():
    schema = extraction_json_schema()
    assert len(json.dumps(schema)) < 1000
    assert set(schema["properties"]) == {"terms"}
    fields = schema["properties"]["terms"]["items"]["properties"]
    assert set(fields) == set(FIELDS)
    assert all(field == {"type": "string"} for field in fields.values())
    text = json.dumps(schema)
    assert all(
        key not in text
        for key in ("$ref", "$defs", "anyOf", "maxItems", "minimum", "nullable")
    )


def test_conversion_preserves_money_unknowns_and_conflicting_citations():
    gear = known_equipment()
    gear["state"] = "conflict"
    alternative = dict(gear, quantity="2", quotation="Camera quantity 2")
    money = row(
        "amounts",
        "known",
        name="Rental total",
        kind="rental_total",
        value="200.00",
        currency="USD",
        source_id=SID,
        quotation="Rental total USD 200.00",
    )
    extraction = decode_extraction(
        json.dumps(payload(equipment=[gear, alternative], amounts=[money]))
    )
    assert extraction.amounts[0].amount == Decimal("200.00")
    assert extraction.amounts[0].amount.as_tuple().exponent == -2
    content = validate_and_classify(extraction, SOURCES)
    assert content.term_statuses.equipment == "needs_clarification"
    assert content.term_statuses.cancellation_conditions == "unknown"
    assert [claim.quantity for claim in content.extraction.equipment] == [1, 2]


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "0"},
        {"quantity": "1.5"},
        {"quantity": "100001"},
        {"source_id": "not-a-uuid"},
        {"page_number": "101"},
        {"quotation": " "},
        {"quantity": 1},
        {"extra": True},
        {"state": "approved"},
        {"currency": "USD"},
    ],
)
def test_wire_cannot_weaken_domain_validation(change):
    gear = dict(known_equipment(), **change)
    with pytest.raises((ValidationError, ValueError)):
        decode_extraction(json.dumps(payload(equipment=[gear])))


@pytest.mark.parametrize("value", [200.1, "-1", "NaN", "0.00001", "12345678901234567"])
def test_financial_constraints_remain_enforced(value):
    money = row(
        "amounts",
        "known",
        name="Total",
        kind="rental_total",
        value=value,
        currency="USD",
        source_id=SID,
        quotation="Rental total USD 200.00",
    )
    with pytest.raises((ValidationError, ValueError)):
        decode_extraction(json.dumps(payload(amounts=[money])))


def test_unknown_states_cannot_discard_facts_or_hide_missing_categories():
    with pytest.raises(ValueError):
        decode_extraction(
            json.dumps(payload(equipment=[dict(known_equipment(), state="unknown")]))
        )
    with pytest.raises(ValueError):
        decode_extraction(json.dumps({"terms": [row("equipment")] * 8}))
    with pytest.raises(ValueError):
        decode_extraction(
            json.dumps(payload(equipment=[row("equipment"), known_equipment()]))
        )


@pytest.mark.parametrize(
    "change",
    [
        {"source_id": "00000000-0000-0000-0000-000000000002"},
        {"quotation": "Invented quotation"},
        {"page_number": "1"},
    ],
)
def test_original_source_quote_and_page_validation_still_runs(change):
    from fastapi import HTTPException

    gear = dict(known_equipment(), **change)
    extraction = decode_extraction(json.dumps(payload(equipment=[gear])))
    with pytest.raises(HTTPException) as caught:
        validate_and_classify(extraction, SOURCES)
    assert caught.value.detail["code"] == "ai_invalid_citation"


@pytest.mark.parametrize("quantity,expected", [("one", 1), ("two", 2), ("Twenty", 20)])
def test_explicit_number_words_convert_without_losing_evidence(quantity, expected):
    quote = f"Camera quantity {quantity}"
    gear = dict(known_equipment(), quantity=quantity, quotation=quote)
    extraction = decode_extraction(json.dumps(payload(equipment=[gear])))
    sources = [
        {
            "source_id": SID,
            "medium": "pdf",
            "pages": [{"page_number": 1, "text": quote}],
        }
    ]
    extraction.equipment[0].citations[0].page_number = 1
    content = validate_and_classify(extraction, sources)
    assert content.extraction.equipment[0].quantity == expected
    assert content.extraction.equipment[0].citations[0].quotation == quote


@pytest.mark.parametrize("category", ["deposit_conditions", "cancellation_conditions"])
def test_policy_paraphrases_still_fail_literal_validation(category):
    from fastapi import HTTPException

    policy = row(
        category,
        "known",
        value="Refundable deposit",
        source_id=SID,
        quotation="Deposit returned on return.",
    )
    extraction = decode_extraction(json.dumps(payload(**{category: [policy]})))
    with pytest.raises(HTTPException) as caught:
        validate_and_classify(
            extraction,
            [
                {
                    "source_id": SID,
                    "medium": "pasted_text",
                    "text": policy["quotation"],
                    "pages": [],
                }
            ],
        )
    assert caught.value.detail["code"] == "ai_unsupported_value"


def test_pdf_number_word_response_persists_through_real_adapter(api, monkeypatch):
    from unittest.mock import MagicMock, Mock

    import pymupdf
    from google.genai import types
    from pydantic import SecretStr

    from app.core.config import Settings
    from app.drafts import provider

    booking = api.post(
        "/api/bookings", json={"title": "Number-word PDF regression"}
    ).json()["id"]
    quote = "Camera quantity two"
    policy = "Deposit returned on return."
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), f"{quote}\n{policy}")
        binary = document.tobytes()
    source = api.post(
        f"/api/bookings/{booking}/sources/pdf",
        data={"source_type": "quotation"},
        files={"file": ("synthetic.pdf", binary, "application/pdf")},
    ).json()
    gear = dict(
        known_equipment(),
        quantity="two",
        source_id=source["id"],
        quotation=quote,
        page_number="1",
    )
    deposit = row(
        "deposit_conditions",
        "known",
        value=policy,
        quotation=policy,
        source_id=source["id"],
        page_number="1",
    )
    raw = json.dumps(payload(equipment=[gear], deposit_conditions=[deposit]))
    client = Mock()
    client.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason="STOP",
                content=types.Content(parts=[types.Part(text=raw)]),
            )
        ],
        model_version="mock-model",
        response_id="mock-id",
    )
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(provider.genai, "Client", factory)
    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=SecretStr("test-only-key")),
    )
    path = f"/api/bookings/{booking}/drafts"
    response = api.post(path, json={"source_ids": [source["id"]]})
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["content"]["extraction"]["equipment"][0]["quantity"] == 2
    assert draft["content"]["term_statuses"]["pickup"] == "unknown"
    assert draft["status"] == "draft"
    assert api.get(f"{path}/{draft['id']}").json() == draft
    client.models.generate_content.assert_called_once()
    prompt = client.models.generate_content.call_args.kwargs[
        "config"
    ].system_instruction
    assert "value must be an exact contiguous substring of quotation" in prompt
    assert "never emit number words" in prompt


def test_rental_fee_deposit_and_inclusive_total_remain_distinct():
    from app.drafts.provider import SYSTEM_PROMPT

    text = "Rental fee USD 120. Deposit USD 80. Total payable USD 200."
    terms = [
        row(
            "amounts",
            "known",
            kind=kind,
            name=label,
            value=amount,
            currency="USD",
            source_id=SID,
            quotation=quote,
        )
        for kind, label, amount, quote in [
            ("rental_total", "Rental fee", "120", "Rental fee USD 120"),
            ("deposit", "Deposit", "80", "Deposit USD 80"),
            ("total_payable", "Total payable", "200", "Total payable USD 200"),
        ]
    ]
    extraction = decode_extraction(json.dumps(payload(amounts=terms)))
    content = validate_and_classify(
        extraction,
        [{"source_id": SID, "medium": "pasted_text", "text": text, "pages": []}],
    )
    assert {c.kind: c.amount for c in content.extraction.amounts} == {
        "rental_total": Decimal("120"),
        "deposit": Decimal("80"),
        "total_payable": Decimal("200"),
    }
    assert content.term_statuses.amounts == "extracted"
    assert "never an additional charge" in SYSTEM_PROMPT
    assert "never calculate a missing total" in SYSTEM_PROMPT
