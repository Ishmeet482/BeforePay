from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.agreements.schemas import CustomerRequest, Fingerprint
from app.drafts.schemas import StrictModel


class CheckoutApprove(CustomerRequest):
    expected_context_fingerprint: Fingerprint
    acknowledged: bool = Field(strict=True)

    @field_validator("acknowledged")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit checkout approval is required")
        return value


class OrderCreate(StrictModel):
    approval_id: UUID


class AttemptRead(StrictModel):
    model_config = {"from_attributes": True, "extra": "forbid"}
    id: UUID
    booking_id: UUID
    approval_id: UUID
    amount: str
    currency: str
    order_id: str | None
    capture_id: str | None
    status: str
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class ReceiptRead(StrictModel):
    model_config = {"from_attributes": True, "extra": "forbid"}
    id: UUID
    booking_id: UUID
    attempt_id: UUID
    approval_id: UUID
    context: dict
    amount: str
    currency: str
    order_id: str
    capture_id: str
    created_at: datetime
