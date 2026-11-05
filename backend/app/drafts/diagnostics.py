"""Allowlisted provider diagnostics; never serialize exception messages/payloads."""

import json
import logging
import re
from functools import lru_cache

import httpx
from fastapi import HTTPException
from google.genai import errors
from pydantic import ValidationError

from app.drafts.gemini_schema import extraction_json_schema

# Inherit Uvicorn's existing stderr handler/level, without configuring root logging.
logger = logging.getLogger("uvicorn.error.contextkey.gemini")

PROVIDER_CODES = frozenset(
    {
        "CANCELLED",
        "UNKNOWN",
        "INVALID_ARGUMENT",
        "DEADLINE_EXCEEDED",
        "NOT_FOUND",
        "ALREADY_EXISTS",
        "PERMISSION_DENIED",
        "RESOURCE_EXHAUSTED",
        "FAILED_PRECONDITION",
        "ABORTED",
        "OUT_OF_RANGE",
        "UNIMPLEMENTED",
        "INTERNAL",
        "UNAVAILABLE",
        "DATA_LOSS",
        "UNAUTHENTICATED",
    }
)

FIELD_ALIASES = {
    "generation_config": "generationConfig",
    "response_json_schema": "responseJsonSchema",
    "response_schema": "responseSchema",
    "response_mime_type": "responseMimeType",
    "response_format": "responseFormat",
    "candidate_count": "candidateCount",
    "max_output_tokens": "maxOutputTokens",
    "system_instruction": "systemInstruction",
    "thinking_config": "thinkingConfig",
    "thinking_budget": "thinkingBudget",
    "thinking_level": "thinkingLevel",
    "top_p": "topP",
    "top_k": "topK",
    "additional_properties": "additionalProperties",
    "min_items": "minItems",
    "max_items": "maxItems",
}


@lru_cache
def allowed_error_fields() -> frozenset[str]:
    # All names come from application-owned configuration/schema, never sources
    # or provider prose. Retain candidateCount to diagnose older server processes.
    fields = {
        "model",
        "contents",
        "systemInstruction",
        "generationConfig",
        *[
            f"generationConfig.{name}"
            for name in (
                "candidateCount",
                "maxOutputTokens",
                "responseMimeType",
                "responseJsonSchema",
                "responseSchema",
                "responseFormat",
                "temperature",
                "topP",
                "topK",
                "thinkingConfig",
            )
        ],
        "generationConfig.thinkingConfig.thinkingBudget",
        "generationConfig.thinkingConfig.thinkingLevel",
    }

    def walk(node, path):
        fields.add(path)
        for key, value in node.items():
            child = f"{path}.{key}"
            fields.add(child)
            if key == "properties":
                for name, prop in value.items():
                    walk(prop, f"{child}.{name}")
            elif key == "items":
                walk(value, child)
            elif key == "type" and isinstance(value, list):
                fields.update(f"{child}[{i}]" for i in range(len(value)))

    schema = extraction_json_schema()
    for prefix in (
        "generationConfig.responseJsonSchema",
        "generationConfig.responseSchema",
    ):
        walk(schema, prefix)
    return frozenset(fields)


def safe_error_fields(error: errors.APIError) -> list[str]:
    """Read only typed RPC field names; never descriptions, messages or values."""
    body = error.details
    if not isinstance(body, dict):
        return []
    body = body.get("error", body)
    if not isinstance(body, dict) or not isinstance(body.get("details"), list):
        return []
    accepted = set()
    for detail in body["details"][:20]:
        if not isinstance(detail, dict):
            continue
        if detail.get("@type") != "type.googleapis.com/google.rpc.BadRequest":
            continue
        violations = detail.get("fieldViolations")
        if not isinstance(violations, list):
            continue
        for violation in violations[:20]:
            field = violation.get("field") if isinstance(violation, dict) else None
            if not isinstance(field, str) or len(field) > 512:
                continue
            # Accept common RPC map-key/snake-case spelling, then match the
            # ENTIRE path. Never expose unknown suffixes or provider field values.
            normalized = re.sub(
                r"\[['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\]", r".\1", field
            )
            normalized = ".".join(
                FIELD_ALIASES.get(part, part) for part in normalized.split(".")
            )
            if normalized in allowed_error_fields():
                accepted.add(normalized)
    return sorted(accepted)[:12]


def log_gemini_failure(
    error: Exception, model: str, api_key: str, response_status: int | None
) -> None:
    status = response_status
    code = "UNKNOWN"
    summary = "Gemini request failed; inspect status and model configuration."
    fields = []
    if isinstance(error, errors.APIError):
        fields = safe_error_fields(error)
        status = (
            error.code if type(error.code) is int and 100 <= error.code <= 599 else None
        )
        code = (
            error.status
            if isinstance(error.status, str) and error.status in PROVIDER_CODES
            else "UNKNOWN"
        )
        summary = {
            400: "Gemini rejected parameters; check model/schema compatibility.",
            401: "Gemini credentials rejected.",
            403: "Gemini access denied; check key permissions and project access.",
            404: "Gemini resource/model unavailable; check configured model access.",
            408: "Gemini request timed out.",
            429: "Gemini quota exhausted or rate limited; wait for reset.",
            500: "Gemini reported an internal provider error.",
            503: "Gemini service unavailable.",
            504: "Gemini request timed out.",
        }.get(status, summary)
    elif isinstance(error, (httpx.TimeoutException, TimeoutError)):
        code, summary = "TIMEOUT", "Gemini transport timed out."
    elif isinstance(error, httpx.RequestError):
        code, summary = "CONNECTION_ERROR", "Gemini transport connection failed."
    elif isinstance(error, ValidationError):
        code, summary = "INVALID_OUTPUT", "Gemini output failed Pydantic validation."
    elif isinstance(error, ValueError):
        code, summary = (
            "INVALID_OUTPUT",
            "Gemini configuration/output validation failed.",
        )
    elif isinstance(error, HTTPException):
        code, summary = (
            "NO_DRAFT",
            "Gemini returned blocked/incomplete/non-JSON output.",
        )

    # Model configuration is not trusted log content: reject URLs, headers, control
    # characters, oversized strings and accidental inclusion of the actual key.
    safe_model = (
        model
        if re.fullmatch(r"(?:models/)?gemini-[A-Za-z0-9._-]{1,100}", model)
        else "[redacted]"
    )
    if api_key and api_key in safe_model:
        safe_model = "[redacted]"
    exception_type = type(error).__name__
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", exception_type) or (
        api_key and api_key in exception_type
    ):
        exception_type = "[redacted]"
    # Do not attach error/response objects, exc_info, stack_info or original text
    # to LogRecord. Redacting free text cannot reliably remove customer evidence.
    logger.warning(
        "gemini_failure %s",
        json.dumps(
            {
                "exception_type": exception_type,
                "provider_http_status": status,
                "provider_error_code": code,
                "model": safe_model,
                "summary": summary,
                "parameter_paths": fields,
            },
            sort_keys=True,
        ),
    )
