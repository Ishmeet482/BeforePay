# Buyer and Merchant workspace refinement

BeforePay keeps one typography/component system with two explicitly labelled
prototype views. Buyer uses teal; Merchant uses indigo with slate navigation.
Navigation, selected controls, primary/AI buttons and quiet surface tints follow
the active view. Success, attention and error colours retain the same meanings
and values in both workspaces. Colour never establishes identity, approval or state.

## What changed

- Added scoped role tokens in `frontend/src/workspace-themes.css`, loaded after the
  existing product styles. The existing internal `--green`/`--ai` token names remain
  aliases for compatibility. No dependency or lockfile changes.
- Added styling-only `data-workspace` markers to the app shell and selected demo
  login view. The sticky header names the current Buyer/Merchant demo view and
  retains sandbox/no-authentication notices. Public How it works remains public.
- Made desktop rails edge-aligned and 248px wide. Navigation and next-task content
  scroll inside a bounded rail area; identity, Switch role and Sign out remain at
  the bottom with independent 44px targets. Removed large per-section gaps and
  reserved padding for visible keyboard focus rings.
- On tablet/mobile, workspace navigation scrolls with the document so it does not
  obscure terms and forms. The role-labelled header remains sticky. Task/evidence
  scroll offsets account for the header's measured height and actual sticky state.
  The navigation, role controls and existing navigation/discard actions remain.
- Set ordinary prose/material terms to 16px, labels to 15px, secondary text/statuses
  generally to 14px, editable text to 16px and controls to 44–46px minimum. Kept
  technical references compact and optional. Headings, money and document references
  retain distinct scales; no transform/zoom or uniform page scaling.
- Rebalanced overview task/action tracks, money summaries, source/draft columns,
  agreement/evidence columns, comparison columns, policy selectors, checkout and
  receipt references. Preserved semantic table colgroups and right-aligned money;
  stacked booking rows keep explicit labels on smaller widths. Long names/clauses
  wrap naturally rather than clipping into adjacent controls.
- Coordinated hover states with each role, kept destructive/semantic colours shared,
  and retained native keyboard controls. The receipt's captured snapshot, copy
  controls, payment history separation and print behaviour remain intact.

All stateful feature components, request bodies, source acknowledgements, correction
reasons, explicit AI actions, separate approvals, optimistic/version guards, uncertain
payment notices and backend payment protections remain in their existing flows.
The theme marker is not a backend role or access-control claim. No authentication,
migrations, backend changes, booking/payment data or credential changes are included.

## Rendered audit and verification

Before editing, captured the existing desktop/tablet/mobile screens using the
environment-free QA server and shared synthetic fixtures. Reviewed old rail density,
identical role styling, small labels and the mobile sticky navigation stack. Then
captured and inspected the refined screens, including both dashboards, every Buyer
and Merchant task, empty/long/missing values, stale comparison, uncertain checkout,
historical receipt and payment history. Additional checks cover 1280×720 short
desktop, 1920×1080 wide desktop and 320px narrow mobile.

The role-theme audit checks role labels, distinct accents, identical semantic
colours, AA contrast for primary/selected-state text, readable fields, common table
columns/stacked labels, bottom identity placement, no overlap/overflow, retained
unsaved corrections and immutable captured values. It performs no API writes and
explicitly forbids the policy-consistency action. Fixture values are synthetic;
screenshots are not evidence of real booking, provider or payment outcomes.

### Reproduce without the backend

From repository root, use installed dependencies and supported Node. In separate
terminals:

```sh
npm --prefix frontend run dev:qa
```

```sh
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --headless=new --disable-gpu --no-first-run --no-default-browser-check \
  --remote-debugging-port=9228 \
  --user-data-dir=/private/tmp/beforepay-role-theme-review about:blank
```

```sh
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 \
  node frontend/tests/role-themes.browser.mjs
```

Omit `--headless=new` to watch. QA Vite reads no environment files and has no backend
proxy. The script installs synthetic fetch responses before navigation and blocks
provider origins. Captures go to `/private/tmp/beforepay-role-themes/`. Run browser
suites sequentially to avoid overlapping fixtures in the same debugging tab.

For a visual walkthrough in that dedicated tab after the script has installed its
fixtures, use `http://127.0.0.1:5187/?case=changed#bookings` for Buyer and
`http://127.0.0.1:5187/?case=changed#merchant/bookings` for Merchant. Open the shared
synthetic booking and inspect each task. Switch through the existing demo modal;
names, saved versions and explicit actions are unchanged. Never use this walkthrough
as authorization to click an AI/payment action on the normal backend.

**Intentionally excluded:** the pending policy-consistency test/action, every backend
test, migrations, development database inspection/writes and live Gemini/PayPal calls.
Cancellation screens use only existing mocked read responses for that panel; no
consistency check was requested or generated.

Browser emulation and accessible-name/contrast checks do not replace physical-device
or dedicated screen-reader testing. The mobile navigation now scrolls with content;
users can return to it at the document top while the current role stays visible in
the header. Prototype demo identity still supplies no backend authentication.

## Checks completed

- `npm --prefix frontend run build`: TypeScript and Vite passed.
- New role-theme rendered audit: **121 assertions passed**. Existing correction,
  clarification/reply, product journey, workspace, alignment, booking-entry,
  demo-login, included-item and mocked PayPal component suites: **674 passed**.
  Combined **795 browser assertions**. These use only synthetic records/providers.
- Static branding/compatibility checks: **33 passed**.
- Actual Chromium receipt PDF export and existing copy/print, evidence, approvals,
  stale-state and unsaved-form regressions passed through the existing suites.
- [Before/after and representative captures](screenshots/beforepay-workspace-themes/index.md)
  visually reviewed at desktop, tablet and mobile widths. Corrected the Merchant
  task-action column, Buyer AI-panel tint, navigation hover contrast, stacked-row
  labels and narrow-header layout during this review.

Initial new audit assertions mistakenly treated checkbox font size as editable text
and expected desktop table geometry for already-stacked tablet rows. Corrected the
assertions to test the actual control types and labelled layout; final audit passed.
No application approval or payment guard was relaxed.

The pending policy-consistency test/action was **not run**. Backend tests, migrations,
normal backend endpoints, development records and credentials were not accessed or
changed. No live Gemini/PayPal calls, deployment or publication were performed.
