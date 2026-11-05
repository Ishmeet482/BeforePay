# First Git commit preparation

Prepared 2026-11-05. Local Git repository initialised on `main`; no files staged,
no commit, no remote, no push and no deployment. Existing source, local environment
files, uploads and configuration were preserved. Only ignore rules and this
preparation note were added/updated.

## Proposed contents

- React/TypeScript frontend, shared styles, browser regression fixtures and tests.
- FastAPI backend, application services, tests, all 15 Alembic migrations and
  explicit operator scripts. No migration or application service was run here.
- `frontend/package-lock.json`, `backend/uv.lock`, package/runtime declarations,
  Compose and prepared Vercel configuration with invalid domain placeholders.
- Four sanitised configuration examples: root `.env.example`, backend
  `.env.example` and `.env.public.example`, frontend `.env.example`.
- README, implementation/deployment/demo guides, APIMatic attribution, labelled
  synthetic screenshots and receipt-print specimens, evaluation datasets/freeze
  manifest and preserved synthetic model-pilot results.
- `AGENTS.md`, `paypal-plan.md` and the explicitly required supplied project brief
  `ContextKey - Book with confidence.pdf`.

## Exclusions and verification

Root `.gitignore` excludes actual `.env` files, local credential/agent/service
state, keys, database exports/files, customer upload/storage paths, logs,
temporary/browser artifacts, dependencies and build/cache output. PDFs are
excluded except the supplied brief and documented synthetic screenshot prints.
Existing Python migrations remain included; ad hoc SQL dump files are excluded.

Git ignore boundary checks covered 21 excluded paths and nine required retained
paths. Candidate scanning used offline provider-token/private-key/JWT patterns,
credential-bearing database URLs and secret-like literal assignments. Findings
were reported by path/line/category only; no secret values or actual `.env`
contents were printed or read. Placeholder configuration and public demo login
strings are intentional, not production credentials. No dedicated secret-scanner
binary was installed; this was a custom offline candidate review.

All candidate UTF-8 text and six PDF text layers were scanned. The 235 PNGs are
documented synthetic UI captures; their pixels were not OCR-scanned. Binary image
review and pattern matching cannot guarantee absence of every possible secret.
Future added/staged files require a fresh scan. No known secret blocker was found.

Proposed snapshot is approximately 33 MB; no individual candidate exceeds 10 MB.
Nothing is staged. Git repository URL and publishing remain intentionally unset;
choose the destination only in a separately authorised step. Application build,
provider, database and regression tests were not rerun for ignore-only changes.
