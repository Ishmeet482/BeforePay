"""Compact Gemini wire contract; original domain validators remain authoritative."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.drafts.schemas import Extraction
from app.drafts.service import NUMBER_WORDS

FIELDS = (
    "category",
    "state",
    "name",
    "value",
    "quantity",
    "currency",
    "kind",
    "timezone",
    "source_id",
    "quotation",
    "page_number",
)


def extraction_json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "terms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {name: {"type": "string"} for name in FIELDS},
                    "required": list(FIELDS),
                },
            }
        },
        "required": ["terms"],
    }


class WireTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    state: Literal["known", "unknown", "conflict"]
    name: str
    value: str
    quantity: str
    currency: str
    kind: str
    timezone: str
    source_id: str
    quotation: str
    page_number: str


class WireDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms: list[WireTerm] = Field(min_length=8, max_length=808)


def decode_extraction(raw: str) -> Extraction:
    wire = WireDraft.model_validate_json(raw)
    data = {field: [] for field in Extraction.model_fields}
    seen = set()
    unknown = set()
    for term in wire.terms:
        category = term.category
        if category not in data:
            raise ValueError("Unknown category")
        seen.add(category)
        values = term.model_dump()
        if term.state == "unknown":
            if any(
                value
                for field, value in values.items()
                if field not in {"category", "state"}
            ):
                raise ValueError("Unknown terms cannot contain invented facts")
            unknown.add(category)
            continue
        page = term.page_number
        if page and not re.fullmatch(r"[1-9][0-9]*", page):
            raise ValueError("Page must be a positive integer string")
        claim = {
            "ambiguous": term.state == "conflict",
            "citations": [
                {
                    "source_id": term.source_id,
                    "quotation": term.quotation,
                    "page_number": int(page) if page else None,
                }
            ],
        }
        used = {"category", "state", "source_id", "quotation", "page_number"}
        if category in {"equipment", "included_items"}:
            # The domain's evidence validator already supports these literal
            # number words. Normalize their representation, never infer a count.
            quantity = term.quantity
            if quantity.casefold() in NUMBER_WORDS[1:]:
                quantity = str(NUMBER_WORDS.index(quantity.casefold()))
            if quantity and not re.fullmatch(r"[1-9][0-9]*", quantity):
                raise ValueError("Quantity must be a positive integer string")
            claim.update(name=term.name, quantity=int(quantity) if quantity else None)
            used.update({"name", "quantity"})
        elif category in {"pickup", "return_time"}:
            claim["value"] = {
                "local_datetime": term.value or None,
                "timezone": term.timezone or None,
            }
            used.update({"value", "timezone"})
        elif category == "amounts":
            claim.update(
                kind=term.kind,
                label=term.name,
                amount=term.value,
                currency=term.currency or None,
            )
            used.update({"kind", "name", "value", "currency"})
        else:
            claim["value"] = term.value
            used.add("value")
        if any(value for field, value in values.items() if field not in used):
            raise ValueError("Unused fields must stay empty")
        data[category].append(claim)
    if seen != set(data) or any(data[field] for field in unknown):
        raise ValueError(
            "All categories required; unknown cannot conceal known/conflicting claims"
        )
    return Extraction.model_validate(data)
