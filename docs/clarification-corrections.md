# Explicit correction review history

Buyer **Compare booking → Clarifications & correction history** keeps saved questions
reachable after the merchant corrects a proposal and a fresh comparison matches.
**Review correction** reads the original discrepancy/supporting terms, merchant
statement, candidate corrected proposal and fresh saved comparison together. It
does not generate a suggestion or comparison. Source-backed original terms retain
their evidence controls. A buyer must enter a provisional reviewer label and note
before explicitly clicking **Record correction reviewed**.

The saved outcome is **Correction reviewed for these versions—not checkout approval.**
Merchant **Clarification replies** shows the same append-only history read-only,
including snapshots of the reviewed context. The old question/reply will normally
be historical because a correction needs a newer proposal; this does not itself
make the correction-review record outdated. Its status uses the corrected versions.

## Backend contract and safeguards

The existing booking row lock covers validation, duplicate lookup and commit.
Every POST re-reads authoritative saved context; browser flags cannot authorize it.
No Gemini/PayPal provider is a dependency of these new routes. Requirements:

- Original suggestion must describe a saved discrepancy for the same booking;
  original comparison, buyer agreement/confirmation and merchant proposal references
  must agree exactly with their persisted fingerprints.
- A saved merchant reply must belong to that exact suggestion/comparison/proposal.
  One reply can be selected unambiguously; multiple replies require explicit
  selection. Missing or unrelated replies cannot establish a review. The response
  text is never interpreted as proof of changed terms or resolution.
- The buyer agreement ID/fingerprint and confirmation ID must remain unchanged
  from the original question. Existing confirmation/evidence checks must be current.
- The current latest comparison must bind a newer merchant proposal version, with
  an actual change to the question's affected proposal terms (including an explicit
  included-items-none change when relevant). Saving an unchanged proposal does not
  establish a correction.
- All eight comparison categories must be present exactly once and match, with
  no unresolved comparison blockers. The affected category must match too. Saved
  terms are checked against exact underlying versions. Existing Python comparison
  planning rechecks deterministic values and missing/ambiguous terms. For policy
  meaning, only the already-saved, source-supported comparison judgment is reused;
  its supporting quotes are revalidated without inference. AI comparison remains
  advisory, not a guarantee.
- Submitted bindings and context fingerprint must exactly equal the server's
  re-read context. A proposal/comparison/evidence/baseline change while a form is
  open, including changes racing before the POST obtains its lock, rejects the save.

Records link the exact question, selected reply, original comparison/proposal,
unchanged agreement/confirmation, corrected proposal and fresh comparison. IDs and
fingerprints are retained together with immutable context snapshots, reviewer label,
note, timestamp and record fingerprint. UPDATE/DELETE triggers reject rewriting
history. Reads compute stale reasons without editing snapshots.

One record is allowed per suggestion and corrected comparison. An identical repeat
POST returns the existing record only after current-version checks. Changed label,
note or reply cannot overwrite it and returns 409. Stale repeat POSTs also reject;
GET remains available to inspect old history. The UI prevents concurrent double
submission. Failed or uncertain saves retain fields and require explicit refresh;
there is no automatic retry. Refresh history before manually retrying after a lost
response. Ordinary task/role navigation keeps review fields mounted; page unload
warns when the reviewer label or note is unsaved.

**No checkout code, eligibility, policy approval, agreement confirmation or payment
action changed.** This history is not an extra checkout prerequisite. A matching
comparison may change existing eligibility through the existing rules independently
of review history; recording review neither approves nor unblocks anything. Stale
versions remain subject to all existing backend guards. Demo identities are
provisional; this adds no authentication, authorization or verified merchant identity.

## API

All paths are scoped to the same booking and suggestion:

```http
GET /api/bookings/BOOKING_ID/clarifications/SUGGESTION_ID/correction
GET /api/bookings/BOOKING_ID/clarifications/SUGGESTION_ID/correction?reply_id=EXACT_REPLY_UUID
GET /api/bookings/BOOKING_ID/clarifications/SUGGESTION_ID/correction-reviews?limit=20&offset=0
POST /api/bookings/BOOKING_ID/clarifications/SUGGESTION_ID/correction-reviews
```

Context GET returns `eligible`, specific `blockers`, `bindings`,
`context_fingerprint`, original question/terms/comparison, saved replies, selected
reply ID, candidate corrected proposal and saved comparison. Here `eligible` means
eligible to record this review only, not eligible for checkout. Multiple replies
without `reply_id` leave selection unresolved. Context/history GETs never call AI.

POST accepts only the exact `bindings` object and `context_fingerprint` returned by
GET, plus `reviewer_label` (1–100 characters) and `note` (1–5,000 characters). Both
must be nonblank and contain no NUL. Unexpected action/approval fields are rejected.
201 returns the immutable record, including `stale`/`stale_reasons`; identical current
replays return the same record ID. Missing/unrelated booking/question/reply yields
404; missing/invalid fields yield 422; stale, blocked, mismatched or already-reviewed
changed context yields 409. No PATCH, DELETE, approve, resolve or payment endpoint
was added. The frontend paginates the inbox/history through the existing helper.

## Migration and setup

Implementation initially left **0011_correction_reviews unapplied** to development;
the separately authorized rollout below has now applied it. Tests migrate
only randomly named disposable PostgreSQL databases and drop those databases on
completion. The additive migration creates `clarification_correction_reviews`,
foreign keys, indexes, the per-context uniqueness constraint, provisional-identity
check and append-only trigger. It does not update existing tables or records.
Migration 0010 was applied in the separately authorized previous stage.

Using this feature on another database requires an authorized rollout
with `cd backend && uv run --frozen alembic upgrade head`, then a backend restart
if its process has not reloaded the new routes. Implementation did not perform that
rollout, inspect developer secrets or use the development database. Missing-table
errors before rollout are a setup issue, never an invitation to bypass guards.

### Authorized development rollout — 2026-11-04

Ran `cd backend && uv run --frozen alembic upgrade head` successfully, advancing
the configured loopback-local PostgreSQL database from 0010. Both `alembic current`
and `alembic heads` returned **0011_correction_reviews (head)**.

Read-only repeatable-read snapshots before and after matched counts and SHA-256
row fingerprints across all **17 pre-existing tables**, including:

| Existing records | Before | After |
| --- | ---: | ---: |
| Bookings | 4 | 4 |
| Clarification suggestions | 1 | 1 |
| Merchant replies | 1 | 1 |
| Saved comparisons | 6 | 6 |
| Merchant proposal versions | 6 | 6 |
| Payment attempts | 3 | 3 |
| Sandbox receipts | 2 | 2 |

The new `clarification_correction_reviews` table contains zero rows. Read-only
PostgreSQL catalog checks confirmed eight validated foreign keys, unique
`(suggestion_id, comparison_id)` protection, the provisional-identity check, and an
enabled BEFORE UPDATE OR DELETE row trigger bound to
`contextkey_reject_review_mutation()`. Its inspected function body raises an
unconditional exception. No mutation was attempted against development to test
that trigger; behavioral enforcement was already tested in disposable PostgreSQL.

A GET-only inspection of local backend OpenAPI confirmed correction-context GET
and correction-history GET/POST routes are loaded. **No backend restart was needed
or performed.** No business/test records, credential edits or Gemini/PayPal calls
were made. Normal project configuration was loaded without printing secrets or
record contents. Tests were not rerun for this migration-only rollout.

## Provider-free UI verification

Use installed project dependencies, a supported Node version and Chrome. From the
repository root, run in separate terminals:

```sh
npm --prefix frontend run dev:qa
```

```sh
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --disable-gpu --no-first-run --no-default-browser-check \
  --remote-debugging-port=9228 \
  --user-data-dir=/private/tmp/beforepay-correction-review-demo about:blank
```

```sh
FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 \
  node frontend/tests/correction-reviews.browser.mjs
```

Omit `--headless=new` to watch. QA Vite loads no environment files and has no backend
proxy. The script installs synthetic API responses before navigation in its dedicated
tab, blocks PayPal/Google origins and rejects unrelated writes. Run scripts
sequentially in the debugging tab. Captures go to
`/private/tmp/beforepay-correction-reviews/`. These fixtures show interaction, not
real database or provider behavior; backend tests below verify persistence/guards.

### Exact hands-on steps in the mocked tab

After running the script once in visible dedicated Chrome, keep that same tab open;
fixture installation belongs to it. Do not use the normal application/backend tab.

1. Navigate to `http://127.0.0.1:5187/?case=missingrules#bookings` in that tab.
   A fresh navigation resets synthetic state and selects Buyer demo only.
2. Open **Cinema kit · November shoot**, then **Compare booking**. Saved terms
   match, but **Clarifications & correction history** still contains the original
   question about the USD 80 deposit. No correction review was recorded automatically.
3. Click **Review correction**. Compare the original refundable buyer term against
   the original non-refundable merchant term. Use **View evidence** for the buyer
   support, then Escape to close. Read the merchant response as an unverified
   statement, the corrected proposal version and the fresh saved comparison.
4. Enter **Reviewer label (provisional)** and **Review note**. Navigate to another
   task and back if desired; fields must remain. Click **Record correction reviewed**
   once. Expect the exact outcome label, your note, provisional identity, timestamp
   and expandable version-bound snapshot. A second save for the same context is
   disabled. No agreement, policy or checkout approval is created; missing policy
   reviews still block this fixture's checkout.
5. **Switch role → Merchant**, enter `merchant.demo / MerchantDemo123!`, then open
   **Clarification replies**. Expand the historical deposit question. The same
   correction review appears read-only below the original reply. Expand
   **Reviewed discrepancy, reply and corrected versions** to inspect its snapshot.
6. To simulate relevant version changes, enter in that dedicated tab's console:

   ```js
   window.__contextOutdated = true;
   window.dispatchEvent(new Event('contextkey:changed'));
   ```

   Current labels disappear immediately. **Refresh correction history** must keep
   the record visible as outdated. No historical text is rewritten.
7. Freshly reload the URL in step 1 for each negative mode. Before **Review
   correction**, set `window.__correctionMode = 'blocked'` for remaining discrepancies
   or `'ambiguous'` for multiple saved replies. The former blocks saving with an
   explanation; the latter requires **Merchant reply reviewed** selection and shows
   that exact statement. To simulate a stale POST, first open a ready context and
   fill the form, then set `window.__correctionMode = 'stale'` before saving. Expect
   a failure, retained fields, no fake record and no automatic retry. These flags
   are test-fixture controls, not application API parameters.

Close only the dedicated QA Chrome and stop QA Vite afterwards. No real correction,
approval, provider call or payment should be made for these steps.

## Provider-free API/database verification

The existing PostgreSQL test fixture uses `Settings(_env_file=None)`, a random
disposable database and mocked/blocked providers. It does not load developer `.env`
or migrate development. A local PostgreSQL instance and test-database creation
permission are required:

```sh
cd backend
uv run --frozen pytest -q tests/test_correction_reviews.py
```

Coverage includes exact valid review, unchanged checkout eligibility, cross-booking
and mismatched references, remaining discrepancies, unchanged affected terms,
missing/ambiguous replies or terms, changed buyer baseline, stale evidence/proposal/
comparison, concurrent version change before locking, concurrent identical duplicate
submissions, changed duplicate notes and database UPDATE/DELETE rejection. Browser
checks additionally cover both workspaces, retained drafts, explicit actions, source
layout, disabled/blocked/error states and responsive presentation.

Earlier user-reported live clarification/reply verification is recorded separately
in [Merchant replies](merchant-replies.md#user-reported-manual-verification--reported-2026-11-04).
It predates this feature and is not live verification of correction review records.

## Automated verification — previous mocked runs

- Full backend suite: **418 passed**, six existing dependency warnings. Subsequently
  expanded the focused correction suite to **25 passing cases**, adding two checks
  for reuse of an existing semantic policy judgment without new inference and exact
  selection among multiple replies. Those two were run in the final focused suite;
  the full suite was not rerun after these test-only additions.
- Real disposable PostgreSQL applied 0011 and exercised transactions, concurrent
  submissions and immutable UPDATE/DELETE triggers. No development migration or
  development-record inspection was performed.
- Backend Ruff lint and format checks passed (**93 Python files**).
- Frontend TypeScript/Vite build passed. No dependencies or lockfiles changed.
- New correction browser suite: **33 passed**. Existing clarification/reply,
  redesign, workspace, alignment, creation, demo-login, item and sandbox SDK
  regressions: **641 passed**. Combined **674 mocked browser assertions**.
- Static branding/compatibility checks: **31 passed**.
- [Synthetic Buyer/Merchant screenshots](screenshots/beforepay-correction-reviews/index.md)
  reviewed at desktop 1440×1000, tablet 834×1112 and mobile 390×844 widths, including
  exact support, corrected-version context, read-only history and retained notes.

These are mocked-provider automated checks, not a live correction-review test.
Browser checks use Chromium viewport emulation and accessible-name inspection;
physical devices, other engines and a dedicated screen-reader audit remain
unverified. No live Gemini/PayPal calls, development-record/credential changes, publication or
deployment occurred. The historical user-reported manual observations above are
separate evidence and do not extend these automated results.

## User-reported manual correction review — reported 2026-11-04

The user reported the following manual observations after the correction-review
feature and migration were available:

1. A correction review was saved against the corrected merchant proposal and fresh
   saved comparison.
2. The saved review persisted after refreshing the application.
3. The review appeared in both Buyer and Merchant workspaces.
4. Recording the review did **not** grant checkout approval.

These are **user-reported manual observations**, separate from the previous mocked
automated results above and from the earlier clarification/reply-only report. This
documentation update did not independently inspect records, logs, provider responses
or screenshots, reproduce the workflow, or rerun tests. No record/version IDs,
reviewer label, note text or execution timestamps were supplied; none are inferred.
The date identifies when the report was recorded.

The outcome remains **Correction reviewed for these versions—not checkout approval.**
This report does not establish policy approval, authenticated identity, checkout
eligibility or payment capture. Existing separate approvals and backend payment
guards remain applicable. It does not demonstrate additional live negative-path,
concurrency or immutable-trigger tests; those checks remain the earlier automated
evidence.

Only documentation changed while recording this report. No application-record or
credential changes, test reruns, or new Gemini/PayPal calls were performed.
