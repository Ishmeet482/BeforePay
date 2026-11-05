# Reviewed cancellation consequence preview

Narrow scope: pre-pickup cancellation, one cutoff measured in hours, two complete
bands with explicit boundary inclusion, and separate rental-fee/deposit refunds.
The supported financial basis is explicitly stated USD rental fee + deposit =
inclusive total payable, all in exact cents. Taxes, other nonzero charges,
additional cutoffs, unreviewed exceptions, missing terms, unsupported currencies
or unresolved contradictions require clarification. No payment or actual
cancellation is executed.

The [Merchant prototype workspace](buyer-merchant-workspaces.md) now exposes
proposal-only rule preparation/review separately. Buyer cancellation retains the
calculator and both-source review capability; these are not access permissions.

## Browser steps

Use the existing services on http://127.0.0.1:8000 and
http://127.0.0.1:5173. Apply `cd backend && uv run --frozen alembic upgrade head`
and restart FastAPI if it is not running with reload.

1. Select a booking and open **Cancellation**. The calculator and rule-review task are separate.
   Open the rule-review disclosure below the calculator to author/propose rules. Choose the current confirmed
   agreement or latest merchant proposal. Read **all** displayed cancellation and
   deposit text, including original evidence quotations when present. The exact
   source version and fingerprint are shown.
2. Enter rules manually or explicitly choose **Propose rules with AI**.
   Only that button can call Gemini. It proposes an immutable **unapproved** rule
   version; it never computes refunds or approves rules. A missing key/quota/error
   produces a clear failure without fabricated rules or provider fallback.
3. Optionally **Load 48-hour example · form only**. This populates percentages,
   flags clarification and does not save, approve, invoke AI or calculate. Check
   every field against the actual source; unsupported samples cannot be approved.
   If policies are consolidated into one source field, copy the exact relevant
   substring separately for each band. Never use an entire combined policy as a
   band citation when it also contains the other band's refund conditions.
4. For the supported example, set cutoff `48`, assign exactly-at-cutoff to the
   earlier band, earlier rental/deposit refunds `100`/`100` percent, later refunds
   `0`/`100` percent. Cite the exact earlier/later cancellation clauses and deposit
   clause. This yields USD 200 before/at cutoff and USD 80 inside cutoff only if
   the source explicitly establishes USD 120 rental + USD 80 deposit + USD 200 total
   and supports those refund obligations. Do not invent missing policy text.
5. Keep **Missing terms, contradictions or unsupported conditions** checked until
   resolved. Correct contradictory agreement text through the existing reasoned
   agreement revision/confirmation flow, or save a new merchant proposal. Rules
   cannot grant precedence or override contradictory source clauses.
6. Enter your provisional reviewer label and a reason. **Save rules for review**. Review server blockers and correct rules as a new version if needed.
7. Check completeness, absence of unresolved contradictions and exact-fingerprint
   approval, add a review note, then **Confirm reviewed rules**. Rules, AI proposals
   and approvals are separate append-only records; none change the original
   agreement, merchant proposal or customer agreement confirmation.
8. Enter cancellation local ISO date/time and an explicit IANA timezone or offset.
   **Preview refund**. See cancellation time, refund, amount retained,
   component refunds, cutoff instant/boundary, applied clause and exact source
   version/fingerprint. At or after pickup the result is needs clarification.
9. Review and confirm rules for the other version independently. Only when both
   have current complete approved rules may you enable **Side-by-side**. If either
   is stale/incomplete, the API returns no definite outcomes for either side.

Refresh is manual. Saving a new source version or rule version makes old approval
non-current; evidence or confirmation changes also invalidate agreement rules.
The server checks under the booking lock before every approval and preview. Old
rule/approval history remains readable and unchanged. Local edits disable
confirmation/calculation until saved and reviewed again.

## Explicit rules and arithmetic

Rules store `cutoff_hours` as a Decimal string and `early_includes_boundary` as a
strict boolean. Earlier applies farther before pickup; later applies closer to
pickup but strictly before pickup. Each band contains a `rental_refund` and
`deposit_refund`, each with `mode: "amount" | "percent"` and decimal-string `value`,
plus an exact supporting `clause`. Percent `100` means 100%, not 1%. A separate
`deposit_clause`, `needs_clarification` flag and clarification note are required.

Python compares exact elapsed microseconds against Decimal cutoff seconds.
Timezone conversion reuses the validated IANA/offset handling; ambiguous DST
local times require clarification or an explicit offset. No binary floats or
current locale are used. Refund percentages apply to each **component**, then
refunds are added once. Amount retained = stated inclusive total payable - refund.
The inclusive total is never added to its own components. Refunds above component
amounts, percentages above 100, inconsistent totals and fractional-cent results
are blocked; no unstated rounding policy is invented.

Literal citations, explicit cutoff hours and recognizable boundary language are
checked against source-version text. Source ambiguity flags/direct opposing
policies block approval. A non-refundable deposit contradicting a full refund or
promised deposit return is flagged across deposit/cancellation clauses; a split
that refunds such a deposit also blocks. Conservative lexical checks are not a
complete semantic policy engine. Human review must explicitly attest that **all**
clauses, exceptions, boundary and component refunds are complete and consistent.
Unrepresentable policies must remain needs clarification rather than be forced
into these two bands. Approving rules does not amend or resolve source text.

## Corrected merchant samples

The **USD 200 total, non-refundable deposit** sample now has consistent clauses:
farther than/at 48 hours, refund rental fee USD 120 only and retain deposit USD 80;
closer than 48 hours, retain both components and refund USD 0. A separate
**contradictory deposit / cancellation** sample combines non-refundability with a
full early refund and a later deposit refund, intentionally requiring clarification.
Loading samples only changes the form. Existing saved proposals are not rewritten.

## API and persistence

Prefix: `/api/bookings/{booking_id}/cancellation`.

- POST `/rules`: human-authored unapproved version, exact target, expected latest
  rule ID (null for first version), reviewer label, reason and structured rules.
- POST `/rules/propose`: explicit Gemini proposal for the exact target, expected
  latest rule ID and reviewer label. Releases database lock during inference,
  then rechecks source, confirmation and latest rule before persistence.
- GET `/rules` and `/rules/{rule_id}`: history, blockers and effective approval.
- POST `/rules/{rule_id}/confirm`: exact rule fingerprint, strict true
  acknowledgement/completeness/no-contradiction attestations and review note.
- POST `/preview`: one or two `rule_ids` and `cancellation` with `local_datetime`
  and `timezone`. Two IDs must identify an agreement and a proposal. Returns
  `ready` or `needs_clarification`; no preview money is returned if any blocker
  exists. Malformed schema input gets 422; stale approval/actions get 409.

A target is `{ "kind": "agreement" | "proposal", "id": "UUID",
"fingerprint": "64 lowercase hex characters" }`. Migration
`0006_cancellation_rules` adds only immutable rule versions and separate approvals;
existing records/confirmations remain intact. Preview itself is a read-only
calculation, not a booking cancellation, financial ledger or payment authorization.
Identity remains provisional until authentication is implemented.

## Checks

```sh
cd backend
uv run --frozen pytest -q tests/test_cancellation_preview.py tests/test_booking_comparisons.py
uv run --frozen ruff check .
uv run --frozen ruff format --check .
cd ../frontend
npm run build
```

Automated tests mock/block all AI calls and use an isolated PostgreSQL database.
No live calls or billing changes are needed for manual rule entry or previews.

## User-reported live proposal and manual preview verification — 2026-11-02

The user reports that the live **Propose rules with AI** action successfully
generated a Gemini rule proposal, followed by explicit human approval of the
rules and these cancellation previews:

- Exactly 48 hours before pickup: **USD 200 refund**.
- One minute later (47 hours 59 minutes before pickup): **USD 80 refund and
  USD 120 retained**.

The reported boundary result places exactly 48 hours in the earlier cancellation
band. These are user-reported manual workflow results, separate from automated
tests, which mock/block provider calls. They were not independently reproduced
or checked against database records during this documentation update. No booking,
rule/version, model or provider-response identifiers were supplied or inferred.

Gemini proposes unapproved source-linked rules; explicit human confirmation
remains a separate step. Python Decimal and timezone-aware datetime code calculate
the refund previews. This report does not attribute the monetary calculations to
Gemini or establish support for policies outside the implemented narrow model.

Documentation only: no new AI or PayPal calls, payment/refund actions, database
access or tests. Existing records, approvals, receipts, Python calculations and
all approval safeguards were left unchanged. A preview does not cancel a booking
or issue a refund.
