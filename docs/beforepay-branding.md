# BeforePay branding, workspaces and sandbox receipt

**BeforePay** is the display name. Tagline: **Know what you’re agreeing to, before
you pay.** The rename changes presentation and documentation, not existing data,
payment references or integration identities.

## Design audit and changes

The previous interface used warm paper/neutral surfaces (`#f5f3ee`, `#fffefa`),
restrained green (`#235d48`), Helvetica/system typography and 4–5 px controls.
Those tokens remain. Main issues were a tall descriptive rail, repeated status
headings, sequential source/draft panels and a receipt presented as another form
panel. Layout variance 4, motion 2 and density 6 fit this trust-focused product.
The invoked design-taste-frontend skill's audit/typography/spacing guidance was
used; its landing-page imagery and animation patterns do not apply to these
multi-step product workspaces. No component-library/dependency migration.

| Surface | Change |
| --- | --- |
| App shell | BeforePay wordmark/tagline, shorter navigation, 32–48 px desktop gutters, explicit mobile collapse, no redundant visible booking dropdown |
| Bookings | Name, saved dates/total/status and Continue; Create booking stays clear |
| Overview | One next action, equipment/dates, amount and booking checklist; reduced repeated status text; paid total comes from receipt without current-term itemisation |
| Sources | Source inbox/addition/selection beside explicit generation and draft review; one column on mobile |
| Agreement | Readable summaries/section editors beside source acknowledgements; contextual evidence drawer remains keyboard accessible |
| Comparison | Differences, changed tokens and supported deposit amount affected precede merchant editing; matching sections collapse |
| Cancellation | Date/time inputs with prominent backend refund/retained breakdown; supporting rule review/history stays separate |
| Completed payment | Document-style app-issued sandbox receipt; payment history outside it, audit data collapsed |

Paragraphs/form sections are bounded independently of workspace width. Green
identifies actions/current state; amber/red remain for differences or warnings.
No fabricated metrics, decorative imagery or new automatic AI/payment operations.
Source acknowledgement, correction reason, separate save/confirm, stale-input
handling, uncertain payment warnings and in-memory unsaved-tab behavior remain.

## Receipt data contract and limitations

Receipt presentation consumes only the persisted `/checkout/receipt` response for
amount, currency, recorded timestamp, receipt/order/capture IDs, checkout approval
and captured agreement/proposal/comparison/confirmation/rule references. It does
not retrieve current terms to construct a financial breakdown. Existing immutable
checkout contexts contain total and references, **no itemised amount snapshot**;
the receipt explicitly says itemised amounts were not stored. It does not invent
rental/deposit/tax amounts, buyer/merchant identities, a receipt number or new
capture/issue timestamp. The receipt reference is the stored receipt UUID.

Booking title is passed from the booking list and explicitly labelled **Current
booking display label**. A historical title snapshot does not exist in the
receipt, so the UI does not claim this name was captured at payment time. Exact
approved version references continue to identify the historical agreement.
New itemisation or a captured booking-title snapshot would need a separately
authorized persistence change; existing records are not backfilled or rewritten.

PayPal order/capture and receipt references have keyboard-operable Copy controls
with exact values and status/error feedback. Clipboard API permission failures
use a user-triggered fallback and otherwise explain manual copying. Print receipt
calls the browser print action. Print CSS outputs the receipt without navigation,
buttons, payment history or collapsed technical audit, using A4 document spacing.
Native browser Print also uses receipt styling when its workspace is active.

The document is issued by BeforePay, **not by PayPal**, and prominently identifies
sandbox/test funds. It is a historical capture record, not proof of current
settlement or an actual refund/cancellation action. Refund/dispute operations
remain unsupported. No frontend branding can authorize or establish payment.

## Technical identifiers intentionally retained

| Retained identifier | Compatibility reason |
| --- | --- |
| Project directory `Context Key`, source brief `ContextKey - Book with confidence.pdf` | Existing paths and supplied original brief remain intact |
| `contextkey-frontend`, `contextkey-backend` | Distribution identities, lockfiles, imports/tooling remain compatible; package description/API documentation display title use BeforePay |
| Database/user `contextkey`, existing Compose database settings and `postgres_data` volume name | No new database, migration, role, volume or credentials |
| `contextkey-api` health service value | Existing API contract |
| `/api/...`, JSON field names and migration revision IDs | Existing frontend/backend contracts and history |
| `contextkey:changed`, `data-contextkey-sandbox` / `contextkeySandbox` | Internal event and SDK script detection |
| `contextkey-<attempt UUID>` invoice prefix | Order verification and existing provider references must agree |
| `contextkey_reject_*`, `contextkey_protect_payment_attempt` | Existing immutable database trigger functions |
| `uvicorn.error.contextkey.gemini` | Existing diagnostics/logger integration |
| `GEMINI_*`, `PAYPAL_*`, `DATABASE_URL`, other environment keys | No credential/configuration or integration changes |
| Test database/profile/artifact path prefixes | Reproduction and compatibility, not product display branding |
| Stored booking titles, documents, quoted evidence, fingerprints and payment records | Historical customer data is never renamed for presentation branding |

README, guides, demo documentation, contributor heading and app/page/API display
metadata use BeforePay. Literal code/path examples retain the compatibility names
above. Branding coverage tests distinguish display text from those identifiers.

## Verification

Browser QA uses the existing `frontend/vite.qa.config.ts`: environment loading is
disabled and no backend proxy exists. API/provider behavior is synthetic; unknown
API operations fail, PayPal/Google hosts are blocked. No existing booking/payment
records, developer credentials or backend secret files are accessed. Copy tests
stub Clipboard API writes rather than inspect or overwrite the user's clipboard.
The print button invocation is checked separately from real Chrome PDF rendering.

Commands and final outcomes are recorded in the implementation plan after checks.
Reproduction uses the existing mock-browser setup in
[frontend-redesign.md](frontend-redesign.md#verification-and-reproduction), plus:

```sh
cd frontend
node tests/branding.mjs
node tests/redesign.browser.mjs
node tests/included-items.browser.mjs
node tests/paypal-approval.browser.mjs
npm run build
```

Run browser suites sequentially against an isolated headless Chrome page and QA
server. Print PDF/screenshots are synthetic artifacts under `/private/tmp`, not
customer documents or database records. Browser checks cannot establish live
provider availability or actual physical-printer output. There is no deployment,
webhook registration or new payment in this task.

Final outcomes (2026-11-02): build/typecheck passed; **107** desktop/mobile mock
journey/receipt assertions, **12** correction regressions, **7** mocked PayPal SDK
checks and **22** static branding/compatibility checks passed. Changed backend
metadata files passed Ruff lint/format. Backend functional tests were not rerun
for the display-metadata changes; dependencies/lockfiles were unchanged.

The generated synthetic A4 PDF was independently inspected with PyMuPDF: one
page, recorded amount/order/capture/approved-version references present; current
terms, payment history, app chrome, copy/print controls and audit absent. The
rendered background was white. Desktop/mobile evidence, sources, agreement and
receipt screenshots were visually reviewed. The PDF is at
`/private/tmp/beforepay/receipt-fixture.pdf`; screenshots use the retained
`/private/tmp/contextkey-redesign/` QA artifact directory. These files contain
synthetic fixtures only. Owned QA server/browser stopped after checks; no user
backend or tunnel process was managed.


## Receipt integration update — 2026-11-03

The current booking display title now appears outside the printable document. The
receipt itself uses “Sandbox capture record” and its immutable captured values and
references, without filling a missing historical title/itemisation from current
booking data. Copy, print, captured versions and separate payment history remain.
See [current product redesign](product-redesign-2026-11-03.md). Earlier verification
above records the prior display implementation.
