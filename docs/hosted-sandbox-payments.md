# Controlled hosted PayPal sandbox checkout

Implemented 2026-11-07; **disabled by default**. This supersedes the earlier
unconditional public payment ban only when an operator explicitly enables the
sandbox opt-in. Live payments and hosted webhooks remain disabled; Buyer/Merchant
roles remain simulated views. The implementation checkpoint used mocked providers;
the later user-reported hosted capture is recorded separately below.

## User-verified hosted sandbox capture — 7 November 2026

**Manual verification reported by the user; not an automated test or a fresh
independent database/PayPal audit during this documentation update.**

- Booking **Camera kit- test 1** completed a **USD 200 PayPal sandbox capture**.
- Its app-issued sandbox receipt persisted after browser refresh.
- The receipt links **buyer agreement v2**, **merchant proposal v2**, the saved
  comparison, separate checkout approval and **both approved cancellation rules**.
  These are the reported saved approval references, not reconstructed current terms.
- This is a hosted sandbox transaction with test funds, separate from historical
  local receipts and mocked test receipts. No real-money payment is supported.
- Refresh persistence does not establish hosted webhook delivery, duplicate-capture
  replay, browser-interruption recovery or current settlement. Hosted webhooks stay
  disabled. No order/capture/receipt identifiers or exact capture time were supplied
  for this report; none are invented here.

The [earlier hosted walkthrough](demo.md#user-reported-hosted-walkthrough--2026-11-07)
included two AI refund-allocation errors, manual buyer/merchant rule corrections
and separate human approvals. Those errors remain part of the evidence; a successful
capture does not establish correct AI proposals or prove the later offline-tested
prompt update's live effectiveness. Intermittent `public_setup_required` errors
cleared on refresh, but their hosted causes remain unresolved. Sanitised diagnostic
logging is available; no captured failure has established the cause.

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
5 per session**, all-time rather than daily; configurable maximums are 100 and 5.
Existing Production overrides retain their configured values; explicitly update
`DEMO_PAYMENT_ATTEMPTS_PER_SESSION=5` and redeploy the updated backend to use five.
Older backend revisions reject values above three. Existing consumed reservations
continue to count; no reset or migration is needed. Global/write/AI limits are
unchanged; see [session allowances and rollout](public-demo-controls.md#session-allowances-and-deployment-overrides).
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

## Owner grants applied — 7 November 2026

No migration is needed: the existing ledger already supports the write action.
The documented minimum payment grants were separately authorised and applied to
`beforepay_demo_runtime` on the exact project/branch/database below.
Vercel readiness refuses sandbox opt-in until the minimum payment grants exist
and still refuses owner/admin/schema-create privileges. Do not enable the opt-in
first and then weaken readiness to make it pass.

For a separately authorised repeat/setup, use the verified owner connection to project
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
All existing triggers remain enabled. Real runtime-authenticated SQL verification
exercised allowed inserts/operational updates and 12 forbidden-operation checks in
an explicitly rolled-back transaction. Zero probe records persisted; all 25 table
counts/fingerprints and all 20 trigger definitions/states remained unchanged.
Ownership stays with `neondb_owner`, revision stays `0015_demo_templates`, and runtime
has no admin memberships. This grant verification is distinct from the user's
subsequent hosted payment observation. See [permission inventory](neon-runtime-permissions.md).

## Explicit backend Vercel sandbox configuration

Keep the existing private runtime database URL, exact HTTPS frontend origin,
Secure session cookies, quotas and AI settings. The user subsequently reported
successful explicitly enabled hosted sandbox checkout; this documentation update
does not inspect or change dashboard values. The required enablement pattern is
shown below, with code-default attempt caps rather than an audit of current limits.
Set only in the backend project's
environment store, never frontend `VITE_*` variables:

```dotenv
PUBLIC_DEMO_MODE=true
PUBLIC_SANDBOX_PAYMENTS_ENABLED=true
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_SANDBOX_ENABLED=true
DEMO_PAYMENT_ATTEMPTS_GLOBAL=20
DEMO_PAYMENT_ATTEMPTS_PER_SESSION=5
PUBLIC_WEBHOOKS_ENABLED=false
```

Privately configure `PAYPAL_SANDBOX_CLIENT_ID`, `PAYPAL_SANDBOX_CLIENT_SECRET` and
`PAYPAL_SANDBOX_MERCHANT_ID` from the **same Sandbox REST app/business account**.
Leave `PAYPAL_SANDBOX_WEBHOOK_ID` absent while hosted webhooks are disabled.
`backend/vercel.json` no longer forces the sandbox enable flag to false; Python
defaults still deny payment and need both explicit flags. No model/key changes
are needed. Enabling this on another deployment requires a separate operator action;
the default remains off.

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
reconciliation after return. The reported hosted capture above does not demonstrate
live interruption recovery.

## Offline evidence

Focused tests use mocked PayPal/Gemini and disposable local PostgreSQL, covering
default-off denial, complete sandbox opt-in, live-environment rejection, client-ID
exposure without secrets, atomic global limits/session cycling, independent
per-session limits, durable failure charges, stable retries, foreign ownership,
approval/version/amount guards, duplicate captures, immutable receipts and signed
webhook regressions. An expanded test applies the exact optional grants to a
restricted disposable role and completes mocked checkout through the public HTTP
flow; readiness rejects the missing grants beforehand. That implementation/test
checkpoint performed no hosted grant, migration, credential retrieval, provider call
or deployment. The later owner grants and manual hosted capture are separate evidence.

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
