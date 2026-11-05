# Start a booking in the browser

Start PostgreSQL, FastAPI on port 8000 and Vite on port 5173 using the
[README](../README.md). Keep the existing environment files and PostgreSQL host
port 5433. No migration or new dependency is required for this UI.

1. Open <http://127.0.0.1:5173> for the product explanation and clearly illustrative
   deposit example. **Start a booking** opens the creation form; enter a title
   (up to 200 characters), then explicitly **Create booking**. The new booking
   opens **Sources & draft** directly. **Open your bookings** or `/#bookings`
   reaches saved rentals directly. Each row opens its actual saved-state next task;
   the **Overview** and other stages remain available in booking navigation.
2. Choose **Quotation** or **Message**. Paste original text and click **Save
   source**, or choose **Upload PDF**, select a text-based PDF and save it.
   Each successful save persists a separate source; it does not call AI.
3. Under **Select sources for your draft**, expand **Read saved source** to inspect the
   original text and PDF pages. Check the sources to include. Selection does not
   imply that you have acknowledged them during agreement review.
4. Read the AI usage notice, then explicitly click **Generate AI draft**.
   Only checked sources are submitted to Gemini. Loading, refreshing, uploading
   and selecting sources never generate a draft. Generation creates an immutable,
   unconfirmed draft after backend schema, financial and exact-evidence validation.
5. Enter **Your name / reviewer label** and click **Open Agreement review**.
   A new draft is imported as an unconfirmed review version. Reopening a draft
   already under review uses the saved agreement without replacing corrections.
   Follow the [review guide](customer-review.md) to correct terms with reasons,
   acknowledge evidence, **Save review**, then explicitly confirm a complete
   version. No action in the starting flow confirms an agreement or starts payment.

## Limits and errors

- Pasted text: nonblank, no NUL characters, up to 100,000 characters per source;
  original whitespace and wording are preserved.
- PDF: nonempty `.pdf`, filename up to 255 characters, maximum 5 MiB, 100 pages
  and 100,000 extracted characters. Browser checks file size/type; backend checks
  actual PDF content. Encrypted/unreadable files are rejected. Scanned or image-only
  pages require OCR before upload; alternatively paste the original text.
- Extraction: select 1–20 saved sources, at most 200,000 combined characters.
  The server remains authoritative for all limits and ownership checks.
- Saving/uploading/generating displays progress and prevents duplicate clicks.
  Errors preserve input where persistence was not confirmed. If a timeout/network
  error leaves the outcome uncertain, refresh saved sources/drafts before retrying;
  the server may have completed the request. Refresh the booking list before
  retrying uncertain booking creation. Nothing retries AI automatically.
- Missing backend AI configuration, exhausted quota, unavailable service and
  invalid output have actionable messages. Failed validation never produces a
  fabricated draft. Saved evidence remains available after generation failure.

## AI configuration and review safeguards

For a manual extraction only, configure `GEMINI_API_KEY` and `GEMINI_MODEL` in the
ignored **backend** environment as described in the [extraction guide](backend-drafts.md).
Keep the existing Free Tier project and billing settings; this UI neither changes
billing nor guarantees remaining quota. Never put credentials in frontend settings.
Reading saved drafts and reviewing agreements needs no provider credentials.

Missing terms and conflicts remain unresolved. Review must account for all current
sources, including any omitted from extraction. Adding evidence or publishing a
new draft requires renewed review; historical drafts, corrections, confirmations
and receipts remain stored. The backend continues to enforce exact fingerprints,
latest-version checks and payment eligibility. Customer labels and perspective views are provisional
until authentication is implemented. Verified sandbox webhooks are implemented;
refund operations remain unimplemented. See [current product/workspace design](product-redesign-2026-11-03.md).

## Historical verification for the original starting-flow stage

- `cd frontend && npm run build`: TypeScript and production build passed.
- `cd backend && .venv/bin/python -m pytest -q tests/test_starting_journey.py tests/test_bookings_evidence.py --tb=short`:
  32 passed against an isolated PostgreSQL database, with provider calls mocked.
- Headless Chrome exercised the actual React/API journey using a separate randomly
  named PostgreSQL test database and mocked Gemini SDK responses: booking creation,
  original quotation/message preservation, oversize/unreadable/valid PDF handling,
  page references, selected-source extraction, opening and reopening unconfirmed
  review, unresolved-term blockers, quota failure, refresh without retry and 390px
  layout. One synthetic booking, four sources, one draft and one review version;
  zero confirmations/receipts. The test database was removed afterward.
- Existing mocked checkout browser regression passed. No live AI or PayPal calls
  and no access to completed customer bookings/receipts during browser verification.
