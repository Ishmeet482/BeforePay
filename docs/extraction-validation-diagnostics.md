# Extraction output validation diagnostics — 9 November 2026

## Confirmed evidence and limit

The user reported a hosted draft-extraction failure around **08:10–08:14 UTC**
on 9 November. The supplied sanitised runtime record contains:

```json
{
  "exception_type": "ValidationError",
  "model": "gemini-3.5-flash-lite",
  "parameter_paths": [],
  "provider_error_code": "INVALID_OUTPUT",
  "provider_http_status": 200,
  "summary": "Gemini output failed Pydantic validation."
}
```

This confirms local Pydantic validation failed while handling a successful provider
response. It does **not** identify the field, rejected value or validation stage.
`parameter_paths` refers to structured provider request errors, not local output
validation. No Vercel runtime-log tool or CLI was available in this session; the
record above was supplied by the user. No hosted records or raw responses were
retrieved. The historical failed field remains unknown and cannot be inferred from
consistent source facts alone. No particular model/prompt/date/money defect is
claimed fixed, and no prompt or acceptance constraint was changed speculatively.

## Implemented diagnostic correction

`gemini_failure` now adds `validation_stage` and `validation_errors` for structured
validation failures. Stages distinguish:

| Stage | Validated boundary |
| --- | --- |
| `provider_response` | Pydantic failures outside the explicitly tagged conversions, such as SDK response handling. This fallback does not guess a narrower stage. |
| `wire_schema` | Raw JSON → strict all-string `WireDraft` / `WireTerm`. |
| `wire_invariants` | Category coverage, unknown/known mixing, positive integer syntax and unused wire fields. |
| `domain_schema` | Wire conversion → internal `Extraction` and its nested claims, citations, times and money. |
| `metadata_schema` | Response metadata → `ModelMetadata`. |
| `draft_schema` | Service-level Extraction revalidation and final `TermStatuses` / `DraftContent` construction. |

Internal service conversion failures emit `draft_validation_failure` through the
same `uvicorn.error.contextkey.gemini` logger. Final draft construction failures
now return the existing safe `502 ai_invalid_output` contract instead of an
unhandled construction error; no draft can be persisted from either failure.
Original Pydantic exceptions in the provider path keep their type/cause; tagging
adds only a fixed stage name. Manual decoder checks retain the same rejection
conditions and carry fixed field/rule identifiers through a `ValueError` subclass.

An **illustrative synthetic** diagnostic might contain:

```json
{
  "validation_stage": "wire_schema",
  "validation_errors": [
    {"path": "terms[0].quantity", "category": "string_type"}
  ]
}
```

That example describes an offline regression, **not the hosted incident**.
Domain paths may instead resemble `amounts[0].amount` or
`pickup[0].value.local_datetime`. `value_error` is Pydantic's category for a custom
validator rejection; consult the validator at that path without logging its input
or exception prose. Unknown categories become `validation_error`.

## Privacy and unchanged safeguards

- Only application-owned field names, bounded list indices, fixed stages and
  allowlisted error categories are emitted. Unknown field/path components become
  `[unknown_field]`; at most 12 issues and eight path components are reported.
- Pydantic inputs, contexts and URLs are excluded. Error messages, exception text,
  raw model output, quotes/source text, field values, UUIDs, booking titles,
  credentials and personal identifiers are never attached to the new log fields.
  No exception/traceback objects are attached to diagnostic records. Existing
  safe provider/model/status logging remains unchanged.
- No financial values are repaired, quantities inferred or citations bypassed.
  Money/date/evidence validation, exact quotations, strict wire schema and review
  requirements remain authoritative. No automatic retry, fallback, model change,
  quota reset or refund of reservations was introduced.
- No migration, deployment, environment/configuration edit, credential retrieval,
  hosted write or Gemini/PayPal call occurred in this investigation.

## Offline checks

**151 passed**, six existing dependency warnings:

```sh
cd backend
uv run --frozen --offline pytest -q -x --tb=short \
  tests/test_extraction_validation_diagnostics.py tests/test_gemini_diagnostics.py \
  tests/test_compact_extraction.py tests/test_drafts.py tests/test_public_admission.py
```

Coverage includes all tagged boundaries, malformed JSON, strict scalar types,
invalid UUIDs, unused fields, metadata failure, internal draft conversion failure,
bounded unknown-key redaction, secrets/source/exception canaries, single SDK call,
no draft publication on rejection, original evidence constraints and public quotas.
Ruff lint/format and whitespace checks also passed. No frontend files changed.

A separately authored synthetic case mirrors the reported facts in **two
consistent test sources**: one camera, two batteries, one microphone; pickup
20 November 09:00 UTC, return 22 November 09:00 UTC; USD 60 rental, USD 40 deposit,
USD 100 total; at least 48 hours refunds rental 60/deposit 40, nearer pickup rental
0/deposit 40. Correct wire rows pass the existing schema/evidence validators and
retain exact test citations and stated amounts. This is a mocked/offline
compatibility regression, not the saved hosted sources or a reproduction of the
unknown model response. It does not calculate refunds or certify model accuracy.

## Remaining hosted diagnosis

After the normal authorised deployment of this code, if a separately authorised
extraction fails again, retrieve that invocation's `gemini_failure` or
`draft_validation_failure` JSON from backend Vercel runtime logs. Share only stage,
field paths/error categories, safe status/model and invocation time. Do not turn on
SDK payload/debug logging, expose raw exceptions, change sources to guess around
validation, or run another provider request solely to manufacture diagnostic data.
This code cannot reconstruct field details missing from the old runtime entry.
