from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.agreements.schemas import Fingerprint
from app.drafts.schemas import StrictModel

Category = Literal[
    "equipment",
    "included_items",
    "pickup",
    "return_time",
    "currency",
    "amounts",
    "deposit_conditions",
    "cancellation_conditions",
]


class SuggestCreate(StrictModel):
    comparison_fingerprint: Fingerprint
    category: Category


class TermReference(StrictModel):
    term_id: str = Field(min_length=1, max_length=40)
    quotation: str = Field(min_length=1, max_length=40000)


class SuggestionOutput(StrictModel):
    status: Literal["suggested", "needs_more_information"]
    question: str | None = Field(max_length=1000)
    explanation: str = Field(min_length=1, max_length=2000)
    references: list[TermReference] = Field(max_length=20)

    @field_validator("question", "explanation")
    @classmethod
    def meaningful(cls, value):
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("Nonblank text without NUL required")
        return value

    @model_validator(mode="after")
    def advisory_shape(self):
        if self.status == "suggested" and (
            not self.question or len(self.references) < 2
        ):
            raise ValueError("A supported question and references are required")
        if self.status == "suggested" and not self.question.rstrip().endswith("?"):
            raise ValueError("Return a question, not an instruction or assertion")
        if self.status == "needs_more_information" and self.question is not None:
            raise ValueError("Insufficient evidence cannot yield a question")
        return self


class SuggestionRead(StrictModel):
    id: UUID
    booking_id: UUID
    comparison_id: UUID
    comparison_fingerprint: Fingerprint
    agreement_id: UUID
    agreement_fingerprint: Fingerprint
    proposal_id: UUID
    proposal_fingerprint: Fingerprint
    confirmation_id: UUID
    category: Category
    fingerprint: Fingerprint
    output: SuggestionOutput
    supporting_terms: list[dict]
    model_metadata: dict | None
    created_at: datetime
    stale: bool
    stale_reasons: list[str]


class ReplyCreate(StrictModel):
    suggestion_fingerprint: Fingerprint
    comparison_fingerprint: Fingerprint
    proposal_id: UUID
    proposal_fingerprint: Fingerprint
    merchant_label: str = Field(min_length=1, max_length=100)
    response: str = Field(min_length=1, max_length=5000)

    @field_validator("merchant_label", "response")
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("A nonblank label and reply without NUL are required")
        return value


class ReplyRead(StrictModel):
    id: UUID
    booking_id: UUID
    suggestion_id: UUID
    suggestion_fingerprint: Fingerprint
    comparison_id: UUID
    comparison_fingerprint: Fingerprint
    proposal_id: UUID
    proposal_fingerprint: Fingerprint
    merchant_label: str
    response: str
    identity_provisional: Literal[True]
    fingerprint: Fingerprint
    created_at: datetime
    stale: bool
    stale_reasons: list[str]
