"""Default/override boundaries and durable admissions; no provider calls."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_public_admission import caller, charges, owner
from test_public_admission import controls as controls_fixture

from app.admission.service import reserve
from app.core.config import Settings

controls = controls_fixture


def configured(**overrides):
    return Settings(
        _env_file=None,
        vercel=True,
        public_demo_mode=True,
        database_url="postgresql+psycopg://placeholder@db.example/demo?sslmode=require",
        public_demo_database="demo",
        demo_allowed_origins=["https://frontend.example"],
        **overrides,
    )


def test_defaults_change_only_the_two_session_allowances():
    settings = configured()
    assert settings.demo_bookings_per_session == 5
    assert settings.demo_payment_attempts_per_session == 5
    assert settings.demo_max_bookings == 100
    assert settings.demo_payment_attempts_global == 20
    assert settings.demo_max_writes == 4000
    assert settings.demo_writes_per_session == 100
    assert settings.demo_sources_per_session == 8
    assert settings.demo_ai_calls_per_session == 6
    assert settings.demo_ai_calls_per_day == settings.demo_ai_tokens_per_day == 0
    assert settings.demo_ai_calls_per_minute == 2
    assert (
        settings.demo_ai_concurrent_global == settings.demo_ai_concurrent_session == 1
    )
    assert not settings.public_sandbox_payments_enabled
    assert not settings.public_webhooks_enabled


@pytest.mark.parametrize(
    "field", ["demo_bookings_per_session", "demo_payment_attempts_per_session"]
)
def test_valid_boundaries_and_environment_overrides(monkeypatch, field):
    for value in (0, 1, 2, 3, 4, 5):
        monkeypatch.setenv(field.upper(), str(value))
        assert getattr(configured(), field) == value
    for value in (-1, 6):
        monkeypatch.setenv(field.upper(), str(value))
        with pytest.raises(ValidationError):
            configured()
    monkeypatch.delenv(field.upper())
    assert getattr(configured(), field) == 5


def test_environment_five_with_complete_hosted_sandbox_configuration(monkeypatch):
    monkeypatch.setenv("DEMO_PAYMENT_ATTEMPTS_PER_SESSION", "5")
    settings = configured(
        public_sandbox_payments_enabled=True,
        paypal_sandbox_enabled=True,
        paypal_sandbox_client_id="synthetic-client",
        paypal_sandbox_client_secret="synthetic-secret",
        paypal_sandbox_merchant_id="synthetic-merchant",
    )
    assert settings.demo_payment_attempts_per_session == 5
    assert settings.public_sandbox_payments_enabled
    with pytest.raises(ValidationError):
        configured(paypal_environment="live")


def test_repository_vercel_configuration_does_not_override_session_limits():
    overrides = json.loads(Path("vercel.json").read_text()).get("env", {})
    for name in ("DEMO_BOOKINGS_PER_SESSION", "DEMO_PAYMENT_ATTEMPTS_PER_SESSION"):
        assert name not in overrides


@pytest.mark.parametrize(
    "kind,action,field,code",
    [
        (
            "booking",
            "create_booking",
            "demo_bookings_per_session",
            "demo_resource_limit",
        ),
        (
            "write",
            "sandbox_payment_attempt",
            "demo_payment_attempts_per_session",
            "demo_payment_attempt_limit",
        ),
    ],
)
def test_consumed_reservations_count_after_increase_and_concurrent_boundary(
    api, postgres_engine, controls, kind, action, field, code
):
    identity = owner(postgres_engine, api)

    def claim(index):
        with caller(postgres_engine, identity) as db:
            try:
                reserve(db, kind, action, {"synthetic": index})
                return 200
            except HTTPException as error:
                assert error.detail["code"] == code
                return error.status_code

    controls(**{field: 2})
    assert [claim(i) for i in range(2)] == [200, 200]
    original = {row.id for row in charges(postgres_engine, kind)}
    assert claim(2) == 429
    controls()  # New defaults; existing reservations must not be reset.
    assert [claim(i) for i in range(2, 4)] == [200, 200]
    # Exactly one remaining slot, admitted atomically with the unchanged lock.
    with ThreadPoolExecutor(2) as workers:
        assert sorted(workers.map(claim, [4, 5])) == [200, 429]
    rows = charges(postgres_engine, kind)
    assert len(rows) == 5 and original <= {row.id for row in rows}
    assert claim(6) == 429
    assert len(charges(postgres_engine, kind)) == 5
