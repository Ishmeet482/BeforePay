import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from conftest import postgres_engine as postgres_factory
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.bookings.models import Booking
from app.core.config import Settings
from app.core.database import build_engine
from app.hosting.models import DemoDeployment, DemoTemplate
from app.hosting.readiness import require_public_database
from app.hosting.templates import TEMPLATES
from app.main import app
from scripts.setup_demo import setup


@pytest.fixture
def isolated_hosting(monkeypatch):
    factory = postgres_factory.__wrapped__()
    engine = next(factory)
    settings = Settings(
        _env_file=None,
        public_demo_mode=True,
        database_url=engine.url.render_as_string(hide_password=False),
        public_demo_database=engine.url.database,
        demo_allowed_origins=["https://beforepay.example"],
    )
    for module in (
        "app.core.database",
        "app.hosting.middleware",
        "app.admission.service",
        "app.demo_sessions.router",
        "app.demo_sessions.service",
        "app.core.body_limit",
        "app.evidence.router",
        "app.payments.router",
    ):
        monkeypatch.setattr(module + ".get_settings", lambda: settings)
    runtime = build_engine()
    admissions = build_engine(admission=True)
    monkeypatch.setattr("app.core.database.get_engine", lambda: runtime)
    monkeypatch.setattr("app.core.database.get_admission_engine", lambda: admissions)
    try:
        yield engine, runtime, admissions, settings
    finally:
        runtime.dispose()
        admissions.dispose()
        factory.close()


class Rewrite(httpx.BaseTransport):
    """Model a same-origin external rewrite, not a hosted Vercel integration."""

    def handle_request(self, request):
        # Fresh backend client prevents a proxy-owned cookie jar leaking sessions.
        client = TestClient(app, base_url="https://backend.example")
        response = client.request(
            request.method,
            request.url.path,
            headers=dict(request.headers),
            content=request.read(),
        )
        client.close()
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )


def browser():
    return httpx.Client(
        transport=Rewrite(),
        base_url="https://beforepay.example",
        headers={"Origin": "https://beforepay.example"},
    )


def test_same_origin_public_flow_and_private_cookie(isolated_hosting):
    engine, _, _, settings = isolated_hosting
    with browser() as buyer:
        assert buyer.post("/api/demo-sessions").status_code == 503
        setup(engine, settings.public_demo_database)
        login = buyer.post("/api/demo-sessions")
        assert login.status_code == 201
        cookie = login.headers["set-cookie"].lower()
        assert all(
            value in cookie
            for value in ("secure", "httponly", "samesite=lax", "path=/api")
        )
        assert "domain=" not in cookie
        assert all(c.domain == "beforepay.example" for c in buyer.cookies.jar)
        assert (
            buyer.post("/api/bookings", json={"title": "Blocked CSRF"}).status_code
            == 403
        )
        buyer.headers["X-BeforePay-CSRF"] = login.json()["csrf_token"]
        assert (
            buyer.post(
                "/api/bookings",
                headers={"Origin": "https://evil.example"},
                json={"title": "Blocked origin"},
            ).status_code
            == 403
        )
        template = buyer.get("/api/demo-templates").json()[0]
        booking = buyer.post(
            "/api/bookings", json={"title": "SYNTHETIC hosting workflow"}
        ).json()
        base = "/api/bookings/" + booking["id"]
        saved = buyer.post(
            base + "/sources/text",
            json={
                "source_type": template["source_type"],
                "original_text": template["original_text"],
            },
        )
        assert saved.status_code == 201
        assert (
            buyer.post(
                base + "/drafts", json={"source_ids": [saved.json()["id"]]}
            ).status_code
            == 429
        )
        assert buyer.get(base + "/checkout/config").status_code == 403
        assert buyer.get(base + "/checkout/receipt").status_code == 404
        assert buyer.post("/api/paypal/sandbox/webhook", json={}).status_code == 404
        with browser() as merchant_other:
            second = merchant_other.post("/api/demo-sessions")
            merchant_other.headers["X-BeforePay-CSRF"] = second.json()["csrf_token"]
            assert merchant_other.get("/api/bookings").json() == []
            response = merchant_other.get(base)
            assert response.status_code == 404
            assert response.headers["cache-control"] == "private, no-store"
            assert "Cookie" in response.headers["vary"]
        before = buyer.get("/api/bookings").json()
        assert (
            buyer.post("/api/demo-sessions", json={"role": "merchant"}).status_code
            == 200
        )
        assert buyer.get("/api/bookings").json() == before


def test_setup_idempotent_and_no_fabricated_history(isolated_hosting):
    engine, _, _, settings = isolated_hosting
    setup(engine, settings.public_demo_database)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Booking)) == 0
        assert db.scalar(select(func.count()).select_from(DemoTemplate)) == len(
            TEMPLATES
        )
        original = db.execute(text("SELECT to_jsonb(t) FROM demo_deployment t")).all()
    setup(engine, settings.public_demo_database)
    with Session(engine) as db:
        assert (
            db.execute(text("SELECT to_jsonb(t) FROM demo_deployment t")).all()
            == original
        )
        assert db.scalar(text("SELECT count(*) FROM sandbox_receipts")) == 0
        assert db.scalar(text("SELECT count(*) FROM draft_versions")) == 0
        assert db.scalar(text("SELECT count(*) FROM demo_admissions")) == 0
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE demo_templates SET fingerprint='changed'"))


def test_setup_refuses_unmarked_records_and_wrong_target(isolated_hosting):
    engine, _, _, settings = isolated_hosting
    with Session(engine) as db:
        db.add(Booking(title="SYNTHETIC pre-existing record"))
        db.commit()
    with pytest.raises(ValueError):
        setup(engine, "contextkey")
    with pytest.raises(ValueError):
        setup(engine, "not_the_target")
    with pytest.raises(ValueError, match="refusing adoption"):
        setup(engine, settings.public_demo_database)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Booking)) == 1
        assert db.scalar(select(func.count()).select_from(DemoDeployment)) == 0
        assert db.scalar(select(func.count()).select_from(DemoTemplate)) == 0


def test_readiness_rejects_disabled_controls(isolated_hosting):
    engine, _, _, settings = isolated_hosting
    setup(engine, settings.public_demo_database)
    with Session(engine) as db:
        require_public_database(db, settings)
        db.execute(
            text("ALTER TABLE bookings DISABLE TRIGGER bookings_owner_immutable")
        )
        with pytest.raises(HTTPException) as error:
            require_public_database(db, settings)
        assert error.value.status_code == 503
        db.rollback()
        require_public_database(db, settings)
        db.execute(text("DELETE FROM demo_admission_control"))
        with pytest.raises(HTTPException):
            require_public_database(db, settings)
        db.rollback()


def test_least_privilege_hosted_role_check(isolated_hosting):
    engine, _, _, settings = isolated_hosting
    setup(engine, settings.public_demo_database)
    hosted = settings.model_copy(update={"vercel": True})
    name = "beforepay_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE ROLE "{name}"'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{name}"'))
        connection.execute(
            text(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{name}"')
        )
    try:
        with Session(engine) as db:
            with pytest.raises(HTTPException):
                require_public_database(db, hosted)
            db.execute(text(f'SET LOCAL ROLE "{name}"'))
            require_public_database(db, hosted)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{name}"'))
            connection.execute(text(f'DROP ROLE "{name}"'))


def test_separate_bounded_pools_and_transaction_timeouts(isolated_hosting):
    engine, runtime, admissions, settings = isolated_hosting
    setup(engine, settings.public_demo_database)
    assert runtime.pool.size() == 2 and admissions.pool.size() == 1
    assert runtime.pool._max_overflow == 0 and admissions.pool._max_overflow == 0
    with runtime.connect() as first, runtime.connect() as second:
        assert first.connection.driver_connection.prepare_threshold is None
        assert first.scalar(text("SHOW statement_timeout")) == "5s"
        assert second.scalar(text("SHOW lock_timeout")) == "3s"
        with admissions.connect() as third:
            assert third.scalar(text("SELECT 1")) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"public_demo_database": ""},
        {"demo_cookie_secure": False},
        {"demo_allowed_origins": []},
        {"demo_allowed_origins": ["http://localhost:5173"]},
        {"demo_max_sessions": 1_000_000},
        {"demo_max_writes": 1_000_000},
        {"vercel": True, "public_demo_mode": False},
        {"vercel": True, "demo_ai_calls_per_day": 1},
        {"vercel": True, "gemini_api_key": "synthetic-only"},
        {"vercel": True, "paypal_sandbox_enabled": True},
        {"vercel": True, "public_webhooks_enabled": True},
    ],
)
def test_invalid_public_configuration_fails_closed(change):
    values = dict(
        public_demo_mode=True,
        public_demo_database="beforepay_demo",
        database_url="postgresql+psycopg://synthetic:synthetic@db.example/beforepay_demo?sslmode=require",
        demo_allowed_origins=["https://beforepay.example"],
    )
    values.update(change)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "synthetic@" not in str(error.value)


def test_bad_settings_returns_private_503(monkeypatch):
    def invalid():
        return Settings(_env_file=None, vercel=True)

    monkeypatch.setattr("app.hosting.middleware.get_settings", invalid)
    response = TestClient(app).post("/api/demo-sessions")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"
    assert "database_url" not in response.text


def test_vercel_configs_and_no_api_spa_fallback():
    root = Path(__file__).resolve().parents[2]
    backend = json.loads((root / "backend/vercel.json").read_text())
    frontend = json.loads((root / "frontend/vercel.json").read_text())
    assert backend["functions"]["app/main.py"]["maxDuration"] == 90
    assert backend["env"]["DEMO_AI_CALLS_PER_DAY"] == "0"
    assert backend["env"]["PUBLIC_WEBHOOKS_ENABLED"] == "false"
    assert frontend["rewrites"] == [
        {
            "source": "/api/:path*",
            "destination": "https://backend-not-configured.invalid/api/:path*",
        }
    ]
    assert "no-store" in frontend["headers"][0]["headers"][0]["value"]


def test_rewrite_generator_validates_origin():
    import runpy

    root = Path(__file__).resolve().parents[2]
    configure = runpy.run_path(str(root / "scripts/prepare_vercel.py"))["configure"]
    assert (
        configure({}, "https://api.example")["rewrites"][0]["destination"]
        == "https://api.example/api/:path*"
    )
    for value in (
        "http://api.example",
        "https://user:password@api.example",
        "https://api.example/path",
        "https://localhost",
        "https://api.example?key=value",
        "https://backend.invalid",
    ):
        with pytest.raises(ValueError):
            configure({}, value)
