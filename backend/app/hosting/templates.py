"""Authored synthetic source text. No AI output, approvals or payment fixtures."""

from app.admission.service import fingerprint

TEMPLATES = [
    {
        "key": "camera-quotation",
        "version": 1,
        "content": {
            "title": "SYNTHETIC · Camera rental quotation",
            "source_type": "quotation",
            "provenance": (
                "Synthetic example authored for demonstration; "
                "not an actual merchant quotation or AI output."
            ),
            "original_text": (
                "SYNTHETIC DEMO QUOTATION — not a real rental.\n"
                "Camera quantity 1. Included Battery quantity 2.\n"
                "Pickup 2026-11-15T09:00:00 UTC. Return 2026-11-17T09:00:00 UTC.\n"
                "Currency USD. Rental fee USD 120.00. Deposit USD 80.00. "
                "Inclusive total payable USD 200.00, including rental fee "
                "and deposit.\n"
                "The USD 80 deposit is refundable on undamaged return. "
                "On cancellation, "
                "the deposit is refunded according to the cancellation clauses.\n"
                "Cancellation at least 48 hours before pickup gives a full refund "
                "of rental fee USD 120 and deposit USD 80, total USD 200.\n"
                "Cancellation less than 48 hours before pickup refunds deposit USD 80 "
                "and retains rental fee USD 120."
            ),
        },
    },
    {
        "key": "camera-message",
        "version": 1,
        "content": {
            "title": "SYNTHETIC · Included items message",
            "source_type": "message",
            "provenance": "Synthetic supporting message, authored for demonstration.",
            "original_text": (
                "SYNTHETIC DEMO MESSAGE — not a real conversation. "
                "The quotation includes Battery quantity 2 with "
                "Camera quantity 1. Pickup and return use UTC "
                "as stated in the quotation."
            ),
        },
    },
]
for template in TEMPLATES:
    template["fingerprint"] = fingerprint(template)
TEMPLATE_DIGEST = fingerprint(TEMPLATES)
