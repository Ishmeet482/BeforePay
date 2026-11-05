import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pymupdf
import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.agreements.models import AgreementConfirmation, AgreementVersion
from app.agreements.service import require_current_confirmation
from app.bookings.models import Booking
from app.drafts.models import DraftVersion
from app.drafts.provider import ProviderResult, get_extractor
from app.drafts.schemas import Extraction, ModelMetadata
from app.drafts.service import fingerprint, validate_and_classify
from app.main import app

TEXT = (
    "Camera quantity 1. Included Battery quantity 2.\n"
    "Pickup 2026-11-01T09:00:00 UTC. Return 2026-11-03T10:00:00 UTC.\n"
    "Rental total USD 200.00. Deposit USD 50.00 refundable on undamaged return.\n"
    "Cancel at least 48 hours before pickup for full refund."
)


def seed_review(api, engine, transform=None, extra_text="", begin=True):
    booking = api.post(
        "/api/bookings", json={"title": "Synthetic customer review"}
    ).json()["id"]
    source = api.post(
        f"/api/bookings/{booking}/sources/text",
        json={"source_type": "quotation", "original_text": TEXT + extra_text},
    ).json()
    sid = source["id"]

    def cited(quote):
        return {
            "ambiguous": False,
            "citations": [{"source_id": sid, "quotation": quote, "page_number": None}],
        }

    data = {
        "equipment": [{**cited("Camera quantity 1"), "name": "Camera", "quantity": 1}],
        "pickup": [
            {
                **cited("Pickup 2026-11-01T09:00:00 UTC"),
                "value": {"local_datetime": "2026-11-01T09:00:00", "timezone": "UTC"},
            }
        ],
        "return_time": [
            {
                **cited("Return 2026-11-03T10:00:00 UTC"),
                "value": {"local_datetime": "2026-11-03T10:00:00", "timezone": "UTC"},
            }
        ],
        "currency": [{**cited("USD 200.00"), "value": "USD"}],
        "amounts": [
            {
                **cited("Rental total USD 200.00"),
                "kind": "rental_total",
                "label": "Rental total",
                "amount": "200.00",
                "currency": "USD",
            }
        ],
        "deposit_conditions": [
            {
                **cited("Deposit USD 50.00 refundable on undamaged return."),
                "value": "Deposit USD 50.00 refundable on undamaged return.",
            }
        ],
        "cancellation_conditions": [
            {
                **cited("Cancel at least 48 hours before pickup for full refund."),
                "value": "Cancel at least 48 hours before pickup for full refund.",
            }
        ],
        "included_items": [
            {**cited("Included Battery quantity 2"), "name": "Battery", "quantity": 2}
        ],
    }
    if transform:
        transform(data)
    extraction = Extraction.model_validate(data)
    snapshot = {
        "source_id": sid,
        "source_type": "quotation",
        "medium": "pasted_text",
        "filename": None,
        "text": source["original_text"],
        "pages": [],
    }
    metadata = ModelMetadata(
        provider="gemini",
        requested_model="offline",
        response_model="offline",
        response_id="mock-review",
        sdk_version="offline",
        prompt_version="offline",
        input_tokens=None,
        output_tokens=None,
    )
    with Session(engine) as session:
        draft = DraftVersion(
            booking_id=UUID(booking),
            version=1,
            status="draft",
            input_source_ids=[sid],
            source_fingerprints={sid: fingerprint(snapshot)},
            content=validate_and_classify(extraction, [snapshot]).model_dump(
                mode="json"
            ),
            model_metadata=metadata.model_dump(),
        )
        session.add(draft)
        session.commit()
        draft_id = str(draft.id)
    original = api.get(f"/api/bookings/{booking}/drafts/{draft_id}").json()
    if not begin:
        return {"booking": booking, "source": source, "draft": original}
    response = api.post(
        f"/api/bookings/{booking}/agreements/from-draft",
        json={"draft_id": draft_id, "customer_label": "local customer"},
    )
    assert response.status_code == 201, response.text
    return {
        "booking": booking,
        "source": source,
        "draft": original,
        "agreement": response.json(),
        "extraction": extraction,
        "metadata": metadata,
    }


@pytest.fixture
def reviewed(api, postgres_engine):
    return seed_review(api, postgres_engine)


def confirm(api, context, agreement=None, **overrides):
    agreement = agreement or context["agreement"]
    return api.post(
        f"/api/bookings/{context['booking']}/agreements/{agreement['id']}/confirmations",
        json={
            "expected_fingerprint": agreement["fingerprint"],
            "customer_label": "local customer",
            "acknowledged": True,
            **overrides,
        },
    )


def revise(api, context, changes=None, agreement=None, **overrides):
    agreement = agreement or context["agreement"]
    return api.post(
        f"/api/bookings/{context['booking']}/agreements/{agreement['id']}/revisions",
        json={
            "expected_fingerprint": agreement["fingerprint"],
            "customer_label": "local customer",
            "review_reason": "Reviewed current evidence and negotiated details",
            "reviewed_source_ids": [context["source"]["id"]],
            "changes": changes or [],
            **overrides,
        },
    )


def equipment_change(quantity=2):
    return {
        "category": "equipment",
        "reason": "Customer explicitly corrects negotiated camera count",
        "items": [{"name": "Camera", "quantity": quantity, "ambiguous": False}],
    }


def state(api, context):
    result = api.get(f"/api/bookings/{context['booking']}/review")
    assert result.status_code == 200, result.text
    return result.json()


def test_complete_confirmation_is_separate_idempotent_and_current(
    api, reviewed, postgres_engine
):
    agreement = copy.deepcopy(reviewed["agreement"])
    assert state(api, reviewed)["blockers"] == []
    assert state(api, reviewed)["requires_review"] is True
    response = confirm(api, reviewed)
    assert response.status_code == 201, response.text
    assert response.json()["reviewed_fingerprint"] == agreement["fingerprint"]
    assert response.json()["agreement_id"] == agreement["id"]
    duplicate = confirm(api, reviewed)
    assert duplicate.status_code == 200 and duplicate.json() == response.json()
    current = state(api, reviewed)
    assert current["confirmation_current"] is True
    assert current["requires_review"] is False
    assert current["identity_provisional"] is True
    assert (
        api.get(
            f"/api/bookings/{reviewed['booking']}/agreements/{agreement['id']}"
        ).json()
        == agreement
    )
    with Session(postgres_engine) as session:
        session.info["demo_session_id"] = session.get(
            Booking, UUID(reviewed["booking"])
        ).owner_session_id
        record = require_current_confirmation(session, UUID(reviewed["booking"]))
        assert str(record.id) == response.json()["id"]
        assert (
            session.scalar(
                select(func.count())
                .select_from(AgreementConfirmation)
                .where(AgreementConfirmation.agreement_id == agreement["id"])
            )
            == 1
        )


def test_correction_versions_preserve_ai_and_reason_provenance(
    api, reviewed, postgres_engine
):
    assert confirm(api, reviewed).status_code == 201
    response = revise(api, reviewed, [equipment_change()])
    assert response.status_code == 201, response.text
    revised = response.json()
    assert (
        revised["version"] == 2 and revised["parent_id"] == reviewed["agreement"]["id"]
    )
    assert revised["fingerprint"] != reviewed["agreement"]["fingerprint"]
    corrected = revised["content"]["extraction"]["equipment"][0]
    assert corrected["origin"] == "customer_entered"
    assert corrected["claim"]["quantity"] == 2 and corrected["claim"]["citations"] == []
    assert corrected["reason"] == equipment_change()["reason"]
    assert (
        revised["content"]["extraction"]["currency"][0]["origin"] == "source_supported"
    )
    assert revised["audit"]["identity_provisional"] is True
    assert revised["audit"]["changes"][0]["reason"] == corrected["reason"]
    assert state(api, reviewed)["confirmation_current"] is False
    assert (
        api.get(
            f"/api/bookings/{reviewed['booking']}/drafts/{reviewed['draft']['id']}"
        ).json()
        == reviewed["draft"]
    )
    assert (
        api.get(
            f"/api/bookings/{reviewed['booking']}/sources/{reviewed['source']['id']}"
        ).json()
        == reviewed["source"]
    )
    with Session(postgres_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AgreementConfirmation)
                .where(AgreementConfirmation.booking_id == reviewed["booking"])
            )
            == 1
        )
    assert confirm(api, reviewed, revised).status_code == 201
    assert state(api, reviewed)["confirmation_current"] is True


@pytest.mark.parametrize("category", list(Extraction.model_fields))
def test_missing_required_categories_block_confirmation(api, postgres_engine, category):
    context = seed_review(
        api, postgres_engine, lambda data: data.__setitem__(category, [])
    )
    response = confirm(api, context)
    assert response.status_code == 409
    assert f"{category}_missing" in response.json()["detail"]["blockers"]


def test_conflicts_require_explicit_correction(api, postgres_engine):
    def conflict(data):
        claim = copy.deepcopy(data["equipment"][0])
        claim["quantity"] = 2
        claim["citations"][0]["quotation"] = "Camera quantity 2"
        data["equipment"].append(claim)

    context = seed_review(
        api, postgres_engine, conflict, "\nAlternative Camera quantity 2."
    )
    assert "equipment_unresolved" in confirm(api, context).json()["detail"]["blockers"]
    revised = revise(api, context, [equipment_change()]).json()
    assert confirm(api, context, revised).status_code == 201
    assert len(context["draft"]["content"]["extraction"]["equipment"]) == 2


def test_missing_rental_total_cannot_pass_with_other_amount(api, postgres_engine):
    context = seed_review(
        api, postgres_engine, lambda data: data["amounts"][0].update(kind="other")
    )
    assert "rental_total_missing" in confirm(api, context).json()["detail"]["blockers"]


def test_explicit_no_included_items_requires_reason_not_fake_evidence(api, reviewed):
    revised = revise(
        api,
        reviewed,
        [
            {
                "category": "included_items",
                "reason": "Customer confirms no additional items are included",
                "items": [],
                "explicit_none": True,
            }
        ],
    )
    assert revised.status_code == 201
    version = revised.json()
    assert version["content"]["explicit_none_categories"] == ["included_items"]
    assert confirm(api, reviewed, version).status_code == 201


@pytest.mark.parametrize("mode", ["fingerprint", "revision"])
def test_stale_confirmation_and_revision_rejected(api, reviewed, mode):
    if mode == "revision":
        assert revise(api, reviewed, [equipment_change()]).status_code == 201
    response = (
        confirm(api, reviewed, expected_fingerprint="0" * 64)
        if mode == "fingerprint"
        else confirm(api, reviewed)
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_agreement"
    assert revise(api, reviewed, expected_fingerprint="0" * 64).status_code == 409


@pytest.mark.parametrize("kind", ["text", "pdf"])
def test_added_evidence_invalidates_and_explicit_re_review_restores(
    api, reviewed, postgres_engine, kind
):
    confirmation = confirm(api, reviewed).json()
    path = f"/api/bookings/{reviewed['booking']}/sources"
    if kind == "text":
        extra = api.post(
            path + "/text",
            json={
                "source_type": "message",
                "original_text": "Customer repeats unchanged rental details.",
            },
        )
    else:
        with pymupdf.open() as doc:
            doc.new_page().insert_text(
                (72, 72), "Customer repeats unchanged rental details."
            )
            binary = doc.tobytes()
        extra = api.post(
            path + "/pdf",
            data={"source_type": "message"},
            files={"file": ("additional.pdf", binary, "application/pdf")},
        )
    assert extra.status_code == 201
    current = state(api, reviewed)
    assert current["confirmation_current"] is False
    assert "evidence_changed_requires_review" in current["blockers"]
    assert confirm(api, reviewed).status_code == 409
    assert revise(api, reviewed).status_code == 422
    with Session(postgres_engine) as session:
        assert session.get(AgreementConfirmation, confirmation["id"]) is not None
        session.info["demo_session_id"] = session.get(
            Booking, UUID(reviewed["booking"])
        ).owner_session_id
        with pytest.raises(Exception) as caught:
            require_current_confirmation(session, UUID(reviewed["booking"]))
        assert caught.value.status_code == 409
    refreshed = revise(
        api,
        reviewed,
        reviewed_source_ids=[reviewed["source"]["id"], extra.json()["id"]],
    )
    assert refreshed.status_code == 201, refreshed.text
    assert confirm(api, reviewed, refreshed.json()).status_code == 201


def test_new_ai_draft_requires_new_review_without_calling_ai(api, reviewed):
    from unittest.mock import Mock

    fake = Mock()
    fake.extract.return_value = ProviderResult(
        reviewed["extraction"], reviewed["metadata"]
    )
    app.dependency_overrides[get_extractor] = lambda: fake
    assert confirm(api, reviewed).status_code == 201
    result = api.post(
        f"/api/bookings/{reviewed['booking']}/drafts",
        json={"source_ids": [reviewed["source"]["id"]]},
    )
    assert result.status_code == 201
    assert "newer_ai_draft_requires_review" in state(api, reviewed)["blockers"]
    assert revise(api, reviewed).status_code == 409
    assert confirm(api, reviewed).status_code == 409
    imported = api.post(
        f"/api/bookings/{reviewed['booking']}/agreements/from-draft",
        json={"draft_id": result.json()["id"], "customer_label": "local customer"},
    )
    assert imported.status_code == 201
    assert state(api, reviewed)["confirmation_current"] is False
    assert confirm(api, reviewed, imported.json()).status_code == 201


@pytest.mark.parametrize(
    "invalid",
    [
        "reason",
        "label",
        "ack",
        "fake_citation",
        "float_money",
        "origin",
        "foreign_sources",
    ],
)
def test_explicit_corrections_and_customer_identity_inputs(api, reviewed, invalid):
    if invalid == "reason":
        change = equipment_change()
        change["reason"] = " "
        result = revise(api, reviewed, [change])
    elif invalid == "label":
        result = confirm(api, reviewed, customer_label=" ")
    elif invalid == "ack":
        result = confirm(api, reviewed, acknowledged=False)
    elif invalid == "fake_citation":
        change = equipment_change()
        change["items"][0]["citations"] = reviewed["draft"]["content"]["extraction"][
            "equipment"
        ][0]["citations"]
        result = revise(api, reviewed, [change])
    elif invalid == "float_money":
        result = revise(
            api,
            reviewed,
            [
                {
                    "category": "amounts",
                    "reason": "Customer corrects total",
                    "items": [
                        {
                            "kind": "rental_total",
                            "label": "Total",
                            "amount": 200.1,
                            "currency": "USD",
                            "ambiguous": False,
                        }
                    ],
                }
            ],
        )
    elif invalid == "origin":
        change = equipment_change()
        change["items"][0]["origin"] = "source_supported"
        result = revise(api, reviewed, [change])
    else:
        from uuid import uuid4

        result = revise(api, reviewed, reviewed_source_ids=[str(uuid4())])
    assert result.status_code == 422, result.text


@pytest.mark.parametrize(
    "local,zone,blocker",
    [
        ("2026-11-01T08:00:00", "UTC", "return_must_follow_pickup"),
        (
            "2026-11-01T01:30:00",
            "America/New_York",
            "rental_time_requires_clarification",
        ),
        (None, None, "return_time_unresolved"),
    ],
)
def test_incomplete_or_ambiguous_times_cannot_confirm(
    api, reviewed, local, zone, blocker
):
    response = revise(
        api,
        reviewed,
        [
            {
                "category": "return_time",
                "reason": "Customer provides revised return details",
                "items": [
                    {
                        "value": {"local_datetime": local, "timezone": zone},
                        "ambiguous": False,
                    }
                ],
            }
        ],
    )
    assert response.status_code == 201
    result = confirm(api, reviewed, response.json())
    assert result.status_code == 409 and blocker in result.json()["detail"]["blockers"]


@pytest.mark.parametrize(
    "model,mutation",
    [
        (AgreementVersion, "update"),
        (AgreementVersion, "delete"),
        (AgreementConfirmation, "update"),
        (AgreementConfirmation, "delete"),
    ],
)
def test_database_keeps_content_and_confirmation_history_immutable(
    api, reviewed, postgres_engine, model, mutation
):
    confirmation = confirm(api, reviewed).json()
    record_id = (
        reviewed["agreement"]["id"] if model is AgreementVersion else confirmation["id"]
    )
    if mutation == "delete":
        statement = delete(model)
    else:
        statement = update(model).values(
            **(
                {"content": {}}
                if model is AgreementVersion
                else {"customer_label": "changed"}
            )
        )
    with pytest.raises(DBAPIError, match="immutable"):
        with postgres_engine.begin() as connection:
            connection.execute(statement.where(model.id == record_id))


def race(first, second):
    barrier = Barrier(2)

    def execute(action):
        barrier.wait(timeout=5)
        return action()

    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(execute, [first, second]))


def test_concurrent_revisions_reject_stale_parent(api, reviewed):
    responses = race(
        lambda: revise(api, reviewed, [equipment_change(2)]),
        lambda: revise(api, reviewed, [equipment_change(3)]),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    versions = api.get(f"/api/bookings/{reviewed['booking']}/agreements").json()
    assert [version["version"] for version in versions] == [2, 1]


def test_concurrent_confirmation_and_revision_never_leave_stale_current_confirmation(
    api, reviewed
):
    confirmation, revision = race(
        lambda: confirm(api, reviewed),
        lambda: revise(api, reviewed, [equipment_change()]),
    )
    assert confirmation.status_code in {201, 409}
    assert revision.status_code == 201
    assert state(api, reviewed)["confirmation_current"] is False
    assert state(api, reviewed)["requires_review"] is True


def test_concurrent_confirmation_and_evidence_require_renewed_review(api, reviewed):
    confirmation, source = race(
        lambda: confirm(api, reviewed),
        lambda: api.post(
            f"/api/bookings/{reviewed['booking']}/sources/text",
            json={
                "source_type": "message",
                "original_text": "Additional customer message",
            },
        ),
    )
    assert confirmation.status_code in {201, 409}
    assert source.status_code == 201
    assert state(api, reviewed)["confirmation_current"] is False
    assert "evidence_changed_requires_review" in state(api, reviewed)["blockers"]


def test_concurrent_duplicate_confirmations_share_one_audit_record(api, reviewed):
    responses = race(lambda: confirm(api, reviewed), lambda: confirm(api, reviewed))
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]


def test_cross_booking_version_cannot_be_retrieved_or_confirmed(api, reviewed):
    other = api.post("/api/bookings", json={"title": "Other customer booking"}).json()[
        "id"
    ]
    path = f"/api/bookings/{other}/agreements/{reviewed['agreement']['id']}"
    assert api.get(path).status_code == 404
    assert (
        api.post(
            path + "/confirmations",
            json={
                "expected_fingerprint": reviewed["agreement"]["fingerprint"],
                "acknowledged": True,
                "customer_label": "local customer",
            },
        ).status_code
        == 404
    )


def test_import_does_not_silently_mark_unselected_evidence_reviewed(
    api, postgres_engine
):
    context = seed_review(api, postgres_engine, begin=False)
    api.post(
        f"/api/bookings/{context['booking']}/sources/text",
        json={
            "source_type": "message",
            "original_text": "Additional evidence not in extraction",
        },
    )
    result = api.post(
        f"/api/bookings/{context['booking']}/agreements/from-draft",
        json={"draft_id": context["draft"]["id"], "customer_label": "local customer"},
    )
    assert result.status_code == 201
    context["agreement"] = result.json()
    assert "unreviewed_evidence" in confirm(api, context).json()["detail"]["blockers"]


def test_duplicate_import_cannot_reset_customer_corrections(api, reviewed):
    revised = revise(api, reviewed, [equipment_change()]).json()
    result = api.post(
        f"/api/bookings/{reviewed['booking']}/agreements/from-draft",
        json={
            "draft_id": reviewed["draft"]["id"],
            "customer_label": "another local label",
        },
    )
    assert result.status_code == 409
    assert state(api, reviewed)["agreement_id"] == revised["id"]


def test_unknown_policy_placeholder_is_not_complete(api, reviewed):
    revised = revise(
        api,
        reviewed,
        [
            {
                "category": "cancellation_conditions",
                "reason": "Details still unavailable",
                "items": [{"value": "TBD", "ambiguous": False}],
            }
        ],
    )
    assert revised.status_code == 201
    result = confirm(api, reviewed, revised.json())
    assert result.status_code == 409
    assert "cancellation_conditions_unresolved" in result.json()["detail"]["blockers"]


def payable_changes(total="200.00"):
    return [
        {
            "category": "amounts",
            "reason": "Separate rental fee, deposit and inclusive total",
            "items": [
                {
                    "kind": kind,
                    "label": label,
                    "amount": amount,
                    "currency": "USD",
                    "ambiguous": False,
                }
                for kind, label, amount in [
                    ("rental_total", "Rental fee", "120.00"),
                    ("deposit", "Deposit", "80.00"),
                    ("total_payable", "Total payable", total),
                ]
            ],
        }
    ]


def test_revision_inclusive_total_preserves_original_and_requires_confirmation(
    api, reviewed
):
    old = copy.deepcopy(reviewed["agreement"])
    response = revise(api, reviewed, payable_changes())
    assert response.status_code == 201, response.text
    revised = response.json()
    entries = revised["content"]["extraction"]["amounts"]
    assert {e["claim"]["kind"]: e["claim"]["amount"] for e in entries} == {
        "rental_total": "120.00",
        "deposit": "80.00",
        "total_payable": "200.00",
    }
    assert all(
        e["origin"] == "customer_entered" and e["claim"]["citations"] == []
        for e in entries
    )
    current = state(api, reviewed)
    assert current["blockers"] == []
    assert current["confirmation_current"] is False
    path = f"/api/bookings/{reviewed['booking']}"
    assert api.get(f"{path}/agreements/{old['id']}").json() == old
    assert (
        api.get(f"{path}/drafts/{reviewed['draft']['id']}").json() == reviewed["draft"]
    )
    assert confirm(api, reviewed, revised).status_code == 201


@pytest.mark.parametrize("case", ["conflict", "missing_rental", "currency"])
def test_total_payable_does_not_bypass_review_blockers(api, reviewed, case):
    changes = payable_changes()
    items = changes[0]["items"]
    if case == "conflict":
        items.append(dict(items[-1], amount="210.00"))
        blocker = "amounts_unresolved"
    elif case == "missing_rental":
        items.pop(0)
        blocker = "rental_total_missing"
    else:
        items[-1]["currency"] = "EUR"
        blocker = "currency_mismatch"
    response = revise(api, reviewed, changes)
    assert response.status_code == 201, response.text
    confirmation = confirm(api, reviewed, response.json())
    assert confirmation.status_code == 409
    assert blocker in confirmation.json()["detail"]["blockers"]


def test_source_supported_total_payable_imports_without_amount_conflict(
    api, postgres_engine
):
    def amounts(data):
        sid = data["amounts"][0]["citations"][0]["source_id"]
        data["amounts"] = [
            {
                "kind": kind,
                "label": label,
                "amount": amount,
                "currency": "USD",
                "ambiguous": False,
                "citations": [
                    {"source_id": sid, "quotation": quote, "page_number": None}
                ],
            }
            for kind, label, amount, quote in [
                ("rental_total", "Rental fee", "120", "Rental fee USD 120"),
                ("deposit", "Deposit", "80", "Deposit USD 80"),
                ("total_payable", "Total payable", "200", "Total payable USD 200"),
            ]
        ]

    context = seed_review(
        api,
        postgres_engine,
        amounts,
        "\nRental fee USD 120. Deposit USD 80. Total payable USD 200.",
    )
    entries = context["agreement"]["content"]["extraction"]["amounts"]
    assert [e["claim"]["kind"] for e in entries] == [
        "rental_total",
        "deposit",
        "total_payable",
    ]
    assert all(e["origin"] == "source_supported" for e in entries)
    assert state(api, context)["blockers"] == []
    assert state(api, context)["confirmation_current"] is False


def test_complementary_policy_clauses_and_explicit_consolidation(api, postgres_engine):
    first = "Cancel at least 48 hours before pickup for full refund."
    second = "Late cancellation forfeits the deposit."

    def clauses(data):
        claim = copy.deepcopy(data["cancellation_conditions"][0])
        claim["value"] = second
        claim["citations"][0]["quotation"] = second
        data["cancellation_conditions"].append(claim)

    context = seed_review(api, postgres_engine, clauses, "\n" + second)
    assert "cancellation_conditions_unresolved" not in state(api, context)["blockers"]
    original = copy.deepcopy(context["agreement"])
    consolidated = first + "\n" + second
    revised = revise(
        api,
        context,
        [
            {
                "category": "cancellation_conditions",
                "reason": "Reviewed both complementary clauses; both remain applicable",
                "items": [{"value": consolidated, "ambiguous": False}],
            }
        ],
    )
    assert revised.status_code == 201
    entries = revised.json()["content"]["extraction"]["cancellation_conditions"]
    assert len(entries) == 1 and entries[0]["claim"]["value"] == consolidated
    assert entries[0]["origin"] == "customer_entered"
    assert state(api, context)["confirmation_current"] is False
    assert (
        api.get(
            f"/api/bookings/{context['booking']}/agreements/{original['id']}"
        ).json()
        == original
    )


@pytest.mark.parametrize("explicit_flag", [True, False])
def test_policy_conflicts_still_block_confirmation(api, postgres_engine, explicit_flag):
    def clauses(data):
        first = data["deposit_conditions"][0]
        first["value"] = "Refundable"
        first["citations"][0]["quotation"] = "Refundable"
        first["ambiguous"] = explicit_flag
        second = copy.deepcopy(first)
        second["value"] = (
            "Nonrefundable" if not explicit_flag else "Return subject to inspection"
        )
        second["citations"][0]["quotation"] = second["value"]
        data["deposit_conditions"].append(second)

    context = seed_review(
        api,
        postgres_engine,
        clauses,
        "\nRefundable. Nonrefundable. Return subject to inspection.",
    )
    response = confirm(api, context)
    assert response.status_code == 409
    assert "deposit_conditions_unresolved" in response.json()["detail"]["blockers"]
