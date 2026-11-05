"""Public controls use real disposable PostgreSQL and mocked providers only."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_booking_comparisons import compare, content, fake_policy, save
from test_cancellation_preview import context as cancellation_context
from test_cancellation_preview import rules, target
from test_clarifications import install as install_clarifier
from test_demo_sessions import visitor
from test_drafts import empty, metadata
from test_policy_consistency import install as install_consistency

from app.admission.models import Admission
from app.admission.service import reserve, run_ai
from app.cancellations.provider import GeminiRuleProposer, get_rule_proposer
from app.cancellations.schemas import Rules
from app.clarifications.provider import GeminiClarifier
from app.comparisons.provider import GeminiPolicyComparator, PolicyResult
from app.core.config import Settings
from app.demo_sessions.models import DemoSession
from app.demo_sessions.service import COOKIE, token_hash
from app.drafts.provider import GeminiExtractor, ProviderResult, get_extractor
from app.drafts.schemas import Extraction
from app.main import app
from app.policy_consistency.provider import GeminiConsistencyChecker


@pytest.fixture
def controls(api, postgres_engine, monkeypatch):
    assert postgres_engine.url.database.startswith("contextkey_test_")
    # Test-only reset between cases; runtime has no reset/delete endpoint.
    with postgres_engine.begin() as connection:
        connection.execute(text("TRUNCATE demo_admissions"))
        connection.execute(
            text("UPDATE demo_admission_control SET circuit_reason=NULL")
        )

    def enable(**overrides):
        values = dict(
            public_demo_mode=True,
            database_url=postgres_engine.url.render_as_string(hide_password=False),
            public_demo_database=postgres_engine.url.database,
            demo_allowed_origins=["https://testserver"],
            demo_ai_calls_per_day=20,
            demo_ai_calls_per_minute=20,
            demo_ai_tokens_per_day=4_000_000,
            demo_ai_tokens_per_minute=4_000_000,
            demo_ai_cooldown_seconds=0,
        )
        values.update(overrides)
        settings = Settings(_env_file=None, **values)
        for path in (
            "app.admission.service",
            "app.demo_sessions.router",
            "app.evidence.router",
            "app.payments.router",
            "app.core.body_limit",
        ):
            monkeypatch.setattr(path + ".get_settings", lambda: settings)
        return settings

    return enable


def owner(engine, client):
    with Session(engine) as db:
        return db.scalar(
            select(DemoSession.id).where(
                DemoSession.token_hash == token_hash(client.cookies[COOKIE])
            )
        )


def caller(engine, identity):
    db = Session(engine)
    db.info["demo_session_id"] = identity
    return db


def charges(engine, kind="ai"):
    with Session(engine) as db:
        return list(db.scalars(select(Admission).where(Admission.kind == kind)))


@pytest.mark.parametrize(
    "action", ["extraction", "comparison", "clarification", "consistency", "rules"]
)
@pytest.mark.parametrize("allowed", [False, True])
def test_every_ai_entry_point(api, postgres_engine, controls, action, allowed):
    ctx = cancellation_context.__wrapped__(api, postgres_engine)
    data = content(ctx)
    data["deposit_conditions"][0]["value"] = "The deposit is non-refundable."
    proposal = save(api, ctx, data).json()
    fake_policy("differs")
    comparison = compare(api, ctx, proposal).json()
    base = f"/api/bookings/{ctx['booking']}"
    fake = Mock()
    if action == "extraction":
        fake.extract.return_value = ProviderResult(
            Extraction.model_validate(empty()), metadata()
        )
        app.dependency_overrides[get_extractor] = lambda: fake
        path, body, method = (
            base + "/drafts",
            {"source_ids": [ctx["source"]["id"]]},
            "extract",
        )
    elif action == "comparison":
        fake = fake_policy("differs")
        path, body, method = (
            base + "/comparisons",
            {
                "agreement_id": ctx["agreement"]["id"],
                "agreement_fingerprint": ctx["agreement"]["fingerprint"],
                "proposal_id": proposal["id"],
                "proposal_fingerprint": proposal["fingerprint"],
            },
            "compare",
        )
    elif action == "clarification":
        fake = install_clarifier()
        path, body, method = (
            base + f"/comparisons/{comparison['id']}/clarifications",
            {
                "comparison_fingerprint": comparison["fingerprint"],
                "category": "deposit_conditions",
            },
            "suggest",
        )
    elif action == "consistency":
        fake = install_consistency()
        path, body, method = (
            base + "/policy-consistency",
            {
                "proposal_id": proposal["id"],
                "proposal_fingerprint": proposal["fingerprint"],
            },
            "check",
        )
    else:
        fake.compare.return_value = PolicyResult(Rules.model_validate(rules()), {})
        app.dependency_overrides[get_rule_proposer] = lambda: fake
        path, body, method = (
            base + "/cancellation/rules/propose",
            {
                "target": target(ctx),
                "expected_latest_rule_id": None,
                "customer_label": "Provisional reviewer",
            },
            "compare",
        )
    controls(demo_ai_calls_per_day=20 if allowed else 0)
    result = api.post(path, json=body)
    assert result.status_code == (201 if allowed else 429), result.text
    assert getattr(fake, method).call_count == int(allowed)
    rows = charges(postgres_engine)
    assert len(rows) == int(allowed)
    if allowed:
        assert rows[0].action == action and rows[0].finished_at is not None
        assert rows[0].booking_id == UUID(ctx["booking"])
        assert len(rows[0].input_hash) == 64 and rows[0].units >= 48768


def test_concurrent_global_slot_and_inflight_replay(api, postgres_engine, controls):
    controls(demo_ai_concurrent_global=1)
    identity = owner(postgres_engine, api)
    entered, release = Event(), Event()

    def request():
        with caller(postgres_engine, identity) as db:
            return run_ai(
                db,
                "extraction",
                {"saved_fingerprint": "a" * 64},
                lambda: (entered.set(), release.wait(5)),
                booking_id=uuid4(),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(request)
        assert entered.wait(5)
        try:
            with caller(postgres_engine, identity) as db:
                for context, code in [
                    ({"saved_fingerprint": "a" * 64}, "demo_ai_in_flight"),
                    ({"saved_fingerprint": "b" * 64}, "demo_ai_busy"),
                ]:
                    with pytest.raises(HTTPException) as error:
                        run_ai(
                            db,
                            "extraction",
                            context,
                            lambda: pytest.fail("Unadmitted provider call"),
                            booking_id=uuid4(),
                        )
                    assert error.value.detail["code"] == code
        finally:
            release.set()
        future.result()
    assert len(charges(postgres_engine)) == 1
    assert charges(postgres_engine)[0].finished_at is not None


@pytest.mark.parametrize(
    "limits",
    [
        {"demo_ai_calls_per_day": 1},
        {"demo_ai_calls_per_session": 1},
        {"demo_ai_calls_per_minute": 1},
        {"demo_ai_tokens_per_session": 49000},
        {"demo_ai_tokens_per_day": 49000},
        {"demo_ai_tokens_per_minute": 49000},
        {"demo_ai_cooldown_seconds": 60},
    ],
)
def test_durable_usage_and_rate_limits(api, postgres_engine, controls, limits):
    controls(**limits)
    identity = owner(postgres_engine, api)
    with caller(postgres_engine, identity) as db:
        run_ai(db, "comparison", {}, lambda: None, booking_id=uuid4())
        db.rollback()
    # Independent connection/process-equivalent view; caller rollback cannot refund.
    with caller(postgres_engine, identity) as db:
        with pytest.raises(HTTPException) as error:
            run_ai(
                db,
                "comparison",
                {"other": True},
                lambda: pytest.fail("Over-budget call"),
                booking_id=uuid4(),
            )
        assert error.value.status_code == 429
    assert len(charges(postgres_engine)) == 1


def test_atomic_last_call_race(api, postgres_engine, controls):
    controls(demo_ai_calls_per_day=1, demo_ai_concurrent_global=4)
    identity = owner(postgres_engine, api)

    def request(index):
        with caller(postgres_engine, identity) as db:
            try:
                run_ai(
                    db, "comparison", {"index": index}, lambda: None, booking_id=uuid4()
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(request, range(8)))
    assert sorted(results) == [200] + [429] * 7
    assert len(charges(postgres_engine)) == 1


def test_per_session_slot_does_not_block_another_owner(api, postgres_engine, controls):
    controls(demo_ai_concurrent_global=3, demo_ai_concurrent_session=1)
    with caller(postgres_engine, owner(postgres_engine, api)) as db:
        reserve(db, "ai", "extraction", {"input": "one"}, units=100)
        with pytest.raises(HTTPException) as error:
            run_ai(
                db,
                "rules",
                {},
                lambda: pytest.fail("Same owner slot"),
                booking_id=uuid4(),
            )
        assert error.value.detail["code"] == "demo_ai_busy"
    with (
        visitor(True) as other,
        caller(postgres_engine, owner(postgres_engine, other)) as db,
    ):
        run_ai(db, "rules", {}, lambda: None, booking_id=uuid4())
    assert len(charges(postgres_engine)) == 2


def test_stale_result_retains_committed_charge(api, postgres_engine, controls):
    ctx = cancellation_context.__wrapped__(api, postgres_engine)
    data = content(ctx)
    data["deposit_conditions"][0]["value"] = "Non-refundable deposit."
    proposal = save(api, ctx, data).json()
    fake_policy(
        "differs", before=lambda: save(api, ctx, content(ctx), expected=proposal["id"])
    )
    controls()
    assert compare(api, ctx, proposal).status_code == 409
    assert len(charges(postgres_engine)) == 1
    assert charges(postgres_engine)[0].finished_at is not None


def test_atomic_session_creation_cap(api, postgres_engine, controls):
    controls(demo_max_sessions=1)

    def enter(_):
        with visitor() as client:
            return client.post("/api/demo-sessions").status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(enter, range(6)))
    assert sorted(results) == [201] + [429] * 5
    assert len(charges(postgres_engine, "session")) == 1


@pytest.mark.parametrize("code", ["ai_rate_limited", "ai_credentials_rejected"])
def test_provider_failure_trips_shared_circuit(api, postgres_engine, controls, code):
    controls()
    identity = owner(postgres_engine, api)

    def failure():
        raise HTTPException(503, {"code": code, "message": "Safe provider failure"})

    with caller(postgres_engine, identity) as db:
        with pytest.raises(HTTPException):
            run_ai(db, "extraction", {}, failure, booking_id=uuid4())
    with (
        visitor(True) as other,
        caller(postgres_engine, owner(postgres_engine, other)) as db,
    ):
        with pytest.raises(HTTPException) as error:
            run_ai(
                db,
                "comparison",
                {},
                lambda: pytest.fail("Circuit must stop calls"),
                booking_id=uuid4(),
            )
        assert error.value.detail["code"] == "demo_ai_paused"
    assert len(charges(postgres_engine)) == 1


def test_abandoned_slot_is_fail_closed_and_charge_immutable(
    api, postgres_engine, controls
):
    controls()
    identity = owner(postgres_engine, api)
    with caller(postgres_engine, identity) as db:
        ident = reserve(db, "ai", "comparison", {}, units=100)
    with caller(postgres_engine, identity) as db:
        with pytest.raises(HTTPException):
            run_ai(
                db,
                "rules",
                {},
                lambda: pytest.fail("Abandoned slot"),
                booking_id=uuid4(),
            )
    with Session(postgres_engine) as db:
        with pytest.raises(DBAPIError, match="immutable"):
            db.execute(update(Admission).where(Admission.id == ident).values(units=0))
            db.commit()


@pytest.mark.parametrize(
    "provider,method,args",
    [
        (GeminiExtractor, "extract", []),
        (GeminiPolicyComparator, "compare", []),
        (GeminiClarifier, "suggest", {}),
        (GeminiConsistencyChecker, "check", []),
        (GeminiRuleProposer, "compare", []),
    ],
)
def test_provider_boundary_cannot_bypass_admission(controls, provider, method, args):
    controls()
    with pytest.raises(HTTPException) as error:
        getattr(provider(), method)(args)
    assert error.value.detail["code"] == "demo_ai_admission_required"


def test_session_cycling_cannot_reset_ai_or_booking_caps(
    api, postgres_engine, controls
):
    controls(demo_ai_calls_per_day=1, demo_max_bookings=1)
    assert (
        api.post("/api/bookings", json={"title": "One synthetic booking"}).status_code
        == 201
    )
    with caller(postgres_engine, owner(postgres_engine, api)) as db:
        run_ai(db, "extraction", {}, lambda: None, booking_id=uuid4())
    assert api.delete("/api/demo-sessions").status_code == 204
    with visitor(True) as other:
        assert other.get("/api/bookings").json() == []
        assert (
            other.post(
                "/api/bookings", json={"title": "Blocked new session"}
            ).status_code
            == 429
        )
        with caller(postgres_engine, owner(postgres_engine, other)) as db:
            with pytest.raises(HTTPException):
                run_ai(
                    db,
                    "comparison",
                    {},
                    lambda: pytest.fail("Session cycling"),
                    booking_id=uuid4(),
                )


@pytest.mark.parametrize(
    "limits", [{"demo_max_sessions": 1}, {"demo_sessions_per_hour": 1}]
)
def test_session_creation_global_caps(api, controls, limits):
    controls(**limits)
    with visitor(True) as first:
        assert first.post("/api/demo-sessions").status_code == 200
        assert first.delete("/api/demo-sessions").status_code == 204
    with visitor() as second:
        result = second.post("/api/demo-sessions")
        assert result.status_code == 429
        assert result.json()["detail"]["code"] == "demo_session_limit"


def test_source_storage_upload_and_write_limits(api, postgres_engine, controls):
    booking = api.post(
        "/api/bookings", json={"title": "Synthetic source budget"}
    ).json()["id"]
    controls(demo_source_bytes=4, demo_sources_per_session=1)
    base = f"/api/bookings/{booking}/sources"
    assert (
        api.post(
            base + "/text", json={"source_type": "quotation", "original_text": "text"}
        ).status_code
        == 201
    )
    assert (
        api.post(
            base + "/text", json={"source_type": "quotation", "original_text": "more"}
        ).status_code
        == 429
    )
    controls(demo_upload_bytes=1)
    result = api.post(
        base + "/pdf",
        data={"source_type": "quotation"},
        files={"file": ("synthetic.pdf", b"%PDF-invalid", "application/pdf")},
    )
    assert result.status_code == 429
    assert not charges(postgres_engine, "upload")
    controls(demo_max_writes=0)
    assert api.post("/api/bookings", json={"title": "Write blocked"}).status_code == 429


def test_public_upload_and_text_size_limits(api, controls):
    booking = api.post(
        "/api/bookings", json={"title": "Synthetic small upload"}
    ).json()["id"]
    controls(demo_pdf_max_bytes=32, demo_source_max_chars=4)
    base = f"/api/bookings/{booking}/sources"
    assert (
        api.post(
            base + "/pdf",
            data={"source_type": "quotation"},
            files={"file": ("synthetic.pdf", b"%PDF-" + b"x" * 32, "application/pdf")},
        ).status_code
        == 413
    )
    assert (
        api.post(
            base + "/text",
            json={"source_type": "quotation", "original_text": "too long"},
        ).status_code
        == 413
    )


def test_public_pdf_extraction_and_parser_limits(api, postgres_engine, controls):
    from test_bookings_evidence import make_pdf

    booking = api.post("/api/bookings", json={"title": "Synthetic PDF parsing"}).json()[
        "id"
    ]
    base = f"/api/bookings/{booking}/sources"
    controls(demo_source_bytes_per_session=2_000_000)
    result = api.post(
        base + "/pdf",
        data={"source_type": "quotation"},
        files={
            "file": (
                "synthetic.pdf",
                make_pdf(texts=("Camera with batteries",)),
                "application/pdf",
            )
        },
    )
    assert result.status_code == 201, result.text
    assert len(result.json()["pages"]) == 1
    assert api.get(base + "/" + result.json()["id"]).json() == result.json()
    assert charges(postgres_engine, "source")[0].units == 40_000 * 8
    controls(demo_source_bytes_per_session=2_000_000, demo_pdf_max_pages=1)
    result = api.post(
        base + "/pdf",
        data={"source_type": "quotation"},
        files={"file": ("synthetic.pdf", make_pdf(), "application/pdf")},
    )
    assert (
        result.status_code == 413
        and result.json()["detail"]["code"] == "too_many_pages"
    )
    controls(demo_source_bytes_per_session=2_000_000, demo_source_max_chars=4)
    result = api.post(
        base + "/pdf",
        data={"source_type": "quotation"},
        files={
            "file": (
                "synthetic.pdf",
                make_pdf(texts=("Camera with batteries",)),
                "application/pdf",
            )
        },
    )
    assert (
        result.status_code == 413 and result.json()["detail"]["code"] == "text_too_long"
    )
