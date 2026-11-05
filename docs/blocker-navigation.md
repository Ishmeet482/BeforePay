# Saved blockers and next actions

BeforePay uses one exact-code mapping in `frontend/src/blocker-actions.ts` for
Buyer/Merchant overview actions, checkout blockers and cancellation review/preview
blockers. `BlockerActions.tsx` renders the explanation, affected saved source/rule
version when available, and destination. No backend eligibility or approval code
changed. A navigation action is not confirmation, policy approval or payment.

| Saved blocker | Destination |
| --- | --- |
| Merchant policy consistency requires clarification | Relevant merchant findings in the current workspace's policy panel; refreshes saved findings without replacing rule fields |
| Stale/missing comparison | Buyer comparison of saved versions; Merchant view offers an explicit Buyer demo switch |
| Differences/clarification | Buyer difference review; proposal editing remains a separate Merchant action |
| Missing/stale agreement rule approval | Buyer cancellation rule review, selecting the saved agreement |
| Missing/stale merchant rule approval | Merchant policy-rule review, selecting the saved proposal |
| Missing merchant proposal / inconsistent merchant clauses | Merchant versioned proposal editor |
| Cancellation instant invalid | Buyer calculator inputs |
| Unknown code or missing rule-source binding | Honest explanation and original code; no guessed destination |

Cross-role actions say **Switch to Buyer/Merchant demo view** and open the existing
demo-login modal. Switching does not write booking data or grant an approval.
These views provide **no backend access control**. Existing forms stay mounted for
ordinary navigation and role switching. A source-specific rule action refreshes
saved inputs; replacing dirty fields or selecting another source requires a discard
warning. Staying on the same source retains dirty rule fields. Existing explicit
refresh/discard and page-unload behaviour remains.

Version labels come from saved API data, not inferred numbering. Rule-local
blockers use that rule's source/version; checkout uses the latest saved snapshot.
A stale comparison links to comparison review, where exact historical bindings
remain available. Missing data is labelled unavailable. Navigation/GET refreshes
never generate AI output or automatically compare, save, confirm or pay.

## Isolated browser verification

Use the installed Node **22.12+** (or supported Node 20.19+) and installed Chrome.
No dependency installation or credentials are required for these mocked suites.
Start the QA server from the repository root:

```sh
npm --prefix frontend run dev:qa
```

In another terminal, start a dedicated browser profile:

```sh
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --disable-gpu --no-first-run --no-default-browser-check \
  --remote-debugging-port=9228 \
  --user-data-dir=/private/tmp/beforepay-blocker-review about:blank
```

Run **all existing browser feature suites**, including the connected blocker journey:

```sh
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 \
  npm --prefix frontend run test:browser:all
```

The runner discovers every `tests/*.browser.mjs`, runs sequentially in a fresh tab
per suite, closes its own tabs and stops on failure. Existing single-suite command
`npm run test:browser` remains available. For focused reproduction:

```sh
cd frontend
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 \
  node tests/all-browser.mjs blocker-journey.browser.mjs
```

The QA Vite configuration reads no environment files and has no backend proxy.
Suites inject synthetic API responses and block provider origins. Do not substitute
the normal development server. Stop the dedicated QA server/browser afterwards.

The connected journey explicitly generates a mocked clarification for a saved
discrepancy, saves a merchant response, corrects the proposal, follows the stale
comparison handoff, explicitly compares, records correction review, separately
reviews/approves agreement and merchant rules, then separately approves checkout.
It never loads PayPal, creates an order or captures payment. Additional assertions
cover unknown blockers, role/source selection, unsaved fields, keyboard focus and
mobile wrapping. Captures are written to `/private/tmp/beforepay-blocker-journey/`.

## Boundaries

Existing policy findings, comparison discrepancies, source problems, missing rule
approvals and uncertain payments remain blockers until their existing server checks
pass. A clean policy report cannot override conservative rule checks. Missing source
bindings cannot safely select a rule version; unknown codes require inspection.
Cross-client changes still require refresh, and every approval/payment action
rechecks the backend independently. No authentication, migration, new approval,
calculation model or provider behaviour was added.

This work is provider-free automated verification, separate from the previously
documented user-reported live/manual observations. No development records or
credentials are read or changed, and no live Gemini/PayPal calls are needed.

## Verification completed — 2026-11-04

- `npm run test:browser:all`: all **13 feature suites passed**, **837 assertions**
  in that full run. This includes the original connected-journey coverage.
- Expanded connected journey subsequently passed **18 assertions**, including
  explicit discard/cancel, saved-source selection and preserved dirty fields.
  The affected redesign regression also passed **187 assertions** after the
  findings/rule focus and scroll fixes. Final focused journey passed after adding
  the inactive-workspace request guard. Repeated runs are not added to the full-run
  assertion total.
- `npm run build` passed, including strict TypeScript checking; static branding
  checks passed **34 assertions**. Dependencies and lockfiles are unchanged.
- Reviewed generated desktop checkout and mobile policy-findings screenshots.
  The initial mobile capture exposed focus without scrolling to the findings;
  corrected the destination scrolling and inspected the new capture.

Initial runner verification found a URL-encoded project path issue; fixed with
`fileURLToPath`. An older checkout fixture supplied a source-less generic rule
blocker; changed the missing-rules case to the actual agreement/proposal backend
codes and updated the corresponding navigation expectation. Connected-fixture
corrections addressed selectors, explicit demo-modal handling and initially
unapproved rule states. No backend guard was relaxed to make tests pass.

No backend tests, migrations or completed live/manual provider scenarios were
rerun. All new scenario state and writes belong to in-browser synthetic fixtures;
no development database, secret files, Gemini or PayPal service was accessed.
