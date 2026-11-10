from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Event, Lock, Timer
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_hosting_preparation import isolated_hosting as hosting_fixture

from app.bookings.router import lock_booking
from app.core.database import Base
from app.main import app
from scripts.setup_demo import setup

isolated_hosting = hosting_fixture


@pytest.fixture
def restricted_hosting(request, monkeypatch):
    owner, _, _, settings = request.getfixturevalue("isolated_hosting")
    settings.vercel = True
    setup(owner, settings.public_demo_database)
    role = "beforepay_snapshot_" + uuid4().hex
    tables = sorted(Base.metadata.tables)
    readonly = {
        "demo_admission_control",
        "demo_deployment",
        "demo_templates",
        "payment_attempts",
        "payment_events",
        "paypal_webhook_events",
        "sandbox_receipts",
    }
    with owner.begin() as conn:
        conn.execute(text(f'CREATE ROLE "{role}" NOINHERIT'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
        conn.execute(
            text(f'GRANT SELECT ON {", ".join(tables)}, alembic_version TO "{role}"')
        )
        conn.execute(
            text(
                "GRANT INSERT ON "
                + ", ".join(t for t in tables if t not in readonly)
                + f' TO "{role}"'
            )
        )
        for table, column in (
            ("bookings", "owner_session_id"),
            ("demo_sessions", "revoked_at"),
            ("demo_admissions", "finished_at"),
            ("demo_admission_control", "circuit_reason"),
        ):
            conn.execute(text(f'GRANT UPDATE ({column}) ON {table} TO "{role}"'))
    runtime = create_engine(owner.url, pool_size=2, max_overflow=0, pool_timeout=3)
    admission = create_engine(owner.url, pool_size=1, max_overflow=0, pool_timeout=3)
    for engine in (runtime, admission):

        @event.listens_for(engine, "connect")
        def restricted_connection(dbapi, _):
            with dbapi.cursor() as cursor:
                cursor.execute(f'SET ROLE "{role}"')
            dbapi.commit()

        @event.listens_for(engine, "begin")
        def bounded_transaction(connection):
            connection.exec_driver_sql("SET LOCAL lock_timeout = '500ms'")

    monkeypatch.setattr("app.core.database.get_engine", lambda: runtime)
    monkeypatch.setattr("app.core.database.get_admission_engine", lambda: admission)
    try:
        yield runtime
    finally:
        runtime.dispose()
        admission.dispose()
        with owner.begin() as conn:
            conn.execute(text(f'DROP OWNED BY "{role}"'))
            conn.execute(text(f'DROP ROLE "{role}"'))


def test_saved_state_routes_under_restricted_role(restricted_hosting):
    statements = []

    @event.listens_for(restricted_hosting, "before_cursor_execute")
    def capture_locks(_conn, _cursor, statement, *_):
        if "FOR " in statement and "bookings" in statement:
            statements.append(statement)

    with TestClient(
        app,
        base_url="https://beforepay.example",
        headers={"Origin": "https://beforepay.example"},
    ) as client:
        login = client.post("/api/demo-sessions")
        assert login.status_code == 201
        client.headers["X-BeforePay-CSRF"] = login.json()["csrf_token"]
        created = client.post(
            "/api/bookings", json={"title": "Synthetic restricted snapshot"}
        )
        assert created.status_code == 201
        base = "/api/bookings/" + created.json()["id"]
        paths = [
            "/review",
            "/merchant-bookings?limit=1",
            "/comparisons?limit=1",
            "/cancellation/rules?limit=100&offset=0",
            "/checkout/attempts",
            "/checkout/eligibility",
            "/saved-state",
        ]
        for path in paths:
            response = client.get(base + path)
            assert response.status_code == 200, (path, response.text)
        with ThreadPoolExecutor(max_workers=6) as workers:
            responses = list(workers.map(lambda path: client.get(base + path), paths))
        assert [r.status_code for r in responses] == [200] * len(paths)
        assert statements and all(s.endswith("FOR SHARE") for s in statements)
        statements.clear()
        assert (
            client.post(
                base + "/sources/text",
                json={
                    "source_type": "message",
                    "original_text": "Synthetic lock probe",
                },
            ).status_code
            == 201
        )
        assert statements and all(s.endswith("FOR UPDATE") for s in statements)
        assert client.get(base + "/checkout/config").status_code == 403
        assert (
            client.post(
                base + "/checkout/orders", json={"approval_id": str(uuid4())}
            ).status_code
            == 403
        )
        with TestClient(
            app,
            base_url="https://beforepay.example",
            headers={"Origin": "https://beforepay.example"},
        ) as other:
            assert other.post("/api/demo-sessions").status_code == 201
            for path in paths:
                assert other.get(base + path).status_code == 404


def test_parallel_saved_state_gets_do_not_wait_for_each_other(restricted_hosting):
    with TestClient(
        app,
        base_url="https://beforepay.example",
        headers={"Origin": "https://beforepay.example"},
    ) as client:
        login = client.post("/api/demo-sessions")
        assert login.status_code == 201
        client.headers["X-BeforePay-CSRF"] = login.json()["csrf_token"]
        created = client.post("/api/bookings", json={"title": "Parallel readers"})
        assert created.status_code == 201
        base = "/api/bookings/" + created.json()["id"]
        held, release = Event(), Event()
        once = Lock()

        @event.listens_for(restricted_hosting, "after_cursor_execute")
        def hold_first_reader(_conn, _cursor, statement, *_):
            if "FOR " in statement and "bookings" in statement:
                if once.acquire(blocking=False):
                    held.set()
                    assert release.wait(10), "Reader was not released"

        with ThreadPoolExecutor(max_workers=6) as workers:
            first = workers.submit(client.get, base + "/review")
            assert held.wait(3)
            try:
                paths = [
                    "/merchant-bookings?limit=1",
                    "/comparisons?limit=1",
                    "/cancellation/rules?limit=100&offset=0",
                    "/checkout/attempts",
                    "/checkout/eligibility",
                    "/saved-state",
                ]
                pending = [workers.submit(client.get, base + path) for path in paths]
                for response in pending:
                    assert response.result(timeout=3).status_code == 200
                assert not first.done()
            finally:
                release.set()
            assert first.result(timeout=3).status_code == 200


def test_read_burst_pool_timeout_and_bounded_lifecycle(restricted_hosting, caplog):
    """Delayed read workload, not a claim about measured hosted query latency."""
    runtime = restricted_hosting
    assert runtime.pool.size() == 2
    assert runtime.pool._max_overflow == 0 and runtime.pool.timeout() == 3
    with TestClient(
        app,
        base_url="https://beforepay.example",
        headers={"Origin": "https://beforepay.example"},
    ) as client:
        login = client.post("/api/demo-sessions")
        client.headers["X-BeforePay-CSRF"] = login.json()["csrf_token"]
        booking = client.post(
            "/api/bookings", json={"title": "Synthetic read burst"}
        ).json()["id"]
        base = f"/api/bookings/{booking}"
        paths = [
            "/review",
            "/merchant-bookings",
            "/comparisons",
            "/cancellation/rules",
            "/checkout/attempts",
            "/checkout/eligibility",
            "/saved-state",
        ]
        release, lock = Event(), Lock()
        starts = 0
        checkouts = []

        def checkout(dbapi, *_):
            checkouts.append(id(dbapi))

        def delayed_readiness(_connection, _cursor, statement, *_):
            nonlocal starts
            if statement == "SELECT current_database()":
                with lock:
                    starts += 1
                    hold = starts <= 2
                if hold:
                    assert release.wait(10)

        event.listen(runtime, "checkout", checkout)
        event.listen(runtime, "before_cursor_execute", delayed_readiness)
        try:
            with ThreadPoolExecutor(max_workers=6) as workers:
                futures = [workers.submit(client.get, base + path) for path in paths]
                try:
                    done, _ = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
                    assert done
                    assert any(f.result().status_code == 503 for f in done)
                finally:
                    release.set()
                responses = [f.result(timeout=5) for f in futures]
            assert any(r.status_code == 503 for r in responses)
            assert '"exception_type": "PoolTimeout"' in caplog.text
            assert '"check": "database_identity"' in caplog.text
            assert runtime.pool.checkedout() == 0
            # Same slow workload with the frontend's new two-read admission bound.
            release.clear()
            starts = 0
            checkouts.clear()
            timer = Timer(3.2, release.set)
            timer.start()
            try:
                with ThreadPoolExecutor(max_workers=2) as workers:
                    responses = list(
                        workers.map(lambda path: client.get(base + path), paths)
                    )
            finally:
                release.set()
                timer.join()
            assert all(r.status_code == 200 for r in responses)
            assert len(checkouts) == len(
                paths
            )  # One connection per request, no nested checkout.
            assert len(set(checkouts)) <= 2
            assert starts == len(paths)  # Readiness retained on every request.
            assert runtime.pool.checkedout() == 0
            assert (
                client.get(
                    base + "/sources/00000000-0000-0000-0000-000000000000"
                ).status_code
                == 404
            )
            assert runtime.pool.checkedout() == 0  # Error cleanup, too.
        finally:
            release.set()
            event.remove(runtime, "checkout", checkout)
            event.remove(runtime, "before_cursor_execute", delayed_readiness)


@pytest.mark.parametrize(
    "holder_read,contender_read", [(True, False), (False, True), (False, False)]
)
def test_mutations_still_exclude_readers_and_other_mutations(
    restricted_hosting,
    holder_read,
    contender_read,
):
    with TestClient(
        app,
        base_url="https://beforepay.example",
        headers={"Origin": "https://beforepay.example"},
    ) as client:
        login = client.post("/api/demo-sessions")
        client.headers["X-BeforePay-CSRF"] = login.json()["csrf_token"]
        booking = client.post(
            "/api/bookings", json={"title": "Mutation lock probe"}
        ).json()
    from uuid import UUID

    ident = UUID(booking["id"])
    with Session(restricted_hosting) as lookup:
        owner = lookup.scalar(
            text("SELECT owner_session_id FROM bookings WHERE id=:id"), {"id": ident}
        )
    with (
        Session(restricted_hosting) as holder,
        Session(restricted_hosting) as contender,
    ):
        holder.info["demo_session_id"] = owner
        contender.info["demo_session_id"] = owner
        # Absence of the safe-read marker preserves the exclusive default used
        # by payment actions and internal/webhook callers.
        if holder_read:
            holder.info["booking_read_only"] = True
        if contender_read:
            contender.info["booking_read_only"] = True
        lock_booking(holder, ident)
        with pytest.raises(OperationalError) as blocked:
            lock_booking(contender, ident)
        assert blocked.value.orig.sqlstate == "55P03"
        contender.rollback()
        holder.rollback()
        assert lock_booking(contender, ident).id == ident
