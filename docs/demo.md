# BeforePay demo guide

For the current 3–4 minute presentation, use the [read-only readiness checklist
and existing-booking scene plan](demo-readiness.md). It separates historical
clarification/correction scenes from an existing real sandbox receipt and identifies
the current stale-comparison/missing-rule blockers. No new AI/payment is required.

Current entry: use **Log in** or **Log in by role** and the displayed
[public demo credentials](demo-login.md). Roles remain simulated;
[server sessions](demo-sessions.md) now isolate each anonymous workspace. Both
roles share that session's bookings. Migration 0013 remains unapplied; the existing
local-booking scene inventory predates isolation and cannot be assigned to new
public sessions. Real-person authentication remains unsupported.

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
