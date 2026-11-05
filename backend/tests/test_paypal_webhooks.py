"""Offline provider responses; disposable PostgreSQL tests."""

# Fixtures are imported for pytest discovery and injected by parameter name.
# ruff: noqa: F811

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_paypal_sandbox import (  # noqa: F401
    checkout_approve,
    context,
    order,
    path,
    paypal,
    settings,
)

from app.payments import service
from app.payments.models import PaymentAttempt, PayPalWebhookEvent
from app.payments.provider import PayPalFailure, SandboxPayPal

URL = "/api/paypal/sandbox/webhook"
HEADERS = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api.sandbox.paypal.com/v1/notifications/certs/TEST",
    "paypal-transmission-id": "transmission-1",
    "paypal-transmission-sig": "fake-signature",
    "paypal-transmission-time": "2026-11-02T00:00:00Z",
}


def notification(paypal, kind="PAYMENT.CAPTURE.COMPLETED"):
    resource = {
        "id": paypal.capture_id,
        "supplementary_data": {"related_ids": {"order_id": paypal.order_id}},
    }
    if kind.startswith("CHECKOUT.ORDER."):
        resource["id"] = paypal.order_id
    return {"id": "WH-" + uuid4().hex, "event_type": kind, "resource": resource}


def test_verified_webhook_needs_no_demo_cookie_or_csrf(api, context, paypal, setup):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, base_url="https://testserver") as provider:
        event = notification(paypal)
        assert provider.post(URL, json=event).json() == {"status": "processed"}
        assert provider.post(URL, json=event).json() == {"status": "duplicate"}
    paypal.verify_webhook.assert_called()
    assert api.get(path(context) + "/receipt").json()["capture_id"] == paypal.capture_id


@pytest.fixture
def setup(api, context, paypal, postgres_engine):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.verify_webhook = Mock()
    with Session(postgres_engine) as session:
        record = session.get(PaymentAttempt, UUID(attempt["id"]))
        record.capture_requested_at = service.now()
        record.status = "capture_uncertain"
        session.commit()
    paypal.remote_status = paypal.capture_status = "COMPLETED"
    return attempt


def test_browser_loss_concurrent_duplicates_and_out_of_order(
    api, context, paypal, setup, postgres_engine
):
    event = notification(paypal)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: api.post(URL, json=event), range(2)))
    assert sorted(r.json()["status"] for r in responses) == ["duplicate", "processed"]
    receipt = api.get(path(context) + "/receipt").json()
    assert receipt["capture_id"] == paypal.capture_id
    assert receipt["approval_id"] == setup["approval_id"]
    paypal.remote_status, paypal.capture_status = "APPROVED", None
    for kind in (
        "CHECKOUT.ORDER.APPROVED",
        "PAYMENT.CAPTURE.PENDING",
        "PAYMENT.CAPTURE.DENIED",
    ):
        assert api.post(URL, json=notification(paypal, kind)).status_code == 200
    assert api.get(path(context) + "/receipt").json() == receipt
    assert paypal.get_calls == 1 and paypal.capture_keys == []
    with Session(postgres_engine) as session:
        saved = session.get(PayPalWebhookEvent, event["id"])
        assert saved.attempt_id == UUID(setup["id"])
        with pytest.raises(DBAPIError):
            session.execute(
                update(PayPalWebhookEvent)
                .where(PayPalWebhookEvent.event_id == event["id"])
                .values(digest="changed")
            )
            session.commit()


def test_approval_and_event_completed_not_proof(api, context, paypal, setup):
    paypal.remote_status, paypal.capture_status = "APPROVED", None
    for kind in ("CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED"):
        assert api.post(URL, json=notification(paypal, kind)).status_code == 200
    assert api.get(path(context) + "/receipt").status_code == 404
    assert paypal.capture_keys == []


@pytest.mark.parametrize(
    "bad",
    [
        "amount",
        "payee",
        "currency",
        "custom_id",
        "order_id",
        "capture_amount",
        "timeout",
    ],
)
def test_reconciliation_failure_rolls_back_claim_for_redelivery(
    api, context, paypal, setup, postgres_engine, bad
):
    event = notification(paypal)
    original = paypal.get
    if bad == "timeout":
        paypal.get = Mock(side_effect=PayPalFailure("paypal_timeout"))
    else:
        paypal.bad = bad
    assert api.post(URL, json=event).status_code == 503
    with Session(postgres_engine) as session:
        assert session.get(PayPalWebhookEvent, event["id"]) is None
        assert (
            session.get(PaymentAttempt, UUID(setup["id"])).status == "capture_uncertain"
        )
    assert api.get(path(context) + "/receipt").status_code == 404
    paypal.get, paypal.bad = original, None
    assert api.post(URL, json=event).json()["status"] == "processed"
    assert api.get(path(context) + "/receipt").status_code == 200


def test_bad_signature_and_verification_outage(api, paypal, setup, postgres_engine):
    event = notification(paypal)
    for error, status in [
        (HTTPException(400, "Invalid"), 400),
        (PayPalFailure("paypal_timeout"), 503),
    ]:
        paypal.verify_webhook.side_effect = error
        assert api.post(URL, json=event).status_code == status
    assert paypal.get_calls == 0
    with Session(postgres_engine) as session:
        assert session.get(PayPalWebhookEvent, event["id"]) is None


def test_unknown_malformed_and_conflicting_events(api, paypal, setup):
    event = notification(paypal)
    unknown = copy.deepcopy(event)
    unknown["resource"]["supplementary_data"]["related_ids"]["order_id"] = "UNKNOWN"
    assert api.post(URL, json=unknown).json()["status"] == "ignored"
    assert (
        api.post(URL, json={**event, "event_type": "UNSUPPORTED"}).json()["status"]
        == "ignored"
    )
    assert api.post(URL, json={**event, "resource": []}).status_code == 400
    assert paypal.get_calls == 0
    assert api.post(URL, json=event).status_code == 200
    assert api.post(URL, json={**event, "summary": "changed"}).status_code == 409


def test_pending_then_completed_uses_current_provider_state(
    api, context, paypal, setup
):
    paypal.capture_status = "PENDING"
    event = notification(paypal)
    assert api.post(URL, json=event).status_code == 200
    assert api.get(path(context) + "/receipt").status_code == 404
    paypal.capture_status = "COMPLETED"
    assert api.post(URL, json=event).json()["status"] == "duplicate"
    assert (
        api.post(URL, json=notification(paypal, "PAYMENT.CAPTURE.PENDING")).status_code
        == 200
    )
    assert api.get(path(context) + "/receipt").status_code == 200


@pytest.mark.parametrize("result", ["SUCCESS", "FAILURE", None])
def test_offline_verification_contract(monkeypatch, settings, result):
    safe = settings.model_copy(update={"paypal_sandbox_webhook_id": "REGISTERED"})
    monkeypatch.setattr("app.payments.provider.get_settings", lambda: safe)
    requests = []
    event = {"id": "WH-TEST", "resource": {"arbitrary": [1, {"nested": True}]}}

    def handler(request):
        requests.append(request)
        assert request.url.host == "api-m.sandbox.paypal.com"
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "fake-token"})
        assert request.url.path == "/v1/notifications/verify-webhook-signature"
        data = json.loads(request.content)
        assert data["webhook_id"] == "REGISTERED" and data["webhook_event"] == event
        for key, value in HEADERS.items():
            assert data[key.removeprefix("paypal-").replace("-", "_")] == value
        return httpx.Response(200, json={"verification_status": result})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        SandboxPayPal, "_client", lambda _: httpx.Client(transport=transport)
    )
    provider = SandboxPayPal()
    if result == "SUCCESS":
        provider.verify_webhook(event, HEADERS)
    else:
        with pytest.raises(HTTPException) as error:
            provider.verify_webhook(event, HEADERS)
        assert error.value.status_code == 400
    assert len(requests) == 2


def test_missing_config_and_headers(settings, monkeypatch):
    provider = SandboxPayPal()
    with pytest.raises(HTTPException) as error:
        provider.verify_webhook({}, HEADERS)
    assert error.value.status_code == 503
    safe = settings.model_copy(update={"paypal_sandbox_webhook_id": "FAKE"})
    monkeypatch.setattr("app.payments.provider.get_settings", lambda: safe)
    for missing in HEADERS:
        with pytest.raises(HTTPException) as error:
            provider.verify_webhook(
                {}, {k: v for k, v in HEADERS.items() if k != missing}
            )
        assert error.value.status_code == 400


def test_historical_completion_preserves_approval(api, context, paypal, setup):
    from test_booking_comparisons import save

    assert save(api, context, expected=context["proposal"]["id"]).status_code == 201
    assert api.post(URL, json=notification(paypal)).status_code == 200
    receipt = api.get(path(context) + "/receipt").json()
    assert receipt["context"]["proposal_id"] == context["proposal"]["id"]
    assert receipt["approval_id"] == setup["approval_id"]
    assert paypal.capture_keys == []
