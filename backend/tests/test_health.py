from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.database import get_session
from app.main import app


def test_liveness_does_not_require_database():
    def unavailable_session():
        raise AssertionError("Liveness must not request a database session")

    app.dependency_overrides[get_session] = unavailable_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "contextkey-api"}
    finally:
        app.dependency_overrides.clear()


def test_readiness_success_contract():
    # This checks the API contract, not a real PostgreSQL connection.
    session = Mock()
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.get("/api/health/ready")
        assert response.status_code == 200
        assert response.json()["database"] == "ok"
        assert str(session.execute.call_args.args[0]) == "SELECT 1"
    finally:
        app.dependency_overrides.clear()


def test_readiness_failure_does_not_leak_details():
    session = Mock()
    session.execute.side_effect = OperationalError(
        "SELECT 1", {}, Exception("secret database connection details")
    )
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.get("/api/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
    finally:
        app.dependency_overrides.clear()
