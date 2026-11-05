from uuid import uuid4

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bookings.models import Booking
from app.evidence.limits import MAX_FILE_BYTES, MAX_REQUEST_BYTES, MAX_TEXT_LENGTH
from app.evidence.models import EvidenceSource


def make_pdf(
    texts=("Camera with two batteries", "Return Monday 10:00"), encrypted=False
):
    with pymupdf.open() as document:
        for value in texts:
            page = document.new_page()
            if value:
                page.insert_text((72, 72), value)
        options = {}
        if encrypted:
            options = {
                "encryption": pymupdf.PDF_ENCRYPT_AES_256,
                "owner_pw": "owner",
                "user_pw": "" if encrypted == "owner_only" else "reader",
            }
        return document.tobytes(**options)


@pytest.fixture
def booking_id(api):
    response = api.post("/api/bookings", json={"title": "Camera and AV rental"})
    assert response.status_code == 201
    return response.json()["id"]


def test_booking_persists_across_sessions(api, postgres_engine, booking_id):
    # An independent connection verifies the endpoint committed, not just flushed.
    with Session(postgres_engine) as session:
        booking = session.get(Booking, booking_id)
        assert booking.title == "Camera and AV rental"
    assert api.get(f"/api/bookings/{booking_id}").json()["id"] == booking_id
    listing = api.get("/api/bookings?limit=100").json()
    assert any(item["id"] == booking_id for item in listing)
    assert len(api.get("/api/bookings?limit=1").json()) == 1
    assert api.get("/api/bookings?limit=101").status_code == 422


@pytest.mark.parametrize("title", ["", "   ", "x" * 201, "bad\x00title"])
def test_invalid_booking(api, title):
    assert api.post("/api/bookings", json={"title": title}).status_code == 422


def test_missing_booking_and_bad_uuid(api):
    assert api.get(f"/api/bookings/{uuid4()}").status_code == 404
    assert api.get("/api/bookings/not-a-uuid").status_code == 422
    assert api.get(f"/api/bookings/{uuid4()}/sources").status_code == 404


@pytest.mark.parametrize("source_type", ["quotation", "message"])
def test_original_text_and_source_retrieval(
    api, postgres_engine, booking_id, source_type
):
    original = "  Camera + 2 batteries\r\nMicrophone included.\n₹200\n "
    path = f"/api/bookings/{booking_id}/sources"
    response = api.post(
        path + "/text", json={"source_type": source_type, "original_text": original}
    )
    assert response.status_code == 201
    source = response.json()
    assert source["original_text"] == original
    assert source["source_type"] == source_type
    assert source["medium"] == "pasted_text"
    assert source["filename"] is None and source["pages"] == []
    with Session(postgres_engine) as session:
        assert session.get(EvidenceSource, source["id"]).original_text == original
    assert api.get(path + "/" + source["id"]).json() == source
    assert any(item["id"] == source["id"] for item in api.get(path).json())
    other = api.post("/api/bookings", json={"title": "Other booking"}).json()["id"]
    assert api.get(f"/api/bookings/{other}/sources/{source['id']}").status_code == 404
    assert api.get(path + f"/{uuid4()}").status_code == 404


@pytest.mark.parametrize("text", ["", "  ", "bad\x00text", "x" * (MAX_TEXT_LENGTH + 1)])
def test_invalid_text(api, booking_id, text):
    path = f"/api/bookings/{booking_id}/sources/text"
    assert (
        api.post(
            path, json={"source_type": "message", "original_text": text}
        ).status_code
        == 422
    )


def test_text_boundary_and_invalid_type(api, booking_id):
    path = f"/api/bookings/{booking_id}/sources/text"
    assert (
        api.post(
            path,
            json={"source_type": "message", "original_text": "x" * MAX_TEXT_LENGTH},
        ).status_code
        == 201
    )
    assert (
        api.post(
            path, json={"source_type": "invented", "original_text": "text"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            f"/api/bookings/{uuid4()}/sources/text",
            json={"source_type": "message", "original_text": "text"},
        ).status_code
        == 404
    )


def test_pdf_pages_persist(api, postgres_engine, booking_id):
    data = make_pdf()
    path = f"/api/bookings/{booking_id}/sources"
    response = api.post(
        path + "/pdf",
        data={"source_type": "quotation"},
        files={"file": ("quote.pdf", data, "application/pdf")},
    )
    assert response.status_code == 201
    source = response.json()
    assert source["filename"] == "quote.pdf" and source["medium"] == "pdf"
    with pymupdf.open(stream=data, filetype="pdf") as document:
        expected = [page.get_text("text") for page in document]
    assert source["pages"] == [
        {"page_number": i + 1, "original_text": value}
        for i, value in enumerate(expected)
    ]
    assert source["original_text"] == "".join(expected)
    with Session(postgres_engine) as session:
        stored = session.get(EvidenceSource, source["id"])
        assert [p.original_text for p in stored.pages] == expected
    assert api.get(path + "/" + source["id"]).json() == source


@pytest.mark.parametrize(
    "filename,mime,data,status,code",
    [
        ("bad.txt", "application/pdf", b"bad", 415, "invalid_filename"),
        ("../quote.pdf", "application/pdf", b"bad", 415, "invalid_filename"),
        ("quote.pdf", "text/plain", b"bad", 415, "unsupported_media_type"),
        ("quote.pdf", "application/pdf", b"", 422, "unreadable_pdf"),
        ("quote.pdf", "application/pdf", b"not PDF", 422, "unreadable_pdf"),
        ("quote.pdf", "application/pdf", b"%PDF-broken", 422, "unreadable_pdf"),
        (
            "quote.pdf",
            "application/pdf",
            b"%PDF-" + b"x" * MAX_FILE_BYTES,
            413,
            "file_too_large",
        ),
    ],
)
def test_upload_rejected_without_persisting(
    api, postgres_engine, booking_id, filename, mime, data, status, code
):
    response = api.post(
        f"/api/bookings/{booking_id}/sources/pdf",
        data={"source_type": "quotation"},
        files={"file": (filename, data, mime)},
    )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(EvidenceSource)
                .where(EvidenceSource.booking_id == booking_id)
            )
            == 0
        )


@pytest.mark.parametrize(
    "kind", ["encrypted", "owner_only", "blank", "scanned", "mixed", "pages", "text"]
)
def test_pdf_content_validation(api, booking_id, kind):
    if kind in {"encrypted", "owner_only"}:
        data, code, status = make_pdf(encrypted=kind), "encrypted_pdf", 422
    elif kind == "blank":
        data, code, status = make_pdf(("",)), "pdf_ocr_required", 422
    elif kind in {"scanned", "mixed"}:
        with pymupdf.open() as document:
            if kind == "mixed":
                document.new_page().insert_text((72, 72), "Quotation")
            page = document.new_page()
            pixel = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2, 2), False)
            pixel.clear_with(100)
            page.insert_image(page.rect, stream=pixel.tobytes("png"))
            data = document.tobytes()
        code, status = "pdf_ocr_required", 422
    elif kind == "pages":
        data, code, status = make_pdf(["Camera"] * 101), "too_many_pages", 413
    else:
        with pymupdf.open() as document:
            for _ in range(60):
                page = document.new_page()
                for line in range(40):
                    page.insert_text((20, 20 + line * 15), "Camera " * 8)
            data = document.tobytes()
        code, status = "text_too_long", 413
    response = api.post(
        f"/api/bookings/{booking_id}/sources/pdf",
        data={"source_type": "quotation"},
        files={"file": ("quote.pdf", data, "application/pdf")},
    )
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code


def test_multipart_validation(api, booking_id):
    path = f"/api/bookings/{booking_id}/sources/pdf"
    assert api.post(path, data={"source_type": "quotation"}).status_code == 422
    assert (
        api.post(
            path,
            data={"source_type": "unknown"},
            files={"file": ("quote.pdf", make_pdf(), "application/pdf")},
        ).status_code
        == 422
    )
    assert (
        api.post(
            f"/api/bookings/{uuid4()}/sources/pdf",
            data={"source_type": "quotation"},
            files={"file": ("quote.pdf", make_pdf(), "application/pdf")},
        ).status_code
        == 404
    )


def test_request_limit_without_content_length(api):
    def chunks():
        for _ in range(6):
            yield b"x" * (MAX_REQUEST_BYTES // 5)

    response = api.post(
        "/api/bookings", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
