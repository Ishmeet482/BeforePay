"""Bounded structured-output diagnostics. Never serialize values or error prose."""

import json
import logging

from pydantic import ValidationError

STAGES = frozenset(
    {
        "provider_response",
        "wire_schema",
        "wire_invariants",
        "domain_schema",
        "metadata_schema",
        "draft_schema",
    }
)
FIELDS = frozenset(
    {
        "terms",
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
        "citations",
        "ambiguous",
        "amount",
        "label",
        "local_datetime",
        "equipment",
        "pickup",
        "return_time",
        "amounts",
        "deposit_conditions",
        "cancellation_conditions",
        "included_items",
        "extraction",
        "term_statuses",
        "needs_clarification",
        "provider",
        "requested_model",
        "response_model",
        "response_id",
        "sdk_version",
        "prompt_version",
        "input_tokens",
        "output_tokens",
    }
)
CATEGORIES = frozenset(
    {
        "missing",
        "extra_forbidden",
        "string_type",
        "string_too_short",
        "string_too_long",
        "string_pattern_mismatch",
        "literal_error",
        "uuid_parsing",
        "uuid_type",
        "int_type",
        "int_parsing",
        "bool_type",
        "bool_parsing",
        "list_type",
        "dict_type",
        "model_type",
        "model_attributes_type",
        "json_invalid",
        "json_type",
        "too_short",
        "too_long",
        "greater_than_equal",
        "less_than_equal",
        "decimal_type",
        "decimal_parsing",
        "decimal_max_digits",
        "decimal_max_places",
        "decimal_whole_digits",
        "finite_number",
        "value_error",
        "unknown_category",
        "unknown_row_contains_fact",
        "positive_integer_string_required",
        "unused_field_not_empty",
        "missing_category",
        "unknown_with_known_claims",
    }
)


class WireInvariantError(ValueError):
    def __init__(self, issues):
        super().__init__("Invalid extraction wire contract")
        self.issues = issues
        self._beforepay_validation_stage = "wire_invariants"


def validate_at(stage, operation):
    """Preserve the original Pydantic exception and validation behaviour."""
    try:
        return operation()
    except ValidationError as error:
        error._beforepay_validation_stage = stage
        raise


def safe_path(location):
    parts = []
    for item in location[:8]:
        if isinstance(item, str) and item in FIELDS:
            parts.append(("." if parts else "") + item)
        elif type(item) is int and 0 <= item <= 808:
            parts.append(f"[{item}]")
        else:
            parts.append(".[unknown_field]" if parts else "[unknown_field]")
    return "".join(parts) or "$"


def validation_report(error, stage="provider_response"):
    if isinstance(error, ValidationError):
        # Deliberately never read msg, input, ctx, URL, str(error) or repr(error).
        issues = [
            (item["loc"], item["type"])
            for item in error.errors(
                include_input=False, include_context=False, include_url=False
            )[:12]
        ]
    elif isinstance(error, WireInvariantError):
        issues = error.issues[:12]
    else:
        return {}
    tagged = getattr(error, "_beforepay_validation_stage", stage)
    return {
        "validation_stage": tagged if tagged in STAGES else "provider_response",
        "validation_errors": [
            {
                "path": safe_path(path),
                "category": category if category in CATEGORIES else "validation_error",
            }
            for path, category in issues
        ],
    }


def log_draft_validation(error):
    logging.getLogger("uvicorn.error.contextkey.gemini").warning(
        "draft_validation_failure %s",
        json.dumps(validation_report(error, "draft_schema"), sort_keys=True),
    )
