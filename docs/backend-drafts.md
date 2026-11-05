# Cited rental draft extraction

Extraction creates immutable **drafts**, never automatically approved agreements.
The separate [customer review stage](customer-review.md) now supports explicit
corrections and confirmation without changing AI drafts. The browser now supports
[booking creation, evidence intake and explicit draft generation](starting-flow.md).
Comparison, cancellation preview and sandbox checkout have their own guides;
draft generation does not perform any of those actions.
The API remains an unauthenticated localhost prototype.

## Provider and model

Use the official `google-genai` Python SDK (locked at 2.34.0), synchronous
`client.models.generate_content`, JSON MIME output and a compact primitive wire
contract converted into fully validated Pydantic domain models. Default **`GEMINI_MODEL=gemini-3.5-flash-lite`**.

Verified against current official Google documentation on 2026-10-29:

- [Pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite)
  lists free-tier input and output for standard requests.
- [Model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
  lists the stable ID and structured-output support.
- [GenerateContent structured-output guide](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
  documents `response_json_schema` and the supported JSON Schema subset.
- [Official SDK documentation](https://googleapis.github.io/python-genai/)
  documents client configuration and request options.

Use the key from your existing **Free Tier project** and leave billing disabled.
Free-tier access has project-specific quotas and availability; this application
cannot verify billing state from an API key. A free-capable model does not make
requests free if you deliberately move the project to a paid tier. No account or
billing changes are made by BeforePay. Quota exhaustion fails clearly; no retry,
paid-provider/model fallback, tools, grounding, caching or batch jobs are invoked.
Google's pricing page notes free-tier content may be used to improve products;
use synthetic evidence for manual verification.

The Developer API client receives only the explicit backend `GEMINI_API_KEY`;
`GOOGLE_API_KEY`, Vertex/enterprise defaults and ADC cannot substitute for it.
Calls have a 60-second timeout, 16,000 output-token cap and one total attempt.
The model ID is configurable; verify free-tier support before changing it.
There is no automatic alternate model selection. An API key is never sent to a
frontend, stored in model metadata, or returned in errors.

The provider-facing schema is a 610-byte `{"terms":[...]}` contract, not the
expanded nested domain schema. Each row has string fields `category`, `state`,
`name`, `value`, `quantity`, `currency`, `kind`, `timezone`, `source_id`, `quotation`
and `page_number`. States are `known`, `unknown`, `conflict`; unused/unknown scalar
fields are empty strings. Unknown categories require an explicit empty unknown
row. Conflicting alternatives are separate cited conflict rows. Money is always
a decimal string; PDF page/quantity strings are parsed only as positive integers.

Amount kinds: `rental_total` (rental fee/subtotal), `total_payable` (inclusive
stated total), `deposit`, `tax`, `delivery`, `other`. For a USD 120 rental fee,
USD 80 deposit and USD 200 total payable, preserve three distinct cited claims:
`rental_total=120`, `deposit=80`, `total_payable=200`. The inclusive total is never
an extra charge; do not add it to the component amounts. Missing totals are not
calculated or invented. Prompt version `rental-draft-gemini-flat-v4` encodes this
distinction. Existing saved classifications remain unchanged.

The wire schema sends only simple objects, arrays and strings, with no reference
expansion, nullable unions, enums or numeric/array constraints. Python strictly
validates the wire DTO, requires all eight categories, rejects extra/unused data
and mixed unknown/known rows, then constructs the original `Extraction` models.
All original quantity, Decimal, timezone, length and UUID checks still run, followed
by unchanged booking/source ownership, exact-quotation, PDF-page and financial
support checks before persistence. A blank quantity becomes unknown, never zero.
Explicit conflicts remain ambiguous regardless of source order. Normal endpoint
responses and stored draft content retain their existing domain shape.

On 2026-10-30, one user-authorized live synthetic extraction through the actual
FastAPI service succeeded (201), persisted an unapproved draft, and was retrieved
through GET (200) and an independent PostgreSQL session. One of five authorized
Gemini requests was used. The flat contract succeeded on the first request;
therefore a further minimal JSON envelope was unnecessary. No automatic retry or
model/provider fallback was added. Exact server-side keyword/complexity limit
behind the previous expanded-schema 400 remains undisclosed.

Selected evidence remains untrusted user data under fixed system instructions.
No tools or automatic function calling are enabled. Prompt-injection precautions
do not prove semantic completeness or correctness; drafts still require review.
New records use `model_metadata.provider="gemini"`. Existing OpenAI drafts retain
all stored metadata and remain readable without installing/calling OpenAI. No
schema migration or record rewrite is needed for the JSON metadata discriminator.

## Configure credentials (backend only)

Edit existing ignored `backend/.env` locally; preserve its database URL and other
settings. Add these lines, replacing only the key placeholder:

```dotenv
GEMINI_API_KEY=your-private-gemini-api-key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Alternatively set these backend process environment variables. Never put keys in
frontend files, `VITE_*` variables, Git, screenshots, or this chat. Restart FastAPI
after configuration changes because settings are cached. No credentials were
added to local environment files by this implementation.

With a blank/missing key, live extraction returns **503** with code
`ai_not_configured` before constructing the SDK client. Ordinary booking/evidence
and draft retrieval operations do not require Gemini credentials.

From root, with existing PostgreSQL running on host **5433**:

```sh
cd backend
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## One manual extraction in Swagger

The provider migration used offline tests; an authorized synthetic live fix was
verified on 2026-10-30 as described above. This walkthrough is for a later
manual check, only after you choose to run it. Step 4 consumes Gemini free-tier
quota when using the verified model on your Free Tier project.

1. Open <http://127.0.0.1:8000/docs>. Select **Try it out → Execute** for each
   operation. `POST /api/bookings` with `{"title":"Manual camera rental"}`.
   Copy returned `id` as `booking_id`.
2. `POST /api/bookings/{booking_id}/sources/text`: use that booking UUID and:

   ```json
   {
     "source_type": "quotation",
     "original_text": "Sony FX3 quantity 1. Battery quantity 2. Included microphone quantity 1.\nPickup 2026-11-01T09:00:00 Asia/Kolkata.\nReturn 2026-11-03T10:00:00 Asia/Kolkata.\nRental total USD 200.10.\nDeposit USD 50.00, refundable on undamaged return."
   }
   ```

3. Copy returned source `id`. A stored text-based PDF can also be selected; its
   citations must specify the actual one-based PDF page containing the quotation.
4. `POST /api/bookings/{booking_id}/drafts`: supply booking UUID and:

   ```json
   {"source_ids":["REPLACE_WITH_SOURCE_UUID"]}
   ```

   Expect **201** with new draft `id`, `version`, `status: "draft"`, explicit input
   source IDs, source hashes, model metadata, extracted claims and term statuses.
   Inspect every quotation against stored evidence. Cancellation remains unknown
   in this example; no policy was supplied. All money is returned as decimal
   strings. No interpretation is automatically approved.
5. `GET /api/bookings/{booking_id}/drafts/{draft_id}` retrieves that exact saved
   version. `GET /api/bookings/{booking_id}/drafts` lists versions newest first
   with `limit`/`offset`. These GET operations make no provider calls.
6. On failure, inspect the safe error code below. A failed/local-rejected result
   may still consume free-tier quota. Repeating POST makes another request and,
   on success, a new immutable draft version. There is no auto-retry or fallback.
   For `ai_rate_limited`, wait for the quota reset; do not enable billing.

For later conflict checks, add a message saying `Battery quantity 1` and include
both source IDs in a separate extraction. Both alternatives must remain present
and require clarification. This consumes additional free-tier quota and is not needed for the
single-extraction smoke check above.

## Contract and validation

- Input: 1–20 distinct stored source UUIDs belonging to this booking; at most
  200,000 original text characters in total. Unknown/foreign input IDs reject
  before provider use. Sources are sorted by UUID for a stable payload; upload
  timestamps are not sent and no source is designated the winner.
- Required Pydantic categories: `equipment`, `pickup`, `return_time`, `currency`,
  `amounts`, `deposit_conditions`, `cancellation_conditions`, `included_items`.
  Each holds cited claims; empty lists mean unknown. Missing scalar components
  stay null. Required `ambiguous` flags can increase uncertainty, never approve.
- Every claim needs a nonblank exact quotation and source UUID. PDF citations
  need a valid page; pasted citations require `page_number: null`. Quotes must
  occur on that particular page/source, without case/whitespace normalization.
  A source outside the selected input set is invalid even within the same booking.
- Lexical support checks also reject obvious fabricated values: item names must
  occur in their quotations; known quantities require digits or number words
  zero–twenty; monetary amounts require matching numeric text; currency requires
  an explicit uppercase code; timezone must appear literally; policy values must
  be verbatim. These conservative checks may reject valid unusual wording. They
  do not establish semantic entailment, identity across differently named items,
  or completeness; human review remains necessary.
- Time has separate `local_datetime` (full ISO local date/time or null) and
  `timezone` (literal IANA name, numeric UTC offset, UTC, or null). No current-date,
  locale or customer-timezone inference. Ambiguous abbreviations stay unknown.
- Money uses finite nonnegative `Decimal`, up to 12 integer and four fractional
  digits, serialized as strings. Floats, conversion, totals and rounding are not
  introduced. Bare currency symbols do not establish a currency code.
- Backend status per category: `unknown`, `extracted`, or `needs_clarification`.
  Different quantities for the same normalized item name, different times,
  different named totals/currencies, ambiguous claims or incomplete scalar values
  require clarification. Different policy strings conservatively require
  clarification even when potentially complementary. No precedence is inferred.
- Any unknown/unclear category sets draft `needs_clarification=true`; even a fully
  extracted draft still has `status: "draft"`, never approval or payment eligibility.
- Each successful extraction inserts a new version with requested/returned model,
  SDK/prompt version, provider response ID, token usage, selected source IDs and
  SHA-256 fingerprints. Original evidence is never rewritten. The provider call
  holds no DB transaction; a booking lock serializes version-number allocation.
  PostgreSQL triggers reject UPDATE/DELETE of draft rows; no mutation routes exist.

## Errors and tests

### Find a sanitized Gemini failure diagnostic

Restart FastAPI in its terminal with normal INFO logging:

```sh
cd backend
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

To reproduce once later, open Swagger at <http://127.0.0.1:8000/docs> and submit
the same `POST /api/bookings/{booking_id}/drafts` with the source IDs from the
failed request. This issues one Gemini request and may consume free-tier quota;
the implementation/tests do not issue live requests. A successful retry creates a
normal new draft; a failed request stores no draft.

Find the `WARNING: ... gemini_failure { ... }` line in that FastAPI terminal's
stderr (or search `gemini_failure` in your existing backend log capture). It comes
from logger `uvicorn.error.contextkey.gemini`, inheriting Uvicorn's stderr handler.
No debug logging, new log file or logging configuration is required.

The JSON contains `exception_type`, `provider_http_status`, `provider_error_code`,
`model`, `summary` and `parameter_paths`. Provider HTTP status is not the API's generic 502: an
upstream 400/`INVALID_ARGUMENT` points toward model/schema/request compatibility;
404 points toward model/resource access; 429 toward quota exhaustion. A transport
failure without a response records null status; failed output validation records
200 because the provider returned a successful HTTP response before validation.

Summary text is selected from fixed safe descriptions, not provider prose.
Provider error codes are allowlisted canonical codes; unknown text is suppressed.
Malformed/credential-containing model IDs are redacted. Exception messages,
response bodies, prompts, documents, request URLs, headers and tracebacks are
never attached to these log records. Original SDK/transport/validation exceptions
remain available internally as the raised HTTPException's `__cause__`, without
being included in the client response or formatted in logs. Do not enable raw
exception/SDK payload logging to inspect that cause.

`parameter_paths` extracts field names only from structured
`google.rpc.BadRequest.fieldViolations`. Snake-case and map-key paths are mapped
to canonical names, then matched in full against application-owned request/schema
paths. For example, `generation_config.candidate_count` becomes
`generationConfig.candidateCount`. Field descriptions, unknown names/suffixes,
values, URLs and untyped details are discarded. Output count/path lengths are
bounded. Empty `parameter_paths` means no recognized field details were supplied;
the code does not scrape free-text provider messages.

### Investigation of 400 INVALID_ARGUMENT

The audit below records the earlier investigation. The subsequent flat-wire fix
and successful live service/PostgreSQL verification are documented in the current
provider section above; no further live probe is required to verify that fix.

If the sanitized application log has no parameter paths, use the separate
[three-probe manual diagnostic](gemini-probes.md). It isolates basic model access,
tiny structured output and the application schema, and retains safely redacted
provider explanations. It does not change the application or run automatically.

Reviewed SDK **2.34.0**, its actual offline-serialized Developer API request, and
the current official model-specific guidance. Confirmed incompatible setting:
the previous adapter explicitly sent `candidateCount: 1`. Google's
[Gemini 3.x migration guidance](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6#api-changes-and-parameter-updates)
instructs removing `candidate_count` for Gemini 3 and later, including 3.5 Flash-Lite.
The adapter now omits it; it still checks that exactly one complete result returns.
Model selection, output token cap, billing and retries are unchanged.

The request audit confirmed:

| Component | Finding |
| --- | --- |
| SDK serialization | `generationConfig` now contains only `responseMimeType`, `responseJsonSchema`, `maxOutputTokens` |
| Output limit | 16,000 is within the model's documented 65,536-token output limit |
| Input/system instruction | User evidence and separate system instruction; no prefilled model turn |
| Decimal | Sent as JSON string type; actual Decimal/string constraints validated locally |
| Nested models/references | Definitions inlined; no `$defs`/`$ref` or recursive schema sent |
| Nullable fields | Primitive type arrays with `null`, documented by Google |
| Constraints | Required properties, enums, numeric bounds and array limits documented; regex/string length/UUID constraints omitted only from transport |
| SDK controls | HTTP timeout/retries and automatic function-call disabling do not become unknown generation parameters |

[Structured-output schema guide](https://ai.google.dev/gemini-api/docs/generate-content/structured-output),
[model limits](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite),
and [GenerateContent reference](https://ai.google.dev/api/generate-content)
support this audit. No additional schema incompatibility was confirmed, so the
schema and full application-side evidence/Pydantic validation were not weakened.
No SDK upgrade or speculative model/API switch was necessary.

This identifies a documented request incompatibility, **not proof it was the sole
cause of the user's live 400**. No live call was made and the supplied diagnostic
did not contain structured field violations. Next step: restart FastAPI and repeat
the same extraction once using the walkthrough above; inspect the sanitized
`gemini_failure.parameter_paths`. If still failing, share only that sanitized
event. Empty paths leave the exact rejecting field unknown; do not publish raw
provider bodies or enable payload logging.

| HTTP | Code or condition | Result |
| --- | --- | --- |
| 404 | Unknown booking/draft, or draft belongs to another booking | No provider call |
| 422 | Invalid/empty/duplicate/foreign input source IDs | No provider call |
| 413 | Input character budget exceeded | No provider call |
| 503 | `ai_not_configured` | No provider call |
| 503 | `ai_credentials_rejected` | No draft saved |
| 503 | `ai_rate_limited` (quota exhausted/rate limited) | No draft saved; wait for reset, no fallback |
| 504 | `ai_timeout` | No draft saved |
| 502 | `ai_unavailable`, `ai_no_draft`, `ai_invalid_output` | No draft saved |
| 502 | `ai_invalid_citation`, `ai_unsupported_value` | Whole draft rejected |

Errors never echo provider payloads, API keys or customer text. Test with:

```sh
cd backend
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen alembic current
uv run --frozen alembic check
```

Tests use isolated PostgreSQL, mocked extractors and the actual Google SDK over
HTTPX MockTransport. Developer `.env` files are never loaded by these tests; local
test database defaults come from the public settings, with no real API keys. An autouse guard blocks live SDK construction unless a test
explicitly installs its offline fake. They cover quotation/source/page integrity,
unknown terms, conflicts/order independence, invalid typed values, missing keys,
safe provider failures, committed storage, immutable rows and concurrent version
allocation. They do not prove live model quality or account availability.
