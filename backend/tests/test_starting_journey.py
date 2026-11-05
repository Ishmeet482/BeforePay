from unittest.mock import Mock

import pymupdf
from fastapi import HTTPException
from test_drafts import empty, metadata

from app.drafts.provider import ProviderResult, get_extractor
from app.drafts.schemas import Extraction
from app.main import app


def test_create_sources_generate_explicitly_and_open_unconfirmed_review(api):
    fake = Mock()
    app.dependency_overrides[get_extractor] = lambda: fake
    initial_ids = {b["id"] for b in api.get("/api/bookings?limit=100").json()}
    booking_response = api.post(
        "/api/bookings", json={"title": "Isolated UI starting flow"}
    )
    assert booking_response.status_code == 201
    booking = booking_response.json()["id"]
    base = f"/api/bookings/{booking}"
    original = "  Confirmed quotation\nCamera quantity 1\n"
    quotation = api.post(
        base + "/sources/text",
        json={"source_type": "quotation", "original_text": original},
    ).json()
    assert quotation["original_text"] == original
    message = api.post(
        base + "/sources/text",
        json={"source_type": "message", "original_text": "Original supporting message"},
    ).json()
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Camera quantity 2")
        binary = pdf.tobytes()
    uploaded = api.post(
        base + "/sources/pdf",
        data={"source_type": "quotation"},
        files={"file": ("synthetic.pdf", binary, "application/pdf")},
    )
    assert uploaded.status_code == 201
    pdf_source = uploaded.json()
    assert pdf_source["pages"][0]["page_number"] == 1
    assert "Camera quantity 2" in pdf_source["pages"][0]["original_text"]
    assert len(api.get(base + "/sources").json()) == 3
    assert api.get(base + "/drafts").json() == []
    assert api.get(base + "/review").json()["agreement_id"] is None
    fake.extract.assert_not_called()

    def mocked_extraction(sources):
        assert {s["source_id"] for s in sources} == {quotation["id"], pdf_source["id"]}
        data = empty()
        for source in sources:
            is_pdf = source["medium"] == "pdf"
            quantity = 2 if is_pdf else 1
            data["equipment"].append(
                {
                    "name": "Camera",
                    "quantity": quantity,
                    "ambiguous": True,
                    "citations": [
                        {
                            "source_id": source["source_id"],
                            "quotation": f"Camera quantity {quantity}",
                            "page_number": 1 if is_pdf else None,
                        }
                    ],
                }
            )
        return ProviderResult(Extraction.model_validate(data), metadata())

    fake.extract.side_effect = mocked_extraction
    generated = api.post(
        base + "/drafts", json={"source_ids": [quotation["id"], pdf_source["id"]]}
    )
    assert generated.status_code == 201
    draft = generated.json()
    assert message["id"] not in draft["input_source_ids"]
    assert draft["status"] == "draft" and draft["content"]["needs_clarification"]
    assert api.get(base + f"/drafts/{draft['id']}").json() == draft
    assert (
        api.get(base + "/agreements").json() == []
    )  # Generation does not import/confirm.
    opened = api.post(
        base + "/agreements/from-draft",
        json={"draft_id": draft["id"], "customer_label": "Synthetic reviewer"},
    )
    assert opened.status_code == 201
    agreement = opened.json()
    assert agreement["draft_id"] == draft["id"]
    review = api.get(base + "/review").json()
    assert review["agreement_id"] == agreement["id"]
    assert review["requires_review"] and not review["confirmation_current"]
    assert "unreviewed_evidence" in review["blockers"]
    assert (
        api.post(
            base + f"/agreements/{agreement['id']}/confirmations",
            json={
                "expected_fingerprint": agreement["fingerprint"],
                "customer_label": "Synthetic reviewer",
                "acknowledged": True,
            },
        ).status_code
        == 409
    )
    fake.extract.assert_called_once()
    assert (
        api.get(base + "/sources/" + quotation["id"]).json()["original_text"]
        == original
    )
    # A new booking can push an existing record beyond the first page when the
    # session-scoped test database contains more than 100 bookings.
    remaining_ids = set()
    offset = 0
    while True:
        page = api.get(f"/api/bookings?limit=100&offset={offset}").json()
        remaining_ids.update(b["id"] for b in page)
        if len(page) < 100:
            break
        offset += 100
    assert initial_ids <= remaining_ids


def test_failed_generation_keeps_saved_evidence_and_no_fabricated_draft(api):
    fake = Mock()
    fake.extract.side_effect = HTTPException(
        503, {"code": "ai_rate_limited", "message": "Mock quota exhausted"}
    )
    app.dependency_overrides[get_extractor] = lambda: fake
    booking = api.post(
        "/api/bookings", json={"title": "Isolated failed draft flow"}
    ).json()["id"]
    base = f"/api/bookings/{booking}"
    source = api.post(
        base + "/sources/text",
        json={"source_type": "message", "original_text": "Camera quantity 1"},
    ).json()
    fake.extract.assert_not_called()
    response = api.post(base + "/drafts", json={"source_ids": [source["id"]]})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_rate_limited"
    assert api.get(base + "/drafts").json() == []
    assert api.get(base + "/agreements").json() == []
    assert (
        api.get(base + "/sources/" + source["id"]).json()["original_text"]
        == "Camera quantity 1"
    )
    fake.extract.assert_called_once()
