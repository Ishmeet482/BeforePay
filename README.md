# BeforePay

Know what you’re agreeing to, before you pay.

Compare a confirmed rental quotation and messages with a
final booking, resolve differences, approve a version, and pay through PayPal
sandbox. See [BeforePay branding and receipt](docs/beforepay-branding.md),
[demo guide](docs/demo.md), [implementation plan](docs/implementation-plan.md) and
[contributor rules](AGENTS.md).

**Current stage: complete starting flow and guarded PayPal sandbox checkout.** Create bookings,
attach text/PDF evidence, extract drafts, then review, explicitly correct and
confirm complete immutable agreement versions. AI drafts remain unchanged.
The product entry explains why equal prices can hide changed obligations, then
opens guided rental workspaces with saved-state next actions. See the
[product redesign](docs/product-redesign-2026-11-03.md) and the latest
[alignment refinement, verification and screenshots](docs/alignment-refinement-2026-11-03.md).
Buyer and Merchant demo dashboards share bookings with separate task navigation.
Use the labelled [demo login](docs/demo-login.md): Buyer/Merchant remain simulated
roles within one [server-isolated expiring workspace](docs/demo-sessions.md).
Migration 0013 remains unapplied to development; public deployment is still blocked.
Public-demo [Phase 2 controls](docs/public-demo-controls.md) add durable AI/resource
limits and payment denial; migration 0014 is also unapplied. Public AI defaults off.
Phase 3 [hosting preparation and operator runbook](docs/hosting-preparation.md)
adds Vercel configs, strict readiness checks and template-only setup. Migration
0015 is unapplied; no hosting services have been provisioned or deployed.
See [workspace routes, handoffs and limits](docs/buyer-merchant-workspaces.md).
See [evidence API steps](docs/backend-evidence.md) and
[draft configuration and one manual extraction](docs/backend-drafts.md).
Open http://127.0.0.1:5173 and choose **Log in** / **Log in by role**, or start a booking.
Use only the displayed Buyer/Merchant demo credentials.
**Start a booking** always starts the [Buyer flow](docs/booking-entry.md); Merchant demos are offered an explicit switch first. Direct links also request demo entry:
http://127.0.0.1:5173/#bookings for saved rentals. Enter a name and explicitly
**Create booking** to open the evidence inbox. In **Sources & draft**,
paste a quotation/message or upload a text-based PDF, select saved sources, then
explicitly **Generate AI draft** and **Open Agreement review**. See the
[starting-flow guide](docs/starting-flow.md) for limits, configuration and errors.
Loading pages, uploading evidence and editing never start AI extraction.
Existing bookings can go directly to **Agreement review** to read evidence, save
reasoned corrections and explicitly confirm the latest version; this needs no AI
credentials or calls. See [customer review and Swagger verification](docs/customer-review.md).
The **Compare booking** workspace separates buyer differences from the labelled
merchant prototype editing view. It saves independent proposals and explicitly compares them against the confirmed
agreement, with policy-only Gemini judgments when wording differs. See
[comparison screen and API guide](docs/booking-comparison.md).
Saved discrepancies also support explicit, advisory-only
[clarification suggestions](docs/clarification-suggestions.md) and append-only,
provisional [merchant replies](docs/merchant-replies.md); neither can resolve or
approve terms or unblock checkout. Explicit
[correction-review history](docs/clarification-corrections.md) binds buyer
review to the original question/reply, corrected proposal and fresh matching
comparison; it is separate from checkout approval. A narrow
[cancellation preview](docs/cancellation-preview.md) supports explicitly reviewed,
source-bound rules and Python-calculated pre-pickup USD refunds. Explicit
[merchant policy consistency checks](docs/policy-consistency.md)
review saved deposit/cancellation clauses together; current conflict or uncertainty
findings block merchant refund outcomes and checkout without granting approvals.
Explicit,
version-bound [PayPal sandbox checkout](docs/paypal-sandbox.md) now supports order
creation, buyer approval, backend capture/reconciliation and linked receipts.
Sandbox credentials are needed only when explicitly enabling checkout; review
and local previews require none. Verified sandbox webhooks can reconcile completed captures independently of the
browser; see [webhook setup](docs/paypal-webhooks.md). The [local live-delivery audit](docs/paypal-webhook-verification-2026-11-02.md)
does not demonstrate interruption recovery. Live payments are deferred.
Manual sandbox capture and receipt persistence after browser refresh have now
been verified by the user; see the [verification record](docs/paypal-sandbox.md#successful-manual-capture-and-refresh-persistence--2026-10-31).
Refund operations remain unimplemented.
The API is an unauthenticated local prototype; keep the loopback binding.

## Prerequisites

- Node 20.19+ on the 20.x line, or Node 22.12+ (a supported LTS recommended).
  Verified locally with Node 20.20.2 and npm 11.16.0.
- Python 3.14.1 and [uv](https://docs.astral.sh/uv/).
- Docker Engine/Desktop with Compose, or an existing PostgreSQL 17 instance.

Run all commands from the repository root unless a block says otherwise. Start
Docker Desktop/Engine before using the Compose option. Environment examples contain
development placeholders; keep real secrets in ignored `.env` files. Never use
the example database password for a shared or deployed instance.

If using nvm, run `nvm install` and `nvm use` from the repository root first;
`.nvmrc` selects the verified Node 20.20.2 runtime. Run `node --version` before
installing frontend dependencies: some shells on this host default to Node 18,
which cannot run this Vite version.

## 1. Configure and start PostgreSQL

```sh
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up -d --wait db
```

PostgreSQL binds only to host `127.0.0.1:5433` and persists in a named Docker volume.
The container's PostgreSQL port remains `5432`.
If that port is occupied, change `POSTGRES_PORT` in root `.env` and the port in
`backend/.env`'s `DATABASE_URL`. Changing root database credentials also requires
updating `DATABASE_URL`. PostgreSQL initialization variables apply only when the
volume is first initialized; changing them does not change an existing role.

**Existing PostgreSQL alternative:** skip Docker. Ask your DBA to create a local
role and empty database, or run these commands as a PostgreSQL administrator:

```sh
createuser --pwprompt contextkey
createdb --owner=contextkey contextkey
```

Set `backend/.env` to your connection details, using the explicit synchronous
driver: `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE`.
URL-encode special characters in credentials. Use appropriate SSL settings for a
remote instance. The app does not create database users or databases.

## 2. Install and start backend

```sh
cd backend
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend reads `.env` relative to `backend/`; launch commands there. uv creates
`backend/.venv` and installs locked runtime and development dependencies.

- API docs: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/api/health/live> — process only, HTTP 200.
- Readiness: <http://127.0.0.1:8000/api/health/ready> — `SELECT 1`, HTTP 200 or
  HTTP 503 with a generic error. Does not check schema or provider configuration.

## 3. Start frontend (second terminal)

```sh
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to port 8000. Change
`API_PROXY_TARGET` in `frontend/.env` if needed, then restart Vite. Keep the backend
running. Use **Refresh latest** to reload review state and evidence; unsaved edits
require an explicit discard confirmation.

## Focused verification

```sh
# From repository root
docker compose config --quiet
curl --fail http://127.0.0.1:8000/api/health/live
curl --fail http://127.0.0.1:8000/api/health/ready
curl --fail http://127.0.0.1:5173/api/health/live
```

```sh
cd backend
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen alembic upgrade head --sql
# Requires PostgreSQL; confirms migrations are actually applied:
uv run --frozen alembic upgrade head
uv run --frozen alembic current
```

```sh
cd frontend
npm run build
```

Health tests use test doubles; booking/evidence tests create a uniquely named,
isolated PostgreSQL database using public local settings (port 5433), migrate it, exercise actual
committed storage, then remove only that test database. The local database role
needs `CREATEDB` (Compose's default role has it). Existing project data is never
reset. PostgreSQL must be running; database failures fail the integration suite.
All AI calls in automated tests are offline mocks, including the SDK transport;
live SDK construction is blocked by default. Tests do not read developer `.env`
files or actual API keys. No tests verify live model quality,
account access or payment integration. Offline Alembic SQL generation likewise
does not verify a live migration. `npm run build`
includes strict TypeScript checking. Production hosting is outside this stage;
Vite's dev proxy does not run in the static build.

For all mocked frontend feature suites, first start the isolated QA Vite server
and dedicated Chrome as described in [blocker navigation verification](docs/blocker-navigation.md#isolated-browser-verification), then run:

```sh
CDP_URL=http://127.0.0.1:9228 FRONTEND_URL=http://127.0.0.1:5187 npm --prefix frontend run test:browser:all
```

The runner uses a fresh tab per suite, includes clarification/reply/correction,
policy consistency, payment/receipt and connected blocker journeys, and never
proxies to the development backend.

The [frozen v2 policy evaluation dataset and opt-in runner](docs/policy-evaluation.md)
cover 20 labelled comparison/consistency cases. The default runner performs only
offline validation and prints an unmeasured call plan; no AI accuracy is claimed.
Original v1 is retained; v2 verifies a hash manifest and excludes local missing-input
checks from every model-performance denominator.

Stop local API/frontend with Ctrl-C; stop database with `docker compose stop db`.
This preserves database data.

## Layout

```text
frontend/           React + TypeScript + Vite + Tailwind CSS
backend/app/core/  Pydantic settings and synchronous SQLAlchemy sessions
backend/app/health/ Typed liveness/readiness routes
backend/app/bookings/ Booking models, schemas, and endpoints
backend/app/evidence/ Original sources, PDF pages, intake limits and endpoints
backend/app/drafts/ Cited schemas, Gemini adapter, validation and immutable versions
backend/app/agreements/ Customer corrections, review state and confirmations
backend/alembic/   Additive evidence/draft migrations and immutability trigger
backend/tests/     Health and isolated PostgreSQL integration tests
docs/              Scope, staged implementation, official reference notes
compose.yaml       Local PostgreSQL service
```

Drafts are never approved automatically. Customer labels remain provisional;
server-issued demo sessions enforce booking ownership but do not authenticate
people or merchant/buyer roles. Keep local-only until remaining public-deployment
gates are addressed. Confirmation alone never authorizes payment.
