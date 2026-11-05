# BeforePay product entry and guided workspaces

Implemented 2026-11-03. This stage adds a real product entry page and rebuilds the
working interface around ownership, prerequisites and explicit outcomes. Backend
contracts, records, technical identifiers, calculations and payment guards remain
unchanged. No external Gemini or PayPal call was made.

## Entry and navigation

The root URL explains the product with **“The price matches. Do the terms?”**,
**Start a booking** and **Open your bookings**. The original code-rendered example
keeps USD 200 unchanged while a USD 80 refundable deposit becomes non-refundable.
It is explicitly labelled **illustrative**, **not a booking or live analysis**, and
not a refund calculation/payment record. There is no fabricated live feed, analysis
result or transaction. Three stages explain evidence → review changes → approve/pay.
AI assists only on request; people approve and Python calculates consequences.

Entry renders without application API reads or provider calls. Returning users can
open `/#bookings` directly; `/#bookings/new` opens the creation form without saving.
A booking opens at `/#bookings/BOOKING_ID`, with the actual saved next action chosen
from its review/comparison/policy/payment state. Hash routing needs no new server
route or router dependency. Reload retrieves records through existing read APIs.

Home and Bookings keep the currently opened booking workspace mounted. Its inputs
survive those navigation paths and workspace/perspective changes. Opening a different
booking warns before discarding the previous workspace. Inputs do not survive a
page reload/browser restart; this is not a persisted draft-forms feature. Existing
version, sample replacement, refresh and unload warnings remain.

## Design and task presentation

One product system uses deep ink navigation/headings, teal primary actions, cobalt
AI assistance, warm paper and differentiated buyer/merchant surfaces. Semantic
success, attention and blocked states pair colour with text and typographic symbols.
Buttons, input fields, selectors, feedback, focus rings and disclosures share tokens.
Larger local system typography adds hierarchy without loading remote fonts or assets.
Motion is limited to short feedback/hover transitions with reduced-motion support.
There are no decorative metrics, floating art, gradients or nonfunctional controls.

The design-taste-frontend skill informed the audit, composition, typographic
hierarchy and restraint. Its marketing guidance fits entry; its explicit exclusion
of multi-step product UI means cinematic motion, decorative imagery and quotation
truncation were not applied to task forms or exact source evidence. Settings:
DESIGN_VARIANCE 5, MOTION_INTENSITY 3, VISUAL_DENSITY 5. Existing React/TypeScript,
Vite, Tailwind and native controls remain; no dependency or lockfile changes.

| Workspace | Implemented hierarchy and outcome |
| --- | --- |
| Bookings | Scannable rental/date/total/status rows and specific saved-state actions, including **Resolve deposit change**, **Review extracted terms** and **View receipt**. No generic Continue funnel. Mobile dates, status and action use distinct rows. |
| Booking overview | Rental equipment, explicit-timezone dates, stated amounts, outstanding tasks and one next action. Navigation shows completed/current prerequisites; mobile indicates completion with labelled symbols and keeps the current tab in view. |
| Sources | Original evidence inbox beside AI drafting on desktop, stacked on mobile. Save source, select evidence, explicitly generate, then open an unconfirmed review. Selection never calls AI or acknowledges a source for confirmation. AI assistance has its own notice/surface. |
| Agreement | Explicit unconfirmed vs buyer-confirmed status, readable grouped terms, opt-in section editors and adjacent evidence drawer. Reviewer identity precedes saving. Reasons and source acknowledgements remain separate from exact-version confirmation. History is optional. |
| Merchant proposal | Labelled prototype view switch separates buyer review from merchant editing. **Copy buyer-confirmed terms into form** reuses the existing form-only matching helper; it establishes no merchant agreement and does not save/compare. Other illustrative samples remain optional. Each save creates an independent merchant version with label/reason. |
| Comparison | Changed wording, both versions and supported financial consequences lead; matches collapse. Resolution guidance routes to a corrected merchant proposal or reasoned buyer revision/renewed confirmation, followed by an explicit comparison. Same total never establishes a match. |
| Cancellation | Date/time and explicit timezone lead into Python-returned refund/retained amounts. Reviewed cutoff and applied cutoff/cancellation instants are visible. Rule authoring/AI proposal and human approval are a separately labelled task. Preview never cancels or refunds. |
| Checkout | Stated inclusive total and exact saved versions sit beside separate review/approval/PayPal steps. Server eligibility remains authoritative. An uncertain saved attempt leads with its warning and reconciliation actions, without fresh approval forms. |
| Completed payment | Current booking context sits **outside** the printable receipt. The preserved document shows captured amount/date, provider and exact approved references, copy controls and print action. Missing itemisation or historical booking title is never filled from current terms. Payment history stays outside the document; audit details collapse. |

Reviewer and buyer/merchant perspective labels are provisional. No authentication,
merchant authorization, access control or new real-world identity is implied.
Sandbox/test-funds and unverified-identity notices remain visible in app navigation.

## Teaching through use and retained safeguards

Short task explanations precede controls; longer reference material is available
in contextual help. Selected policy/version labels explain their consequences.
Disabled primary actions keep adjacent reasons and routes to the relevant task or
field. Evidence opens exact quotations and original PDF pages in a native modal
with focus trapping, Escape/focus restoration and full mobile width.

When a write in another task changes saved inputs, an already-open workspace shows
a refresh notice instead of silently resetting edits. Explicit refresh uses that
workspace's existing guard/discard warnings. The notice clears after a successful
saved-input read; a cancelled/failed refresh keeps it. This covers changes made in
this tab; there is no cross-browser push subscription or collaborative editor.
Booking list/overview status refreshes after successful writes. Snapshot reads
never constitute authorization and server stale-version checks remain mandatory.

No AI, comparison, confirmation, SDK loading, order, capture or retry runs on page
load/navigation. Existing exact fingerprints, source acknowledgements, overall and
section reasons, immutable versions, separate confirmations, rule attestations,
uncertain-result handling and backend payment locks/eligibility are preserved.
Buyer approval alone is never payment proof. The wire API and receipt snapshot
schema were not changed. Existing databases, environment variables, invoice prefixes,
event/SDK identifiers, migrations, stored references and project directory retain
their compatibility names.

## Verification and screenshots

The isolated QA config loads no environment files and has no backend proxy.
Browser tests install synthetic API fixtures before navigation and block provider
hosts. AI proposals and receipt/provider responses in those tests are mocks,
never persisted developer records. Test navigation uses fresh document query keys
where appropriate, so hash-only navigation cannot accidentally reuse a previous
fixture. Real hash navigation is tested separately for retained inputs.

The suite covers entry, a genuinely empty first-time booking through explicit
checkout approval, a returning user's saved-state action, returning paid receipt,
changed-term blockers, stale comparison/save rejection, missing rules, reviewed
cutoff/refund previews, errors, uncertain payment, keyboard focus and copy, drawer
interaction, mobile/tablet/desktop overflow, and isolated receipt printing. It does
not create an order or capture in the first-time UI journey; the separate existing
SDK handoff regression mocks the SDK, blocks PayPal hosts and never invokes approval.

Reproduce with the isolated QA server on 5187 and an isolated headless Chrome CDP
page on 9228 as described in [QA setup](frontend-redesign.md). Run browser suites
sequentially; Node must satisfy `frontend/package.json`:

```sh
cd frontend
npm run build
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/redesign.browser.mjs
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/included-items.browser.mjs
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/paypal-approval.browser.mjs
node tests/branding.mjs
```

[Rendered screenshot gallery](screenshots/beforepay-product/index.md) includes entry
and every booking workspace, responsive variants, error/blocking states and the
synthetic A4 receipt. Screenshots are interface evidence only. They do not establish
live AI/model quality, sandbox settlement or browser-interruption recovery.

## Remaining functional limits

- No authentication, merchant permissions, live payments, actual booking
  cancellation or refund operations. The receipt is an app-issued historical
  sandbox capture record, not a PayPal-issued receipt or proof of current settlement.
- Cancellation remains the existing narrow, pre-pickup, reviewed USD two-band
  model. Unsupported/contradictory/stale policies require clarification.
- Workspaces keep snapshots until explicitly refreshed. This tab shows known
  cross-task changes; changes from another browser/process are checked by the
  backend, not a live subscription. Unsaved forms remain in memory only.
- Booking status still uses several existing reads per booking; no aggregation API
  or unsupported collaboration feature was added. The entry itself requires none.
- Responsive/keyboard/accessibility-tree and print checks use Chrome emulation.
  They are not a complete WCAG audit, screen-reader certification or real-device/
  Safari/Firefox verification. Browser print settings can change pagination.
- No real Gemini/PayPal call, credential access, existing-record mutation, tunnel,
  deployment, publication or live recovery demonstration occurred in this stage.


## Recorded checks

- Node 24.2.0 / npm 11.3.0: `npm run build` passed strict TypeScript and Vite production build.
- `redesign.browser.mjs`: **187 assertions passed**; synthetic APIs only, provider hosts blocked. Includes first-time and returning paths, direct-route fallback, version/reason/acknowledgement payloads, retained inputs, stale/error/blocked states, navigation focus, copy/print and responsive layouts.
- Existing `included-items.browser.mjs`: **12 passed**; `paypal-approval.browser.mjs`: **7 passed**. No real SDK/provider call or capture. Navigation waits for committed focus before keyboard events; new-document keys prevent hash-only fixture reuse.
- `branding.mjs`: **24 static checks passed**, including compatibility identifiers.
- `UV_CACHE_DIR=/private/tmp/beforepay-uv-cache uv run --frozen pytest -q -x --tb=short tests/test_starting_journey.py tests/test_customer_review.py tests/test_booking_comparisons.py tests/test_cancellation_preview.py tests/test_paypal_sandbox.py tests/test_paypal_webhooks.py`: **182 passed**, six dependency warnings. Existing fixture creates/migrates/removes only its randomly named disposable PostgreSQL database, uses `_env_file=None` and blocks live providers. Existing development records were untouched.
- Backend `uv run --frozen ruff check .` and `uv run --frozen ruff format --check .`: passed; 78 files already formatted. No backend source changed.
- Actual print action and receipt-only print media verified in Chrome. PyMuPDF confirms **one A4 page**, exact captured total/references, and no current booking title, app controls, history or audit. The rendered print artifact was visually reviewed.
- Core text token pairs (body, primary, success, attention, blocked, AI and navigation) each exceed **4.5:1** contrast; lowest tested pair 6.36:1. This is a token check, not a full-page accessibility certification.
- Rendered entry and all workspaces visually inspected across desktop/mobile and representative tablet views. Corrected cramped mobile dates, repeated introductory context, current-tab visibility, rule status alignment and result focus before final artifacts.
