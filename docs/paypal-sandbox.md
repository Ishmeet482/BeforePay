# PayPal sandbox checkout

This milestone implements **sandbox only**. It does not enable live payments,
PayPal billing changes, real funds, AI calls or automatic payment requests. No
external payment/AI calls were made during implementation. Refunds,
dispute/reversal processing and shared-user authentication remain deferred.

## APIMatic Context Plugin compatibility and setup (original checkout stage)

Verified against APIMatic's official [PayPal plugin page](https://context.apimatic.io/plugins/paypal/),
[plugin overview](https://docs.apimatic.io/v4/generate-context-plugins/context-plugins/)
and [installer documentation](https://github.com/apimatic/context-plugins-installer):
Codex is supported. The installer requires Node 18+ and a `codex` CLI on PATH;
this workspace has Node 22.23.1 and Codex CLI 0.164.0-alpha.11.1, and read-only
`codex plugin --help` confirms plugin management commands.

Documented setup, if you choose to install it:

```sh
npx context-plugins install paypal --targets codex
```

The installer registers the marketplace and adds the plugin through Codex. Start
a **new Codex session** afterward; reload the VS Code window if needed. Optional
installer diagnostics: `npx context-plugins doctor` and
`npx context-plugins installed --targets codex`. The installer documents telemetry
controls such as `DO_NOT_TRACK=1` or `CP_TELEMETRY=off`.

**At the original checkout stage (2026-10-31), the plugin was not installed,
loaded or used.** The webhook stage (2026-11-02) used the now-installed plugin
skills; see [guidance attribution](paypal-webhooks.md#installed-apimatic-paypal-context-plugin-guidance).
Implementation retains HTTPX and existing dependencies. No global plugin
configuration was changed during either implementation stage.

## Required backend settings

Create a **Sandbox REST app** and Sandbox Business seller/Personal buyer accounts
in the [PayPal developer dashboard](https://developer.paypal.com/dashboard/).
See official [sandbox accounts](https://developer.paypal.com/tools/sandbox/accounts/)
and [REST authentication](https://developer.paypal.com/api/rest/authentication/).
Use a seller app's sandbox credentials and the matching Business merchant/account
ID. The buyer must be a separate Sandbox Personal account, not a live account or
the seller account.

Configure only `backend/.env` (never Git or frontend VITE variables):

```dotenv
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_SANDBOX_ENABLED=true
PAYPAL_SANDBOX_CLIENT_ID=YOUR_SANDBOX_REST_APP_CLIENT_ID
PAYPAL_SANDBOX_CLIENT_SECRET=YOUR_SANDBOX_REST_APP_SECRET
PAYPAL_SANDBOX_MERCHANT_ID=YOUR_SANDBOX_BUSINESS_MERCHANT_ID
```

The default is disabled. Empty credentials give a clear 503; the actual `.env`
was not changed. Existing legacy PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET variables
are not used. No live base URL/configuration exists, and a non-sandbox environment
is rejected. HTTP requests use the fixed sandbox API host, ignore proxy environment
variables, and never follow redirects. The frontend loads only the sandbox SDK
v6 origin after an explicit click. Client ID is a public SDK identifier returned
by the backend config endpoint; client secret/access tokens stay backend-only.
Changing merchant identity changes checkout context and requires renewed approval.

Apply the additive migration and start services:

```sh
cd backend
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

```sh
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. Keep the local loopback binding: customer/merchant
labels remain self-declared until authentication is implemented.

## Browser verification (manual sandbox calls only when you choose)

1. Select a booking. Confirm the latest complete agreement, save a matching latest
   merchant proposal, and explicitly compare. All eight comparison categories
   must match; equal total price alone is insufficient.
2. In Cancellation preview, review/confirm complete current rules for **both**
   versions. Their cutoff/boundary and calculated component refunds must agree.
   This extra deterministic check prevents inconsistent policies passing solely
   because a semantic comparison returned matches.
3. Open **Sandbox checkout**. Missing/currentness/policy problems appear as blocked.
   Loading this tab makes local read requests only; it loads no PayPal SDK and
   creates no external order. Refresh after resolving prerequisites.
4. Inspect the exact agreement/proposal versions, comparison and inclusive stored
   USD total. Enter your provisional label, explicitly acknowledge those terms,
   then **Approve exact sandbox checkout**. This creates an immutable local
   checkout approval, not an order or payment.
5. Click **Load sandbox PayPal buyer approval**. This explicitly loads the sandbox
   SDK v6 and checks buyer-method availability. Click its PayPal button to create
   or reuse the server-bound order and approve it using the Sandbox Personal buyer.
   The official SDK handles buyer approval; its callback is not proof of payment.
6. After buyer approval the backend verifies the sandbox order, rechecks current
   eligibility and captures. A receipt appears only after authenticated PayPal
   order retrieval verifies a final COMPLETED capture, exact amount/currency,
   expected merchant, order and attempt identifiers. Receipt links the captured
   agreement/proposal/comparison and reviewed policies.
7. Close/cancel the buyer window to test cancelled checkout. A capture that may
   have occurred cannot be marked cancelled; it must be reconciled. Provider
   pending/declined states show pending/failed with no paid receipt. SDK/network
   errors show a failure/uncertain message, never fake success.
8. If interrupted or uncertain, **Reconcile PayPal status** retrieves the existing
   order only. If capture is still uncertain, a separate explicit retry first
   retrieves it again, rechecks eligibility and reuses the original capture key.
   There is no automatic retry. Resume saved checkout approval after refresh to
   reopen an uncaptured buyer order, or cancel it locally before a new approval.
9. Change evidence, proposal, agreement, comparison or rules before capture to
   verify server blocking. Do not create a fresh attempt to bypass pending or
   uncertain outcomes. An already captured historical payment is still recorded
   by reconciliation; later changes do not rewrite its receipt or authorize more
   payment. One verified sandbox payment per booking is supported in this milestone.

## Server eligibility and concurrency

Checkout approval binds the current agreement confirmation, exact agreement and
latest merchant proposal fingerprints, latest comparison ID/fingerprint, reviewed
cancellation rule/approval fingerprints, merchant ID and derived amount/currency.
The backend requires the existing `require_current_confirmation` guard, a current
all-matching comparison, recomputed numeric/date matches and reviewed consistent
policies. Missing, ambiguous, differing or stale terms block creation/capture.

Amounts come from a unique explicit positive USD `total_payable`, with reviewed
component accounting. The inclusive total is not added to rental/deposit again.
Order/capture endpoints accept local approval/attempt IDs, never browser amounts,
currency, payee or arbitrary PayPal URLs. Returned IDs are validated before use.

All version/evidence mutations and payment actions use the same booking row lock.
A durable capture intent/request ID is committed before the remote action. After
reacquiring the lock, eligibility is checked again. The lock is retained across
capture and verification, so an edit must occur before authorization (and block
it) or afterward (and remain a later historical revision), never slip between.
There is intentionally a bounded network wait while this lock is held.

## Idempotency, persistence and reconciliation

Migration `0007_paypal_sandbox` adds immutable checkout approvals, append-only
payment events and immutable agreement-linked receipts, plus durable mutable
attempt status. Database protection prevents changing attempt identity, approval,
amount/currency, stable keys, known order/capture IDs or capture-intent timestamp.
Existing agreement/proposal/evidence/confirmation records are not rewritten.

Each attempt has separate persisted UUID `PayPal-Request-Id` values for create and
capture. Repeated requests reuse the same attempt/keys; another active/uncertain
attempt blocks a second order. Receipt booking/order/capture uniqueness adds a
local duplicate guard. Success requires provider verification, not a redirect,
browser callback, SDK promise or mocked fallback. Only safe status codes and
identifiers are persisted; raw payment/buyer bodies and secrets are not logged.

Unknown capture outcomes are stored as `capture_uncertain`. Before every capture
POST, including an explicit retry, the server GETs and verifies the existing order.
COMPLETED is recorded; PENDING is left pending; known captures are never silently
replaced. Retry requires explicit intent, APPROVED/no capture, unchanged eligibility
and the same key. A conservative **15-minute local replay window** limits uncertain
create/capture replays; this is an operational guard, not a rental policy or claim
about PayPal's retention guarantee. Beyond it, GET reconciliation/manual sandbox
account review is required rather than rotating keys or blindly charging again.

The capture request and follow-up provider GET can fail independently. A timeout
may mean PayPal captured successfully; never treat it as cancelled or create a
new payment automatically. Reconciliation may record that completed capture even
if the booking has since changed, preserving the original approved references.

## Official references used

- [PayPal SDK v6 sandbox setup](https://developer.paypal.com/sdk/js/set-up): sandbox
  script origin, public client-ID initialization and `{orderId}` promise contract.
- [JavaScript SDK reference](https://developer.paypal.com/sdk/js/reference/): buyer
  method availability, one-time sessions and approval/cancel/error callbacks.
- [Orders v2 create](https://developer.paypal.com/api/orders/v2/orders-create) and
  [capture](https://developer.paypal.com/api/orders/v2/orders-capture): server-side
  orders and capture, request IDs, representation responses and statuses.
- [PayPal idempotency](https://developer.paypal.com/api/rest/reference/idempotency/):
  stable request IDs and ambiguous-outcome retry semantics.

## Checks and remaining limits

Tests use isolated PostgreSQL, mocked provider calls and offline HTTPX transport;
PayPal/AI constructors/transports are blocked by default in automated tests.
The user has now reported a successful manual sandbox capture and verified that
the completed checkout/receipt persists after a browser refresh (see verification
record below). This documentation update did not repeat the transaction or
independently query PayPal. Sandbox webhooks are now covered in [webhook setup](paypal-webhooks.md). Refunds remain unimplemented:
this milestone cannot automatically observe refunds, reversals or disputes after
capture. Receipt is a historical sandbox capture record, not a production ledger
or guarantee of final settlement. Authentication, amount adjustments after capture
and production/live payments are intentionally unavailable.

```sh
cd backend
uv run --frozen pytest -q tests/test_paypal_sandbox.py tests/test_cancellation_preview.py tests/test_booking_comparisons.py
uv run --frozen ruff check .
uv run --frozen ruff format --check .
cd ../frontend
npm run build
```

## Read-only diagnosis of an existing approval failure — 2026-10-31

Booking `19907e60-025b-4d47-93cb-18ced6b6c984`, attempt
`07040e51-f9f2-4460-ad1a-ed392b0903ae`, existing sandbox order
`8KW67820DV915823H` were inspected without changing records. One backend-credential
OAuth authentication and one sandbox GET of that order were performed; no order
creation, capture, buyer approval or AI request was made.

Verified results:

- Stored attempt is `awaiting_buyer`, with no capture ID. Sandbox order is
  `PAYER_ACTION_REQUIRED`, `intent=CAPTURE`, one USD 200.00 purchase unit and no
  captures. Full existing server order/payee/amount/reference validation passed.
- Current FastAPI config and Vite-proxied config return the same client ID used
  by backend credentials. Both specify sandbox and the sandbox SDK v6 origin.
  Configured merchant ID matches order payee and stored checkout approval context.
  No secrets/tokens, raw payment response or account login details were printed.
- The actual React code returns `{orderId: attempt.order_id}` with PayPal's ID as
  a string. SDK v6 explicitly requires that envelope; a bare string is the older
  v5 contract. Do not change v6 code to return local `attempt.id` or a bare string.
  See [official v6 order promise contract](https://developer.paypal.com/sdk/js/set-up#return-order-id-to-sdk).
- User confirmed separate Sandbox Personal buyer and Sandbox Business merchant,
  **both India**, with no error/debug ID visible in the failed popup. PayPal's
  [India help article](https://www.paypal.com/in/cshelp/article/can-i-use-paypal-to-receive-payments-from-indian-customers-help1049)
  states that Indian merchants cannot receive domestic Indian payments. This
  makes the country pair a likely approval blocker. That service restriction is
  documented; its application to this particular generic sandbox popup remains
  an inference, not a verified provider error code.

No confirmed application defect was found, so application behavior, eligibility
and capture guards were not changed. The current configuration was checked; the
historical failing SDK instance itself was not instrumented. Exact provider-side
cause cannot be proved from a successful Orders GET and generic popup text alone.
A later approved test with a non-India Sandbox Personal buyer, or PayPal support
correlation for the existing order, is needed to isolate the country restriction.
Do not complete buyer approval in the current application until capture is
explicitly authorized: its normal onApprove callback requests backend capture.
Do not create another order to test this diagnosis.

Focused regressions now cover read-only existing-order retrieval/authentication,
config app-ID equality, `PAYER_ACTION_REQUIRED` capture blocking, and the actual
React-to-SDK order promise with distinct synthetic local/PayPal IDs. Browser test
mocks every application request and SDK operation, blocks PayPal hosts, and never
invokes onApprove or captures. With Vite on port 5173 and an isolated headless
Chrome debugging page on port 9225, run:

```sh
node frontend/tests/paypal-approval.browser.mjs
```

Optional `CDP_URL` and `FRONTEND_URL` override those local endpoints. No additional
frontend dependency or live PayPal session is needed. Four focused backend tests,
seven browser assertions, lint/format and frontend TypeScript/Vite build passed.

## Successful manual capture and refresh persistence — 2026-10-31

**User-reported manual verification:** sandbox buyer approval and backend capture
completed successfully, and the completed checkout/receipt remained available
after refreshing the frontend. This records the subsequent successful manual
flow; the earlier approval-failure diagnosis remains historical and does not
establish the cause of that earlier generic popup error.

No new order/capture/receipt identifiers or buyer-country details were supplied
with this report, so none are inferred or attributed to the previously inspected
order. No new order, capture, reconciliation, payment API request or AI call was
made for this documentation update. Existing payment attempts, approvals,
receipts and agreement/proposal records were preserved.

**Still unimplemented:** refund operations and automatic post-capture
refund/reversal/dispute reconciliation. Successful sandbox capture and refresh
persistence do not verify those deferred capabilities or production/live payments.


## Sandbox webhooks — 2026-11-02

Verified webhook intake and order reconciliation now implemented. See
[webhook setup, plugin guidance and limitations](paypal-webhooks.md).
No real webhook registration, provider request or sandbox webhook test performed.
