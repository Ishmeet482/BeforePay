import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError

from app.drafts.schemas import DraftContent, Extraction, TermStatuses
from app.evidence.models import EvidenceSource

NUMBER_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
).split()


def policy_conflicts(claims) -> bool:
    """Retain explicit conflicts and detect direct opposites with equal scope.

    Different clauses alone are not conflicting. This lexical check does not
    establish semantic equivalence or silently resolve an ambiguous claim.
    """
    polarities = defaultdict(set)
    for claim in claims:
        if claim.ambiguous:
            return True
        text = " ".join(claim.value.casefold().split()).rstrip(".")
        negative = bool(re.search(r"\b(?:non[- ]?refundable|no refund)\b", text))
        canonical = re.sub(r"\bnon[- ]?refundable\b", "refundable", text)
        canonical = re.sub(r"\b(?:no refund|full refund)\b", "refund", canonical)
        polarities[canonical].add(negative)
    return any(len(values) > 1 for values in polarities.values())


def validate_literal_support(category, claim):
    """Conservative lexical checks; not a claim of semantic entailment/completeness."""
    quotations = [citation.quotation for citation in claim.citations]
    text = "\n".join(quotations)
    valid = True
    if category in {"equipment", "included_items"}:
        valid = any(claim.name.casefold() in quote.casefold() for quote in quotations)
        if claim.quantity is not None:
            terms = [str(claim.quantity)]
            if claim.quantity < len(NUMBER_WORDS):
                terms.append(NUMBER_WORDS[claim.quantity])
            valid &= any(
                re.search(rf"(?<!\w){term}(?!\w)", text, re.I) for term in terms
            )
    elif category in {"pickup", "return_time"}:
        zone = claim.value.timezone
        valid = zone is None or any(zone in quote for quote in quotations)
    elif category == "currency":
        valid = bool(re.search(rf"\b{claim.value}\b", text))
    elif category == "amounts":
        numbers = re.findall(r"(?<!\w)[+-]?\d[\d,]*(?:\.\d+)?(?!\w)", text)
        valid = any(
            Decimal(number.replace(",", "")) == claim.amount for number in numbers
        )
        if claim.currency is not None:
            valid &= bool(re.search(rf"\b{claim.currency}\b", text))
    else:
        valid = any(claim.value in quote for quote in quotations)
    if not valid:
        raise HTTPException(
            502,
            {
                "code": "ai_unsupported_value",
                "message": "Value is not explicit in its supporting quotations.",
            },
        )


def source_snapshot(source: EvidenceSource) -> dict:
    return {
        "source_id": str(source.id),
        "source_type": source.source_type,
        "medium": source.medium,
        "filename": source.filename,
        "text": source.original_text if source.medium == "pasted_text" else None,
        "pages": [
            {"page_number": page.page_number, "text": page.original_text}
            for page in source.pages
        ],
    }


def fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def validate_and_classify(extraction: Extraction, sources: list[dict]) -> DraftContent:
    try:
        extraction = Extraction.model_validate(extraction.model_dump())
    except ValidationError:
        raise HTTPException(
            502, {"code": "ai_invalid_output", "message": "Invalid extraction schema."}
        ) from None
    by_id = {item["source_id"]: item for item in sources}
    statuses = {}
    for category in Extraction.model_fields:
        claims = getattr(extraction, category)
        groups = defaultdict(set)
        unclear = False
        for claim in claims:
            for citation in claim.citations:
                source = by_id.get(str(citation.source_id))
                valid = source is not None
                text = ""
                if valid and source["medium"] == "pdf":
                    text = next(
                        (
                            page["text"]
                            for page in source["pages"]
                            if page["page_number"] == citation.page_number
                        ),
                        "",
                    )
                    valid = citation.page_number is not None
                elif valid:
                    text = source["text"]
                    valid = citation.page_number is None
                if not valid or citation.quotation not in text:
                    raise HTTPException(
                        502,
                        {
                            "code": "ai_invalid_citation",
                            "message": "Citation text or source/page is invalid.",
                        },
                    )
            validate_literal_support(category, claim)
            unclear |= claim.ambiguous
            if category in {"equipment", "included_items"}:
                key = claim.name.strip().casefold()
                value = claim.quantity
                unclear |= claim.quantity is None
            elif category in {"pickup", "return_time"}:
                key = category
                value = (claim.value.local_datetime, claim.value.timezone)
                unclear |= None in value
            elif category == "amounts":
                key = (
                    claim.kind
                    if claim.kind != "other"
                    else (claim.kind, claim.label.strip().casefold())
                )
                value = (claim.amount, claim.currency)
                unclear |= claim.currency is None
            elif category in {"deposit_conditions", "cancellation_conditions"}:
                # Complementary clauses remain separate; upload order has no role.
                key = claim.value
                value = claim.value
            else:
                key = category
                value = claim.value
            groups[key].add(value)
        unclear |= any(len(values) > 1 for values in groups.values())
        if category in {"deposit_conditions", "cancellation_conditions"}:
            unclear |= policy_conflicts(claims)
        statuses[category] = (
            "unknown"
            if not claims
            else "needs_clarification"
            if unclear
            else "extracted"
        )
    # A currency mismatch across named money claims also requires clarification.
    currencies = {c.value for c in extraction.currency}
    currencies.update(c.currency for c in extraction.amounts if c.currency is not None)
    if len(currencies) > 1:
        if extraction.currency:
            statuses["currency"] = "needs_clarification"
        if extraction.amounts:
            statuses["amounts"] = "needs_clarification"
    return DraftContent(
        extraction=extraction,
        term_statuses=TermStatuses(**statuses),
        needs_clarification=any(value != "extracted" for value in statuses.values()),
    )
