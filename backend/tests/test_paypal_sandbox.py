import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_booking_comparisons import compare, save
from test_cancellation_preview import approve as approve_rules
from test_cancellation_preview import context as cancellation_context
from test_cancellation_preview import create as create_rules
from test_customer_review import revise, state

from app.core.config import Settings
from app.main import app
from app.payments import service
from app.payments.models import CheckoutApproval, PaymentAttempt, SandboxReceipt
from app.payments.provider import PayPalFailure, SandboxPayPal, get_paypal


@pytest.fixture
def settings(monkeypatch):
    safe = Settings(
        _env_file=None,
        paypal_sandbox_enabled=True,
        paypal_sandbox_client_id="fake-sandbox-client",
        paypal_sandbox_client_secret=SecretStr("fake-sandbox-secret"),
        paypal_sandbox_merchant_id="FAKEMERCHANT",
    )
    for path in (
        "app.payments.provider.get_settings",
        "app.payments.router.get_settings",
        "app.payments.service.get_settings",
    ):
        monkeypatch.setattr(path, lambda: safe)
    return safe


@pytest.fixture
def context(api, postgres_engine, settings):
    ctx = cancellation_context.__wrapped__(api, postgres_engine)
    proposal = save(api, ctx).json()
    response = compare(api, ctx, proposal)
    assert response.status_code == 201
    for source in (None, proposal):
        rule = create_rules(api, ctx, proposal=source).json()
        assert approve_rules(api, ctx, rule).json()["approved_current"]
    return {**ctx, "proposal": proposal, "comparison": response.json()}


class FakePayPal:
    def __init__(self):
        self.attempt = None
        self.order_id = "ORDER" + uuid4().hex[:20].upper()
        self.capture_id = "CAP" + uuid4().hex[:20].upper()
        self.remote_status = "CREATED"
        self.capture_status = None
        self.create_keys = []
        self.capture_keys = []
        self.get_calls = 0
        self.timeout_after_capture = False
        self.bad = None
        self.capture_entered = None
        self.capture_release = None

    def create(self, attempt):
        self.attempt = {
            "id": str(attempt.id),
            "amount": attempt.amount,
            "currency": attempt.currency,
        }
        self.create_keys.append(attempt.create_key)
        return {"id": self.order_id, "status": "CREATED"}

    def get(self, order_id):
        self.get_calls += 1
        assert order_id == self.order_id
        a = self.attempt
        unit = {
            "reference_id": a["id"],
            "custom_id": a["id"],
            "invoice_id": f"contextkey-{a['id']}",
            "payee": {"merchant_id": "FAKEMERCHANT"},
            "amount": {"value": a["amount"], "currency_code": a["currency"]},
        }
        if self.capture_status:
            unit["payments"] = {
                "captures": [
                    {
                        "id": self.capture_id,
                        "status": self.capture_status,
                        "final_capture": True,
                        "amount": copy.deepcopy(unit["amount"]),
                    }
                ]
            }
        data = {
            "id": order_id,
            "intent": "CAPTURE",
            "status": self.remote_status,
            "purchase_units": [unit],
        }
        if self.bad == "amount":
            unit["amount"]["value"] = "0.01"
        if self.bad == "payee":
            unit["payee"]["merchant_id"] = "OTHER"
        if self.bad == "custom_id":
            unit["custom_id"] = str(uuid4())
        if self.bad == "order_id":
            data["id"] = "OTHERORDER"
        if self.bad == "currency":
            unit["amount"]["currency_code"] = "EUR"
        if self.bad == "capture_amount" and self.capture_status:
            unit["payments"]["captures"][0]["amount"]["value"] = "0.01"
        return data

    def capture(self, attempt):
        self.capture_keys.append(attempt.capture_key)
        if self.capture_entered:
            self.capture_entered.set()
            assert self.capture_release.wait(10)
        self.remote_status = "COMPLETED"
        self.capture_status = "COMPLETED"
        if self.timeout_after_capture:
            raise PayPalFailure("paypal_timeout")
        return {"id": attempt.order_id, "status": "COMPLETED"}


@pytest.fixture
def paypal():
    fake = FakePayPal()
    app.dependency_overrides[get_paypal] = lambda: fake
    return fake


def path(context):
    return f"/api/bookings/{context['booking']}/checkout"


def checkout_approve(api, ctx):
    e = api.get(path(ctx) + "/eligibility").json()
    assert e["eligible"], e
    response = api.post(
        path(ctx) + "/approvals",
        json={
            "customer_label": "Sandbox buyer",
            "acknowledged": True,
            "expected_context_fingerprint": e["fingerprint"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def order(api, ctx, approval):
    response = api.post(path(ctx) + "/orders", json={"approval_id": approval["id"]})
    assert response.status_code == 200, response.text
    return response.json()


def capture(api, ctx, attempt, retry=False):
    return api.post(
        path(ctx) + f"/attempts/{attempt['id']}/capture",
        json={"retry_uncertain": retry},
    )


def test_complete_payment_requires_verified_capture_and_links_receipt(
    api, context, paypal, postgres_engine
):
    original = state(api, context)
    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)
    assert attempt["amount"] == "200.00" and attempt["currency"] == "USD"
    assert attempt["status"] == "awaiting_buyer"
    assert api.get(path(context) + "/receipt").status_code == 404
    # Browser callback alone is not buyer approval or payment.
    assert capture(api, context, attempt).json()["status"] == "awaiting_buyer"
    assert paypal.capture_keys == []
    paypal.remote_status = "APPROVED"
    response = capture(api, context, attempt)
    assert response.json()["status"] == "completed", response.text
    receipt = api.get(path(context) + "/receipt").json()
    assert (
        receipt["order_id"] == paypal.order_id
        and receipt["capture_id"] == paypal.capture_id
    )
    assert receipt["context"]["agreement_id"] == context["agreement"]["id"]
    assert receipt["context"]["proposal_id"] == context["proposal"]["id"]
    assert receipt["context"]["comparison_id"] == context["comparison"]["id"]
    assert receipt["amount"] == "200.00" and state(api, context) == original
    assert capture(api, context, attempt).json()["status"] == "completed"
    assert len(paypal.capture_keys) == 1
    assert not api.get(path(context) + "/eligibility").json()["eligible"]
    with Session(postgres_engine) as session:
        assert session.get(SandboxReceipt, UUID(receipt["id"]))


def test_foreign_child_references_never_authorize_payment_or_policy(
    api, context, paypal, postgres_engine
):
    from test_customer_review import seed_review
    from test_demo_sessions import visitor

    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)
    rules = api.get(f"/api/bookings/{context['booking']}/cancellation/rules").json()
    assert rules
    with visitor(True) as other:
        own = seed_review(other, postgres_engine)
        base = f"/api/bookings/{own['booking']}"
        # Real foreign child IDs under an owned parent, not random missing IDs.
        for suffix in (
            f"/merchant-bookings/{context['proposal']['id']}",
            f"/comparisons/{context['comparison']['id']}",
            f"/cancellation/rules/{rules[0]['id']}",
            f"/checkout/approvals/{approval['id']}",
        ):
            assert other.get(base + suffix).status_code == 404
        assert (
            other.post(
                base + "/checkout/orders", json={"approval_id": approval["id"]}
            ).status_code
            == 404
        )
        for action in ("capture", "reconcile", "cancel"):
            assert (
                other.post(
                    base + f"/checkout/attempts/{attempt['id']}/{action}", json={}
                ).status_code
                == 404
            )
        assert (
            other.post(
                base + "/policy-consistency",
                json={
                    "proposal_id": context["proposal"]["id"],
                    "proposal_fingerprint": context["proposal"]["fingerprint"],
                },
            ).status_code
            == 404
        )
        assert (
            other.post(
                base + "/cancellation/preview",
                json={
                    "rule_ids": [rules[0]["id"]],
                    "cancellation": {
                        "local_datetime": "2026-11-01T09:00:00",
                        "timezone": "UTC",
                    },
                },
            ).status_code
            == 404
        )
        assert paypal.get_calls == 0 and paypal.capture_keys == []
        assert len(paypal.create_keys) == 1
        paypal.remote_status = "APPROVED"
        assert capture(api, context, attempt).json()["status"] == "completed"
        assert other.get(path(context) + "/receipt").status_code == 404
        assert other.get(base + "/checkout/receipt").status_code == 404


def test_explicit_checkout_approval_and_browser_amount_rejected(api, context, paypal):
    approval = checkout_approve(api, context)
    e = api.get(path(context) + "/eligibility").json()
    assert (
        api.post(
            path(context) + "/approvals",
            json={
                "customer_label": "Buyer",
                "acknowledged": False,
                "expected_context_fingerprint": e["fingerprint"],
            },
        ).status_code
        == 422
    )
    assert (
        api.post(
            path(context) + "/approvals",
            json={
                "customer_label": "Buyer",
                "acknowledged": True,
                "expected_context_fingerprint": "0" * 64,
            },
        ).status_code
        == 409
    )
    assert (
        api.post(
            path(context) + "/orders",
            json={"approval_id": approval["id"], "amount": "0.01"},
        ).status_code
        == 422
    )
    assert paypal.create_keys == []


@pytest.mark.parametrize(
    "change", ["proposal", "evidence", "agreement", "rules", "comparison"]
)
def test_changes_block_creation_and_capture(api, context, paypal, change):
    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)
    paypal.remote_status = "APPROVED"
    if change == "proposal":
        save(api, context, expected=context["proposal"]["id"])
    elif change == "evidence":
        api.post(
            f"/api/bookings/{context['booking']}/sources/text",
            json={"source_type": "message", "original_text": "New relevant source"},
        )
    elif change == "agreement":
        revise(api, context)
    elif change == "comparison":
        assert compare(api, context, context["proposal"]).status_code == 201
    else:
        r = api.get(f"/api/bookings/{context['booking']}/cancellation/rules").json()
        existing = next(x for x in r if x["target"]["kind"] == "agreement")
        assert create_rules(api, context, expected=existing["id"]).status_code == 201
    assert (
        api.post(
            path(context) + "/orders", json={"approval_id": approval["id"]}
        ).status_code
        == 409
    )
    assert capture(api, context, attempt).status_code == 409
    assert paypal.capture_keys == []


def test_mismatches_and_unreviewed_policies_block(api, postgres_engine, settings):
    ctx = cancellation_context.__wrapped__(api, postgres_engine)
    proposal = save(api, ctx).json()
    assert compare(api, ctx, proposal).status_code == 201
    e = api.get(path(ctx) + "/eligibility").json()
    assert (
        not e["eligible"]
        and "agreement_reviewed_cancellation_rules_required" in e["blockers"]
    )


def test_contradictory_deposit_policy_blocks_even_matching_model_output(api, context):

    # A deliberately incorrect mocked semantic result cannot bypass rule review.
    data = copy.deepcopy(context["proposal"]["content"])
    data["deposit_conditions"][0]["value"] = "The deposit is non-refundable."
    proposal = save(api, context, data, context["proposal"]["id"]).json()
    from test_booking_comparisons import fake_policy

    fake_policy("matches")
    assert compare(api, context, proposal).status_code == 201
    e = api.get(path(context) + "/eligibility").json()
    assert (
        not e["eligible"]
        and "inconsistent_deposit_cancellation_policies" in e["blockers"]
    )


def test_timeout_reconciles_completed_capture_without_reposting(api, context, paypal):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"
    paypal.timeout_after_capture = True
    response = capture(api, context, attempt).json()
    assert response["status"] == "capture_uncertain"
    assert api.get(path(context) + "/receipt").status_code == 404
    reconciled = api.post(path(context) + f"/attempts/{attempt['id']}/reconcile").json()
    assert reconciled["status"] == "completed" and len(paypal.capture_keys) == 1
    assert api.get(path(context) + "/receipt").status_code == 200


def test_uncertain_retry_first_gets_order_and_uses_same_key(
    api, context, paypal, postgres_engine
):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"
    original_capture = paypal.capture

    def timeout(a):
        paypal.capture_keys.append(a.capture_key)
        raise PayPalFailure("paypal_timeout")

    paypal.capture = timeout
    assert capture(api, context, attempt).json()["status"] == "capture_uncertain"
    assert capture(api, context, attempt).json()["status"] == "capture_uncertain"
    assert len(paypal.capture_keys) == 1
    before = paypal.get_calls
    paypal.capture = original_capture
    assert capture(api, context, attempt, True).json()["status"] == "completed"
    assert (
        paypal.get_calls > before and paypal.capture_keys[0] == paypal.capture_keys[1]
    )


@pytest.mark.parametrize("remote", ["PENDING", "DECLINED"])
def test_pending_and_failed_captures_never_show_paid(api, context, paypal, remote):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"

    def capture_remote(a):
        paypal.capture_keys.append(a.capture_key)
        paypal.capture_status = remote
        paypal.remote_status = "COMPLETED"
        return {"status": "COMPLETED"}

    paypal.capture = capture_remote
    result = capture(api, context, attempt).json()
    assert result["status"] == ("pending" if remote == "PENDING" else "failed")
    assert result["capture_id"] == paypal.capture_id
    assert api.get(path(context) + "/receipt").status_code == 404


@pytest.mark.parametrize(
    "bad", ["amount", "currency", "payee", "custom_id", "order_id", "capture_amount"]
)
def test_verification_rejects_provider_mismatches(api, context, paypal, bad):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"
    paypal.bad = bad
    result = capture(api, context, attempt).json()
    assert result["status"] in {"create_uncertain", "capture_uncertain"}
    assert api.get(path(context) + "/receipt").status_code == 404


def test_cancel_does_not_allow_capture_or_reactivate(api, context, paypal):
    attempt = order(api, context, checkout_approve(api, context))
    cancelled = api.post(path(context) + f"/attempts/{attempt['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    paypal.remote_status = "APPROVED"
    assert (
        api.post(path(context) + f"/attempts/{attempt['id']}/reconcile").json()[
            "status"
        ]
        == "cancelled"
    )
    assert capture(api, context, attempt).status_code == 409 and not paypal.capture_keys


def test_duplicate_creation_and_other_attempt_blocking(api, context, paypal):
    approval = checkout_approve(api, context)
    first = order(api, context, approval)
    second = order(api, context, approval)
    assert first["id"] == second["id"] and len(paypal.create_keys) == 1
    other = checkout_approve(api, context)
    assert (
        api.post(
            path(context) + "/orders", json={"approval_id": other["id"]}
        ).status_code
        == 409
    )


def test_capture_lock_prevents_concurrent_proposal_edit(api, context, paypal):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"
    paypal.capture_entered = Event()
    paypal.capture_release = Event()
    edit_started = Event()

    def edit():
        edit_started.set()
        return save(api, context, expected=context["proposal"]["id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        captured = pool.submit(capture, api, context, attempt)
        assert paypal.capture_entered.wait(10)
        edited = pool.submit(edit)
        assert edit_started.wait(3)
        with pytest.raises(TimeoutError):
            edited.result(timeout=0.2)
        paypal.capture_release.set()
        assert captured.result().json()["status"] == "completed"
        assert edited.result().status_code == 201
    receipt = api.get(path(context) + "/receipt").json()
    assert receipt["context"]["proposal_id"] == context["proposal"]["id"]


@pytest.mark.parametrize("table", [CheckoutApproval, SandboxReceipt])
def test_approvals_and_receipts_immutable(api, context, paypal, postgres_engine, table):
    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)
    paypal.remote_status = "APPROVED"
    capture(api, context, attempt)
    ident = (
        approval["id"]
        if table == CheckoutApproval
        else api.get(path(context) + "/receipt").json()["id"]
    )
    with Session(postgres_engine) as session:
        with pytest.raises(DBAPIError):
            session.execute(delete(table).where(table.id == UUID(ident)))
        session.rollback()


def test_sandbox_transport_exact_host_keys_and_redirects(monkeypatch, settings):
    original_client = httpx.Client
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "api-m.sandbox.paypal.com"
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "fake-token"})
        return httpx.Response(200, json={"id": "FAKEORDER123", "status": "CREATED"})

    monkeypatch.setattr(
        SandboxPayPal,
        "_client",
        lambda self: original_client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
        ),
    )
    a = Mock(
        id=uuid4(),
        amount="200.00",
        currency="USD",
        create_key=str(uuid4()),
        capture_key=str(uuid4()),
        order_id="FAKEORDER123",
    )
    client = SandboxPayPal()
    client.create(a)
    client.get(a.order_id)
    client.capture(a)
    assert requests[1].headers["PayPal-Request-Id"] == a.create_key
    assert requests[-1].headers["PayPal-Request-Id"] == a.capture_key
    assert len([r for r in requests if r.url.path.endswith("/token")]) == 1
    assert all("paypal.com" not in str(r.url.query) for r in requests)


def test_no_live_environment_and_missing_credentials(monkeypatch):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, paypal_environment="live")
    with pytest.raises(HTTPException) as caught:
        SandboxPayPal().get("FAKEORDER123")
    assert caught.value.status_code == 503


def test_create_timeout_reuses_durable_attempt_and_key(api, context, paypal):
    approval = checkout_approve(api, context)
    original = paypal.create

    def timeout(a):
        original(a)
        raise PayPalFailure("paypal_timeout")

    paypal.create = timeout
    first = order(api, context, approval)
    assert first["status"] == "create_uncertain" and first["order_id"] is None
    paypal.create = original
    second = order(api, context, approval)
    assert (
        first["id"] == second["id"] and paypal.create_keys[0] == paypal.create_keys[1]
    )


def test_pending_capture_reconciliation_does_not_repost(api, context, paypal):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"

    def pending(a):
        paypal.capture_keys.append(a.capture_key)
        paypal.remote_status = "COMPLETED"
        paypal.capture_status = "PENDING"
        return {"id": a.order_id, "status": "COMPLETED"}

    paypal.capture = pending
    assert capture(api, context, attempt).json()["status"] == "pending"
    paypal.capture_status = "COMPLETED"
    assert (
        api.post(path(context) + f"/attempts/{attempt['id']}/reconcile").json()[
            "status"
        ]
        == "completed"
    )
    assert len(paypal.capture_keys) == 1


def test_uncertain_reconciliation_can_record_historical_capture(api, context, paypal):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"
    paypal.timeout_after_capture = True
    assert capture(api, context, attempt).json()["status"] == "capture_uncertain"
    save(api, context, expected=context["proposal"]["id"])
    result = api.post(path(context) + f"/attempts/{attempt['id']}/reconcile")
    assert result.json()["status"] == "completed"
    assert (
        api.get(path(context) + "/receipt").json()["context"]["proposal_id"]
        == context["proposal"]["id"]
    )
    assert len(paypal.capture_keys) == 1


def test_expired_uncertain_capture_never_blindly_retries(
    api, context, paypal, monkeypatch
):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "APPROVED"

    def timeout(a):
        paypal.capture_keys.append(a.capture_key)
        raise PayPalFailure("paypal_timeout")

    paypal.capture = timeout
    assert capture(api, context, attempt).json()["status"] == "capture_uncertain"
    future = service.now() + timedelta(minutes=16)
    monkeypatch.setattr(service, "now", lambda: future)
    result = capture(api, context, attempt, True).json()
    assert result["status"] == "capture_uncertain" and len(paypal.capture_keys) == 1


def test_cross_booking_payment_ids_rejected(api, context, paypal):
    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)
    other = api.post("/api/bookings", json={"title": "Other checkout"}).json()["id"]
    otherpath = f"/api/bookings/{other}/checkout"
    assert (
        api.post(
            otherpath + "/orders", json={"approval_id": approval["id"]}
        ).status_code
        == 404
    )
    assert (
        api.post(otherpath + f"/attempts/{attempt['id']}/capture", json={}).status_code
        == 404
    )
    assert paypal.capture_keys == []


def test_attempt_binding_and_idempotency_keys_immutable(
    api, context, paypal, postgres_engine
):
    attempt = order(api, context, checkout_approve(api, context))
    with Session(postgres_engine) as session:
        with pytest.raises(DBAPIError):
            session.execute(
                update(PaymentAttempt)
                .where(PaymentAttempt.id == UUID(attempt["id"]))
                .values(capture_key=str(uuid4()))
            )
        session.rollback()


def test_transport_rejects_redirect_without_following(monkeypatch, settings):
    original_client = httpx.Client
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": "https://api-m.paypal.com/v1/oauth2/token"}
        )

    monkeypatch.setattr(
        SandboxPayPal,
        "_client",
        lambda self: original_client(
            transport=httpx.MockTransport(redirect),
            follow_redirects=False,
            trust_env=False,
        ),
    )
    with pytest.raises(PayPalFailure):
        SandboxPayPal().get("FAKEORDER123")
    assert len(requests) == 1 and requests[0].url.host == "api-m.sandbox.paypal.com"


@pytest.mark.parametrize("case", ["differs", "needs_clarification"])
def test_comparison_result_blocks_checkout(api, context, case):
    data = copy.deepcopy(context["proposal"]["content"])
    if case == "differs":
        data["equipment"][0]["quantity"] = 3
    else:
        data["included_items"] = []
    proposal = save(api, context, data, context["proposal"]["id"]).json()
    assert compare(api, context, proposal).status_code == 201
    e = api.get(path(context) + "/eligibility").json()
    assert not e["eligible"]
    assert "comparison_has_differences_or_clarification" in e["blockers"]


def test_public_config_and_attempt_response_do_not_expose_secrets(
    api, context, paypal, settings
):
    config = api.get(path(context) + "/config")
    assert config.json()["environment"] == "sandbox"
    assert config.json()["sdk_url"].startswith("https://www.sandbox.paypal.com/")
    assert settings.paypal_sandbox_client_secret.get_secret_value() not in config.text
    attempt = order(api, context, checkout_approve(api, context))
    assert "capture_key" not in attempt and "create_key" not in attempt


def test_existing_order_readonly_uses_same_app_as_sdk_config(
    api, settings, monkeypatch
):
    """Diagnosing approval must never create an order or capture a payment."""
    import base64
    from types import SimpleNamespace

    original_client = httpx.Client
    calls = []
    attempt = SimpleNamespace(
        id=uuid4(),
        order_id="EXISTINGORDER123",
        amount="200.00",
        currency="USD",
        capture_id=None,
    )
    order_data = {
        "id": attempt.order_id,
        "intent": "CAPTURE",
        "status": "PAYER_ACTION_REQUIRED",
        "purchase_units": [
            {
                "reference_id": str(attempt.id),
                "custom_id": str(attempt.id),
                "invoice_id": f"contextkey-{attempt.id}",
                "payee": {"merchant_id": settings.paypal_sandbox_merchant_id},
                "amount": {"currency_code": "USD", "value": "200.00"},
            }
        ],
    }

    def handler(request):
        calls.append(request)
        if request.url.path == "/v1/oauth2/token":
            assert request.method == "POST"
            return httpx.Response(200, json={"access_token": "fake-token"})
        assert request.method == "GET"
        assert request.url.path == f"/v2/checkout/orders/{attempt.order_id}"
        return httpx.Response(200, json=order_data)

    monkeypatch.setattr(
        SandboxPayPal,
        "_client",
        lambda self: original_client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
        ),
    )
    booking = api.post(
        "/api/bookings", json={"title": "Read-only approval diagnosis"}
    ).json()["id"]
    config = api.get(f"/api/bookings/{booking}/checkout/config").json()
    result = SandboxPayPal().get(attempt.order_id)
    assert service.validate_order(result, attempt) == []
    assert result["status"] == "PAYER_ACTION_REQUIRED"  # awaiting buyer, not paid
    client_id, secret = (
        base64.b64decode(calls[0].headers["authorization"].split()[1])
        .decode()
        .split(":", 1)
    )
    assert client_id == config["client_id"] == settings.paypal_sandbox_client_id
    assert secret == settings.paypal_sandbox_client_secret.get_secret_value()
    assert config["sdk_url"] == "https://www.sandbox.paypal.com/web-sdk/v6/core"
    assert [(r.method, r.url.path) for r in calls] == [
        ("POST", "/v1/oauth2/token"),
        ("GET", f"/v2/checkout/orders/{attempt.order_id}"),
    ]


def test_payer_action_required_never_triggers_capture(api, context, paypal):
    attempt = order(api, context, checkout_approve(api, context))
    paypal.remote_status = "PAYER_ACTION_REQUIRED"
    result = capture(api, context, attempt).json()
    assert result["status"] == "awaiting_buyer"
    assert paypal.capture_keys == []
    assert api.get(path(context) + "/receipt").status_code == 404


def test_refundable_to_nonrefundable_deposit_blocks_order_and_capture(
    api, context, paypal
):
    from test_booking_comparisons import fake_policy
    from test_cancellation_preview import rules as cancellation_rules

    original_review = state(api, context)
    original_agreement = copy.deepcopy(context["agreement"])
    approval = checkout_approve(api, context)
    attempt = order(api, context, approval)  # Mocked provider, synthetic booking only.
    paypal.remote_status = "APPROVED"

    proposal_data = copy.deepcopy(context["proposal"]["content"])
    deposit = "The USD 80 deposit is non-refundable."
    early = (
        "Cancellation at least 48 hours before pickup refunds rental fee USD 120 "
        "only; deposit USD 80 is retained."
    )
    late = (
        "Cancellation less than 48 hours before pickup retains rental fee USD 120 "
        "and deposit USD 80; refund USD 0."
    )
    proposal_data["deposit_conditions"] = [{"value": deposit, "ambiguous": False}]
    proposal_data["cancellation_conditions"] = [
        {"value": value, "ambiguous": False} for value in (early, late)
    ]
    proposal_response = save(api, context, proposal_data, context["proposal"]["id"])
    assert proposal_response.status_code == 201
    proposal = proposal_response.json()
    assert (
        next(
            c["amount"]
            for c in proposal["content"]["amounts"]
            if c["kind"] == "total_payable"
        )
        == "200.00"
    )

    # Review consistent new rules, so missing approvals/contradictions cannot be
    # the sole explanation for rejection of the changed merchant terms.
    new_rules = cancellation_rules()
    new_rules["deposit_clause"] = deposit
    new_rules["early"]["clause"] = early
    new_rules["late"]["clause"] = late
    new_rules["early"]["deposit_refund"]["value"] = "0"
    new_rules["late"]["deposit_refund"]["value"] = "0"
    rule_response = create_rules(api, context, new_rules, proposal)
    assert rule_response.status_code == 201
    rule = rule_response.json()
    assert rule["blockers"] == []
    assert approve_rules(api, context, rule).json()["approved_current"]

    fake_policy("differs")  # Policy meaning is mocked; no Gemini call.
    comparison = compare(api, context, proposal)
    assert comparison.status_code == 201
    results = {r["category"]: r for r in comparison.json()["results"]}
    assert results["amounts"]["status"] == "matches"
    assert results["deposit_conditions"]["status"] == "differs"

    eligibility = api.get(path(context) + "/eligibility").json()
    assert eligibility["eligible"] is False
    assert "comparison_has_differences_or_clarification" in eligibility["blockers"]
    assert not any("required" in b for b in eligibility["blockers"])
    assert "inconsistent_deposit_cancellation_policies" not in eligibility["blockers"]
    assert (
        api.post(
            path(context) + "/approvals",
            json={
                "customer_label": "Buyer",
                "acknowledged": True,
                "expected_context_fingerprint": approval["fingerprint"],
            },
        ).status_code
        == 409
    )
    assert (
        api.post(
            path(context) + "/orders", json={"approval_id": approval["id"]}
        ).status_code
        == 409
    )
    assert capture(api, context, attempt).status_code == 409
    assert len(paypal.create_keys) == 1  # No additional mocked order was created.
    assert paypal.capture_keys == []
    assert api.get(path(context) + "/receipt").status_code == 404
    assert state(api, context) == original_review
    assert (
        api.get(
            f"/api/bookings/{context['booking']}/agreements/{original_agreement['id']}"
        ).json()
        == original_agreement
    )
