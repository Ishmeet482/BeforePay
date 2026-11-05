# Buyer and Merchant prototype workspaces — stage 1

The later [demo-entry stage](demo-login.md) adds browser-only role selection.
[Phase 1 server sessions](demo-sessions.md) now independently enforce anonymous
booking ownership. The two views share only their current session's bookings.
Migration 0013 is unapplied to development. The stage-1 history below predates
that backend boundary; authenticated people/roles remain unsupported.

BeforePay now has separate task navigation and overviews for two prototype views of the **same bookings and saved versions**. Switching views changes navigation only. It never saves, confirms, compares, starts AI, creates an order or captures a payment.

**Prototype views—not authenticated accounts.** No authentication, role permissions, database migration or backend permission change is included. Provisional editor/reviewer labels remain self-reported. These UI boundaries do not restrict direct API access.

## Entry and navigation

- Buyer: `/#bookings`, or `/#bookings/BOOKING_ID`. Existing links remain compatible.
- Merchant: `/#merchant/bookings`, or `/#merchant/bookings/BOOKING_ID`.
- Global Buyer/Merchant links open the corresponding shared booking list. The in-booking workspace switch retains the same booking and returns to that view's last task. Booking IDs are never copied or replaced.
- Landing page retains Start a booking and adds a Merchant entry. Creating a booking uses the existing explicit endpoint through the [Buyer-only creation journey](booking-entry.md). Merchant sessions explicitly switch to Buyer demo before creation; success opens Sources & draft.
- Browser history and direct links use the same route parser. Opening another booking or creating another while a previous booking is mounted retains the existing discard warning. Home, lists, task and prototype switches keep the mounted booking forms. Refreshing saved inputs retains existing explicit discard checks. A full page reload is not durable draft storage.

## Buyer journey

Overview → Sources & draft → Agreement → Compare booking → Cancellation → Checkout & receipt.

Evidence intake, explicitly requested Gemini drafting, source evidence/acknowledgements, correction reasons, separate immutable save/confirmation, exact-version comparison, Python cancellation previews and guarded sandbox checkout are retained. The existing completed-payment receipt stays in this flow. Missing merchant proposals lead to the Merchant handoff; comparison differences remain visible and require resolution. No comparison or payment runs on navigation.

## Merchant journey

Overview → Buyer reference → Final proposal → Merchant policy rules → Payment status.

- **Buyer reference:** read-only current saved agreement, original wording, provenance and evidence. It is labelled buyer-confirmed only when current confirmation is true; otherwise it explicitly requests buyer review. It does not substitute an old confirmation for a current one. Editing/confirmation requires an explicit switch to Buyer review.
- **Final proposal:** the existing independent immutable proposal editor, including saved version selection, reasons, unknown/conflicting terms and optimistic latest-version guard. Buyer baseline remains read-only alongside the fields. Optional copying/samples fill fields only. Save appends a version; comparison remains an explicit Buyer action. One shared editor instance retains unsaved values across both views.
- **Merchant policy rules:** reuses existing rule preparation, explicit AI proposal, manual editing, source clauses, separate review attestations and exact-fingerprint confirmation. This instance is fixed to the latest proposal target. It retains its own unsaved fields separately from the Buyer calculator. Approval concerns merchant-proposal rules only; it does not confirm the buyer agreement or approve checkout. The existing API field `customer_label` remains unchanged and provisional. Buyer cancellation retains both policy targets and side-by-side preview capability; no role enforcement is implied.
- **Payment status:** read-only recorded attempts and immutable receipt amount/date. Uncertain/pending/buyer-approved orders remain unpaid unless a captured receipt exists. An explicit handoff opens the existing Buyer receipt or payment review. Merchant view adds no payment, capture, reconcile, cancellation or refund endpoint/action.

## Saved-state handoffs

Overviews and booking-list actions derive from existing review, proposal, comparison, rule, eligibility, attempt and receipt responses. Merchant handoffs include Buyer review needed, Merchant proposal needed, Resolve booking differences, Merchant policy review needed and recorded payment status. Buyer retains backend-derived checkout blockers and View receipt. Stale comparisons require renewed explicit comparison. Saved-state failures display an error/retry instead of an old payment summary.

Existing `contextkey:changed` notifications refresh overview data. Mounted inactive editors disclose cross-task saved changes and require explicit refresh; they do not silently overwrite fields. No polling worker, notification service or automatic proposal acceptance was added.

## Inspected contracts and preservation

Read repository instructions, implementation plan, customer review/comparison/cancellation guides, navigation/state/frame components, existing editor/payment components and synchronous comparison/cancellation routes before implementation. Reused `/review`, agreement GET, `/merchant-bookings`, `/comparisons`, `/cancellation/rules`, `/checkout/eligibility`, `/checkout/attempts` and `/checkout/receipt` contracts. All writes retain existing payloads, explicit actions, expected version IDs/fingerprints and backend guards. Numeric/date calculations and immutable records remain backend-owned.

No backend source, schemas, migrations, permissions, dependencies, lockfiles, environment files, credentials or existing records were changed. No real API/database, Gemini/PayPal calls, payments, tunnels, deployment or publication were used in verification.

## Verification and screenshots

The environment-free QA Vite server has no backend proxy or environment-file loading. Chromium tests inject synthetic API fixtures and block provider origins. Run browser scripts with `FRONTEND_URL=http://127.0.0.1:5187` and `CDP_URL` pointing to an isolated local debugging session.

Completed checks:

- `PATH="/usr/local/opt/node@22/bin:$PATH" npm --prefix frontend run build`: TypeScript/Vite passed.
- `frontend/tests/workspaces.browser.mjs`: **108 passed**. Buyer/Merchant navigation, direct links, shared lists/version IDs, unchanged buyer confirmation after proposal revision, read-only reference, independent unsaved inputs, explicit merchant rule save/approval targets, unpaid/uncertain/completed status, error/retry, receipt handoff, named accessibility controls and responsive overflow/heading checks.
- `frontend/tests/redesign.browser.mjs`: **187 passed**, including continuous buyer/merchant journeys and existing approval/payment/stale/error safeguards. Updated expected notice to “not authenticated accounts”; no guard assertions removed.
- `frontend/tests/alignment.browser.mjs`: **107 passed** across desktop/tablet/mobile.
- Existing included-item corrections: **12 passed**; mocked PayPal SDK handoff: **7 passed**. No real payment approval/capture was invoked.
- `node frontend/tests/branding.mjs`: **26 passed**.
- Current synthetic receipt PDF: one page, captured total and provider/version references present; navigation, history and changed current total excluded. Offline text inspection passed.
- Rendered desktop/tablet/mobile captures reviewed. Backend functional/database tests were not rerun for this frontend-only stage; no real database was connected.

[Desktop/tablet/mobile screenshots](screenshots/beforepay-workspaces/index.md) document mocked behaviour only. They do not establish authenticated identities or live integrations. Physical devices, Safari/Firefox and a dedicated screen-reader audit remain unverified.

## Authentication is a separate stage

Pause for user review here. Account provisioning, authentication/session handling, booking membership, server-side buyer/merchant authorization and migration strategy are not implemented or implicitly authorized by this stage. Current UI labels and rule approvals must not be presented as authenticated merchant identity or access control.
