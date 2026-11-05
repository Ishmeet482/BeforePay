import json
import logging
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException
from google.genai import errors, types

from app.core.config import Settings
from app.drafts import provider
from app.drafts.diagnostics import log_gemini_failure, safe_error_fields

KEY = "AIza-test-secret-canary"
DOCUMENT = "private customer quotation canary"
URL = f"https://example.invalid/generate?key={KEY}&document={DOCUMENT}"
PRIVATE = f"Authorization: Bearer {KEY}; URL={URL}; source={DOCUMENT}"
MODEL = "gemini-3.5-flash-lite"
LOGGER = "uvicorn.error.contextkey.gemini"


def diagnostic(caplog):
    records = [record for record in caplog.records if record.name == LOGGER]
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is None
    assert record.stack_info is None
    message = record.getMessage()
    assert message.startswith("gemini_failure ")
    assert KEY not in message
    assert DOCUMENT not in message
    assert "Authorization" not in message
    assert "https://" not in message
    assert provider.SYSTEM_PROMPT not in message
    return json.loads(message.removeprefix("gemini_failure "))


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "INVALID_ARGUMENT"),
        (404, "NOT_FOUND"),
        (429, "RESOURCE_EXHAUSTED"),
        (503, "UNAVAILABLE"),
    ],
)
def test_api_diagnostics_are_allowlisted(caplog, status, code):
    error = errors.APIError(
        status,
        {
            "error": {
                "status": code,
                "message": PRIVATE,
                "details": [{"prompt": provider.SYSTEM_PROMPT}],
            }
        },
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        log_gemini_failure(error, MODEL, KEY, None)
    logged = diagnostic(caplog)
    assert logged["exception_type"] == "APIError"
    assert logged["provider_http_status"] == status
    assert logged["provider_error_code"] == code
    assert logged["model"] == MODEL
    assert logged["summary"]
    assert all(value is not error for value in caplog.records[0].__dict__.values())


@pytest.mark.parametrize(
    "model",
    [
        URL,
        f"gemini-{KEY}",
        "gemini-3.5-flash-lite\nAuthorization: Bearer secret",
        "x" * 1000,
    ],
)
def test_untrusted_model_and_error_fields_are_redacted(caplog, model):
    error = errors.APIError(400, {"error": {"status": PRIVATE, "message": PRIVATE}})
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        log_gemini_failure(error, model, KEY, None)
    logged = diagnostic(caplog)
    assert logged["provider_error_code"] == "UNKNOWN"
    assert logged["model"] == "[redacted]"


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("api", 502, "ai_unavailable"),
        ("timeout", 504, "ai_timeout"),
        ("connection", 502, "ai_unavailable"),
        ("quota", 503, "ai_rate_limited"),
        ("validation", 502, "ai_invalid_output"),
    ],
)
def test_failures_keep_original_cause_without_logging_it(
    monkeypatch, caplog, kind, status, code
):
    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=KEY, gemini_model=MODEL),
    )
    request = httpx.Request(
        "POST", URL, headers={"Authorization": f"Bearer {KEY}"}, content=DOCUMENT
    )
    originals = {
        "api": errors.APIError(
            400, {"error": {"status": "INVALID_ARGUMENT", "message": PRIVATE}}
        ),
        "timeout": httpx.ReadTimeout(PRIVATE, request=request),
        "connection": httpx.ConnectError(PRIVATE, request=request),
        "quota": errors.APIError(
            429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": PRIVATE}}
        ),
    }
    client = MagicMock()
    client.__enter__.return_value = client
    if kind == "validation":
        client.models.generate_content.return_value = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    finish_reason=types.FinishReason.STOP,
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text=json.dumps({"equipment": PRIVATE})
                            )
                        ],
                    ),
                )
            ]
        )
    else:
        client.models.generate_content.side_effect = originals[kind]
    monkeypatch.setattr(provider.genai, "Client", lambda **kwargs: client)
    with (
        caplog.at_level(logging.WARNING, logger=LOGGER),
        pytest.raises(HTTPException) as caught,
    ):
        provider.GeminiExtractor().extract([{"text": DOCUMENT}])
    assert caught.value.status_code == status
    assert caught.value.detail["code"] == code
    if kind == "validation":
        from pydantic import ValidationError

        assert isinstance(caught.value.__cause__, ValidationError)
    else:
        assert caught.value.__cause__ is originals[kind]
    logged = diagnostic(caplog)
    assert logged["model"] == MODEL
    if kind == "validation":
        assert logged["provider_http_status"] == 200
        assert logged["provider_error_code"] == "INVALID_OUTPUT"
    if kind == "api":
        assert logged["provider_http_status"] == 400
        assert logged["provider_error_code"] == "INVALID_ARGUMENT"
    if kind in {"timeout", "connection"}:
        assert logged["provider_http_status"] is None
    assert KEY not in json.dumps(caught.value.detail)
    assert DOCUMENT not in json.dumps(caught.value.detail)
    assert client.models.generate_content.call_count == 1


def rpc_error(fields):
    return errors.ClientError(
        400,
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": PRIVATE,
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.BadRequest",
                        "fieldViolations": [
                            {"field": field, "description": PRIVATE} for field in fields
                        ],
                    }
                ],
            }
        },
    )


def test_structured_error_paths_are_canonical_and_allowlisted(caplog):
    path = (
        "generation_config.response_json_schema.properties[terms]"
        ".items.properties[value].type"
    )
    error = rpc_error(
        [
            "generation_config.candidate_count",
            "generationConfig.maxOutputTokens",
            path,
            URL,
            PRIVATE,
            f"generationConfig.responseJsonSchema.properties.{DOCUMENT}",
            "generationConfig.candidateCount.secret",
            "generationConfig.candidateCount\n",
            "generationConfig.responseJsonSchema.properties.equipment.items.properties.quantity.type[99999999]",
        ]
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        log_gemini_failure(error, MODEL, KEY, None)
    assert diagnostic(caplog)["parameter_paths"] == sorted(
        [
            "generationConfig.candidateCount",
            "generationConfig.maxOutputTokens",
            "generationConfig.responseJsonSchema.properties.terms.items.properties.value.type",
        ]
    )


@pytest.mark.parametrize(
    "details",
    [
        None,
        PRIVATE,
        [],
        [PRIVATE],
        [{"@type": "unknown", "fieldViolations": [{"field": "model"}]}],
        [
            {
                "@type": "type.googleapis.com/google.rpc.BadRequest",
                "fieldViolations": PRIVATE,
            }
        ],
        [
            {
                "@type": "type.googleapis.com/google.rpc.BadRequest",
                "fieldViolations": [
                    None,
                    {"field": {"secret": KEY}},
                    {"field": "x" * 1000},
                ],
            }
        ],
    ],
)
def test_unrecognized_structured_details_never_leak(details):
    error = errors.ClientError(400, {"error": {"message": PRIVATE, "details": details}})
    assert safe_error_fields(error) == []


def test_offline_sdk_400_details_reach_safe_diagnostic(monkeypatch, caplog):

    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=KEY, gemini_model=MODEL),
    )
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": 400,
                    "status": "INVALID_ARGUMENT",
                    "message": PRIVATE,
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.BadRequest",
                            "fieldViolations": [
                                {
                                    "field": (
                                        "generation_config.response_json_schema"
                                        ".properties[terms].items.properties[value].type"
                                    ),
                                    "description": PRIVATE,
                                }
                            ],
                        }
                    ],
                }
            },
        )

    # conftest blocks the public Client constructor. Use the concrete installed
    # class through its defining module, with an entirely offline transport.
    from google.genai.client import Client as ConcreteSDKClient

    def factory(**kwargs):
        kwargs["http_options"].client_args = {"transport": httpx.MockTransport(handler)}
        return ConcreteSDKClient(**kwargs)

    monkeypatch.setattr(provider.genai, "Client", factory)
    with (
        caplog.at_level(logging.WARNING, logger=LOGGER),
        pytest.raises(HTTPException) as caught,
    ):
        provider.GeminiExtractor().extract([{"text": DOCUMENT}])
    assert len(calls) == 1
    assert caught.value.detail["code"] == "ai_unavailable"
    assert isinstance(caught.value.__cause__, errors.ClientError)
    logged = diagnostic(caplog)
    assert logged["provider_http_status"] == 400
    assert logged["parameter_paths"] == [
        "generationConfig.responseJsonSchema.properties.terms.items.properties.value.type"
    ]
