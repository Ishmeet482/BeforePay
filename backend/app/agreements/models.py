from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class AgreementVersion(Base):
    __tablename__ = "agreement_versions"
    __table_args__ = (
        UniqueConstraint("booking_id", "version", name="uq_agreement_booking_version"),
        CheckConstraint("version >= 1"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("draft_versions.id"))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agreement_versions.id"))
    version: Mapped[int]
    fingerprint: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSONB)
    evidence_fingerprints: Mapped[dict] = mapped_column(JSONB)
    reviewed_source_ids: Mapped[list] = mapped_column(JSONB)
    audit: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgreementConfirmation(Base):
    __tablename__ = "agreement_confirmations"
    __table_args__ = (
        UniqueConstraint("agreement_id", name="uq_confirmation_agreement"),
        CheckConstraint("acknowledged = true"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    agreement_id: Mapped[UUID] = mapped_column(ForeignKey("agreement_versions.id"))
    reviewed_fingerprint: Mapped[str] = mapped_column(String(64))
    customer_label: Mapped[str] = mapped_column(String(100))
    acknowledged: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
