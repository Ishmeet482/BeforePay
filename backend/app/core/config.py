from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://contextkey:contextkey_local@127.0.0.1:5433/contextkey"
    )
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    paypal_environment: Literal["sandbox"] = "sandbox"
    paypal_sandbox_enabled: bool = False
    paypal_sandbox_client_id: str = ""
    paypal_sandbox_client_secret: SecretStr | None = None
    paypal_sandbox_merchant_id: str = ""
    paypal_sandbox_webhook_id: str = ""
    demo_session_ttl_seconds: int = Field(default=2_592_000, ge=60, le=2_592_000)
    demo_cookie_secure: bool = True
    public_demo_mode: bool = False
    vercel: bool = False
    public_demo_database: str = ""
    public_webhooks_enabled: bool = False
    public_sandbox_payments_enabled: bool = False
    demo_payment_attempts_global: int = Field(default=200, ge=0, le=200)
    demo_payment_attempts_per_session: int = Field(default=50, ge=0, le=50)
    db_pool_size: int = Field(default=2, ge=2, le=4)
    db_max_overflow: int = Field(default=0, ge=0, le=2)
    db_pool_timeout: int = Field(default=3, ge=1, le=5)
    demo_max_sessions: int = Field(default=1000, ge=0)
    demo_sessions_per_hour: int = Field(default=20, ge=0)
    demo_max_bookings: int = Field(default=1000, ge=0)
    demo_bookings_per_session: int = Field(default=50, ge=0)
    demo_max_sources: int = Field(default=4000, ge=0)
    demo_sources_per_session: int = Field(default=80, ge=0)
    demo_max_writes: int = Field(default=40_000, ge=0)
    demo_writes_per_session: int = Field(default=1000, ge=0)
    demo_source_bytes: int = Field(default=80_000_000, ge=0)
    demo_source_bytes_per_session: int = Field(default=4_000_000, ge=0)
    demo_upload_bytes: int = Field(default=640 * 1024 * 1024, ge=0)
    demo_upload_bytes_per_session: int = Field(default=60 * 1024 * 1024, ge=0)
    demo_pdf_max_bytes: int = Field(default=3 * 1024 * 1024, ge=1, le=3 * 1024 * 1024)
    demo_pdf_max_pages: int = Field(default=20, ge=1, le=100)
    demo_source_max_chars: int = Field(default=40_000, ge=1, le=100_000)
    demo_ai_calls_per_session: int = Field(default=60, ge=0)
    demo_ai_tokens_per_session: int = Field(default=4_000_000, ge=0)
    demo_ai_calls_per_day: int = Field(default=0, ge=0)
    demo_ai_calls_per_minute: int = Field(default=2, ge=0)
    demo_ai_tokens_per_day: int = Field(default=0, ge=0)
    demo_ai_tokens_per_minute: int = Field(default=0, ge=0)
    demo_ai_concurrent_global: int = Field(default=1, ge=0)
    demo_ai_concurrent_session: int = Field(default=1, ge=0)
    demo_ai_cooldown_seconds: int = Field(default=15, ge=0)
    demo_allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @field_validator("demo_allowed_origins")
    @classmethod
    def exact_origins(cls, values):
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
                or parsed.netloc != parsed.netloc.lower()
                or (
                    parsed.scheme == "http"
                    and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                )
            ):
                raise ValueError(
                    "Use exact HTTPS origins or explicit loopback HTTP origins"
                )
        return values

    @model_validator(mode="after")
    def insecure_cookie_is_local_only(self):
        if not self.demo_cookie_secure and (
            not self.demo_allowed_origins
            or any(
                urlsplit(origin).scheme != "http"
                or urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}
                for origin in self.demo_allowed_origins
            )
        ):
            raise ValueError(
                "Insecure demo cookies are only for loopback HTTP development"
            )
        return self

    @model_validator(mode="after")
    def public_deployment_boundary(self):
        if self.vercel and not self.public_demo_mode:
            raise ValueError("Vercel requires PUBLIC_DEMO_MODE=true")
        if not self.public_demo_mode:
            return self
        url = make_url(self.database_url.get_secret_value())
        if (
            not self.public_demo_database
            or url.database != self.public_demo_database
            or url.database in {"contextkey", "postgres", "template0", "template1"}
        ):
            raise ValueError(
                "Public mode requires an explicitly named dedicated demo database"
            )
        if (
            not self.demo_cookie_secure
            or not self.demo_allowed_origins
            or any(
                urlsplit(origin).scheme != "https"
                for origin in self.demo_allowed_origins
            )
        ):
            raise ValueError(
                "Public mode requires Secure cookies and exact HTTPS origins"
            )
        if url.host not in {"localhost", "127.0.0.1", "::1"} and url.query.get(
            "sslmode"
        ) not in {"require", "verify-full"}:
            raise ValueError("Remote public PostgreSQL requires TLS")
        caps = {
            "demo_max_sessions": 1000,
            "demo_sessions_per_hour": 100,
            "demo_max_bookings": 1000,
            "demo_max_sources": 4000,
            "demo_max_writes": 40_000,
            "demo_writes_per_session": 1000,
            "demo_sources_per_session": 80,
            "demo_bookings_per_session": 50,
            "demo_upload_bytes": 640 * 1024 * 1024,
            "demo_source_bytes": 80_000_000,
            "demo_ai_concurrent_global": 4,
            "demo_ai_concurrent_session": 1,
        }
        if any(getattr(self, key) > ceiling for key, ceiling in caps.items()):
            raise ValueError(
                "Public resource limits exceed the supported safety ceiling"
            )
        if self.public_sandbox_payments_enabled and not (
            self.paypal_environment == "sandbox"
            and self.paypal_sandbox_enabled
            and self.paypal_sandbox_client_id.strip()
            and self.paypal_sandbox_client_secret
            and self.paypal_sandbox_client_secret.get_secret_value().strip()
            and self.paypal_sandbox_merchant_id.strip()
        ):
            raise ValueError(
                "Public sandbox opt-in requires complete sandbox configuration"
            )
        if self.vercel and (
            self.public_webhooks_enabled
            or (
                not self.public_sandbox_payments_enabled
                and (
                    self.paypal_sandbox_enabled
                    or self.paypal_sandbox_client_secret
                    or self.paypal_sandbox_client_id
                )
            )
        ):
            raise ValueError(
                "Hosting requires payment secrets absent and webhooks disabled"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def require_sync_postgresql(cls, value: SecretStr) -> SecretStr:
        if make_url(value.get_secret_value()).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
