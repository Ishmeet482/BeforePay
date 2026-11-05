from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_booking_comparisons import content, save
from test_cancellation_preview import approve, preview
from test_paypal_sandbox import capture, checkout_approve, order
from test_paypal_sandbox import context as context
from test_paypal_sandbox import paypal as paypal
from test_paypal_sandbox import settings as settings

from app.comparisons.provider import PolicyResult
from app.main import app
from app.policy_consistency.models import PolicyConsistencyCheck
from app.policy_consistency.provider import (
    GeminiConsistencyChecker,
    get_consistency_checker,
)
from app.policy_consistency.schemas import Output


def path(c):
    return f"/api/bookings/{c['booking']}/policy-consistency"


def install(status="potential_contradiction", before=None, modify=None):
    fake = Mock()

    def check(clauses):
        if before:
            before()
        output = {
            "findings": [
                {
                    "status": status,
                    "explanation": (
                        "Review all saved conditions and exceptions together; "
                        "no precedence selected."
                    ),
                    "references": [
                        {"clause_id": c["clause_id"], "quotation": c["text"]}
                        for c in clauses
                    ],
                }
            ]
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

    fake.check.side_effect = check
    app.dependency_overrides[get_consistency_checker] = lambda: fake
    return fake


def check(api, c, proposal=None, **changes):
    p = proposal or c["proposal"]
    return api.post(
        path(c),
        json={
            "proposal_id": p["id"],
            "proposal_fingerprint": p["fingerprint"],
            **changes,
        },
    )


@pytest.mark.parametrize("status", ["potential_contradiction", "needs_clarification"])
def test_findings_block_existing_approved_refunds_and_checkout(api, context, status):
    c = context
    base = f"/api/bookings/{c['booking']}"
    eligibility = api.get(base + "/checkout/eligibility").json()
    assert eligibility["eligible"]
    rules = api.get(base + "/cancellation/rules").json()
    merchant_rule = next(r for r in rules if r["target"]["kind"] == "proposal")
    assert preview(api, c, [merchant_rule]).json()["status"] == "ready"
    provider = install(status)
    saved = check(api, c)
    assert saved.status_code == 201, saved.text
    assert saved.json()["status"] == status and not saved.json()["stale"]
    assert "raw_response" not in saved.json()["model_metadata"]
    clauses = provider.check.call_args.args[0]
    assert len(clauses) == 3 and {c["category"] for c in clauses} == {
        "deposit_conditions",
        "cancellation_conditions",
    }
    blocked = api.get(base + "/checkout/eligibility").json()
    assert (
        not blocked["eligible"]
        and "merchant_policy_consistency_requires_clarification" in blocked["blockers"]
    )
    result = preview(api, c, [merchant_rule]).json()
    assert result["status"] == "needs_clarification" and result["previews"] == []
    assert "merchant_policy_consistency_requires_clarification" in result["blockers"]
    assert approve(api, c, merchant_rule).status_code == 409
    assert (
        api.post(
            base + "/checkout/approvals",
            json={
                "expected_context_fingerprint": eligibility["fingerprint"],
                "customer_label": "Buyer",
                "acknowledged": True,
            },
        ).status_code
        == 409
    )
    # A clean rerun cannot erase unresolved current findings.
    install("no_contradiction_found")
    assert check(api, c).status_code == 201
    assert not api.get(base + "/checkout/eligibility").json()["eligible"]
    assert api.get(base + "/checkout/attempts").json() == []


def test_clean_is_advisory_and_does_not_approve_rules(api, context):
    p = save(api, context, expected=context["proposal"]["id"]).json()
    before = api.get(f"/api/bookings/{context['booking']}/checkout/eligibility").json()
    install("no_contradiction_found")
    result = check(api, context, p)
    assert (
        result.status_code == 201
        and result.json()["status"] == "no_contradiction_found"
    )
    assert (
        api.get(f"/api/bookings/{context['booking']}/checkout/eligibility").json()
        == before
    )


def test_real_conflict_and_compatible_exception_context(api, context):
    data = content(context)
    data["deposit_conditions"] = [
        {"value": "The deposit is never refundable.", "ambiguous": False}
    ]
    data["cancellation_conditions"] = [
        {"value": "Every cancellation returns the deposit in full.", "ambiguous": False}
    ]
    conflicting = save(api, context, data, expected=context["proposal"]["id"]).json()
    fake = install()
    assert (
        check(api, context, conflicting).json()["status"] == "potential_contradiction"
    )
    assert (
        fake.check.call_args.args[0][1]["text"]
        == data["cancellation_conditions"][0]["value"]
    )
    data["deposit_conditions"][0]["value"] = (
        "The deposit is non-refundable except for cancellation "
        "at least 48 hours before pickup."
    )
    data["cancellation_conditions"][0]["value"] = (
        "Cancellation at least 48 hours before pickup refunds the deposit; "
        "later cancellation retains it."
    )
    conditional = save(api, context, data, expected=conflicting["id"]).json()
    install("no_contradiction_found")
    result = check(api, context, conditional)
    assert (
        result.status_code == 201
        and result.json()["status"] == "no_contradiction_found"
    )
    # The clean result never overrides older conservative rule/checkout checks.
    assert api.get(path(context) + "/state").json()["blockers"] == []
    assert api.get(path(context)).json()[1]["stale"]


@pytest.mark.parametrize("category", ["deposit_conditions", "cancellation_conditions"])
def test_missing_terms_decline_without_provider(api, context, category):
    data = content(context)
    data[category] = []
    p = save(api, context, data, expected=context["proposal"]["id"]).json()
    fake = install("no_contradiction_found")
    result = check(api, context, p)
    assert (
        result.status_code == 201 and result.json()["status"] == "needs_clarification"
    )
    assert result.json()["model_metadata"] is None
    fake.check.assert_not_called()


@pytest.mark.parametrize(
    "bad",
    ["unknown", "truncated", "duplicate", "one_side", "omit_exception", "extra_action"],
)
def test_unsupported_results_rejected(api, context, bad):
    def modify(output):
        f = output["findings"][0]
        if bad == "unknown":
            f["references"][0]["clause_id"] = "invented:0"
        elif bad == "truncated":
            f["references"][0]["quotation"] = "The deposit"
        elif bad == "duplicate":
            f["references"].append(f["references"][0])
        elif bad == "one_side":
            f["references"] = f["references"][:1]
        elif bad == "omit_exception":
            f["references"] = f["references"][:2]
        else:
            f["approve_checkout"] = True

    install("no_contradiction_found", modify=modify)
    assert check(api, context).status_code == 502
    assert api.get(path(context)).json() == []


def test_provider_failure_does_not_create_result_or_clear_blocker(api, context):
    install()
    assert check(api, context).status_code == 201
    fake = install()
    fake.check.side_effect = HTTPException(504, {"code": "ai_timeout"})
    assert check(api, context).status_code == 504
    assert len(api.get(path(context)).json()) == 1
    assert api.get(path(context) + "/state").json()["blockers"]
    assert fake.check.call_count == 1


def test_concurrent_edit_rejects_publication_and_stale_post(api, context):
    newer = []

    def change():
        newer.append(save(api, context, expected=context["proposal"]["id"]).json())

    install(before=change)
    assert check(api, context).status_code == 409
    assert api.get(path(context)).json() == []
    fake = install()
    assert check(api, context).status_code == 409
    fake.check.assert_not_called()
    assert (
        check(api, context, newer[0], proposal_fingerprint="0" * 64).status_code == 409
    )


def test_history_immutable_and_old_checks_not_current_guards(
    api, context, postgres_engine
):
    install()
    record = check(api, context).json()
    for stmt in (
        update(PolicyConsistencyCheck).values(status="no_contradiction_found"),
        delete(PolicyConsistencyCheck),
    ):
        with Session(postgres_engine) as s:
            with pytest.raises(DBAPIError):
                s.execute(stmt.where(PolicyConsistencyCheck.id == UUID(record["id"])))
            s.rollback()
    p = save(api, context, expected=context["proposal"]["id"]).json()
    old = api.get(path(context)).json()[0]
    assert old["stale"] and old["output"] == record["output"]
    assert api.get(path(context) + "/state").json()["blockers"] == []
    assert p["id"] != record["proposal_id"]


def test_prompt_and_structured_parse():
    checker = GeminiConsistencyChecker()
    assert "UNTRUSTED" in checker.prompt and "exceptions" in checker.prompt
    assert "precedence" in checker.prompt and "EVERY" in checker.prompt
    with pytest.raises(ValueError):
        checker.parse('{"findings":[],"approve":true}')
    with pytest.raises(ValueError):
        Output.model_validate(
            {
                "findings": [
                    {
                        "status": "no_contradiction_found",
                        "explanation": "ok",
                        "references": [],
                    },
                    {
                        "status": "needs_clarification",
                        "explanation": "unknown",
                        "references": [],
                    },
                ]
            }
        )


def test_saved_checkout_approval_cannot_capture_after_finding(api, context, paypal):
    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)
    paypal.remote_status = "APPROVED"
    install()
    assert check(api, context).status_code == 201
    assert capture(api, context, attempt).status_code == 409
    assert paypal.capture_keys == []


def test_historical_receipt_unchanged_after_finding(api, context, paypal):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"
    assert capture(api, context, attempt).json()["status"] == "completed"
    url = f"/api/bookings/{context['booking']}/checkout/receipt"
    original = api.get(url).json()
    install("needs_clarification")
    assert check(api, context).status_code == 201
    assert api.get(url).json() == original


def test_oversized_context_rejected_without_inference(api, context):
    data = content(context)
    data["deposit_conditions"] = [
        {"value": "Long saved policy " * 100, "ambiguous": False} for _ in range(30)
    ]
    response = save(api, context, data, expected=context["proposal"]["id"])
    assert response.status_code == 201, response.text
    p = response.json()
    fake = install()
    assert check(api, context, p).status_code == 413
    fake.check.assert_not_called()


def test_adapter_uses_existing_offline_transport_seam(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from google.genai import types
    from pydantic import SecretStr

    from app.core.config import Settings
    from app.drafts import provider as gemini

    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                finish_reason=types.FinishReason.STOP,
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            text=(
                                '{"findings":[{"status":"needs_clarification",'
                                '"explanation":"Scopes unclear.","references":[]}]}'
                            ),
                            thought=False,
                            function_call=None,
                            executable_code=None,
                        )
                    ]
                ),
            )
        ],
        model_version="mock",
        response_id="mock",
    )
    constructor = MagicMock()
    constructor.return_value.__enter__.return_value = client
    monkeypatch.setattr(gemini.genai, "Client", constructor)
    monkeypatch.setattr(
        gemini,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=SecretStr("fake")),
    )
    result = GeminiConsistencyChecker().check(
        [{"clause_id": "deposit_conditions:0", "text": "UNTRUSTED sample"}]
    )
    assert result.output.findings[0].status == "needs_clarification"
    options = constructor.call_args.kwargs["http_options"]
    assert options.timeout == 60000 and options.retry_options.attempts == 1
    call = client.models.generate_content.call_args.kwargs
    assert "UNTRUSTED sample" in call["contents"].parts[0].text
    assert call["config"].automatic_function_calling.disable
    assert call["config"].max_output_tokens == 8000
