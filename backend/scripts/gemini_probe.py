"""Manual, sequential Gemini probes. Importing this module never loads credentials."""

import json
import logging
import warnings
from pathlib import Path
from typing import Literal

import httpx
from fastapi import HTTPException
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.drafts.diagnostics import PROVIDER_CODES, safe_error_fields
from app.drafts.gemini_schema import decode_extraction, extraction_json_schema
from app.drafts.provider import SYSTEM_PROMPT
from app.drafts.service import validate_and_classify
from scripts.probe_redaction import explanation

TEXT_INPUT = "Reply exactly OK."
JSON_INPUT = 'Return JSON with status equal to "ok".'
SOURCE = {
    "source_id": "00000000-0000-0000-0000-000000000001",
    "source_type": "quotation",
    "medium": "pasted_text",
    "filename": None,
    "text": "Camera quantity 1. Rental total USD 200.00.",
    "pages": [],
}
EXTRACTION_INPUT = json.dumps({"evidence": [SOURCE]})


class TinyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


def load_settings() -> Settings:
    return Settings(_env_file=Path(__file__).resolve().parents[1] / ".env")


PROBE_NAMES = ("minimal_text", "tiny_schema", "extraction_schema")


def request_for(name):
    if name == "minimal_text":
        return TEXT_INPUT, types.GenerateContentConfig(max_output_tokens=1024)
    if name == "tiny_schema":
        return JSON_INPUT, types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "object",
                "properties": {"status": {"type": "string", "enum": ["ok"]}},
                "required": ["status"],
                "additionalProperties": False,
            },
            max_output_tokens=1024,
        )
    return EXTRACTION_INPUT, types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_json_schema=extraction_json_schema(),
        max_output_tokens=16000,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def diagnostics(error, key, model, output):
    result = {"exception_type": type(error).__name__, "sdk_version": genai.__version__}
    if isinstance(error, errors.APIError):
        result["provider_http_status"] = (
            error.code if type(error.code) is int and 100 <= error.code <= 599 else None
        )
        result["provider_error_code"] = (
            error.status
            if isinstance(error.status, str) and error.status in PROVIDER_CODES
            else "UNKNOWN"
        )
        result["parameter_paths"] = safe_error_fields(error)
        excluded = [
            TEXT_INPUT,
            JSON_INPUT,
            EXTRACTION_INPUT,
            SOURCE["text"],
            SYSTEM_PROMPT,
            *output,
        ]
        messages = [error.message]
        # Select messages/descriptions only, not body serialization or arbitrary
        # metadata. All selected text goes through the same strict redactor.
        body = error.details if isinstance(error.details, dict) else {}
        body = body.get("error", body)
        details = body.get("details", []) if isinstance(body, dict) else []
        for detail in details[:10] if isinstance(details, list) else []:
            if (
                isinstance(detail, dict)
                and detail.get("@type") == "type.googleapis.com/google.rpc.BadRequest"
            ):
                violations = detail.get("fieldViolations", [])
                for violation in (
                    violations[:10] if isinstance(violations, list) else []
                ):
                    if isinstance(violation, dict):
                        messages.append(violation.get("description"))
        result["explanations"] = list(
            dict.fromkeys(
                explanation(message, secret=key, excluded=excluded, model=model)
                for message in messages
                if isinstance(message, str)
            )
        )[:6]
    elif isinstance(error, (httpx.TimeoutException, TimeoutError)):
        result["summary"] = "Gemini request timed out."
    elif isinstance(error, ValidationError):
        result["summary"] = (
            "Response failed application-side validation; output omitted."
        )
    elif isinstance(error, HTTPException):
        code = error.detail.get("code") if isinstance(error.detail, dict) else None
        if code in {"ai_invalid_citation", "ai_unsupported_value", "ai_invalid_output"}:
            result["validation_code"] = code
        result["summary"] = "Response failed evidence validation; output omitted."
    else:
        result["summary"] = "Probe failed; exception text omitted for privacy."
    return result


def emit(name, success, detail=None):
    print(
        json.dumps(
            {
                "probe": name,
                "status": "success" if success else "failure",
                "diagnostics": detail or {},
            },
            sort_keys=True,
        ),
        flush=True,
    )


def run_probes(client, key, model) -> int:
    output = []
    for name in PROBE_NAMES:
        try:
            text, config = request_for(name)
            response = client.models.generate_content(
                model=model,
                contents=types.Content(
                    role="user", parts=[types.Part.from_text(text=text)]
                ),
                config=config,
            )
            candidates = response.candidates or []
            if (
                len(candidates) != 1
                or candidates[0].finish_reason != types.FinishReason.STOP
            ):
                emit(
                    name,
                    False,
                    {"summary": "Provider blocked or did not complete the probe."},
                )
                return 1
            parts = candidates[0].content.parts if candidates[0].content else []
            raw = "".join(part.text or "" for part in parts or [] if not part.thought)
            output.append(raw)
            if not raw.strip():
                emit(name, False, {"summary": "Provider returned no text."})
                return 1
            if name == "tiny_schema":
                TinyOutput.model_validate_json(raw)
            elif name == "extraction_schema":
                validate_and_classify(decode_extraction(raw), [SOURCE])
        except Exception as error:
            emit(name, False, diagnostics(error, key, model, output))
            return 1
        emit(name, True)
    return 0


def main() -> int:
    # Suppress SDK/HTTP logging and warnings, even if enabled in this process.
    # Only the explicit sanitized JSON probe events are written to stdout.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        client = None
        key, model = "", ""
        try:
            settings = load_settings()
            key = (
                settings.gemini_api_key.get_secret_value()
                if settings.gemini_api_key
                else ""
            )
            model = settings.gemini_model.strip()
            if not key.strip() or not model:
                emit(
                    "minimal_text",
                    False,
                    {"summary": "Configure backend GEMINI_API_KEY and GEMINI_MODEL."},
                )
                return 1
            client = genai.Client(
                api_key=key,
                vertexai=False,
                http_options=types.HttpOptions(
                    api_version="v1beta",
                    base_url="https://generativelanguage.googleapis.com",
                    timeout=60000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            return run_probes(client, key, model)
        except KeyboardInterrupt:
            emit("manual_probe", False, {"summary": "Cancelled."})
            return 1
        except Exception as error:
            emit("minimal_text", False, diagnostics(error, key, model, []))
            return 1
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass  # Cleanup is not a probe; never print a raw traceback.
            logging.disable(previous)


if __name__ == "__main__":
    raise SystemExit(main())
