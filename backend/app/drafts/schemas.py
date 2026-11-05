import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Text = Annotated[str, Field(min_length=1, max_length=4000)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


def decimal_input(value):
    if not isinstance(value, (str, Decimal)):
        raise ValueError(
            "Money must be a decimal string, never a floating-point number"
        )
    return value


Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=16, decimal_places=4, allow_inf_nan=False),
    BeforeValidator(decimal_input),
    WithJsonSchema({"type": "string", "pattern": r"^\d{1,12}(\.\d{1,4})?$"}),
]


class Citation(StrictModel):
    source_id: UUID
    quotation: Text
    page_number: Annotated[int, Field(ge=1, le=100)] | None

    @field_validator("quotation")
    @classmethod
    def nonblank_quote(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Supporting quotation must not be blank")
        return value


class Claim(StrictModel):
    citations: Annotated[list[Citation], Field(min_length=1, max_length=20)]
    ambiguous: bool


class EquipmentClaim(Claim):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    quantity: Annotated[int, Field(strict=True, ge=1, le=100000)] | None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Equipment/item name must not be blank")
        return value


class TimeValue(StrictModel):
    # Missing date/year/time or timezone stays null; do not resolve relative dates.
    local_datetime: str | None
    timezone: str | None

    @field_validator("local_datetime")
    @classmethod
    def local_iso_datetime(cls, value: str | None) -> str | None:
        if value is not None:
            if "T" not in value or len(value) > 40:
                raise ValueError(
                    "Use ISO local date/time, without an inferred timezone"
                )
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                raise ValueError("Use separate explicit timezone field")
        return value

    @field_validator("timezone")
    @classmethod
    def explicit_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if re.fullmatch(r"[+-](?:0\d|1[0-3]):[0-5]\d|[+-]14:00", value):
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError, ValueError:
            raise ValueError("Use an explicit IANA timezone or UTC offset") from None
        # Abbreviations such as IST/CST are ambiguous, even if a system resolves one.
        if value != "UTC" and "/" not in value:
            raise ValueError("Ambiguous timezone abbreviation; leave timezone null")
        return value


class TimeClaim(Claim):
    value: TimeValue


class CurrencyClaim(Claim):
    value: Currency


class MoneyClaim(Claim):
    # total_payable is an inclusive stated total, not another charge to add.
    kind: Literal[
        "rental_total", "total_payable", "deposit", "tax", "delivery", "other"
    ]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    amount: Money
    currency: Currency | None


class TextClaim(Claim):
    value: Text


class Extraction(StrictModel):
    """Provider schema: all categories required; absent terms use empty lists."""

    equipment: Annotated[list[EquipmentClaim], Field(max_length=100)]
    pickup: Annotated[list[TimeClaim], Field(max_length=100)]
    return_time: Annotated[list[TimeClaim], Field(max_length=100)]
    currency: Annotated[list[CurrencyClaim], Field(max_length=100)]
    amounts: Annotated[list[MoneyClaim], Field(max_length=100)]
    deposit_conditions: Annotated[list[TextClaim], Field(max_length=100)]
    cancellation_conditions: Annotated[list[TextClaim], Field(max_length=100)]
    included_items: Annotated[list[EquipmentClaim], Field(max_length=100)]


TermStatus = Literal["unknown", "extracted", "needs_clarification"]


class TermStatuses(StrictModel):
    equipment: TermStatus
    pickup: TermStatus
    return_time: TermStatus
    currency: TermStatus
    amounts: TermStatus
    deposit_conditions: TermStatus
    cancellation_conditions: TermStatus
    included_items: TermStatus


class DraftContent(StrictModel):
    extraction: Extraction
    term_statuses: TermStatuses
    needs_clarification: bool


class ModelMetadata(StrictModel):
    # Legacy OpenAI metadata remains readable; new extraction uses only Gemini.
    provider: Literal["openai", "gemini"]
    requested_model: str
    response_model: str
    response_id: str
    sdk_version: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None


class DraftCreate(StrictModel):
    source_ids: Annotated[list[UUID], Field(min_length=1, max_length=20)]

    @field_validator("source_ids")
    @classmethod
    def unique_sources(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Source IDs must be unique")
        return value


class DraftRead(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    booking_id: UUID
    version: int
    status: Literal["draft"]
    input_source_ids: list[UUID]
    source_fingerprints: dict[str, str]
    content: DraftContent
    model_metadata: ModelMetadata
    created_at: datetime
