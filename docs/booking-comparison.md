# Merchant booking comparison

This local prototype compares a merchant's saved final booking proposal with a
**currently customer-confirmed** agreement. Proposals are independent immutable
records: submitting or saving one never edits, invalidates or confirms the
customer baseline. This feature does not authorize payment.

The current [Buyer/Merchant workspace stage](buyer-merchant-workspaces.md) gives
proposal editing a separate Merchant navigation and overview, using these same APIs.

## Start and use the screen

Apply the additive migration and run the existing services:

```sh
cd backend
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```sh
cd frontend
npm run dev
```

Open http://127.0.0.1:5173/#bookings, open a booking and choose **Compare booking**.
Use **Merchant · edit proposal** in the labelled **Prototype view switch** to edit.
Buyer difference review remains a separate view of the same local booking. First confirm the agreement in Agreement review if necessary.
Saving a merchant proposal is allowed without confirmation; comparing requires
current confirmation. Customer and merchant identity labels remain provisional
until authentication is added.

1. Optionally **Copy buyer-confirmed terms into form** as a starting point. This
   fills fields only and does not establish merchant agreement. Check against the
   actual final booking, or enter it directly. Enter equipment quantities, included items (or explicitly none), full local
   dates and explicit timezones, currency, decimal-string amounts, deposit terms
   and all cancellation clauses. Blank categories remain unknown, never zero or
   no-policy. The confirmed terms appear alongside each category.
2. Optional **Demo samples · fill fields only** populate the editable form. The
   separate copy action above uses this booking's confirmed values. **USD 200 total, non-refundable deposit**
   sets rental fee USD 120, deposit USD 80 and inclusive total payable USD 200,
   with a non-refundable deposit policy. This may differ in other ways if the
   actual baseline uses other values. **Equivalent policy wording** retains all
   original clauses and restates their presentation. Its label is not a judgment:
   the policy comparator must evaluate it explicitly.
3. Enter a merchant label and a reason/note. Click **Save as new merchant version**.
   Every save appends a version; old records and baseline confirmation remain.
4. Choose **Review saved versions & compare**, then explicitly click
   **Compare bookings · may use AI** in buyer view. Only this click can invoke
   the policy model. Identical complete policy text needs no model call; changed
   text uses the existing backend-only GEMINI_API_KEY and GEMINI_MODEL. No provider
   call occurs while loading, editing, loading samples or saving proposals.
5. Read matches/differences/needs clarification beside the exact confirmed and
   proposed terms. Policy judgments include exact supporting quotations on both
   sides. Same total price cannot hide changed deposit/cancellation obligations.
6. Save another proposal, then refresh/select the previous comparison to see
   **stale**. Agreement revisions, new evidence or lost current confirmation also
   stale prior comparisons. Refresh is manual; server rechecks inputs on actions.

Editing fields makes the form unsaved and disables comparison until saved. A
comparison always describes persisted versions, never the current unsaved form.
Historical proposals can be loaded and copied into a new version; only the latest
saved proposal can be compared. Historical comparisons retain their original
inputs and results and are labelled stale based on current state.

## Advisory clarification questions

Buyer discrepancies now offer **Suggest clarification**, an explicit model action
with exact saved-term references and immutable, version-bound history. It never
resolves or approves a difference. See [provider-free UI/API verification and
rollout](clarification-suggestions.md). [Merchant replies](merchant-replies.md) and
[explicit correction-review history](clarification-corrections.md) are implemented.
Replies are unverified statements; recording correction review is not checkout approval.

## Comparison rules and limits

- Python compares item identities using case/whitespace normalization, exact
  quantities, named monetary kinds and Decimal values/currency. Duplicate item or
  amount identities are ambiguous, never silently aggregated. Equipment aliases
  are not inferred. Different names differ; genuinely unknown quantities stay
  unknown. Missing amount kinds require clarification instead of assuming zero.
- `rental_total` is the rental fee/subtotal. `total_payable` is the inclusive stated
  total, never an extra charge. No component sums, taxes or missing totals are
  invented. USD 120 rental + USD 80 deposit + USD 200 total is not USD 400.
- Dates compare timezone-aware instants. Equivalent explicit offsets can match;
  missing/ambiguous dates or DST instants need clarification.
- Policy-only Gemini input contains the full clauses from both versions, treated
  as untrusted data. Each requested category must appear exactly once in output;
  allowed judgments are `matches`, `differs`, `needs_clarification`. Both quotations
  must be exact nonblank substrings of their own input text. A response is not
  accepted for invented text, wrong categories, missing results or schema errors.
  Whole policies remain visible alongside these citations. Quote validation does
  not prove the semantic judgment is correct: the customer must inspect results.
- Missing, placeholder or explicitly ambiguous policies do not become model-made
  facts. Complementary clauses are not automatically contradictory. Input policy
  text is bounded at 40,000 combined characters for one comparison request.
- Same official GenAI SDK, configured model/key, Developer API, 60-second timeout,
  one total attempt and no fallback. Missing credentials, quota exhaustion,
  timeout and invalid output return clear errors and create no successful result.
  No live model calls were made while implementing/verifying this feature.

## Persistence and API

Comparison prompt v2 distinguishes explicit conflicting commitments (`differs`)
from undefined outcomes/conditions or unbounded discretion (`needs_clarification`).
Neither status is a match or checkout approval. See [cmp-08 analysis, prompt change
and offline limitations](policy-comparison-commitments.md). Existing saved results
remain historical; the frozen pilot used prompt v1 and was not rerun.

Migration `0005_booking_comparison` adds `merchant_booking_versions` and
`booking_comparisons`, protected against UPDATE/DELETE by database triggers. No
old agreement/draft/evidence/confirmation rows are rewritten. Fingerprints bind
proposal content, version, identity and audit; comparison fingerprints bind the
exact agreement, confirmation, proposal, results and model metadata. Staleness is
computed on retrieval, without updating immutable comparison history.

Swagger at http://127.0.0.1:8000/docs exposes:

- POST/GET `/api/bookings/{booking_id}/merchant-bookings`
- GET `/api/bookings/{booking_id}/merchant-bookings/{proposal_id}`
- POST/GET `/api/bookings/{booking_id}/comparisons`
- GET `/api/bookings/{booking_id}/comparisons/{comparison_id}`

Proposal create takes `expected_latest_id` (null for first save), `merchant_label`,
`reason` and `content`. Content uses the same validated customer claim fields as
agreement revisions, empty citations, eight category arrays, plus
`included_items_none`. All category arrays may be empty to explicitly preserve
missing information. Concurrent saves based on the same old ID return 409.

Comparison create requires `agreement_id`, `agreement_fingerprint`, `proposal_id`
and `proposal_fingerprint`. The backend requires current confirmation, checks
both latest versions, releases the transaction during policy inference, then
locks and rechecks versions, evidence and confirmation before inserting results.
Changes during inference return 409 and publish no result. Cross-booking IDs
cannot be used. Saving a proposal does not alter baseline review eligibility;
payment code must additionally check a current suitable comparison under
its transaction. A historical comparison or confirmation alone cannot authorize
payment. Live payments, comparison resolution, broader consequence calculations and
merchant/customer authentication remain deferred. A separate narrow
[cancellation preview](cancellation-preview.md) now supports reviewed two-band
pre-pickup rules; it does not amend comparison results or execute cancellation.
Guarded [sandbox checkout](paypal-sandbox.md) now uses the current comparison as
one of its server-enforced prerequisites.

## Verification

```sh
cd backend
uv run --frozen pytest -q tests/test_booking_comparisons.py tests/test_customer_review.py
uv run --frozen ruff check .
uv run --frozen ruff format --check .
cd ../frontend
npm run build
```

Tests use a separate randomly named PostgreSQL database and mocked/blocked AI.
They cover exact matches, quantity/equipment/date/money differences, missing
terms, equivalent policy output, same-total deposit mismatch, citation rejection,
provider failures, immutable history, preserved confirmation, stale fingerprints
and versions, and concurrent evidence/proposal changes during policy inference.
