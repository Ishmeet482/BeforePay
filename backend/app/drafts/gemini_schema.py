"""Compact Gemini wire contract; original domain validators remain authoritative."""

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.drafts.schemas import Extraction
from app.drafts.service import NUMBER_WORDS
from app.drafts.validation import WireInvariantError, validate_at

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
    wire = validate_at("wire_schema", lambda: WireDraft.model_validate_json(raw))
    data = {field: [] for field in Extraction.model_fields}
    seen = set()
    unknown = set()
    offset_times = []
    for index, term in enumerate(wire.terms):
        category = term.category
        if category not in data:
            raise WireInvariantError(
                [(("terms", index, "category"), "unknown_category")]
            )
        seen.add(category)
        values = term.model_dump()
        if term.state == "unknown":
            if any(
                value
                for field, value in values.items()
                if field not in {"category", "state"}
            ):
                raise WireInvariantError(
                    [
                        (("terms", index, field), "unknown_row_contains_fact")
                        for field, value in values.items()
                        if field not in {"category", "state"} and value
                    ]
                )
            unknown.add(category)
            continue
        page = term.page_number
        if page and not re.fullmatch(r"[1-9][0-9]*", page):
            raise WireInvariantError(
                [(("terms", index, "page_number"), "positive_integer_string_required")]
            )
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
                raise WireInvariantError(
                    [(("terms", index, "quantity"), "positive_integer_string_required")]
                )
            claim.update(name=term.name, quantity=int(quantity) if quantity else None)
            used.update({"name", "quantity"})
        elif category in {"pickup", "return_time"}:
            local = term.value
            # Compatibility at the provider boundary only. An offset is redundant
            # only after the separately supplied zone resolves this same wall time
            # to exactly the same instant. Never derive a missing zone from it.
            offset_format = re.fullmatch(
                r"(?P<wall_time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
                r"(?::\d{2}(?:\.\d{1,6})?)?)"
                r"(?:Z|[+-](?:(?:0\d|1[0-3]):[0-5]\d|14:00))",
                local,
            )
            if term.timezone and offset_format:
                try:
                    aware = datetime.fromisoformat(local)
                except ValueError:
                    pass  # Let the unchanged domain validator reject invalid dates.
                else:
                    local = offset_format.group("wall_time")
                    offset_times.append((category, len(data[category]), index, aware))
            claim["value"] = {
                "local_datetime": local or None,
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
            raise WireInvariantError(
                [
                    (("terms", index, field), "unused_field_not_empty")
                    for field, value in values.items()
                    if field not in used and value
                ]
            )
        data[category].append(claim)
    if seen != set(data) or any(data[field] for field in unknown):
        raise WireInvariantError(
            [
                (
                    (field,),
                    "missing_category"
                    if field not in seen
                    else "unknown_with_known_claims",
                )
                for field in data
                if field not in seen or (field in unknown and data[field])
            ]
        )
    extraction = validate_at("domain_schema", lambda: Extraction.model_validate(data))
    if offset_times:
        # Reuse the approval/calculation resolver, including its DST gap/overlap
        # rejection. Import locally to keep provider/domain initialization separate.
        from app.agreements.service import explicit_instant

        for category, claim_index, wire_index, aware in offset_times:
            value = getattr(extraction, category)[claim_index].value
            try:
                instant = explicit_instant(value)
            except ValueError:
                raise WireInvariantError(
                    [(("terms", wire_index, "value"), "datetime_timezone_ambiguous")]
                ) from None
            if instant != aware.astimezone(UTC):
                raise WireInvariantError(
                    [
                        (
                            ("terms", wire_index, "value"),
                            "datetime_offset_timezone_mismatch",
                        )
                    ]
                )
    return extraction
