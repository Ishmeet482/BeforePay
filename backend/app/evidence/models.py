from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EvidenceSource(Base):
    __tablename__ = "evidence_sources"
    __table_args__ = (
        CheckConstraint("source_type IN ('quotation', 'message')"),
        CheckConstraint("medium IN ('pasted_text', 'pdf')"),
        CheckConstraint("char_length(original_text) BETWEEN 1 AND 100000"),
        CheckConstraint(
            "(medium = 'pdf' AND filename IS NOT NULL) OR "
            "(medium = 'pasted_text' AND filename IS NULL)"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    medium: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str | None] = mapped_column(String(255))
    original_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    pages: Mapped[list[EvidencePage]] = relationship(
        order_by="EvidencePage.page_number", cascade="all, delete-orphan"
    )


class EvidencePage(Base):
    __tablename__ = "evidence_pages"
    __table_args__ = (CheckConstraint("page_number BETWEEN 1 AND 100"),)

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_sources.id"), primary_key=True
    )
    page_number: Mapped[int] = mapped_column(primary_key=True)
    original_text: Mapped[str] = mapped_column(Text)
