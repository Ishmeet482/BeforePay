"""Offline request/SQL counts and isolation; no hosted latency claims."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.orm import Session
from test_cancellation_preview import approve, create
from test_hosting_preparation import isolated_hosting as hosting_fixture
from test_paypal_sandbox import context as payment_fixture
from test_paypal_sandbox import settings as settings_fixture
from test_public_admission import controls as admission_fixture
from test_restricted_saved_state import restricted_hosting as restricted_fixture

from app.core.config import Settings
from app.hosting.readiness import require_public_database
from app.main import app

isolated_hosting = hosting_fixture
restricted_hosting = restricted_fixture
controls = admission_fixture
settings = settings_fixture
context = payment_fixture


def public_settings(**overrides):
    return Settings(
        _env_file=None,
        vercel=True,
        public_demo_mode=True,
        public_demo_database="beforepay_demo_test",
        database_url="postgresql+psycopg://placeholder@db.example/beforepay_demo_test?sslmode=require",
        demo_allowed_origins=["https://frontend.example"],
        **overrides,
    )


def test_booking_increment_is_validated_without_changing_defaults():
    assert public_settings().demo_bookings_per_session == 50
    assert public_settings(demo_bookings_per_session=3).demo_bookings_per_session == 3
    assert public_settings(demo_bookings_per_session=5).demo_bookings_per_session == 5
    for cap in (-1, 51):
        with pytest.raises(ValidationError):
            public_settings(demo_bookings_per_session=cap)
    with pytest.raises(ValidationError):
        public_settings(demo_payment_attempts_per_session=51)


def test_one_extra_booking_in_existing_scope_preserves_ledger(api, controls):
    enable = controls
    enable(demo_bookings_per_session=2)
    first = api.post("/api/bookings", json={"title": "Synthetic first"})
    second = api.post("/api/bookings", json={"title": "Synthetic second"})
    assert first.status_code == second.status_code == 201
    blocked = api.post("/api/bookings", json={"title": "Synthetic third"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "demo_resource_limit"
    assert "booking allowance" in blocked.json()["detail"]["message"]
    enable(demo_bookings_per_session=3)
    assert (
        api.post("/api/bookings", json={"title": "Synthetic third"}).status_code == 201
    )
    assert (
        api.post("/api/bookings", json={"title": "Synthetic fourth"}).status_code == 429
    )
    saved = api.get("/api/bookings").json()
    assert len(saved) == 3
    assert {first.json()["id"], second.json()["id"]} <= {b["id"] for b in saved}


def test_snapshot_retains_guarded_state_and_payment_restrictions(api, context):
    base = f"/api/bookings/{context['booking']}"
    snapshot = api.get(base + "/saved-state")
    assert snapshot.status_code == 200, snapshot.text
    data = snapshot.json()
    assert data["review"] == api.get(base + "/review").json()
    assert (
        data["agreement"]
        == api.get(base + "/agreements/" + data["review"]["agreement_id"]).json()
    )
    assert data["proposal"]["id"] == context["proposal"]["id"]
    assert (
        data["eligible"] == api.get(base + "/checkout/eligibility").json()["eligible"]
    )
    assert len(data["rules"]) == 2 and all(r["approved_current"] for r in data["rules"])
    assert data["attempts"] == [] and data["receipt"] is None


def test_summary_reads_only_current_rules_and_never_caches_approval(
    api, context, postgres_engine
):
    base = f"/api/bookings/{context['booking']}"
    old_rules = api.get(base + "/cancellation/rules").json()
    new_rules = []
    for old in old_rules:
        proposal = context["proposal"] if old["target"]["kind"] == "proposal" else None
        response = create(
            api, context, old["rules"], proposal=proposal, expected=old["id"]
        )
        assert response.status_code == 201, response.text
        new_rules.append(response.json())
    assert len(api.get(base + "/cancellation/rules").json()) == 4
    statements = []

    def capture(_conn, _cursor, statement, *_):
        statements.append(statement)

    event.listen(postgres_engine, "before_cursor_execute", capture)
    try:
        for suffix in (
            "/review",
            "/merchant-bookings?limit=1",
            "/comparisons?limit=1",
            "/cancellation/rules?limit=100&offset=0",
            "/checkout/attempts",
            "/checkout/eligibility",
            "/agreements/" + context["agreement"]["id"],
        ):
            assert api.get(base + suffix).status_code == 200
        legacy = len(statements)
        statements.clear()
        saved = api.get(base + "/saved-state").json()
        aggregate = len(statements)
        assert aggregate < legacy
        assert len(saved["rules"]) == 2
        assert {r["id"] for r in saved["rules"]} == {r["id"] for r in new_rules}
        assert not saved["eligible"] and not any(
            r["approved_current"] for r in saved["rules"]
        )
        for rule in new_rules:
            assert approve(api, context, rule).json()["approved_current"]
        assert api.get(base + "/saved-state").json()["eligible"]
        print(
            f"Populated/history SQL statements: legacy={legacy}, aggregate={aggregate}"
        )
    finally:
        event.remove(postgres_engine, "before_cursor_execute", capture)


def test_readiness_batched_and_snapshot_reduces_read_round_trips(
    restricted_hosting, isolated_hosting
):
    _, _, _, settings = isolated_hosting
    engine = restricted_hosting
    statements = []

    def capture(_conn, _cursor, statement, *_):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as db:
            require_public_database(db, settings)
        assert len([s for s in statements if s.lstrip().startswith("SELECT")]) == 2
        with TestClient(
            app,
            base_url="https://beforepay.example",
            headers={"Origin": "https://beforepay.example"},
        ) as client:
            login = client.post("/api/demo-sessions")
            client.headers["X-BeforePay-CSRF"] = login.json()["csrf_token"]
            booking = client.post(
                "/api/bookings", json={"title": "Synthetic snapshot"}
            ).json()["id"]
            base = f"/api/bookings/{booking}"
            statements.clear()
            for suffix in (
                "/review",
                "/merchant-bookings?limit=1",
                "/comparisons?limit=1",
                "/cancellation/rules?limit=100&offset=0",
                "/checkout/attempts",
                "/checkout/eligibility",
            ):
                assert client.get(base + suffix).status_code == 200
            old_count = len(statements)
            statements.clear()
            response = client.get(base + "/saved-state")
            assert response.status_code == 200, response.text
            new_count = len(statements)
            assert new_count < old_count
            assert sum(s == "SELECT current_database()" for s in statements) == 1
            assert engine.pool.checkedout() == 0
            assert response.headers["cache-control"] == "private, no-store"
            # Independent session cannot read any part of the aggregate.
            with TestClient(
                app,
                base_url="https://beforepay.example",
                headers={"Origin": "https://beforepay.example"},
            ) as other:
                assert other.get(base + "/saved-state").status_code == 401
                assert other.post("/api/demo-sessions").status_code == 201
                assert other.get(base + "/saved-state").status_code == 404
            assert engine.pool.checkedout() == 0
            print(
                f"Saved-state SQL statements: legacy={old_count}, aggregate={new_count}"
            )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
