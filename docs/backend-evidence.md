# Booking and evidence backend verification

This guide covers the completed bookings and evidence intake milestone.
For the browser journey, see [Sources & draft](starting-flow.md).
[Draft extraction](backend-drafts.md) is now a separate backend feature; intake
itself performs no AI, approval, cancellation computation or payment operation.
Session update: all booking/evidence routes now require an active owner cookie;
mutations require allowed Origin and CSRF. See [session API/setup](demo-sessions.md)
before using the older request examples below. They need the same cookie/CSRF
context; public demo passwords are not API credentials. Migration 0013 remains
unapplied to development. Keep FastAPI bound to `127.0.0.1` and use synthetic
rental examples. Source lookup retains its booking binding, now combined with
session ownership authorization.

## Startup

Keep existing `.env` files; do not overwrite credentials. PostgreSQL host port
remains `5433`, container port `5432`. With Docker already running, from root:

```sh
docker compose up -d --wait db
cd backend
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Migration `0002_bookings_evidence` adds three tables and one index; no existing
tables are dropped or truncated on upgrade. Re-running upgrade at head is safe.

## Exact Swagger steps

Open <http://127.0.0.1:8000/docs>. For each operation select **Try it out**, fill
fields, then **Execute**.

1. `GET /api/health/ready`: expect **200**, `database: "ok"`.
2. `POST /api/bookings`: submit the JSON below. Expect **201**. Copy returned `id`
   as `booking_id`; timestamps are server-generated and timezone-aware.

   ```json
   {"title": "Camera and AV rental — weekend shoot"}
   ```

3. `GET /api/bookings`: use `limit=20`, `offset=0`; expect **200** with booking.
   `GET /api/bookings/{booking_id}`: paste copied UUID; expect **200**.
4. `POST /api/bookings/{booking_id}/sources/text`: paste UUID and JSON below.
   Expect **201**. Copy returned `id` as `source_id`.

   ```json
   {
     "source_type": "quotation",
     "original_text": "Camera, two batteries, microphone.\nPickup Friday 09:00; return Monday 10:00.\nQuoted total: USD 200."
   }
   ```

5. Repeat the text endpoint with `source_type: "message"` and original message
   text. Whitespace/newlines are preserved; no conditions or policies are inferred.
6. `GET /api/bookings/{booking_id}/sources`: expect metadata for attached sources.
   `GET /api/bookings/{booking_id}/sources/{source_id}`: expect exact original text,
   source type, `medium: "pasted_text"`, `filename: null`, `pages: []`.
7. `POST /api/bookings/{booking_id}/sources/pdf`: paste UUID, select
   `source_type=quotation`, and choose a text-based `.pdf` file in the file picker.
   Expect **201**, original filename, `medium: "pdf"`, complete extracted text,
   and `pages` containing `page_number` starting at **1** and each page's text.
   The supplied project brief PDF can verify extraction mechanically; it is not
   a rental quotation, so use a synthetic rental PDF to verify representative data.
8. Copy PDF source `id`; retrieve through the source GET endpoint. Reload Swagger
   or restart FastAPI and repeat GET; booking, original text and pages persist.
9. Negative checks: upload corrupt `.pdf` (**422**, `unreadable_pdf`), password-
   protected PDF (**422**, `encrypted_pdf`), image-only/scanned PDF (**422**,
   `pdf_ocr_required`), or non-PDF file (**415**). Use an unknown valid booking UUID
   for **404**. An invalid UUID or missing required form field returns **422**.

## Evidence contract and limits

- Booking title: 1–200 characters, nonblank, no NUL. Sources classify as
  `quotation` or `message`; medium records `pasted_text` or `pdf` independently.
- Pasted original text: 1–100,000 characters, nonblank, no NUL. No stripping,
  rewriting, normalization or semantic extraction.
- PDFs: at most **5 MiB (5,242,880 bytes)**, **100 pages**, **100,000 extracted
  characters** total. Require a `.pdf` filename (up to 255 characters, no directory
  path), `application/pdf` MIME type, PDF signature and a readable PDF structure.
- Whole POST/PUT/PATCH bodies are bounded at **5 MiB + 64 KiB** before multipart
  parsing, even without Content-Length. Oversized body/file/text/page count gives
  **413**; oversized pasted JSON text gives Pydantic **422**.
- PDF page text is the unmodified PyMuPDF `get_text("text")` output, not a promise
  of original typography or perfect reading order. Source `original_text` is the
  concatenation of page text; individual page records preserve boundaries.
  Original PDF binary files are not retained or served by this milestone.
- Blank pages within a text PDF retain their page number. Image pages without
  extractable text reject the entire document, including mixed text/scanned PDFs.
  Documents with no extractable text reject with an OCR-required explanation.
  No OCR runs. Images with some text elsewhere on the same page cannot reliably
  be classified as a complete transcription; inspect evidence before later use.
- All encrypted PDFs are rejected, including owner-password-only encryption.
  Rejections occur before evidence is persisted. PDF extraction runs synchronously
  under a process-local lock because PyMuPDF does not support concurrent threads.
- Lists paginate with `limit` (1–100, default 20) and `offset` (0 or higher).
  Source lists return metadata; source detail GET returns text and pages.
- No source update/delete routes are added. Extraction creates separate immutable
  drafts without rewriting evidence. No approvals or checkout operations exist.

## Checks

Run from `backend/` against the local PostgreSQL server:

```sh
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen alembic current
uv run --frozen alembic check
uv run --frozen alembic upgrade head --sql
```

Integration fixture creates `contextkey_test_<random UUID>` on the configured
server, applies actual Alembic migrations, and uses new request sessions and
independent database connections to verify commits and source/page retrieval.
Only that fixture-created database is removed afterward. Tests never reset the
configured project database. The role needs `CREATEDB`; database errors are test
failures rather than silently skipped checks.

Official implementation references:
[FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/),
[PyMuPDF documents](https://pymupdf.readthedocs.io/en/latest/document.html), and
[SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html).
