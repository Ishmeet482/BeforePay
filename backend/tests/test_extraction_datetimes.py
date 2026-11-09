"""Offline wire compatibility; domain times and source evidence remain strict."""

import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_compact_extraction import SID, payload, row

from app.agreements.service import explicit_instant
from app.drafts.gemini_schema import decode_extraction
from app.drafts.provider import PROMPT_VERSION, SYSTEM_PROMPT
from app.drafts.schemas import TimeValue
from app.drafts.service import validate_and_classify
from app.drafts.validation import WireInvariantError, validation_report


def decode_time(value, zone="UTC", quote="Pickup: 20 November 2026 at 09:00 UTC."):
    return decode_extraction(
        json.dumps(
            payload(
                pickup=[
                    row(
                        "pickup",
                        "known",
                        value=value,
                        timezone=zone,
                        source_id=SID,
                        quotation=quote,
                    )
                ]
            )
        )
    )


@pytest.mark.parametrize(
    "value,zone,expected",
    [
        ("2026-11-20T09:00:00Z", "UTC", datetime(2026, 11, 20, 9, tzinfo=UTC)),
        ("2026-11-20T09:00:00+00:00", "UTC", datetime(2026, 11, 20, 9, tzinfo=UTC)),
        (
            "2026-11-20T09:00:00+05:30",
            "+05:30",
            datetime(2026, 11, 20, 3, 30, tzinfo=UTC),
        ),
        (
            "2026-11-20T09:00:00-05:00",
            "America/New_York",
            datetime(2026, 11, 20, 14, tzinfo=UTC),
        ),
        (
            "2026-11-20T09:00:00.123456Z",
            "UTC",
            datetime(2026, 11, 20, 9, microsecond=123456, tzinfo=UTC),
        ),
    ],
)
def test_redundant_offset_requires_same_explicit_zone_instant(value, zone, expected):
    result = decode_time(value, zone).pickup[0].value
    assert result.timezone == zone
    assert datetime.fromisoformat(result.local_datetime).tzinfo is None
    assert explicit_instant(result) == expected


@pytest.mark.parametrize(
    "value,zone,category",
    [
        ("2026-11-20T09:00:00+01:00", "UTC", "datetime_offset_timezone_mismatch"),
        ("2026-11-20T09:00:00Z", "+05:30", "datetime_offset_timezone_mismatch"),
        (
            "2026-11-20T09:00:00-04:00",
            "America/New_York",
            "datetime_offset_timezone_mismatch",
        ),
        (
            "2026-11-01T01:30:00-04:00",
            "America/New_York",
            "datetime_timezone_ambiguous",
        ),
        (
            "2026-11-01T01:30:00-05:00",
            "America/New_York",
            "datetime_timezone_ambiguous",
        ),
        (
            "2026-03-08T02:30:00-05:00",
            "America/New_York",
            "datetime_timezone_ambiguous",
        ),
    ],
)
def test_offset_cannot_override_zone_or_choose_dst_fold(value, zone, category):
    with pytest.raises(WireInvariantError) as caught:
        decode_time(value, zone)
    assert validation_report(caught.value) == {
        "validation_stage": "wire_invariants",
        "validation_errors": [{"path": "terms[1].value", "category": category}],
    }


@pytest.mark.parametrize(
    "value,zone",
    [
        ("2026-11-20T09:00:00Z", ""),
        ("2026-11-20T09:00:00Z", "IST"),
        ("2026-11-20T09:00:00Z", "CST"),
        ("2026-11-20T09:00:00Z", "Invalid/Zone"),
        ("2026-11-31T09:00:00Z", "UTC"),
        ("2026-11-31T09:00:00", "UTC"),
        ("2026-02-29T09:00:00+00:00", "UTC"),
        ("11/20/2026T09:00:00Z", "UTC"),
        ("20/11/2026T09:00:00", "UTC"),
        ("20 NovemberT09:00:00", "UTC"),
        ("2026-11-20", "UTC"),
        ("next FridayT09:00:00", "UTC"),
        ("2026-11-20T25:00:00Z", "UTC"),
        ("2026-11-20T09:00:00+00:60", "UTC"),
    ],
)
def test_invalid_or_incomplete_dates_and_zones_still_rejected(value, zone):
    with pytest.raises(ValidationError):
        decode_time(value, zone)


def test_missing_zone_remains_missing_and_needs_review():
    extraction = decode_time("2026-11-20T09:00:00", "")
    content = validate_and_classify(
        extraction,
        [
            {
                "source_id": SID,
                "medium": "pasted_text",
                "pages": [],
                "text": "Pickup: 20 November 2026 at 09:00 UTC.",
            }
        ],
    )
    assert content.extraction.pickup[0].value.timezone is None
    assert content.term_statuses.pickup == "needs_clarification"


@pytest.mark.parametrize("wall_time", ["2026-11-20T09:00", "2026-11-20T09:00:00.120"])
def test_wire_conversion_preserves_wall_time_spelling(wall_time):
    assert decode_time(wall_time + "Z").pickup[0].value.local_datetime == wall_time


def test_naive_ambiguous_local_time_still_cannot_establish_instant():
    value = decode_time("2026-11-01T01:30:00", "America/New_York").pickup[0].value
    with pytest.raises(ValueError, match="Ambiguous or nonexistent"):
        explicit_instant(value)


def test_conversion_does_not_bypass_literal_timezone_support():
    quote = "Pickup: 20 November 2026 at 09:00."
    extraction = decode_time("2026-11-20T09:00:00Z", "UTC", quote)
    with pytest.raises(HTTPException) as caught:
        validate_and_classify(
            extraction,
            [
                {
                    "source_id": SID,
                    "medium": "pasted_text",
                    "pages": [],
                    "text": quote,
                }
            ],
        )
    assert caught.value.detail["code"] == "ai_unsupported_value"


@pytest.mark.parametrize("value", ["2026-11-20T09:00:00Z", "2026-11-20T09:00:00+00:00"])
def test_internal_domain_model_still_requires_separate_local_time(value):
    with pytest.raises(ValidationError):
        TimeValue(local_datetime=value, timezone="UTC")


def test_prompt_explicitly_describes_split_representation():
    assert PROMPT_VERSION == "rental-draft-gemini-flat-v5"
    assert "without Z or a UTC offset" in SYSTEM_PROMPT
    assert 'value="2026-11-20T09:00:00"' in SYSTEM_PROMPT
    assert 'timezone="UTC"' in SYSTEM_PROMPT


@pytest.mark.parametrize("suffix,expected_status", [("Z", 201), ("+01:00", 502)])
def test_two_source_times_through_mocked_sdk_and_persistence(
    api, monkeypatch, suffix, expected_status
):
    from test_extraction_validation_diagnostics import install

    booking = api.post(
        "/api/bookings", json={"title": "Synthetic datetime regression"}
    ).json()["id"]
    base = f"/api/bookings/{booking}"
    quotes = {
        "pickup": "Pickup: 20 November 2026 at 09:00 UTC.",
        "return_time": "Return: 22 November 2026 at 09:00 UTC.",
    }
    sources = []
    terms = {key: [] for key in quotes}
    for kind in ("quotation", "message"):
        response = api.post(
            base + "/sources/text",
            json={
                "source_type": kind,
                "original_text": "\n".join(quotes.values()),
            },
        )
        assert response.status_code == 201, response.text
        source = response.json()["id"]
        sources.append(source)
        for category, day in (("pickup", 20), ("return_time", 22)):
            terms[category].append(
                row(
                    category,
                    "known",
                    value=f"2026-11-{day}T09:00:00{suffix}",
                    timezone="UTC",
                    source_id=source,
                    quotation=quotes[category],
                )
            )
    client = install(monkeypatch, json.dumps(payload(**terms)))
    response = api.post(base + "/drafts", json={"source_ids": sources})
    assert response.status_code == expected_status, response.text
    client.models.generate_content.assert_called_once()
    if expected_status == 502:
        assert response.json()["detail"]["code"] == "ai_invalid_output"
        assert api.get(base + "/drafts").json() == []
        return
    draft = response.json()
    assert draft["status"] == "draft"
    assert draft["model_metadata"]["prompt_version"] == PROMPT_VERSION
    for category, day in (("pickup", 20), ("return_time", 22)):
        claims = draft["content"]["extraction"][category]
        assert len(claims) == 2
        assert all(
            c["value"]
            == {
                "local_datetime": f"2026-11-{day}T09:00:00",
                "timezone": "UTC",
            }
            for c in claims
        )
        assert {c["citations"][0]["source_id"] for c in claims} == set(sources)
        assert all(c["citations"][0]["quotation"] == quotes[category] for c in claims)
    assert api.get(base + f"/drafts/{draft['id']}").json() == draft
