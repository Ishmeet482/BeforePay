from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.evidence.limits import MAX_TEXT_LENGTH

SourceType = Literal["quotation", "message"]


class TextSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: SourceType
    original_text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)

    @field_validator("original_text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Evidence must contain text and no NUL characters")
        return value


class PageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    page_number: int
    original_text: str


class SourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    booking_id: UUID
    source_type: SourceType
    medium: Literal["pasted_text", "pdf"]
    filename: str | None
    created_at: datetime


class SourceRead(SourceSummary):
    original_text: str
    pages: list[PageRead]
