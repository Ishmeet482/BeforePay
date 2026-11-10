# Demo booking capacity and saved reads — 10 November 2026

> **Superseded allowance recommendation (10 November):** this investigation below
> records the defaults and supported bounds before the general-usage increase.
> Current code defaults to **50 bookings and 50 payment reservations per session**;
> payment maximum is now 50. Do not follow the earlier cap-three recommendation
> or cap-four rejection below as current configuration advice. Existing counters
> remain unchanged. See [current settings and rollout](usage-allowances.md).

## Confirmed booking allowance at inspection

The user confirmed both `DEMO_BOOKINGS_PER_SESSION` and `DEMO_MAX_BOOKINGS` are
unset in backend Production. `backend/vercel.json` does not override either.
Read-only inspection of the dedicated demo database found two saved bookings and
two booking reservations in the workspace owning “Smith- Demo”; global booking
reservations total three. No hosted record or counter was changed.

| Setting | Effective default | Validation |
| --- | --- | --- |
| `DEMO_BOOKINGS_PER_SESSION` | 2 | Integer >= 0; public mode rejects values above 5. |
| `DEMO_MAX_BOOKINGS` | 100 | Integer >= 0; public mode rejects values above 1000. |

`POST /api/bookings` first passes the usual session/CSRF/origin/write admission,
then reserves `kind=booking`, `action=create_booking`. Admission counts durable
ledger rows for that kind, globally and across **all bookings in the owning
session**. It rejects when usage is **>= cap**, with HTTP 429
`demo_resource_limit`, “This workspace has reached its booking allowance.”
These are lifetime reservations, not a count reset by role switching, sign-out,
time passing or deleting display rows. Reservations survive later caller failure.
Buyer/Merchant prototype views share the same owner and allowance.

### Prepared change; not applied

The smallest existing configuration change is one backend Production variable:

```dotenv
DEMO_BOOKINGS_PER_SESSION=3
```

Keep the global booking allowance and all other controls unchanged. At current
usage two, cap three permits exactly one more reservation; a fourth is blocked.
Default code remains two. Settings checks in complete synthetic public/Vercel
configuration accept 2, 3 and 5 and reject -1 and 6. No credential was needed for
that validation and no private environment file was loaded or edited.

This knob applies to **every session**, not a visitor-specific exception. It does
not reassign or expose other visitors' records. If used temporarily for recording,
an authorised operator can restore two afterward; existing third bookings remain
owned/readable and counters are not reset. No targeted override or migration was
added. Do not start another session to bypass ownership or resource controls.

At inspection, workspace write usage was 73/100 and global write usage 74/4000
under their previously confirmed unset/default settings. A rejected booking can
still consume its outer write reservation. Other quotas remain independent.
In particular the session has **three payment-attempt reservations**, already
the supported per-session maximum. Do **not** recommend payment cap four: its
field validator rejects values above three. Allowing another booking does not
authorise another payment or AI call. An already verified saved receipt can be
shown as its own historical capture scene; never attach it to a new booking.

## Confirmed performance evidence and limits

- User reports slow ordinary saved reads and one dashboard status unavailable.
- User supplied `public_setup_failure`: `database_readiness`, `database_identity`,
  `PoolTimeout`, empty failed checks and null SQLSTATE. That establishes pool
  acquisition failure **before** the identity SELECT, not a wrong database or
  proven connection leak. No endpoint/duration correlation was supplied for the
  individual failed row.
- User confirmed selected Vercel function region **iad1 (Washington)**. Read-only
  Neon project metadata confirms **aws-ap-southeast-1 (Singapore)**. The repository
  previously had no function-region pin. Region distance is a latency contributor,
  not proof of the pool exhaustion cause.
- No hosted request waterfall, SQL timing or post-fix speed measurement was
  collected. Neon MCP tool wall time is not an application/database benchmark.

Vercel recommends locating functions near their data source and supports the
`regions` project configuration; `sin1` is Singapore. See official
[function-region configuration](https://vercel.com/docs/functions/configuring-functions/region)
and [region codes](https://vercel.com/docs/regions). `backend/vercel.json` now
**prepares** `regions: ["sin1"]`. No hosted setting/deployment was changed.

## Before/after request and connection trace

Previously each dashboard booking independently loaded review state, latest
proposal, latest comparison, **all** rule history, attempts and eligibility in
parallel. It then fetched the agreement and, for completed attempts, receipt.
That is 6–8 GETs per booking, plus rule-history pagination, the booking list and
any entry/session request. A failure in any part rejects that row's `Promise.all`,
discarding even successful sibling status reads. Two reviewed bookings typically
need 15–17 booking-data GETs including the list. Names/list and creation are
independent, but the two-read queue could delay other rows' later status requests.

Opening a booking performed that fan-out again. Task screens separately load
their editable data and history on first visit; those reads are legitimate and
still exist. Visited forms remain mounted through navigation. Two listeners for
the same mutation notification also updated the parent's epoch and the journey's
local revision; the redundant journey listener is removed. Manual refresh remains.

Now dashboard and booking overview each request **one**
`GET /api/bookings/{booking_id}/saved-state`. Dashboard with two bookings needs
three booking-data GETs including the list. No fallback fan-out or retry is added.

The aggregate endpoint uses the existing owner/session dependency and shared
booking lock, one synchronous SQLAlchemy session/connection and the existing
review/comparison/rule/payment guard implementations. Writers take the same
booking lock exclusively, so the saved response is coherent. It returns only
the latest rule for each current agreement/proposal target; full history remains
on existing endpoints/screens. Eligibility is still recalculated server-side,
not inferred from displayed matching terms. Receipts come from immutable receipt
storage, never current terms; completed status without a receipt fails closed.
No provider operation, approval or write reservation is executed by this GET.

Every public request still checks database identity, revision, deployment marker,
enabled immutable protections, admission-control row, ownership column, exact
synthetic catalogue contents and applicable runtime/payment privileges. Readiness
now uses **two SELECT round trips** (identity, then one atomic JSON snapshot of
the remaining invariants), rather than seven plus runtime/payment checks.
There is no cross-request/session readiness cache. Batch SQL failures log fixed
`check=readiness_snapshot`; invariant failures retain their named failed checks.
`database_identity` / `PoolTimeout` remains distinguishable. No SQL, parameters,
sources or credentials are logged.

Request sessions retain their transaction/connection through read/response cleanup;
tests verify return to the pool on success and error. No leak or nested checkout
was found in the exercised saved-read path. The separate admission engine remains
for durable mutation/AI reservations. Inference paths still release their read
transaction before provider work. Pool size **2**, overflow **0**, pool wait **3s**,
connection timeout **3s**, statement timeout **5s**, lock timeout **3s**, pre-ping
and recycling are unchanged. No automatic retries or increased timeouts are used.

The frontend still bounds reads to two, cancels inactive snapshot reads and stops
hidden dashboard refreshes. It also checks cancellation after acquiring a queue
slot but before starting a fetch. Loading clears the summary instead of retaining
stale readiness/payment labels. Failed optional status is explicit per row; it
does not imply absent terms/bookings or disable creation. Malformed aggregate
responses fail visibly rather than becoming an empty or approved snapshot.
Unsaved forms remain mounted. Rule navigation treats a pending/failed parent
snapshot as **unknown**, not evidence that its saved source changed; real changes
and explicit saves still require normal version checks and discard warnings.

## Offline measurements and checks

Instrumented local SQL executions (not hosted latency):

| Synthetic fixture | Legacy summary GETs | Aggregate GETs | Legacy SQL | Aggregate SQL |
| --- | ---: | ---: | ---: | ---: |
| Empty booking, restricted runtime | 6 | 1 | 54 | 21 |
| Populated booking, four rule-history rows | 7 | 1 | 112 | 77 |

Both sides use the new batched readiness where applicable, so these counts measure
aggregation separately from the readiness reduction. SQL totals include transaction
setup; they are not query CPU or network-duration measurements. Tests confirm
current-rule selection and immediate approval freshness after writes, owner-only
reads, missing/expired sessions, private/no-cache responses, unchanged verified
receipt content and sandbox/provider restrictions. Controlled pool-occupancy
regressions still verify fail-closed timeout and connection cleanup.

Browser mocks hold one status indefinitely while the other completes; list names,
the healthy row and create form stay usable. A failed status stays local to its
row; explicit refresh retains the unsaved title and performs one new aggregate
read per row. Mutation notification refreshes only the active booking. Other
workspace/navigation/approval/receipt regressions use synthetic fetch fixtures;
their internal composition of old mocks is test transport, not production fan-out.

Verification completed locally:

- Original selected backend suite: **206 passed**. After the cumulative allowance
  change, the combined quota/read/payment suite passed **288 distinct tests** (286 combined plus two new AI-boundary checks), with six
  existing dependency warnings.
- After extending the restricted-role burst/lock/lifecycle tests to include
  `/saved-state`, those **6 checks passed** again; they are included in the
  selected suite, not six additional distinct tests.
- All **19 browser feature suites passed** across isolated synthetic fixtures,
  including connected blocker navigation and desktop/tablet/mobile flows.
- Frontend build/typecheck and offline read-queue/corroboration checks passed.
- Ruff lint/format passed for **144 Python files**; `git diff --check` passed.
- Browser tests now wait for rule confirmation's readback to finish before
  editing; checkout assertions target the active workspace instead of a hidden
  previously visited task. No approval, quota or ownership assertion was removed.

Run commands:

```sh
cd backend
uv run --frozen --offline pytest -q -x --tb=short \
  tests/test_saved_state_performance.py tests/test_hosting_preparation.py \
  tests/test_hosting_diagnostics.py tests/test_restricted_saved_state.py \
  tests/test_demo_sessions.py tests/test_hosted_sandbox_payments.py \
  tests/test_paypal_sandbox.py tests/test_paypal_webhooks.py \
  tests/test_legacy_corroboration_flow.py
uv run --frozen --offline ruff check .
uv run --frozen --offline ruff format --check .
cd ../frontend
node tests/corroboration.mjs
npm run build -- --config vite.qa.config.ts
# With isolated local Vite QA and Chrome CDP as described in frontend-redesign.md:
node tests/all-browser.mjs
```

Tests use mocked providers and disposable local PostgreSQL only. No development
or hosted records, credentials, sessions/counters or approvals were modified.

## Required rollout and hosted verification

1. The original one-line cap-three proposal is superseded by the complete
   [cumulative allowance rollout](usage-allowances.md). Apply its changed settings
   with compatible backend code; preserve all three hidden AI settings and the
   owning browser session. No Production setting was changed by this work.
2. Deploy the prepared backend first: new saved-state endpoint, batched readiness,
   and explicit `sin1` placement. Verify startup/settings/readiness succeeds and
   deployed execution region is `sin1`. No migration/grant change is required.
3. Deploy the frontend afterward. Existing leaf APIs remain supported for task
   workspaces and other clients; the new frontend requires the new endpoint.
4. Only then manually create “Smith - HTC camera rental”. The updated session
   cap is fifty, with existing usage still counted. Creation can remain blocked
   by unchanged hosted overrides until the operator applies the complete block. No booking was created
   during preparation. Source intake, AI generation, review and approvals remain
   separate explicit actions with their own limits.
5. Compare before/after ordinary GET measurements, excluding explicit AI/payment
   actions. Minimum evidence: endpoint suffix, HTTP status, duration and diagnostic
   category for `/bookings`, `/saved-state`, and one failed request if it recurs.
   Include execution region and whether failure is pool acquisition, invariant,
   settings or allowlisted SQLSTATE. Omit IDs, cookies, SQL, source text and secrets.

No claim is made that hosted speed improved or the failed row recovered. Other
visitors, long reads or infrastructure availability can still exhaust a bounded
pool; the remaining cause needs correlated hosted timings if it persists.
