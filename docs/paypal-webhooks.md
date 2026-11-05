# Sandbox webhooks and payment reconciliation

Latest local audit: capture `37479790XD8219546` has one receipt and a recorded
verified-path capture notification. Receipt predates webhook; live browser-loss
recovery remains unproven. Resend reported by user; no separate delivery log
located. See [read-only evidence and APIMatic attribution](paypal-webhook-verification-2026-11-02.md).

`POST /api/paypal/sandbox/webhook` receives PayPal notifications independently of
the browser. Only an authenticated sandbox order GET with a final COMPLETED
capture can create a receipt. Browser callbacks and event resource/status fields
cannot establish payment. This recovers a capture completed remotely before a
process failure or browser closure prevented local recording.

Approval notifications only reconcile. Closing the browser before capture was
requested does not initiate capture: the customer must return to the existing
explicit checkout/capture flow. No automatic create/capture retry or worker was
added. Existing manual reconcile endpoint remains available if delivery is lost
or an accepted pending event has no later notification.

## Verification and processing

The adapter posts the complete parsed event and five original PayPal signature
headers to the fixed sandbox `/v1/notifications/verify-webhook-signature` endpoint
using backend OAuth credentials and backend-configured webhook ID. Only literal
`verification_status: SUCCESS` is accepted. Neither certificate URLs nor links in
events are fetched locally. No raw payload, bearer token or signature is logged
or persisted. Existing body-size middleware applies before JSON parsing.

Supported events: `CHECKOUT.ORDER.APPROVED`, `CHECKOUT.ORDER.COMPLETED`,
`PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.PENDING`, `PAYMENT.CAPTURE.DENIED`.
Capture events resolve `resource.supplementary_data.related_ids.order_id`; order
events use `resource.id`. Only previously persisted local order bindings qualify.
Unknown orders/types are verified then acknowledged as ignored. They do not
attach an event-supplied attempt, approval or booking to a payment.

Processing takes the common booking lock, claims the provider event ID with a
PostgreSQL primary key, then retrieves current provider state through the existing
adapter. The claim, state updates and receipt commit in one transaction. A crash
or failed GET/validation rolls back the claim; a 503 invites provider redelivery.
Signature failure returns 400; provider verification outage returns 503. A
successful duplicate returns 200 without another order GET; a reused event ID
with a changed canonical JSON digest or local attempt returns 409. Claims are
immutable, contain no raw payload, and are created only for known supported
notifications. Unknown order deliveries remain unclaimed and can be resent after
an uncertain create outcome has been resolved through the existing flow.

Authenticated order checks retain exact local order, attempt reference/custom/
invoice IDs, merchant, amount, currency and one final COMPLETED capture. Current
checkout eligibility is never used to authorize a new remote write here: this is
read-only historical reconciliation. Receipts retain the original exact approval
and version context even if agreement/proposal/evidence later changes. Existing
receipt uniqueness, immutable database triggers and stable create/capture keys
remain intact. Another attempt's receipt blocks a second receipt.

Concurrent deliveries serialize with captures and agreement changes. Completed
attempts do not regress when delayed pending/denied/approved notifications arrive;
current GET state, rather than event chronology, determines unpaid status. An
older pending notification can discover a now-completed capture. A duplicate
previously accepted pending notification does not poll again; use a later distinct
event or manual reconcile.

Refunds, reversals, disputes and settlement accounting remain unsupported and
cannot rewrite a historical receipt. They are verified then ignored as unsupported
event types. This feature does not claim current funds are still settled after
capture, and creates no refund or dispute actions.

## Installed APIMatic PayPal Context Plugin guidance

Read installed `paypal:python-integrate-paypal`, `paypal:python-getting-started`,
`paypal:python-error-handling` and `paypal:python-testing` skills from plugin
version 0.4.1. Used its plan-first survey/contract sheet (`paypal-plan.md`), durable
local duplicate claims, claim-before-provider ordering, unknown-result handling,
missing-field checks, no raw provider logging, mocked transport verification and
negative-path guidance. Host is synchronous FastAPI with synchronous SQLAlchemy.

Plugin's documented Python SDK surface has orders, payments, subscriptions,
transaction search and vault controllers; no webhook verification/registration
controller. Environment probe confirmed `paypal` SDK is absent; no PayPal MCP
operation is exposed in this session. This feature therefore preserves BeforePay's
existing fixed-sandbox HTTPX adapter. No SDK install, dependency change, model or
error-union claim, SDK map lookup, SDK-specific type checking, or SDK migration was
needed. SDK initialization/transport instructions do not describe this HTTPX
adapter. SDK's default retry behavior is not used; HTTPX requests remain one
attempt with no redirects, proxy environment or automatic retry. Live credential
smoke from plugin workflow was omitted because user explicitly forbids provider
calls and secret-file reads.

REST wire contracts came from official
[PayPal postback verification guide](https://developer.paypal.com/api/rest/webhooks/rest/)
and [Webhooks Management API](https://developer.paypal.com/api/webhooks/v1/).
Plugin is guidance, not a webhook verification service or tested provider integration.

## Remaining real sandbox setup

1. Apply migration: `cd backend && uv run --frozen alembic upgrade head`.
   Automated checks apply it only to a fresh disposable PostgreSQL database;
   actual development database is not changed during implementation.
2. Keep backend sandbox enabled and existing sandbox app credentials/merchant ID
   configured. Add `PAYPAL_SANDBOX_WEBHOOK_ID` to backend environment only; obtain
   it when registering the webhook on that same Sandbox REST app. Restart backend.
   `.env.example` contains a placeholder; actual `.env` was not read or edited.
3. Expose **only this webhook path** through a trusted HTTPS endpoint on port 443
   forwarding to the local backend. Preserve request JSON and all five signature
   headers. Do not expose other unauthenticated prototype routes to the internet.
4. In PayPal Developer Dashboard, choose that Sandbox app and register
   `https://YOUR-HOST/api/paypal/sandbox/webhook` for the five events above. Do not
   use a live app or pass client/webhook IDs in event bodies as configuration.
5. With explicit authorization for external sandbox calls, perform a fresh sandbox
   checkout using separate sandbox merchant/buyer accounts. Interrupt browser
   after capture request; allow webhook delivery, then confirm the linked receipt
   and exact original approval context through the local API/UI. Never infer paid
   status from buyer approval, simulator success or an event body's status alone.
6. Resend an actual capture event from the dashboard; verify one receipt, unchanged
   capture/key binding and 200 duplicate response. Check a late pending/approval
   event does not downgrade it. For a delivery/GET outage, restore service and
   resend the same real event or use the explicit reconcile endpoint.

PayPal's guide states postback verification does **not** support simulator mock
events. Use actual app-generated sandbox events for the real test. Never disable
verification or substitute a simulator webhook ID to make a test pass.

No registration, tunnel, SDK download, external PayPal/Gemini call or real sandbox
webhook test was performed. Authentication and live payments remain outside scope.

## Verification performed

- Untouched payment baseline: 39 passed.
- Focused payment/webhook checks: 55 passed; historical-approval webhook regression
  subsequently included in full suite.
- `cd backend && uv run --frozen pytest -q`: **336 passed**, six existing dependency
  warnings. Real disposable PostgreSQL applies migration 0008 and verifies
  concurrent event deduplication and append-only trigger enforcement. Provider
  responses are mocked; wire-contract verification uses HTTPX MockTransport.
- `uv run --frozen ruff check .` and `uv run --frozen ruff format --check .` passed
  (76 Python files). No dependencies/lockfiles or frontend files changed.
- First full run found an existing starting-flow test checking preservation only
  within the first 100 bookings; updated that assertion to paginate. Full rerun
  passed without changing booking behavior.

## Prepared local HTTPS tunnel gate — 2026-11-02

Tool survey: ngrok 3.33.1 at `/usr/local/bin/ngrok`, Homebrew at
`/usr/local/bin/brew`; cloudflared, Caddy and nginx not found on PATH. No tunnel
configuration, credentials or account state were inspected. No installation or
public tunnel was started.

`backend/scripts/webhook_proxy.py` is a separate development proxy. It imports no
backend settings, database or payment adapter. Its upstream is fixed to
`http://127.0.0.1:8000/api/paypal/sandbox/webhook`. Only exact raw-path POST without
a query string can reach that upstream. All other paths/methods return 404,
including documentation, bookings, encoded path aliases and trailing slashes.
Oversize bodies return 413 before forwarding. Tunnel the proxy port **8082**,
never backend port **8000** or frontend port **5173**.

The proxy forwards body bytes without JSON parsing or serialization and retains
all `PayPal-*` header values plus content-type/content-encoding. Host/framing are
regenerated for the fixed upstream; cookies, Authorization, forwarding headers
and other unrelated headers are discarded. Backend response status is preserved,
including retryable failures; connection failure returns 502. No redirects,
proxy-environment routing, automatic retries or request/body logging are enabled.
Backend signature verification remains mandatory and unchanged.

The following commands are prepared for a later authorized test. Run each server
in its own terminal. They were **not** used to start a public endpoint here.

Terminal 1, backend (skip if already running on 127.0.0.1:8000):

```sh
cd '/Users/kishan/Documents/Projects/Context Key/backend'
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, restricted local proxy:

```sh
cd '/Users/kishan/Documents/Projects/Context Key/backend'
uv run --frozen uvicorn scripts.webhook_proxy:app --host 127.0.0.1 --port 8082 --no-access-log --no-proxy-headers
```

Terminal 3, **only when ready to start public HTTPS**:

```sh
ngrok http http://127.0.0.1:8082 --inspect=false
```

No ngrok installation is needed on this machine. A free ngrok account and locally
configured agent authtoken are needed if not already set up; follow the official
[ngrok getting-started instructions](https://ngrok.com/docs/getting-started/).
Keep the token outside this repository and chat. Account/token readiness was not
checked. `--inspect=false` disables agent HTTP inspection; do not enable payload
inspection or header/body transformation policies for this test. Existing user
ngrok/cloud account policies were not inspected or modified, so public end-to-end
preservation must still be checked when authorized.

Use the printed **HTTPS** URL plus `/api/paypal/sandbox/webhook` when later
registering the Sandbox app webhook. Free plan includes an assigned development
domain, with usage limits: [ngrok free-plan documentation](https://ngrok.com/docs/pricing-limits/free-plan-limits/).
No paid plan, custom domain, traffic policy or certificate installation is needed
for this setup. Public HTTPS terminates at the tunnel service; both local hops
remain loopback HTTP. No local TLS certificate or privileged port is required.

Optional accountless free alternative, if ngrok account setup is unwanted:

```sh
brew install cloudflared
cloudflared tunnel --url http://127.0.0.1:8082
```

These optional commands were not executed. Cloudflare Quick Tunnels issue a
random HTTPS URL, require cloudflared installation, and are development-only with
availability/concurrency limits. An existing default `.cloudflared/config.yaml`
can prevent Quick Tunnel startup; do not delete existing user configuration.
See [Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
and [macOS installation](https://developers.cloudflare.com/tunnel/downloads/).
Start only one tunnel option. Stop its terminal with Ctrl-C first, then stop the
proxy when finished; stopping the proxy closes access even if the tunnel remains.

Safe local deny-route smoke, after starting the proxy (no forwarding/provider call):

```sh
curl -i http://127.0.0.1:8082/api/bookings
curl -i -X POST http://127.0.0.1:8082/docs
curl -i http://127.0.0.1:8082/api/paypal/sandbox/webhook
```

Each must return 404. Do not POST to the allowed webhook route against the real
backend until external verification calls are authorized.

Offline verification: `cd backend && uv run --frozen pytest tests/test_webhook_proxy.py -q`
passed **18 tests** with HTTPX MockTransport and in-process TestClient. Verified
exact body/signature preservation, blocked paths/methods, size limit, unchanged
upstream 503 and single-attempt connection failure. Changed-file Ruff lint and
format checks passed. No actual backend/database requests, PayPal/Gemini calls,
webhook registrations or tunnels were involved. No dependency/lockfile changes.

Migration setup status: the later explicitly authorized local development upgrade
succeeded and `uv run --frozen alembic current` reported
`0008_paypal_webhooks (head)`. Earlier disposable-only statements above describe
implementation-time checks, before that separate development migration.
