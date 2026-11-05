import uuid

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.core.database import get_session
from app.main import app


@pytest.fixture(autouse=True)
def forbid_live_gemini(monkeypatch):
    # No test may reach the real SDK constructor by accident, even if developer
    # credentials are configured. Adapter tests explicitly install offline fakes.
    def forbidden(*args, **kwargs):
        raise AssertionError("Live Gemini calls are forbidden in automated tests")

    monkeypatch.setattr("app.drafts.provider.genai.Client", forbidden)
    # Tests never load developer .env files or real API keys.
    safe = Settings(
        _env_file=None, gemini_api_key=None, demo_allowed_origins=["https://testserver"]
    )
    monkeypatch.setattr("app.demo_sessions.service.get_settings", lambda: safe)
    monkeypatch.setattr("app.demo_sessions.router.get_settings", lambda: safe)
    monkeypatch.setattr("app.core.config.get_settings", lambda: safe)
    monkeypatch.setattr("app.hosting.middleware.get_settings", lambda: safe)
    monkeypatch.setattr("app.admission.service.get_settings", lambda: safe)
    monkeypatch.setattr("app.evidence.router.get_settings", lambda: safe)
    monkeypatch.setattr("app.core.body_limit.get_settings", lambda: safe)
    monkeypatch.setattr("app.drafts.provider.get_settings", lambda: safe)
    monkeypatch.setattr("app.core.database.get_settings", lambda: safe)
    monkeypatch.setattr("app.payments.provider.get_settings", lambda: safe)
    monkeypatch.setattr("app.payments.router.get_settings", lambda: safe)
    monkeypatch.setattr("app.payments.service.get_settings", lambda: safe)
    monkeypatch.setattr("app.payments.provider.SandboxPayPal._client", forbidden)


@pytest.fixture(scope="session")
def postgres_engine():
    """Create and migrate our own database; never reset the configured database."""
    from sqlalchemy.engine import make_url

    url = make_url(
        Settings(_env_file=None, gemini_api_key=None).database_url.get_secret_value()
    )
    name = f"contextkey_test_{uuid.uuid4().hex}"
    admin = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    created = False
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        engine = create_engine(url.set(database=name))
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(
                    "app.core.config.get_settings",
                    lambda: Settings(_env_file=None, gemini_api_key=None),
                )
                command.upgrade(config, "head")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            # Only the randomly named database created by this fixture is removed.
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


@pytest.fixture
def api(postgres_engine):
    def isolated_session():
        with Session(postgres_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session
    try:
        with TestClient(
            app, base_url="https://testserver", headers={"Origin": "https://testserver"}
        ) as client:
            issued = client.post("/api/demo-sessions")
            assert issued.status_code == 201
            client.headers["X-BeforePay-CSRF"] = issued.json()["csrf_token"]
            yield client
    finally:
        app.dependency_overrides.clear()
