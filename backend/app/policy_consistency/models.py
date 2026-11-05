from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PolicyConsistencyCheck(Base):
    __tablename__ = "policy_consistency_checks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchant_booking_versions.id"), index=True
    )
    proposal_fingerprint: Mapped[str] = mapped_column(String(64))
    proposal_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(40))
    output: Mapped[dict] = mapped_column(JSONB)
    clauses: Mapped[list] = mapped_column(JSONB)
    model_metadata: Mapped[dict | None] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
