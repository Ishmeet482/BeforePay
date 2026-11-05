"""Real disposable PostgreSQL, local ASGI requests, no external providers."""

import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_customer_review import seed_review
from test_drafts import empty, metadata

from app.bookings.models import Booking
from app.core.config import Settings
from app.demo_sessions.models import DemoSession
from app.demo_sessions.service import COOKIE, token_hash
from app.drafts.models import DraftVersion
from app.drafts.provider import ProviderResult, get_extractor
from app.drafts.schemas import Extraction
from app.main import app

ORIGIN = "https://testserver"


@contextmanager
def visitor(entered=False):
    # api fixture installs the disposable database dependency for all clients.
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        if entered:
            result = client.post("/api/demo-sessions")
            assert result.status_code == 201
            client.headers["X-BeforePay-CSRF"] = result.json()["csrf_token"]
        yield client


def create(client):
    response = client.post("/api/bookings", json={"title": "Isolated synthetic"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def expire(engine, client):
    with Session(engine) as session:
        session.execute(
            update(DemoSession)
            .where(DemoSession.token_hash == token_hash(client.cookies[COOKIE]))
            .values(
                created_at=datetime.now(UTC) - timedelta(hours=2),
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        session.commit()


def test_cookie_hash_ttl_and_role_switch_reuse(api, postgres_engine):
    token = api.cookies[COOKIE]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    with Session(postgres_engine) as session:
        row = session.scalar(
            select(DemoSession).where(DemoSession.token_hash == token_hash(token))
        )
        original = (row.id, row.expires_at)
        assert set(DemoSession.__table__.columns.keys()) == {
            "id",
            "token_hash",
            "created_at",
            "expires_at",
            "revoked_at",
        }
        assert row.token_hash != token
        assert 2690 < (row.expires_at - row.created_at).total_seconds() < 2710
    first = api.get("/api/demo-sessions").json()
    again = api.post(
        "/api/demo-sessions",
        json={"role": "merchant", "owner_session_id": str(uuid4())},
    )
    assert again.status_code == 200
    assert again.json() == first
    assert token not in again.text
    assert api.cookies[COOKIE] == token
    with Session(postgres_engine) as session:
        row = session.get(DemoSession, original[0])
        assert row.expires_at == original[1]
    with visitor() as guest:
        response = guest.post("/api/demo-sessions")
        cookie = response.headers["set-cookie"].lower()
        for expected in (
            "httponly",
            "secure",
            "samesite=lax",
            "path=/api",
            "max-age=2700",
        ):
            assert expected in cookie
        assert "domain=" not in cookie


@pytest.mark.parametrize("token", [None, "invented", "a" * 43, "é" * 43])
def test_direct_api_missing_or_forged_session(api, token):
    with visitor() as guest:
        if token and token.isascii():
            guest.cookies.set(COOKIE, token, path="/api")
        for method, path in [
            ("GET", "/api/bookings"),
            ("POST", "/api/bookings"),
            ("GET", "/api/demo-sessions"),
        ]:
            result = guest.request(method, path, json={"title": "Must not create"})
            assert result.status_code == 401
            assert result.headers["cache-control"] == "private, no-store"
            assert result.headers["x-vercel-enable-rewrite-caching"] == "0"


@pytest.mark.parametrize(
    "origin", [None, "null", "https://evil.example", "https://testserver.evil"]
)
def test_origin_required_for_issuance_and_mutation(api, origin):
    headers = {"Origin": origin} if origin else {}
    with visitor() as guest:
        guest.headers.clear()
        assert guest.post("/api/demo-sessions", headers=headers).status_code == 403
    original = api.headers.pop("Origin")
    try:
        assert (
            api.post(
                "/api/bookings", json={"title": "Blocked"}, headers=headers
            ).status_code
            == 403
        )
    finally:
        api.headers["Origin"] = original


@pytest.mark.parametrize("csrf", [None, "bad", "a" * 64])
def test_csrf_required_even_with_cookie(api, csrf):
    saved = api.headers.pop("X-BeforePay-CSRF")
    try:
        headers = {"X-BeforePay-CSRF": csrf} if csrf else {}
        assert (
            api.post(
                "/api/bookings", json={"title": "Blocked"}, headers=headers
            ).status_code
            == 403
        )
        assert api.delete("/api/demo-sessions", headers=headers).status_code == 403
    finally:
        api.headers["X-BeforePay-CSRF"] = saved


def test_expiry_and_revocation_preserve_records(api, postgres_engine):
    booking = create(api)
    token = api.cookies[COOKIE]
    expire(postgres_engine, api)
    for method, path in [
        ("GET", "/api/bookings"),
        ("GET", f"/api/bookings/{booking}"),
        ("POST", "/api/bookings"),
    ]:
        assert api.request(method, path, json={"title": "Blocked"}).status_code == 401
    assert api.get("/api/demo-sessions").status_code == 401
    assert api.post("/api/demo-sessions").status_code == 201
    assert api.cookies[COOKIE] != token
    assert api.get("/api/bookings").json() == []
    active = api.get("/api/demo-sessions").json()
    api.headers["X-BeforePay-CSRF"] = active["csrf_token"]
    assert api.delete("/api/demo-sessions").status_code == 204
    assert api.get("/api/bookings").status_code == 401
    with Session(postgres_engine) as session:
        assert session.get(Booking, UUID(booking)) is not None
    with visitor() as replay:
        replay.cookies.set(COOKIE, token, path="/api")
        assert replay.get("/api/bookings").status_code == 401


def test_independent_scope_csrf_and_no_role_authority(api, postgres_engine):
    booking = create(api)
    with visitor(True) as other:
        own = create(other)
        assert [b["id"] for b in other.get("/api/bookings").json()] == [own]
        assert [b["id"] for b in api.get("/api/bookings").json()] == [booking]
        assert (
            other.get(
                f"/api/bookings/{booking}", headers={"X-Demo-Role": "merchant"}
            ).status_code
            == 404
        )
        assert (
            other.post(
                "/api/bookings",
                json={"title": "Blocked"},
                headers={"X-BeforePay-CSRF": api.headers["X-BeforePay-CSRF"]},
            ).status_code
            == 403
        )
        assert (
            other.get(
                "/api/bookings", headers={"Sec-Fetch-Site": "cross-site"}
            ).status_code
            == 403
        )
        # Legacy local records remain unassigned, with no public adoption route.
        with Session(postgres_engine) as session:
            legacy = Booking(title="Unowned historical local record")
            session.add(legacy)
            session.commit()
            legacy_id = legacy.id
        assert api.get(f"/api/bookings/{legacy_id}").status_code == 404
        assert other.get(f"/api/bookings/{legacy_id}").status_code == 404
        with Session(postgres_engine) as session:
            with pytest.raises(DBAPIError, match="ownership is immutable"):
                session.execute(
                    update(Booking)
                    .where(Booking.id == legacy_id)
                    .values(
                        owner_session_id=session.scalar(
                            select(Booking.owner_session_id).where(
                                Booking.id == UUID(own)
                            )
                        )
                    )
                )
                session.commit()


BOOKING_ROUTES = [
    (method.upper(), path)
    for path, methods in app.openapi()["paths"].items()
    if path.startswith("/api/bookings/{booking_id}")
    for method in methods
    if method in {"get", "post", "put", "patch", "delete"}
]


@pytest.mark.parametrize("method,template", BOOKING_ROUTES)
def test_every_booking_route_gates_foreign_and_missing_sessions(
    api, postgres_engine, method, template
):
    booking = create(api)
    path = re.sub(
        r"\{([^}]+)\}",
        lambda match: booking if match[1] == "booking_id" else str(uuid4()),
        template,
    )
    with visitor(True) as other, visitor() as guest:
        for client, expected in [(other, 404), (guest, 401)]:
            kwargs = (
                {
                    "files": {"file": ("quote.pdf", b"unparsed", "application/pdf")},
                    "data": {"source_type": "quotation"},
                }
                if path.endswith("/sources/pdf")
                else {"json": {}}
            )
            response = client.request(method, path, **kwargs)
            assert response.status_code == expected, (method, template, response.text)
        expire(postgres_engine, other)
        assert other.request(method, path, **kwargs).status_code == 401


def test_nested_foreign_source_draft_and_agreement_references(api, postgres_engine):
    victim = seed_review(api, postgres_engine)
    with visitor(True) as other:
        own = create(other)
        base = f"/api/bookings/{own}"
        for kind, value in [
            ("sources", victim["source"]["id"]),
            ("drafts", victim["draft"]["id"]),
            ("agreements", victim["agreement"]["id"]),
        ]:
            assert other.get(f"{base}/{kind}/{value}").status_code == 404
        response = other.post(
            base + "/drafts", json={"source_ids": [victim["source"]["id"]]}
        )
        assert response.status_code == 422
        response = other.post(
            base + "/agreements/from-draft",
            json={"draft_id": victim["draft"]["id"], "customer_label": "Demo"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "latest_booking_draft_required"


def test_expired_during_inference_cannot_publish(api, postgres_engine):
    booking = create(api)
    source = api.post(
        f"/api/bookings/{booking}/sources/text",
        json={"source_type": "quotation", "original_text": "Synthetic camera terms"},
    ).json()

    class Extractor:
        def extract(self, snapshots):
            expire(postgres_engine, api)
            return ProviderResult(Extraction.model_validate(empty()), metadata())

    app.dependency_overrides[get_extractor] = lambda: Extractor()
    response = api.post(
        f"/api/bookings/{booking}/drafts", json={"source_ids": [source["id"]]}
    )
    assert response.status_code == 401
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(DraftVersion)
                .where(DraftVersion.booking_id == UUID(booking))
            )
            == 0
        )


def test_all_booking_routes_use_owned_dependency():
    from app.demo_sessions.service import owned_session

    def contains(dependency):
        return dependency.call is owned_session or any(
            contains(child) for child in dependency.dependencies
        )

    routes = [
        r
        for included in app.routes
        if hasattr(included, "original_router")
        for r in included.original_router.routes
        if getattr(r, "path", "").startswith("/api/bookings")
    ]
    assert len(routes) >= 40
    assert all(contains(route.dependant) for route in routes)
    assert {
        path
        for path in app.openapi()["paths"]
        if path.startswith("/api/") and not path.startswith("/api/bookings")
    } == {
        "/api/health/live",
        "/api/health/ready",
        "/api/demo-sessions",
        "/api/demo-templates",
        "/api/paypal/sandbox/webhook",
    }


@pytest.mark.parametrize(
    "origins",
    [["*"], ["https://demo.example/path"], ["http://public.example"], ["null"]],
)
def test_configuration_rejects_unsafe_origins(origins):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, demo_allowed_origins=origins)


def test_insecure_cookies_only_loopback():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            demo_cookie_secure=False,
            demo_allowed_origins=["https://demo.example"],
        )
    assert (
        Settings(_env_file=None, demo_cookie_secure=False).demo_cookie_secure is False
    )


def test_owner_trigger_enabled(postgres_engine):
    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT tgenabled FROM pg_trigger "
                    "WHERE tgname='bookings_owner_immutable'"
                )
            )
            == "O"
        )
