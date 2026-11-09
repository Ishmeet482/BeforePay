# Source corroboration and saved-state loading — 9 November 2026

## Evidence and diagnosis

The user reported repeated equipment, amounts and policies for “Smith- Demo”,
whose quotation and supporting message describe the same rental. The initial
implementation inspected code and synthetic fixtures only. The follow-up below
adds narrowly scoped read-only inspection of that booking's saved terms/comparison;
no credentials were retrieved and no hosted record was changed.

Code trace confirms a repeat-preserving path: Gemini wire rows become separate
cited claims; draft publication previously stored every validated claim; opening
review copied every claim; `CategorySummary` rendered every row; copying the buyer
baseline into the merchant form copied every entry again. The renderer was not
duplicating a single row itself. The follow-up confirms that pattern in saved
included-item inputs rather than inferring it only from the display.

Originally, comparison canonicalisation rejected every duplicate item/amount
identity; cancellation rejected repeated amount kinds, currencies and pickups.
It never summed repeated mentions. The first change corrected new publication and
display, but left legacy stored claims blocked. The follow-up corrects that
unfinished integration using read-only, source-aware interpretation; remaining
ambiguous identities still block.

### Saved comparison follow-up

Read-only Neon MCP inspection, using `beforepay_demo_runtime` in the already
verified dedicated demo database, located one matching booking. Its latest saved
comparison at inspection was recorded **9 November 2026, 09:33:23.350 UTC**, bound
to **agreement v2 / merchant proposal v1**, both latest at that time.

- Included items: buyer inputs contain four claims (batteries quantity 2 and
  microphone quantity 1, each repeated across two source IDs); merchant inputs
  contain two. Every included-item `ambiguous` flag is **false**.
  Buyer `explicit_none_categories` is empty, merchant `included_items_none` is
  false, and both saved comparison fingerprints match their bound versions.
- Saved reason is `missing_or_ambiguous_terms` / `needs_clarification`. The UI
  displayed two corroborated terms but comparison canonicalisation still saw
  four raw claims and rejected repeated identities. This was not an unresolved
  checkbox or a hidden conflicting quantity.
- Equipment, pickup, return, currency and amounts had the same generic blocker.
  Typed values corroborate across sources. Summary amount labels differ in case
  and in the inclusive-total alias “Total payable” / “total”; component values are
  rental 60, deposit 40 and inclusive total 100, all USD. Policies already matched
  in the saved comparison; their different original wording is preserved.

New comparisons interpret corroborating source mentions once without rewriting
the agreement or changing its fingerprint. **Comparison results still retain all
raw saved input terms and citations**, preserving clarification/correction term
indices and exact reference checks. Previously saved comparison statuses are not
rewritten: a fresh explicit comparison is required. Checkout still checks the
latest saved comparison and separately rechecks deterministic values.

Cancellation currency/amount validation, pickup completeness and preview use the
same typed corroboration projection. This avoids moving the same legacy blocker
from comparison into the next stage. New rule versions, human approvals and exact
source fingerprint checks remain required; a matching comparison grants none.

For the three summary amount kinds, typed interpretation permits label case/spacing
differences and a closed set of inclusive-total names: `total`, `total payable`,
`inclusive total`, `total payable (inclusive)`. All material typed fields must agree.
Other qualifiers remain significant: “Non-refundable security deposit”, “Rental
fee including delivery” and “Total before taxes” do not merge with the reported
labels. Custom/other charges retain exact label identity. No general semantic
deduplication, policy precedence, rounding or inferred amount allocation is added.
Same-source or uncited merchant/customer-authored duplicates and unresolved flags
continue to block. No repeated mention is added to another charge.

Amount summaries show one corroborated component with every original label and
quotation still available. The overview and explicit merchant baseline copy use
that projection too, preventing the copy action from turning source label variants
into duplicate uncited merchant charges. Original editors retain individual rows.
Comparison shows unresolved flags on **both** sides, and explains grouped display
versus old saved clarification status instead of forcing a client-side match.

## Exact corroboration, not semantic deduplication

After validating **all** original claims and citations, newly published drafts
group identical, non-ambiguous claims from disjoint source IDs. Opening an older
draft for a new review and explicitly saving a review revision use the same
conservative grouping. All citations remain attached to the resulting claim.

- In newly persisted strict consolidation, every typed field must agree, including item name, quantity, amount kind/label,
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
For legacy duplicate reviews, a notice explains separate saved claims and the
optional explicit revision to consolidate their stored representation. Pure
corroboration no longer requires a new agreement just to compare or preview.
The overview uses the same display projection;
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
2. After the code update, **explicitly compare saved versions again**. The existing
   saved comparison is not changed automatically. Pure source corroboration can
   match; flagged, differing, missing or authored duplicate terms still require
   explicit correction. Different policy wording still uses the existing explicit
   comparison workflow and is never assumed equivalent by this fix.
3. If you want a consolidated stored review, acknowledge every current source.
   Open the review actions at the bottom (a
   confirmed agreement shows a confirmation/history summary there),
   enter a reviewer label and a reason such as “Consolidated exact corroborating
   source mentions; no term values changed.” Select **Save review**.
   No AI regeneration is required. The new immutable review merges only proven
   source corroboration; the old version remains available in history.
   Recheck that new version, acknowledge sources as required and **confirm** it
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

The comparison follow-up adds `tests/test_legacy_corroboration_flow.py`: synthetic
legacy source versions reproduce the included-items mismatch and label variants,
then exercise fresh comparison, separate buyer/merchant rule approvals, Python
cutoff previews and explicit checkout approval without creating an order/capture.
At exactly 48 hours the synthetic USD 100 rental refunds 60 + 40; one minute later
it refunds 40 and retains 60. Unresolved flags, changed quantities/amounts/currency,
same-source repetition, uncited duplicates and qualifying label changes still
block. Old agreements, fingerprints, source citations/indices and old comparison
results remain unchanged. This is offline regression evidence, not a hosted
retest, AI evaluation or real payment observation.

Follow-up checks passed: **262 backend regressions**, then **17 final focused
legacy-flow checks** after adding further date/currency negatives, each run with
six existing dependency warnings. The focused set is included in the larger run
except for those final negatives; do not add the counts as independent coverage.
Five distinct mocked browser suites passed (comparison corroboration, source
corroboration/loading, blocker journey, alignment and PayPal approval), including
desktop/tablet/mobile screenshots inspected locally. Pure frontend corroboration
checks, build/typecheck using `vite.qa.config.ts`, Ruff lint/format and whitespace
checks passed. Hosted recovery after this follow-up has not been exercised.

```sh
cd backend
uv run --frozen --offline pytest -q -x --tb=short \
  tests/test_legacy_corroboration_flow.py tests/test_source_corroboration.py \
  tests/test_booking_comparisons.py tests/test_cancellation_preview.py \
  tests/test_paypal_sandbox.py tests/test_clarifications.py \
  tests/test_correction_reviews.py tests/test_policy_consistency.py \
  tests/test_customer_review.py
cd ../frontend
node tests/corroboration.mjs
npm run build -- --config vite.qa.config.ts
node tests/all-browser.mjs comparison-corroboration.browser.mjs \
  corroboration.browser.mjs blocker-journey.browser.mjs \
  alignment.browser.mjs paypal-approval.browser.mjs
```
