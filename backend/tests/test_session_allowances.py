"""Default/override boundaries and durable admissions; no provider calls."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_public_admission import caller, charges, owner
from test_public_admission import controls as controls_fixture

from app.admission.service import reserve, run_ai
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


CUMULATIVE = {
    "demo_max_sessions": (100, 1000),
    "demo_max_bookings": (100, 1000),
    "demo_bookings_per_session": (5, 50),
    "demo_payment_attempts_global": (20, 200),
    "demo_payment_attempts_per_session": (5, 50),
    "demo_max_writes": (4000, 40000),
    "demo_writes_per_session": (100, 1000),
    "demo_max_sources": (400, 4000),
    "demo_sources_per_session": (8, 80),
    "demo_source_bytes": (8000000, 80000000),
    "demo_source_bytes_per_session": (400000, 4000000),
    "demo_upload_bytes": (67108864, 671088640),
    "demo_upload_bytes_per_session": (6291456, 62914560),
    "demo_ai_calls_per_session": (6, 60),
    "demo_ai_tokens_per_session": (400000, 4000000),
    "demo_ai_calls_per_day": (0, 0),
    "demo_ai_tokens_per_day": (0, 0),
}


def test_all_cumulative_defaults_and_unchanged_throughput():
    settings = configured()
    for field, (old, new) in CUMULATIVE.items():
        assert new == old * 10 if old else new == 0
        assert getattr(settings, field) == new
    unchanged = {
        "demo_sessions_per_hour": 20,
        "demo_ai_calls_per_minute": 2,
        "demo_ai_tokens_per_minute": 0,
        "demo_ai_concurrent_global": 1,
        "demo_ai_concurrent_session": 1,
        "demo_ai_cooldown_seconds": 15,
        "demo_pdf_max_bytes": 3145728,
        "demo_pdf_max_pages": 20,
        "demo_source_max_chars": 40000,
        "db_pool_size": 2,
        "db_max_overflow": 0,
        "db_pool_timeout": 3,
        "demo_session_ttl_seconds": 2592000,
    }
    assert all(getattr(settings, k) == v for k, v in unchanged.items())
    assert not settings.public_sandbox_payments_enabled
    assert not settings.public_webhooks_enabled


@pytest.mark.parametrize("field", CUMULATIVE)
def test_all_environment_strings_and_lower_overrides(monkeypatch, field):
    expected = CUMULATIVE[field][1]
    for value in {0, 1, expected}:
        monkeypatch.setenv(field.upper(), str(value))
        assert getattr(configured(), field) == value
    monkeypatch.setenv(field.upper(), "-1")
    with pytest.raises(ValidationError):
        configured()
    monkeypatch.delenv(field.upper())
    assert getattr(configured(), field) == expected


@pytest.mark.parametrize(
    "field,maximum",
    [
        ("demo_max_sessions", 1000),
        ("demo_max_bookings", 1000),
        ("demo_bookings_per_session", 50),
        ("demo_max_sources", 4000),
        ("demo_sources_per_session", 80),
        ("demo_max_writes", 40000),
        ("demo_writes_per_session", 1000),
        ("demo_source_bytes", 80000000),
        ("demo_upload_bytes", 671088640),
        ("demo_payment_attempts_global", 200),
        ("demo_payment_attempts_per_session", 50),
    ],
)
def test_supported_public_ceiling(monkeypatch, field, maximum):
    monkeypatch.setenv(field.upper(), str(maximum))
    assert getattr(configured(), field) == maximum
    monkeypatch.setenv(field.upper(), str(maximum + 1))
    with pytest.raises(ValidationError):
        configured()


def test_complete_production_quota_environment_with_hosted_sandbox(monkeypatch):
    # This exact non-secret operator block is tested together, not one knob at a time.
    values = dict(
        line.split("=", 1)
        for line in Path(".env.quotas.example").read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert set(values) == {k.upper() for k, (old, _) in CUMULATIVE.items() if old}
    # Production's three hidden settings are UNKNOWN. Supply valid synthetic
    # values only for this isolated validation; never read or replace real ones.
    for name, value in (
        values
        | {
            "DEMO_AI_CALLS_PER_DAY": "1200",
            "DEMO_AI_TOKENS_PER_DAY": "80000000",
            "DEMO_AI_TOKENS_PER_MINUTE": "1000000",
        }
    ).items():
        monkeypatch.setenv(name, value)
    settings = configured(
        public_sandbox_payments_enabled=True,
        paypal_sandbox_enabled=True,
        paypal_sandbox_client_id="synthetic-client",
        paypal_sandbox_client_secret="synthetic-secret",
        paypal_sandbox_merchant_id="synthetic-merchant",
    )
    assert all(getattr(settings, k.lower()) == int(v) for k, v in values.items())
    with pytest.raises(ValidationError):
        configured(paypal_environment="live")


def test_repository_vercel_configuration_does_not_override_session_limits():
    overrides = json.loads(Path("vercel.json").read_text()).get("env", {})
    for name in (field.upper() for field in CUMULATIVE):
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
    assert [claim(i) for i in range(2, 49)] == [200] * 47
    # Exactly one remaining slot, admitted atomically with the unchanged lock.
    with ThreadPoolExecutor(2) as workers:
        assert sorted(workers.map(claim, [49, 50])) == [200, 429]
    rows = charges(postgres_engine, kind)
    assert len(rows) == 50 and original <= {row.id for row in rows}
    assert claim(51) == 429
    assert len(charges(postgres_engine, kind)) == 50


@pytest.mark.parametrize(
    "kind,field,bytes_budget",
    [
        ("session", "demo_max_sessions", False),
        ("booking", "demo_max_bookings", False),
        ("source", "demo_max_sources", False),
        ("source", "demo_sources_per_session", False),
        ("write", "demo_max_writes", False),
        ("write", "demo_writes_per_session", False),
        ("write", "demo_payment_attempts_global", False),
        ("source", "demo_source_bytes", True),
        ("source", "demo_source_bytes_per_session", True),
        ("upload", "demo_upload_bytes", True),
        ("upload", "demo_upload_bytes_per_session", True),
    ],
)
def test_count_and_byte_admission_boundaries_keep_prior_usage(
    api, postgres_engine, controls, kind, field, bytes_budget
):
    controls(**{field: 2})
    identity = owner(postgres_engine, api)
    action = (
        "sandbox_payment_attempt"
        if field == "demo_payment_attempts_global"
        else "synthetic"
    )

    def claim():
        with caller(postgres_engine, identity) as db:
            reserve(db, kind, action, {}, units=1 if bytes_budget else 0)
            db.rollback()  # Independently committed reservations must survive.

    claim()
    claim()  # An exact byte budget is allowed; count caps reject the next claim.
    before = {r.id for r in charges(postgres_engine, kind)}
    with pytest.raises(HTTPException) as blocked:
        claim()
    assert blocked.value.status_code == 429
    assert {r.id for r in charges(postgres_engine, kind)} == before
    controls()  # Increased defaults, same ledger and identity.
    claim()
    after = {r.id for r in charges(postgres_engine, kind)}
    assert before < after and len(after) == len(before) + 1


@pytest.mark.parametrize(
    "field", ["demo_ai_calls_per_session", "demo_ai_tokens_per_session"]
)
def test_ai_default_headroom_keeps_consumed_calls_and_reserved_units(
    api, postgres_engine, controls, field
):
    # No actual model call. These positive test budgets isolate one cumulative
    # allowance from the deliberately unchanged daily/rate/concurrency controls.
    other = dict(
        demo_ai_calls_per_day=1000,
        demo_ai_calls_per_minute=1000,
        demo_ai_tokens_per_day=40000000,
        demo_ai_tokens_per_minute=40000000,
    )
    if field == "demo_ai_tokens_per_session":
        other["demo_ai_calls_per_session"] = 1000
    old, new = CUMULATIVE[field]
    per_claim = 1 if field == "demo_ai_calls_per_session" else 48770
    identity = owner(postgres_engine, api)

    def claim():
        with caller(postgres_engine, identity) as db:
            run_ai(db, "synthetic", {}, lambda: None, booking_id=None)
            db.rollback()

    controls(**other, **{field: old})
    for _ in range(old // per_claim):
        claim()
    prior = {r.id for r in charges(postgres_engine)}
    with pytest.raises(HTTPException):
        claim()
    controls(**other)  # Actual new default for the field under test.
    for _ in range(new // per_claim - len(prior)):
        claim()
    rows = charges(postgres_engine)
    assert len(rows) == new // per_claim
    assert prior <= {r.id for r in rows}
    assert all(r.finished_at is not None for r in rows)
    if field == "demo_ai_tokens_per_session":
        assert sum(r.units for r in rows) <= new
    with pytest.raises(HTTPException) as blocked:
        claim()
    assert blocked.value.status_code == 429
    assert len(charges(postgres_engine)) == len(rows)
