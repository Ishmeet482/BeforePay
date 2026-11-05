# BeforePay demo entry and role dashboards

The public entry now uses BeforePay’s warm paper, deep-ink navigation and restrained teal actions. Its top bar contains the logo, How it works and Log in. Log in and the landing-page Log in by role action open the same accessible role-selection dialog. Start a booking always enters the [Buyer creation flow](booking-entry.md): visitors use Buyer demo login, existing Buyers continue directly, and Merchants explicitly switch before creation.

**Demo login—no real authentication. Use demo credentials only.** Public credentials
still select presentation roles only. [Server-issued expiring sessions](demo-sessions.md)
now enforce booking ownership independently of that role: direct API access and
editing tab state cannot access another session's records. These are anonymous
workspace boundaries, not verified people or authenticated merchant/buyer roles.
Migration 0013 is unapplied to development; public release remains blocked.

## Demo credentials and browser state

| Demo role | Username | Password |
| --- | --- | --- |
| Buyer | `buyer.demo` | `BuyerDemo123!` |
| Merchant | `merchant.demo` | `MerchantDemo123!` |

These deliberately public examples are shipped in frontend code and shown inside the dialog. They are not backend/service credentials. Do not enter real passwords.

Credentials are compared locally against the selected role. Entered passwords live only in the password input and a short-lived submit variable; they are not placed in React state, API calls, URLs, headers, logs, cookies, localStorage or sessionStorage. Password fields are cleared on submission (including errors), role selection, Escape, Close and backdrop dismissal. Username fields are not persisted and reset when the dialog closes. Show/Hide password only changes input presentation. Form autocomplete is disabled; browser extensions/password managers remain outside application control.

Only `beforepay:demo-role = buyer|merchant` is retained in sessionStorage. The demo
name is derived from that role. No token/password/booking data is stored there.
An opaque HttpOnly cookie independently identifies the server session, shared
across same-origin tabs; CSRF material stays in memory. Tab reload retains the
role label; malformed values are ignored. If tab storage is unavailable, a notice
explains that the role lasts until reload. Credentials/configuration are unchanged.

## Journeys

- **Buyer dashboard:** evidence/agreement review, differences/cancellation consequences, then separate checkout approval and receipt. Saved booking rows show dates, inclusive amount, actual persisted status and next action.
- **Merchant dashboard:** buyer-reference/final-proposal preparation, merchant-policy review and buyer handoff/payment monitoring. Its work queue shows buyer confirmation, merchant proposal version, current proposal-rule review and saved-state handoff. It is not a relabelled Buyer table.
- Both dashboards use the same session-owned booking list, IDs, saved versions and receipts. Role selection never creates a booking, approves or captures anything; explicit first demo entry issues the session cookie.
- Sidebar identity panels show Buyer Demo or Merchant Demo, current role, Switch role and Sign out. Booking-level and comparison handoffs to the other view also reopen the same role-selection dialog and require that role’s demo credentials.
- Switching preserves mounted buyer corrections, evidence intake, merchant proposal fields, rule editors and reasons. Each role returns to its prior task; a directed handoff opens the requested task only after valid demo entry. Cancelling login leaves the active view intact. Demo identity does not populate reviewer labels or satisfy approval attestations.
- Signing out always requests confirmation, revokes the server session, clears the role and forms, then returns home with focus on Log in. Saved records remain preserved but a new session cannot reopen them. Rejecting keeps identity and inputs; a session-service outage also retains them. Expired API calls never silently renew or retry mutations. Explicit renewal warns before discarding unsaved work.
- Direct booking URLs request the matching demo view before reads. The backend independently requires active cookie ownership; role switching grants no additional access. Existing route forms remain compatible.

## Accessibility and interaction

Native modal dialog supplies its accessible name, description and inert background. Explicit Tab/Shift-Tab cycling keeps focus among visible controls, with native arrow-key radio selection. Opening focuses role selection. Escape, Close and backdrop dismissal clear typed passwords and restore opener focus where it still exists. Otherwise focus moves to a visible entry/dashboard control. Validation uses inline alerts, labelled inputs, invalid-state descriptions and focus on the required field; other-role credentials cannot change the active identity.

The dialog fits the viewport with natural vertical scrolling. Desktop sidebars become compact identity/navigation sections on tablet/mobile. Shared table definitions remain aligned; mobile rows retain visible labels. Booking evidence remains accessible beside terms, with sidebar offsets measured against the current navigation height. Receipt printing excludes identity/navigation chrome and retains immutable capture content.

## Preservation boundary

The original presentation-only stage changed no backend permissions or schema.
The subsequent [session stage](demo-sessions.md) adds that independent access
boundary and migration 0013. Existing source acknowledgements, correction reasons,
separate saves/confirmations, stale-version checks, uncertainty reconciliation,
Python calculations and immutable receipts remain intact. Provider/comparison/
rule/checkout/payment actions still require explicit controls and server checks.

## Verification

Provider origins were blocked and all API responses synthetic, using the environment-free QA server without a backend proxy. Dedicated demo-entry tests start with empty tab storage and exercise the real dialog. Older workflow regressions seed a demo role and, on cross-role handoffs, submit the displayed public demo credentials through the same production form using a test-only helper. There is no test-login bypass in production code. Their existing approval/payment assertions remain intact.

Verification completed:

- `PATH="/usr/local/opt/node@22/bin:$PATH" npm --prefix frontend run build`: TypeScript and Vite passed. Existing dependency versions/lockfiles retained.
- `frontend/tests/demo-login.browser.mjs`: **88 passed**, covering both local demo logins, empty/wrong/other-role credentials, Show/Hide, Tab/Shift-Tab/Escape/Close/backdrop focus behaviour, role reload, malformed/storage-unavailable cases, direct-link gating, shared booking IDs, retained buyer/merchant inputs, rejected/confirmed sign-out, logged-out Start-a-booking focus, responsive dashboards and labelled controls.
- Existing browser regressions: **187** buyer/merchant journey checks, **108** workspace checks, **107** alignment checks, **12** included-item correction checks and **7** mocked PayPal SDK handoff checks passed. Combined with new entry checks: **509**. No real approval/capture action was initiated.
- `node frontend/tests/branding.mjs`: **27 passed**.
- Offline receipt PDF inspection: one A4 page, immutable captured amount and provider/version references present; identity controls, navigation, history and changed current amount absent.
- [Desktop/tablet/mobile screenshot gallery](screenshots/beforepay-demo-entry/index.md) visually reviewed. Corrected modal focus cycling, dashboard top alignment and responsive identity/navigation spacing. Backend/database tests were not rerun for this frontend-only change.

Browser commands use `FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 node frontend/tests/NAME.browser.mjs` with the isolated QA server (`npm --prefix frontend run dev:qa`) and a dedicated Chrome debugging profile. Scripts must run sequentially in a debugging page because they install different synthetic transports. No real API/database, Gemini/PayPal calls, orders, captures, credential edits, deployment or publishing occurred. Physical devices, other browser engines and a dedicated screen-reader audit remain unverified.

Real accounts, authenticated identities, booking membership and backend authorization remain a separate unimplemented stage.
