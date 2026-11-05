# BeforePay alignment screenshots

Isolated synthetic data; no existing records or provider calls. Captured Chromium viewports: desktop 1440×1000, tablet 834×1112, mobile 390×844. These are actual rendered UI captures, not design mockups.

## Before and after

| Screen / viewport | Before | After |
| --- | --- | --- |
| landing-footer · desktop | [Before](before/landing-footer-desktop.png) | [After](after/landing-footer-desktop.png) |
| landing-footer · tablet | [Before](before/landing-footer-tablet.png) | [After](after/landing-footer-tablet.png) |
| landing-footer · mobile | [Before](before/landing-footer-mobile.png) | [After](after/landing-footer-mobile.png) |
| bookings · desktop | [Before](before/bookings-desktop.png) | [After](after/bookings-desktop.png) |
| bookings · tablet | [Before](before/bookings-tablet.png) | [After](after/bookings-tablet.png) |
| bookings · mobile | [Before](before/bookings-mobile.png) | [After](after/bookings-mobile.png) |
| agreement · desktop | [Before](before/agreement-desktop.png) | [After](after/agreement-desktop.png) |
| agreement · tablet | [Before](before/agreement-tablet.png) | [After](after/agreement-tablet.png) |
| agreement · mobile | [Before](before/agreement-mobile.png) | [After](after/agreement-mobile.png) |

The long agreement includes unknown quantity and an unconfirmed review state. Baseline and final fixtures differ in that synthetic confirmation flag; screenshots establish layout, not persisted state changes.

## Compact agreement and corrected workspaces

| Screen / state | Desktop | Tablet | Mobile |
| --- | --- | --- | --- |
| agreement-short | [View](after/agreement-short-desktop.png) | [View](after/agreement-short-tablet.png) | [View](after/agreement-short-mobile.png) |
| agreement-amounts | [View](after/agreement-amounts-desktop.png) | [View](after/agreement-amounts-tablet.png) | [View](after/agreement-amounts-mobile.png) |
| agreement-long-clauses | [View](after/agreement-long-clauses-desktop.png) | [View](after/agreement-long-clauses-tablet.png) | [View](after/agreement-long-clauses-mobile.png) |
| agreement-edited | [View](after/agreement-edited-desktop.png) | [View](after/agreement-edited-tablet.png) | [View](after/agreement-edited-mobile.png) |
| agreement-empty | [View](after/agreement-empty-desktop.png) | [View](after/agreement-empty-tablet.png) | [View](after/agreement-empty-mobile.png) |
| overview | [View](after/overview-desktop.png) | [View](after/overview-tablet.png) | [View](after/overview-mobile.png) |
| sources | [View](after/sources-desktop.png) | [View](after/sources-tablet.png) | [View](after/sources-mobile.png) |
| comparison | [View](after/comparison-desktop.png) | [View](after/comparison-tablet.png) | [View](after/comparison-mobile.png) |
| merchant | [View](after/merchant-desktop.png) | [View](after/merchant-tablet.png) | [View](after/merchant-mobile.png) |
| cancellation | [View](after/cancellation-desktop.png) | [View](after/cancellation-tablet.png) | [View](after/cancellation-mobile.png) |
| checkout | [View](after/checkout-desktop.png) | [View](after/checkout-tablet.png) | [View](after/checkout-mobile.png) |
| uncertain-actions | [View](after/uncertain-actions-desktop.png) | [View](after/uncertain-actions-tablet.png) | [View](after/uncertain-actions-mobile.png) |
| receipt | [View](after/receipt-desktop.png) | [View](after/receipt-tablet.png) | [View](after/receipt-mobile.png) |
| history | [View](after/history-desktop.png) | [View](after/history-tablet.png) | [View](after/history-mobile.png) |

## Receipt printing

[One-page synthetic A4 receipt PDF](receipt-print.pdf) · [Rendered print page](receipt-print.png).

The fixture has no captured itemisation. Only its recorded total is displayed. Payment history and current agreement context stay outside the printed receipt.

[Implementation, checks and limitations](../../alignment-refinement-2026-11-03.md).
