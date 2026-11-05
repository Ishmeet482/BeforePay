# BeforePay workspace overhaul

For the current entry/workspaces, see [product redesign — 2026-11-03](product-redesign-2026-11-03.md). This document records the earlier stage.

Implemented 2026-11-02. Display branding and the app-issued sandbox receipt are
retained. This stage changes frontend presentation and navigation only. No backend
contracts, calculations, migrations, records, credentials or payment actions changed.

## Journey audit and implemented changes

| Screen | Whose information / current state | Main task and interaction |
| --- | --- | --- |
| Bookings | Saved local bookings; status from persisted agreement, comparison, rules and payment reads | Continue includes the specific next task. Name, equipment, explicit-timezone dates and inclusive total remain concise. Create has a separate form and missing-name explanation. |
| Overview | Buyer baseline, or explicitly labelled merchant proposal when no agreement exists | Next action leads. Equipment, dates, component amounts and outstanding tasks sit beside the inclusive total. Completed bookings lead to the historical receipt. Both current policy approvals are required before showing both policies reviewed. |
| Sources & draft | Buyer evidence and unconfirmed AI output | Source inbox and draft workspace use separate columns. Numbered sequence: save original evidence, select sources and explicitly generate, then open agreement review. Selection consequences are stated. Text/PDF intake and original quotations/pages remain available. |
| Agreement | Buyer-agreed baseline; current confirmation or read-only history | Readable terms come first. Section editors open on request; evidence opens beside the term. Version history is collapsed. Reviewer input sits beside saving, followed by separate exact-version confirmation. Source acknowledgements and correction reasons remain required. |
| Comparison | Buyer-agreed terms against a separate merchant-proposed version | Buyer view leads with changes, exact wording and supported consequences. Matching sections collapse. Merchant view edits an independent proposal beside the buyer baseline. Samples live under optional demo tools. Saving and explicit AI-assisted comparison remain separate actions. |
| Cancellation | Selected buyer agreement or merchant proposal and its reviewed rule status | Policy selector explains its effect and shows the exact source version. Calculator leads; refund and retained amounts come exclusively from the backend. Rule authoring/proposal and explicit rule approval are a separate disclosure. Source clauses, rule editing, blockers and history remain available. |
| Checkout | Exact backend-derived agreement/proposal/comparison/policy bundle | Inclusive total and saved version summary sit beside reviewer/acknowledgement controls. Checkout approval, SDK loading and PayPal action remain distinct. Existing uncertain attempts lead the page; fresh approval forms stay out of the way while status is uncertain. |
| Completed payment | Immutable capture record; current booking label explicitly identified | Existing document receipt, exact amount/date/version/provider references, copy controls and print action remain. History sits outside the receipt; audit data stays collapsed. No historical itemisation is reconstructed from current terms. |

Buyer journey: booking → source evidence → explicit draft → review/correct → save
review → acknowledge sources again → confirm exact agreement → compare the saved
merchant version → separately review both policies → preview consequences → approve
exact checkout → explicit sandbox PayPal flow → recorded receipt.

Merchant journey: open comparison → choose **Merchant · edit proposal** in the
**Prototype view switch** → edit independent fields with label and reason → save a
new merchant version → **Review saved versions & compare** → explicitly compare.
Switching does not save, compare or discard form fields. These views are not
permissions, identities or authenticated roles.

## Shared interaction and visual system

One stylesheet now defines the working system instead of layered redesign
patches. Warm canvas/paper, dark text, restrained green, semantic amber/red and
visible text labels distinguish ordinary, changed and blocked states. Native
buttons, dropdowns, inputs and disclosures use consistent typography, borders,
focus outlines and spacing. Desktop gutters stay within 32–48 px; bounded forms
and readable paragraphs sit inside purposeful working columns. Navigation moves
to a horizontal scroller on tablet/mobile; the active stage is also written above
the booking title. No remote fonts, imagery, animation library or new dependency.

The invoked design-taste-frontend skill supplied audit-first design direction and
its relevant hierarchy, restraint and accessibility guidance. Its own scope excludes
multi-step product UI; marketing-only imagery, hero, motion and system-install
rules were not applied to this native React/Tailwind product. Product settings:
DESIGN_VARIANCE 4, MOTION_INTENSITY 2, VISUAL_DENSITY 5. Caveman controls report
brevity, not customer-facing prose or policy text.

Disabled primary controls retain specific adjacent explanations. Contextual links
route checkout blockers to agreement/comparison/policy review and focus local
missing inputs, source acknowledgements, correction reasons or rule approval.
Opening a local resolution target expands its enclosing disclosure. Loading,
saved, validation-error and stale-response feedback remain visible. Evidence uses
a native modal drawer with focus trapping, Escape, focus restoration and a full
mobile width. Reduced-motion preference is respected.

Visited workspaces stay mounted: source text/file selection, buyer corrections,
merchant fields and rule edits survive normal task navigation. Leaving a booking
warns about discarding workspace edits; existing refresh/version/sample replacement
warnings remain. Opening review from Sources now preserves source input rather
than warning incorrectly that the still-mounted input will be discarded.

## Preserved safeguards

All AI and payment writes remain explicit. Backend server checks are authoritative.
No AI calculation, automatic comparison, automatic approval, buyer-callback payment
proof, provider fallback or new payment capability was added. Exact fingerprints,
source acknowledgements, per-section/overall reasons, rule attestations, current
confirmation/comparison requirements, uncertain-attempt reconciliation and immutable
receipt reads remain unchanged. Technical compatibility identifiers remain as
recorded in [branding notes](beforepay-branding.md).

## Verification

The expanded browser suite uses only synthetic in-browser API fixtures, installed
before navigation. The QA Vite config has `envDir: false` and no backend proxy;
provider hosts are blocked. Desktop 1440×1000, tablet 834×1112 and mobile 390×844
cover empty bookings, awaiting review, changed terms, stale comparison, missing
rules, ready checkout, uncertain payment and a completed receipt. A continuous
buyer/merchant journey exercises evidence save/generation, review save/confirmation,
merchant save/comparison, separate policy proposals/approvals, preview and exact
checkout approval, with no order/capture initiation. Synthetic proposal responses
include the API's default empty customer-entered citation lists.

**174 browser assertions passed**, plus **12 included-items** and **7 sandbox SDK
handoff regressions**. Build/typecheck passed. Static branding coverage passed.
PyMuPDF confirmed the synthetic print PDF is one A4 page with the exact captured
values and no app chrome, history, controls or audit output.

Checks include original text/PDF preservation, explicit mutation payloads, edit
retention, 409 stale rejection, source validation errors, selection consequences,
control names in Chrome's accessibility tree, keyboard focus/copy, drawer Escape,
responsive overflow, supported financial consequences, receipt snapshot isolation,
clipboard denial/fallback, print action and receipt-only print CSS.

Commands (Node must satisfy package.json):

```sh
cd frontend
npm run build
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/redesign.browser.mjs
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/included-items.browser.mjs
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 node tests/paypal-approval.browser.mjs
node tests/branding.mjs
```

Use the isolated QA server and headless Chrome setup from
[the earlier frontend guide](frontend-redesign.md). Browser suites run sequentially.
`redesign.browser.mjs` produces screenshots under `/private/tmp/contextkey-redesign`
and a synthetic print PDF under `/private/tmp/beforepay`; these historical test
paths are compatibility identifiers. A checked-in synthetic gallery is linked below.

Backend guard regression command:

```sh
cd backend
UV_CACHE_DIR=/private/tmp/beforepay-uv-cache uv run --frozen pytest -q -x --tb=short \
  tests/test_customer_review.py tests/test_booking_comparisons.py \
  tests/test_cancellation_preview.py tests/test_paypal_sandbox.py \
  tests/test_paypal_webhooks.py
```

**180 passed**, six dependency warnings. The fixture creates/migrates and removes
only its randomly named disposable PostgreSQL database, uses `_env_file=None`,
and blocks live Gemini construction and the live PayPal client. Initial sandboxed
DB execution could not connect and was stopped; the permitted loopback rerun above
passed. Existing development bookings/payments/receipts were not used or modified.

## Screenshots and remaining limits

[Main-screen screenshot gallery](screenshots/beforepay-ux/index.md) contains desktop,
mobile and tablet views plus blocked/error states. Every name, amount, AI response,
provider reference and receipt in these screenshots is a synthetic frontend fixture;
none establishes a live integration or a real transaction.

No authentication or merchant authorization exists. Reviewer labels remain
provisional. No live AI/provider/browser-interruption recovery test occurred.
Accessible names, keyboard paths and responsive layouts were checked in desktop
Chrome emulation; this is not a full WCAG audit, screen-reader certification or a
real iOS/Android/Safari/Firefox test. Browser-native printing remains dependent on
user print settings; the automated A4 PDF check covers the supplied mock receipt.

Hidden workspaces retain their loaded snapshots until explicitly refreshed; backend
stale-version checks prevent them from authorizing changed inputs. Overview status
refreshes after successful writes. Draft inputs survive task navigation, not a page
reload or browser restart. Booking list status still uses several existing API
reads per booking; no new aggregation/pagination API or unsupported feature was
invented. The receipt snapshot has no itemised component breakdown or historical
booking title, so only its captured total and current labelled booking name appear.
