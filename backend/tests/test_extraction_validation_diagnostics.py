"""Synthetic inputs; never a replay of a retained hosted model response."""

import json
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import HTTPException
from google.genai import types
from test_compact_extraction import SID, known_equipment, payload, row
from test_drafts import empty
from test_gemini_diagnostics import DOCUMENT, KEY, MODEL, PRIVATE, diagnostic

from app.core.config import Settings
from app.drafts import provider, service
from app.drafts.gemini_schema import decode_extraction
from app.drafts.schemas import TermStatuses


def install(monkeypatch, raw):
    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            gemini_api_key=KEY,
            gemini_model=MODEL,
        ),
    )
    client = MagicMock()
    client.__enter__.return_value = client
    client.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason="STOP",
                content=types.Content(parts=[types.Part(text=raw)]),
            )
        ]
    )
    monkeypatch.setattr(provider.genai, "Client", lambda **kwargs: client)
    return client


@pytest.mark.parametrize(
    "kind,stage,path,category",
    [
        ("wire", "wire_schema", "terms[0].quantity", "string_type"),
        (
            "invariant",
            "wire_invariants",
            "terms[0].quantity",
            "positive_integer_string_required",
        ),
        (
            "domain",
            "domain_schema",
            "equipment[0].citations[0].source_id",
            "uuid_parsing",
        ),
        ("metadata", "metadata_schema", "sdk_version", "string_type"),
    ],
)
def test_provider_validation_logs_field_and_rule_without_values(
    monkeypatch, caplog, kind, stage, path, category
):
    gear = known_equipment()
    if kind == "wire":
        gear["quantity"] = 1
    elif kind == "invariant":
        gear["quantity"] = "1.5"
    elif kind == "domain":
        gear["source_id"] = PRIVATE
    else:
        monkeypatch.setattr(provider.genai, "__version__", None)
    gear["quotation"] = PRIVATE
    client = install(monkeypatch, json.dumps(payload(equipment=[gear])))
    with pytest.raises(HTTPException) as caught:
        provider.GeminiExtractor().extract([{"text": DOCUMENT}])
    assert caught.value.detail["code"] == "ai_invalid_output"
    assert caught.value.status_code == 502
    logged = diagnostic(caplog)
    assert logged["validation_stage"] == stage
    assert {"path": path, "category": category} in logged["validation_errors"]
    assert logged["provider_http_status"] == 200
    assert all(
        set(item) == {"path", "category"} for item in logged["validation_errors"]
    )
    client.models.generate_content.assert_called_once()


def test_unknown_field_paths_and_error_volume_are_redacted(caplog, monkeypatch):
    data = payload(equipment=[known_equipment()])
    for index in range(25):
        data["terms"][0][PRIVATE + str(index)] = PRIVATE
    install(monkeypatch, json.dumps(data))
    with pytest.raises(HTTPException):
        provider.GeminiExtractor().extract([{"text": DOCUMENT}])
    logged = diagnostic(caplog)
    assert len(logged["validation_errors"]) == 12
    assert all(
        item == {"path": "terms[0].[unknown_field]", "category": "extra_forbidden"}
        for item in logged["validation_errors"]
    )


@pytest.mark.parametrize(
    "raw,path,category",
    [
        ('{"terms": [', "$", "json_invalid"),
        (json.dumps({"terms": []}), "terms", "too_short"),
        (
            json.dumps(payload(equipment=[dict(known_equipment(), currency=PRIVATE)])),
            "terms[0].currency",
            "unused_field_not_empty",
        ),
    ],
)
def test_malformed_output_stays_rejected_and_diagnostic_only(
    monkeypatch, caplog, raw, path, category
):
    install(monkeypatch, raw)
    with pytest.raises(HTTPException):
        provider.GeminiExtractor().extract([{"text": DOCUMENT}])
    assert {"path": path, "category": category} in diagnostic(caplog)[
        "validation_errors"
    ]


@pytest.mark.parametrize("stage", ["extraction", "draft"])
def test_internal_conversion_validation_is_logged_safely(monkeypatch, caplog, stage):
    if stage == "extraction":
        fake = Mock()
        fake.model_dump.return_value = {**empty(), "equipment": PRIVATE}
    else:
        fake = decode_extraction(json.dumps(payload()))
        original = TermStatuses
        monkeypatch.setattr(
            service,
            "TermStatuses",
            lambda **values: original.model_validate({**values, "equipment": PRIVATE}),
        )
    with pytest.raises(HTTPException) as caught:
        service.validate_and_classify(fake, [])
    assert caught.value.status_code == 502
    assert caught.value.detail["code"] == "ai_invalid_output"
    records = [
        r
        for r in caplog.records
        if r.getMessage().startswith("draft_validation_failure ")
    ]
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is None and record.stack_info is None
    assert PRIVATE not in record.getMessage() and KEY not in record.getMessage()
    logged = json.loads(record.getMessage().split(" ", 1)[1])
    assert logged["validation_stage"] == "draft_schema"
    assert logged["validation_errors"] == [
        {
            "path": "equipment",
            "category": "list_type" if stage == "extraction" else "literal_error",
        }
    ]


def test_rejected_provider_output_publishes_no_draft(api, monkeypatch, caplog):
    book = api.post(
        "/api/bookings", json={"title": "Synthetic diagnostic regression"}
    ).json()
    base = f"/api/bookings/{book['id']}"
    sources = [
        api.post(
            base + "/sources/text",
            json={
                "source_type": kind,
                "original_text": "Synthetic Camera quantity 1. " + kind,
            },
        ).json()["id"]
        for kind in ("quotation", "message")
    ]
    install(
        monkeypatch,
        json.dumps(payload(equipment=[dict(known_equipment(), quantity=1)])),
    )
    result = api.post(base + "/drafts", json={"source_ids": sources})
    assert result.status_code == 502
    assert result.json()["detail"]["code"] == "ai_invalid_output"
    assert api.get(base + "/drafts").json() == []
    assert diagnostic(caplog)["validation_stage"] == "wire_schema"


@pytest.mark.parametrize(
    "suffixes", [("", ""), ("Z", "Z"), ("+00:00", "+00:00"), ("", "Z")]
)
def test_reported_60_40_100_scenario_with_consistent_synthetic_sources(suffixes):
    # Authored test wording based on reported facts; not the actual saved sources.
    clauses = {
        "equipment": [("Camera quantity 1.", {"name": "Camera", "quantity": "1"})],
        "included_items": [
            ("Battery quantity 2.", {"name": "Battery", "quantity": "2"}),
            ("Microphone quantity 1.", {"name": "Microphone", "quantity": "1"}),
        ],
        "pickup": [
            (
                "Pickup: 20 November 2026 at 09:00 UTC.",
                {"value": "2026-11-20T09:00:00", "timezone": "UTC"},
            )
        ],
        "return_time": [
            (
                "Return: 22 November 2026 at 09:00 UTC.",
                {"value": "2026-11-22T09:00:00", "timezone": "UTC"},
            )
        ],
        "currency": [("Currency USD.", {"value": "USD"})],
        "amounts": [
            (
                "Rental fee USD 60.",
                {
                    "name": "Rental fee",
                    "kind": "rental_total",
                    "value": "60",
                    "currency": "USD",
                },
            ),
            (
                "Refundable deposit USD 40.",
                {
                    "name": "Deposit",
                    "kind": "deposit",
                    "value": "40",
                    "currency": "USD",
                },
            ),
            (
                "Inclusive total USD 100.",
                {
                    "name": "Total",
                    "kind": "total_payable",
                    "value": "100",
                    "currency": "USD",
                },
            ),
        ],
        "deposit_conditions": [
            (
                "Deposit USD 40 is refundable.",
                {"value": "Deposit USD 40 is refundable."},
            )
        ],
        "cancellation_conditions": [
            (
                "Cancellation at least 48 hours before pickup: "
                "refund rental USD 60 and deposit USD 40.",
                {},
            ),
            (
                "Cancellation less than 48 hours before pickup: "
                "refund rental USD 0 and deposit USD 40.",
                {},
            ),
        ],
    }
    sources, terms = [], []
    for sid, suffix in zip(
        (SID, "00000000-0000-0000-0000-000000000002"), suffixes, strict=True
    ):
        text = "\n".join(quote for items in clauses.values() for quote, _ in items)
        sources.append(
            {"source_id": sid, "medium": "pasted_text", "text": text, "pages": []}
        )
        for category, items in clauses.items():
            for quote, fields in items:
                if category in {"pickup", "return_time"}:
                    fields = {**fields, "value": fields["value"] + suffix}
                terms.append(
                    row(
                        category,
                        "known",
                        source_id=sid,
                        quotation=quote,
                        **(fields or {"value": quote}),
                    )
                )
    content = service.validate_and_classify(
        decode_extraction(json.dumps({"terms": terms})), sources
    )
    assert not content.needs_clarification
    from datetime import UTC, datetime

    from app.agreements.service import explicit_instant

    for category, day in (("pickup", 20), ("return_time", 22)):
        claims = getattr(content.extraction, category)
        assert len(claims) == 2
        assert {c.value.local_datetime for c in claims} == {f"2026-11-{day}T09:00:00"}
        assert all(c.value.timezone == "UTC" for c in claims)
        assert all(
            explicit_instant(c.value) == datetime(2026, 11, day, 9, tzinfo=UTC)
            for c in claims
        )
        assert {c.citations[0].quotation for c in claims} == {clauses[category][0][0]}
    assert {c.kind: str(c.amount) for c in content.extraction.amounts} == {
        "rental_total": "60",
        "deposit": "40",
        "total_payable": "100",
    }
    assert {c.name: c.quantity for c in content.extraction.included_items} == {
        "Battery": 2,
        "Microphone": 1,
    }
    assert {str(c.citations[0].source_id) for c in content.extraction.equipment} == {
        s["source_id"] for s in sources
    }
