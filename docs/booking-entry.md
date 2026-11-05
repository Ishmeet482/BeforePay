# Buyer booking-creation entry

All creation entry points start the same Buyer demo flow: landing Start a booking, dashboard Create booking, empty-state Create your first booking and both `/#bookings/new` and legacy `/#merchant/bookings/new` URLs.

- **Visitor:** Buyer demo login opens first. Booking creation requires the displayed Buyer demo credentials; Merchant selection is disabled with an adjacent explanation. No booking request occurs on navigation or login.
- **Existing Buyer demo:** Create booking opens directly, retaining any in-memory title and focusing the title field.
- **Existing Merchant demo:** an explicit “Switch to Buyer to create a booking” dialog opens. Merchant identity and unsaved work remain until valid Buyer demo entry. Closing/cancelling or entering Merchant credentials creates nothing and keeps the current session. Generic Log in by role and Switch role still support both roles outside the creation intent.
- **After successful creation:** select the exact returned booking ID/title and open Buyer Sources & draft, with “Booking created” and guidance to add original quotation/messages/PDF. AI generation remains a separate explicit action.

How it works remains public. Roles remain local demo labels, not authenticated
people. The later [server-session increment](demo-sessions.md) independently gates
booking creation and all saved resources by expiring cookie ownership; role
switching reuses that session. Password behaviour remains browser-only as described
in [demo login](demo-login.md). Migration 0013 remains unapplied to development.

## Navigation and submission safeguards

A shared entry handler and canonical creation route ensure dashboard, empty-state and landing actions agree. Direct legacy merchant creation links normalize to Buyer creation. The title form renders only in Buyer view; submitting through an outdated form cannot create in Merchant demo. Existing booking-switch/discard warnings remain before replacing a mounted booking. Cancelling keeps its inputs and makes no creation request.

Creation waits for the initial saved-booking list, preventing a late initial list response from dropping the newly returned booking out of the UI. Initial shared-list reads depend on whether a demo booking workspace can be read, rather than each role/path change. Their successful completion updates list readiness together; URL normalization and role handoffs no longer restart reads unnecessarily or leave the form stuck loading.

The existing synchronous in-flight ref guard and disabled submit control prevent concurrent double submission. Creation is a single POST with no automatic retry. Failed/unknown outcomes retain the title and disable further submits until a successful explicit list refresh; the error asks the user to check whether the booking already exists before retrying. Refresh never resubmits creation. This is client flow protection, not server idempotency across tabs/reloads; the existing booking API contract is unchanged.

## Verification

Dedicated browser coverage uses only synthetic records and provider-blocked Chromium, with the environment-free Vite QA server and no backend proxy. It covers visitor/Buyer/Merchant entry on desktop, tablet and mobile; Merchant cancellation and wrong-role credentials; every creation button and both URL forms; exact returned ID/next step; double submit; delayed initial list reads; failed-result refresh gating; declined discard warnings; unchanged synthetic prior receipt; and public How it works.

No backend source, API contracts, database/schema/migrations, existing bookings, payment/receipt records, credentials, dependencies or lockfiles changed. No real database/API, Gemini/PayPal call, order, capture, deployment or publishing was used. Backend/database tests were not run for this frontend-only change; backend source and contracts are unchanged. Browser coverage uses emulated viewports, not physical devices or every browser engine.

Verification results:

- `PATH="/usr/local/opt/node@22/bin:$PATH" npm --prefix frontend run build`: TypeScript/Vite passed.
- `frontend/tests/booking-entry.browser.mjs`: **60 passed**, including deterministic delayed-list and held-POST cases.
- Existing demo login: **88 passed**; full Buyer/Merchant journey: **187 passed**.
- Existing workspace: **108 passed**; alignment: **107 passed**; included-item correction: **12 passed**; mocked SDK: **7 passed**. Total: **569 browser assertions**.
- `node frontend/tests/branding.mjs`: **28 passed**.
- [Desktop/tablet/mobile captures](screenshots/beforepay-booking-entry/index.md) visually reviewed, including Buyer-only modal and post-create Sources guidance.

Browser commands use `FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 node frontend/tests/booking-entry.browser.mjs` with the existing environment-free QA server and an isolated Chrome profile. All API traffic is synthetic.
