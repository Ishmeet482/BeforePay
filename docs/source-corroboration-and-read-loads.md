# Source corroboration and saved-state loading — 9 November 2026

## Evidence and diagnosis

The user reported repeated equipment, amounts and policies for “Smith- Demo”,
whose quotation and supporting message describe the same rental. No hosted
records, sources or credentials were retrieved during this investigation.

Code trace confirms a repeat-preserving path: Gemini wire rows become separate
cited claims; draft publication previously stored every validated claim; opening
review copied every claim; `CategorySummary` rendered every row; copying the buyer
baseline into the merchant form copied every entry again. The renderer was not
duplicating a single row itself. This explains the reported pattern without
claiming to have inspected that booking's exact persisted values.

Existing comparison canonicalisation rejects duplicate item/amount identities;
cancellation rejects duplicate amount kinds, currencies or pickup candidates.
It does **not** sum repeated mentions. These guards were intentionally retained.
Merely suppressing display rows would leave historical duplicate versions blocked.

## Exact corroboration, not semantic deduplication

After validating **all** original claims and citations, newly published drafts
group identical, non-ambiguous claims from disjoint source IDs. Opening an older
draft for a new review and explicitly saving a review revision use the same
conservative grouping. All citations remain attached to the resulting claim.

- Every typed field must agree, including item name, quantity, amount kind/label,
  currency, datetime/timezone and exact policy wording. No case/whitespace/meaning
  normalisation or precedence inference is added. Python Decimal equality handles
  equivalent decimal representations without arithmetic.
- Conflicting quantities/amounts, different items, different policy wording,
  missing information and unresolved flags remain explicit. Existing term-status
  classification runs before grouping, so consolidation cannot clear uncertainty.
- Same-source repetition is retained: identical wording in one source might
  describe distinct items. Multiplicity is not silently discarded. Matching across
  other sources preserves that multiplicity rather than summing it.
- The existing 20-citation limit remains. A group that cannot retain all citations
  remains separate; no evidence is truncated. Customer-entered terms, reasons and
  ordering are preserved individually.
- Existing agreements/drafts, confirmations, comparisons, receipts and their
  fingerprints are never rewritten. No migration or API request-schema change
  is needed. Receipt contents are not reconstructed or consolidated.

Read-only term summaries group corroboration with all evidence available through
the existing drawer's quotation selector. Original edit rows remain accessible.
For legacy duplicate reviews, a notice explains the separate saved claims and
the explicit revision needed. The overview uses the same display projection;
backend status/eligibility still comes from actual saved state.

Merchant baseline copying is explicit and fills one form row per corroborated
term; it neither saves nor approves. Existing saved merchant-authored rows are
not automatically consolidated. Row/add labels now identify Equipment item,
Included item, Pickup option, Return option, Currency, Charge, Deposit clause or
Cancellation clause.

## Existing booking: explicit review path

No action below was performed on the hosted booking during implementation.

1. In the owning Buyer demo session, open **Agreement** for “Smith- Demo”. Inspect
   grouped values and use **View evidence** → **Supporting quotation** to review
   both original mentions. Different wording or values remain separate.
2. Acknowledge every current source. Open the review actions at the bottom (a
   confirmed agreement shows a confirmation/history summary there),
   enter a reviewer label and a reason such as “Consolidated exact corroborating
   source mentions; no term values changed.” Select **Save review**.
   No AI regeneration is required. The new immutable review merges only proven
   source corroboration; the old version remains available in history.
3. Recheck the new version, acknowledge sources as required and **confirm** it
   separately. Saving a review is not confirmation or checkout approval.
4. In Merchant view, inspect the current final proposal. If its rows already
   contain merchant-entered duplicates, explicitly revise them. Copy the newly
   confirmed buyer terms only if they really describe the merchant's final offer;
   otherwise retain genuine differences and remove only reviewed repetition.
   Supply a merchant label/reason and save a new merchant version.
5. Run a fresh comparison explicitly. Relevant policy-consistency checks, rule
   reviews/approvals and checkout approval remain independently version-bound.
   Renew them where the backend requires; this change bypasses none of them.
   Existing completed receipts continue to describe their captured versions.

## Hosted readiness failure: what is proven

The user supplied this sanitised runtime entry (endpoint/time not supplied):

```json
{
  "boundary": "database_readiness",
  "check": "database_identity",
  "exception_type": "PoolTimeout",
  "failed_checks": [],
  "sqlstate": null
}
```

This establishes connection acquisition exhaustion at the first readiness query.
It does not indicate settings rejection, wrong database identity, a SQL permission
failure, a cold start or a connection leak. The query had not obtained a slot.

Inspection found six parallel status requests **per booking**, additional screen
loads, and hidden dashboard rows still refreshing while an open booking refreshed
its own snapshot. Each public request runs the full readiness sequence using its
request session, then ownership/endpoint reads on that same connection until
request cleanup. AI admission uses its separate bounded engine; inference paths
release their transaction before provider work. No GET connection leak or nested
checkout was found in the inspected/tested path.

The frontend now admits at most **two saved-state reads per tab**, including JSON
decoding, matching the existing minimum backend pool size. Queued cancelled reads
are removed; failures release their slot. Mutations retain existing explicit
execution and guards. Hidden dashboard/open-booking snapshots stop refreshing
while inactive. No retry, cache, readiness bypass or larger pool/timeout is added.

Initial load failures on Sources, Agreement, Comparison, Cancellation and Checkout
show **Saved data unavailable**, never a false empty-data conclusion or a prompt
to regenerate missing records. An explicit refresh is available. Successful prior
loads and unsaved form state remain mounted if a later refresh fails.

## Offline verification and limits

Restricted-runtime PostgreSQL regression uses `pool_size=2`, `max_overflow=0`,
`pool_timeout=3`. A deliberately delayed six-read burst reproduces the supplied
`database_identity` / `PoolTimeout` failure. The same held-read workload admitted
two at a time completes, keeps readiness on every request and uses one checkout
per successful GET. Checked-out connections return to zero after successful and
404 responses. Existing ownership, shared-read/exclusive-mutation locking,
readiness-negative and mocked sandbox-payment regressions pass.

This models the demonstrated contention mechanism; it does not measure the
historical hosted query latency or establish what kept those connections busy.
Other tabs/visitors or backend unavailability can still produce a fail-closed 503.
Hosted recovery has not been verified. If it persists after the code update,
retrieve the failing endpoint suffix/time and its sanitised `public_setup_failure`
entry, plus whether other tabs or explicit actions were active. Do not share
cookies, SQL/parameters, source text, IDs or credentials.

Commands (mocked/offline; PostgreSQL fixtures create disposable databases only):

```sh
cd backend
uv run --frozen --offline pytest -q -x --tb=short \
  tests/test_source_corroboration.py tests/test_extraction_datetimes.py \
  tests/test_extraction_validation_diagnostics.py tests/test_compact_extraction.py \
  tests/test_customer_review.py tests/test_booking_comparisons.py \
  tests/test_cancellation_preview.py tests/test_restricted_saved_state.py \
  tests/test_hosting_diagnostics.py tests/test_hosted_sandbox_payments.py
uv run --frozen --offline ruff check .
uv run --frozen --offline ruff format --check .

cd ../frontend
node tests/corroboration.mjs
npm run build -- --config vite.qa.config.ts
# With the isolated QA server and local Chrome CDP described in frontend-redesign.md:
node tests/all-browser.mjs corroboration.browser.mjs alignment.browser.mjs \
  workspaces.browser.mjs blocker-journey.browser.mjs \
  paypal-approval.browser.mjs public-demo.browser.mjs
```

The first combined backend run passed **239 tests**; final provenance refinements
passed **145 focused tests**, each run with six existing dependency warnings.
The production build/typecheck used the isolated QA config to avoid environment
file loading; backend Ruff lint/format and whitespace checks passed.
Six relevant browser feature suites passed before the final historical-comparison
display refinement; the corroboration, clarification, merchant-reply and correction
suites were then rerun. Browser checks use synthetic fetch
fixtures, block provider domains, and cover desktop/tablet/mobile corroboration,
evidence access, merchant initialisation, failed GETs and explicit refresh. These
are not new manual hosted/provider observations. No provider call, hosted record
or configuration change, private environment edit or development migration occurred.
