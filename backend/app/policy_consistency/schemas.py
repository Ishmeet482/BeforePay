from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.agreements.schemas import Fingerprint
from app.drafts.schemas import StrictModel

Status = Literal[
    "potential_contradiction", "needs_clarification", "no_contradiction_found"
]


class Reference(StrictModel):
    clause_id: str = Field(min_length=1, max_length=60)
    quotation: str = Field(min_length=1, max_length=40000)


class Finding(StrictModel):
    status: Status
    explanation: str = Field(min_length=1, max_length=2000)
    references: list[Reference] = Field(max_length=100)

    @field_validator("explanation")
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Nonblank explanation without NUL required")
        return value


class Output(StrictModel):
    findings: list[Finding] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def consistent(self):
        if (
            any(f.status == "no_contradiction_found" for f in self.findings)
            and len(self.findings) != 1
        ):
            raise ValueError(
                "A clean finding cannot coexist with uncertainty or conflict"
            )
        return self


class CheckCreate(StrictModel):
    proposal_id: UUID
    proposal_fingerprint: Fingerprint


class CheckRead(StrictModel):
    id: UUID
    booking_id: UUID
    proposal_id: UUID
    proposal_fingerprint: Fingerprint
    proposal_version: int
    status: Status
    output: Output
    clauses: list[dict]
    model_metadata: dict | None
    fingerprint: Fingerprint
    created_at: datetime
    stale: bool
    stale_reasons: list[str]
