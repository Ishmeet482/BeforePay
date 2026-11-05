from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.agreements.schemas import Fingerprint
from app.drafts.schemas import StrictModel


class ReviewBindings(StrictModel):
    suggestion_id: UUID
    suggestion_fingerprint: Fingerprint
    original_comparison_id: UUID
    original_comparison_fingerprint: Fingerprint
    agreement_id: UUID
    agreement_fingerprint: Fingerprint
    confirmation_id: UUID
    original_proposal_id: UUID
    original_proposal_fingerprint: Fingerprint
    proposal_id: UUID
    proposal_fingerprint: Fingerprint
    comparison_id: UUID
    comparison_fingerprint: Fingerprint
    reply_id: UUID
    reply_fingerprint: Fingerprint


class CorrectionCreate(StrictModel):
    bindings: ReviewBindings
    context_fingerprint: Fingerprint
    reviewer_label: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=5000)

    @field_validator("reviewer_label", "note")
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError(
                "A nonblank reviewer label and note without NUL are required"
            )
        return value


class CorrectionRead(StrictModel):
    id: UUID
    booking_id: UUID
    suggestion_id: UUID
    context_fingerprint: Fingerprint
    context: dict
    reviewer_label: str
    note: str
    identity_provisional: Literal[True]
    fingerprint: Fingerprint
    created_at: datetime
    stale: bool
    stale_reasons: list[str]
