# Local audit of sandbox capture 37479790XD8219546 — 2026-11-02

Local PostgreSQL inspection found one completed attempt, one immutable receipt,
and one linked `PAYMENT.CAPTURE.COMPLETED` webhook record. The receipt already
existed before either recorded webhook. This supports successful sandbox webhook
processing and a single receipt remaining after the user-reported resend. It does
not independently prove the resend's delivery/response or live browser-interruption
recovery.

## Scope and method

Executed SELECT queries in a single PostgreSQL `REPEATABLE READ` transaction with
`SET TRANSACTION READ ONLY`; `SHOW transaction_read_only` returned `on`. Inspected
revision, linked receipt/attempt/approval, webhook records, payment events, receipt
uniqueness constraints and immutable triggers. Selected only identifiers, statuses,
timestamps, amounts, context-equality booleans and event digests; no raw payment
payload, credentials, tokens, signatures, customer evidence or approval audit labels
were printed or copied here. The database session made no writes.

Read current webhook handler, sandbox verification adapter and proxy source. Also
inspected process names, loopback listener ports and stdout/stderr destinations,
without reading process arguments, terminal contents or tunnel credentials.
No HTTP endpoint was invoked, including local webhook/reconcile endpoints. No
PayPal/Gemini calls, resend, payment actions, migration or service restart occurred.
Only documentation files were changed. No tests rerun for this documentation audit.

## Persisted evidence

| Record | Observed value |
| --- | --- |
| Database revision | `0008_paypal_webhooks` |
| Booking | `007ceaeb-bdc6-4f25-a60a-e9bb402a57a5` |
| Attempt | `7a7e6a6d-deee-4b94-ac1f-221c58382bf7` |
| Checkout approval | `c4e5b90a-95d0-4cd2-95aa-d4d9b1dfc5c7` |
| PayPal order | `5VP72305UG971820U` |
| PayPal capture | `37479790XD8219546` |
| Receipt | `6b9522d4-9c81-4572-b17d-0cb6eb60e98b` |
| Amount/currency | USD 200.00 |
| Attempt status/error | `completed` / null |
| Receipt count for booking | 1 |
| Receipt count for capture within that booking | 1 |
| Receipt context equals original checkout approval context | true |
| Receipt approval equals attempt approval | true |

UTC timeline (database timestamps; not independently fetched provider timestamps):

| Time on 2026-11-02 (UTC) | Event |
| --- | --- |
| 09:45:46.016010 | Exact checkout approval created |
| 09:47:14.978526 | Payment attempt created |
| 09:47:45.842227 | Persisted capture-intent timestamp |
| 09:47:45.858633 | Receipt created; attempt completed and last updated |
| 09:47:49.019723 | `CHECKOUT.ORDER.APPROVED` webhook record created |
| 09:48:09.650249 | `PAYMENT.CAPTURE.COMPLETED` webhook record created |

PostgreSQL `now()` defaults represent transaction start time; these timestamps
are not exact response/commit times. Ordering nevertheless shows the receipt's
recorded creation precedes both webhook records. The payment-event history
contains one `completed` entry at the receipt timestamp, with the preceding
create/awaiting-buyer/capture-prepared/uncertain states. No later completion entry
or attempt update was present in this snapshot.

Capture-completed webhook record:

- Event ID: `WH-0F807248FV9398823-38H5651562937130P`.
- Type: `PAYMENT.CAPTURE.COMPLETED`.
- Linked attempt: `7a7e6a6d-deee-4b94-ac1f-221c58382bf7`.
- Canonical event SHA-256:
  `dca5ebe5b9c0abe30abe95cf4c79db38f39c5d700f77385cf165829ee7b29f77`.
- Exactly one row with this event ID was observed through the linked-attempt query.

The same attempt also has approval event
`WH-02X433843C792162F-2N092618J2564941D`. Approval alone is not payment proof.
The event table stores the attempt binding and digest, not a separate capture ID
or raw event resource; capture association here is through that persisted attempt.
The digest cannot be recomputed without the original event, which was not read.

## Verification and resend: what can be concluded

Current `receive_webhook` calls `verify_webhook` before claiming an event.
The adapter calls the fixed sandbox verification endpoint and accepts only
`verification_status == SUCCESS`. Therefore, under the inspected application
write path, the persisted event is evidence of successful signature verification
and event processing. This is a source-and-record inference, not a fresh provider
verification. The original verification response and transmission headers are
intentionally not retained, so they cannot be independently rechecked locally.

The receipt had already been recorded when the webhook arrived. For an already
completed attempt, this handler claims the verified event and leaves the receipt
and attempt unchanged; it does not perform another order GET in that branch.
Consequently, this live example does not establish that the webhook created the
receipt or recovered an otherwise missing payment result.

For an identical verified resend, the event primary key rejects a second claim;
matching digest/attempt returns `{"status":"duplicate"}` with HTTP 200. Current
receipt constraints enforce unique booking, attempt, order and capture. Database
inspection confirmed those constraints and enabled immutable triggers on receipts
and webhook records. At inspection time there was still exactly one receipt for
this capture and booking, consistent with safe handling of the user-reported
resend. No second receipt exists in this snapshot.

**Resend evidence limit:** duplicate deliveries deliberately create no additional
webhook row or delivery counter. The database therefore cannot distinguish one
delivery from an original plus any number of identical resends. No durable safe
log tying a second request to this event ID and a 200/duplicate response was found.
The user's reported resend is not independently established by this local audit.
Generic access-log 200s, even if supplied later, would not alone establish the
response body was `duplicate` rather than `processed` or `ignored`.

## Available safe logs

Backend listeners were on `127.0.0.1:8000`; the restricted proxy listener was on
`127.0.0.1:8082`, and an ngrok process was present. This indicates local processes,
not successful external reachability or delivery by itself.

Backend stdout/stderr pointed to `/dev/ttys001`, proxy output to `/dev/ttys005`,
and ngrok output to `/dev/ttys006`. These were terminal devices rather than regular
log files; terminal contents were not read. No relevant durable webhook/access
log was located in the inspected project paths or top two levels of `/private/tmp`.
The older intake/browser and npm logs discovered were unrelated and not used.
No ngrok inspection API, config file, payload store or cloud dashboard was queried.
Thus no safe per-delivery evidence for the resend was available through these
sources. This does not claim no such evidence exists elsewhere.

## APIMatic's actual contribution

Installed APIMatic PayPal Context Plugin 0.4.1 supplied Python workflow,
getting-started, error-handling and testing instructions used during implementation:
plan/contract documentation, local duplicate claims, idempotency discipline,
unknown-outcome handling and mocked negative-path/provider-boundary tests.
See [implementation attribution](paypal-webhooks.md#installed-apimatic-paypal-context-plugin-guidance).

The webhook implementation uses BeforePay's existing HTTPX sandbox adapter and
PayPal's REST verification endpoint. No APIMatic SDK or MCP operation performed
verification, delivery, reconciliation or this audit. The documented Python SDK
surface did not provide webhook verification/registration; no such SDK capability
was added or tested. APIMatic contributed implementation guidance, not a running
webhook service, a provider response, or independent proof of this transaction.
This audit read the existing attribution and code; it did not run an APIMatic tool
or reinstall/reprobe its SDK.

## Remaining live demonstration

Successful recorded sandbox notification delivery and a single receipt are
supported locally. Live recovery after browser/process interruption is **not**
demonstrated: the receipt predates the webhook here. Earlier recovery tests used
mocked providers. A future separately authorized controlled sandbox test would
need a capture completed remotely, no locally persisted receipt before delivery,
and that receipt then created through webhook reconciliation. Nothing in this
audit initiates that scenario or authorizes another payment.
