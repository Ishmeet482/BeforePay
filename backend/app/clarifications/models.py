from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClarificationSuggestion(Base):
    __tablename__ = "clarification_suggestions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    comparison_id: Mapped[UUID] = mapped_column(
        ForeignKey("booking_comparisons.id"), index=True
    )
    comparison_fingerprint: Mapped[str] = mapped_column(String(64))
    agreement_id: Mapped[UUID] = mapped_column(ForeignKey("agreement_versions.id"))
    agreement_fingerprint: Mapped[str] = mapped_column(String(64))
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchant_booking_versions.id")
    )
    proposal_fingerprint: Mapped[str] = mapped_column(String(64))
    confirmation_id: Mapped[UUID] = mapped_column(
        ForeignKey("agreement_confirmations.id")
    )
    category: Mapped[str] = mapped_column(String(32))
    fingerprint: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict] = mapped_column(JSONB)
    supporting_terms: Mapped[list] = mapped_column(JSONB)
    model_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MerchantReply(Base):
    __tablename__ = "clarification_replies"
    __table_args__ = (
        CheckConstraint("identity_provisional = true", name="ck_reply_provisional"),
        CheckConstraint("char_length(trim(merchant_label)) > 0", name="ck_reply_label"),
        CheckConstraint("char_length(trim(response)) > 0", name="ck_reply_response"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    suggestion_id: Mapped[UUID] = mapped_column(
        ForeignKey("clarification_suggestions.id"), index=True
    )
    suggestion_fingerprint: Mapped[str] = mapped_column(String(64))
    comparison_id: Mapped[UUID] = mapped_column(ForeignKey("booking_comparisons.id"))
    comparison_fingerprint: Mapped[str] = mapped_column(String(64))
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchant_booking_versions.id")
    )
    proposal_fingerprint: Mapped[str] = mapped_column(String(64))
    merchant_label: Mapped[str] = mapped_column(String(100))
    response: Mapped[str] = mapped_column(Text)
    identity_provisional: Mapped[bool] = mapped_column(default=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CorrectionReview(Base):
    __tablename__ = "clarification_correction_reviews"
    __table_args__ = (
        UniqueConstraint(
            "suggestion_id", "comparison_id", name="uq_correction_review_context"
        ),
        CheckConstraint(
            "identity_provisional = true", name="ck_correction_provisional"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    suggestion_id: Mapped[UUID] = mapped_column(
        ForeignKey("clarification_suggestions.id"), index=True
    )
    reply_id: Mapped[UUID] = mapped_column(ForeignKey("clarification_replies.id"))
    comparison_id: Mapped[UUID] = mapped_column(ForeignKey("booking_comparisons.id"))
    agreement_id: Mapped[UUID] = mapped_column(ForeignKey("agreement_versions.id"))
    confirmation_id: Mapped[UUID] = mapped_column(
        ForeignKey("agreement_confirmations.id")
    )
    original_proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchant_booking_versions.id")
    )
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchant_booking_versions.id")
    )
    context_fingerprint: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict] = mapped_column(JSONB)
    reviewer_label: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text)
    identity_provisional: Mapped[bool] = mapped_column(default=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
