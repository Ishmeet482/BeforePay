from threading import Lock

import pymupdf
from fastapi import HTTPException, UploadFile

from app.evidence.limits import MAX_FILE_BYTES, MAX_PDF_PAGES, MAX_TEXT_LENGTH
from app.evidence.models import EvidencePage

# PyMuPDF does not support concurrent calls from multiple threads. Serialize
# extraction within each API process; no database transaction is held while parsing.
PDF_LOCK = Lock()


def reject(status: int, code: str, message: str) -> None:
    raise HTTPException(status, {"code": code, "message": message})


def extract_pdf(
    upload: UploadFile,
    *,
    max_file_bytes=MAX_FILE_BYTES,
    max_pages=MAX_PDF_PAGES,
    max_text=MAX_TEXT_LENGTH,
) -> tuple[str, str, list[EvidencePage]]:
    filename = upload.filename or ""
    if (
        not filename.lower().endswith(".pdf")
        or len(filename) > 255
        or any(char in filename for char in ("/", "\\", "\x00"))
    ):
        reject(415, "invalid_filename", "Use a PDF filename without directory paths.")
    if upload.content_type != "application/pdf":
        reject(415, "unsupported_media_type", "Upload must use application/pdf.")
    data = upload.file.read(max_file_bytes + 1)
    if len(data) > max_file_bytes:
        reject(
            413, "file_too_large", f"PDF exceeds the {max_file_bytes}-byte file limit."
        )
    if not data or not data.startswith(b"%PDF-"):
        reject(422, "unreadable_pdf", "Upload is not a readable PDF document.")
    with PDF_LOCK:
        try:
            with pymupdf.open(stream=data, filetype="pdf") as document:
                if (
                    document.needs_pass
                    or document.is_encrypted
                    or (document.metadata or {}).get("encryption")
                ):
                    reject(422, "encrypted_pdf", "Encrypted PDFs are not supported.")
                if document.page_count > max_pages:
                    reject(
                        413,
                        "too_many_pages",
                        f"PDF exceeds the {max_pages}-page limit.",
                    )
                pages = []
                total = 0
                for index, page in enumerate(document):
                    text = page.get_text("text")
                    if not text.strip() and page.get_images():
                        reject(
                            422,
                            "pdf_ocr_required",
                            f"Page {index + 1} has images but no text; OCR required.",
                        )
                    if "\x00" in text:
                        reject(
                            422, "invalid_pdf_text", "PDF text contains NUL characters."
                        )
                    total += len(text)
                    if total > max_text:
                        reject(
                            413,
                            "text_too_long",
                            f"PDF text exceeds {max_text} characters.",
                        )
                    pages.append(
                        EvidencePage(page_number=index + 1, original_text=text)
                    )
                original_text = "".join(page.original_text for page in pages)
                if not original_text.strip():
                    reject(
                        422,
                        "pdf_ocr_required",
                        "PDF has no extractable text; scanned PDFs require OCR.",
                    )
                return filename, original_text, pages
        except (RuntimeError, ValueError, pymupdf.FileDataError) as error:
            raise HTTPException(
                422,
                {"code": "unreadable_pdf", "message": "PDF could not be read."},
            ) from error
