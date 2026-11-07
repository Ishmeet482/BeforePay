# Phase 3: Vercel hosting preparation

Prepared locally on 2026-11-05. **No deployment/provisioning, development migration,
credential change or Gemini/PayPal call.** Migration `0015_demo_templates` remains
unapplied to development. Existing local records are not a public demo seed.

## User-reported hosted checkpoint — 2026-11-07

The preparation-only statements below describe earlier checkpoints. The user has
since reported a hosted walkthrough through extraction, deposit-change detection,
clarification/reply, correction review, a fresh matching comparison, manually
corrected and approved buyer/merchant rules, cutoff previews and exact checkout
approval. See [manual observations and limitations](demo.md#user-reported-hosted-walkthrough--2026-11-07).
This is user-reported manual evidence, separate from disposable-database and
mocked-provider tests; no tests were rerun for this documentation update.

Two AI refund-allocation errors required human correction before rule approval.
Their exact erroneous outputs and causes are not established here. Intermittent
`public_setup_required` errors cleared on refresh; the latest Agreement review
loaded version 1 and both source acknowledgements. No failing request/exception
was captured, so no specific configuration, grant or code fix is justified.
The code uses this error for both settings validation and database-readiness
failure; the code alone does not identify which failed in this hosted observation.
Capture the method, endpoint, status, full safe error message and sanitised runtime
exception/SQLSTATE if it recurs. Do not weaken guards or add automatic retries.

Public-demo payment execution remains disabled. Exact checkout approval does not
establish a capture or receipt. This update changes no hosted settings, grants or
records and makes no provider calls. Remaining hosted routing/cookie/cache,
cross-session isolation, quota, reliability and account gates below are not all
certified by this single walkthrough. AI correctness and intermittent readiness
failures remain open limitations.

## Prepared architecture and files

Two projects from the same repository: frontend root `frontend/`, backend root
`backend/`. Keep one FastAPI monolith and one dedicated PostgreSQL database.

- `frontend/vercel.json`: Vite, `npm ci`, `npm run build`, `dist`; only `/api/:path*`
  rewrites externally, with path intact. Hash-based UI routes need no SPA rewrite
  swallowing API errors. API responses carry private/no-store, Cookie/Origin Vary
  and rewrite-cache disable headers at both app and frontend proxy configuration.
- Backend config uses the existing `app/main.py` FastAPI entrypoint, frozen
  production dependencies and a **90-second** function. Python remains `>=3.14,<3.15`.
  Native FastAPI support and Python 3.14 are documented by
  [Vercel](https://vercel.com/docs/frameworks/backend/fastapi) and its
  [Python runtime](https://vercel.com/docs/functions/runtimes/python).
- `backend/.python-version` selects `3.14`, matching the project/lockfile minor
  range. It intentionally does not pin `3.14.1`: Vercel supplies its own 3.14
  patch interpreter, and an exact unavailable patch makes uv discovery fail.
  `uv sync --frozen --no-dev` and the dependency lockfile remain unchanged.
  Isolated Linux verification on 2026-11-06 reproduced the old discovery failure
  on supplied Python 3.14.10, then passed frozen production installation, runtime
  imports and an offline repeat dry-run with the minor pin. Actual Vercel rebuild
  remains to be checked; no environment-variable or dependency changes were needed.
- Backend `.vercelignore` and function `excludeFiles` omit environment files,
  virtualenv, tests, evaluation/pilot artifacts, uploads, temporary storage and
  operator scripts. Migrations/setup are operator commands, never runtime startup
  or build hooks. Frontend ignores local environment files too. No credentials or
  provider tokens belong in `VITE_*`, rewrites, repo config or build logs.
- The committed rewrite now targets `https://before-pay-three.vercel.app/api/:path*`.
  The original preparation used `https://backend-not-configured.invalid`; when
  deliberately changing the backend, prepare the actual origin with:

```sh
# From repository root; edits only a non-secret local JSON rewrite.
python3 scripts/prepare_vercel.py --backend-origin https://YOUR-BACKEND-HOST
```

This command does not deploy, provision or contact that host. It accepts only an
HTTPS origin without credentials, path, query or nonstandard port. No actual
hostname was configured at the original preparation checkpoint. Review the generated
diff before publishing; the committed target above records the subsequent setup.

### Cookie, origin and access boundary

Browser requests remain relative `/api`; no frontend backend-base-URL secret.
The proxy must preserve Cookie, Origin, CSRF header, method, JSON/multipart body
and Set-Cookie. The host-only `HttpOnly; Secure; SameSite=Lax; Path=/api` cookie then
belongs to the frontend host. No cross-origin cookie/CORS relaxation is needed.
Existing exact-origin mutation checks, CSRF binding, session expiry and every
booking/child ownership check remain. Direct backend calls use the same guards.

The local HTTPX/ASGI rewrite test verifies those semantics with two independent
cookie jars, including isolated lists/sources, CSRF rejection, forbidden payment
configuration, no receipt creation and zero-budget AI refusal. **It is not proof
that Vercel forwards or caches headers correctly.** Inspect real hosted responses
and browser behaviour before release. Current external rewrite behaviour is
documented by [Vercel](https://vercel.com/docs/routing/rewrites).

## Fail-closed public configuration

`backend/.env.public.example` contains only placeholders. Set these **backend**
variables in the host's secret/configuration store after authorisation:

| Variable | Required policy |
| --- | --- |
| `DATABASE_URL` | Runtime least-privilege role, dedicated pooled PostgreSQL TLS URL, `postgresql+psycopg`; no local development database. |
| `PUBLIC_DEMO_DATABASE` | Exact dedicated database name matching `current_database()`; default/system `contextkey`, `postgres`, `template0/1` are refused. |
| `PUBLIC_DEMO_MODE` | `true`; Vercel's injected `VERCEL=1` rejects local mode. Never disable the injected indicator to bypass checks. |
| `DEMO_ALLOWED_ORIGINS` | JSON list of exact real HTTPS frontend origins. No localhost HTTP, wildcards or blanket preview domain. |
| `DEMO_COOKIE_SECURE` | `true`. |
| `DEMO_SESSION_TTL_SECONDS` | `2592000` for newly issued 30-day persistent sessions; existing stored expiries are unchanged. Role switching/revisits do not slide expiry. |
| `DEMO_AI_CALLS_PER_DAY`, `DEMO_AI_TOKENS_PER_DAY`, `DEMO_AI_TOKENS_PER_MINUTE` | Default **0**. Explicit operator budgets are now accepted; actual hosted enablement is a separate step. All three must permit a reservation. |
| `GEMINI_API_KEY` | Default absent/empty. May be installed privately for separately authorised budgeted AI; no key was installed by the prerequisite change. No fallback/model change. |
| `PAYPAL_SANDBOX_ENABLED` | `false`; no PayPal client ID/secret installed. Public payment execution remains denied independently. |
| `PUBLIC_WEBHOOKS_ENABLED` | `false`. Hosted preparation refuses enabling it in this phase. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT` | Defaults 2, 0, 3 seconds; small validated bounds. |
| Other `DEMO_*` resource limits | Retain [Phase 2 defaults](public-demo-controls.md); grossly raised session/source/write/storage/concurrency ceilings are rejected. Zero can close admission. |

Frontend needs no database, AI or payment variables. Select **Node 22.x** in project
settings; build tested with Node 22.23.1. Keep real preview and production origins,
databases and privileges separate; previews must not inherit privileged data.

On 2026-11-07 the hosted-Gemini prerequisite removed only the four Vercel-specific
AI vetoes (key and three shared budgets) and the three forced-zero AI entries from
`backend/vercel.json`. Python defaults and sanitised examples remain zero, so
admission is still disabled until explicitly configured. No provider, admission,
ownership, concurrency, circuit-breaker, timeout or retry code changed. PayPal
enablement/client credentials and hosted webhooks remain forbidden on Vercel.
This change installs no credential or dashboard variable and makes no live call;
earlier zero-AI preparation statements describe the original checkpoint.

Focused prerequisite verification: **69 checks passed** across hosting settings,
public admission and payment-denial suites, with six existing dependency warnings.
They cover accepted default/partial/budgeted AI settings, rejection of payment/
webhook settings even alongside AI, all AI entry-point admission, concurrent and
durable limits, circuit failures and direct payment denial. Providers were mocked
and database checks used disposable local PostgreSQL. Ruff lint/format and diff
whitespace checks passed; no live model or hosted configuration was tested.

Invalid settings return a private, generic 503 before body parsing/provider work,
without printing input values or connection strings. Every public database request
also checks exact migration head, explicit dedicated-database marker, exact template
catalogue, ownership column, enabled ownership/admission/receipt/template triggers
and admission control row. Missing/disabled setup fails closed. On Vercel, it also
refuses superuser/bypass-RLS/role-management roles, application table owners,
database/schema CREATE and
admission TRUNCATE privileges. These are additional protections; no authentication
or real Buyer/Merchant roles were added.

## Database pooling and bounded work

### Sanitised setup-failure diagnostics — 2026-11-07

Intermittent hosted `public_setup_required` remains undiagnosed without a captured
failure. Both original 503 responses and all fail-closed checks remain unchanged.
The new warning event **`public_setup_failure`**, under logger
`uvicorn.error.beforepay.hosting`, distinguishes:

| Log fields | Meaning / next check |
| --- | --- |
| `boundary=settings_validation` | Pydantic rejected deployment settings before request processing. `fields` lists only recognised setting names; `model_validation=true` identifies a model-wide rejection without a field location. Inspect configuration privately; no values or validation prose are logged. |
| `boundary=database_readiness`, `exception_type=PoolTimeout` | SQLAlchemy could not acquire a connection within the existing pool wait. `check` identifies the readiness stage awaiting a connection; this is not a failed migration or proof that raising the pool size is appropriate. |
| `boundary=database_readiness`, `exception_type=OperationalError/ProgrammingError/DBAPIError` | A readiness database operation failed. `check` identifies its stage and `sqlstate` is allowlisted; unknown states become `OTHER`. No driver message, SQL or parameters are logged. |
| `check=invariants`, nonempty `failed_checks` | Queries completed but named requirements failed: database identity, migration revision, deployment marker, immutable triggers, admission control, ownership column, template catalogue or runtime privileges. Observed database values are omitted. |

Useful SQLSTATEs include `55P03` (lock timeout/unavailable), `57014` (query cancelled,
including statement timeout), `42501` (insufficient privilege), `42P01` (undefined
table), `42703` (undefined column), `28P01` (authentication failure), `08001/08006`
(connection failures), and `53300` (connection capacity). A state identifies a
class of failure, not its complete cause. Connection timeouts may have no SQLSTATE
and appear as `OTHER`. Fixed exception categories avoid logging arbitrary class
names or exception text. No traceback/exception object, request path/query, cookie,
header, credentials, connection URL, source content or SQL parameters are attached
to these diagnostic records.

Hosted readiness executes seven sequential queries, plus the runtime-privilege
query on Vercel, before endpoint processing. Its transaction normally retains a
connection until request cleanup. Existing runtime defaults are pool size **2**,
overflow **0**, pool acquisition **3 seconds**, connection establishment **3
seconds**, statement timeout **5 seconds**, lock timeout **3 seconds**, recycle
**300 seconds**, with pre-ping. The separate admission pool has size **1**, overflow
**0** and the same configured acquisition wait. No timeouts, pools, locks, guards,
retry behaviour or caching were changed by this diagnostic increment.

A disposable-PostgreSQL test deliberately occupied both runtime slots: readiness
returned the existing 503 and logged `PoolTimeout` at `database_identity`; a later
independent check succeeded after release. This demonstrates one possible
refresh-recovery mechanism, **not the cause of the reported hosted failures**.
No automatic retry is introduced. On recurrence, locate the failing invocation
in Vercel runtime logs by time and search for `public_setup_failure`; retain its
safe JSON alongside the Network method, endpoint suffix, status and response
message. Share neither complete environment dumps nor unrelated raw tracebacks.

Focused offline verification: **44 distinct checks passed** across
`tests/test_hosting_diagnostics.py`, `tests/test_hosting_preparation.py` and
`tests/test_restricted_saved_state.py` (43 initially, followed by the added
model-wide validation test alone). Run from `backend/` with
`uv run --frozen --offline pytest -q -x --tb=short` and those three file paths.
Tests cover fail-closed responses, no automatic retry, sanitised settings/SQL
failures, real pool exhaustion/release, disabled protections and restricted-role
concurrency/ownership. PostgreSQL was disposable and providers were blocked/mocked;
six existing dependency warnings occurred per run. Ruff lint/format and diff
whitespace checks passed. No hosted configuration, records or provider calls were
used, and no new hosted-failure diagnosis is claimed.

### Parallel saved-state read locks — 2026-11-06

The hosted overview traceback reported `sqlalchemy.exc.OperationalError` wrapping
`psycopg.errors.LockNotAvailable` (`55P03`, lock timeout) in
`checkout/attempts → lock_booking`. Buyer/Merchant overview share six parallel
saved-state GETs; previously each held an exclusive booking `FOR UPDATE` lock
until its request session closed. Uncontended local reads passed, so the grants
alone did not reveal the failure. A controlled disposable-PostgreSQL regression
held one reader open and reproduced that exact exception in the other GETs under
the restricted runtime grants.

The authenticated ownership dependency now marks safe HTTP requests internally;
their common/nested booking locks use `FOR SHARE`. Readers can coexist while still
excluding mutations for the transaction lifetime. Unsafe requests and internal/
webhook callers default to `FOR UPDATE`. No lock is removed, no timeout increased
and no automatic retry added. Ownership, CSRF and payment restrictions remain.
The existing column UPDATE grant supports both lock modes; **no grant or migration
change is required**.

Focused regressions exercise all six routes with the restricted role, a held reader
with five parallel GETs, writer exclusion in both directions, foreign-session
rejection and public payment denial. Provider calls are mocked/blocked and only
disposable local PostgreSQL is mutated. Hosted recovery requires checking a new
deployment; no hosted data/configuration was changed by this fix.

Verification: the focused regression selection completed **204 distinct
checks** across the initial run and the two corrected configuration checks; five
restricted-role/concurrency cases were also rerun after final assertions. Ruff
lint/format and diff whitespace checks passed. The initial run passed 202 tests
then stopped at an obsolete `.invalid` rewrite assertion left from before the
authorised backend-origin preparation. That test now verifies HTTPS `/api` routing
without hard-coding an obsolete host. Six existing dependency warnings remain.
No full-suite or deployed recovery result is claimed.

Use the managed provider's pooled TLS endpoint for runtime and a **direct admin/
migration endpoint** for operator setup. There are two bounded SQLAlchemy pools
inside the same monolith: ordinary requests default to two connections; durable
admission/finalization uses a separate one-connection pool, preventing requests
holding ordinary connections from starving their own budget reservations.
No extra database/service is introduced. Per-process default maximum is three;
aggregate serverless fan-out still needs account/database limits and observation.

Both pools have pre-ping, 300-second recycling, a 3-second connection timeout and
bounded pool waiting. Psycopg `prepare_threshold=None` disables automatic statement
preparation conservatively; [Psycopg documents this option](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html).
This does not claim modern PgBouncer cannot handle protocol prepared statements.
Public transactions set **transaction-local** 5-second statement and 3-second lock
timeouts, avoiding session-level state. Admission uses transaction-level advisory
locks. No provider call holds a booking lock/transaction. Actual Neon/PgBouncer
TLS, permissions, JSONB, locks, reconnects and scaling remain hosted checks; see
[Neon's transaction pooling limitations](https://neon.com/docs/connect/connection-pooling).

SDK timeout stays 60 seconds/one attempt; function cap 90 seconds; ordinary browser
API timeout is now 95 seconds. Session-only operations keep 20 seconds. This fits
within Vercel's documented [120-second external proxy ceiling](https://vercel.com/docs/limits#proxied-request-timeout),
but cold starts and account-specific effective durations must be measured. No
timeout automatically retries a mutation. Public AI remains disabled regardless.

Public PDFs stay 3 MiB, 20 pages and 40,000 extracted characters. Raw booking
requests are bounded to 3 MiB + 64 KiB before multipart parsing, below Vercel's
documented [4.5 MB payload ceiling](https://vercel.com/docs/functions/limitations).
Both public extraction/storage quotas and ownership checks still apply. Local
sandbox retains original limits. Hosted response sizes, proxy multipart overhead,
memory, malicious compressed PDFs and edge flood limits still need verification.

## Explicit migration and synthetic setup order

These are future operator steps, **not executed against development here**.

1. Obtain approval/account access; confirm Free-plan eligibility, region, spend
   ceilings and actual limits. Provision a **new empty synthetic database** and
   separate migration owner/runtime role. Never restore/export the local database.
2. Set the dedicated **direct migration/admin** `DATABASE_URL` in the operator
   environment without echoing it or placing it on the command line. Do not source
   the development `.env`. Export `PUBLIC_DEMO_DATABASE` with the exact target name
   and the explicit public configuration above. Use owner credentials only here.
3. From `backend/`, apply and verify migrations explicitly:

```sh
uv run --frozen alembic upgrade head
uv run --frozen alembic current
# Expected: 0015_demo_templates
```

Alembic normally supports local `.env` for developer commands. For this operator
workflow run with a clean environment and the dedicated exported URL; the exported
URL overrides any file default. Never run these commands against local development
for this task. No migration is run at build/startup/request time.

4. Run the separately acknowledged, idempotent catalogue setup:

```sh
uv run --frozen python -m scripts.setup_demo \
  --database-name beforepay_demo_2026 \
  --acknowledge-dedicated-synthetic-db
```

`setup_demo` refuses absent exported URL, wrong/system/development database name,
wrong revision, an unmarked database with application records, conflicting marker
or modified/unknown template versions. All work is one locked transaction; refusal
commits nothing. Repetition preserves existing catalogue/marker and can safely run
after judge sessions exist in an already marked dedicated demo database. It reads
no `.env`, local booking, upload, credential file or receipt export.

The command creates only two explicitly authored synthetic source templates and a
database marker. It creates **no booking, session, AI draft, comparison, approval,
policy rule, attempt or receipt**. Provenance says synthetic authored example, not
actual merchant evidence or AI output. Tables have UPDATE/DELETE protection.

5. Prepare runtime permissions with the provider's role tools. Runtime needs
   schema USAGE and SELECT on application tables; INSERT for application-created
   records, UPDATE for session revocation and admission completion/circuit state.
   Do not give it ownership, schema CREATE, DELETE, TRUNCATE, migration or role
   management privileges. Keep marker/catalogue read-only. Use a provider-supported
   dedicated runtime login; exact role creation/grants require account access.
   Validate least privilege before deploying. Initial preparation provisioned no
   database roles outside disposable tests. Subsequent authorised Neon runtime
   grants and remaining setup are recorded in [runtime permissions](neon-runtime-permissions.md).
6. Install only the pooled runtime URL and safe variables in backend project;
   prepare the frontend rewrite with the real backend HTTPS origin. Review both
   Vercel project settings, ignore files and generated artifacts. Deployment still
   requires separate authorisation.
7. After an authorised staging deployment, `/api/health/ready` must be 200. Test
   actual cookie/Origin/CSRF behaviour through frontend `/api`, direct-backend
   denial, two independent browser contexts, upload bounds and private responses
   before publication. Restart/redeploy backend after approved config changes;
   do not use old code lacking isolation as a rollback target.

### Using templates without inventing saved history

Authorised Neon setup completed on 2026-11-05 for project `super-hat-76778640`,
production branch `br-shy-dawn-b3vw2kgo`, database `beforepay_demo_2026`. The
acknowledged command above ran twice through a direct certificate-verified owner
connection, without reading or changing local `.env`. The second run preserved
the exact marker/template snapshot, including fingerprints and marker timestamp.

Saved catalogue contains **two version-1 authored templates**:
`SYNTHETIC · Camera rental quotation` (`camera-quotation`) and
`SYNTHETIC · Included items message` (`camera-message`), plus **one deployment
marker**. No sessions, admissions, bookings, evidence, drafts, comparisons,
approvals, policy rules or payment records were created. Existing Alembic and
admission-control singleton rows remain; the circuit is NULL.

Actual runtime login reads the exact source contents/fingerprints and passes
`require_public_database` with public mode and hosted least-privilege validation
enabled. Runtime INSERT/UPDATE/DELETE/TRUNCATE on both marker and catalogue were
rejected in rolled-back verification transactions. Security-catalogue snapshots
confirmed permissions, function definitions/defaults, ownership and all 20 enabled
protection triggers unchanged. This is a real database/setup check, **not** a
deployed `/api/health/ready` response or proof of hosted proxy/cookie behaviour.
No deployment or Gemini/PayPal call occurred; public AI/payment execution remain
disabled. No other database was accessed for setup.

After explicit demo entry, `GET /api/demo-templates` returns the shared authored
catalogue to that active session. It contains synthetic quotation and message text.
No automatic import or new UI chooser was added: copy `original_text` into existing
**Sources & draft → Add quotation or message**, choose its stated source type and
explicitly save it to your session-owned booking. Individual saved sources receive
their own IDs and usual acknowledgements. This API can also support a later
explicit template picker; that UI is not claimed implemented here.

With AI off, judges can exercise real session entry, booking/source persistence,
evidence access and honest blocked generation. A full new agreement/comparison
story requires later separately authorised, bounded AI enablement; **no pre-made
AI output or receipt is substituted**. Public payment execution stays unavailable.
Local saved receipts are not copied into hosted sessions or advertised as new
payments. Existing local story docs are historical inventories only.

## Webhook exposure policy

Public `/api/paypal/*` is blocked before database/provider dependencies by default.
Vercel preparation rejects an enabled webhook flag or installed payment secret.
Do not register a public webhook or carry merchant credentials into this demo.
Existing local sandbox and explicitly enabled non-Vercel controlled signature path
remain intact: no bypass of verification/deduplication/immutable receipts. A future
hosted webhook exception needs separate scope, credentials, edge admission limits
and a real signed-delivery test; it is not enabled by frontend role switching.

## Rollback and recovery

- Keep the frontend/API unexposed until gates pass. If staging fails, remove the
  rewrite or restore `.invalid`, disable public session issuance (`DEMO_MAX_SESSIONS=0`)
  and use platform traffic protection. Keep `PUBLIC_DEMO_MODE=true`, AI budgets zero,
  payment execution denied and webhook exposure false.
- Roll back only to a deployment with compatible session/ownership/admission
  protections and the expected schema. Do not bypass a 503 by weakening checks,
  reverting public mode, using an owner runtime login or enabling secrets.
- Retain the database/schema and append-only history. Do not automatically run
  Alembic downgrade, delete ledger rows, truncate tables, reassign legacy bookings
  or recreate receipts. Restore/replace only an explicitly authorised synthetic
  database from a reviewed backup; mark/rerun catalogue setup appropriately.
- Crashed in-flight AI slots and quota/access circuits remain fail-closed as in
  [Phase 2 recovery](public-demo-controls.md). Prove the provider request/process
  ended before a controlled operator completion/circuit review. No reset endpoint
  exists, and this phase makes no provider call to diagnose them.
- Expiry/sign-out cannot be recovered by public demo passwords. New sessions are
  new isolated workspaces. Preserve records and create a new synthetic session
  rather than inventing an authenticated ownership transfer.

## Verification and account-dependent gates

Local automated checks use disposable PostgreSQL and mocked providers. Same-origin
proxy tests are ASGI/HTTPX simulations, not hosted routing certification. Linux
native dependency verification was an ephemeral container with no ports or secret/
database mounts; only public image/PyPI downloads, no provider calls.

Frozen runtime wheels installed successfully on **Linux x86_64, Python 3.14.10**:
FastAPI 0.162.0, Pydantic 2.14.1, SQLAlchemy 2.0.55, psycopg/binary 3.3.6,
PyMuPDF 1.28.2, Google GenAI 2.34.0 and HTTPX 0.28.1. Native PDF creation/extraction
and app imports passed. Site-packages measured **187,656,949 bytes**; this is not
Vercel's final function bundle measurement. Its documented standard Python
uncompressed ceiling is 500 MB; actual builder artifacts still require checking.
No dependency/lockfile changes or model/provider fallback were needed.

Validation results:

- Full offline backend run: **630 passed**, six existing dependency warnings.
  New hosting checks cover proxy/cookies, CSRF, private errors, dedicated setup,
  least privilege, pool separation and safe configuration. Final migration-0015
  preservation and role checks are recorded separately from that full checkpoint.
- Frontend TypeScript/production build passed. No new template-picker UI or live
  browser-to-Vercel verification is claimed. No provider calls were made.
- Ruff lint/format checks passed. The rewrite generator has valid/invalid-origin
  tests and has not been pointed at an actual backend.
- Both configs pass **used-property validation** against the downloaded official
  Vercel schema. The schema itself currently fails meta-validation in its unused
  `experimentalServicesV2/additionalProperties` branch; the standard validator
  therefore cannot certify the whole upstream schema unchanged. No experimental
  services fields are used here. Actual Vercel builder/CLI acceptance remains a
  hosted/account gate, not a claimed completed deployment test.

Container base: `python:3.14-slim`, manifest digest
`sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966`.
Reproduction: export frozen runtime requirements with
`uv export --frozen --no-dev --no-emit-project --format requirements-txt`; install
them with `pip --only-binary=:all: --require-hashes` in an isolated Linux 3.14
container, mounting only `backend/app` and `scripts/verify_linux.py`, then run that
smoke script. Do not mount `.env`, source documents or the Docker socket.

Remaining account/hosted gates: actual Free entitlement/spend controls and regions;
dedicated DB/runtime role/TLS/pooler credentials; Vercel project roots/Node/Python/
duration settings and dependency bundle; trusted origins/rewrite/protection
interactions; real cookie/CSRF/cache/multipart/response-size/cold-start checks;
platform request/edge flood limits and monitoring/retention. Future live AI or
webhook tests require separate explicit authorisation. None of those account or
hosted behaviours were provisioned or verified here.
