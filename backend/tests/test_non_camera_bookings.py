"""Synthetic offline evidence; creation never supplies default equipment."""

from unittest.mock import Mock

import pytest
from test_drafts import empty, metadata

from app.drafts.provider import ProviderResult, get_extractor
from app.drafts.schemas import Extraction
from app.main import app


@pytest.mark.parametrize(
    "name",
    [
        "Wireless PA system",
        "LED lighting panel",
        "Laser projector",
        "Custom sculpture rig",
    ],
)
def test_non_camera_creation_and_source_backed_draft(api, name):
    response = api.post("/api/bookings", json={"title": f"{name} · conference"})
    assert response.status_code == 201
    booking = response.json()
    assert set(booking) == {"id", "title", "created_at"}  # Existing contract.
    base = f"/api/bookings/{booking['id']}"
    for suffix in ("/sources", "/drafts", "/agreements", "/merchant-bookings"):
        assert api.get(base + suffix).json() == []
    assert api.get(base + "/checkout/receipt").status_code == 404
    wording = f"{name} quantity 1"
    source = api.post(
        base + "/sources/text",
        json={
            "source_type": "quotation",
            "original_text": wording,
        },
    ).json()
    extraction = empty()
    extraction["equipment"] = [
        {
            "name": name,
            "quantity": 1,
            "ambiguous": False,
            "citations": [
                {"source_id": source["id"], "quotation": wording, "page_number": None}
            ],
        }
    ]
    fake = Mock()
    fake.extract.return_value = ProviderResult(
        Extraction.model_validate(extraction), metadata()
    )
    app.dependency_overrides[get_extractor] = lambda: fake
    draft = api.post(base + "/drafts", json={"source_ids": [source["id"]]})
    assert draft.status_code == 201, draft.text
    result = draft.json()["content"]
    assert result["extraction"]["equipment"][0]["name"] == name
    assert result["extraction"]["included_items"] == []
    assert result["extraction"]["amounts"] == []
    assert result["needs_clarification"]  # Missing policy/amounts remain missing.
    assert api.get(base + "/sources/" + source["id"]).json()["original_text"] == wording
    fake.extract.assert_called_once()
