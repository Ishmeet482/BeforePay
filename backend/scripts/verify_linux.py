"""Offline smoke executed inside the temporary Linux dependency-check container."""

import importlib.metadata
import json
import platform
import sys
from pathlib import Path

import psycopg
import pymupdf
from google import genai

sys.path.insert(0, "/workspace")


def forbidden(*args, **kwargs):
    raise AssertionError("Provider calls forbidden in packaging smoke")


genai.Client = forbidden
from app.core.config import Settings  # noqa: E402
from app.main import app  # noqa: E402

settings = Settings(_env_file=None, gemini_api_key=None)
assert settings.public_demo_mode is False
assert "/api/demo-sessions" in app.openapi()["paths"]
with pymupdf.open() as document:
    page = document.new_page()
    page.insert_text((72, 72), "SYNTHETIC Linux PDF smoke")
    data = document.tobytes()
with pymupdf.open(stream=data, filetype="pdf") as document:
    assert "SYNTHETIC Linux PDF smoke" in document[0].get_text()
packages = [
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "psycopg",
    "psycopg-binary",
    "pymupdf",
    "google-genai",
    "httpx",
]
site = Path(importlib.metadata.distribution("pymupdf").locate_file("")).resolve()
size = sum(path.stat().st_size for path in site.rglob("*") if path.is_file())
print(
    json.dumps(
        {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "psycopg_impl": psycopg.pq.__impl__,
            "packages": {p: importlib.metadata.version(p) for p in packages},
            "site_packages_bytes": size,
            "native_pdf_and_app_import": "passed",
            "database_or_provider_calls": 0,
        },
        sort_keys=True,
    )
)
