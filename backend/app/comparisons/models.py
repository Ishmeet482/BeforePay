from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProposalVersion(Base):
    __tablename__ = "merchant_booking_versions"
    __table_args__ = (
        UniqueConstraint("booking_id", "version", name="uq_merchant_booking_version"),
        CheckConstraint("version >= 1"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    version: Mapped[int]
    fingerprint: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSONB)
    audit: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BookingComparison(Base):
    __tablename__ = "booking_comparisons"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    agreement_id: Mapped[UUID] = mapped_column(ForeignKey("agreement_versions.id"))
    agreement_fingerprint: Mapped[str] = mapped_column(String(64))
    confirmation_id: Mapped[UUID] = mapped_column(
        ForeignKey("agreement_confirmations.id")
    )
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchant_booking_versions.id")
    )
    proposal_fingerprint: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    results: Mapped[list] = mapped_column(JSONB)
    model_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
