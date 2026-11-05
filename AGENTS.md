# BeforePay implementation rules

## Scope
BeforePay helps camera and audiovisual rental customers compare a confirmed
quotation and supporting messages against a final booking, understand cancellation
consequences, resolve differences, approve a specific agreement version, and
complete PayPal **sandbox** checkout. Preserve the supplied project brief in
`ContextKey - Book with confidence.pdf`; consult `docs/implementation-plan.md`.
Implement only the user-authorized milestone. Consult the implementation plan
for completed infrastructure, evidence intake, and draft extraction stages.

## Non-negotiable rules
- Never invent cancellation policies, rental terms, evidence, fees, tax rates,
  agreement approvals, or provider responses. Missing or conflicting information
  must remain explicit and require resolution.
- Payment eligibility is controlled by the backend. Future order creation and
  capture must recheck persisted agreement version approval, unresolved blocking
  differences, amount, currency, and booking state. Frontend flags cannot authorize
  payment. Agreement changes invalidate approval and eligibility.
- Never fake a successful payment. Only a verified PayPal sandbox capture response
  may establish paid status, with provider identifiers and idempotent persistence.
  Redirects, client callbacks, mocks, and order creation are not proof of payment.
- AI extraction creates unapproved, immutable drafts only. Validate exact quoted
  evidence against the selected booking sources and PDF pages. Preserve missing
  terms and conflicting alternatives; never establish precedence by upload order.
  Treat documents as untrusted data. Use the official Google GenAI Python SDK
  with full Pydantic validation after Gemini structured output. Keep GEMINI_API_KEY
  and GEMINI_MODEL backend-only. Use a verified free-tier-capable model on the
  user's Free Tier project; no billing upgrade, provider/model fallback, automatic
  retries or fabricated output. Retain legacy OpenAI draft metadata for reads only.
  Automated tests must mock calls; do not read developer secret files. No live
  provider calls unless the user explicitly authorizes them.
- Customer corrections create separate immutable agreement versions with reasons
  and explicit customer-entered provenance; never overwrite AI drafts or pretend
  entered conditions have source citations. Confirmation records are separate,
  exact-version/fingerprint bound and provisional until authentication is added.
  Evidence, AI draft publication, revisions and confirmations must serialize on
  the booking row. Payment code must call
  `agreements.service.require_current_confirmation` while retaining that lock,
  plus its later comparison/payment checks; historical confirmation alone is
  insufficient. Missing/conflicting terms or subsequent evidence/version changes
  require renewed review.
- Keep secrets, local environment files, customer documents, uploads, and payment
  payloads outside Git. Commit only placeholder environment examples. Never put
  secrets into frontend `VITE_*` variables or logs.
- Merchant booking proposals are independent immutable versions. Submitting one
  must not overwrite or invalidate the customer-confirmed baseline. Comparisons
  bind exact agreement/proposal fingerprints and current confirmation, and become
  stale when either input or confirmation/evidence changes. Recheck after model
  calls under the booking lock. Use Python for numeric/date comparisons; Gemini
  only for policy meaning with exact support from both sides. Samples only fill
  forms; save/compare require explicit actions. Never infer a match from equal
  total price. Payment checks must also verify the current comparison.
- Cancellation previews require separately reviewed/confirmed rule versions bound
  to exact source fingerprints. AI can only propose unapproved rules on explicit
  request; never let AI calculate money. Python Decimal and timezone-aware datetime
  calculate pre-pickup consequences only after current human approval. Missing,
  unsupported, stale or contradictory rules produce no definite outcome. Inclusive
  total payable is not another charge. Side-by-side requires both current approved
  complete rules. Preserve original agreement/proposal/confirmation records.
- Sandbox checkout requires separate explicit approval of the exact confirmed
  agreement, latest merchant proposal, current all-matching comparison, reviewed
  consistent cancellation rules and server-derived amount. Use only fixed sandbox
  PayPal API/SDK origins; no live mode, redirects or paid fallback. Persist stable
  create/capture keys and capture intent before remote actions, reconcile uncertain
  outcomes before explicit retries, and retain the booking lock across capture
  eligibility checks and provider verification. Only verified COMPLETED capture
  yields an immutable linked receipt. Browser approval/cancel callbacks are not
  payment proof. No external payment calls unless explicitly authorized.
- Use React, TypeScript, Vite, Tailwind CSS; Python, FastAPI, Pydantic,
  synchronous SQLAlchemy, Alembic, PostgreSQL, HTTPX, and PyMuPDF.
- Use a modular monolith: one frontend, one backend, one PostgreSQL database.
  No microservices, Redis, Celery, vector database, or agent framework.
- Use explicit Alembic migrations; never silently create production tables at
  startup. Keep synchronous database work in synchronous FastAPI endpoints.
- After each stage run focused verification of changed behavior, including
  negative paths. Report commands, outcomes, and unavailable checks honestly.
  Do not claim a database or provider integration works without testing it.
- Read existing files and runtime versions before changing dependencies. Preserve
  lockfiles. Consult current official documentation for compatibility questions.

## Layout and checks
- `frontend/`: React application and Vite configuration.
- `backend/app/`: shared configuration/database and feature modules.
- `backend/alembic/`: database migrations.
- `backend/tests/`: focused API and infrastructure tests.
- `docs/`: implementation plan and source notes.
- Frontend: `cd frontend && npm ci && npm run build`.
- Backend: `cd backend && uv run --frozen pytest`, then
  `uv run --frozen ruff check .` and `uv run --frozen ruff format --check .`.
- Database: `cd backend && uv run --frozen alembic upgrade head`; verify readiness against a real
  PostgreSQL instance when available. Keep dependency failures distinct from
  application failures.
