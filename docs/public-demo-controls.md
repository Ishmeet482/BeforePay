# Public demo Phase 2: durable limits and payment denial

**Later sandbox opt-in:** [controlled hosted sandbox payments](hosted-sandbox-payments.md)
supersedes unconditional payment denial only when explicitly configured. Defaults
remain off; attempt caps reuse the immutable write-admission ledger. AI controls
are unchanged, and hosted webhook exposure remains disabled.

On **7 November 2026**, the user verified explicitly enabled hosted sandbox booking
**Camera kit- test 1** captured **USD 200**, with receipt persistence after refresh
and exact agreement v2/proposal v2, comparison, checkout approval and both approved
rule references. This is [manual hosted evidence](hosted-sandbox-payments.md#user-verified-hosted-sandbox-capture--7-november-2026),
separate from the original phase's mocked checks. Live payments remain disabled.

Later [Phase 3 hosting preparation](hosting-preparation.md) adds strict public
settings/readiness and disables public webhook exposure by default. Its hosted
default-off AI/no-payment-secret policy supersedes the earlier optional public
webhook exception below. A later prerequisite permits explicitly budgeted hosted
AI configuration without changing this admission layer; see the hosting guide.
Existing local controlled verification remains intact.

Implemented locally; no deployment, provisioning or provider calls performed.
Migration **0014_public_admission** was tested only in disposable PostgreSQL.
Development migrations/environment/records/credentials remain untouched.

## Mode and admission boundary

`PUBLIC_DEMO_MODE=true` enables these controls. It is deliberately false for
existing local sandbox behaviour. **Never publish a backend left in local mode.**
Public mode must be enabled on the directly reachable backend, not only a frontend
or proxy. Session ownership, cookie/CSRF protections and immutable financial
records from [Phase 1](demo-sessions.md) remain in both modes.

Every public request that could invoke Gemini reserves allowance **before** its
provider callback: extraction, comparison requiring policy inference, clarification,
merchant consistency and cancellation-rule proposals. Deterministic comparisons
and insufficient-input local findings consume no AI allowance. They still count
as booking mutations. No automatic AI, retry, model switch or paid fallback added.
The existing configured model, input validation, citation checks, 60-second SDK
timeout, one-attempt transport and 16k/8k output caps are retained.

All instances use the same PostgreSQL transaction-scoped advisory lock and
committed admission ledger. Admission checks session expiry again after obtaining
the lock, computes shared/per-session usage and concurrency, then commits a
reservation on an independent connection before provider work starts. A caller
rollback, timeout, stale version rejection or provider failure cannot refund it.
No booking lock is held during AI inference; all original post-inference binding
checks still apply. Provider adapters also require a single-use admitted context
in public mode, closing direct adapter/CLI paths without an owning API admission.
This does not add a public evaluation endpoint.

AI records contain a server-generated request UUID, session/booking IDs, action,
hash of exact saved input/binding context, reserved units, creation/completion times.
No prompt, source text, provider response, cookie token or secret is stored there.
An identical in-flight session/action/input hash cannot launch another inference.
A deliberate request after completion is a new charged attempt, not a cached result
or automatic retry. Admission identity/charges cannot be edited or deleted by
normal SQL; a trigger allows only the one-way completion timestamp.

Token accounting is intentionally conservative: serialized input UTF-8 bytes +
32,768 system/schema/envelope allowance + 16,000 maximum output units. These are
**reserved budget units**, not measured billed token counts or an accuracy/cost
claim. No evidence is silently truncated to fit. Call ceilings and zero-default
shared token budgets remain independent gates. Operators must choose ceilings
within the verified Free Tier project's actual request/token limits and reserve;
this implementation does not prove hosting or provider use is universally free.

## Conservative configuration

All settings are backend-only. `.env.example` has placeholders/defaults; actual
`.env` was not read or edited. All numeric limits accept zero to deny admission,
except PDF per-file/page/text bounds, which must remain positive.

| Setting | Default | Scope/accounting |
| --- | ---: | --- |
| `DEMO_AI_CALLS_PER_DAY` | **0** | Shared attempted calls, UTC calendar day; disabled until verified. |
| `DEMO_AI_TOKENS_PER_DAY` / `DEMO_AI_TOKENS_PER_MINUTE` | **0 / 0** | Shared reserved units; both must be explicitly set before public AI works. |
| `DEMO_AI_CALLS_PER_SESSION` / `DEMO_AI_TOKENS_PER_SESSION` | 6 / 400,000 | Lifetime of that workspace; failed/stale calls remain charged. |
| `DEMO_AI_CALLS_PER_MINUTE` | 2 | Shared rolling 60-second allowance. |
| `DEMO_AI_CONCURRENT_GLOBAL` / `DEMO_AI_CONCURRENT_SESSION` | 1 / 1 | Outstanding provider reservations across all processes. |
| `DEMO_AI_COOLDOWN_SECONDS` | 15 | Shared interval since last admitted AI request. |
| `DEMO_MAX_SESSIONS` / `DEMO_SESSIONS_PER_HOUR` | 100 / 20 | All-time issuance attempts / rolling shared hour. Active-cookie reuse does not consume issuance. |
| `DEMO_MAX_BOOKINGS` / `DEMO_BOOKINGS_PER_SESSION` | 100 / 2 | All-time creation attempts. |
| `DEMO_MAX_SOURCES` / `DEMO_SOURCES_PER_SESSION` | 400 / 8 | All-time intake attempts, including failed parsing after admission. |
| `DEMO_MAX_WRITES` / `DEMO_WRITES_PER_SESSION` | 4,000 / 100 | Booking mutations, including versions, reviews, approvals and denied AI attempts. Prevents unlimited version/history growth. |
| `DEMO_SOURCE_BYTES` / `DEMO_SOURCE_BYTES_PER_SESSION` | 8,000,000 / 400,000 | Retained evidence byte reservations. Text charges actual UTF-8 size; PDF reserves max characters × 8 for UTF-8 joined text plus page text. |
| `DEMO_UPLOAD_BYTES` / `DEMO_UPLOAD_BYTES_PER_SESSION` | 64 MiB / 6 MiB | Submitted PDF bytes, charged before extraction. |
| `DEMO_PDF_MAX_BYTES` / `DEMO_PDF_MAX_PAGES` | 3 MiB / 20 | Public PDF extraction caps; max byte setting cannot exceed 3 MiB. |
| `DEMO_SOURCE_MAX_CHARS` | 40,000 | Pasted source/PDF extracted-text cap; cannot exceed existing 100,000 limit. |

Resource/storage limits are **all-time retained attempts**, not daily resets.
Expiry/sign-out/new cookies cannot reclaim them. Session creation has a shared
rolling-hour limit and all-time ceiling rather than trusting attacker-supplied IP
or forwarding headers. No raw IP tracking was added. These caps bound resource
use but do not establish fair access against a determined anonymous attacker.

An authenticated booking mutation first consumes a write reservation; booking,
source and upload admission then consume their own relevant reservations.
Validation/parser/persistence failures may leave charged reservations. A PDF may
consume source allowance even if upload allowance subsequently rejects it. This
is deliberately conservative and never permits extra storage or provider calls.
The raw booking-request body is bounded at PDF max bytes + 64 KiB **before** JSON/
multipart parsing. Resource admission occurs before PDF extraction, after normal
ownership checks. Local mode retains its original 5 MiB PDF limits. Signed webhook
requests retain their original body-size/signature-processing path.

## Quota, crash and error behaviour

Denied admissions return HTTP 429 with specific shared/workspace/token/rate/busy
or resource messages. Browser views display the safe server explanation, preserve
inputs and make no retry. Manual editing/review remains possible within write
allowance. Existing saved history can still be read after quota depletion while
the owning session remains active.

Provider 429 or 401/403 mappings trip a **durable shared circuit breaker** before
releasing the slot. Subsequent AI admissions, including new sessions and other
workers, are blocked. Already-admitted requests cannot be cancelled retroactively.
Timeout/invalid output/other failures remain charged and release their slot when
the synchronous provider call exits; they do not automatically retry.

A process crash or failed completion transaction leaves its slot outstanding.
**No automatic TTL reclaims a potentially active provider call.** This fails closed
rather than permitting overlapping calls. Recovery requires an organiser to first
prove the request/process ended, then mark that reservation finished through a
controlled database operation. Quota/access circuits likewise require review of
actual provider availability before an operator clears the circuit. No reset,
refund, quota-edit, slot-release or circuit-clear API/UI exists. Do not delete or
edit charges to restore budget. Event-end database disposal/retention is a later
explicit operator procedure, never automatic cascading deletion of receipts.

## Public payment policy

Public mode **without explicit sandbox opt-in** returns 403 `public_demo_payment_disabled` for SDK/config exposure,
order creation/retry, capture/retry and provider reconciliation. The service layer
also rejects create/capture/reconciliation, so accidental internal reuse cannot
bypass the router policy. Ordinary sandbox flags or credentials alone cannot
override it; `PUBLIC_SANDBOX_PAYMENTS_ENABLED=true` and complete sandbox configuration
are also required. Default-off eligibility includes `payment_execution_allowed=false`, no configured SDK state and
an explicit policy notice. UI disables SDK loading, provider status checks and
create/capture retries, while retaining uncertain-result warnings.

Agreement/rule/checkout approvals remain separate exact-version actions, not
payment. Public readiness and explicit checkout review can still operate; no
approval grants payment execution by itself. Explicitly enabled sandbox execution
also requires exact current approval, durable global/session attempt admission and
verified capture. Cancellation previews remain Python calculations,
not refunds. Owned historical attempts/receipts remain readable and unchanged;
foreign sessions cannot read them. No fabricated/seeded receipt was added, and an
unpaid booking still returns 404 for receipt retrieval.

**Explicit signed-webhook exception:** user required existing verified webhook
handling to remain intact. It keeps signature verification, event deduplication,
read-only provider reconciliation and immutable capture recording, including legacy
attempts. Only that verified internal path bypasses public reconciliation denial;
caller headers/roles cannot select it. It never creates/captures a new payment.
This supersedes the earlier assessment's recommendation to disable webhook
verification in public mode. Do not assume this exception is free from abuse:
hosted admission/edge limits and controlled webhook exposure remain release work.

## Migration, verification and remaining hosting work

After **separate authorization** for a target database:

```sh
cd backend
uv run --frozen alembic upgrade head
uv run --frozen alembic current
```

Expected head is `0014_public_admission`. Neither this command nor any development
migration was run here; Phase 1 migration may also still be pending. Use a fresh,
dedicated synthetic demo database for hosting. Migration adds only the ledger,
circuit row and protection trigger; no old bookings, ownership or payment data
is backfilled. Restart backend after authorized migration/configuration, rebuild/
reload frontend. Public mode must be true and secure cookie/allowed-origin settings
correct **before** exposing the backend. AI remains disabled with zero defaults.

Offline tests use disposable PostgreSQL, mocked Gemini/PayPal and synthetic browser
fixtures. They cover all five allowed/denied AI entry points, adapter bypass,
concurrent last-call/global/session slots, replay, usage/rate/token limits, failed/
stale calls, persistent circuit, session cycling, session creation races, storage/
upload limits, direct payment attempts, private receipts and signed webhooks.
Migration checks compare counts and canonical row hashes across pre-existing
tables in synthetic 0012 → 0013/0014 databases and verify new protections. They
do not claim a before/after audit of the untouched development database.

Verification commands/results:

- `cd backend && uv run --frozen --offline pytest -q --tb=short`:
  **605 passed**, six existing dependency warnings at the full-run checkpoint.
  Final focused public admission/payment/migration checks subsequently passed
  **40 tests** after limit refinements; these overlap the full suite and are not
  added to its count. Two final PDF checks also passed, covering actual synthetic
  PDF extraction, page/text caps and upload-size rejection.
- `uv run --frozen --offline ruff check .` and `ruff format --check .` passed.
  No dependencies/lockfiles changed.
- `cd frontend && npm run build`: TypeScript and production build passed.
- New `public-demo.browser.mjs`: **16 checks** for desktop/mobile payment policy,
  uncertain states, synthetic historical receipt display, all five quota-message
  actions, preserved input and no automatic retry.
- Five existing mocked browser suites passed: session lifecycle, booking entry,
  connected blocker journey, PayPal approval/SDK and redesign (including receipt
  print behaviour). Browser API/provider responses are synthetic; no claims of a
  real payment or hosted integration are made.

With the existing environment-free QA server and isolated Chrome CDP running:

```sh
cd frontend
FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 \
  node tests/all-browser.mjs public-demo.browser.mjs demo-sessions.browser.mjs \
  booking-entry.browser.mjs blocker-journey.browser.mjs \
  paypal-approval.browser.mjs redesign.browser.mjs
```

Remaining hosting blockers:

- Provision nothing until authorised: dedicated synthetic database/templates,
  runtime build, Vercel `/api` routing, exact origins and Secure cookie forwarding/
  cache isolation still need real hosted verification.
- Verify current Free-hosting eligibility/limits, Python native dependencies,
  cold starts/timeouts, PostgreSQL pooler/connection/locking behaviour, request
  payload overhead and database storage. No hosting guarantee established here.
- Configure verified Free Tier allowances below actual project quotas; zero-cost
  availability has not been tested. Admission limits are not a billing integration.
- Platform/edge request/flood controls, controlled webhook exposure, operational
  crash/circuit recovery and event-end retention remain. Application caps alone
  are not complete public abuse prevention.
- No real buyer/merchant authentication or recovery; prototype roles share one
  anonymous workspace. Existing development records stay outside public hosting.

This phase does not deploy, expose an API, enable live AI or initiate payments.
