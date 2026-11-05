# Manual Gemini isolation probes

No live probes were executed while building this tool. Application behavior,
provider/model settings, records and billing are unchanged.

From the workspace root, run this single command when ready:

```sh
uv run --quiet --directory backend --frozen python -m scripts.gemini_probe
```

The command reads existing `backend/.env` settings at runtime, with the same
backend process-environment override behavior as the application. It uses only
`GEMINI_API_KEY` and the configured `GEMINI_MODEL` for inference. No key copying,
printing, model change, fallback or billing upgrade is performed. Keep the existing
Free Tier project; the tool cannot independently verify account billing state.

## Probe sequence

1. `minimal_text`: a tiny text prompt, no JSON schema.
2. `tiny_schema`: the same model with a single-field JSON schema and JSON MIME
   output; validate the returned status object locally.
3. `extraction_schema`: the exact application transport schema and system prompt,
   with one short synthetic quotation. Validate returned JSON through the existing
   Pydantic and citation validators. No database connection, upload, draft creation
   or source retrieval is performed.

Every request uses the official installed Google GenAI SDK `models.generate_content`
with the Developer API `v1beta` endpoint, explicit backend key, 60-second timeout
and one total attempt. No `candidateCount` or sampling parameters are sent.
Request/schema construction follows Google's
[structured-output example](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
and [official SDK documentation](https://googleapis.github.io/python-genai/).

The tool issues **at most three model requests**, consuming project quota, stopping
immediately after the first provider/response/validation failure. It never retries
or substitutes a model/provider/result. Exit status is 0 if all probes succeed,
1 on failure. Missing credentials fail before the first request.

## Output and privacy

Only JSON lines containing `probe`, `status` and `diagnostics` are printed.
Success does not print generated text or JSON. Failure diagnostics include SDK
version, exception type and, for API errors, HTTP status, canonical provider code,
recognized parameter paths and sanitized provider `explanations`.

Unlike application logging's fixed summaries, explanations retain provider wording
about invalid field names, schema types, unsupported settings and complexity.
For example, `Unknown name "responseJsonSchema" ... Cannot find field` or
`The response schema is too complex for serving.` can survive intact. Messages
and typed field-violation descriptions are processed separately; raw error bodies
and arbitrary metadata are never serialized.

Redaction removes known credentials and URL/JSON-encoded variants, credential
headers, URLs, known input/output content and embedded object bodies. A bounded
technical-vocabulary/schema-identifier check suppresses unrecognized prose rather
than risking document/customer text. Some unusual provider wording may therefore
appear as `[redacted non-diagnostic explanation]`. SDK/HTTP logging and warnings
are suppressed while this manual tool runs; original settings are restored on exit.
No actual credentials were read while developing or testing the tool.

## Interpreting results

- Probe 1 fails: model access, key, transport or the base request failed before
  structured output was attempted; inspect the sanitized provider explanation.
- Probe 1 succeeds, probe 2 fails: failure isolates a small JSON request/response.
- First two succeed, probe 3 fails: inspect whether the provider rejected the
  application schema or local JSON/evidence validation failed. A local validation
  error is not proof of server-side schema rejection; output stays private.
- All three succeed: this synthetic case works. It does not prove a real booking's
  larger evidence payload, extraction quality or a stale running server works.

Share only the tool's sanitized JSON lines when investigating. Automated tests use
fake keys, mocked clients and actual SDK serialization over HTTPX MockTransport;
they never load developer credentials or issue live model calls.
