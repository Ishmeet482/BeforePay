from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.drafts.schemas import (
    Citation,
    CurrencyClaim,
    EquipmentClaim,
    MoneyClaim,
    StrictModel,
    TextClaim,
    TimeClaim,
)

Category = Literal[
    "equipment",
    "pickup",
    "return_time",
    "currency",
    "amounts",
    "deposit_conditions",
    "cancellation_conditions",
    "included_items",
]
Reason = Annotated[str, Field(min_length=1, max_length=2000)]
CustomerLabel = Annotated[str, Field(min_length=1, max_length=100)]
Fingerprint = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class CustomerEquipment(EquipmentClaim):
    citations: list[Citation] = Field(default_factory=list, max_length=0)

    @field_validator("name")
    @classmethod
    def no_nul(cls, value):
        if "\x00" in value:
            raise ValueError("NUL characters are not allowed")
        return value


class CustomerTime(TimeClaim):
    citations: list[Citation] = Field(default_factory=list, max_length=0)


class CustomerCurrency(CurrencyClaim):
    citations: list[Citation] = Field(default_factory=list, max_length=0)


class CustomerMoney(MoneyClaim):
    citations: list[Citation] = Field(default_factory=list, max_length=0)

    @field_validator("label")
    @classmethod
    def meaningful_label(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("A nonblank money label is required")
        return value


class CustomerPolicy(TextClaim):
    citations: list[Citation] = Field(default_factory=list, max_length=0)

    @field_validator("value")
    @classmethod
    def meaningful_policy(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("An explicit nonblank policy is required")
        return value


class SourceEntry[T](StrictModel):
    origin: Literal["source_supported"]
    claim: T


class CustomerEntry[T](StrictModel):
    origin: Literal["customer_entered"]
    claim: T
    reason: Reason


EquipmentEntry = Annotated[
    SourceEntry[EquipmentClaim] | CustomerEntry[CustomerEquipment],
    Field(discriminator="origin"),
]
TimeEntry = Annotated[
    SourceEntry[TimeClaim] | CustomerEntry[CustomerTime], Field(discriminator="origin")
]
CurrencyEntry = Annotated[
    SourceEntry[CurrencyClaim] | CustomerEntry[CustomerCurrency],
    Field(discriminator="origin"),
]
MoneyEntry = Annotated[
    SourceEntry[MoneyClaim] | CustomerEntry[CustomerMoney],
    Field(discriminator="origin"),
]
PolicyEntry = Annotated[
    SourceEntry[TextClaim] | CustomerEntry[CustomerPolicy],
    Field(discriminator="origin"),
]


class ReviewExtraction(StrictModel):
    equipment: list[EquipmentEntry] = Field(max_length=100)
    pickup: list[TimeEntry] = Field(max_length=100)
    return_time: list[TimeEntry] = Field(max_length=100)
    currency: list[CurrencyEntry] = Field(max_length=100)
    amounts: list[MoneyEntry] = Field(max_length=100)
    deposit_conditions: list[PolicyEntry] = Field(max_length=100)
    cancellation_conditions: list[PolicyEntry] = Field(max_length=100)
    included_items: list[EquipmentEntry] = Field(max_length=100)


class ReviewContent(StrictModel):
    extraction: ReviewExtraction
    explicit_none_categories: list[Literal["included_items"]] = Field(
        default_factory=list
    )


class EquipmentChange(StrictModel):
    category: Literal["equipment", "included_items"]
    reason: Reason
    items: list[CustomerEquipment] = Field(max_length=100)
    explicit_none: bool = False

    @model_validator(mode="after")
    def explicit_absence(self):
        if self.explicit_none and (self.category != "included_items" or self.items):
            raise ValueError("Explicit absence applies only to empty included_items")
        return self


class TimeChange(StrictModel):
    category: Literal["pickup", "return_time"]
    reason: Reason
    items: list[CustomerTime] = Field(max_length=100)


class CurrencyChange(StrictModel):
    category: Literal["currency"]
    reason: Reason
    items: list[CustomerCurrency] = Field(max_length=100)


class MoneyChange(StrictModel):
    category: Literal["amounts"]
    reason: Reason
    items: list[CustomerMoney] = Field(max_length=100)


class PolicyChange(StrictModel):
    category: Literal["deposit_conditions", "cancellation_conditions"]
    reason: Reason
    items: list[CustomerPolicy] = Field(max_length=100)


Change = Annotated[
    EquipmentChange | TimeChange | CurrencyChange | MoneyChange | PolicyChange,
    Field(discriminator="category"),
]


class CustomerRequest(StrictModel):
    customer_label: CustomerLabel

    @field_validator("customer_label")
    @classmethod
    def provisional_label(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("A nonblank provisional customer label is required")
        return value


class FromDraft(CustomerRequest):
    draft_id: UUID


class RevisionCreate(CustomerRequest):
    expected_fingerprint: Fingerprint
    review_reason: Reason
    reviewed_source_ids: list[UUID] = Field(max_length=1000)
    changes: list[Change] = Field(max_length=8)

    @model_validator(mode="after")
    def explicit_reasons(self):
        if not self.review_reason.strip() or "\x00" in self.review_reason:
            raise ValueError("Review reason must contain text and no NUL")
        if len(set(self.reviewed_source_ids)) != len(self.reviewed_source_ids):
            raise ValueError("Reviewed source IDs must be unique")
        if len({item.category for item in self.changes}) != len(self.changes):
            raise ValueError("Each category may be corrected only once")
        if any(
            not change.reason.strip() or "\x00" in change.reason
            for change in self.changes
        ):
            raise ValueError("Every correction needs a nonblank reason")
        return self


class ConfirmationCreate(CustomerRequest):
    expected_fingerprint: Fingerprint
    acknowledged: bool = Field(strict=True)

    @field_validator("acknowledged")
    @classmethod
    def explicit_acknowledgement(cls, value):
        if value is not True:
            raise ValueError("Explicit acknowledgement is required")
        return value


class AgreementRead(StrictModel):
    model_config = {"from_attributes": True, "extra": "forbid"}
    id: UUID
    booking_id: UUID
    draft_id: UUID
    parent_id: UUID | None
    version: int
    fingerprint: Fingerprint
    content: ReviewContent
    evidence_fingerprints: dict[str, str]
    reviewed_source_ids: list[UUID]
    audit: dict
    created_at: datetime


class ConfirmationRead(StrictModel):
    model_config = {"from_attributes": True, "extra": "forbid"}
    id: UUID
    booking_id: UUID
    agreement_id: UUID
    reviewed_fingerprint: Fingerprint
    customer_label: str
    acknowledged: Literal[True]
    created_at: datetime


class ReviewState(StrictModel):
    agreement_id: UUID | None
    fingerprint: str | None
    source_ids: list[UUID]
    latest_draft_id: UUID | None
    blockers: list[str]
    confirmation: ConfirmationRead | None
    confirmation_current: bool
    requires_review: bool
    identity_provisional: Literal[True] = True
