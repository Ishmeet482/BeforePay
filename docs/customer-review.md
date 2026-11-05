# Customer review and confirmation

This milestone adds local customer review of existing extracted drafts. It makes
no AI calls. Original AI drafts/evidence stay unchanged; corrections create new
immutable agreement versions. Confirmations are separate append-only records.
This guide describes the original review milestone. The current prototype also
includes [comparison](booking-comparison.md), [consequence previews](cancellation-preview.md),
[guarded sandbox checkout](paypal-sandbox.md) and [guided frontend workspaces](product-redesign-2026-11-03.md).
Authentication remains unimplemented. **Customer labels are self-reported, provisional identifiers**, not
authenticated identity, authorization or proof of a legal signature. Keep the API
bound to localhost; booking-scoped resource lookup is not customer authentication.

## Startup and migration

Use existing environment configuration, including host PostgreSQL **5433** and
container **5432**. Do not overwrite `.env` files.

```sh
cd backend
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Migration `0004_customer_review` adds agreement-version/confirmation tables and
immutability triggers; upgrades never reset existing data. Both tables reject
UPDATE/DELETE. Original `draft_versions` and its trigger are unchanged.

## Swagger walkthrough (no AI calls)

Open <http://127.0.0.1:8000/docs>. For each operation use **Try it out → Execute**.
Use an existing booking with stored evidence and an extracted draft.

1. `GET /api/bookings/{booking_id}/drafts?limit=1`: copy latest draft `id`.
   Existing draft detail GET remains available with original AI conditions/citations.
2. `POST /api/bookings/{booking_id}/agreements/from-draft`:

   ```json
   {"draft_id":"LATEST_DRAFT_UUID","customer_label":"local-demo-customer"}
   ```

   Expect **201**. Copy agreement `id` and `fingerprint`. The response contains
   `content.extraction` entries with `origin: "source_supported"` and original
   `claim`/citations. This checks exact source support, not semantic truth or
   completeness. It never marks the AI draft approved. If this draft is already
   under review, expect **409**; retrieve the current version via agreement list
   or review state instead of resetting customer corrections.
3. `GET /api/bookings/{booking_id}/review`: inspect `blockers`, `source_ids`,
   current agreement/fingerprint and `confirmation_current`. This endpoint is the
   authoritative current review state. Copy **all** returned source IDs for a
   revision. A version imported from an extraction that omitted some sources
   blocks confirmation with `unreviewed_evidence`.
4. To correct a condition, `POST /api/bookings/{booking_id}/agreements/{agreement_id}/revisions`:

   ```json
   {
     "expected_fingerprint":"FINGERPRINT_FROM_GET",
     "customer_label":"local-demo-customer",
     "review_reason":"I reviewed every current source and explicitly corrected the negotiated quantity.",
     "reviewed_source_ids":["ALL_CURRENT_SOURCE_UUIDS"],
     "changes":[{
       "category":"equipment",
       "reason":"Customer confirms the negotiated count is two cameras.",
       "items":[{"name":"Camera","quantity":2,"ambiguous":false}]
     }]
   }
   ```

   Example values are synthetic; enter only conditions actually agreed for your
   booking. Each change replaces its entire named category. Repeat retained items
   explicitly when correcting a list. Every category can appear at most once.
   Expect **201**, a new `id`, higher `version`, `parent_id`, changed fingerprint,
   and `origin: "customer_entered"` with reason and **empty citations**. Providing
   fake source citations or an origin flag in correction items returns **422**.
   Untouched categories retain source provenance. Audit includes provisional
   customer label, review reason, exact changes and per-category reasons.
5. Resolve every blocker using category changes below. Incomplete versions may
   be saved for review, but cannot be confirmed. `GET /agreements/{id}` retrieves
   exact immutable content/audit; `GET /agreements` lists versions newest first.
   No corrections ever overwrite prior agreement or AI versions.
6. Confirm the **latest** version with its **latest fingerprint** using
   `POST /api/bookings/{booking_id}/agreements/{agreement_id}/confirmations`:

   ```json
   {
     "expected_fingerprint":"FINGERPRINT_FROM_LATEST_VERSION",
     "customer_label":"local-demo-customer",
     "acknowledged":true
   }
   ```

   Expect **201** with a separate confirmation ID, exact agreement UUID,
   `reviewed_fingerprint` and timestamp. An identical confirmation repeated by the
   same provisional label returns **200**, same record. False/nonboolean
   acknowledgement returns **422**. Wrong fingerprint, older version, newer AI
   draft, unresolved terms or changed evidence returns **409** without confirming.
7. `GET /review`: expect `confirmation_current: true`, `requires_review: false`
   and no blockers. Confirmation does not mutate agreement content or AI status.
8. Renewal check: add a new pasted message or valid PDF through existing source
   endpoints. Review state becomes non-current. Confirmation of the old version
   fails **409**. Submit a revision with all current source IDs, explicit reason,
   and any necessary corrections. `changes: []` is allowed only as an explicit
   re-review attestation when conditions truly remain unchanged. Confirm the new
   version/fingerprint again. No AI call is needed for manual re-review.

## Required completeness and correction shapes

All eight condition groups must be explicit. Missing fields stay unknown; no
default rental, deposit or cancellation policy is invented. `ambiguous: true`,
competing values, null required quantities/times/currency and placeholder policies
such as `TBD`, `unknown`, `not specified` block confirmation.

| Category | `items` shape in a change | Completeness rule |
| --- | --- | --- |
| `equipment` | `[{"name":"Camera","quantity":1,"ambiguous":false}]` | At least one item, known positive quantities |
| `pickup`, `return_time` | `[{"value":{"local_datetime":"2026-11-05T09:00:00","timezone":"UTC"},"ambiguous":false}]` | Full ISO local datetime and explicit IANA zone/offset; return after pickup |
| `currency` | `[{"value":"USD","ambiguous":false}]` | One consistent explicit currency code |
| `amounts` | `[{"kind":"rental_total","label":"Rental total","amount":"200.00","currency":"USD","ambiguous":false}]` | Known rental total required; finite nonnegative Decimal strings; all currencies agree |
| `deposit_conditions`, `cancellation_conditions` | `[{"value":"Actual explicitly agreed condition text","ambiguous":false}]` | Explicit agreed policy, not an empty/unknown placeholder |
| `included_items` | Equipment-item shape | Known quantities, or explicitly confirm none as described below |

Amount `kind` accepts `rental_total`, `total_payable`, `deposit`, `tax`, `delivery`,
`other`. `rental_total` is the rental fee/subtotal; `total_payable` is the inclusive
stated total, never an additional charge. A USD 120 rental fee plus USD 80 deposit
with USD 200 total payable remains three separate claims, not USD 400 of charges.
Review checks competing values within each kind and consistent currencies; it
does not infer component inclusion or calculate missing totals. A stated
`total_payable` cannot substitute for a missing rental fee. It is optional when
not stated in evidence. Correct old classifications only through an explicit
amounts revision with a reason; that creates a new unconfirmed version and leaves
the original AI draft and agreement unchanged.

For genuinely no included items, use a change with `category: "included_items"`,
nonblank `reason`, `items: []`, `explicit_none: true`. This is recorded as an
explicit customer assertion, not fabricated equipment. `explicit_none` is invalid
for equipment or populated lists. Explicit no-deposit/no-fee conditions may be
entered as actual agreed wording; absence of text is never interpreted as those
conditions. Multiple complementary policy clauses alone are not conflicts.
Explicit ambiguity flags and directly opposing statements with matching scope
still block confirmation. Lexical checks do not establish complete semantic
consistency; unresolved meaning requires explicit human clarification. Customers
may explicitly consolidate clauses with a reason while preserving every clause.
Ambiguous/nonexistent DST local times require an explicit UTC offset. These are
validation checks, not cancellation/consequence or financial calculations.

## Transactions, fingerprints and invalidation

- Fingerprints bind exact version UUID/number, parent/draft, content, correction
  reasons/actor, source fingerprints and acknowledged source IDs. Confirmation
  compares the supplied fingerprint inside the same transaction as persistence.
- Successful evidence writes, AI draft publication, agreement imports/revisions
  and confirmations take the **same booking row lock**. PDF parsing and AI calls
  hold no booking lock; final writes take it before committing. No AI call is
  performed by any customer review endpoint.
- Latest-version checks serialize concurrent revisions and confirmation. A
  confirmation that commits before a later mutation remains valid historical
  evidence of that instant, but cannot count as current afterward.
- Added evidence, a new AI draft, or any new agreement version invalidates current
  review by current-state comparison, preserving all historical records. A new
  AI draft must be imported for review before corrections/confirmation continue.
- Every current source ID must be explicitly acknowledged on revisions. This is
  manual review attestation, not automated comparison of newly added messages.
  The customer must resolve actual differences; the system does not infer
  precedence from upload order or prove the truth of customer-entered assertions.
- Future backend payment work must invoke
  `agreements.service.require_current_confirmation(session, booking_id)` while
  retaining the booking lock through its protected state change, and implement
  its later comparison/payment requirements. A historical confirmation row or
  frontend flag is insufficient. **No payment eligibility is granted here.**

## Focused checks

```sh
cd backend
uv run --frozen pytest -q tests/test_customer_review.py tests/test_bookings_evidence.py tests/test_drafts.py::test_concurrent_version_creation tests/test_drafts.py::test_full_draft_persistence_and_decimal
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen alembic current
uv run --frozen alembic check
```

Tests use an isolated PostgreSQL database, fake seeded extraction and blocked or
mocked model calls. They cover successful/idempotent confirmation, source versus
customer provenance, preserved AI drafts, explicit reasons, missing/conflicting
terms, stale fingerprints/versions, added evidence/new drafts, database
immutability, duplicate-import protection and concurrent revision/confirmation/
evidence interleavings. Existing customer records are never reset.

## Customer review screen

Start FastAPI on port 8000 using the README instructions, then `cd frontend &&
npm run dev`. Open http://127.0.0.1:5173. No Gemini credentials or calls are needed
for reviewing a saved draft.
New customers can complete [booking creation and evidence intake](starting-flow.md)
in **Sources & draft**, then explicitly generate a draft and open review.

1. Select the booking. Open an existing agreement version, or enter a provisional
   customer label and explicitly **Open latest saved draft** if no review exists.
   Draft import creates an unconfirmed review version without running extraction.
2. Read the source evidence in the right column (below conditions on small screens).
   Expand original PDF pages or pasted text. Each saved source-supported condition
   shows its exact quotation, source link and page. Customer corrections show
   their provenance/reason instead of fabricated citations.
3. Edit fields directly. For the existing booking, explicitly enter the agreed
   camera quantity; replace the amounts category with rental fee USD 120,
   deposit USD 80 and inclusive total payable USD 200 if these are the reviewed
   agreed values. Nothing is changed automatically. Every changed category needs
   a reason; all rows in that category become customer-entered corrections.
4. Complementary cancellation clauses may remain separate. To consolidate them,
   copy both complete clauses into one policy field, explicitly remove the other
   row and explain the change. Preserve both clauses. Genuine unresolved terms
   must retain their unresolved/conflicting checkbox until explicitly resolved.
5. Acknowledge every source, enter an overall review reason and **Save review**.
   The server checks the original version fingerprint. Saving also
   supports an explicit re-review of new evidence with no condition changes.
6. Review the new saved version. Source checkboxes and final acknowledgement reset
   after saving. Acknowledge sources again, explicitly agree to the shown version,
   then **Confirm version**. Blockers appear beside relevant sections and in the
   summary. Local unsaved edits, old versions and incomplete terms cannot confirm.

Historical versions and their audit JSON are readable through the version picker.
A stale 409 response preserves edits and blocks further actions until an explicit
refresh; no silent retry or overwrite. Booking/version switches warn before
unsaved edits are discarded. Decimal amounts remain strings throughout requests.
The backend remains authoritative for completeness, fingerprints, concurrency
and current confirmation. Refresh is manual; another tab's changes are checked
by the server when an action is submitted. There is no authentication, payment,
comparison, calculator, evidence upload or extraction action on this screen.

Policy consistency uses explicit ambiguity flags and conservative lexical checks
for directly opposed refund terms with the same wording/scope. It does not claim
complete semantic contradiction detection. Different complementary clauses alone
are not automatically considered conflicts; human review is still required.

Change badges compare editable values with the saved version after the same form
normalization. Opening unchanged included items or restoring original values does
not create a correction; actual edits still require a category reason. With Vite
running and headless Chrome remote debugging on port 9225, the focused offline
browser regression is `node frontend/tests/included-items.browser.mjs` from the
repository root (Node 22). All API responses and mutations are mocked; this check
never reads or modifies customer records or calls AI/PayPal.
