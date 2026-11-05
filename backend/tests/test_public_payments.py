"""Public mode never executes buyer payment actions, even with sandbox enabled."""

# Imported fixtures are requested by pytest by name.
# ruff: noqa: F811
from unittest.mock import Mock

from fastapi.testclient import TestClient
from test_demo_sessions import visitor
from test_paypal_sandbox import (  # noqa: F401
    capture,
    checkout_approve,
    context,
    order,
    path,
    paypal,
    settings,
)
from test_paypal_webhooks import URL, notification, setup  # noqa: F401
from test_public_admission import controls  # noqa: F401

from app.main import app


def test_public_direct_payment_denial_with_configured_credentials(
    api, context, paypal, controls
):
    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)
    before = (len(paypal.create_keys), len(paypal.capture_keys), paypal.get_calls)
    controls()
    for method, suffix, body in [
        ("GET", "/config", {}),
        ("POST", "/orders", {"approval_id": approval["id"]}),
        ("POST", f"/attempts/{attempt['id']}/capture", {"retry_uncertain": True}),
        ("POST", f"/attempts/{attempt['id']}/reconcile", {}),
    ]:
        response = api.request(method, path(context) + suffix, json=body)
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["code"] == "public_demo_payment_disabled"
        assert "client_id" not in response.text and "sdk_url" not in response.text
    assert (
        len(paypal.create_keys),
        len(paypal.capture_keys),
        paypal.get_calls,
    ) == before
    eligibility = api.get(path(context) + "/eligibility").json()
    assert eligibility["payment_execution_allowed"] is False
    assert eligibility["sandbox_configured"] is False
    assert "disabled in the public demo" in eligibility["payment_notice"]
    assert api.get(path(context) + "/receipt").status_code == 404
    assert api.get(path(context) + "/attempts").json()[0]["status"] == attempt["status"]


def test_public_historical_receipt_unchanged_and_isolated(
    api, context, paypal, controls
):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"
    assert capture(api, context, attempt).json()["status"] == "completed"
    receipt = api.get(path(context) + "/receipt").json()
    controls()
    assert api.get(path(context) + "/receipt").json() == receipt
    with visitor(True) as other:
        assert other.get(path(context) + "/receipt").status_code == 404
    assert api.get(path(context) + "/receipt").json() == receipt


def test_public_signed_webhook_keeps_verification_and_reconciliation(
    api, context, paypal, setup, controls
):
    controls(demo_ai_calls_per_day=0)
    paypal.verify_webhook = Mock()
    with TestClient(app, base_url="https://testserver") as provider:
        event = notification(paypal)
        assert provider.post(URL, json=event).json() == {"status": "processed"}
        assert provider.post(URL, json=event).json() == {"status": "duplicate"}
    assert paypal.verify_webhook.call_count == 2
    assert api.get(path(context) + "/receipt").json()["capture_id"] == paypal.capture_id
    assert len(paypal.capture_keys) == 0
