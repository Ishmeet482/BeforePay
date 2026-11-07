import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session
from test_hosting_preparation import isolated_hosting as isolated_hosting

from app.core.config import Settings
from app.hosting.diagnostics import log_settings_failure, logger
from app.hosting.middleware import HostingBoundary
from app.hosting.readiness import require_public_database
from scripts.setup_demo import setup

SECRET = "private-value-must-never-appear"


def diagnostic(caplog):
    records = [r for r in caplog.records if r.name == logger.name]
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is None and record.stack_info is None
    assert SECRET not in record.getMessage()
    assert SECRET not in repr(record.args)
    return json.loads(record.getMessage().split(" ", 1)[1])


def test_settings_failure_logs_fields_not_values_or_request(monkeypatch, caplog):
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None, db_pool_timeout=SECRET)

    def invalid_settings():
        raise raised.value

    async def downstream(*args):
        raise AssertionError("Invalid settings must stop request processing")

    monkeypatch.setattr("app.hosting.middleware.get_settings", invalid_settings)
    response = TestClient(HostingBoundary(downstream)).get(
        "/api/bookings?private=" + SECRET, headers={"Cookie": "secret=" + SECRET}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "public_setup_required"
    result = diagnostic(caplog)
    assert result == {
        "boundary": "settings_validation",
        "exception_type": "ValidationError",
        "fields": ["db_pool_timeout"],
        "model_validation": False,
    }
    assert SECRET not in response.text


def test_model_settings_validation_is_distinct_without_context(caplog):
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None, vercel=True)
    log_settings_failure(raised.value)
    result = diagnostic(caplog)
    assert result["boundary"] == "settings_validation"
    assert result["fields"] == []
    assert result["model_validation"] is True


@pytest.mark.parametrize("state", ["55P03", "57014", "42501", SECRET])
def test_database_error_logs_stage_and_allowlisted_state_only(caplog, state):
    class DriverError(Exception):
        sqlstate = state

    session = Mock()
    session.scalar.side_effect = [
        "synthetic_db",
        OperationalError("SELECT " + SECRET, {"secret": SECRET}, DriverError(SECRET)),
    ]
    settings = Settings(_env_file=None).model_copy(update={"public_demo_mode": True})
    with pytest.raises(HTTPException) as raised:
        require_public_database(session, settings)
    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "public_setup_required"
    assert SECRET not in str(raised.value.detail)
    result = diagnostic(caplog)
    assert result["boundary"] == "database_readiness"
    assert result["check"] == "migration_revision"
    assert result["exception_type"] == "OperationalError"
    assert result["sqlstate"] == (state if state != SECRET else "OTHER")
    assert session.scalar.call_count == 2  # No retry.
    session.rollback.assert_called_once()


def test_pool_timeout_is_distinct_and_not_retried(caplog):
    session = Mock()
    session.scalar.side_effect = PoolTimeout(SECRET)
    settings = Settings(_env_file=None).model_copy(update={"public_demo_mode": True})
    with pytest.raises(HTTPException):
        require_public_database(session, settings)
    result = diagnostic(caplog)
    assert result["exception_type"] == "PoolTimeout"
    assert result["check"] == "database_identity"
    assert result["sqlstate"] is None
    session.scalar.assert_called_once()
    session.rollback.assert_called_once()


def test_real_pool_exhaustion_and_recovery_without_retry(isolated_hosting, caplog):
    engine, runtime, _, settings = isolated_hosting
    setup(engine, settings.public_demo_database)
    # Occupy both runtime slots; leave production limits unchanged.
    with runtime.connect(), runtime.connect(), Session(runtime) as session:
        with pytest.raises(HTTPException) as raised:
            require_public_database(session, settings)
        assert raised.value.status_code == 503
        result = diagnostic(caplog)
        assert result["exception_type"] == "PoolTimeout"
        assert result["check"] == "database_identity"
    caplog.clear()
    with Session(runtime) as session:
        require_public_database(session, settings)
    assert not [r for r in caplog.records if r.name == logger.name]


def test_invariant_failure_names_checks_without_values(isolated_hosting, caplog):
    engine, _, _, settings = isolated_hosting
    setup(engine, settings.public_demo_database)
    with Session(engine) as session:
        session.execute(
            text("ALTER TABLE bookings DISABLE TRIGGER bookings_owner_immutable")
        )
        with pytest.raises(HTTPException) as raised:
            require_public_database(session, settings)
        assert raised.value.status_code == 503
        result = diagnostic(caplog)
        assert result["check"] == "invariants"
        assert result["failed_checks"] == ["immutable_triggers"]
        assert result["exception_type"] is None and result["sqlstate"] is None
        session.rollback()
