import json
import logging
import warnings
from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors, types

from app.core.config import Settings
from app.drafts.gemini_schema import FIELDS, extraction_json_schema
from app.drafts.schemas import Extraction
from scripts import gemini_probe as probe
from scripts.probe_redaction import explanation

KEY = "AIza-offline-secret-canary-123456789"
MODEL = "gemini-3.5-flash-lite"


def response(text):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason=types.FinishReason.STOP,
                content=types.Content(
                    role="model", parts=[types.Part.from_text(text=text)]
                ),
            )
        ]
    )


def successful_responses():
    return [
        response("OK"),
        response('{"status":"ok"}'),
        response(
            json.dumps(
                {
                    "terms": [
                        {
                            **dict.fromkeys(
                                FIELDS,
                                "",
                            ),
                            "category": field,
                            "state": "unknown",
                        }
                        for field in Extraction.model_fields
                    ]
                }
            )
        ),
    ]


def configure(monkeypatch, responses):
    monkeypatch.setattr(
        probe,
        "load_settings",
        lambda: Settings(_env_file=None, gemini_api_key=KEY, gemini_model=MODEL),
    )
    client = MagicMock()
    client.models.generate_content.side_effect = responses

    def factory(**kwargs):
        assert kwargs["api_key"] == KEY
        assert kwargs["vertexai"] is False
        assert kwargs["http_options"].retry_options.attempts == 1
        logging.getLogger("google.genai").warning(KEY)
        warnings.warn(KEY, stacklevel=1)
        return client

    monkeypatch.setattr(probe.genai, "Client", factory)
    return client


def events(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    assert KEY not in captured.out
    assert probe.SOURCE["text"] not in captured.out
    assert probe.SYSTEM_PROMPT not in captured.out
    return [json.loads(line) for line in captured.out.splitlines()]


def test_three_probes_use_same_model_and_only_synthetic_evidence(monkeypatch, capsys):
    client = configure(monkeypatch, successful_responses())
    previous = logging.root.manager.disable
    assert probe.main() == 0
    assert logging.root.manager.disable == previous
    result = events(capsys)
    assert [event["probe"] for event in result] == list(probe.PROBE_NAMES)
    assert all(event["status"] == "success" for event in result)
    calls = client.models.generate_content.call_args_list
    assert len(calls) == 3
    assert all(call.kwargs["model"] == MODEL for call in calls)
    assert calls[0].kwargs["config"].response_json_schema is None
    assert calls[1].kwargs["config"].response_json_schema["properties"] == {
        "status": {"type": "string", "enum": ["ok"]}
    }
    assert calls[2].kwargs["config"].response_json_schema == extraction_json_schema()
    assert calls[2].kwargs["contents"].parts[0].text == probe.EXTRACTION_INPUT
    client.close.assert_called_once()


@pytest.mark.parametrize("failure_index", [0, 1, 2])
def test_first_failure_stops_and_preserves_parameter_explanation(
    monkeypatch, capsys, failure_index
):
    message = (
        'Invalid JSON payload received. Unknown name "responseJsonSchema" '
        'at "generation_config": Cannot find field.'
    )
    failure = errors.ClientError(
        400, {"error": {"status": "INVALID_ARGUMENT", "message": message}}
    )
    responses = successful_responses()
    responses[failure_index] = failure
    client = configure(monkeypatch, responses)
    assert probe.main() == 1
    result = events(capsys)
    assert len(result) == failure_index + 1
    assert result[-1]["status"] == "failure"
    assert result[-1]["diagnostics"]["explanations"] == [message]
    assert result[-1]["diagnostics"]["provider_http_status"] == 400
    assert client.models.generate_content.call_count == failure_index + 1


@pytest.mark.parametrize(
    "message",
    [
        "The response schema is too complex for serving.",
        "Invalid schema: nullable is not supported. Use anyOf instead.",
        "API key not valid. Please pass a valid API key.",
        "The model does not support response_mime_type.",
        'Unknown field "responseJsonSchema" for GenerationConfig.',
    ],
)
def test_safe_provider_explanations_remain_useful(message):
    assert explanation(message, secret=KEY, excluded=[], model=MODEL) == message


def test_failure_redacts_keys_urls_headers_documents_and_bodies(monkeypatch, capsys):
    private_output = "Private customer name and microphone transcript"
    message = "\n".join(
        [
            "Invalid schema: nullable is not supported.",
            f"Authorization: Bearer {KEY}",
            f"https://example.invalid/?key={KEY}",
            probe.EXTRACTION_INPUT,
            probe.SOURCE["text"],
            probe.SYSTEM_PROMPT,
            private_output,
            'raw body: {"source":"private customer document"}',
        ]
    )
    failure = errors.ClientError(
        400,
        {
            "error": {
                "status": "INVALID_ARGUMENT",
                "message": message,
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.BadRequest",
                        "fieldViolations": [
                            {
                                "field": "generation_config.response_json_schema",
                                "description": (
                                    "The response schema is too complex for serving."
                                ),
                            }
                        ],
                    }
                ],
            }
        },
    )
    configure(monkeypatch, [failure])
    assert probe.main() == 1
    serialized = json.dumps(events(capsys))
    assert "Invalid schema: nullable is not supported." in serialized
    assert "The response schema is too complex for serving." in serialized
    for forbidden in (
        KEY,
        "https://",
        "Authorization:",
        private_output,
        "private customer document",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "kind",
    ["timeout", "invalid_tiny", "invalid_extraction", "invalid_citation", "blocked"],
)
def test_non_api_failures_do_not_dump_output(monkeypatch, capsys, kind):
    responses = successful_responses()
    if kind == "timeout":
        responses[0] = httpx.ReadTimeout(f"https://example.invalid/?key={KEY}")
    elif kind == "invalid_tiny":
        responses[1] = response('{"status":"private customer content"}')
    elif kind == "invalid_extraction":
        responses[2] = response('{"equipment":"private customer content"}')
    elif kind == "invalid_citation":
        data = {
            "terms": [
                {**dict.fromkeys(FIELDS, ""), "category": field, "state": "unknown"}
                for field in Extraction.model_fields
            ]
        }
        data["terms"][0].update(
            state="known",
            name="Camera",
            quantity="1",
            source_id="00000000-0000-0000-0000-000000000002",
            quotation="Camera quantity 1",
        )
        responses[2] = response(json.dumps(data))
    else:
        responses[0] = types.GenerateContentResponse(candidates=[])
    configure(monkeypatch, responses)
    assert probe.main() == 1
    result = events(capsys)
    assert result[-1]["status"] == "failure"
    assert "private customer content" not in json.dumps(result)
    if kind == "invalid_citation":
        assert result[-1]["diagnostics"]["validation_code"] == "ai_invalid_citation"


def test_missing_credentials_make_no_call(monkeypatch, capsys):
    monkeypatch.setattr(
        probe, "load_settings", lambda: Settings(_env_file=None, gemini_api_key=None)
    )
    assert probe.main() == 1
    assert events(capsys)[0]["status"] == "failure"


@pytest.mark.parametrize("fail_second", [False, True])
def test_script_uses_real_sdk_with_offline_transport(monkeypatch, capsys, fail_second):
    from google.genai.client import Client as ConcreteClient

    monkeypatch.setattr(
        probe,
        "load_settings",
        lambda: Settings(_env_file=None, gemini_api_key=KEY, gemini_model=MODEL),
    )
    requests = []
    message = 'Unknown name "responseJsonSchema": Cannot find field.'

    def handler(request):
        requests.append(json.loads(request.content))
        index = len(requests) - 1
        assert request.url.path.endswith(f"{MODEL}:generateContent")
        if fail_second and index == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": 400,
                        "status": "INVALID_ARGUMENT",
                        "message": message,
                    }
                },
            )
        texts = [
            "OK",
            '{"status":"ok"}',
            json.dumps(
                {
                    "terms": [
                        {
                            **dict.fromkeys(
                                FIELDS,
                                "",
                            ),
                            "category": field,
                            "state": "unknown",
                        }
                        for field in Extraction.model_fields
                    ]
                }
            ),
        ]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"role": "model", "parts": [{"text": texts[index]}]},
                    }
                ]
            },
        )

    def factory(**kwargs):
        kwargs["http_options"].client_args = {"transport": httpx.MockTransport(handler)}
        return ConcreteClient(**kwargs)

    monkeypatch.setattr(probe.genai, "Client", factory)
    assert probe.main() == (1 if fail_second else 0)
    result = events(capsys)
    assert len(requests) == (2 if fail_second else 3)
    assert "responseJsonSchema" not in requests[0]["generationConfig"]
    assert all(
        "candidateCount" not in request["generationConfig"] for request in requests
    )
    if fail_second:
        assert result[-1]["diagnostics"]["explanations"] == [message]
    else:
        assert (
            requests[2]["generationConfig"]["responseJsonSchema"]
            == extraction_json_schema()
        )
