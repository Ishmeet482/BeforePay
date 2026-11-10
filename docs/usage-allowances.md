# Application allowances — 10 November 2026

These limits apply to every isolated public-mode session, shared between Buyer
and Merchant prototype views. Local non-public mode retains its admission bypass.
Nothing resets counters or assigns another visitor's records. No hosted settings,
records, credentials or providers were accessed by this change.

## Cumulative inventory and enforcement

All configurable cumulative allowances are listed below. Nonzero defaults rise
10× from the preceding code revision. Zero daily AI defaults remain disabled;
they never mean unlimited. Explicit environment overrides continue to win.

| Environment variable | Previous default | New default | Enforcement/accounting |
| --- | ---: | ---: | --- |
| `DEMO_MAX_SESSIONS` | 100 | 1000 | All-time session issuance reservations, including failed issuance after reservation. |
| `DEMO_MAX_BOOKINGS` | 100 | 1000 | Global booking creation reservations. |
| `DEMO_BOOKINGS_PER_SESSION` | 5 | 50 | Same ledger filtered by session, across all its bookings. |
| `DEMO_PAYMENT_ATTEMPTS_GLOBAL` | 20 | 200 | Global write reservations with action `sandbox_payment_attempt`. |
| `DEMO_PAYMENT_ATTEMPTS_PER_SESSION` | 5 | 50 | Same payment ledger filtered by session. |
| `DEMO_MAX_WRITES` | 4000 | 40000 | Global write admissions, including payment reservations. |
| `DEMO_WRITES_PER_SESSION` | 100 | 1000 | Writes across all bookings in the session. |
| `DEMO_MAX_SOURCES` | 400 | 4000 | Global intake reservations, including failed PDF processing after admission. |
| `DEMO_SOURCES_PER_SESSION` | 8 | 80 | Source admissions across all session bookings. |
| `DEMO_SOURCE_BYTES` | 8000000 | 80000000 | Global UTF-8 text storage reservations. |
| `DEMO_SOURCE_BYTES_PER_SESSION` | 400000 | 4000000 | Text reservations across the session. |
| `DEMO_UPLOAD_BYTES` | 67108864 | 671088640 | Global submitted PDF bytes (64 → 640 MiB). |
| `DEMO_UPLOAD_BYTES_PER_SESSION` | 6291456 | 62914560 | Session PDF bytes (6 → 60 MiB). |
| `DEMO_AI_CALLS_PER_SESSION` | 6 | 60 | Lifetime admitted calls across all AI features, including failed/stale output. |
| `DEMO_AI_TOKENS_PER_SESSION` | 400000 | 4000000 | Lifetime reserved units across all AI features. |
| `DEMO_AI_CALLS_PER_DAY` | 0 | 0 | Shared UTC-day admitted calls; code default remains disabled. Production secret value UNKNOWN, preserve it. |
| `DEMO_AI_TOKENS_PER_DAY` | 0 | 0 | Shared UTC-day reserved units; code default remains disabled. Production secret value UNKNOWN, preserve it. |

`app/admission/service.py:reserve` uses the same database-wide advisory transaction
lock and separately committed ledger for every admission. Count quotas reject
`used >= cap`; byte/unit quotas reject `used + requested > cap`, allowing an exact
fit. Deleting a display row, cancelling, failure, sign-out, caller rollback or
changing roles does not refund reservations. No automatic retry/refund/reset was
added. AI daily windows are UTC; other cumulative reservations are all-time.

Text intake charges actual UTF-8 bytes. Each PDF reserves
`DEMO_SOURCE_MAX_CHARS × 8` (currently 320000 units) for joined/page text, plus its
upload bytes separately. This is conservative reserved storage, not measured live
database size. AI reservation is UTF-8 JSON context bytes **+ 32768 + 16000**;
it combines input/system/schema/output allowance rather than billing-token
measurement. No separate input/output cumulative setting exists. The reservation
is not reconciled to actual model token usage.

The session router reserves issuance; booking creation reserves a booking;
ownership middleware reserves writes for non-safe booking requests. Source routes
reserve count/text bytes and PDF upload bytes. Payment service reserves a new
attempt only after existing-attempt reuse checks. Extraction, policy comparison,
clarification, policy consistency and cancellation-rule generation all use
`run_ai`; they share AI quotas, circuit breaker and write controls. There are no
separate cumulative draft, comparison, clarification, reply, correction-review,
policy-check, rule-version or receipt quotas. Saved reads and Python previews make
no provider calls; non-safe preview requests still consume normal writes.

There is **no separate stored-source quota per booking** or environment variable
for it. A single booking can use the owner's remaining source allowance. The
20-source `DraftCreate`/frontend selection limit is per inference request, not a
stored-source allowance; it stays unchanged. Pagination limits are page sizes,
not total-history quotas; exact agreement review still requires acknowledging
all saved evidence. Request schema list lengths remain resource/validation caps.

Public validation ceilings now admit all new defaults: bookings 1000/50,
payment reservations 200/50, sources 4000/80, writes 40000/1000, global text
80000000 bytes and uploads 671088640 bytes. Session issuance ceiling stays 1000.
No unlimited option was introduced; defaults and proposed values are finite.
Existing nonnegative overrides remain supported within the documented ceilings.

## One Production change block

Use the complete tested [non-secret block](../backend/.env.quotas.example) below
in the **backend** Vercel project's **Production** environment. Replace any old
lower overrides for these names; changing code defaults alone cannot override
dashboard/Secret-backed settings. These values are allowances, not enablement.

```dotenv
DEMO_MAX_SESSIONS=1000
DEMO_MAX_BOOKINGS=1000
DEMO_BOOKINGS_PER_SESSION=50
DEMO_PAYMENT_ATTEMPTS_GLOBAL=200
DEMO_PAYMENT_ATTEMPTS_PER_SESSION=50
DEMO_MAX_WRITES=40000
DEMO_WRITES_PER_SESSION=1000
DEMO_MAX_SOURCES=4000
DEMO_SOURCES_PER_SESSION=80
DEMO_SOURCE_BYTES=80000000
DEMO_SOURCE_BYTES_PER_SESSION=4000000
DEMO_UPLOAD_BYTES=671088640
DEMO_UPLOAD_BYTES_PER_SESSION=62914560
DEMO_AI_CALLS_PER_SESSION=60
DEMO_AI_TOKENS_PER_SESSION=4000000
```

**Preserve existing value**, without retrieval or replacement:

- `DEMO_AI_CALLS_PER_DAY` — hidden Production Secret, UNKNOWN.
- `DEMO_AI_TOKENS_PER_DAY` — hidden Production Secret, UNKNOWN.
- `DEMO_AI_TOKENS_PER_MINUTE` — hidden Production Secret, UNKNOWN; throughput control.

The combined settings test loads this exact block as environment strings together
with valid **synthetic** positive values for those three hidden AI settings,
Secure cookies, TLS database/origin settings and complete synthetic sandbox
opt-in credentials. It does not verify real Secret contents, remaining daily
budget, credentials, grants, origin configuration or provider capacity.

## Controls intentionally unchanged

| Control | Current default/limit |
| --- | --- |
| `DEMO_SESSIONS_PER_HOUR` | 20 shared rolling-hour issuance attempts; reuse is not issuance. |
| `DEMO_AI_CALLS_PER_MINUTE` | 2 shared calls/minute. |
| `DEMO_AI_TOKENS_PER_MINUTE` | Code default 0 disables admitted positive units; preserve UNKNOWN Production value. |
| `DEMO_AI_COOLDOWN_SECONDS` | 15 seconds shared; 0 means no cooldown. |
| `DEMO_AI_CONCURRENT_GLOBAL` / `DEMO_AI_CONCURRENT_SESSION` | 1 / 1; public ceilings 4 / 1; 0 closes admission. |
| `DEMO_PDF_MAX_BYTES` / `DEMO_PDF_MAX_PAGES` | 3145728 / 20 public defaults; local 5 MiB / 100 pages. |
| `DEMO_SOURCE_MAX_CHARS` | 40000 public; local/schema maximum 100000. |
| Draft input | At most 20 selected sources and 200000 combined characters per request. |
| Other AI context/output/schema limits | Existing provider limits, exact citations and structured validation retained. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | 2 / 0 / 3 seconds. |
| Database timeouts | Connect 3 seconds; public statements 5 seconds; locks 3 seconds; recycle 300 seconds. |
| `DEMO_SESSION_TTL_SECONDS` | 2592000 seconds; existing expiry/ownership unchanged. |
| Payment transport/guards | Fixed sandbox, no retries/fallback, stable keys, exact approvals and verified capture; webhooks remain disabled on Vercel. |

The 1000 lifetime sessions can still hit the 20/hour rate; 50 bookings can exhaust
80 shared sources, 60 AI calls, reserved units or writes. Global allowances remain
shared and previously consumed usage counts. Payment reservations also consume
writes; a booking can need multiple writes and AI calls. A quota increase is not
a promise of 50 complete walkthroughs or captures. Admission still serializes
under one advisory lock and scans the applicable ledger; higher retained usage
can increase write-admission work. No ledger/cache redesign or throughput uplift
is claimed.

## Verification

The selected regressions passed **288 distinct tests** (286 combined plus two new
AI-boundary checks), with six
existing dependency warnings. It covers all cumulative default/environment strings,
combined synthetic hosted settings, zero/negative/ceiling boundaries, existing
reservations, exact-fit bytes, concurrent final admissions, owner isolation,
public-read connection lifecycle and mocked capture/receipt protections. The
frontend build/typecheck, Ruff lint/format (145 Python files) and whitespace checks
passed. The unchanged UI/performance patch had already passed all **19
mocked browser feature suites**, including unsaved navigation and receipt printing;
these suites were not needlessly rerun after changing backend defaults only.
No provider response or hosted performance was tested live.

```sh
cd backend
uv run --frozen --offline pytest -q -x --tb=short \
  tests/test_session_allowances.py tests/test_public_admission.py \
  tests/test_hosted_sandbox_payments.py tests/test_hosting_preparation.py \
  tests/test_hosting_diagnostics.py tests/test_restricted_saved_state.py \
  tests/test_saved_state_performance.py tests/test_demo_sessions.py \
  tests/test_paypal_sandbox.py tests/test_paypal_webhooks.py \
  tests/test_legacy_corroboration_flow.py
uv run --frozen --offline ruff check .
uv run --frozen --offline ruff format --check .
cd ../frontend
npm run build -- --config vite.qa.config.ts
```

## Deployment and independent readiness checklist

1. Confirm the pushed allowance-compatible backend revision before changing
   Production values. Save the whole block and deploy **that code with those
   environment values together**; never redeploy an older revision with the new
   values. Keep the three hidden AI settings and all credentials/enablement
   settings unchanged. No migration, permission grant or data reset is required.
2. The separately prepared saved-read/performance changes require their own
   reviewed backend revision, then frontend deployment. New frontend saved-state
   reads require the matching backend endpoint. Verify Singapore execution region
   after rollout; no hosted speed improvement is claimed from local tests.
3. Check settings/readiness through ordinary saved-data reads. No automatic
   source generation, AI request, approval or payment is part of rollout.

| Stage | Independent requirements; no actions executed by this audit |
| --- | --- |
| Create booking | Unexpired owner session; issuance/hour, global/session booking and write headroom; CSRF/origin/readiness. |
| Save source | Count, reserved-text/upload bytes and write headroom; request/PDF limits; original evidence validation. |
| AI draft | Explicit selection/action; context limits; shared daily/minute Secret budgets UNKNOWN; session units/calls, concurrency, circuit/provider quota and output validity. |
| Agreement confirmation | Reviewed source acknowledgements, correction reasons where edited, complete/unambiguous terms and exact current version. |
| Merchant proposal | Explicit saved independent proposal; current expected version; write allowance; buyer baseline preserved. |
| Comparison | Explicit request; current confirmed baseline/proposal; Python checks plus shared AI budgets if policy inference is needed; exact evidence. |
| Clarification/reply/correction | Saved discrepancy bindings; AI budget for suggestion; explicit merchant reply; newer matching correction/current comparison for buyer review; none grant checkout approval. |
| Both policy reviews | Independently reviewed/approved current agreement and merchant rules; exact clauses; manual corrections where needed; current contradictions/uncertainty still block. |
| Cancellation preview | Current approved complete rules, no contradiction blockers; explicit date/time; Python calculation; no cancellation/refund executed. |
| Checkout approval | Current matching comparison, separate policy approvals, consistent rules, amount/currency and exact version-bound explicit approval. |
| Payment | Existing explicit sandbox opt-in, valid credentials/grants UNKNOWN, current approval, attempt/write headroom, idempotency and verified provider state. No order/capture was initiated. |
| Saved receipt | Only immutable verified COMPLETED capture record; session-owned retrieval. Existing user-reported receipts remain historical evidence, not a new live test. |

Hidden daily AI and minute-unit budgets cannot be verified from local code.
Provider Free Tier/project quotas, model availability, PayPal account restrictions,
Vercel execution/bandwidth/body/function limits and Neon compute/storage/connection
allowances are external and unchanged. No account-limit uplift or hosted
performance was measured. Existing AI output mistakes/manual correction needs,
unresolved hosted timing failures and session expiry remain independent concerns.
See [hosted observations](hosting-preparation.md), [demo outline](demo-readiness.md)
and [payment setup](hosted-sandbox-payments.md).
