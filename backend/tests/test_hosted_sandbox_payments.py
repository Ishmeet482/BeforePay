"""Explicit hosted sandbox opt-in. All provider responses are mocked."""

# Fixtures imported for pytest; no live SDK/network or developer environment.
# ruff: noqa: F401, F811
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_demo_sessions import visitor
from test_paypal_sandbox import (
    capture,
    checkout_approve,
    context,
    order,
    path,
    paypal,
    settings,
)
from test_public_admission import caller, controls, owner
from test_restricted_saved_state import isolated_hosting, restricted_hosting

from app.admission.models import Admission
from app.admission.service import reserve
from app.core.config import Settings
from app.hosting.readiness import require_public_database
from app.main import app
from app.payments.provider import PayPalFailure


def enable(controls, settings, **limits):
    return controls(
        public_sandbox_payments_enabled=True,
        paypal_sandbox_enabled=True,
        paypal_sandbox_client_id=settings.paypal_sandbox_client_id,
        paypal_sandbox_client_secret=settings.paypal_sandbox_client_secret,
        paypal_sandbox_merchant_id=settings.paypal_sandbox_merchant_id,
        **limits,
    )


def charges(engine):
    with Session(engine) as db:
        return list(
            db.scalars(
                select(Admission).where(Admission.action == "sandbox_payment_attempt")
            )
        )


def test_opt_in_full_flow_reuses_attempt_and_captures_once(
    api, context, paypal, controls, settings, postgres_engine
):
    enable(controls, settings)
    approval = checkout_approve(api, context)
    config = api.get(path(context) + "/config").json()
    assert set(config) == {"environment", "configured", "sdk_url", "client_id"}
    assert config["environment"] == "sandbox"
    assert config["sdk_url"].startswith("https://www.sandbox.paypal.com/")
    assert settings.paypal_sandbox_client_secret.get_secret_value() not in str(config)
    assert api.get(path(context) + "/eligibility").json()["payment_execution_allowed"]
    attempt = order(api, context, approval)
    assert order(api, context, approval)["id"] == attempt["id"]
    assert len(charges(postgres_engine)) == 1
    assert len(paypal.create_keys) == 1
    # A browser approval or CREATED order is not capture proof.
    assert api.get(path(context) + "/receipt").status_code == 404
    paypal.remote_status = "APPROVED"
    assert api.get(path(context) + "/receipt").status_code == 404
    assert capture(api, context, attempt).json()["status"] == "completed"
    receipt = api.get(path(context) + "/receipt").json()
    assert capture(api, context, attempt).json()["status"] == "completed"
    assert len(paypal.capture_keys) == 1
    assert api.get(path(context) + "/receipt").json() == receipt
    with visitor(True) as other:
        assert other.get(path(context) + "/receipt").status_code == 404
        assert (
            other.post(
                path(context) + "/orders", json={"approval_id": approval["id"]}
            ).status_code
            == 404
        )


@pytest.mark.parametrize("scope", ["global", "session", "zero"])
def test_attempt_limit_denies_new_approval_without_provider_call(
    api, context, paypal, controls, settings, postgres_engine, scope
):
    enable(
        controls,
        settings,
        demo_payment_attempts_global=0
        if scope == "zero"
        else 20
        if scope == "session"
        else 1,
        demo_payment_attempts_per_session=1 if scope != "global" else 3,
    )
    approval = checkout_approve(api, context)
    if scope != "zero":
        attempt = order(api, context, approval)
        assert (
            api.post(path(context) + f"/attempts/{attempt['id']}/cancel").status_code
            == 200
        )
    fresh = checkout_approve(api, context)
    before = len(paypal.create_keys)
    result = api.post(path(context) + "/orders", json={"approval_id": fresh["id"]})
    assert result.status_code == 429, result.text
    assert result.json()["detail"]["code"] == "demo_payment_attempt_limit"
    assert len(paypal.create_keys) == before
    assert len(charges(postgres_engine)) == (0 if scope == "zero" else 1)


def test_failed_remote_create_keeps_charge_and_stable_attempt(
    api, context, paypal, controls, settings, postgres_engine, monkeypatch
):
    enable(controls, settings)
    approval = checkout_approve(api, context)

    def failed(attempt):
        paypal.create_keys.append(attempt.create_key)
        raise PayPalFailure("paypal_timeout")

    monkeypatch.setattr(paypal, "create", failed)
    first = order(api, context, approval)
    second = order(api, context, approval)
    assert first["status"] == second["status"] == "create_uncertain"
    assert first["id"] == second["id"]
    assert len(charges(postgres_engine)) == 1
    assert len(set(paypal.create_keys)) == 1
    assert api.get(path(context) + "/receipt").status_code == 404


def test_global_last_attempt_race_and_session_cycling(
    api, controls, settings, postgres_engine
):
    enable(controls, settings, demo_payment_attempts_global=1)
    first = owner(postgres_engine, api)
    with visitor(True) as other:
        second = owner(postgres_engine, other)

    def claim(identity):
        with caller(postgres_engine, identity) as db:
            try:
                reserve(
                    db, "write", "sandbox_payment_attempt", {"unique": str(uuid4())}
                )
                return 200
            except HTTPException as error:
                return error.status_code

    assert sorted(ThreadPoolExecutor(2).map(claim, [first, second])) == [200, 429]
    assert len(charges(postgres_engine)) == 1
    with visitor(True) as third:
        assert claim(owner(postgres_engine, third)) == 429


def test_vercel_opt_in_requires_complete_sandbox_configuration():
    values = dict(
        _env_file=None,
        vercel=True,
        public_demo_mode=True,
        database_url="postgresql+psycopg://test:test@db.example/beforepay_demo_2026?sslmode=require",
        public_demo_database="beforepay_demo_2026",
        demo_allowed_origins=["https://beforepay.example"],
        public_sandbox_payments_enabled=True,
        paypal_sandbox_enabled=True,
        paypal_sandbox_client_id="fake-sandbox",
        paypal_sandbox_client_secret="fake-secret",
        paypal_sandbox_merchant_id="FAKEMERCHANT",
    )
    assert Settings(**values).public_sandbox_payments_enabled
    for change in (
        {"paypal_environment": "live"},
        {"paypal_sandbox_client_secret": ""},
        {"paypal_sandbox_enabled": False},
        {"public_webhooks_enabled": True},
        {"public_sandbox_payments_enabled": False},
        {"demo_payment_attempts_global": 101},
    ):
        with pytest.raises(ValidationError):
            Settings(**(values | change))


def test_hosted_readiness_requires_only_optional_payment_grants(
    restricted_hosting, isolated_hosting, paypal, monkeypatch
):
    owner_engine, _, _, settings = isolated_hosting
    opted = settings.model_copy(update={"public_sandbox_payments_enabled": True})
    with Session(restricted_hosting) as db:
        require_public_database(db, settings)
        with pytest.raises(HTTPException) as error:
            require_public_database(db, opted)
        assert error.value.status_code == 503
        role = db.scalar(text("SELECT current_user"))
    # Apply the exact prepared grants only to the disposable role/database.
    script = Path("scripts/grant_demo_sandbox_payments.sql").read_text()
    grants = script[script.index("GRANT INSERT") : script.index("-- No UPDATE")]
    with owner_engine.begin() as db:
        db.execute(text(grants.replace("beforepay_demo_runtime", role)))
    with Session(restricted_hosting) as db:
        require_public_database(db, opted)
        assert not db.scalar(
            text(
                "SELECT has_table_privilege(current_user, 'sandbox_receipts', 'UPDATE')"
            )
        )
        assert not db.scalar(
            text(
                "SELECT has_column_privilege(current_user, "
                "'payment_attempts', 'amount', 'UPDATE')"
            )
        )
    opted = settings.model_copy(
        update={
            "public_sandbox_payments_enabled": True,
            "paypal_sandbox_enabled": True,
            "paypal_sandbox_client_id": "fake-sandbox-client",
            "paypal_sandbox_client_secret": SecretStr("fake-secret"),
            "paypal_sandbox_merchant_id": "FAKEMERCHANT",
        }
    )
    for module in (
        "app.core.database",
        "app.hosting.middleware",
        "app.admission.service",
        "app.demo_sessions.router",
        "app.demo_sessions.service",
        "app.payments.router",
        "app.payments.provider",
        "app.payments.service",
    ):
        monkeypatch.setattr(module + ".get_settings", lambda: opted)
    with TestClient(
        app,
        base_url="https://beforepay.example",
        headers={"Origin": "https://beforepay.example"},
    ) as client:
        issued = client.post("/api/demo-sessions")
        assert issued.status_code == 201
        client.headers["X-BeforePay-CSRF"] = issued.json()["csrf_token"]
        synthetic = context.__wrapped__(client, owner_engine, opted)
        approval = checkout_approve(client, synthetic)
        attempt = order(client, synthetic, approval)
        paypal.remote_status = "APPROVED"
        assert capture(client, synthetic, attempt).json()["status"] == "completed"
        assert (
            client.get(path(synthetic) + "/receipt").json()["capture_id"]
            == paypal.capture_id
        )
