# Sandbox webhook and reconciliation plan

Scope: verified notification intake and read-only reconciliation of existing orders.
No automatic capture on approval, new payment authorization, live provider smoke,
SDK migration, refund/dispute lifecycle, or frontend changes.

## Survey and contracts

- Synchronous FastAPI/SQLAlchemy; pattern: backend/app/payments/router.py.
- Fixed sandbox HTTPX OAuth/Orders adapter: backend/app/payments/provider.py.
- Exact checkout approval, precommitted capture intent, stable keys, booking lock,
  authenticated GET verification, immutable receipts: backend/app/payments/service.py.
- uv / Python 3.14, frozen lockfile; SDK probe returns None. No SDK dependency or
  SDK calls introduced. Plugin SDK-only installation/map/type-check requirements
  do not govern this REST extension. No SDK contract claims made.
- Plugin python-integrate-paypal and python-getting-started inspected: documented
  controllers are orders, payments, subscriptions, transaction_search, vault;
  webhook verification/registration unsupported. Preserve existing HTTPX boundary.
- Official REST contracts: https://developer.paypal.com/api/rest/webhooks/rest/
  and https://developer.paypal.com/api/webhooks/v1/.
- POST /v1/notifications/verify-webhook-signature, fixed sandbox origin, OAuth:
  auth_algo, cert_url, transmission_id, transmission_sig, transmission_time from
  five PayPal headers; webhook_id from backend settings; webhook_event is complete
  unmodified parsed JSON object. Accept only verification_status == SUCCESS.
  Never fetch certificate/resource/link URLs supplied in event.
- Capture notifications resolve supplementary_data.related_ids.order_id; order
  approval notification uses resource.id. Only local known order IDs reconciled.
  Notification data never establishes paid status. Authenticated GET must pass
  existing order/attempt/merchant/amount/currency/final COMPLETED checks.
- Unknown orders/types acknowledged without writes to payment state. Verified
  supported known events claim event ID plus canonical JSON digest. Duplicate
  same body acknowledged; changed body rejected. Failed GET/validation rolls back
  claim and returns 503, allowing redelivery/manual existing reconcile endpoint.
- Historical reconciliation preserves original checkout approval and receipt
  context; no current-eligibility requirement because no new capture occurs.
- Completed attempts terminal for this milestone; no out-of-order downgrade.

## Duplicate claims

| Write | Store | Rejection | Handling | Code |
| --- | --- | --- | --- | --- |
| Verified event processing | PostgreSQL webhook event primary key | ON CONFLICT DO NOTHING | Same digest returns duplicate; changed digest 409 | receive_webhook claim before reconcile GET |
| Capture/create | Existing durable attempts and booking lock | Existing approval/key uniqueness and serialization | Existing services | create_order / capture_order unchanged |
| Receipt | Existing booking/attempt/order/capture unique constraints plus booking lock | Existing receipt returned, other attempt rejected | record_remote guard | record_remote |

Claim and result commit atomically; a crash rolls back notification claim and state.
Provider reads require no persistent remote-write claim. No remote writes added.

## Required reading used

MUST load python-error-handling: unknown/invalid provider output fails closed.
MUST load python-testing: offline transport tests and forbidden real providers.
Loaded before implementation. SDK initialization not used; no new dependency.

## Assumptions and checks

No unresolved contract lookup. No real credentials read; user forbids live smoke.
Existing payment baseline started on untouched tree against isolated PostgreSQL.
Run focused webhook/payment tests, then full backend pytest, ruff check/format.
Migration tested on disposable real PostgreSQL only; leave actual database alone.
No dependency changes, so no install needed. Frontend unchanged.

## Verification record

Untouched payment baseline: 39 tests passed against disposable PostgreSQL.
Focused payment/webhook run: 55 passed, including database migration, concurrent
notification claims and immutable-event trigger; six existing dependency warnings.
One additional historical-approval webhook regression included in full suite.
`uv run --frozen ruff check .` and `ruff format --check .` passed (76 Python files).
Full backend suite outcome recorded in implementation plan after completion.
No external provider calls; developer secret files untouched. Frontend unchanged.
Final full suite: 336 passed, six existing dependency warnings. Existing
starting-flow first-page-only preservation assertion fixed to paginate after
initial full run exposed it. Full lint/format and suite rerun passed. No SDK type
checking applies to this HTTPX-only extension; no frontend build needed.
