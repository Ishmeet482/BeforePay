# Isolated demo sessions — Phase 1

**Current lifetime update — 2026-11-06:** newly issued sessions default to an
absolute **30 days** (`DEMO_SESSION_TTL_SECONDS=2592000`), with a configurable range
of 60–2592000 seconds. The earlier 45-minute default is historical. Existing
database rows keep their stored expiry; no expired session or booking is adopted,
reassigned or extended by this change. No migration is needed. Hosting variables
must be updated separately if they still override the default with 2700.

Persistent cookie `Max-Age` and `Expires` already existed. A normal browser restart
or revisit on the same profile and exact frontend origin can reuse that cookie.
Tab-only role identity may disappear: explicit Buyer/Merchant demo entry reuses
the valid server session without replacing it, changing ownership or extending
expiry. There is no countdown. Sign-out revokes the server session and clears its
cookie; cookie deletion, private browsing and a different domain/profile do not
recover the original workspace. Review/approval/payment safeguards are unchanged.

Global and per-session admission/storage/write/AI caps retain their existing
values and accounting; a 30-day session does not renew allowances. No global
booking listing, new authentication or recovery endpoint was added.

Focused verification: **116 backend checks passed**, including persistent cookie
attributes, restoring a cookie into a new client against a 20-day-old synthetic
session, unchanged owner/expiry on Buyer→Merchant→Buyer reuse, sign-out/replay
denial, foreign-session isolation and existing resource/payment controls. All
database fixtures were disposable; provider calls were mocked/blocked. The mocked
Chromium lifecycle suite passed **12 assertions**, including switching back to
Buyer without another session POST or booking write. Ruff and whitespace checks
passed. This does not claim a real 30-day elapsed or hosted browser-restart test.

Later update: [Phase 2](public-demo-controls.md) now adds durable resource/AI limits
and public payment denial. Its controls supersede the corresponding outstanding
items in this Phase 1 report; hosted verification is still pending.

Implemented locally, 2026-11-05. **Not ready for public deployment yet.**
Migration `0013_demo_sessions` is intentionally unapplied to the development
database. No existing development records or credentials were read or changed.
No Gemini/PayPal calls, deployment or provisioning were performed.

## What this protects

Explicit demo entry now obtains an opaque server-issued workspace cookie. The
public Buyer/Merchant passwords remain browser-only presentation checks, never
sent to the server. They do not identify real people or confer permissions.
Both prototype views access the same session-owned bookings and saved versions.
Editing the role label cannot expand access to another session.

`POST /api/demo-sessions` issues a cryptographically random 32-byte token
(`secrets.token_urlsafe(32)`). PostgreSQL stores only its SHA-256 hash, creation
time, absolute expiry and optional revocation time. The cookie is host-only,
`HttpOnly; Secure; SameSite=Lax; Path=/api`, with a 30-day lifetime by default.
No token, password or CSRF token is logged or stored in browser storage. The
frontend retains its provisional role label in tab sessionStorage and the CSRF
token in memory. Browser cookies are shared across tabs on the same origin;
use separate browser profiles/private contexts to demonstrate separate owners.

| API | Behaviour |
| --- | --- |
| `POST /api/demo-sessions` | Allowed Origin required. New cookie/session → 201; existing active cookie → 200, same scope and expiry. No sliding extension or caller-selected owner. |
| `GET /api/demo-sessions` | Active cookie → expiry and session-bound CSRF token; otherwise 401. Does not create a session. |
| `DELETE /api/demo-sessions` | Allowed Origin and, for an active session, matching CSRF header. Revokes session and clears cookie; expired/missing cookies can be cleared harmlessly. |
| All `/api/bookings` paths | Active cookie required. Listing only includes this owner; new bookings inherit the server session. Foreign or unowned booking paths return 404. |

The shared dependency gates every booking endpoint: sources and extracted PDF
pages, drafts, agreements/confirmations, merchant proposals, comparisons,
clarifications/replies/correction history, policy consistency, cancellation
rules/approvals/previews, checkout configuration/approval, attempts/actions and
receipts. Existing child-to-booking/reference/version validation still applies;
knowing another child ID cannot attach or read it through an owned booking.
No original PDF download capability was added: the existing API exposes extracted
text/pages, which are owner-scoped. FastAPI may parse bounded multipart/JSON before
dependencies; PDF extraction and inference occur only after ownership checks.

Common booking helpers recheck ownership and expiry, including after waiting for
the booking lock and after AI inference. Expired/revoked sessions cannot publish
inference results. Normal API failures never silently create a replacement
session or retry a mutation. Session errors retain form inputs. Explicit renewal
warns before discarding unsaved state; role switching within an active session
preserves it. Sign-out always warns that a new session cannot reopen old bookings.

## CSRF, origin and cache boundaries

All mutations, including issuance and sign-out, require an exact configured
Origin. Unsafe booking requests also require `X-BeforePay-CSRF`, compared in
constant time against an HMAC derived from the opaque cookie with a fixed
domain-separation string. This derivative is returned through the session API;
the cookie token itself is never exposed to JavaScript. Missing/wrong CSRF is
403. Disallowed/null origins and cross-site Fetch Metadata are rejected. Reads
may omit Origin (normal same-origin browser behaviour), but still require the
cookie; supplied Origins are checked. No wildcard credentialed CORS was added.
Direct backend calls enforce exactly the same session/ownership checks.

API success and handled error responses have `Cache-Control: private, no-store`,
`Vary: Cookie, Origin`, `X-Vercel-Enable-Rewrite-Caching: 0` and `nosniff`.
Actual Vercel rewrite/cookie forwarding and cache isolation remain staging checks.
No reverse proxy or cross-origin credential flow was configured in this increment.

The existing PayPal webhook is the explicit exception: no demo cookie or CSRF is
required. It uses the raw database dependency and enables internal reconciliation
access only **after** the existing signature verifier accepts the event. It can
therefore reconcile historical/unowned attempts and expired sessions. Untrusted
headers, event fields and public role labels cannot select this bypass. Existing
provider verification, duplicate claims, immutable receipts and payment guards
remain in place. Health endpoints remain public; API docs contain contracts only.

## Legacy records and setup

The additive migration creates `demo_sessions`, adds nullable
`bookings.owner_session_id` with a foreign key/index, and installs an immutable
ownership trigger. **No backfill or reassignment:** existing bookings retain NULL
owners and become inaccessible to new demo sessions, including through direct
IDs. Existing child versions, approvals, attempts, fingerprints and receipts are
preserved. Expiry/sign-out revoke access, not delete records. No cleanup job or
legacy-record adoption endpoint exists. Historical receipts keep their protections.

After separate authorization to update a database, the documented command is:

```sh
cd backend
uv run --frozen alembic upgrade head
uv run --frozen alembic current
```

Current repository head: `0015_demo_templates`; Phase 1 introduced
`0013_demo_sessions`. **Not run on development by this documentation update.**
Restart backend after that authorized migration and session configuration; rebuild
or reload frontend for the session-aware client. Until migration, new code needs
the missing table/column and is not runtime-ready against the old schema. Existing
local bookings will not appear in the new session dashboard after migration.

Backend configuration (placeholder defaults in `.env.example`, actual `.env`
untouched):

```text
DEMO_SESSION_TTL_SECONDS=2592000
DEMO_COOKIE_SECURE=true
DEMO_ALLOWED_ORIGINS=["https://YOUR-FRONTEND-HOST"]
```

For strictly loopback HTTP development only, explicitly use
`DEMO_COOKIE_SECURE=false` with exact loopback HTTP origins such as
`http://127.0.0.1:5173`. This option rejects non-loopback/non-HTTP origin settings
and non-loopback issuance hosts. Never use it on a public endpoint. Keep Secure
true for HTTPS hosting and configure only explicitly trusted frontend origins.
No broad preview-domain wildcard. No actual environment/credentials changed here.

After authorized setup: open **Start a booking**, enter displayed Buyer demo
credentials, create a synthetic booking, then switch Merchant and confirm the
same booking/version is visible. A separate private browser context starts with
an empty list and cannot open the first context's booking URL. Sign-out or expiry
ends access; this is an intentionally disposable workspace, not a recoverable
account. Avoid real customer evidence.

## Recovery of an original expired synthetic booking

Changing the TTL cannot recover an already expired owner cookie. Passwords are
public demo labels, not proof of ownership, and token hashes cannot reconstruct
the original cookie. Keep that booking and its immutable ownership/history intact.

The existing safe workflow is to explicitly create a new session-owned synthetic
booking from the authored source templates; do not copy approvals or receipts or
claim the new record is the original. Access to the exact original record would
require separately authorised, narrowly scoped operator-assisted recovery of its
original owner session, with a new secret cookie and preserved resource charges.
That recovery flow is not implemented and was not performed. It must not be exposed
as a public Buyer/Merchant-login capability or an automatic reassignment.

## Verification and public release blockers

Tests use real **disposable PostgreSQL** and mocked providers. Migration tests
upgrade 0012 → 0013 with synthetic legacy booking/evidence, compare row counts and
canonical row hashes across every pre-existing application table, verify NULL
legacy ownership and enabled ownership trigger. Payment/receipt tables are empty
in that specific migration fixture; payment regressions separately exercise their
immutable records. No claim of a before/after audit of the development database.

Security tests enumerate every current booking API route for missing, expired
and foreign sessions, cover direct ASGI requests, nested foreign references,
CSRF/origin/cookie/hash/TTL/revocation/legacy checks, and expiry during inference.
Route inventory guards make newly unscoped booking endpoints fail verification.
Webhook regression verifies mocked signed reconciliation/deduplication without
demo cookies. Browser lifecycle fixtures exercise explicit issuance, failed
session requests, renewal warnings, retained inputs, CSRF attachment, role reuse,
expiry without automatic writes and sign-out. Existing product regressions cover
approvals, uncertain payments and historical receipts. These are local automated
checks, not real browser-to-hosted-proxy or provider integration tests.

Commands/results (offline providers throughout):

- `cd backend && uv run --frozen --offline pytest -q --tb=short`:
  **569 passed**, six dependency warnings. Afterward one added foreign-child
  payment/policy regression passed separately; no application code changed after
  that full run. Its provider calls use the existing in-memory PayPal fake.
- `uv run --frozen --offline ruff check .` and
  `uv run --frozen --offline ruff format --check .`: passed, 115 Python files.
- `cd frontend && npm run build`: typecheck and production build passed under
  Node 22.23.1; dependency manifests/lockfiles unchanged.
- All **14 browser feature suites** passed across the initial run and targeted
  continuation. An older synchronous role-login test helper was updated to wait
  for the session transition. `demo-sessions.browser.mjs` adds 11 lifecycle checks;
  existing suites cover desktop/tablet/mobile, retained edits, approvals and receipt
  printing. No live provider or development API was used.

Browser command (environment-free `npm run dev:qa`, isolated Chrome CDP on 9228):

```sh
cd frontend
FRONTEND_URL=http://127.0.0.1:5187 CDP_URL=http://127.0.0.1:9228 npm run test:browser:all
```

See [browser-test setup](blocker-navigation.md) for the existing local QA workflow.

Remaining blockers from the [deployment assessment](public-hackathon-deployment.md):

- Global/session AI budgets, admission/concurrency limits and issuance/upload/
  booking resource caps. A public client can currently create many sessions and
  repeatedly request AI within its own scope. Expiring sessions alone do not
  limit costs or database growth.
- Backend public-mode payment-action denial or organiser-controlled grants;
  webhook admission controls. Existing sandbox payment protections remain, but
  ownership alone does not authorize safe anonymous public payment execution.
- Dedicated synthetic hosted database/templates, explicit environment separation
  and operational retention policy. Never publish the existing local database.
- Vercel routing, Secure cookie forwarding/host validation/cache behaviour,
  backend secrets, Linux runtime/bundle limits, reduced upload limits, cold starts
  and current Free-hosting availability need staging verification.
- Real user/role authentication, account recovery and two-person authorization
  remain unsupported. Session ownership isolates anonymous workspaces only.

Do not publish this backend until those release gates are addressed.
