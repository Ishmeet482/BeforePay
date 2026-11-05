# Advisory clarification suggestions — first increment

Buyer comparison now offers **Suggest clarification** beside saved `differs` and
`needs_clarification` sections. One explicit request may ask Gemini for a merchant
question, a short explanation and supporting saved terms. Nothing is sent to a
merchant automatically. The first increment adds no reply, negotiation, resolution,
agreement/proposal modification, approval or payment action. A suggestion never clears a discrepancy
or changes checkout eligibility.

The subsequent [merchant reply increment](merchant-replies.md) adds explicitly saved,
provisional statements and shared history. Replies remain unverified and cannot
resolve discrepancies or change terms/approvals/payment eligibility.

## Saved context and validation

The server selects one category from the requested existing comparison. It verifies
that its terms equal those in the bound immutable agreement and merchant proposal.
Only that category's complete saved terms, discrepancy status/reason, provenance
and already validated supporting citation excerpts enter the prompt. Full source
documents, unrelated categories, identities and payment payloads do not. Policy
text is verbatim; other typed terms use deterministic JSON field serialization,
without arithmetic. References to saved terms are distinct from document citations.
Customer-entered terms and merchant-entered proposals never gain invented citations.

The prompt treats every term/citation as untrusted data; no tools, retrieval,
precedence selection, money calculation, actions or approvals are permitted. It
requires one question, not an asserted agreement or resolution. Full Pydantic
validation rejects extra action fields, blank/oversized text and non-question
output. Every model reference must name an available term and quote that **complete
exact term**, including case/whitespace. Unknown IDs, altered/truncated quotes,
duplicate references or one-sided support reject the response. A successful
question requires support from both sides. The server supplies original citation
IDs/pages from saved data; the model cannot invent or attach provenance.

Missing, ambiguous, placeholder or unsupported saved information returns
**Needs more information**, with no question. Known incomplete context is declined
locally without a provider call. Gemini may also explicitly decline with this
status. A provider error is an error, never a fabricated insufficient/success result.
Literal reference validation does not prove the semantic quality of the question
or explanation: users must assess this advisory prose against the visible terms.

## Provider and transaction boundaries

Reuses the existing `GeminiPolicyComparator` transport via `GeminiClarifier`:
configured backend model/key only, Google GenAI Python SDK, fixed Developer API,
60-second timeout, one total attempt, maximum 8,000 output tokens, no function calls,
retries or fallback. Relevant input is bounded at 40,000 serialized characters.
Shared allowlisted diagnostics/error classification remain; no raw prompts,
provider outputs, secret values or customer text are logged. No dependency change.

Before inference, take the common booking lock and require the exact fingerprint,
latest saved comparison, current agreement/proposal and current confirmation/evidence.
Release the transaction before inference. Afterwards reload and reacquire the same
lock, then repeat these checks before validating against the saved terms and
committing an append-only suggestion. Changes during inference yield 409 and save
nothing. A newer comparison supersedes prior suggestions even with identical
underlying version IDs. Generation never holds a booking lock across a model call.

Migration **0009_clarification_suggestions** adds only the suggestion table, foreign
keys/indexes and an UPDATE/DELETE rejection trigger. Rows bind comparison ID and
fingerprint, agreement/proposal IDs and fingerprints, confirmation ID, category,
validated output/support snapshots, safe model metadata and their own fingerprint.
No existing row is rewritten. Read responses compute `stale`/`stale_reasons` under
the booking lock without changing history. Existing payment code is untouched.

## UI behaviour

In Buyer demo, open a booking → Compare booking → a changed/uncertain section.
Click **Suggest clarification**. Read the merchant question and why clarification
is needed. Expand either **open exact supporting term** control. Source-supported
buyer terms additionally open the existing original-source/PDF-page evidence drawer;
merchant terms are explicitly labelled saved merchant-entered wording.

No generation on page load, selection, refresh or workspace switch. Refresh
suggestions only performs a GET. Unsaved merchant edits, non-current confirmation,
stale/older selected comparisons, loading and an in-flight generation disable the
control with a specific explanation. Existing forms/reasons stay mounted and intact.
Known local writes immediately remove the current label until rechecked. Server-stale
records remain explicitly **Historical / not current**. Earlier suggestions stay in
collapsed history. “Current at last check” is a read-time snapshot, not a realtime
push guarantee; refresh after changes from another client. Every POST rechecks the
server state independently. Demo roles still supply no backend access control.

## Provider-free local UI verification

Prerequisites: installed project dependencies, supported Node version and Chrome.
These commands use **no real backend/database or provider**.

1. From repository root, start the environment-free QA server in one terminal:

   ```sh
   npm --prefix frontend run dev:qa
   ```

2. Start a dedicated Chrome profile in another terminal (macOS command):

   ```sh
   '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
     --headless=new --disable-gpu --no-first-run --no-default-browser-check \
     --remote-debugging-port=9228 \
     --user-data-dir=/private/tmp/beforepay-clarification-review about:blank
   ```

   Omit `--headless=new` to watch the isolated mocked journey interactively.
   Use a free debugging port and update `CDP_URL` if needed.

3. In a third terminal, from repository root:

   ```sh
   FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 \
     node frontend/tests/clarifications.browser.mjs
   ```

   The script installs synthetic API responses before navigating and blocks
   PayPal/Google provider origins. It checks explicit generation, exact binding,
   evidence controls, insufficient information, invalid-reference/provider/version
   errors, stale history, unsaved edits and desktop/tablet/mobile layouts. It writes
   captures to `/private/tmp/beforepay-clarifications/`. Running scripts sequentially
   avoids mixing synthetic transports in a debugging page. QA Vite has no backend
   proxy and does not load environment files. A normal browser page without the
   fixture is not a mocked full backend.

### Hands-on UI steps in the mocked browser

No development migration or normal backend is needed for this mocked verification.
It remains isolated from development records. Use the QA server and dedicated Chrome commands above, omitting
`--headless=new`, then run the browser script once to install its synthetic transport.
Keep that same debugging tab open; the fixture installation belongs to that tab.

1. In that tab, navigate to
   `http://127.0.0.1:5187/?case=changed#bookings`. A fresh navigation resets only
   synthetic fixture state and selects Buyer demo. Do not use your ordinary app tab.
2. Find **Cinema kit · November shoot**, then click its next action
   **Resolve deposit change**. This opens **Compare booking**.
3. In **Deposit conditions**, read both saved versions. Below them, find
   **Ask before agreeing** and click **Suggest clarification**. Loading this page
   alone must not generate a question.
4. Expect a question about the USD 80 deposit, a short explanation, and
   **Current at last check · advisory**. **Resolve before checkout** must remain.
5. Expand **Buyer agreement · open exact supporting term**, then click
   **View evidence**. Inspect the original-source drawer; close it with Escape.
   Expand **Merchant proposal · open exact supporting term** and check its saved
   non-refundable wording and explicit merchant-entered/no-document-citation label.
6. To inspect stale handling, run this in that tab's developer console:

   ```js
   window.__staleSuggestion = true;
   window.dispatchEvent(new Event('contextkey:changed'));
   ```

   The current label must disappear immediately. Click **Refresh suggestions**;
   the record must stay **Historical / not current**, with generation disabled.
   This changes mock state only, not saved application records.
7. Reload the same URL to reset the fixtures. For each negative case, set one of
   the following console values before clicking **Suggest clarification**:

   ```js
   window.__suggestMode = 'insufficient';     // Needs more information; no question
   // Or, after a fresh reload:
   window.__suggestMode = 'bad_reference';    // Safe invalid-output error; no result
   window.__suggestMode = 'provider_failure'; // Safe timeout error; no automatic retry
   window.__suggestMode = 'changed';          // Stale-input error; no result
   ```

   Use one mode per fresh page. These are test-fixture controls, never production
   API parameters. Actual reference validation and changes during inference are
   tested through the backend suite below, not proved by frontend mock responses.

Close the isolated Chrome window and stop QA Vite when finished. No merchant reply,
resolution, approval or checkout action is part of this verification.

## Provider-free local API/database verification

A local PostgreSQL server must be available to the existing test fixture. It uses
`Settings(_env_file=None)`, creates a randomly named **disposable test database**,
applies all current migrations there and drops only that database afterwards.
It does not read developer `.env` files or migrate the development database. Tests
block live Gemini/PayPal constructors and override the clarification provider.

```sh
cd backend
uv run --frozen pytest -q tests/test_clarifications.py
```

For the full regression suite, run `uv run --frozen pytest -q`. A database connection
or CREATE DATABASE permission failure is an infrastructure prerequisite, not proof
of a working integration. Do not point tests at a remote production server.

The tests create synthetic confirmed agreements/proposals/comparisons and exercise
real FastAPI routes and PostgreSQL transactions/triggers, including a second request
changing versions/evidence during the mocked inference. They verify that comparison,
confirmation, payment eligibility and prior saved inputs remain unchanged.

### API contract (examples, not live-call instructions)

Get the existing comparison ID/fingerprint from the saved comparison response.
The clarification routes are booking-scoped:

```http
POST /api/bookings/BOOKING_ID/comparisons/COMPARISON_ID/clarifications
Content-Type: application/json

{
  "comparison_fingerprint": "EXACT_64_HEX_FINGERPRINT",
  "category": "deposit_conditions"
}
```

Only that POST can invoke Gemini when sufficient context exists. A complete-context
POST to a real configured backend is a **live model call** and is outside the
current no-provider verification scope; use the mocked tests above instead.

Read-only history (no inference):

```http
GET /api/bookings/BOOKING_ID/comparisons/COMPARISON_ID/clarifications?category=deposit_conditions&limit=20&offset=0
```

201 returns a bound record with `output.status` = `suggested` or
`needs_more_information`, question/explanation/references, resolved `supporting_terms`,
metadata and computed staleness. GET returns a paginated list, including stale
history. Category may be any of the eight comparison categories; matching sections
are rejected. Typical failures: 404 wrong booking/comparison, 409 stale inputs or
superseded comparison, 413 oversized relevant context, 422 invalid request/matching
section, 502 invalid model output/references or unavailable provider, 503 missing
configuration/quota/access rejection, 504 timeout. Errors save no suggestion and
trigger no retry. No suggestion update/delete, resolve or approval route exists.
The separate reply routes are documented in [Merchant replies](merchant-replies.md#api).

## Development rollout applied — 2026-11-03

With explicit user authorization, ran the documented command against the configured
local development database:

```sh
cd backend
uv run --frozen alembic upgrade head
```

`alembic current` and `alembic heads` both reported
`0009_clarification_suggestions (head)`. Before/after read-only SHA-256 row
fingerprints and counts matched for all **15 pre-existing tables**, including:

| Records | Before | After |
| --- | ---: | ---: |
| Bookings | 4 | 4 |
| Checkout approvals | 4 | 4 |
| Payment attempts | 3 | 3 |
| Payment events | 15 | 15 |
| Sandbox receipts | 2 | 2 |
| PayPal webhook records | 2 | 2 |

The new suggestion table contains zero rows; its immutable trigger is enabled.
No test records, payment actions or provider calls were made. Application
configuration was loaded normally without printing credentials or row payloads;
credential/environment files were not edited. The running backend's read-only
OpenAPI document already exposes GET and POST clarification routes, so no restart
was needed or performed. Normal-backend Suggest clarification can invoke Gemini;
live inference remains outside this migration-only authorization.

## Verification results

- `cd backend && uv run --frozen pytest -q`: **379 passed**, six existing dependency warnings. New clarification coverage: **25 tests**. Real disposable PostgreSQL applied 0009 and enforced append-only triggers; all model/payment providers mocked.
- Backend Ruff lint and formatting passed (**86 Python files**).
- Frontend TypeScript/Vite build passed; no dependency/lockfile changes.
- Clarification browser suite: **36 passed**. Existing journey/workspace/alignment/booking-entry/demo-login/item/SDK regressions: **569 passed**. Combined **605 browser assertions**; no live providers or real backend.
- Static branding/compatibility checks: **29 passed**.
- [Synthetic desktop/tablet/mobile captures](screenshots/beforepay-clarifications/index.md) visually reviewed, including exact support, source drawer, unchanged blocking comparison and insufficient-information presentation.

No real booking/payment records, secret files, live provider calls, deployment or publication were used. Browser
checks use Chromium viewport emulation; physical devices, other browser engines
and a dedicated screen-reader audit remain unverified. These results describe the
first increment; subsequent merchant reply work is documented separately. Actual
resolution remains unimplemented.

Subsequent [explicit correction-review history](clarification-corrections.md) records
human review of exact corrected versions. It does not infer resolution from reply
text, automatically resolve issues or grant checkout approval.

## Subsequent user-reported manual verification — 2026-11-04

The user reports a live clarification with exact supporting terms, a merchant reply
visible to the buyer without unblocking checkout, stale old context after a corrected
proposal, and a fresh comparison that now matches. See the
[manual report and evidence limits](merchant-replies.md#user-reported-manual-verification--reported-2026-11-04).
These observations are separate from the earlier mocked test results. This update
made no provider calls or record changes and reran no tests. A reply is not a
verified resolution; a matching comparison is not approval or proof of payment.
