# Controlled hosted PayPal sandbox checkout

Implemented 2026-11-07; **disabled by default**. This supersedes the earlier
unconditional public payment ban only when an operator explicitly enables the
sandbox opt-in. Nothing here enables live payments, authenticates Buyer/Merchant
roles, changes hosted records/configuration or demonstrates a hosted capture.

## Boundary and durable limits

`PUBLIC_SANDBOX_PAYMENTS_ENABLED=false` denies SDK configuration, order creation,
capture and browser reconciliation in public mode. To opt in, settings require
the existing sandbox enable flag and complete sandbox credentials. Environment is
still the literal `sandbox`; `live` fails server validation. Backend HTTPX URLs
remain fixed to `https://api-m.sandbox.paypal.com`, without redirects, proxy
environment, automatic retries or fallback. Browser SDK remains fixed to
`https://www.sandbox.paypal.com/web-sdk/v6/core`. No new SDK integration was added.
Credential strings cannot be proven sandbox credentials offline: operators must
select the Sandbox app; live credentials cannot select a live endpoint here.

Only the sandbox client ID is exposed to the SDK through the session-owned config
endpoint. The secret, OAuth token and merchant configuration remain backend-only.
Anonymous session ownership, Origin/CSRF, exact current agreement confirmation,
proposal/comparison/rule eligibility and separate checkout approval are unchanged.
The opt-in alone grants no checkout eligibility.

Each **new local attempt** reserves one durable `demo_admissions` row with kind
`write` and action `sandbox_payment_attempt`, using the existing global advisory
lock and independently committed ledger. Defaults: **20 attempts globally,
1 per session**, all-time rather than daily; configurable maximums are 100 and 3.
Zero closes new-attempt admission. It also consumes normal write allowance.
Cancelling, failing, expiring, signing out or changing sessions does not refund
the shared charge. Reusing the same saved attempt/approval does not consume a new
attempt slot. These are attempt limits, not a promise to cap each provider HTTP
request; existing write limits and the short explicit retry window still apply.

A crash between reservation and attempt persistence can consume a slot without
creating an attempt. It fails closed; no automatic refund/reset/retry is added.
Independent processes/sessions contend for the same committed global allowance.
The existing booking lock, unique approval binding and stable create/capture keys
prevent competing local attempts from authorising duplicate capture. Every
capture checks provider state and current exact approval; only authenticated final
COMPLETED capture data matching amount/currency, merchant, order and attempt can
create the immutable receipt. Buyer approval/callback alone cannot establish paid.

## Pending owner grants — not applied

No migration is needed: the existing ledger already supports the write action.
The current hosted runtime role intentionally lacks payment write permissions.
Vercel readiness now refuses sandbox opt-in until the minimum payment grants exist
and still refuses owner/admin/schema-create privileges. Do not enable the opt-in
first and then weaken readiness to make it pass.

After separate authorisation, use the verified direct owner connection to project
`super-hat-76778640`, branch `br-shy-dawn-b3vw2kgo`, database
`beforepay_demo_2026`. Privately set a native PostgreSQL owner URL in the operator's
shell (not an environment file committed to Git), verify the target, then run:

```sh
cd backend
psql "$BEFOREPAY_OWNER_DIRECT_URL" -X -v ON_ERROR_STOP=1 \
  -f scripts/grant_demo_sandbox_payments.sql
```

The script verifies database name and `neondb_owner`, then grants only INSERT on
`payment_attempts`, `payment_events`, `sandbox_receipts` and UPDATE on attempt
`order_id`, `capture_id`, `status`, `error_code`, `capture_requested_at`, `updated_at`.
Existing read grants are reused. No receipt/event UPDATE, DELETE, TRUNCATE,
immutable binding updates, schema ownership, function or webhook grants are added.
All existing triggers remain enabled. This script was exercised only against a
disposable role/database during testing; it has not been applied to Neon.

## Proposed backend Vercel configuration — not applied

Keep the existing private runtime database URL, exact HTTPS frontend origin,
Secure session cookies, quotas and AI settings. Set only in the backend project's
environment store, never frontend `VITE_*` variables:

```dotenv
PUBLIC_DEMO_MODE=true
PUBLIC_SANDBOX_PAYMENTS_ENABLED=true
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_SANDBOX_ENABLED=true
DEMO_PAYMENT_ATTEMPTS_GLOBAL=20
DEMO_PAYMENT_ATTEMPTS_PER_SESSION=1
PUBLIC_WEBHOOKS_ENABLED=false
```

Privately configure `PAYPAL_SANDBOX_CLIENT_ID`, `PAYPAL_SANDBOX_CLIENT_SECRET` and
`PAYPAL_SANDBOX_MERCHANT_ID` from the **same Sandbox REST app/business account**.
Leave `PAYPAL_SANDBOX_WEBHOOK_ID` absent while hosted webhooks are disabled.
`backend/vercel.json` no longer forces the sandbox enable flag to false; Python
defaults still deny payment and need both explicit flags. No model/key changes
are needed. A deployment loading these settings is a later operator action.

For rollback, remove sandbox credentials and set both enable flags false together
in the next configuration revision. Retain all attempts/receipts/charges. An
in-flight synchronous provider action is not retroactively cancelled by a flag
change; inspect/reconcile uncertain outcomes through separately authorised steps.

## Sandbox buyer walkthrough

1. In PayPal Developer Dashboard, select **Sandbox** and the merchant's REST app.
   Use its business account as seller, and a separate **Personal sandbox account**
   as buyer. Obtain or set that test buyer's login privately in Sandbox Accounts;
   never use a real PayPal account/card or put buyer passwords into BeforePay.
   See [PayPal sandbox accounts](https://developer.paypal.com/sandbox-testing/accounts)
   and [REST setup](https://developer.paypal.com/api/get-started/).
2. In one BeforePay demo session, create synthetic terms, review/confirm the
   agreement, save a matching proposal/comparison, separately review/approve both
   rule versions and explicitly approve the exact checkout bundle. Changing
   Buyer/Merchant views retains the same owning session; it grants no extra access.
3. Explicitly load sandbox checkout and approve through the PayPal sandbox popup
   using the personal test buyer. BeforePay must verify capture before showing an
   app-issued **sandbox payment receipt** with the saved approval references.
4. If the result is uncertain, preserve the attempt. Explicit **Check PayPal
   status** performs guarded reconciliation; never start another booking/approval
   to bypass uncertainty or the attempt cap. Existing retries retain their keys.
5. A second new attempt in the same session is denied by the default cap even
   after cancellation/failure. Existing records remain readable only by their owner.

Hosted webhooks remain blocked by the existing Vercel exposure guard; do not
register or enable one for this increment. Signed verification/deduplication and
historical reconciliation remain unchanged for existing authorised local webhook
use. Without hosted delivery, browser-interruption recovery may require explicit
reconciliation after return; no live recovery or hosted payment is claimed here.

## Offline evidence

Focused tests use mocked PayPal/Gemini and disposable local PostgreSQL, covering
default-off denial, complete sandbox opt-in, live-environment rejection, client-ID
exposure without secrets, atomic global limits/session cycling, independent
per-session limits, durable failure charges, stable retries, foreign ownership,
approval/version/amount guards, duplicate captures, immutable receipts and signed
webhook regressions. An expanded test applies the exact optional grants to a
restricted disposable role and completes mocked checkout through the public HTTP
flow; readiness rejects the missing grants beforehand. No hosted grant, migration,
credential retrieval, provider call or deployment was performed.

Focused verification: **144 distinct backend checks passed**, with six existing
dependency warnings per run. The initial seven-suite run passed 143; the added
failure-charge test and expanded restricted-role test were checked afterward,
including a corrected independent session-limit case. An intermediate expanded
test passed its assertions but exposed a test-only session cleanup leak; the
session scope was fixed, its rerun passed and its leftover disposable database
was removed. No application database was touched.

```sh
cd backend
uv run --frozen --offline pytest -q -x --tb=short \
  tests/test_hosted_sandbox_payments.py tests/test_public_payments.py \
  tests/test_paypal_sandbox.py tests/test_paypal_webhooks.py \
  tests/test_hosting_preparation.py tests/test_hosting_diagnostics.py \
  tests/test_public_admission.py
```

Ruff lint/format and diff whitespace checks passed. The frontend's existing
server-driven `payment_execution_allowed` gate and fixed sandbox SDK are reused;
no frontend API contract or payment interaction was changed.
