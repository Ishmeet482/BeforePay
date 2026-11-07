# BeforePay: 3 minute 45 second demo checklist

**Current hosted evidence:** the user subsequently reported extraction, deposit-change
detection, clarification/reply, correction review, a matching comparison, manually
corrected and separately approved buyer/merchant rules, cutoff previews and exact
checkout approval. See the [2026-11-07 hosted walkthrough](demo.md#user-reported-hosted-walkthrough--2026-11-07)
for the two AI refund-allocation errors and intermittent refresh-cleared
`public_setup_required` errors; their causes remain unresolved. Subsequently, on
**7 November 2026**, the user verified **Camera kit- test 1** completed a **USD 200
sandbox capture** with receipt persistence after refresh. It links agreement **v2**,
merchant proposal **v2**, saved comparison, checkout approval and both approved
cancellation rules. Hosted sandbox execution defaults off and was explicitly
enabled for this walkthrough; live payments and hosted webhooks remain disabled.
See [hosted receipt evidence and Personal sandbox buyer setup](hosted-sandbox-payments.md).
These are manual observations, not new test results. The local
record inventory and scene plan below remain historical and must not be presented
as the hosted session's bookings or receipt.

**Current hosted receipt scene:** in the original owning session, open
**Camera kit- test 1 → Checkout & receipt** and show the saved USD 200 capture and
exact approval links. Avoid PayPal/create/capture actions during a saved-history
replay. Judges in a different isolated session cannot open this booking; use a
labelled recording if owner-session access is unavailable, not a fabricated receipt.
A fresh payment requires separately configured sandbox checkout and a distinct
Personal sandbox buyer login entered only in PayPal's sandbox popup. No credentials
belong in a presentation, README or source intake. This receipt scene does not
demonstrate webhook delivery or browser-interruption recovery.

**Session-isolation update:** this is a historical local-record inventory from
before [Phase 1](demo-sessions.md). At that local checkpoint migration 0013 was
unapplied; this does not describe the migrated hosted database. Once applied,
existing bookings remain unowned and cannot be opened by new public/demo sessions.
Do not assign them to a judge session or publish the development database. A new
isolated synthetic presentation setup is still required; this outline is not a
working browser recipe for the new session boundary.

**Recommended: saved-history walkthrough, ending with an existing sandbox receipt.**
No fresh AI or payment needed. At that checkpoint code/docs and local records were inspected
using a PostgreSQL `REPEATABLE READ` transaction with `SET TRANSACTION READ ONLY`
(`read_only=on`, revision `0012_policy_consistency`). Only docs were written; no
tests, previews, provider actions, migrations or service startup occurred. Screens
were mapped from components, not rehearsed in a browser during this preparation.

## Bookings to stage

| Existing booking | Use | Actual saved state |
| --- | --- | --- |
| **Fresh Demo- Camera Rental** | Agreement, deposit difference, clarification/reply, correction history | Confirmed agreement v3; proposal v1 makes USD 80 deposit non-refundable while total stays USD 200. Saved comparison 1 has Gemini metadata/prompt v1 and deposit `differs`. Proposal v2 restores refundability; comparison 2 matches deterministically. One question, reply and correction review exist. Latest proposal is now **v4**, making both comparisons and the v2 review historical. No merchant rule versions or receipt. |
| **Weekend camera rental** | Cancellation preview and receipt | Agreement v2; latest agreement rules v3 and proposal v3 rules have stored approvals. Pickup **15 Nov 2026, 09:00 UTC**; USD 120 rental + USD 80 deposit = USD 200. Existing completed sandbox receipt binds agreement v2/proposal v3. |
| **SYNTHETIC webhook sandbox test 2026-11-02 9dae8088** | Backup receipt | Previously processed actual sandbox capture `37479790XD8219546`, USD 200. Synthetic rental scenario; actual earlier sandbox payment, not a browser fixture. |

Omit **Synthetic Gemini compact transport verification**: evidence-only, without
saved agreement/proposal/receipt. Stored approvals are not proof every current
readiness check passes; this inspection did not recalculate all application guards.

## Timed story — read existing records

| Time | Screen / booking | Demonstration cue |
| --- | --- | --- |
| 0:00–0:25 | Buyer → **Agreement**, Fresh Demo | Agreement v3: refundable USD 80 deposit, inclusive USD 200 total. Open adjacent evidence. Explain separate exact-version confirmation; leave editors closed. |
| 0:25–0:50 | Merchant → **Final proposal**, Fresh Demo | Select **Saved merchant version → Version 1 · historical**. Show non-refundable deposit beside unchanged total. Merchant proposal does not overwrite buyer terms. Do not save. |
| 0:50–1:15 | Buyer → **Compare booking**, Fresh Demo | Select **Saved comparison 1**: amounts match; deposit differs. Show both terms/support. Call this a **saved AI-assisted finding**, not new inference or a guarantee. Keep historical/stale label visible. |
| 1:15–1:50 | Merchant → **Clarification replies**, Fresh Demo | Expand historical question, supporting terms and saved reply. Question asks whether USD 80 deposit is refundable. Point to **Merchant response—not verified resolution**; replying did not approve or unblock checkout. |
| 1:50–2:20 | Buyer → **Compare booking → Clarifications & correction history**, Fresh Demo | Expand recorded review and its context: original discrepancy, reply, corrected proposal v2, matching comparison 2. Say **Correction reviewed for these versions—not checkout approval**. Explain later v4 makes this historical; do not record another review. |
| 2:20–3:05 | Buyer → **Cancellation**, Weekend | Announce booking switch. Select buyer agreement v2 and show approved rule history. Stage **13 Nov 2026 09:00 UTC**, then **09:01 UTC**. Stored rules support USD 200 refund at cutoff; one minute later USD 80 refund / USD 120 retained. Python calculates; preview does not cancel or refund. Not recomputed during preparation. |
| 3:05–3:35 | Buyer → **Checkout & receipt**, Weekend | Say this separate booking **already completed sandbox checkout**. Show captured USD 200, recorded date, receipt reference, exact versions, copy controls and Print. Payment history remains outside receipt; audit details collapsed. |
| 3:35–3:45 | Closing | Same total can conceal different obligations. Review exact terms; unresolved differences block checkout. Receipt is an app-issued historical sandbox capture record, with test funds only. |

## Preparation needed

- [ ] Use existing database/configuration. If services are stopped, start backend
  with `cd backend && uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`;
  frontend: `nvm use`, then `cd frontend && npm run dev` (Node 20.20.2). No install,
  migration, reseed or credential change needed.
- [ ] Pre-open Buyer and Merchant Fresh Demo tabs plus a Buyer Weekend tab. Use
  displayed demo credentials: `buyer.demo / BuyerDemo123!` and
  `merchant.demo / MerchantDemo123!`. Keep **prototype views—not authenticated
  accounts** visible; separate tabs avoid repeated role-switch login during the story.
- [ ] Select historical versions and expand saved histories beforehand. Start with
  no dirty fields; respect discard warnings. Avoid all Save/Confirm/generate/compare,
  checkout-approval and PayPal/reconciliation actions. Read history instead of
  recreating it. No public tunnel or sandbox buyer login is needed for saved receipts.
- [ ] Check calculator readiness before presenting. Use explicit UTC and the exact
  instants above. If blocked, show saved rules or the documented prior manual preview;
  do not invent a result. An interactive preview during the eventual demo is a local
  read-only calculation; a fully passive presentation can use existing captures.

## Genuine blockers and evidence boundaries

- **Fresh Demo is not current-checkout-ready:** v4 has no fresh matching comparison
  or merchant rules. Its clean consistency finding does not replace comparison or
  rule approvals. A fresh same-booking end-to-end demonstration would need separately
  authorised comparison and merchant-rule preparation/approval, then separate
  checkout/payment actions. None was performed or is needed for this history replay.
- **AI provenance:** saved difference records `gemini-3.5-flash-lite`,
  `rental-policy-comparison-v1`, `gemini_policy`. Corrected comparison 2 is deterministic,
  not another AI call. Prompt v2 has only mocked verification; do not claim proven
  improved uncertainty handling. Stale suggestions/reviews remain historical.
- **Saved sandbox versus mocks:** Weekend receipt
  `653c8b1d-665b-453c-8dd6-cfa7e1f2886a`, capture `9SS72790DX919711W`, records USD 200
  on **31 Oct 2026, 18:22:30 UTC**. Supported by current stored records and the prior
  [user-reported manual capture](paypal-sandbox.md#successful-manual-capture-and-refresh-persistence--2026-10-31),
  not a fresh PayPal verification. Backup receipt has a separate
  [local webhook audit](paypal-webhook-verification-2026-11-02.md). QA examples
  **Cinema kit · November shoot**, `ORDER_FIXTURE` and `CAPTURE_FIXTURE` are mocked;
  label them prominently if used, never present them as actual sandbox transactions.
- BeforePay issues the receipt; PayPal does not issue this document. No real funds,
  current-settlement guarantee, refund execution or authenticated roles. Do not claim
  live browser-interruption recovery: the prior webhook audit did not demonstrate it.

<details>
<summary>Presenter routes</summary>

- Fresh Buyer: `http://127.0.0.1:5173/#bookings/fbfaaaf1-9c5f-4992-a8a5-91c0f0418dc5`
- Fresh Merchant: `http://127.0.0.1:5173/#merchant/bookings/fbfaaaf1-9c5f-4992-a8a5-91c0f0418dc5`
- Weekend Buyer: `http://127.0.0.1:5173/#bookings/19907e60-025b-4d47-93cb-18ced6b6c984`
- Backup receipt: `http://127.0.0.1:5173/#bookings/007ceaeb-bdc6-4f25-a60a-e9bb402a57a5`

</details>
