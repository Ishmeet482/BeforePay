# Merchant replies — synthetic UI captures

Mocked APIs only; no development records or provider calls. Desktop 1440×1000,
tablet 834×1112 and mobile 390×844 viewport emulation. Images capture complete
page content, so image height exceeds viewport height. Captured amounts and terms
are synthetic fixture values, not evidence of a real payment or agreement.

| View | Desktop | Tablet | Mobile |
| --- | --- | --- | --- |
| Merchant: question, both supporting terms, append-only replies and reply form | [Desktop](merchant-desktop.png) | [Tablet](merchant-tablet.png) | [Mobile](merchant-mobile.png) |
| Buyer: unchanged blocking discrepancy and shared read-only responses | [Desktop](buyer-desktop.png) | [Tablet](buyer-tablet.png) | [Mobile](buyer-mobile.png) |
| Historical question: retained draft with submission blocked | — | — | [Mobile](historical-mobile.png) |

Reviewed for wrapping, predictable evidence controls, labelled inputs, visible
provisional/unverified notices and responsive support/history layout. These are
frontend fixtures; real persistence/version/immutable-trigger checks run separately
against disposable PostgreSQL. See [verification and precise UI steps](../../merchant-replies.md).
