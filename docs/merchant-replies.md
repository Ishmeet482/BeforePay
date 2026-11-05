# Merchant clarification replies

Merchant demo now has a **Clarification replies** task for each shared booking.
It lists existing saved questions and both exact supporting terms, including the
existing source/PDF evidence controls. It does not generate questions automatically.
Buyer **Compare booking** shows the same reply history after **Refresh suggestions**
or the comparison's **Refresh** action.

Every reply is labelled **Merchant response—not verified resolution**. A merchant
label is user-entered, provisional information, not authenticated identity. Demo
workspace selection provides no backend access control. Reply text is displayed
as plain text; it is not sent to Gemini or interpreted as new terms, a resolution,
an approval or payment authority. Existing discrepancies continue to block checkout.
Use **Edit proposal as a new version** for an actual change to merchant terms;
the existing revision reason, save and comparison/review safeguards still apply.

The subsequent [explicit correction-review history](clarification-corrections.md)
lets the buyer record review of a corrected proposal and fresh matching comparison.
It links back to the original suggestion/reply without turning that reply into a
verified resolution, changing terms or approving checkout. History is visible here
in Merchant Clarification replies and in Buyer Compare booking.

## Persistence and stale context

New `clarification_replies` records bind the booking, exact suggestion ID/fingerprint,
comparison ID/fingerprint and merchant proposal ID/fingerprint. Suggestion bindings
already include the buyer agreement and confirmation context. The backend takes
the common booking lock, checks the latest current comparison, exact submitted
references and current suggestion context, then appends a new reply. Repeated
explicit saves append separate statements; there is no edit/delete/resolve endpoint.
Database UPDATE/DELETE triggers preserve history. Whitespace-only labels/responses,
NUL characters, oversized text and unexpected fields are rejected. Labels permit
100 characters; response text permits 5,000 characters. Original entered wording
and line breaks are retained.

A later proposal, comparison, agreement, confirmation or evidence change invalidates
the context using the existing suggestion/version checks. POST rejects stale context
with 409; historical GET remains available with computed `stale` and `stale_reasons`.
Reads never rewrite history. Current means **at last refresh**, not live push state.
Local saved-input events immediately remove current labels; refresh after another
client's changes. Server checks apply independently of frontend state.

Unsaved merchant label/response fields remain mounted through ordinary workspace
navigation, proposal editing and role switching. A page unload warns when fields
are dirty. Errors preserve fields, show an explicit failure and require refresh;
no automatic retry. A pending-submit guard prevents a double click from making
concurrent duplicate requests. A lost POST response remains uncertain until history
is refreshed; no claim of exactly-once delivery across explicit manual retries.

## API

All routes use the existing booking-scoped API. No provider dependency is involved:

```http
GET /api/bookings/BOOKING_ID/clarifications?limit=20&offset=0
GET /api/bookings/BOOKING_ID/comparisons/COMPARISON_ID/clarifications/SUGGESTION_ID/replies?limit=20&offset=0
POST /api/bookings/BOOKING_ID/comparisons/COMPARISON_ID/clarifications/SUGGESTION_ID/replies
Content-Type: application/json

{
  "suggestion_fingerprint": "EXACT_SAVED_SUGGESTION_FINGERPRINT",
  "comparison_fingerprint": "EXACT_SAVED_COMPARISON_FINGERPRINT",
  "proposal_id": "EXACT_SAVED_PROPOSAL_UUID",
  "proposal_fingerprint": "EXACT_SAVED_PROPOSAL_FINGERPRINT",
  "merchant_label": "Provisional rental desk",
  "response": "Please review a new proposal before agreeing to any changed terms."
}
```

POST returns 201 with the immutable reply and computed context status. Wrong
booking/comparison/suggestion yields 404, invalid/empty input or a Needs more
information entry without a question yields 422, stale or mismatched bindings
yield 409. Lists are paginated; the UI loads all reply and merchant inbox pages.
The existing Buyer suggestion list retains its current 20-per-category display.

## Migration and rollout

Implementation initially left **0010_clarification_replies unapplied** to the
development database. The separately authorized rollout below has now applied it. It
adds only this table, foreign keys/indexes/check constraints and immutable trigger.
Existing tables/records and all payment code remain intact. Tests apply it to a
random disposable PostgreSQL database, then drop only that test database. Migration
0009 was applied during the separately authorized earlier rollout.

For another database, apply the documented
`cd backend && uv run --frozen alembic upgrade head` command only when authorized,
then restart a backend process that has not reloaded the new routes. Implementation
did neither. It did not read or change credentials, existing booking/payment records
or environment files. No Gemini/PayPal call was made.

### Authorized development rollout — 2026-11-04

Ran `cd backend && uv run --frozen alembic upgrade head` successfully against the
configured loopback-local PostgreSQL database. `alembic current` and `alembic heads`
both returned **0010_clarification_replies (head)**, advancing from 0009.

Read-only repeatable-read snapshots before/after compared row counts and SHA-256
fingerprints for all **16 pre-existing tables**; every table matched exactly.

| Protected records | Before | After |
| --- | ---: | ---: |
| Bookings | 4 | 4 |
| Clarification suggestions | 1 | 1 |
| Payment attempts | 3 | 3 |
| Sandbox receipts | 2 | 2 |

The new reply table has zero rows and its immutable trigger is enabled. No test or
business records were created. Project configuration was loaded normally without
printing credentials, row contents or payment payloads; no credentials were edited.
No Gemini/PayPal calls occurred. A GET-only check of local backend OpenAPI confirmed
the inbox GET and reply GET/POST routes are already loaded. **No backend restart
was needed or performed.** This route check does not submit a reply or test providers.

## Provider-free verification

Backend tests use the existing disposable PostgreSQL fixture, never developer
`.env`, and block live providers. They exercise real persistence/immutable triggers,
multiple statements, blank/invalid replies, exact context guards, stale proposals,
superseding comparisons/evidence, cross-booking isolation, unchanged saved versions
and checkout eligibility/blocking:

```sh
cd backend
uv run --frozen pytest -q tests/test_merchant_replies.py tests/test_clarifications.py
```

For UI verification, from repository root, use three terminals:

```sh
npm --prefix frontend run dev:qa
```

```sh
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --disable-gpu --no-first-run --no-default-browser-check \
  --remote-debugging-port=9228 \
  --user-data-dir=/private/tmp/beforepay-merchant-replies-review about:blank
```

```sh
FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 \
  node frontend/tests/merchant-replies.browser.mjs
```

Omit `--headless=new` to watch. This environment-free Vite configuration has no
backend proxy. The script installs synthetic API responses in its dedicated tab
before navigation and blocks provider origins. Running browser suites sequentially
avoids mixing fixtures. Captures go to `/private/tmp/beforepay-merchant-replies/`.
Frontend mocks demonstrate presentation/navigation; backend tests establish real
database behavior. Neither constitutes live provider or authenticated-role testing.

### Exact hands-on UI steps

After running the browser script once with a visible dedicated Chrome window,
keep that same debugging tab open; fixture installation belongs to that tab.

1. Navigate in that tab to
   `http://127.0.0.1:5187/?case=changed#merchant/bookings`.
   This fresh navigation resets synthetic data only and selects Merchant demo.
2. Open **Cinema kit · November shoot**, then **Clarification replies** in the
   booking navigation. Read the saved deposit question, the refundable buyer
   condition and the merchant's non-refundable USD 80 condition. Open **View
   evidence** beside buyer support; Escape closes the drawer.
3. Enter **Merchant label (provisional)** and **Response text**. Save with
   **Save merchant response**. Expect the exact warning label, your statement,
   date and provisional label. Empty or whitespace-only text cannot be saved.
4. Enter a follow-up without saving. Choose **Edit proposal as a new version**,
   then return to **Clarification replies**. Your draft must remain. Save it to
   append a second statement; the first statement must remain unchanged.
5. Use **Switch role**, select Buyer and enter `buyer.demo / BuyerDemo123!` if
   prompted. Open **Compare booking**, then **Refresh
   suggestions** (or the comparison's **Refresh**). Both responses must appear
   read-only. **Resolve before checkout** must remain; no approval is created.
6. To simulate changed saved context, use the dedicated tab's developer console:

   ```js
   window.__replyStale = true;
   window.dispatchEvent(new Event('contextkey:changed'));
   ```

   Reply labels become historical/noncurrent. In Merchant **Clarification replies**,
   click **Refresh questions & replies**, expand **Historical context**, and check
   saved history remains visible while submission is disabled. Unsaved drafts
   remain available inside the historical section.
7. Freshly reload the URL in step 1 for each simulated error. Before saving, set
   `window.__replyMode = 'stale'` or `'failure'`. Expect an error, retained input,
   no invented saved reply and no automatic retry. For an empty inbox set
   `window.__noQuestions = true`, then refresh. These flags exist only in fixtures.

Do not click **Suggest clarification** on the normal backend during provider-free
verification: that existing explicit action can invoke Gemini. Close only the
isolated QA Chrome and stop QA Vite afterwards. This stage adds no merchant
negotiation resolution, verified identity, notifications or backend authorization.

## Automated verification — previous mocked runs

- `uv run --frozen pytest -q`: **395 passed**, six existing dependency warnings.
  Focused reply/suggestion suite: **41 passed**, including **16 new reply cases**.
  Real disposable PostgreSQL applied migration 0010 and enforced immutable triggers.
  Gemini/PayPal boundaries were mocked/blocked.
- Backend Ruff lint and format checks passed (**89 Python files**).
- Frontend TypeScript/Vite production build passed; dependencies/lockfiles unchanged.
- New mocked Merchant/Buyer browser suite: **36 assertions passed** at desktop
  1440×1000, tablet 834×1112 and mobile 390×844. Existing clarification, redesign,
  workspace, alignment, creation, demo-login, item and sandbox SDK regressions:
  **605 passed**. Combined **641 browser assertions**. The item/SDK scripts needed
  explicit `CDP_URL` because their default is the older QA port; rerun passed.
- Static branding/compatibility checks: **30 passed**.
- [Synthetic screenshots](screenshots/beforepay-merchant-replies/index.md) visually
  reviewed for supporting terms, response history, form controls and narrow layouts.

These browser checks used Chromium viewport emulation and accessible-name inspection,
not a physical-device or dedicated screen-reader audit. The implementation checks
did not test or add real merchant identity, notification delivery, production access
control or live provider integration. They avoided the development database; the
separately authorized migration rollout is recorded above.

## User-reported manual verification — reported 2026-11-04

The user reported the following observations from a manual live workflow:

1. A live clarification was generated with the exact supporting buyer-agreement
   and merchant-proposal terms displayed.
2. A merchant reply appeared in the Buyer workspace. The reply did **not** unblock
   checkout; it remained an unverified statement rather than a resolution.
3. A corrected merchant proposal made the old clarification/reply context stale.
4. A fresh comparison of the corrected saved versions now shows a match.

These are **user-reported manual observations**, distinct from the earlier mocked
automated results above. This documentation update did not independently inspect
database records, provider responses, logs or screenshots, reproduce the workflow,
or rerun tests. No booking/version IDs, exact question/reply text or execution
timestamps were supplied; none are inferred. The date is when the report was recorded.

The reported matching result belongs to a fresh comparison after a proposal
correction; the merchant reply itself did not resolve the discrepancy or amend
terms. A matching comparison does not establish checkout eligibility, agreement or
policy approval, payment capture, or authenticated merchant identity. Existing
explicit approvals and backend payment guards still apply. Demo identity remains
provisional and replies remain **Merchant response—not verified resolution**.

Only documentation changed while recording this report. No new AI/PayPal calls,
application-record changes, credential changes or test reruns were performed.
