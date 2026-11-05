# BeforePay alignment and grouping refinement — 2026-11-03

Inspected rendered screens and their React/CSS implementations before editing. Preserved the existing warm neutral, deep-ink and restrained teal identity. [Before/after screenshots and print specimen](screenshots/beforepay-alignment/index.md) use isolated synthetic fixtures only.

## Changes

- Landing footer: removed the star before “AI helps read. You decide.”; aligned its heading and paragraph to the column edge and adjacent section.
- Bookings: replaced independently spaced header/row grids with one semantic five-column table. Booking/equipment, schedule, inclusive total, status and action share column definitions. Monetary headings and values align right. Tablet/mobile use labelled stacked rows; long names, missing terms and captured totals remain explicit.
- Agreement review: grouped all eight existing individually editable categories into equipment/included-item quantity tables, a pickup/return schedule, an amount/currency breakdown and readable policy sections. Small screens place evidence beneath the relevant item instead of squeezing long names into narrow columns. Larger item lists occupy the document width. Source acknowledgements remain beside the agreement on desktop/tablet and below it on mobile.
- Sources and merchant workspace: reused the same read-only term renderer for draft and buyer-baseline summaries. Original wording, quantities, currency, ambiguity, customer-entered provenance, correction reasons and evidence links remain available.
- Comparison: aligned charge/amount tables within buyer and merchant versions; retained exact quoted policy differences, consequences, unresolved issues and stale-version gates.
- Overview: consistent task/status/action columns and aligned financial summaries. Cancellation: aligned refund/retained amounts and readable wrapping while keeping rule authoring and explicit confirmation separate from previewing.
- Checkout: grouped available payment actions, aligned the recorded attempt amount and preserved uncertainty warnings. Payment history now uses a semantic status/recorded amount/details table, outside the receipt. Receipt amount/date alignment and copy-control sizing were refined; historical snapshot content and print separation remain intact.
- Shared controls: consistent heights, predictable evidence/edit positions, bounded selectors, visible focus, wrapping and reduced section padding. Inputs still expand normally; no fixed-height term cards or truncated clauses.

## Preserved safeguards

Existing save, correction-reason, acknowledgement and exact-version confirmation handlers remain separate. All eight agreement editors remain accessible. No automatic AI, comparison, approval or payment action was introduced. Unsaved values and correction reasons survive workspace navigation. Backend contracts, calculations, credentials, stored records, receipt snapshots and provider integrations were not changed. No dependencies or lockfiles changed.

## Verification

- `PATH="/usr/local/opt/node@22/bin:$PATH" npm --prefix frontend run build`: TypeScript and Vite passed.
- `frontend/tests/alignment.browser.mjs`: 107 assertions across 1440×1000 desktop, 834×1112 tablet and 390×844 mobile. Includes short and long terms, unknown quantities, long clauses, missing terms, blocked confirmation, unsaved edits, original evidence, booking columns, history and overflow checks.
- `frontend/tests/redesign.browser.mjs`: 187 assertions passed, including existing buyer/merchant journeys, keyboard/focus, blocked/error/stale/uncertain/completed states and receipt behaviour. Its merchant-editor focus assertion now waits for the existing asynchronous focus transition before checking it.
- `frontend/tests/included-items.browser.mjs`: 12 regressions passed; `frontend/tests/paypal-approval.browser.mjs`: 7 mocked SDK-handoff checks passed. No approval or capture was initiated.
- `node frontend/tests/branding.mjs`: 25 static brand/compatibility checks passed.
- Browser API responses are synthetic; provider origins are blocked. The shared fixture module is test-only. No real backend API or database was used.
- Actual before/after captures were visually reviewed. Review found narrow mobile term columns and excessive tablet booking stacking; these were corrected and recaptured. A one-page A4 synthetic receipt PDF was text-checked and visually inspected: immutable recorded amount/references remain, history/current changed amount/print controls are excluded.

For browser scripts, run the existing environment-free QA server (`npm --prefix frontend run dev:qa`), an isolated Chrome debugging session, then set `CDP_URL` and `FRONTEND_URL`. The alignment script accepts `BEFOREPAY_ALIGNMENT_PHASE=before|after` and saves to `/private/tmp/beforepay-alignment/`. Baseline files were captured before product changes; do not regenerate them from the refined implementation as historical evidence.

## Limits

Validation used desktop Chromium with emulated viewport sizes, not physical devices, Safari/Firefox or a dedicated screen-reader audit. Screenshots demonstrate layout with mocks, not live provider or database behaviour. The receipt fixture deliberately lacks captured itemisation; nothing was reconstructed from current terms. No live Gemini/PayPal calls, secrets, existing records, payments, deployment or publishing were involved.
