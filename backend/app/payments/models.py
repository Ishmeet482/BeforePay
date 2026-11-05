from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CheckoutApproval(Base):
    __tablename__ = "checkout_approvals"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict] = mapped_column(JSONB)
    audit: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    approval_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_approvals.id"), unique=True
    )
    amount: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    create_key: Mapped[str] = mapped_column(String(36), unique=True)
    capture_key: Mapped[str] = mapped_column(String(36), unique=True)
    order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    capture_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_attempts.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32))
    code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SandboxReceipt(Base):
    __tablename__ = "sandbox_receipts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), unique=True)
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_attempts.id"), unique=True
    )
    approval_id: Mapped[UUID] = mapped_column(ForeignKey("checkout_approvals.id"))
    context: Mapped[dict] = mapped_column(JSONB)
    amount: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    order_id: Mapped[str] = mapped_column(String(64), unique=True)
    capture_id: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PayPalWebhookEvent(Base):
    """Only verified, successfully handled notifications; no raw payloads."""

    __tablename__ = "paypal_webhook_events"
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("payment_attempts.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
