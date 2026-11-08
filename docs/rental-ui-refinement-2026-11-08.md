# Rental setup, cancellation alignment and BP mark — 8 November 2026

Focused frontend refinement; no backend production changes, database migration,
existing-record/configuration changes or live Gemini/PayPal calls. Screenshots
below use isolated synthetic browser fixtures, including all amounts and receipts.
They are not new hosted verification or payment evidence.

## Camera-only investigation and rental categories

The booking endpoint stores only title and session owner. It creates no sources,
drafts, equipment, included items or payment records. Source intake starts empty;
equipment names in extraction/review are unrestricted. Camera-centric material
comes from the old title placeholder, the authored camera quotation/message in
the demo catalogue, camera-based documentation examples and isolated browser
fixtures (some explicitly include batteries/microphones). There is no production
creation default that adds those items. No hosted booking/source records were
read here, so a particular reported booking's source provenance was not audited.

Creation now offers Camera & photography, Audio equipment, Lighting equipment,
Projectors & presentation equipment and Other / custom equipment. This is an
optional, labelled **setup guide**, not a stored category or equipment restriction.
It changes the title placeholder only; it never changes an entered title, creates
items, saves evidence, invents prices/policies or invokes AI. The descriptive title
is persisted through the unchanged `{title}` API. Category choice resets after
creation/sign-out and is not retained as booking metadata after browser reload.
Persisting separate searchable category metadata would need a separately scoped
data-model change; it is not necessary for this naming/source-intake improvement.

Actual equipment and custom item names still come from explicitly saved sources,
validated source-linked extraction and reasoned human revisions. Changing a setup
guide cannot override them. Existing bookings/versions/receipts require no rewrite.

In **Sources & draft**, original evidence intake comes first. **Optional synthetic
camera example** explicitly reads the existing `/api/demo-templates` catalogue and
loads the chosen quotation/message into the form only. Nothing is saved, selected
for extraction, generated or approved automatically. Replacing unsaved input
requires confirmation. Saving and AI generation remain separate explicit steps.
The catalogue must already exist; an unavailable/empty catalogue reports an error,
without inventing substitute sample terms. No templates were seeded by this task.

## Layout and brand changes

- Calculator inputs and results now have matching card boundaries, internal
  headings and top alignment on desktop. Empty/loading/error/blocked states retain
  an honest result area. Two previews expand naturally inside it. Tablet/mobile
  stack input then result in DOM/visual order; a successful request still focuses
  its result. No fixed card heights or refund-calculation changes were introduced.
- Policy source labels and status indicators wrap with a consistent gap. Shared
  toolbar buttons align with heading tops; form columns have explicit minimum
  width/wrapping. Existing booking tables, evidence drawers, agreement summaries,
  comparison, checkout/history and merchant workspaces were audited rather than
  broadly redesigned. Warm surfaces, teal Buyer and indigo Merchant accents remain.
- An original **437-byte SVG** BP monogram replaces the lowercase text tile. B's
  two bowls and P's single bowl use matching strokes and baselines within a teal
  square. One shared component pairs it with the existing wordmark in navigation
  and receipts; the same asset serves as favicon. Paired images are decorative to
  assistive technology because the adjacent wordmark names BeforePay; standalone
  SVG has its own title. Checked at 16/24/32 px, in mobile headers and printed receipt.
- Removed only obsolete lowercase-tile typography/background styling. No assets,
  dependency/lockfiles, migrations or audit documentation were deleted.

The supplied Adobe references informed simple letter/shape composition and testing
at small sizes/in context, not copied artwork: [monogram tutorial](https://www.adobe.com/learn/illustrator/web/create-monogram),
[logo principles](https://www.adobe.com/express/learn/blog/how-to-design-a-logo).

## Verification

- `cd frontend && npm run build`: TypeScript and production build passed using
  Node 22.23.1, existing Vite 7.3.7 and frozen existing dependencies; no install or
  dependency change. Static branding check passed separately.
- Eight mocked browser suites passed: rental refinements, booking entry, alignment,
  redesign, Buyer/Merchant workspaces, role themes, PayPal SDK approval handling and
  connected blocker journey. The expanded refinement suite subsequently passed
  **48 checks**, including all five creation categories, keyboard focus, custom
  title preservation, no implicit writes, sample/discard behaviour, four saved
  non-camera agreements, desktop/tablet/mobile calculator states, role layouts,
  favicon and receipt printing. A QA harness navigation-dialog stall was corrected
  and rerun with a fresh disposable browser profile; no product guard was removed.
- `cd backend && uv run --frozen --offline pytest -q -x --tb=short
  tests/test_non_camera_bookings.py tests/test_bookings_evidence.py`:
  **34 passed**, six existing dependency warnings. Tests create/migrate/drop only
  disposable PostgreSQL; extraction responses are mocked. New audio/lighting/
  projector/custom bookings start without terms and retain exact source-backed
  equipment without camera accessories, inferred prices or approvals.
- Ruff lint/format for the new Python test, JS syntax, SVG structure and whitespace
  checked. A generated synthetic receipt PDF was rendered and inspected: one page,
  BP/BeforePay branding, original fixture amount/references and no invented items.
- Before/after screenshots inspected at 1440×1000, 820×1180 and 390×844; existing
  role tests additionally cover 320 px. Screens include bookings/creation, overview,
  sources, agreement, comparison, cancellation, checkout, receipt/history and
  merchant overview/reference/proposal/replies/rules/payment. These are mocked,
  offline checks, not hosted/provider certification or a screen-reader audit.

Reproduce with the environment-free QA server and isolated Chrome CDP from the
[browser guide](blocker-navigation.md#isolated-browser-verification):

```sh
cd frontend
node tests/all-browser.mjs rental-refinements.browser.mjs booking-entry.browser.mjs \
  alignment.browser.mjs redesign.browser.mjs workspaces.browser.mjs \
  role-themes.browser.mjs paypal-approval.browser.mjs blocker-journey.browser.mjs
node tests/branding.mjs
```

No hosted/payment/AI setting or behaviour was enabled by these changes. Session
ownership, CSRF/origins, quota admission, citations, correction reasons, separate
approvals, stale-version checks, Python money calculations and verified sandbox
capture/immutable receipt protections remain in their existing services.

## Synthetic screenshots

All images below are fixtures, not evidence of a real payment. The before image
shows the 55 px desktop gap between input-card top and refund article; the after
image places the result heading inside its own aligned card.

| Screen | Capture |
| --- | --- |
| Before: cancellation desktop | [Image](screenshots/rental-refinement-2026-11-08/cancellation-before-desktop.png) |
| After: cancellation desktop | [Image](screenshots/rental-refinement-2026-11-08/cancellation-after-desktop.png) |
| After: cancellation mobile | [Image](screenshots/rental-refinement-2026-11-08/cancellation-after-mobile.png) |
| Custom booking mobile | [Image](screenshots/rental-refinement-2026-11-08/custom-booking-mobile.png) |
| Saved audio agreement | [Image](screenshots/rental-refinement-2026-11-08/audio-agreement-desktop.png) |
| Monogram at small sizes | [Image](screenshots/rental-refinement-2026-11-08/monogram-sizes.png) |
| Printed fixture receipt | [Image](screenshots/rental-refinement-2026-11-08/receipt-print.png) |
