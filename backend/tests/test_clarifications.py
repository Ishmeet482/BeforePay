import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from google.genai import types
from pydantic import SecretStr
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_booking_comparisons import compare, content, fake_policy, save
from test_customer_review import confirm, seed_review, state

from app.clarifications.models import ClarificationSuggestion
from app.clarifications.provider import GeminiClarifier, get_clarifier
from app.clarifications.schemas import SuggestionOutput
from app.comparisons.provider import PolicyResult
from app.core.config import Settings
from app.drafts import provider as gemini
from app.main import app


@pytest.fixture
def discrepancy(api, postgres_engine):
    context = seed_review(api, postgres_engine)
    assert confirm(api, context).status_code == 201
    data = content(context)
    data["deposit_conditions"][0]["value"] = "The deposit is non-refundable."
    proposal = save(api, context, data).json()
    fake_policy("differs")
    comparison = compare(api, context, proposal).json()
    return context, proposal, comparison


def path(d):
    c, _, comparison = d
    return f"/api/bookings/{c['booking']}/comparisons/{comparison['id']}/clarifications"


def generate(api, d, category="deposit_conditions", **changes):
    return api.post(
        path(d),
        json={
            "comparison_fingerprint": d[2]["fingerprint"],
            "category": category,
            **changes,
        },
    )


def install(before=None, modify=None):
    provider = Mock()

    def run(context):
        if before:
            before()
        output = {
            "status": "suggested",
            "question": (
                "Will the deposit be refundable on undamaged return as agreed, "
                "or is the final booking changing this condition?"
            ),
            "explanation": (
                "The saved deposit terms describe different refund obligations."
            ),
            "references": [
                {"term_id": t["term_id"], "quotation": t["text"]}
                for t in context["terms"]
            ],
        }
        if modify:
            modify(output)
        return PolicyResult(
            SimpleNamespace(model_dump=lambda: output),
            {
                "provider": "gemini",
                "prompt_version": "mock",
                "raw_response": "must not persist",
            },
        )

    provider.suggest.side_effect = run
    app.dependency_overrides[get_clarifier] = lambda: provider
    return provider


def test_success_is_advisory_exact_and_immutable(api, discrepancy, postgres_engine):
    original = state(api, discrepancy[0])
    base = f"/api/bookings/{discrepancy[0]['booking']}"
    eligibility = api.get(base + "/checkout/eligibility").json()
    provider = install()
    response = generate(api, discrepancy)
    assert response.status_code == 201, response.text
    result = response.json()
    assert not result["stale"] and result["output"]["status"] == "suggested"
    assert result["comparison_fingerprint"] == discrepancy[2]["fingerprint"]
    assert result["confirmation_id"] == discrepancy[2]["confirmation_id"]
    assert result["agreement_id"] == discrepancy[0]["agreement"]["id"]
    assert result["proposal_id"] == discrepancy[1]["id"]
    assert (
        result["supporting_terms"][0]["citations"][0]["source_id"]
        == discrepancy[0]["source"]["id"]
    )
    assert result["supporting_terms"][1]["origin"] == "merchant_entered"
    assert result["supporting_terms"][1]["citations"] == []
    assert "raw_response" not in result["model_metadata"]
    context = provider.suggest.call_args.args[0]
    assert set(context) == {"category", "status", "reason", "terms"}
    assert "cancellation_conditions" not in json.dumps(context)
    assert "customer_label" not in json.dumps(context)
    assert api.get(path(discrepancy)).json() == [result]
    assert state(api, discrepancy[0]) == original
    assert api.get(base + "/checkout/eligibility").json() == eligibility
    assert api.get(base + "/checkout/attempts").json() == []
    assert (
        api.get(base + f"/comparisons/{discrepancy[2]['id']}").json() == discrepancy[2]
    )
    for statement in [
        update(ClarificationSuggestion).values(category="amounts"),
        delete(ClarificationSuggestion),
    ]:
        with Session(postgres_engine) as session:
            with pytest.raises(DBAPIError):
                session.execute(
                    statement.where(ClarificationSuggestion.id == UUID(result["id"]))
                )
                session.commit()
            session.rollback()


@pytest.mark.parametrize(
    "bad",
    ["unknown", "quote", "one_side", "duplicate", "action", "blank", "not_question"],
)
def test_invalid_output_is_rejected_without_record(api, discrepancy, bad):
    def modify(output):
        if bad == "unknown":
            output["references"][0]["term_id"] = "agreement:999"
        elif bad == "quote":
            output["references"][0]["quotation"] = "invented source condition"
        elif bad == "one_side":
            output["references"] = [output["references"][0]] * 2
        elif bad == "duplicate":
            output["references"].append(output["references"][0])
        elif bad == "action":
            output["resolved"] = True
        elif bad == "not_question":
            output["question"] = "Approve the final booking now."
        else:
            output["question"] = "   "

    provider = install(modify=modify)
    response = generate(api, discrepancy)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ai_invalid_output"
    provider.suggest.assert_called_once()
    assert api.get(path(discrepancy)).json() == []


def test_model_can_decline_insufficient_context(api, discrepancy):
    def insufficient(output):
        output.update(
            status="needs_more_information",
            question=None,
            explanation="The merchant must supply the missing exception details.",
            references=[],
        )

    install(modify=insufficient)
    result = generate(api, discrepancy)
    assert result.status_code == 201
    assert result.json()["output"]["status"] == "needs_more_information"
    assert result.json()["output"]["question"] is None


def test_missing_saved_terms_never_invoke_provider(api, discrepancy):
    c, old, _ = discrepancy
    data = content(c)
    data["deposit_conditions"] = []
    proposal = save(api, c, data, expected=old["id"]).json()
    comparison = compare(api, c, proposal).json()
    d = c, proposal, comparison
    provider = install()
    result = generate(api, d)
    assert result.status_code == 201, result.text
    assert result.json()["output"]["status"] == "needs_more_information"
    assert result.json()["model_metadata"] is None
    provider.suggest.assert_not_called()


def test_provider_failure_no_retry_or_persistence(api, discrepancy):
    provider = install()
    provider.suggest.side_effect = gemini.provider_error(
        "ai_timeout", "Safe provider timeout.", 504
    )
    assert generate(api, discrepancy).status_code == 504
    provider.suggest.assert_called_once()
    assert api.get(path(discrepancy)).json() == []


@pytest.mark.parametrize("change", ["proposal", "evidence", "comparison"])
def test_changes_during_inference_rejected(api, discrepancy, change):
    c, proposal, _ = discrepancy

    def mutate():
        if change == "proposal":
            assert save(api, c, content(c), expected=proposal["id"]).status_code == 201
        elif change == "evidence":
            assert (
                api.post(
                    f"/api/bookings/{c['booking']}/sources/text",
                    json={
                        "source_type": "message",
                        "original_text": "New evidence requires review.",
                    },
                ).status_code
                == 201
            )
        else:
            fake_policy("differs")
            assert compare(api, c, proposal).status_code == 201

    install(before=mutate)
    response = generate(api, discrepancy)
    assert response.status_code == 409, response.text
    assert api.get(path(discrepancy)).json() == []


def test_saved_suggestion_becomes_stale(api, discrepancy):
    install()
    saved = generate(api, discrepancy).json()
    c, proposal, _ = discrepancy
    assert save(api, c, content(c), expected=proposal["id"]).status_code == 201
    read = api.get(path(discrepancy)).json()[0]
    assert read["id"] == saved["id"] and read["output"] == saved["output"]
    assert read["stale"] and "merchant_booking_changed" in read["stale_reasons"]
    provider = install()
    assert generate(api, discrepancy).status_code == 409
    provider.suggest.assert_not_called()


def test_matching_wrong_fingerprint_and_cross_booking_rejected(api, discrepancy):
    provider = install()
    assert generate(api, discrepancy, category="equipment").status_code == 422
    assert (
        generate(api, discrepancy, comparison_fingerprint="0" * 64).status_code == 409
    )
    other = api.post("/api/bookings", json={"title": "Other synthetic booking"}).json()[
        "id"
    ]
    assert (
        api.post(
            path(discrepancy).replace(discrepancy[0]["booking"], other),
            json={
                "comparison_fingerprint": discrepancy[2]["fingerprint"],
                "category": "deposit_conditions",
            },
        ).status_code
        == 404
    )
    assert (
        api.get(
            path(discrepancy).replace(discrepancy[2]["id"], str(uuid4()))
        ).status_code
        == 404
    )
    provider.suggest.assert_not_called()


def test_provider_wire_contract_and_timeout(monkeypatch):
    monkeypatch.setattr(
        gemini,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=SecretStr("fake-offline-key")),
    )
    client = Mock()
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(gemini.genai, "Client", factory)
    output = {
        "status": "needs_more_information",
        "question": None,
        "explanation": "Missing merchant context.",
        "references": [],
    }
    client.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason="STOP",
                content=types.Content(parts=[types.Part(text=json.dumps(output))]),
            )
        ]
    )
    assert GeminiClarifier().suggest(
        {"category": "equipment", "terms": []}
    ).output == SuggestionOutput(**output)
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 60000 and options.retry_options.attempts == 1
    assert factory.call_args.kwargs["vertexai"] is False
    config = client.models.generate_content.call_args.kwargs["config"]
    assert (
        config.automatic_function_calling.disable and config.max_output_tokens == 8000
    )
    assert "UNTRUSTED DATA" in config.system_instruction
    client.models.generate_content.side_effect = httpx.ReadTimeout(
        "private source must not leak"
    )
    with pytest.raises(HTTPException) as error:
        GeminiClarifier().suggest({})
    assert error.value.status_code == 504
    assert "private source" not in str(error.value.detail)
    assert client.models.generate_content.call_count == 2


@pytest.mark.parametrize(
    "category",
    ["equipment", "included_items", "pickup", "return_time", "currency", "amounts"],
)
def test_typed_term_references_retain_original_evidence(api, discrepancy, category):
    c, old, _ = discrepancy
    data = content(c)
    if category in {"equipment", "included_items"}:
        data[category][0]["quantity"] += 1
    elif category in {"pickup", "return_time"}:
        data[category][0]["value"]["local_datetime"] = "2026-11-02T10:00:00"
    elif category == "currency":
        data[category][0]["value"] = "EUR"
    else:
        data[category][0]["amount"] = "201.00"
    proposal = save(api, c, data, expected=old["id"]).json()
    comparison = compare(api, c, proposal).json()
    install(
        modify=lambda output: output.update(
            question="Which saved values should the final booking specify?"
        )
    )
    response = generate(api, (c, proposal, comparison), category=category)
    assert response.status_code == 201, response.text
    assert response.json()["supporting_terms"][0]["citations"]


def test_placeholder_policy_is_insufficient_without_model(api, discrepancy):
    c, old, _ = discrepancy
    data = content(c)
    data["deposit_conditions"][0]["value"] = "Unknown"
    proposal = save(api, c, data, expected=old["id"]).json()
    comparison = compare(api, c, proposal).json()
    provider = install()
    result = generate(api, (c, proposal, comparison))
    assert (
        result.status_code == 201
        and result.json()["output"]["status"] == "needs_more_information"
    )
    provider.suggest.assert_not_called()


def test_new_comparison_stales_existing_suggestion(api, discrepancy):
    install()
    saved = generate(api, discrepancy).json()
    fake_policy("differs")
    assert compare(api, discrepancy[0], discrepancy[1]).status_code == 201
    read = api.get(path(discrepancy)).json()[0]
    assert read["id"] == saved["id"] and read["stale"]
    assert "comparison_superseded" in read["stale_reasons"]
