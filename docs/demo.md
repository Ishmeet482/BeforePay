# BeforePay demo guide

For the user-reported hosted walkthrough, see the [manual observations below](#user-reported-hosted-walkthrough--2026-11-07).
For the historical local 3–4 minute presentation, use the [read-only readiness checklist
and existing-booking scene plan](demo-readiness.md). It separates historical
clarification/correction scenes from an existing real sandbox receipt and identifies
the current stale-comparison/missing-rule blockers. No new AI/payment is required.

Current entry: use **Log in** or **Log in by role** and the displayed
[public demo credentials](demo-login.md). Roles remain simulated;
[server sessions](demo-sessions.md) now isolate each anonymous workspace. Both
roles share that session's bookings. The existing local-booking scene inventory
predates isolation and cannot be assigned to new public sessions. Its unapplied
migration notice describes that local preparation checkpoint, not the hosted
database. Real-person authentication remains unsupported.

## User-reported hosted walkthrough — 2026-11-07

**Evidence: manual observations reported by the user, not an automated test run
or an independent database/provider audit.** The report covers the hosted flow
below; it does not certify all versions, sessions, browsers or error paths.

| Stage | Reported observation | Evidence boundary |
| --- | --- | --- |
| Sources and agreement | Extraction completed. Agreement version 1 and both source acknowledgements loaded after refresh. | Successful extraction/review was observed; intermittent setup errors also occurred. |
| Deposit comparison | AI detected the merchant's deposit-refundability change. | This is one reported comparison, not model-accuracy evidence or a checkout approval. |
| Clarification and reply | The clarification/reply flow was completed. | A merchant response remains unverified resolution; it cannot change terms or approve checkout. |
| Correction and comparison | Correction review was recorded and the fresh comparison matched. | Correction review applies to its saved context; it is separate from rule and checkout approvals. |
| Buyer and merchant rules | AI-proposed rules needed manual refund-allocation corrections; the corrected buyer and merchant rules were explicitly approved. | Human correction and separate approvals were required. Do not describe the original AI proposals as correct. |
| Cancellation | Cutoff previews were exercised after rule correction and approval. | Python calculates from approved rules. This report supplies no exact cutoff timestamps or numeric preview outputs; do not substitute values from the separate local example. No cancellation or refund execution is claimed. |
| Checkout | Exact checkout approval was completed. | Approval remains separate from capture. Hosted sandbox execution defaults off and requires explicit configuration; live payments and hosted webhooks remain disabled. |
| Hosted sandbox receipt (later verification on 7 November) | **Camera kit- test 1** completed a **USD 200** sandbox capture; receipt persisted after refresh and links agreement **v2**, merchant proposal **v2**, saved comparison, checkout approval and both approved cancellation rules. | User-reported manual hosted verification, not a mocked result, independent re-audit or webhook/interruption-recovery demonstration. [Capture details and boundaries](hosted-sandbox-payments.md#user-verified-hosted-sandbox-capture--7-november-2026). |

### Observed errors and remaining limitations

- **Two AI refund-allocation errors were reported**, including assigning the
  inclusive USD 200 refund to the USD 120 rental component. Raw provider outputs
  are not reproduced here. Manual buyer/merchant rule corrections preceded separate
  approvals. The later [component-allocation prompt/schema and blocker update](cancellation-preview.md#component-allocation-correction--2026-11-07)
  was verified offline; its live model-quality improvement is not established.
  This is a reason to review each proposed rental-fee/deposit allocation against
  the saved clauses, not evidence that AI calculates money.
- **Intermittent `public_setup_required` errors cleared on refresh.** During the
  earlier investigation, Agreement review loaded version 1 and both source acknowledgements.
  No failing Network request or sanitised runtime exception was captured, so the
  failing GET/POST, exact guard and root cause remain unresolved. Recovery on
  refresh is an observation, not a diagnosed or fixed defect, and is not a reason
  to retry AI or payment actions automatically. If it recurs, capture the request
  method, endpoint suffix, HTTP status, full `detail.code`/`detail.message`, and
  sanitised Vercel exception class/SQLSTATE; omit cookies, tokens and source text.
- This hosted report is separate from the earlier local sandbox captures and
  [webhook audit](paypal-webhook-verification-2026-11-02.md). Existing local sandbox
  receipts are historical provider-backed records; browser-fixture receipts are
  mocked. Neither is evidence for the new hosted capture; that capture has its
  own user-reported manual verification above.

To demonstrate the saved hosted receipt, use the original owning demo session and
open **Camera kit- test 1 → Checkout & receipt**; refresh and inspect the saved
version links. It is not globally available to other visitors. Do not create or
capture another payment merely to replay this observation. For a separately
authorised new sandbox checkout, use a **Personal sandbox buyer account** distinct
from the app's Business sandbox seller, enter that buyer login only in PayPal's
sandbox popup, and obtain credentials privately from the organiser or Sandbox
Accounts. BeforePay's demo-role credentials are not PayPal credentials. Never
publish passwords or use real PayPal credentials/cards. See [buyer setup](hosted-sandbox-payments.md#sandbox-buyer-walkthrough).

This documentation update reran no tests, made no Gemini/PayPal calls and changed
no hosted records. Existing automated checks remain the separately documented
mocked/offline evidence; they do not reproduce these live observations or resolve
the reported failures. Do not claim general AI accuracy or production readiness
from this walkthrough. See [hosting follow-up](hosting-preparation.md#user-reported-hosted-checkpoint--2026-11-07).

## General walkthrough and evidence boundaries

**Know what you’re agreeing to, before you pay.**

BeforePay compares rental terms with a final merchant booking, makes differences
visible, previews supported cancellation consequences and supports guarded PayPal
sandbox checkout. Identity remains provisional; merchant/customer workspaces are
prototype editing areas, not authenticated roles.

For a provider-free demonstration, use the isolated QA server and synthetic browser
fixtures described in [frontend verification](frontend-redesign.md#verification-and-reproduction).
Never present fixture AI results or mocked receipts as real persisted transactions.
Do not generate AI, compare changed policy wording, load PayPal, create orders,
capture or resend provider events without explicit authorization for that action.

1. **Bookings:** review saved dates/total/status, then Continue. Empty state has a
   clear Create booking entry. Creating a real booking is an explicit write.
2. **Overview:** inspect equipment, pickup/return with timezone, stated amount and
   outstanding checklist. Follow the single next action.
3. **Sources & draft:** source inbox is beside the draft workspace. Saving text or
   uploading a PDF does not generate anything. Source selection, explicit Gemini
   generation, opening review, saving corrections and confirmation remain separate.
4. **Agreement:** read summaries, open individual editors and adjacent original
   evidence. Keep correction reasons and all-source acknowledgements visible.
5. **Comparison:** differences lead. In the labelled synthetic USD 200 example,
   a USD 80 deposit becoming non-refundable remains significant even though total
   is unchanged. A comparison is not a guarantee or approval. Merchant samples
   only fill the form; save and compare are explicit actions.
6. **Cancellation:** choose instant/timezone and request a preview using approved
   complete rules. Rule proposal and human confirmation are separate. Python
   calculates money. Preview does not cancel the rental or issue a refund.
7. **Checkout:** observe backend blockers, separate exact checkout approval and
   explicit PayPal action. Pending/uncertain outcomes are not paid.
8. **Receipt:** a completed capture opens BeforePay's app-issued sandbox payment
   receipt with recorded amount/date and exact references. Copy controls and Print
   are local actions. Itemised amounts are omitted because they were not stored
   in existing captured snapshots; current terms never reconstruct the receipt.
   Payment history is outside the printable document, and audit JSON is collapsed.

Recorded manual verification is separate from this mocked demo: see the
[user-reported cancellation preview](cancellation-preview.md#user-reported-live-proposal-and-manual-preview-verification--2026-11-02)
and [local webhook evidence audit](paypal-webhook-verification-2026-11-02.md).
The webhook audit did not demonstrate live browser-interruption recovery.
Technical compatibility names and receipt limitations are documented in
[BeforePay branding](beforepay-branding.md).


## Current workspace navigation

See [workspace walkthrough and synthetic screenshots](beforepay-ux-overhaul.md).
Comparison now offers a labelled **Prototype view switch** between buyer difference
review and merchant proposal editing. Open optional demo samples inside merchant
view, save explicitly, then return to review and explicitly compare. Cancellation
rule authoring/approval lives in the rule-review disclosure below the calculator.
These views do not imply authenticated identities. All provider actions remain
explicit and need their existing authorization and backend setup.


## Product entry and returning users — 2026-11-03

Root now explains the product with a clearly illustrative unchanged-total/deposit
example. **Start a booking** opens a form without writing; **Open your bookings**
or `/#bookings` goes straight to existing rentals. Booking rows have specific
saved-state actions. Merchant editing offers **Copy buyer-confirmed terms into
form** before optional demo samples; it is not merchant agreement. Saving, comparing,
confirming rules and approving checkout remain separate explicit actions. Home and
Bookings retain the currently opened workspace's unsaved inputs. See
[current walkthrough and synthetic screenshots](product-redesign-2026-11-03.md).
