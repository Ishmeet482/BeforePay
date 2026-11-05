from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CancellationRuleVersion(Base):
    __tablename__ = "cancellation_rule_versions"
    __table_args__ = (
        UniqueConstraint(
            "booking_id",
            "target_kind",
            "target_id",
            "version",
            name="uq_cancellation_rule_version",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    target_kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[UUID]
    target_fingerprint: Mapped[str] = mapped_column(String(64))
    source_version: Mapped[int]
    version: Mapped[int]
    fingerprint: Mapped[str] = mapped_column(String(64))
    rules: Mapped[dict] = mapped_column(JSONB)
    origin: Mapped[str] = mapped_column(String(20))
    audit: Mapped[dict] = mapped_column(JSONB)
    model_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CancellationRuleApproval(Base):
    __tablename__ = "cancellation_rule_approvals"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("cancellation_rule_versions.id"), unique=True
    )
    reviewed_fingerprint: Mapped[str] = mapped_column(String(64))
    audit: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
