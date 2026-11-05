# Merchant deposit/cancellation consistency — first increment

Both Buyer **Cancellation** and Merchant **Merchant policy rules** contain
**Merchant policy consistency → Check policy consistency**. One explicit request
checks all deposit and cancellation clauses together from the **latest saved merchant
proposal**. Buyer agreement clauses and unsaved forms are outside this check.
Loading, refreshing and switching workspace never invoke Gemini.

Findings are **Potential contradiction**, **Needs clarification**, or **No
contradiction found**, with a short explanation and expandable exact saved-clause
references. Full saved clause context and historical checks remain accessible.
These references identify immutable merchant-entered wording; they are not invented
source-document citations or independently verified merchant evidence. No precedence,
agreement amendment, rule approval, correction review or payment action is created.

## Inference and validation

`GeminiConsistencyChecker` extends the existing `GeminiPolicyComparator`, reusing
the official Google GenAI SDK, configured backend model/key, fixed Developer API,
60-second timeout, one total attempt, 8,000 output-token limit, disabled function
calling, allowlisted diagnostics and existing safe provider-error translation.
No dependency, credential, model selection, fallback or retry policy changed.

The server supplies all saved deposit/cancellation clauses in one context, with
stable category/index IDs, exact text and saved ambiguity flags. No unrelated
booking terms, identities, receipts or full evidence documents are sent. Input is
bounded at 100 clauses and 40,000 serialized characters; oversized context returns
413 rather than truncating clauses. All source text is untrusted data. The prompt
requires evaluation of conditions/scopes and explicit exceptions together: different
conditions can be compatible. Unclear exception relationships need clarification.
It forbids inventing precedence, selecting a governing clause, calculating money,
actions and approvals.

Full Pydantic validation rejects unsupported status values, empty findings, extra
action fields, oversized/blank explanations and mixed clean/conflicting outputs.
Each provider finding must reference both deposit and cancellation groups using
complete exact clause text, preserving case/whitespace. Unknown IDs, altered or
truncated quotes, duplicate references and one-sided support reject the result.
A clean finding must stand alone and reference **every** supplied clause, including
exceptions. Server-derived aggregate status uses the most cautious finding.
Literal support validation does not prove semantic correctness; findings are
AI-assisted, not a legal or policy guarantee.

Missing, placeholder or explicitly ambiguous saved terms produce a deterministic
**Needs clarification** completeness result without calling Gemini. It references
only available nonblank saved text and is labelled as a completeness check, not an
AI response. Provider outages/invalid outputs remain errors, never fabricated clean
or uncertainty findings. A failed request saves no result and clears no old blocker.

## Version, persistence and blocking boundaries

The existing common booking lock verifies the exact latest proposal ID/fingerprint
before inference. The transaction is released for the provider request. Afterwards
the session reloads, takes the same lock and rechecks the current proposal and exact
clause context before committing. Concurrent edits yield 409 and publish nothing.

Each append-only check retains proposal ID/version/fingerprint, all input clauses,
validated findings, safe model metadata, timestamp and its own fingerprint. Read
responses compute outdated status against the latest proposal without rewriting
history. Proposal edits invalidate earlier checks, including a new version with
similar wording. Historical findings remain visible in both workspaces.

`blocking_findings` is shared by existing cancellation rule reads and checkout
eligibility. Any conflict/uncertainty check bound to the exact current proposal
blocks definitive merchant refund previews, side-by-side previews involving that
proposal, rule confirmation and checkout approval/order/capture guards. Existing
approval rows remain immutable historical records; their current usability is
computed, never rewritten. An already-saved checkout approval cannot bypass a new
finding. Existing historical capture reconciliation and receipts remain intact.
Buyer-only agreement previews retain their separate existing requirements.

A later clean inference for the same proposal **cannot erase** an earlier current
blocking finding. Revise the proposal and explicitly check the new version. There
is no acknowledge-away, delete or automatic-resolution endpoint. Current findings
remain visible even if the most recent inference is clean.

This increment does **not** make absence of a check a new universal checkout gate:
unchecked means unknown, not consistent. Existing guards still apply. A clean check
does not establish eligibility, confirm terms, approve cancellation rules or replace
explicit checkout approval. Existing conservative cross-policy regex checks and
bounded Python rule validation remain; they may still block a conditional/complex
policy even when Gemini reports compatibility. A clean report does not make such
an unsupported refund schedule calculable. No monetary calculation moved to AI.

The UI retains unsaved rule inputs. Learning a blocking result clears prior refund
previews and marks matching merchant rules unusable locally from server state;
the backend independently rechecks every action. Refresh after changes in another
client. Existing explicit actions (including preview requests) may invalidate cached
reads; use **Refresh policy checks** when its adjacent guidance requests it. Local saved-state events remove current labels immediately. Failed checks
require explicit refresh before another request; no automatic generation or retry.
Demo views remain provisional and supply no backend authentication or permissions.

## API and migration

```http
POST /api/bookings/BOOKING_ID/policy-consistency
Content-Type: application/json

{
  "proposal_id": "EXACT_LATEST_SAVED_PROPOSAL_UUID",
  "proposal_fingerprint": "EXACT_64_HEX_FINGERPRINT"
}
```

201 returns the bound check, `status`, structured `output.findings`, saved `clauses`,
metadata, fingerprint and computed `stale`/`stale_reasons`. The POST can invoke
Gemini on a configured normal backend; use the mocked verification below instead
for provider-free checks. Wrong booking/proposal yields 404; stale bindings or
concurrent edits yield 409; oversized context 413; invalid body 422; shared provider
errors use safe 502/503/504 responses. No automatic retries or provider fallback.

Read-only endpoints never invoke inference:

```http
GET /api/bookings/BOOKING_ID/policy-consistency?limit=20&offset=0
GET /api/bookings/BOOKING_ID/policy-consistency/state
```

History is paginated; the UI loads all pages. State returns the current proposal
binding and current blocking findings, independent of the last report shown.
No result update/delete route was added.

Implementation initially left **0012_policy_consistency unapplied** to development;
the separately authorized rollout below has now applied it. It adds
only `policy_consistency_checks`, two foreign keys, indexes and an immutable
UPDATE/DELETE rejection trigger. Tests apply migrations to randomly named disposable
PostgreSQL databases only. Development records and credentials were not accessed
or changed during implementation. Use on another database needs an authorized
`cd backend && uv run --frozen alembic upgrade head` rollout and backend reload/restart
if routes have not reloaded. Do not run this migration as part of the mocked UI steps.

### Authorized development rollout — 2026-11-04

Ran `cd backend && uv run --frozen alembic upgrade head` successfully against the
configured loopback-local PostgreSQL database, advancing from 0011. Both
`alembic current` and `alembic heads` returned **0012_policy_consistency (head)**.

Read-only repeatable-read snapshots matched counts and SHA-256 row fingerprints
for every one of the **18 pre-existing application tables**. No additional
application-table schemas were found. Alembic revision metadata is excluded from
the data comparison because advancing that revision is the intended migration.

| Pre-existing table | Before | After |
| --- | ---: | ---: |
| agreement_confirmations | 3 | 3 |
| agreement_versions | 7 | 7 |
| booking_comparisons | 6 | 6 |
| bookings | 4 | 4 |
| cancellation_rule_approvals | 6 | 6 |
| cancellation_rule_versions | 7 | 7 |
| checkout_approvals | 4 | 4 |
| clarification_correction_reviews | 1 | 1 |
| clarification_replies | 1 | 1 |
| clarification_suggestions | 1 | 1 |
| draft_versions | 4 | 4 |
| evidence_pages | 1 | 1 |
| evidence_sources | 6 | 6 |
| merchant_booking_versions | 6 | 6 |
| payment_attempts | 3 | 3 |
| payment_events | 15 | 15 |
| paypal_webhook_events | 2 | 2 |
| sandbox_receipts | 2 | 2 |

The new `policy_consistency_checks` table contains zero rows. Read-only catalog
inspection verified its 11 expected columns, JSONB output/clauses/metadata storage,
nullability, primary key, two validated foreign keys and booking/proposal indexes.
The enabled BEFORE UPDATE OR DELETE row trigger calls
`contextkey_reject_review_mutation()`; its inspected body raises an unconditional
exception. No development mutation was attempted to exercise that trigger;
behavioral enforcement was previously tested in disposable PostgreSQL.

A GET-only check of local backend OpenAPI confirmed policy-consistency GET/POST
and state GET routes are already loaded. **No backend restart was needed or
performed.** No application/test records were created, credentials edited or
Gemini/PayPal calls made. Normal configuration was loaded without printing secrets
or record contents. Tests were not rerun for this migration-only rollout.

## Precise provider-free UI verification

Prerequisites: installed project dependencies, supported Node and Chrome. From the
repository root, run in separate terminals:

```sh
npm --prefix frontend run dev:qa
```

```sh
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --disable-gpu --no-first-run --no-default-browser-check \
  --remote-debugging-port=9228 \
  --user-data-dir=/private/tmp/beforepay-policy-consistency-demo about:blank
```

```sh
FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 \
  node frontend/tests/policy-consistency.browser.mjs
```

QA Vite loads no environment files and has no backend proxy. The script installs
synthetic responses in its dedicated tab before navigation and blocks provider
origins. Omit `--headless=new` to watch. Run browser suites sequentially. Captures go
to `/private/tmp/beforepay-policy-consistency/`.

For hands-on checks after running that script once with visible Chrome, keep the
same debugging tab open; fixtures belong to that tab:

1. Navigate to `http://127.0.0.1:5187/?case=ready#merchant/bookings`. Fresh navigation
   resets synthetic state and selects Merchant demo. Open **Cinema kit · November
   shoot**, then **Merchant policy rules**.
2. Find **Merchant policy consistency** above rule authoring. Expect **No current
   policy check**. Click **Check policy consistency** once. Expect a saved
   **Potential contradiction** result and the server-blocking explanation.
3. Expand each **exact supporting saved clause** and **All saved deposit and
   cancellation clauses**. Read conditions/exceptions without treating them as
   document citations or assuming one overrides another.
4. Switch to Buyer using `buyer.demo / BuyerDemo123!`, open **Cancellation**, then
   **Refresh policy checks**. The same merchant finding must appear. Choose
   **Merchant-proposed · latest booking** as policy source: this finding must not
   allow a definitive merchant refund result or bypass rule approval requirements.
5. To simulate a proposal revision in the dedicated tab's console:

   ```js
   window.__proposalChanged = true;
   window.dispatchEvent(new Event('contextkey:changed'));
   ```

   Click **Refresh policy checks** and expand **Outdated policy-check history**.
   Old wording/results remain, labelled outdated. No current check is equivalent
   to neither a clean finding nor approval.
6. Freshly reload the step 1 URL for each fixture mode. Before requesting a check:

   ```js
   window.__policyMode = 'no_contradiction_found'; // compatible explicit exception
   // Or, after a fresh reload:
   window.__policyMode = 'needs_clarification';
   window.__policyMode = 'invalid'; // simulated unsupported provider references
   window.__policyMode = 'failure'; // simulated provider timeout
   window.__policyMode = 'changed'; // simulated edit during inference
   ```

   Use one mode per fresh page. Clean/uncertain results must keep the no-approval
   notice. Errors must show no invented result, disable rechecking until explicit
   refresh and perform no automatic retry. These are test flags, not production API
   parameters. Frontend mocks demonstrate display; they do not prove classification
   quality or actual reference validation.

Close the dedicated QA Chrome and stop QA Vite afterwards. Do not use the normal
backend's check button during provider-free verification; it may make a live call.

## Provider-free backend verification

```sh
cd backend
uv run --frozen pytest -q tests/test_policy_consistency.py
```

The test fixture uses `Settings(_env_file=None)`, blocks live Gemini/PayPal, migrates
only its disposable PostgreSQL database and drops that database afterwards. Tests
cover conflicting clauses, compatible explicit exceptions, missing terms, exact
reference validation/coverage, provider failure, concurrent edits, stale results,
size limits, immutable history, approved refund/checkout blocking, capture guards,
historical receipt preservation and the mocked existing SDK transport seam.
Classification is mocked; this is not evidence of a live Gemini semantic judgment.

## Automated verification — previous mocked runs

- `cd backend && uv run --frozen pytest -q`: **440 passed**, six existing dependency
  warnings. Focused consistency coverage: **20 passed**. Actual disposable PostgreSQL
  applied 0012 and verified immutable history; provider responses/SDK seam mocked.
- Backend Ruff lint and format checks passed (**101 Python files**).
- Frontend TypeScript/Vite build passed; dependencies/lockfiles unchanged.
- New consistency browser suite: **26 passed** at desktop 1440×1000, tablet
  834×1112 and mobile 390×844. Existing suites: **674 passed**. Combined **700 mocked
  browser assertions**, including existing payment and receipt regressions.
- Static branding/compatibility checks: **32 passed**.
- [Synthetic responsive captures](screenshots/beforepay-policy-consistency/index.md)
  reviewed for both workspaces, exact support, blocking notices and retained inputs.

Initial verification exposed test-harness issues: the oversized-context test first
exceeded the pre-existing individual-clause save limit; the preview UI test needed
the Buyer calculator with merchant policy selected and an explicit policy refresh
after preview invalidated cached reads. Corrected fixtures/selectors; focused and
full reruns passed. No application guard was weakened to pass these tests.

No live Gemini/PayPal request, development migration, development-record or
credential change, deployment or publication occurred. Browser checks use Chromium
viewport emulation and accessible-name inspection; physical devices, other browser
engines and a dedicated screen-reader audit remain unverified. Real semantic quality
and a live check are not demonstrated by these mocked results.

## User-reported live verification — 2026-11-04

The user reported the following manual observations from a live policy-consistency
check. These observations are separate from the earlier mocked automated results
above; this documentation update did not reproduce or independently audit them.

1. A conflicting merchant proposal returned **“Potential contradiction”**, with
   the exact supporting deposit and cancellation clauses displayed. Checkout
   showed the corresponding policy-consistency blocker.
2. A corrected **new merchant proposal version** returned **“No contradiction
   found.”** The corresponding policy-consistency blockers disappeared, while
   **stale-comparison and rule-approval blockers remained**.

The reported clean result belongs to the corrected proposal version. It does not
demonstrate that rerunning inference against an unchanged proposal can erase an
earlier blocking finding. Results remain bound to their saved proposal versions;
the implementation retains historical checks rather than overwriting them. Record
preservation was not independently inspected during this documentation update.

Clearing the reported policy-consistency blockers did not remove the remaining
comparison and rule-approval requirements. A clean result is not agreement,
cancellation-rule or checkout approval, and does not by itself establish payment
eligibility. This report does not establish successful checkout or payment, or
live coverage of every failure and concurrency case.

No proposal IDs, clause text, provider response identifiers or check timestamps
were supplied for this report, so none are inferred here. The date above records
the report date. No records or credentials were changed, tests rerun, or new
Gemini/PayPal calls made for this documentation-only update.
