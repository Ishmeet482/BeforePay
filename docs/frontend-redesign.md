# Rental-agreement frontend redesign — 2026-11-02

Current product entry/workspaces and verification: [product redesign](product-redesign-2026-11-03.md). The [2026-11-02 workspace overhaul](beforepay-ux-overhaul.md) and stage below record earlier verification.

BeforePay now starts with bookings and a saved-data overview, then leads the
customer through terms, differences, cancellation consequences and sandbox
checkout. This is a layout and interaction redesign of the existing React app;
backend contracts and financial/approval services are unchanged.

## Structure and interactions

| Previous interface | New interface | Purpose |
| --- | --- | --- |
| Introductory hero, booking dropdown and five form tabs | Concise booking rows, a compact workflow rail and an overview with one primary next action | Explain where each booking stands without requiring prior guidance |
| All agreement fields open immediately | Readable document sections with section editors opened on request | Make the agreement readable before asking for corrections |
| Evidence in a separate long column | Evidence buttons beside terms open a native dialog drawer | Read exact quotation and original text/PDF pages in context |
| Merchant forms precede results | Differences first, highlighted wording, both saved versions and collapsed matches; independent merchant editor below | Show changed obligations even when total price stays the same |
| Rule configuration precedes cancellation preview | Cancellation date/time first; approved results beside inputs on desktop and ahead of them on mobile; focused rule-review panel | Lead with supported consequences, keep policy review separate |
| Checkout forms can remain beside completed payment | Completed receipt and payment history replace approval forms | Preserve historical proof and avoid suggesting another payment |
| Switching tabs unmounts edited forms | Visited workspaces stay mounted within the booking | Keep unsaved terms, reasons, labels, acknowledgements and preview inputs during normal tab navigation |

Warm neutral surfaces, flat document separators, sharp local system typography,
restrained green actions and state labels replace the previous generic form-card
layout. Amber highlights actual changed policy wording; red identifies errors.
Status meaning is also written in text. No decorative imagery, gradients,
external fonts, fabricated activity metrics or added component dependencies.

Booking rows show name, recorded equipment, human-readable timezone-labelled
pickup/return, stated inclusive total and status derived from existing endpoints.
Missing or ambiguous values remain explicit. Overview includes separate rental
fee/deposit/inclusive total, saved agreement/comparison/payment state and the next
required action. A paid overview uses the receipt amount; it avoids mixing current
component amounts into a receipt total when the agreement version has changed.
No frontend arithmetic determines amounts, eligibility, cancellation outcomes or
payment status. Status-read failure is shown as unavailable, not as success.

The deposit-impact callout is deliberately narrow: a current comparison must
report a deposit-policy difference, the saved wording must show refundability
versus non-refundability, and both bound amount sets must contain the same single
deposit amount/currency. An unchanged single inclusive total can be mentioned,
without being treated as a policy match. The callout identifies the amount at
issue; it does not calculate or guarantee a lost refund. Exact consequences still
require separately reviewed cancellation rules. Stale comparisons show a warning
and suppress this current-impact callout. Highlighting marks tokens absent from
the opposite text; it is a visual aid, not a semantic diff or policy verdict.

## Safeguards retained

- Text/PDF intake, unchanged original text, explicit source selection and explicit
  AI draft generation/opening remain separate actions. Extracted terms are
  readable before agreement editing. Source quotations and page references remain
  available; customer-entered corrections do not acquire invented citations.
- Correction/category reasons, overall review reason, all-source acknowledgements,
  exact version/fingerprint submissions and separate agreement confirmation remain.
  Save does not confirm. New versions reset acknowledgements. Stale server errors
  preserve edited fields and require refresh before further save/confirmation.
- Merchant samples only fill forms. Save creates an independent merchant version;
  Compare remains explicit and uses exact agreement/proposal fingerprints.
  Policy comparison is labelled AI-assisted, not a guarantee or customer approval.
  Merchant editing/customer review are labelled prototype workspaces, not verified
  or authenticated roles.
- Reviewer name precedes AI rule proposal. Proposal/manual editing, saving and
  explicit confirmation stay separate. Exact clauses, cutoff ownership, component
  rule fields, completeness/no-contradiction/version attestations and review note
  remain. Saved rule history, origin, blockers and approval details are accessible.
- Cancellation results come from the backend. Date/time edits clear the previous
  result. Preview needs current approved rules; paired previews need both current
  approvals. Python Decimal/timezone-aware calculations remain untouched.
  Preview does not cancel a booking or issue a refund.
- Checkout retains backend eligibility, exact-context explicit approval, separate
  SDK initialization/buyer action, durable attempt resume/reconcile/retry paths and
  immutable receipt handling. Loading a screen never loads the PayPal SDK, creates
  an order, captures or approves. Uncertain/pending states are not paid. Receipt
  history preserves captured versions; post-capture refunds/disputes remain outside
  this prototype's scope.
- Primary actions include an adjacent, specific disabled explanation, linked by
  `aria-describedby`. Focus rings, native buttons/details/labels and status text
  support keyboard use. Drawer has a labelled native modal, Escape handling,
  focus restoration, body scroll lock and full-width mobile presentation.
  IDs, fingerprints and audit JSON stay in optional details.

Existing backend models, routes, migrations, provider integration and payment
eligibility checks were not changed. No database connection or records were used
for the redesign or its browser verification. Backend `.env` was not read/edited;
no PayPal/Gemini calls, deployment, publication or public tunnel actions occurred.

## Verification and reproduction

Verified runtime: Node 24.2.0, npm 11.3.0 (explicit
`/usr/local/opt/node@22/bin` PATH; the binary in that directory actually reports
Node 24.2.0 despite its directory name);
existing React 19/TypeScript 5.9/Vite 7/Tailwind 4 stack and lockfile retained.
No dependencies added. Frozen `npm ci` passed, audit reported zero vulnerabilities.
`npm run build` passed, including `tsc --noEmit` and Vite production output.
An initial build inherited unsupported Node 18 through npm's script PATH; final
builds explicitly used the supported Node 24.2.0 binary and completed without
that warning.

Browser checks used a separate headless Chrome profile and loopback QA server at
port 5187. `vite.qa.config.ts` explicitly disables environment-file loading and
has **no backend proxy**. Fixtures replace fetch before navigation, reject unknown
API operations, and block PayPal/Google hosts. Synthetic browser upload fixtures
verify multipart handling, not actual backend PDF parsing. Synthetic AI/payment
responses are test fixtures, never persisted drafts, approvals or receipts.

Passed checks:

- `tests/redesign.browser.mjs`: **83 assertions**. Empty state plus awaiting review,
  changed deposit policy, stale comparison, missing rules, ready checkout,
  uncertain payment and completed receipt at **1440×1000** and **390×844**.
  Includes no implicit writes on navigation, human timezone display, no horizontal
  overflow, drawer quotations/pages/Escape/focus restoration, mobile drawer width,
  edit preservation, exact reason/source/fingerprint payloads, stale rejection,
  separate human rule approval, backend refund rendering/clearing, text/PDF intake,
  explicit source generation, merchant save versus compare, explicit reconciliation
  and exact separate checkout approval. No uncaught browser exceptions.
- `tests/included-items.browser.mjs`: **12 assertions** passed. Updated navigation
  to open Agreement and its section editor; retained normalization, no-change save,
  edit/revert, correction-reason, complete-item and provenance assertions.
- `tests/paypal-approval.browser.mjs`: **7 assertions** passed. SDK initialization
  creates no order; explicit button gets the real provider-order-ID envelope,
  stored currency/amount and sandbox SDK config. This mocked regression never
  invokes capture or downloads the real SDK.

Reproduce with Node 22.12+ or a newer supported version in separate terminals:

```sh
cd frontend
npm ci
npm run build
npm run dev:qa
```

```sh
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --disable-gpu --no-first-run --no-default-browser-check \
  --remote-debugging-port=9228 \
  --user-data-dir=/private/tmp/contextkey-redesign-chrome about:blank
```

```sh
cd frontend
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 npm run test:browser
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/included-items.browser.mjs
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/paypal-approval.browser.mjs
```

The browser suites share the page; run them sequentially. Screenshots from the new
suite are synthetic and written to `/private/tmp/contextkey-redesign/`, including
booking overview, changed-policy comparison, evidence drawer and completed receipt
at both sizes, plus desktop cancellation results. Owned QA processes are stopped
after verification; existing user development/backend/tunnel processes are not
managed or restarted by this task.

## Remaining limits

This remains a local unauthenticated sandbox prototype. Browser verification is
mocked; it does not establish live AI/payment behavior, database persistence,
provider availability or backend PDF parsing for this redesign. Backend tests
were not rerun because backend code/contracts were unchanged.

Edits persist in memory across workspace tabs within one booking, not across a
page reload or another browser. Leaving the booking warns before discarding its
workspace state; existing evidence/term/rule dirty-state unload warnings remain.
An already-open workspace keeps its local snapshot to preserve edits; use its
Refresh action after changing inputs elsewhere. The overview refreshes after
successful actions, while backend stale-version checks remain authoritative.
No polling or automatic AI, comparison, approval or payment action was introduced.

Booking summary/status uses several read endpoints per booking because the
existing booking-list API contains only booking identity/title. This adds read
traffic for large booking lists; no aggregation API, server pagination redesign
or backend caching was added. Dates/totals may require review or be unavailable;
the UI does not infer missing terms or a match from equal totals. Native
browser/assistive-technology behavior beyond tested Chrome and the two tested
viewports has not been independently audited.
