from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.agreements.schemas import CustomerRequest, Fingerprint, Reason
from app.drafts.schemas import Money, StrictModel, TimeValue

TargetKind = Literal["agreement", "proposal"]


class Target(StrictModel):
    kind: TargetKind
    id: UUID
    fingerprint: Fingerprint


class Refund(StrictModel):
    mode: Literal["amount", "percent"]
    value: Money


class Band(StrictModel):
    rental_refund: Refund = Field(
        description="Refund of rental fee only; percent uses rental fee as its base."
    )
    deposit_refund: Refund = Field(
        description="Refund of deposit only; percent uses deposit as its base."
    )
    # Empty support preserves unknowns in an unapproved draft; service blocks
    # confirmation and calculation until a real exact source clause is supplied.
    clause: str = Field(max_length=4000)


class Rules(StrictModel):
    cutoff_hours: Money
    early_includes_boundary: bool = Field(strict=True)
    early: Band
    late: Band
    deposit_clause: str = Field(max_length=4000)
    needs_clarification: bool = Field(strict=True)
    clarification_note: str = Field(max_length=2000)


class RuleCreate(CustomerRequest):
    target: Target
    expected_latest_rule_id: UUID | None
    reason: Reason
    rules: Rules

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Explicit review reason required")
        return value


class RulePropose(CustomerRequest):
    target: Target
    expected_latest_rule_id: UUID | None


class RuleConfirm(CustomerRequest):
    expected_fingerprint: Fingerprint
    acknowledged: bool = Field(strict=True)
    complete_pre_pickup_policy: bool = Field(strict=True)
    no_unresolved_contradictions: bool = Field(strict=True)
    review_note: Reason

    @field_validator(
        "acknowledged", "complete_pre_pickup_policy", "no_unresolved_contradictions"
    )
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("Explicit human review and resolution required")
        return value

    @field_validator("review_note")
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("A nonblank review note is required")
        return value


class RuleRead(StrictModel):
    id: UUID
    booking_id: UUID
    target: Target
    source_version: int
    version: int
    fingerprint: Fingerprint
    rules: Rules
    origin: Literal["human", "gemini"]
    audit: dict
    model_metadata: dict | None
    created_at: datetime
    blockers: list[str]
    approved_current: bool
    approval: dict | None


class PreviewCreate(StrictModel):
    rule_ids: Annotated[list[UUID], Field(min_length=1, max_length=2)]
    cancellation: TimeValue


class PreviewRead(StrictModel):
    status: Literal["ready", "needs_clarification"]
    blockers: list[str]
    cancellation_at: str | None
    previews: list[dict]
