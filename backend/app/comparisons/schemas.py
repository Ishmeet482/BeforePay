from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.agreements.schemas import (
    CustomerCurrency,
    CustomerEquipment,
    CustomerMoney,
    CustomerPolicy,
    CustomerTime,
    Fingerprint,
    Reason,
)
from app.drafts.schemas import StrictModel


class ProposalContent(StrictModel):
    equipment: list[CustomerEquipment] = Field(default_factory=list, max_length=100)
    included_items: list[CustomerEquipment] = Field(
        default_factory=list, max_length=100
    )
    included_items_none: bool = Field(default=False, strict=True)
    pickup: list[CustomerTime] = Field(default_factory=list, max_length=100)
    return_time: list[CustomerTime] = Field(default_factory=list, max_length=100)
    currency: list[CustomerCurrency] = Field(default_factory=list, max_length=100)
    amounts: list[CustomerMoney] = Field(default_factory=list, max_length=100)
    deposit_conditions: list[CustomerPolicy] = Field(
        default_factory=list, max_length=100
    )
    cancellation_conditions: list[CustomerPolicy] = Field(
        default_factory=list, max_length=100
    )


class ProposalCreate(StrictModel):
    expected_latest_id: UUID | None
    merchant_label: str = Field(min_length=1, max_length=100)
    reason: Reason
    content: ProposalContent

    @field_validator("merchant_label", "reason")
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("An explicit label/reason without NUL is required")
        return value


class ProposalRead(StrictModel):
    model_config = {"from_attributes": True, "extra": "forbid"}
    id: UUID
    booking_id: UUID
    version: int
    fingerprint: Fingerprint
    content: ProposalContent
    audit: dict
    created_at: datetime


class ComparisonCreate(StrictModel):
    agreement_id: UUID
    agreement_fingerprint: Fingerprint
    proposal_id: UUID
    proposal_fingerprint: Fingerprint


Status = Literal["matches", "differs", "needs_clarification"]
PolicyCategory = Literal["deposit_conditions", "cancellation_conditions"]


class PolicyJudgment(StrictModel):
    category: PolicyCategory
    status: Status
    agreement_quote: str = Field(min_length=1, max_length=400000)
    proposal_quote: str = Field(min_length=1, max_length=400000)


class PolicyOutput(StrictModel):
    results: list[PolicyJudgment] = Field(min_length=1, max_length=2)


class ComparisonRead(StrictModel):
    id: UUID
    booking_id: UUID
    agreement_id: UUID
    agreement_fingerprint: Fingerprint
    confirmation_id: UUID
    proposal_id: UUID
    proposal_fingerprint: Fingerprint
    fingerprint: Fingerprint
    results: list[dict]
    model_metadata: dict | None
    created_at: datetime
    stale: bool
    stale_reasons: list[str]
