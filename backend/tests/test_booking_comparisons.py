from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
from google.genai import errors, types
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_customer_review import confirm, revise, seed_review, state

from app.comparisons.models import BookingComparison, ProposalVersion
from app.comparisons.provider import (
    GeminiPolicyComparator,
    PolicyResult,
    get_policy_comparator,
)
from app.comparisons.schemas import PolicyOutput
from app.core.config import Settings
from app.drafts import provider as gemini
from app.main import app


@pytest.fixture
def context(api, postgres_engine):
    context = seed_review(api, postgres_engine)
    assert confirm(api, context).status_code == 201
    return context


def content(context):
    data = {
        category: [{**e["claim"], "citations": []} for e in entries]
        for category, entries in context["agreement"]["content"]["extraction"].items()
    }
    data["included_items_none"] = False
    return data


def save(api, context, data=None, expected=None):
    return api.post(
        f"/api/bookings/{context['booking']}/merchant-bookings",
        json={
            "expected_latest_id": expected,
            "merchant_label": "Local merchant",
            "reason": "Synthetic proposal test",
            "content": data or content(context),
        },
    )


def compare(api, context, proposal, **overrides):
    return api.post(
        f"/api/bookings/{context['booking']}/comparisons",
        json={
            "agreement_id": context["agreement"]["id"],
            "agreement_fingerprint": context["agreement"]["fingerprint"],
            "proposal_id": proposal["id"],
            "proposal_fingerprint": proposal["fingerprint"],
            **overrides,
        },
    )


def install(comparator):
    app.dependency_overrides[get_policy_comparator] = lambda: comparator


def fake_policy(status="matches", before=None, bad_quote=False):
    fake = Mock()

    def run(policies):
        if before:
            before()
        return PolicyResult(
            PolicyOutput(
                results=[
                    {
                        "category": p["category"],
                        "status": status,
                        "agreement_quote": "Invented"
                        if bad_quote
                        else p["agreement_text"],
                        "proposal_quote": p["proposal_text"],
                    }
                    for p in policies
                ]
            ),
            {"provider": "gemini", "prompt_version": "mock", "response_id": "mock"},
        )

    fake.compare.side_effect = run
    install(fake)
    return fake


def results(response):
    assert response.status_code == 201, response.text
    return {r["category"]: r for r in response.json()["results"]}


def test_matching_persisted_versions_do_not_change_confirmation(
    api, context, postgres_engine
):
    original = state(api, context)
    fake = Mock()
    install(fake)
    proposal = save(api, context).json()
    response = compare(api, context, proposal)
    assert all(r["status"] == "matches" for r in results(response).values())
    fake.compare.assert_not_called()
    record = response.json()
    assert not record["stale"]
    assert record["agreement_fingerprint"] == context["agreement"]["fingerprint"]
    assert record["proposal_fingerprint"] == proposal["fingerprint"]
    path = f"/api/bookings/{context['booking']}"
    assert api.get(f"{path}/comparisons/{record['id']}").json() == record
    assert api.get(f"{path}/merchant-bookings/{proposal['id']}").json() == proposal
    assert api.get(f"{path}/comparisons").json()[0] == record
    assert state(api, context) == original
    with Session(postgres_engine) as session:
        assert session.get(BookingComparison, UUID(record["id"])) is not None


@pytest.mark.parametrize(
    "category",
    ["equipment", "included_items", "amounts", "pickup", "return_time", "currency"],
)
def test_deterministic_mismatches(api, context, category):
    data = content(context)
    if category in {"equipment", "included_items"}:
        data[category][0]["quantity"] += 1
    elif category == "amounts":
        data[category][0]["amount"] = "201.00"
    elif category in {"pickup", "return_time"}:
        data[category][0]["value"]["local_datetime"] = "2026-11-02T10:00:00"
    else:
        data[category][0]["value"] = "EUR"
    fake = Mock()
    install(fake)
    result = results(compare(api, context, save(api, context, data).json()))
    assert result[category]["status"] == "differs"
    fake.compare.assert_not_called()


@pytest.mark.parametrize(
    "category",
    [
        "equipment",
        "amounts",
        "pickup",
        "deposit_conditions",
        "cancellation_conditions",
        "included_items",
    ],
)
def test_missing_terms_stay_unknown(api, context, category):
    data = content(context)
    data[category] = []
    fake = Mock()
    install(fake)
    result = results(compare(api, context, save(api, context, data).json()))
    assert result[category]["status"] == "needs_clarification"
    fake.compare.assert_not_called()


def test_equivalent_timezone_instant_and_decimal_representation(api, context):
    data = content(context)
    data["pickup"][0]["value"] = {
        "local_datetime": "2026-11-01T14:30:00",
        "timezone": "+05:30",
    }
    data["amounts"][0]["amount"] = "200.0000"
    result = results(compare(api, context, save(api, context, data).json()))
    assert result["pickup"]["status"] == result["amounts"]["status"] == "matches"


@pytest.mark.parametrize("status", ["matches", "differs", "needs_clarification"])
def test_policy_wording_uses_mock_provider_with_support(api, context, status):
    data = content(context)
    data["cancellation_conditions"][0]["value"] = (
        "Full refund when cancelled 48 hours or more before pickup."
    )
    fake = fake_policy(status)
    response = compare(api, context, save(api, context, data).json())
    policy = results(response)["cancellation_conditions"]
    assert policy["status"] == status
    assert policy["basis"] == "gemini_policy"
    assert policy["proposal_quote"] == data["cancellation_conditions"][0]["value"]
    assert response.json()["model_metadata"]["provider"] == "gemini"
    fake.compare.assert_called_once()
    assert set(fake.compare.call_args.args[0][0]) == {
        "category",
        "agreement_text",
        "proposal_text",
    }


def test_same_usd_200_total_does_not_hide_nonrefundable_deposit(api, context):
    data = content(context)
    data["amounts"] = [
        {"kind": k, "label": k, "amount": a, "currency": "USD", "ambiguous": False}
        for k, a in [
            ("rental_total", "120"),
            ("deposit", "80"),
            ("total_payable", "200"),
        ]
    ]
    corrected = revise(
        api,
        context,
        [
            {
                "category": "amounts",
                "reason": "Separate components",
                "items": data["amounts"],
            }
        ],
    ).json()
    assert confirm(api, context, corrected).status_code == 201
    context = {**context, "agreement": corrected}
    data["deposit_conditions"][0]["value"] = "The USD 80 deposit is non-refundable."
    fake_policy("differs")
    result = results(compare(api, context, save(api, context, data).json()))
    assert result["amounts"]["status"] == "matches"
    assert result["deposit_conditions"]["status"] == "differs"


def test_untrusted_provider_cannot_invent_policy_support(api, context, postgres_engine):
    data = content(context)
    data["deposit_conditions"][0]["value"] = "A different policy."
    fake_policy(bad_quote=True)
    response = compare(api, context, save(api, context, data).json())
    assert (
        response.status_code == 502
        and response.json()["detail"]["code"] == "ai_invalid_output"
    )
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(BookingComparison).where(
                    BookingComparison.booking_id == UUID(context["booking"])
                )
            )
            is None
        )


def test_new_proposal_marks_comparison_stale_without_invalidating_baseline(
    api, context
):
    first = save(api, context).json()
    record = compare(api, context, first).json()
    assert save(api, context, expected=first["id"]).status_code == 201
    assert state(api, context)["confirmation_current"]
    stored = api.get(
        f"/api/bookings/{context['booking']}/comparisons/{record['id']}"
    ).json()
    assert stored["stale"] and "merchant_booking_changed" in stored["stale_reasons"]
    assert compare(api, context, first).status_code == 409
    assert save(api, context).status_code == 409


@pytest.mark.parametrize("change", ["agreement", "evidence"])
def test_baseline_changes_stale_previous_result(api, context, change):
    record = compare(api, context, save(api, context).json()).json()
    if change == "agreement":
        assert revise(api, context).status_code == 201
    else:
        assert (
            api.post(
                f"/api/bookings/{context['booking']}/sources/text",
                json={"source_type": "message", "original_text": "New evidence"},
            ).status_code
            == 201
        )
    stored = api.get(
        f"/api/bookings/{context['booking']}/comparisons/{record['id']}"
    ).json()
    assert (
        stored["stale"] and "confirmation_no_longer_current" in stored["stale_reasons"]
    )


def test_concurrent_proposal_change_during_ai_is_rejected(api, context):
    data = content(context)
    data["deposit_conditions"][0]["value"] = "Refundable on return."
    proposal = save(api, context, data).json()
    fake_policy(before=lambda: save(api, context, data, proposal["id"]))
    response = compare(api, context, proposal)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_merchant_booking"


def test_cross_booking_and_fingerprint_protection(api, context):
    proposal = save(api, context).json()
    assert (
        compare(api, context, proposal, agreement_fingerprint="0" * 64).status_code
        == 409
    )
    assert (
        compare(api, context, proposal, proposal_fingerprint="0" * 64).status_code
        == 409
    )
    assert compare(api, context, {**proposal, "id": str(uuid4())}).status_code == 404
    other = api.post("/api/bookings", json={"title": "Other"}).json()["id"]
    assert (
        api.get(f"/api/bookings/{other}/merchant-bookings/{proposal['id']}").status_code
        == 404
    )


@pytest.mark.parametrize("table", [ProposalVersion, BookingComparison])
@pytest.mark.parametrize("mutation", ["update", "delete"])
def test_proposals_and_comparisons_immutable(
    api, context, postgres_engine, table, mutation
):
    proposal = save(api, context).json()
    record = compare(api, context, proposal).json()
    ident = proposal["id"] if table == ProposalVersion else record["id"]
    with Session(postgres_engine) as session:
        statement = (
            delete(table)
            if mutation == "delete"
            else update(table).values(fingerprint="0" * 64)
        )
        with pytest.raises(DBAPIError):
            session.execute(statement.where(table.id == UUID(ident)))
        session.rollback()


def test_unconfirmed_baseline_cannot_compare(api, postgres_engine):
    context = seed_review(api, postgres_engine)
    proposal = save(api, context).json()
    fake = Mock()
    install(fake)
    assert compare(api, context, proposal).status_code == 409
    fake.compare.assert_not_called()


@pytest.mark.parametrize(
    "error,code,status",
    [
        (
            errors.ClientError(
                429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}
            ),
            "ai_rate_limited",
            503,
        ),
        (
            errors.ClientError(
                400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}}
            ),
            "ai_unavailable",
            502,
        ),
        (httpx.ReadTimeout("private"), "ai_timeout", 504),
    ],
)
def test_policy_provider_failures_have_no_fallback(monkeypatch, error, code, status):
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    monkeypatch.setattr(
        gemini,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=SecretStr("fake-test-key")),
    )
    client = Mock()
    client.models.generate_content.side_effect = error
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(gemini.genai, "Client", factory)
    with pytest.raises(HTTPException) as caught:
        GeminiPolicyComparator().compare([])
    assert caught.value.status_code == status and caught.value.detail["code"] == code
    assert caught.value.__cause__ is error
    client.models.generate_content.assert_called_once()


def test_policy_provider_request_and_invalid_output(monkeypatch):
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    monkeypatch.setattr(
        gemini,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=SecretStr("fake-test-key")),
    )
    client = Mock()
    client.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason="STOP",
                content=types.Content(parts=[types.Part(text='{"results": []}')]),
            )
        ]
    )
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(gemini.genai, "Client", factory)
    with pytest.raises(HTTPException) as caught:
        GeminiPolicyComparator().compare([])
    assert caught.value.detail["code"] == "ai_invalid_output"
    options = factory.call_args.kwargs["http_options"]
    assert (
        options.retry_options.attempts == 1
        and factory.call_args.kwargs["vertexai"] is False
    )
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.candidate_count is None and config.automatic_function_calling.disable
    assert config.response_mime_type == "application/json"


def test_policy_missing_credentials_clear_error(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        gemini, "get_settings", lambda: Settings(_env_file=None, gemini_api_key=None)
    )
    with pytest.raises(HTTPException) as caught:
        GeminiPolicyComparator().compare([])
    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "ai_not_configured"


@pytest.mark.parametrize("category", ["deposit_conditions", "cancellation_conditions"])
def test_unknown_placeholder_policy_never_invents_meaning(api, context, category):
    data = content(context)
    data[category][0]["value"] = "Unknown"
    fake = Mock()
    install(fake)
    result = results(compare(api, context, save(api, context, data).json()))
    assert result[category]["status"] == "needs_clarification"
    fake.compare.assert_not_called()


def test_evidence_changed_during_policy_inference_rejects_publication(api, context):
    data = content(context)
    data["deposit_conditions"][0]["value"] = "Deposit is returned after inspection."
    proposal = save(api, context, data).json()

    def changed():
        assert (
            api.post(
                f"/api/bookings/{context['booking']}/sources/text",
                json={
                    "source_type": "message",
                    "original_text": "Another relevant source",
                },
            ).status_code
            == 201
        )

    fake_policy(before=changed)
    response = compare(api, context, proposal)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "current_confirmation_required"


@pytest.mark.parametrize(
    "case", ["money_float", "unknown_kind", "fake_citation", "negative_quantity"]
)
def test_proposal_reuses_strict_domain_constraints(api, context, case):
    data = content(context)
    if case == "money_float":
        data["amounts"][0]["amount"] = 200.0
    elif case == "unknown_kind":
        data["amounts"][0]["kind"] = "additional_total"
    elif case == "fake_citation":
        data["equipment"][0]["citations"] = [
            {"source_id": str(uuid4()), "quotation": "Fake", "page_number": None}
        ]
    else:
        data["equipment"][0]["quantity"] = -1
    assert save(api, context, data).status_code == 422
