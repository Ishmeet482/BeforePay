# BeforePay implementation plan

Current browser starting flow: [create booking → evidence → explicit AI draft →
Agreement review](starting-flow.md). Existing comparison, cancellation and sandbox
checkout stages remain available with their original backend protections.

## Product brief and scope

Source: `ContextKey - Book with confidence.pdf`, supplied in the workspace
(three pages; read with PyMuPDF). No pre-existing `docs/` brief was present.

BeforePay serves camera and audiovisual rental customers and merchants. A
confirmed quotation plus supporting messages becomes a concise, source-linked
agreement summary. The customer confirms it; the final booking is compared with
that agreement. Equivalent wording should pass, while missing conditions and
ambiguous or conflicting evidence stay unresolved. Price equality alone does not
establish agreement: equipment, accessories, quantities, pickup/return dates,
deposits, cancellation and refund conditions all matter.

Customers can inspect cancellation consequences, resolve differences through
merchant corrections or explicit customer revision approval, approve an immutable
agreement version, and complete PayPal sandbox checkout. Store approved version
references alongside provider identifiers and transaction state. Booking changes
after approval require renewed review before the backend permits capture.

The brief requires meaningful AI and PayPal integration in the eventual prototype.
AI extracts structured conditions, compares meaning, flags ambiguity, and explains
differences with evidence. Application code validates data, calculates money and
deadlines, versions approvals, and controls payments. Google Gemini is selected
for draft extraction through the official Google GenAI Python SDK, with Pydantic
validation. Do not claim validated customer demand or reduced disputes.

## Architecture

- Modular monolith: React/TypeScript/Vite/Tailwind frontend, one Python/FastAPI API,
  one PostgreSQL database. Synchronous SQLAlchemy 2.0 and psycopg 3 sessions;
  Alembic migrations, Pydantic validation, HTTPX external API calls, PyMuPDF PDF
  text extraction. No queues, microservices, Redis, Celery, vector DB, or agent
  framework.
- `backend/app/core/` owns settings and database access. `health/`, `bookings/`,
  `evidence/`, and `drafts/` are implemented. Add `agreements/`, `comparisons/`,
  `cancellations/`, and `payments/` as their milestones begin. Feature modules
  should contain routers, schemas, services, and persistence models only as needed.
- Browser calls relative `/api` URLs. Vite proxies them locally. A future
  production reverse proxy must route `/api` to FastAPI and serve frontend assets;
  Vite's development proxy is not production infrastructure.
- No schema creation during API startup. Baseline tracks Alembic versions;
  migration `0002_bookings_evidence` adds bookings, evidence sources, and PDF pages;
  `0003_immutable_drafts` adds draft versions and their immutability trigger.
- Liveness checks API process only; readiness executes PostgreSQL `SELECT 1`.
  Readiness does not assert schema currency, PayPal availability, or AI readiness.

## Stages and exit checks

1. **Scaffold (complete).** Guardrails, this plan, locked dependencies,
   environment examples, local database Compose service, runnable frontend/API,
   typed health responses, synchronous session infrastructure, Alembic baseline.
   Exit: TypeScript/build; API health tests including database failure and safe
   error response; Python lint/format; Compose validation; Alembic offline SQL.
   Apply migration and verify readiness against real PostgreSQL when available.
2. **Persisted bookings and evidence intake (complete).** Add bookings,
   pasted quotation/message text, and text-based PDF uploads with source type,
   original text, filenames and one-based PDF page provenance. Enforce bounded
   requests, file sizes, page counts and extracted text lengths. No OCR or AI.
   Exit: migration applied on PostgreSQL, isolated PostgreSQL persistence/source
   retrieval tests and upload rejection tests. See
   [backend verification guide](backend-evidence.md) for API contracts and Swagger.
   User narrowed this milestone to intake; agreement versions are deferred.
   This remains an unauthenticated local prototype bound to loopback, not a shared
   customer/merchant service. No owner identity or access guarantees are invented.
   Define ownership and enforce customer/merchant authorization before shared use.
3. **AI draft extraction (implemented; manual provider verification pending).**
   Provider migrated to Google GenAI SDK + Gemini structured output. Default
   `gemini-3.5-flash-lite`, configurable through backend `GEMINI_MODEL`; secret
   `GEMINI_API_KEY`. Official pricing and model docs verify free-tier text usage
   and structured outputs. Keep the user's project on Free Tier; no billing
   upgrade or provider/model fallback. Gemini transport schema uses its documented
   subset; full original Pydantic/domain validation still runs on raw output.
   Extract equipment/quantities, pickup/return with explicit timezone, currency,
   Decimal amounts, deposit/cancellation conditions and included items. Validate
   booking-scoped exact citations and PDF pages; preserve unknowns/conflicts.
   Each request creates an immutable unapproved draft with input IDs, source
   fingerprints, model/SDK/prompt metadata and server-assigned version. No AI call
   holds a database transaction. Booking row locks serialize version allocation.
   Exit: isolated PostgreSQL tests with mocked providers, immutability, concurrency,
   schema/citation failures, missing terms, conflicting sources and safe provider
   errors. No live provider call is authorized in this migration session.
   See [manual extraction guide](backend-drafts.md).
   **Deferred:** ownership/customer/merchant authorization before shared use;
   final-booking comparison, agreement approval/review state, consequence
   calculations, checkout and frontend screens. Comparison needs its own stage
   and examples for equivalent wording and missing battery/microphone conditions.
4. **Cancellation and resolution.** Calculate only from evidenced policy using
   Python Decimal and timezone-aware datetime; make currency, timing, rounding,
   and missing rules explicit. Merchant correction or explicit customer revision
   creates a new immutable version. Exit: deadline boundaries, incomplete policy,
   amount precision, and concurrent revisions.
5. **Approval and backend payment eligibility.** Persist explicit approval tied
   to an exact immutable agreement version. Block missing approval or blocking
   differences. Any booking revision invalidates eligibility. Exit: stale approval,
   cross-booking access, concurrent edit/approval, server-derived amount/currency.
6. **PayPal sandbox checkout and reconciliation.** Use JS SDK and Orders API v2
   with test buyer/merchant accounts. Backend creates, retrieves, and captures;
   recheck eligibility before both order creation and capture. Use `custom_id`
   for internal references, supported `PayPal-Request-Id` idempotency, durable
   payment attempts, and verified webhooks. Plan concurrency so booking revisions
   cannot race capture authorization; reconcile ambiguous network results instead
   of blindly retrying. Payment success requires verified completed capture,
   provider IDs, amount/currency and agreement association. Handle non-completed
   states explicitly. Exit: actual sandbox flow, decline/cancel, stale agreement,
   retry, duplicate webhook, forged webhook, amount mismatch, and timeout recovery.

Run focused checks after each stage; update this plan with observed results and
remaining limits. Do not replace actual sandbox verification with mocked success.

## Runtime and official documentation notes

Observed host: Node 20.20.2, npm 11.16.0, Python 3.14.1, uv 0.11.8,
Docker 27.4.0 and Compose 2.31.0. `psql` is absent and Docker daemon was stopped.
Use Python 3.14.1 for this scaffold. Vite 7 is deliberately bounded to its supported
major; SQLAlchemy stays on stable 2.0 APIs. Lockfiles record actual resolved
dependencies. Node's installed version meets Vite's technical floor; use a
supported Node LTS when preparing deployment.

Official documentation checked on 2026-10-29:

- [Vite guide](https://vite.dev/guide/) and
  [Vite 7 runtime floor](https://vite.dev/blog/announcing-vite7): Node 20.19+ or 22.12+.
- [Tailwind with Vite](https://tailwindcss.com/docs/installation/using-vite):
  Vite plugin plus CSS import, without a legacy Tailwind configuration.
- [FastAPI database tutorial](https://fastapi.tiangolo.com/tutorial/sql-databases/):
  request-scoped sessions. This project uses SQLAlchemy directly, not SQLModel.
- [SQLAlchemy psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg):
  explicit `postgresql+psycopg` URL with synchronous `create_engine`.
- [PyMuPDF installation](https://pymupdf.readthedocs.io/en/latest/installation.html):
  runtime/wheel compatibility; local installation successfully read the brief.

Gemini free-tier model and structured-output references are recorded in
[draft documentation](backend-drafts.md). Consult current PayPal documentation
when implementing payments. No checkout simulation or successful payment exists.

## Scaffold verification results

Verified on 2026-10-29:

- `npm ci` completed with Node 20.20.2; `npm run build` passed strict TypeScript
  checking and Vite 7.3.7 production build. Shell runtime selection initially
  selected Node 18; explicit Node 20 PATH fixed installation/build. Root `.nvmrc`
  and README document runtime selection.
- Python 3.14.1 dependency lock and installation completed, including native
  psycopg, Pydantic, SQLAlchemy and PyMuPDF wheels.
- `python -m pytest`: 3 passed. Installed Starlette emits one deprecation warning
  about its TestClient HTTPX adapter; tests pass with the requested HTTPX stack.
- `ruff check .` and `ruff format --check .`: passed.
- `alembic upgrade head --sql`: passed; `path_separator = os` handles the space in
  the workspace path. Baseline emits Alembic version tracking only.
- `docker compose config --quiet`: passed.
- Real local HTTP checks: frontend HTML 200, API liveness 200, proxied liveness
  200, direct and proxied readiness 503 with `Database unavailable` and no
  connection details. Temporary verification servers stopped afterward.
- Live PostgreSQL readiness success and online migration remain **unverified**:
  Docker daemon is stopped; no `psql` client is installed. The readiness success
  unit test uses a test double. Start Docker or configure existing PostgreSQL,
  then run the README migration and readiness commands.
- No AI or PayPal requests, payment simulations, domain tables, or product flows
  were implemented in this milestone.

## Booking/evidence milestone results

Verified on 2026-10-29 against running PostgreSQL 17:

- Added seven booking/source API operations, metadata pagination and source detail
  with exact pasted text or extracted PDF text and one-based page provenance.
- Added `python-multipart` 0.0.32 to the existing dependency lock; no unrelated
  dependency upgrades. No environment files, credentials, Compose ports or
  frontend files changed. Host remains `5433`; container remains `5432`.
- Applied `alembic upgrade head` to the existing project database;
  `alembic current` reports `0002_bookings_evidence (head)`.
  `alembic check`: `No new upgrade operations detected.` Upgrade only adds tables
  and an index; no existing table, record, service or volume was deleted.
- `python -m pytest -q`: **33 passed** against a fixture-created isolated
  PostgreSQL database, removed after the suite. Tests verify independent-session
  booking/source commits, page retrieval, booking-scoped lookup, text validation,
  malformed UUIDs, missing entities/form fields, invalid file types/signatures,
  corrupt PDFs, password and owner-only encryption, scanned/mixed/blank PDFs,
  upload byte limits, page/text limits, and chunked request body limits.
  Six dependency deprecation warnings remain (Starlette TestClient/PyMuPDF SWIG);
  none represent failed assertions.
- `ruff check .`, `ruff format --check .`, offline migration SQL generation,
  lockfile consistency, Compose validation and Swagger/OpenAPI generation passed.
  Confirmed PDF operation publishes a multipart form with source type and file.
- Local-only unauthenticated API is the explicit boundary. Authorization,
  structured conditions and immutable agreement versions remain next foundation
  work; AI, cancellation, approvals, payments and frontend product screens were
  not implemented. See [Swagger walkthrough](backend-evidence.md).

## AI draft milestone results (historical OpenAI implementation)

Verified on 2026-10-29:

- Implemented `POST/GET /api/bookings/{booking_id}/drafts` and
  `GET /api/bookings/{booking_id}/drafts/{draft_id}`. All successful creations
  persist a fresh immutable, unapproved version. Selected source IDs and exact
  page quotations are validated; source evidence remains unchanged.
- Added official OpenAI SDK 2.54.0 and its five-package dependency resolution
  (SDK plus distro, jiter, sniffio and tqdm). Existing dependency versions stayed
  locked. `OPENAI_API_KEY` and `OPENAI_MODEL` are backend-only settings; only the
  placeholder example changed. Actual `.env` files and port configuration did not.
- Original implementation selected configurable `gpt-6-luna` with Responses and
  structured outputs. This choice has been superseded by the Gemini migration.
- Applied `alembic upgrade head` to existing project PostgreSQL without modifying
  evidence. `alembic current`: `0003_immutable_drafts (head)`.
  `alembic check`: `No new upgrade operations detected.` Upgrade adds only the
  draft table, index, immutability function and trigger; no data/volumes removed.
- `python -m pytest -q`: **77 passed**, six existing dependency deprecation
  warnings. New tests cover citations, literal support, unknowns, conflicting
  sources/order independence, source ownership, PDF pages, Decimal validation,
  configuration errors, sanitized provider failures, committed immutable drafts,
  concurrency and an actual SDK parse over HTTPX MockTransport. PostgreSQL tests
  use the fixture-created isolated database; no test calls the paid provider.
- `ruff check .`, `ruff format --check .` (32 Python files), offline migration SQL,
  strict Structured Outputs schema generation, Swagger/OpenAPI generation,
  lockfile consistency and Compose validation passed. Host `5433` and container
  `5432` remain intact. No frontend files changed.
- **No paid OpenAI API calls made.** Live account/model availability and model
  extraction quality remain unverified, intentionally. Missing credentials return
  a clear 503; normal use never falls back to fake extraction. Follow
  [one manual extraction](backend-drafts.md#one-manual-extraction-in-swagger)
  after configuring credentials locally.

## Gemini provider migration results

Verified on 2026-10-29:

- Replaced the runtime OpenAI adapter/dependency with official Google GenAI Python
  SDK 2.34.0. New drafts use Gemini metadata; historical OpenAI metadata remains
  accepted for retrieval only. No OpenAI integration, model fallback or fabricated
  extraction path remains. Existing endpoints and evidence/domain validators stay
  intact; no database migration, existing-record rewrite, frontend or port change.
- Default `GEMINI_MODEL=gemini-3.5-flash-lite`: current Google pricing lists
  free-tier standard input/output; model/structured-output docs confirm support.
  See [verified model and SDK references](backend-drafts.md#provider-and-model).
  Use the existing Free Tier project without enabling billing. Account access,
  quotas and live quality are not verified by this implementation.
- `GEMINI_API_KEY` is the sole accepted backend extraction credential. Missing
  key/model gives 503. The explicit Developer API/key overrides Google/Vertex SDK
  environment defaults; one total attempt and no tools/paid service options.
  Quota exhaustion gives clear 503; timeouts 504; invalid output/citations 502.
  Errors never expose raw provider messages, secret keys or evidence text.
- Gemini transport schema is derived from the original Pydantic schema, with
  references inlined and nullable primitive type arrays. Unsupported string/regex
  constraints are omitted from transmission only; raw output passes full original
  Pydantic and evidence validation before an immutable draft can be inserted.
- Full regression run: **83 passed**, six existing dependency deprecation
  warnings. Tests include offline Google SDK serialization, explicit key/model
  selection, no retry/fallback on failures, invalid output, domain/citation and
  immutability regression, and retrieval of a legacy OpenAI draft. Tests use a
  uniquely named isolated PostgreSQL database and never load actual `.env` files.
- Final focused provider/compatibility run after metadata handling adjustment:
  **17 passed**, 33 draft tests deselected. OpenAPI generation and absence of the
  OpenAI SDK also verified without loading credentials.
- `ruff check .`, `ruff format --check .` (33 files), frozen dependency sync and
  offline lockfile consistency passed. Dependencies installed on Python 3.14.1;
  cryptography was successfully built from source on this Intel macOS host.
- **No live API calls made; actual secrets were not read or printed.** Actual
  environment files remain untouched; configure the two Gemini variables locally.
  Host PostgreSQL port remains `5433`, container port `5432`; project data and
  volumes remain untouched. No automated test substitutes fake results in normal
  application use.

## Safe Gemini failure diagnostics

- Added warning event `gemini_failure` under Uvicorn's existing stderr logger.
  Fields: exception type, provider HTTP status, canonical error code, sanitized
  configured model ID, and fixed allowlisted summary. No exception messages,
  payloads, prompts, source text, credential URLs, headers, keys or tracebacks are
  logged. Invalid or credential-containing model IDs are redacted.
- Provider, transport and Pydantic failures retain their original exception as
  internal `__cause__`; API status/error bodies remain unchanged. Logical blocked
  or incomplete responses also emit a safe warning. No validation, model/provider,
  database, environment or dependency changes.
- New mocked diagnostic tests cover redaction, safe structured fields, original
  exception retention and transport/provider/validation status handling. No live
  calls or developer secret-file reads. See the
  [one-request reproduction instructions](backend-drafts.md#find-a-sanitized-gemini-failure-diagnostic).
- Verification: 13 diagnostic tests and 15 focused existing provider regressions
  passed (28 total); `ruff check .` and `ruff format --check .` passed. Existing
  six dependency deprecation warnings remain. Regression persistence tests used
  only the fixture-created isolated PostgreSQL database; project records untouched.

## Gemini 400 request compatibility investigation

- Inspected installed SDK 2.34.0, generated static JSON Schema and actual request
  serialization through offline HTTPX transport against current official Google
  model-specific migration, GenerateContent and structured-output documentation.
- Confirmed request incompatibility: explicit `candidateCount: 1` is unsupported
  for Gemini 3.x according to Google's migration guidance, applied to 3.5 Flash-Lite.
  Removed that setting. No model, SDK version, billing, dependency or schema changes.
  Request contract regression now rejects candidateCount in the mock transport
  and checks the entire generation-setting key set for default and configured models.
- Decimal strings, inline nested schemas, primitive nullable type arrays, required
  fields, numeric/array bounds and JSON MIME output match documented constructs.
  No extra schema defect confirmed. All application-side schema/evidence checks,
  immutable drafts, exception chaining, records and port configuration preserved.
- Safe diagnostics now include bounded `parameter_paths` from typed Google RPC
  BadRequest details, matched to static request/schema allowlists. No free-text
  message parsing, field descriptions, values, unknown suffixes, secrets, URLs,
  evidence or raw bodies are logged. Mock SDK 400 tests cover actual detail decoding.
- No live requests or developer secret-file reads. Exact live rejection is not
  independently reproduced; the unsupported parameter is confirmed from docs,
  but a sole root cause cannot be asserted from the original generic 400 alone.
  See [audit and next diagnostic step](backend-drafts.md#investigation-of-400-invalid_argument).
- Verification: **73 focused draft/provider/diagnostic tests passed** against
  isolated PostgreSQL and offline mocked Gemini responses; six pre-existing
  dependency warnings. Lint, formatting and offline lockfile consistency passed.

## Standalone manual Gemini probes

- Added `backend/scripts/gemini_probe.py` and a script-local explanation redactor.
  Manual command reads existing backend settings only when invoked, performs
  minimal text, tiny schema and application-schema/synthetic quotation probes in
  order, and stops at first failure. No application files, model/settings,
  dependencies, billing, database records or validation behavior changed.
- Emits only probe/result/sanitized diagnostics JSON. Retains safe provider wording
  about parameter/schema rejection; excludes credentials, headers, URLs, known
  input/output content, raw bodies and unrecognized nontechnical prose. SDK logs
  and warnings are suppressed during manual execution. No real source evidence
  is used and no extracted draft is persisted.
- No live probes executed or developer credentials read. Tests use fake settings,
  mocked clients and the real SDK via offline HTTPX MockTransport. See
  [single-command usage](gemini-probes.md).
- Verification: **18 mocked/offline tests passed**; lint and formatting passed.
  Tested first failure at each stage, useful provider explanation preservation,
  key/header/URL/document redaction, SDK log suppression, actual SDK request
  serialization, local validation failures and missing credentials. Module import
  and the uv directory/module command path were verified without loading settings
  or executing any live probe. Six existing dependency warnings remain.

## Compact provider contract and verified live extraction — 2026-10-30

- User confirmed minimal text/tiny JSON probes worked while expanded extraction
  schema returned 400. Inspected actual SDK serialization and replaced the domain
  schema expansion with a **610-byte flat terms contract**: primitive string
  fields, explicit known/unknown/conflict states, decimal-string money and exact
  source/page quotations. No model, provider, billing, SDK or database changes.
- Python validates the wire DTO and converts to existing domain models. Missing
  categories, extra/unused fields, fabricated unknowns, invalid quantities/pages,
  floats and invalid money are rejected. Original Pydantic, ownership, literal
  financial support, exact quotation and PDF page validation remain mandatory.
  Existing API response shapes, records and immutable version storage are intact.
- **Live verification succeeded on request 1 of 5 authorized requests.** Used only
  newly created synthetic evidence and the existing Free Tier backend credentials,
  without printing secrets or enabling retries/billing. Actual application POST
  returned 201, draft GET returned 200, and an independent PostgreSQL Session
  confirmed matching committed content and unapproved state.
- Verification booking: `1997b186-0efa-4803-a742-5e69664d3c71`;
  source: `3a9a7773-3c64-44cc-9e6a-4e5e749b72e3`;
  draft: `2b21e6bd-4f2e-4d9d-b6cb-2e2c7aa08e91`.
  Synthetic records retained for inspection; existing records and port 5433 untouched.
- The expanded provider contract is isolated as the failing stage; the compact
  contract is confirmed accepted. Google's exact rejecting keyword/complexity
  limit remains unknown. No speculative model change or automatic fallback needed.
- Focused verification: **61 compact adapter/diagnostic/manual-probe tests + 27
  affected provider/persistence/ownership/citation tests passed (88 total)**.
  Mocked tests use isolated PostgreSQL/offline SDK transports. Lint and formatting
  passed; six pre-existing dependency warnings remain. No broad suite rerun.
- Existing manual probe now decodes the same compact contract as production.
  Only user action remaining: restart a backend process still running old code.

## Customer review and confirmation — 2026-10-30

- Added immutable `agreement_versions` separate from original AI drafts, and
  append-only `agreement_confirmations` separate from agreement content. Source
  entries retain original citations and pass unchanged evidence validation;
  customer corrections have empty citations, explicit reasons and customer-entered
  provenance. Full parent/version, actor-label and change audit trail retained.
- Added six review API operations. Import only the latest booking draft; duplicate
  import cannot reset existing corrections. Corrections replace explicit named
  categories, creating a new version; every current source must be acknowledged.
  Confirmation requires strict true acknowledgement, exact latest version and
  server fingerprint, complete required conditions and no represented conflicts.
- Fingerprints bind version identity, content, lineage, audit reasons/actor and
  evidence snapshots. Added evidence or a newer AI/agreement version immediately
  makes the old confirmation non-current without deleting history. Evidence
  intake, AI draft final publication, review mutations and confirmation serialize
  on the booking row. Concurrent stale revisions fail; concurrent confirmation
  before a later change remains historical but cannot satisfy the current guard.
- Added `require_current_confirmation` as a locked review prerequisite for future
  payment work. It is not payment eligibility/authorization; comparison and later
  provider checks remain deferred. Authentication, frontend, consequence
  calculations and PayPal are not implemented. Labels/attestation are provisional.
- Focused verification: **72 passed** (40 customer-review tests, 30 evidence-intake
  checks and two affected draft preservation/concurrency checks), six existing
  dependency warnings. No broad test rerun. Tests use isolated PostgreSQL and
  block or mock all AI calls. Lint/format and Swagger generation passed; additive
  migration SQL verified offline without loading credentials.
- Migration `0004_customer_review` adds only review tables/indexes and immutability
  triggers. Original data, draft endpoints, Gemini validation, port 5433, secrets
  and billing remain unchanged. No AI calls made.
- Applied migration to the configured project database: `alembic current` reports
  `0004_customer_review (head)`; `alembic check` reports
  `No new upgrade operations detected.` Existing tables and rows were not reset.
- See [exact Swagger walkthrough](customer-review.md).

## Actual PDF booking extraction correction — 2026-10-30

- Reproduced `ai_invalid_output` on booking
  `19907e60-025b-4d47-93cb-18ced6b6c984` with its selected stored PDF source.
  JSON and wire field validation passed. Flat conversion rejected explicit
  number-word quantities. Offline replay also identified paraphrased deposit and
  cancellation values rejected by unchanged literal evidence validation.
- Normalize only explicit number words one through twenty, already supported by
  the domain evidence validator, into integer quantities. Missing counts remain
  unknown; source/page/quotation and financial validation remains unchanged.
  Prompt `rental-draft-gemini-flat-v3` clarifies digit output and requires verbatim
  policy values contained within their exact cited quotations.
- Second of three authorized live requests succeeded through the actual FastAPI
  extraction endpoint with the original booking/source: POST 201, persisted GET
  200, unapproved draft `d4987f32-2d7a-400c-93e6-d26610159e25`. Two total live
  requests; no retries, model/provider/billing changes or original evidence edits.
  Continue customer review using this draft without extracting again.
- Focused verification: 38 mocked compact-conversion, PDF persistence, SDK request,
  citation/page and unsupported-value tests passed; lint and formatting passed.
  Six existing dependency warnings remain. Temporary private provider output was
  removed after inspection; no document contents or credentials were printed.

## Inclusive total amount classification — 2026-10-31

- Added `total_payable` to the shared validated money kind, inherited by
  source-supported extraction and customer amount revisions. Compact conversion
  retains it unchanged; prompt v4 distinguishes rental fee/subtotal from the
  inclusive total. USD 120 rental fee, USD 80 deposit and USD 200 total payable
  remain three distinct claims, never summed as USD 400 of charges.
- Review groups conflicts by amount kind, preserves required rental fee and
  currency checks, and does not infer missing totals or component inclusion.
  No saved records rewritten or automatically confirmed; JSON content requires
  no database migration. Existing kinds and immutable history remain readable.
- Focused checks: 73 compact extraction and customer-review tests passed using
  mocked/blocked AI and an isolated PostgreSQL database. Covers conversion,
  source-supported import, explicit revisions, preserved history/unconfirmed
  state, competing payable totals, missing rental fee and currency mismatch.
  Six existing dependency warnings remain. Lint and formatting passed.
- No AI calls, billing, frontend, environment or port changes.

## Customer agreement review frontend — 2026-10-31

- Replaced the health-only frontend with a responsive customer review workspace:
  paginated booking/version/source loading, saved draft import by explicit action,
  original PDF pages/pasted text and exact quotations, readable condition editors,
  category and overall reasons, source acknowledgements, immutable revision saves
  and explicit exact-version confirmation. No model calls on load/edit/import.
- Frontend uses current API contracts and passes expected fingerprints; historical
  versions are read-only. Unsaved edits block confirmation; source/final checkboxes
  reset after version publication. Stale errors retain edits and require refresh.
  Audit/provenance, blockers, loading/errors/success and provisional identity are
  visible. Inclusive totals remain distinct decimal strings, never summed.
- Backend no longer labels different policy clauses inherently conflicting.
  Explicit ambiguity flags and lexical direct opposites with equal scope still
  block; equipment/money/date/currency, evidence and concurrency checks remain.
  No automatic policy consolidation or complete semantic consistency claim.
- Checks: production frontend TypeScript/Vite build passed (Node 22.23.1), focused
  Python lint/format passed, 53 review/policy/conflict tests passed against isolated
  PostgreSQL with AI blocked/mocked; six existing dependency warnings remain.
- Headless Chrome verified existing booking/evidence loading through real FastAPI
  read-only. Synthetic mocked browser mutations verified camera count, separate
  USD 120 rental fee / USD 80 deposit / USD 200 inclusive total, both cancellation
  clauses retained, correction reasons/source IDs, fingerprints, explicit renewed
  confirmation, read-only history and stale rejection preserving edits. Mobile
  390px layout had no horizontal overflow; no browser exceptions or AI requests.
  Real customer records were not revised or confirmed during browser testing.
- No dependencies, migrations, credentials, billing, provider/model, port 5433,
  payments, comparison or consequence-calculator changes. Local URL:
  http://127.0.0.1:5173; backend remains http://127.0.0.1:8000.

## Persisted final-booking comparison and React screen — 2026-10-31

- Added independent immutable merchant booking versions with optimistic latest-ID
  checks and fingerprints/audit. Saving a proposal never overwrites or invalidates
  the confirmed customer baseline. Additive migration `0005_booking_comparison`
  applied; `alembic current` is head and `alembic check` reports no new operations.
- Added deterministic equipment/quantity, included-item, Decimal/kind/currency and
  timezone-aware date comparison. Missing terms remain unknown; inclusive total
  is not added as a charge. Complete identical policy text matches directly;
  changed policy wording uses the existing Gemini integration only on explicit
  Compare, with simple structured output and exact support text from both sides.
- Comparisons bind agreement/proposal IDs and fingerprints plus confirmation and
  model metadata. Booking locks protect save/publication; inference holds no DB
  transaction. Post-inference recheck rejects concurrent edits. Staleness derives
  from changed versions/evidence/confirmation without modifying history.
- React adds a merchant comparison workspace with all requested fields, confirmed
  terms alongside, immutable saved-version/history controls, explicit save/compare,
  errors/loading and version-bound results. Three labelled samples only populate
  fields: same USD 200 total/non-refundable deposit, matching, equivalent wording.
  No automated policy judgment or approval is fabricated by sample loading.
- Full setup, browser steps, API contracts and limitations:
  [booking-comparison.md](booking-comparison.md). No payments, consequence
  calculator, billing, dependency/provider/model, secret or port 5433 changes.
- Final verification: **89 focused backend tests passed** (41 new comparison
  checks plus 48 existing customer-review checks), six pre-existing dependency
  warnings. Changed Python lint/format (10 files) and frontend TypeScript/Vite
  build passed. No broad test rerun or live Gemini call.
- Headless Chrome tested all three samples with synthetic API fixtures: loading
  creates no writes, save does not compare, fingerprints are submitted exactly,
  matching/equivalent results display, same-total deposit mismatch remains clear,
  new proposal stales old comparison and both supporting policy texts display.
  At 390px no horizontal overflow; no runtime exceptions or extraction/approval
  requests. Browser mutations used mocks; real persistence is tested on isolated
  PostgreSQL. Real customer records/confirmation were not altered.

## Narrow reviewed cancellation preview — 2026-10-31

- Added immutable structured cancellation rule versions and separate human
  approvals, bound to exact agreement/proposal source fingerprints. Manual entry
  and explicit Gemini proposal are separate actions; neither approves rules.
  Approval requires exact rule fingerprint, explicit complete-policy and
  no-unresolved-contradiction attestations, and an audit note. Source/evidence/
  confirmation or newer rule changes make old approvals non-current without
  rewriting records. AI proposals recheck source/rule state after inference.
- Scope: one positive cutoff in hours, explicit boundary inclusion, separate
  rental-fee and deposit amount/percentage refunds, USD cents, pre-pickup only.
  Python uses Decimal and aware instants/exact elapsed microseconds. Total payable
  equals the two components and is never added as a charge. Missing, unsupported,
  inconsistent or contradictory conditions yield needs clarification with no
  definite preview. Side-by-side is atomic and needs both reviewed complete rules.
- Source quote/cutoff/boundary checks and cross-policy non-refundable versus
  deposit/full-refund flags block contradictions. Human review remains required
  for all clauses and exceptions; no claim of complete semantic policy analysis.
  AI shares the existing official SDK, settings, transport/errors, one attempt,
  no fallback and safe diagnostics. It only proposes rules, never computes money.
- React adds rule review, source text/evidence quotations, manual/form-only example,
  explicit Gemini proposal, save/confirm, cancellation date/time and single/paired
  previews with refund, retained amount, applied clause and source version. Loading
  and editing never call AI. Existing records/confirmation and port 5433 preserved.
- Corrected non-refundable sample now consistently retains deposit in both
  cancellation bands. Separate contradictory sample explicitly promises conflicting
  refunds for clarification tests. Saved merchant proposals are never rewritten.
- Additive migration `0006_cancellation_rules` applied; current=head and Alembic
  check reports no new operations. Original tables/rows/confirmation untouched.
- Browser/setup/API instructions: [cancellation-preview.md](cancellation-preview.md).
  No live AI calls, billing changes, PayPal or actual cancellation operation.
- Final checks: **76 tests passed** (35 cancellation checks plus 41 shared
  comparison/provider regressions) using isolated PostgreSQL and mocked/blocked
  AI; six pre-existing dependency warnings. Changed Python lint/format (11 files)
  and frontend TypeScript/Vite production build passed. No broad test rerun.
- Headless Chrome with synthetic API fixtures verified no load/example mutations,
  source/rule fingerprint submission, explicit review/approval gate, side-by-side
  gate, USD 200/0 at cutoff and USD 80/120 later display, clearing old results on
  time edits, 390px mobile layout, consistent versus contradictory sample loading,
  no auto AI/save actions and no runtime exceptions. Browser writes were mocked;
  real persistence/calculation/immutability were verified on isolated PostgreSQL.

## PayPal sandbox checkout — 2026-10-31

- Inspected confirmation/proposal/comparison/cancellation eligibility. Added a
  backend checkout gate using current agreement confirmation, latest proposal,
  latest exact all-matching comparison, recomputed numeric matches, reviewed
  consistent cancellation rules and a unique explicit positive USD total payable.
  Separate immutable customer checkout approval binds every ID/fingerprint and
  merchant/amount. Browser amounts/payees cannot enter order/capture requests.
- APIMatic official docs confirm Codex support; local Node 22.23.1 and Codex CLI
  0.164.0-alpha.11.1/plugin commands satisfy documented prerequisites. Plugin was
  not installed, loaded or used. Its documented installer/new-session instructions
  and verified official PayPal references are in [paypal-sandbox.md](paypal-sandbox.md).
- Implemented fixed sandbox HTTPX OAuth + Orders v2, and explicit-loaded sandbox
  JS SDK v6 buyer sessions. No live API/SDK origin, redirect following, proxy
  environment, automatic retries or fabricated fallback. Secret/token backend-only;
  only public client ID is exposed to SDK initialization.
- Durable attempts persist separate stable request keys, precommitted capture
  intent, known provider IDs/status, and append-only events. Capture rechecks
  exact checkout approval and holds the common booking lock across capture and
  authenticated provider verification. Concurrent edits cannot cross this gate.
  Receipt requires exact order/attempt/merchant/amount/currency plus final
  COMPLETED capture, never browser callbacks or SDK completion alone.
- Uncertain outcomes reconcile by GET before any explicit same-key retry; pending
  captures never become paid automatically. Conservative 15-minute local replay
  guard then manual reconciliation; no key rotation/new attempts to bypass unknown
  outcomes. Reconciliation can record a completed historical capture without
  authorizing a new payment after terms change. One payment per booking supported.
- React adds explicit checkout approval, sandbox buyer approval and blocked,
  cancelled, pending, failed, completed and SDK-error states. Resume/cancel and
  reconciliation actions are explicit. Loading page never downloads SDK or makes
  payment/AI calls. Linked receipts retain captured version references.
- Additive migration `0007_paypal_sandbox` applied; standalone Alembic metadata
  registered and check clean (`head`, no new upgrade operations). Existing rows,
  source confirmations, real `.env`, port 5433 and provider/model preserved.
- Verification: **112 tests passed** (36 payment checks + 76 cancellation/shared
  comparison regressions), six pre-existing dependency warnings. Isolated
  PostgreSQL, fully mocked providers/offline HTTPX; all external payment/AI
  transports blocked by default. Includes duplicate/idempotency keys, amount/payee
  verification, uncertain/declined/pending states, stale guards and an actual
  competing database edit blocked during capture. Changed Python lint/format and
  frontend TypeScript/Vite build passed.
- Headless Chrome verified blocked/cancelled/pending/failed/completed/SDK-error
  flows, exact approval fingerprints, no SDK/order calls on load, no order from SDK
  initialization alone, no receipt for non-completed outcomes, linked capture IDs
  on receipt and mobile width. All browser SDK/backend calls mocked with PayPal
  hosts blocked; no runtime exceptions after discarding prior-page error replay.
- **No external PayPal/payment or AI calls made.** No live sandbox capture has been
  verified at implementation time; subsequent user-reported manual success is
  recorded below.
  Webhooks, reversals/refunds/disputes, authentication and live payments deferred.

## Existing sandbox approval failure diagnosis — 2026-10-31

- Read-only inspection of actual booking `19907e60-025b-4d47-93cb-18ced6b6c984`,
  attempt `07040e51-f9f2-4460-ad1a-ed392b0903ae`, order `8KW67820DV915823H`.
  Existing order GET via backend credentials succeeded: PAYER_ACTION_REQUIRED,
  CAPTURE, USD 200, matching payee/attempt/reference, zero captures. Current
  frontend/backend app settings and sandbox origins agree. No order creation,
  capture, buyer approval, AI calls, record changes or secret/token output.
- Official SDK v6 docs confirm `{orderId: string}` promise contract used by current
  React code. Bare-string callback is not the v6 contract. Mocked browser regression
  exercises actual component and confirms PayPal ID rather than local attempt ID.
- User confirmed separate buyer/merchant sandbox accounts both India. Official
  PayPal India help excludes domestic Indian receipts, making this country pair
  a likely blocker. Generic popup has no error/debug ID; actual causal attribution
  remains unverified without a later permitted non-India buyer test/provider trace.
  No confirmed code defect; application behavior and guards left unchanged.
- Added focused tests only: four backend regressions passed on isolated PostgreSQL
  with mocked PayPal, seven browser assertions passed with PayPal hosts blocked,
  lint/format and frontend build passed. No broad suite rerun. See diagnosis in
  [paypal-sandbox.md](paypal-sandbox.md#read-only-diagnosis-of-an-existing-approval-failure--2026-10-31).

## Manual sandbox capture and refresh verification — 2026-10-31

- User reports successful manual sandbox capture and successful refresh-persistence
  verification: completed checkout/receipt remains available after frontend
  refresh. This supersedes the earlier implementation-time manual-verification
  pending status; it does not prove the cause of the historical approval failure.
- Recorded the report in README and the sandbox guide. No new transaction IDs,
  buyer-country changes or additional test outcomes were supplied or inferred.
  Verification is attributed to the user, not a new agent-executed transaction.
- Documentation-only update. Existing records, approvals and guards preserved;
  no order creation, capture, PayPal/reconciliation request or AI call made.
- Webhooks and refund operations remain unimplemented. Automatic post-capture
  reversal/dispute handling, authentication and live payments remain deferred.

## Presentation-only usability cleanup — 2026-11-01

- Kept the requested labels **Your name / reviewer label** and **Save review**,
  including the existing ability to save an explicit review without corrections.
  Shortened screen introductions/actions, moved repeated explanations into
  expandable help, and kept AI-use notices next to explicit AI actions.
- Added collapsed Version details, Source details and Payment details for IDs,
  fingerprints and audit data. Version numbers, dates, filenames, source quotes,
  amounts and statuses stay visible; full technical references remain expandable.
- Added actionable display wording for common review, rule and checkout blockers.
  Relevant field blockers remain inline. Checkout shows Review total, Approve
  checkout and Continue to PayPal as separate steps; sandbox/pending warnings stay
  prominent. No conditions, handlers, request bodies, acknowledgements or backend
  guards were changed. No backend, database or completed-record operations.
- Frontend TypeScript/Vite production build passed. Mocked Chrome verification
  covered all four workspaces, source acknowledgement, save with no corrections,
  exact fingerprint submission, renewed review after saving, separate explicit
  confirmation, unsaved samples, incomplete rule/checkout blockers, collapsed and
  expanded receipt references and 390px mobile layout. No runtime exceptions.
  Existing mocked SDK handoff regression passed after updating button labels.
- All application data and mutations in browser checks were synthetic/mocked;
  PayPal/Google hosts were blocked. No PayPal or AI calls, SDK downloads or access
  to actual completed bookings/receipts occurred. No backend tests rerun for this
  frontend presentation change.

## Booking-to-review browser journey — 2026-11-01

- Added booking creation and a **Sources & draft** workspace using existing API
  endpoints. Customers can save original quotation/message text or text-based
  PDFs, read stored text/page references, explicitly select sources, generate an
  immutable unconfirmed AI draft and open Agreement review. Existing bookings
  and agreement review remain directly accessible.
- Show input limits, progress, configuration/quota/validation errors and explicit
  AI usage notice. Multipart uploads use browser-generated boundaries. Duplicate
  clicks are blocked while requests run; uncertain outcomes require refresh
  before an explicit retry. No extraction on load, upload, selection or refresh;
  no automatic retry, review save, confirmation, checkout or payment action.
- Opening a draft already under review reuses its immutable agreement version;
  newer evidence/drafts retain all existing renewal and stale-version protections.
  New review import requires a provisional customer label and explicit action.
  No backend behavior, migrations, credentials, ports or dependencies changed.
- Verification: frontend TypeScript/Vite build and changed Python test lint/format
  passed; 32 focused PostgreSQL API tests passed (`test_starting_journey.py` and
  `test_bookings_evidence.py`). Provider calls were mocked; six existing dependency
  deprecation warnings remain.
- Headless Chrome exercised actual UI/API on a separate randomly named PostgreSQL
  database with mocked Gemini SDK output: new booking, pasted text/message,
  oversize/unreadable/valid PDFs, original page text, selected-source draft,
  unconfirmed review, unresolved blockers, quota error, manual refresh and review
  reopening. Mobile width and runtime-exception checks passed. Existing mocked
  checkout browser regression passed all seven assertions.
- Browser verification created only one synthetic booking, four sources, one
  draft and one review version, with zero confirmations/receipts. Its test database
  and temporary servers were cleaned up. Actual completed bookings/receipts were
  not accessed or changed; no live AI or PayPal calls. See [starting flow](starting-flow.md).
  Authentication, webhooks and refunds remain unimplemented.

## Included-item review change detection — 2026-11-01

- Investigated form initialization with source-supported batteries quantity 2 and
  microphone quantity 1. The clean mocked opening already showed Saved; the
  reported fresh-open symptom was not reproduced. Confirmed a related root defect:
  event-based dirty flags remained set even after restoring the exact saved values.
- Review now derives changed categories by comparing current and saved terms
  through the same form/claim normalization, excluding UI keys and provenance.
  Included-item explicit-none changes remain tracked. Invalid intermediate edits
  remain dirty; real changes still require nonblank category reasons. Overall
  review reason, source acknowledgements, exact fingerprints and all server-side
  correction/confirmation guards remain unchanged.
- Added `frontend/tests/included-items.browser.mjs`: clean opening, both quantities
  and quotations, normalized/unknown values, untouched save with `changes: []`,
  real edit/revert, blank-reason rejection and complete two-item correction payload.
  The edit/revert assertion failed before the fix and passed afterward. All API
  reads/writes are mocked; no existing records, AI or PayPal calls are involved.
- Frontend TypeScript/Vite build and focused mocked browser regression passed.

## Verified sandbox webhook reconciliation — 2026-11-02

- Added fixed-path sandbox webhook signature postback verification using configured
  backend webhook ID and original PayPal headers/event. Only SUCCESS proceeds;
  no certificate/resource URL fetching, raw payload storage or provider logging.
- Known supported notifications reconcile persisted order IDs under the shared
  booking lock using existing authenticated order/capture checks. Approval events
  never initiate capture or establish payment. Completed remote captures can be
  recorded after browser/process loss without changing historical approvals.
- Added migration `0008_paypal_webhooks`: immutable provider event IDs and canonical
  digests, transactional claim-before-GET deduplication. Failed retrieval/validation
  rolls back claim and returns 503 for redelivery. Concurrent duplicate events,
  stale pending/denied/approval events and identity conflicts handled safely.
  Completed receipts remain immutable and cannot be downgraded by notifications.
- Used installed APIMatic plugin Python workflow/getting-started/error/testing
  guidance; documented missing webhook SDK controller and absent SDK. Retained
  existing synchronous HTTPX adapter and dependencies. Full setup, scope and
  guidance attribution: [paypal-webhooks.md](paypal-webhooks.md).
- Existing actual `.env`, credentials, customer data and development database
  untouched. Migration runs only on isolated test PostgreSQL during verification.
  No external PayPal/Gemini calls, registration, tunnel or real webhook test.
  Refund/reversal/dispute accounting, authentication and live mode remain deferred.
- Final verification: `cd backend && uv run --frozen pytest -q` **336 passed**,
  six existing dependency warnings. `uv run --frozen ruff check .` and
  `uv run --frozen ruff format --check .` passed, 76 Python files formatted.
  First full run exposed an existing starting-flow test assumption that every
  booking fits in the first 100 results; corrected that assertion to paginate,
  then full rerun passed. No booking API behavior changed. No frontend changes
  or build rerun. Real sandbox delivery/provider integration remains untested.

## Restricted local webhook tunnel preparation — 2026-11-02

- Prepared standalone loopback proxy in `backend/scripts/webhook_proxy.py` for
  exact POST `/api/paypal/sandbox/webhook` only, fixed backend upstream, raw body
  and PayPal header preservation, no retries/redirects/access logs. Other paths,
  methods, query strings, trailing slashes and encoded aliases blocked.
- Found ngrok 3.33.1 and Homebrew; cloudflared/Caddy/nginx absent on PATH. Documented
  exact backend/proxy/ngrok start commands, optional cloudflared installation,
  free account/setup requirements and offline deny-route checks in
  [webhook guide](paypal-webhooks.md#prepared-local-https-tunnel-gate--2026-11-02).
- 18 offline proxy tests passed; changed Python lint/format passed. No public
  tunnel, installation, webhook registration, database mutation or provider calls.
  Actual `.env` and tunnel credentials/configuration untouched. Existing checkout,
  approvals, receipts and signature verification unchanged.
- Recorded earlier authorized development migration success: current revision
  `0008_paypal_webhooks (head)`. Public end-to-end sandbox test still pending.

## Read-only sandbox webhook evidence audit — 2026-11-02

- Audited capture `37479790XD8219546` with PostgreSQL REPEATABLE READ / READ ONLY
  SELECTs. Found one completed attempt, one USD 200 receipt and one linked
  PAYMENT.CAPTURE.COMPLETED webhook row. Receipt context matches exact original
  checkout approval. Receipt uniqueness and immutable triggers remain enabled.
- Current handler verifies SUCCESS before inserting event records; persisted row
  supports successful verification/processing through that application path.
  No original verification response is stored; no new provider call was made.
- One receipt remains after user-reported resend. Duplicate deliveries have no
  separate counter; no durable safe per-delivery log was located. Therefore the
  resend's arrival and 200/duplicate response cannot be independently established
  from this audit. Backend/proxy/ngrok output destinations were terminal devices.
- Receipt recorded at 09:47:45.858633 UTC; capture webhook record at
  09:48:09.650249 UTC. This is delivery recording with an existing receipt, not
  demonstrated live browser-interruption recovery. Mocked recovery coverage and
  a real recovery demonstration remain distinct.
- [Evidence and APIMatic's actual contribution](paypal-webhook-verification-2026-11-02.md):
  plugin supplied implementation instructions; BeforePay HTTPX/PayPal REST handle
  verification. No APIMatic SDK/MCP webhook operation used. Documentation only;
  no records changed, tests rerun, provider/payment actions or resend performed.

## User-reported live cancellation rule proposal and previews — 2026-11-02

- User reports successful live Gemini rule proposal, separate explicit human
  approval and manual cancellation previews: exactly 48 hours before pickup
  returns USD 200 refund; one minute later returns USD 80 refund and USD 120
  retained. Exactly-at-cutoff result belongs to the earlier band in this report.
- This is user-reported manual verification, separate from mocked automated
  coverage. No independent reproduction or database inspection was performed;
  no booking/rule/version/model identifiers were supplied or inferred.
- Gemini proposes rules only; Python retains Decimal/timezone-aware calculations.
  Explicit approval, source/version binding and all existing safeguards remain.
  Documentation-only update: no records changed, tests rerun, new AI/PayPal calls
  or payment/refund actions. See [manual verification record](cancellation-preview.md#user-reported-live-proposal-and-manual-preview-verification--2026-11-02).

## Rental-agreement product frontend redesign — 2026-11-02

- Rebuilt booking list and overview around actual saved terms, dates, fee/deposit/
  inclusive total, agreement/comparison/payment status and one next action. Added
  compact desktop workflow rail/mobile navigation, warm flat document surfaces,
  sharp system typography and visible sandbox/provisional-identity context.
- Agreement terms are readable summaries with opt-in section editors. Contextual
  evidence opens a keyboard-accessible drawer with original quotations/PDF pages,
  Escape/focus restoration and full-width mobile presentation. Existing reasons,
  source acknowledgements, separate confirmation and immutable history remain.
- Comparison leads with differences, highlighted wording, both versions, narrowly
  supported deposit amount affected and collapsed matching sections. Merchant
  editing is separate and explicitly a prototype workspace. Samples/save/compare
  remain distinct; no guarantee or equal-total match inference introduced.
- Cancellation starts with instant/timezone and backend refund results; AI/manual
  rule review is focused, name precedes request, exact clauses and attestations
  remain. Paid checkout shows existing receipt/history instead of approval forms.
  All original approval, retry/reconcile, stale-input and backend payment guards
  remain. No backend, database, migration or provider changes.
- Visited forms stay mounted across workspace tabs; leaving booking warns before
  discard. Disabled primary/payment actions explain the missing condition. Human
  dates retain explicit timezones; technical IDs/audit JSON stay in details.
- Frozen npm install and Node 24.2.0 / npm 11.3.0 TypeScript/Vite build passed. Isolated mock browser
  suite passed 83 assertions covering all eight requested states at desktop/mobile,
  intake, provenance, stale rejection and explicit save/confirm/compare/preview/
  checkout actions. Existing included-item (12) and PayPal handoff (7) regressions
  passed. No uncaught browser exceptions; screenshot visual review completed.
- QA config disables environment loading and backend proxy. No existing booking/
  payment records or backend secret files accessed, no Gemini/PayPal calls, SDK
  downloads, deploy/publish or tunnel actions. Actual services/records preserved.
  Backend tests not rerun for frontend-only changes. Details, reproduction and
  remaining in-memory/refresh/list-read/browser limits: [frontend-redesign.md](frontend-redesign.md).

## BeforePay display rename, workspace refinement and sandbox receipt — 2026-11-02

- Display name is now BeforePay with “Know what you’re agreeing to, before you pay.”
  Updated frontend wordmark/footer, HTML title/description, README, guides, demo,
  contributor heading, API documentation title and package description. Retained
  original project/source-brief paths, distribution/health/event/SDK identifiers,
  database/Compose/volume/environment names, invoice prefixes, migration/trigger
  names, stored records and fingerprints. No directory or data rename.
- Refined working layout rather than only increasing width: compact navigation,
  32–48 px desktop gutters, bounded paragraphs/forms, source inbox beside draft,
  terms beside acknowledgements/evidence, differences before merchant editing,
  and calculator result separate from rule workbench. Removed redundant booking
  selector and repeated paid-screen headings while preserving explicit actions,
  approval/reason/acknowledgement/stale/uncertain/unsaved behavior.
- Completed payments use BeforePay's app-issued sandbox receipt: recorded total,
  UTC timestamp, current booking display label, stored receipt/PayPal references,
  exact captured version/approval references, working Copy controls and Print.
  History is outside the document; audit JSON collapsed and excluded from print.
  Existing captured context has no itemised amounts or historical booking-title
  snapshot. No reconstruction from current terms, backfill or invented details.
- Final verification: frontend TypeScript/Vite build passed on Node 24.2.0/npm
  11.3.0. 107 mock journey/receipt assertions passed at 1440×1000 and 390×844,
  including keyboard/focus, responsive columns, exact clipboard values/fallback/
  failure, stale rejection, separate approvals and historical-receipt isolation.
  Existing correction (12) and mocked PayPal SDK (7) regressions passed. Static
  branding/compatibility coverage passed 22 checks. Changed backend metadata-file
  Ruff lint/format passed (2 files); backend functional suite not rerun for display
  metadata. No dependency or lockfile changes.
- Chrome produced a one-page A4 synthetic receipt PDF. Offline PyMuPDF inspection
  verified recorded total/references, no app chrome/history/actions/audit/current
  amount, and white print background; screenshots visually reviewed. Clipboard
  API/permission behavior was mocked to avoid touching user's clipboard. Physical
  printers/other browsers and live providers were not tested.
- QA server disabled env loading/backend proxy; API responses were synthetic and
  provider hosts blocked. No credentials changed, real records queried/altered,
  provider/payment calls, registrations, deployment/publication or tunnel actions.
  Owned QA processes stopped afterward. Details/compatibility limits:
  [beforepay-branding.md](beforepay-branding.md); [demo guide](demo.md).


## BeforePay frontend workspace overhaul — 2026-11-02

Rebuilt shared product styling and every task workspace around explicit ownership,
current stage and next action. Added labelled buyer/merchant prototype view switch,
source/draft sequence, focused agreement review and acknowledgements, differences-first
comparison, separate cancellation calculator/rule review, and amount-led checkout.
Uncertain payment leads with its saved attempt. Preserved the app-issued immutable
sandbox receipt, exact-version safeguards, explicit AI/payment actions and all API
contracts. No backend source, dependency, lockfile, credential or existing record
changes in this stage.

Verification: production build/typecheck; 174 isolated mocked browser assertions
at desktop/tablet/mobile; 12 included-items and 7 sandbox SDK handoff regressions;
static branding coverage; one-page synthetic A4 receipt PDF; 180 backend guard tests
with mocked providers and a randomly named disposable PostgreSQL database. No live
Gemini/PayPal calls. See [full audit and limitations](beforepay-ux-overhaul.md) and
[synthetic screenshot gallery](screenshots/beforepay-ux/index.md).


## Product entry and guided BeforePay workspaces — 2026-11-03

Added a separate product entry with an original explicitly illustrative unchanged-price /
changed-deposit example, direct existing-bookings access and a three-stage explanation.
Reworked all task surfaces with deep-ink navigation, teal actions, distinct AI/review/
blocked states, visible prerequisite progress, direct saved-state actions and retained
Home/Bookings inputs. Merchant form-copy remains explicit and does not establish
merchant agreement. Known cross-task writes show a refresh notice rather than erase
edits. Cancellation foregrounds refund/retained/cutoff results; completed booking context
sits outside the historical capture receipt. No backend/API/dependency/lockfile/record
or credential changes, provider calls, deployment or publishing.

Verification: TypeScript/Vite build; 187 synthetic browser assertions at desktop,
tablet and mobile; 12 included-items and 7 SDK handoff regressions; 24 static brand /
compatibility checks; 182 isolated backend guard tests; backend lint/format; text-token
contrast and one-page A4 print checks. Actual rendered screens visually reviewed and
corrected. See [changes, commands and limitations](product-redesign-2026-11-03.md) and
[synthetic screenshot gallery](screenshots/beforepay-product/index.md).


## BeforePay alignment and grouping — 2026-11-03

Refined all task layouts, compacted agreement summaries while preserving all eight
editors and source acknowledgements, and introduced shared semantic booking/payment
history columns. Preserved explicit actions and all backend/version/payment guards.
Verified build/typecheck, 107 alignment assertions, 187 journey assertions, 12 item
and 7 mocked SDK regressions, responsive screenshots and one-page receipt printing.
No backend/contracts/records/dependencies/credentials/provider calls changed. See
[refinement report](alignment-refinement-2026-11-03.md) and
[before/after gallery](screenshots/beforepay-alignment/index.md).


## Buyer and Merchant prototype workspaces — stage 1, 2026-11-03

Separate entry routes, task navigation and overviews now share the existing booking
and version records. Merchant view reuses proposal editing and proposal-rule review,
adds read-only buyer reference and recorded payment status, and hands review/receipt
back to Buyer view. Switching never mutates data; mounted buyer/proposal/rule forms
retain unsaved inputs. Existing API contracts, explicit actions, version guards and
backend payment protections remain unchanged. No authentication, permissions,
migrations, backend/dependency/environment/record changes or provider calls.

Verified build/typecheck, 108 workspace checks, 187 existing journey checks, 107
alignment checks, 12 item and 7 mocked SDK checks, 26 branding checks and offline
one-page receipt print inspection. No backend/database tests run for this stage.
See [stage guide, verification and authentication boundary](buyer-merchant-workspaces.md).
Authentication is deferred pending user review of this completed frontend stage.


## Local demo login and role dashboards — 2026-11-03

Added a single accessible Buyer/Merchant demo-entry modal, minimal public top bar,
explicit public demo credentials, local-only validation and role-only tab identity.
Distinct Buyer review/payment and Merchant proposal/policy dashboards share the
existing booking records. Sidebar role switching uses the same modal; sign-out
warns before discarding mounted work and clears only the demo role. No backend
authentication, permissions, schemas, records, credentials or providers changed.

Verified build/typecheck, 88 demo-entry checks plus 421 existing browser regressions,
27 branding checks, desktop/tablet/mobile captures and offline one-page receipt
printing. All APIs/providers mocked. No backend/database tests run for this stage.
See [privacy boundary, journeys and checks](demo-login.md) and
[screenshot gallery](screenshots/beforepay-demo-entry/index.md). Real backend
authentication remains separate and unimplemented.


## Buyer-first booking creation — 2026-11-03

Unified landing, dashboard, empty-state and direct creation routes through Buyer
demo entry. Merchants explicitly switch before creation; success selects the
returned booking and opens Sources & draft with next-step guidance. Corrected
shared-list loading across role/route transitions, retained the in-flight submit
guard and required explicit list refresh after failed/unknown creation outcomes.
No backend, records, credentials, migrations or provider calls changed.

Verified build/typecheck, 60 focused creation checks plus 509 existing browser
regressions, 28 branding checks and responsive captures. APIs/providers mocked.
See [flow and limits](booking-entry.md) and
[screenshots](screenshots/beforepay-booking-entry/index.md). Demo login remains
unrelated to backend authentication or access control.


## Advisory clarification suggestions — first increment, 2026-11-03

Added explicit Buyer discrepancy suggestions, scoped Gemini context, complete exact
saved-term references, source provenance, strict structured validation and a clear
insufficient-information result. New append-only suggestion records bind exact
comparison/agreement/proposal/confirmation inputs. Booking-lock checks repeat after
inference; stale/superseded history cannot be labelled current. No reply, resolution,
approval or payment capability added. Existing guards/records remain unchanged.

Migration 0009 is included and tested only in disposable PostgreSQL; development
database migration remains a local rollout step. No secret files or live providers
accessed. Verified 379 backend tests (25 new), 605 browser assertions (36 new),
frontend build/typecheck, backend lint/format and 29 branding checks. See
[provider-free UI/API commands, contract and limits](clarification-suggestions.md)
and [synthetic captures](screenshots/beforepay-clarifications/index.md).


## Development migration 0009 applied — 2026-11-03

Applied `cd backend && uv run --frozen alembic upgrade head` on explicit request.
Current revision and expected head both equal 0009_clarification_suggestions.
Read-only before/after fingerprints and counts match across all 15 pre-existing
tables (4 bookings, 3 payment attempts, 2 receipts among protected records).
New suggestion table is empty and immutable trigger enabled. Backend OpenAPI
already contains both routes; no restart needed. No test records, credentials
changes or Gemini/PayPal calls. See [rollout evidence](clarification-suggestions.md#development-rollout-applied--2026-11-03).

## Provisional merchant replies — 2026-11-03

Added Merchant Clarification replies task with both saved supporting terms and
source evidence, explicit merchant label/response entry, Buyer read-only refreshed
history and existing versioned proposal-editor handoff. Statements are append-only,
bound to exact suggestion/comparison/proposal versions, and labelled **Merchant
response—not verified resolution**. Booking-lock version checks reject stale POSTs;
history computes stale context without rewriting records. Replies cannot change
terms, resolve differences, approve anything or affect checkout eligibility.
Navigation retains unsaved drafts; errors retain fields and never retry automatically.

Additive migration 0010 is tested only in disposable PostgreSQL and remains
unapplied to development. No credentials, development records or provider calls
used. See [contracts, rollout limits and precise mocked verification](merchant-replies.md).

## Development migration 0010 applied — 2026-11-04

On explicit authorization, ran `cd backend && uv run --frozen alembic upgrade head`.
Current revision and repository head both report 0010_clarification_replies.
Read-only before/after counts and SHA-256 fingerprints match for all 16 pre-existing
tables, including 4 bookings, 1 suggestion, 3 payment attempts and 2 receipts.
New reply table is empty with its immutable trigger enabled. Running backend OpenAPI
already exposes inbox GET and reply GET/POST; no restart needed or performed.
No business/test records, credential changes or Gemini/PayPal calls. See
[rollout evidence](merchant-replies.md#authorized-development-rollout--2026-11-04).

## User-reported manual clarification/reply workflow — 2026-11-04

Recorded the user's report: live clarification displayed exact supporting terms;
merchant reply appeared for the buyer without unblocking checkout; a corrected
proposal made the old context stale; a fresh comparison now matches. These are
manual user observations, not independently audited evidence or additional mocked
test passes. Matching follows a proposal correction and fresh comparison, not reply-
driven resolution; no approval or payment outcome is inferred. Documentation only:
no new AI/PayPal calls, application-record changes or test reruns. See
[manual report and limits](merchant-replies.md#user-reported-manual-verification--reported-2026-11-04).

## Explicit correction review history — 2026-11-04

Added Buyer Review correction and Record correction reviewed, combining original
discrepancy/support, selected saved merchant reply, corrected proposal and fresh
matching comparison. Backend booking-lock checks require the same booking and
unchanged buyer baseline/confirmation, a newer proposal with changed affected terms,
and complete current matching comparison coverage. Exact references/fingerprints
and reviewer label/note form append-only history; stale/unrelated/ambiguous bindings
reject. Identical current retries share one record; stale retries and changed
statements cannot overwrite it. Both workspaces retain historical snapshots and
compute outdated status from corrected references. Review never changes checkout
eligibility, policy approvals, terms or payment state. No providers called.

Migration 0011_correction_reviews is tested only in disposable PostgreSQL and left
unapplied to development. No existing records or credentials accessed or changed.
See [guard details, setup and exact mocked UI/API steps](clarification-corrections.md).

## Development migration 0011 applied — 2026-11-04

On explicit authorization, ran `cd backend && uv run --frozen alembic upgrade head`.
Current revision and repository head both report 0011_correction_reviews. Read-only
before/after counts and SHA-256 fingerprints match across all 17 pre-existing
tables, including 4 bookings, 1 suggestion, 1 reply, 3 payment attempts and 2 receipts.
New correction-review table is empty; eight validated foreign keys, unique review
context, provisional check and enabled immutable trigger/function verified through
catalog reads. No development mutations were attempted to exercise the trigger.
Running backend OpenAPI already exposes correction GET and review GET/POST routes;
no restart needed or performed. No records created, credential changes, provider
calls or test reruns. See [rollout evidence](clarification-corrections.md#authorized-development-rollout--2026-11-04).

## User-reported manual correction review — 2026-11-04

Recorded the user's report that correction review saved against the corrected
proposal and fresh comparison, persisted after refresh, and appeared in both Buyer
and Merchant workspaces. Recording it did not grant checkout approval. These are
manual user observations, not an independent record audit or additional mocked
test passes; no approval, identity or payment outcome is inferred. Documentation
only: no application-record changes, test reruns or Gemini/PayPal calls. See
[manual correction-review report and limits](clarification-corrections.md#user-reported-manual-correction-review--reported-2026-11-04).

## Merchant deposit/cancellation consistency — 2026-11-04

Added explicit Check policy consistency in both cancellation workspaces. Reused
Gemini policy transport/limits with complete saved merchant clauses, untrusted-data
prompting, structured findings and exact full-clause reference validation. Missing
or ambiguous input declines locally without inference. Append-only results bind
the latest proposal fingerprint; booking-lock checks repeat after inference, and
edits make history stale. Current conflict/uncertainty findings feed existing rule
read/confirmation, refund preview and checkout guards; later clean reruns cannot
erase an unresolved finding for the same proposal. No check or clean result grants
approval, precedence, calculated amounts or eligibility. Conservative existing
checks, immutable receipts and historical capture reconciliation remain intact.

Migration 0012_policy_consistency is tested only in disposable PostgreSQL and left
unapplied to development. No existing records, credentials or live provider calls
used. See [boundaries and precise mocked UI/API verification](policy-consistency.md).

## Development migration 0012 applied — 2026-11-04

On explicit authorization, ran `cd backend && uv run --frozen alembic upgrade head`.
Current revision and repository head both report 0012_policy_consistency. All 18
pre-existing application-table counts and SHA-256 row fingerprints match before/
after. New policy-consistency table is empty; expected columns/JSONB/nullability,
primary key, two validated foreign keys, indexes and enabled UPDATE/DELETE rejection
trigger/function verified read-only. No mutation was attempted to test protections
in development. Local backend OpenAPI already exposes check/history GET/POST and
state GET; no restart needed or performed. No test records, credential changes,
provider calls or test reruns. See [full rollout evidence](policy-consistency.md#authorized-development-rollout--2026-11-04).

## Buyer/Merchant themes and readable workspace layout — 2026-11-04

Refined the shared frontend with teal Buyer and indigo/slate Merchant tokens,
explicit role text, coordinated navigation/controls/surfaces and unchanged semantic
status colours. Desktop rails now have compact spacing and bottom identity controls
outside a scrollable navigation region. Tablet/mobile navigation scrolls with the
document; the measured sticky header remains role-labelled. Increased prose, labels
and controls selectively, adjusted related columns and audited long/empty/blocked,
comparison, cancellation, checkout, receipt and history layouts through isolated
rendered fixtures. Kept all stateful forms/actions and backend contracts untouched.

No booking records, migrations, credentials, backend tests or Gemini/PayPal calls.
The pending policy-consistency test/action was explicitly excluded. See
[scope, audit and provider-free reproduction](workspace-themes.md).

## User-reported live policy-consistency verification — 2026-11-04

User reported that a conflicting proposal returned “Potential contradiction” with
exact deposit/cancellation support and the corresponding checkout blocker. A
corrected new proposal returned “No contradiction found”; policy-consistency
blockers cleared while stale-comparison and rule-approval blockers remained.
These are manual, user-reported observations, separate from prior mocked tests;
not independently reproduced or audited. Clean policy findings grant no approval
or payment eligibility by themselves. Documentation only: no record/credential
changes, test reruns or Gemini/PayPal calls. See
[observations and evidence limits](policy-consistency.md#user-reported-live-verification--2026-11-04).

## Shared blocker navigation — 2026-11-04

Buyer/Merchant overviews, cancellation and checkout now share exact backend-code
explanations, saved-version labels and destinations. Policy blockers open refreshed
findings; comparison blockers open Buyer comparison; rule blockers select the
appropriate agreement/Merchant rule source. Cross-role links explicitly use the demo
modal. Dirty inputs are retained or require a discard warning; unknown/missing-source
bindings receive no guessed link. Backend guards and approvals remain unchanged.
Corrected the comparison guide's obsolete merchant-replies deferral. Added a
fresh-tab runner for every existing browser feature suite and a connected synthetic
clarification/reply/correction/comparison/rule/checkout-approval journey. See
[behaviour, limits and exact offline commands](blocker-navigation.md).

## Synthetic policy evaluation preparation — 2026-11-04

Added 20 assistant-authored, labelled synthetic policy cases, pending human review:
10 comparison and 10 merchant consistency cases, with exact clause references,
expected findings, rationales and embedded-instruction examples. Separate files,
no development-booking records. Opt-in runner reuses production planners, provider
adapters and output/reference validation. Default mode validates/plans only and
reports unmeasured metrics; live inference requires explicit flags/cap and a new
artifact. Proposed full run: 18 Gemini calls, two local missing-term guards.
Offline checks exercise dataset structure and scoring mechanics, not AI accuracy.
No UI, migration, dependency, credential or development-record changes and no
Gemini/PayPal calls. See [dataset, scoring definitions and live-run proposal](policy-evaluation.md).

Verification: 30 focused offline dataset/scoring/gate checks passed (six existing
dependency warnings); three-file Ruff lint/format passed. Default plan exercised
without settings/provider construction; all performance rates remain unmeasured.

## Frozen policy-evaluation revision v2 — 2026-11-04

Preserved v1 and added frozen v2 with explicit common equipment/refund scope in
cmp-04/05/06, the requested unresolved-discretion rationale for cmp-08, and an
explicit deposit-refund scope in con-08. Labels remain unchanged. Documented the
single-status, policy-category comparison schema limitation: cmp-08 is never a
match; `differs` remains distinguishable from that unsafe result in case reports.
Model metrics/failures now exclude cmp-07/con-07 completely; separate local checks
retain their outcomes. Default runner verifies the v2 hash manifest before any
live configuration/inference. Proposed calls remain 18; no live evaluation is
authorised or performed. See [frozen inputs and schema limits](policy-evaluation.md#reviewed-expectations-and-schema-limits).

Verification: 43 focused offline checks passed, six existing dependency warnings;
three-file Ruff lint/format passed. Frozen plan verified with 18 proposed calls and
all performance rates unmeasured. No provider/model or database checks run.

## Authorised six-case synthetic policy pilot — 2026-11-04

Ran exactly cmp-01/04/08 and con-01/04/08, sequentially, on existing configured
gemini-3.5-flash-lite after frozen v2 hash verification. Six responses preserved
in an append-only checkpoint journal; no retries, quota/auth failures, fallback or
model changes. Literal citations passed for all six. cmp-08 returned `differs`
rather than frozen `needs_clarification`: a label mismatch, not a false match.
Other five matched their labels. Comparison uncertainty 0/1; consistency
uncertainty 1/1. Small synthetic pilot, not general accuracy. No prompts, labels,
development records or PayPal calls changed/made. Bounded-wrapper mocked safety
checks are separate. See [results, denominators and evidence](policy-pilot-v2-2026-11-04.md).

## Explicit versus unresolved policy commitments — 2026-11-04

Read preserved cmp-08 output and prompt/schema/checkout guard. Its `differs` result
has no explanation field; competing v1 changed-obligation/uncertainty instructions
are a plausible cause, not observed model reasoning. Both nonmatching statuses
remain checkout blockers. Comparison prompt v2 now prioritises clarification for
undefined outcomes/criteria, preserves explicit conflict classification and avoids
keyword-only treatment of bounded options. Schema, model, transport and payment
guards unchanged. Seven mocked SDK cases plus three actual eligibility-function
unit checks added; 64 focused offline checks passed, with changed-file Ruff checks.
No live inference, dataset/pilot edits, database fixtures or records changed. No
claim that mocked tests establish semantic improvement. See
[analysis, distinction and limitations](policy-comparison-commitments.md).

## Public hackathon deployment assessment — 2026-11-05

Assessed current deployment/runtime/storage/session/AI/payment boundaries and current
official Free-hosting documentation. Recommended two Vercel projects (static React,
Python 3.14 FastAPI monolith) plus dedicated Neon Free Postgres, contingent on Linux
bundle/upload limits and actual account eligibility. No durable raw-file store is
needed for existing extracted-text evidence. Public release is blocked on backend
demo-session isolation, owner-scoped access, global AI/resource budgets, server-side
payment denial/controlled grants and production routing/headers. Judges should use
actual isolated workflows; recorded/mock receipt examples must remain distinct from
new captures. No code/config/credential changes, tests, provisioning, deployment,
database access or provider API calls. See [architecture, current limits and phased
gates](public-hackathon-deployment.md).

## Public demo Phase 1: session ownership — 2026-11-05

Implemented opaque expiring HttpOnly demo cookies, hash-only storage, revocation,
exact Origin/session-bound CSRF checks and private API headers. Shared booking
dependencies and helpers enforce owner access across all reads/writes and child
references, including post-inference publication. Buyer/Merchant remain simulated
views of one workspace. Existing local bookings retain NULL ownership; no public
adoption/backfill. Signed webhook processing retains its verified internal access.
Additive migration 0013 tested only in disposable PostgreSQL, development unapplied.
No real-person authentication, public resource budgets or payment-execution policy
added. No provider calls/provisioning/deployment. See [setup and release gates](demo-sessions.md).

## Public demo Phase 2: durable admission — 2026-11-05

Public-only PostgreSQL reservations enforce global/per-session AI attempted-call,
reserved token, rate, cooldown and concurrency limits, plus session issuance,
booking/source/upload/storage and generic version-write caps. Charges commit before
provider work and survive failures/stale publication; quota/access errors trip a
shared circuit. Crashed slots fail closed without automatic expiry. All five AI
routes and adapters participate. Public SDK/config, orders, capture and provider
reconciliation are denied; signed webhooks retain verified historical reconciliation.
Local sandbox behaviour and immutable receipts remain. Migration 0014 is tested only
in disposable PostgreSQL and left unapplied to development. No secrets/records or
live providers touched; no deployment. See [configuration, accounting and remaining
hosting blockers](public-demo-controls.md).

## Public demo Phase 3: hosting preparation — 2026-11-05

Prepared two Vercel roots with same-origin API rewrite and safe non-resolving default,
90-second backend function, frozen runtime installation and secret/artifact ignores.
Public/hosted settings fail closed; requests verify explicit dedicated database,
schema, immutable protections, catalogue and hosted least-privilege role. Added
separate bounded ordinary/admission pools, disabled automatic prepared statements
and transaction-local SQL timeouts. Template-only acknowledged setup is idempotent
and refuses adoption of unmarked records; migration 0015 is disposable-tested and
unapplied to development. Linux/amd64 Python 3.14 native imports/PDF smoke passed
with frozen wheels (~188 MB site-packages), no provider/database calls. Full backend
checkpoint 630 passed; build/typecheck and Ruff passed. Vercel used-field schema
validation passed, with an upstream unused experimental schema meta-validation
issue documented. No deployment/provisioning, credentials or development data
changed. See [variables, setup order, rollback and hosted gates](hosting-preparation.md).
