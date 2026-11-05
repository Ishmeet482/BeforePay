from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_booking_comparisons import compare, content, save
from test_clarifications import discrepancy as discrepancy
from test_customer_review import state
from test_merchant_replies import question as question
from test_merchant_replies import reply

from app.bookings.router import lock_booking
from app.clarifications import corrections
from app.clarifications.models import CorrectionReview


def base(q):
    return f"/api/bookings/{q[0][0]['booking']}/clarifications/{q[1]['id']}"


@pytest.fixture
def corrected(api, question):
    assert reply(api, question).status_code == 201
    c, original, _ = question[0]
    proposal = save(api, c, expected=original["id"]).json()
    comparison = compare(api, c, proposal).json()
    ctx = api.get(base(question) + "/correction").json()
    assert ctx["eligible"], ctx
    return question, proposal, comparison, ctx


def payload(ctx, **changes):
    return {
        "bindings": ctx["bindings"],
        "context_fingerprint": ctx["context_fingerprint"],
        "reviewer_label": "Provisional buyer",
        "note": "Reviewed the corrected saved deposit terms and comparison.",
        **changes,
    }


def record(api, corrected, **changes):
    q, _, _, ctx = corrected
    return api.post(base(q) + "/correction-reviews", json=payload(ctx, **changes))


def test_exact_review_immutable_and_checkout_unchanged(api, corrected, postgres_engine):
    q, proposal, comparison, ctx = corrected
    c = q[0][0]
    original_state = state(api, c)
    route = f"/api/bookings/{c['booking']}/checkout"
    eligibility = api.get(route + "/eligibility").json()
    assert not eligibility["eligible"]
    first = record(api, corrected)
    assert first.status_code == 201, first.text
    data = first.json()
    assert not data["stale"] and data["identity_provisional"]
    assert data["context"]["bindings"] == ctx["bindings"]
    assert data["context"]["original"]["comparison"]["id"] == q[0][2]["id"]
    assert data["context"]["corrected_proposal"]["id"] == proposal["id"]
    assert data["context"]["comparison"]["id"] == comparison["id"]
    assert api.get(base(q) + "/correction-reviews").json() == [data]
    assert state(api, c) == original_state
    assert api.get(route + "/eligibility").json() == eligibility
    assert api.get(route + "/attempts").json() == []
    q[2].suggest.assert_not_called()
    for stmt in (
        update(CorrectionReview).values(note="overwrite"),
        delete(CorrectionReview),
    ):
        with Session(postgres_engine) as session:
            with pytest.raises(DBAPIError):
                session.execute(stmt.where(CorrectionReview.id == UUID(data["id"])))
            session.rollback()


def test_concurrent_duplicate_submissions_one_record(api, corrected):
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=5)
        return record(api, corrected)

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda _: run(), range(2)))
    assert [r.status_code for r in rows] == [201, 201]
    assert rows[0].json()["id"] == rows[1].json()["id"]
    assert len(api.get(base(corrected[0]) + "/correction-reviews").json()) == 1
    assert (
        record(
            api, corrected, note="Changed statement cannot replace original."
        ).status_code
        == 409
    )


@pytest.mark.parametrize("change", ["proposal", "comparison", "evidence"])
def test_history_outdated_and_retry_preserves_original(api, corrected, change):
    saved = record(api, corrected).json()
    q, proposal, _, _ = corrected
    c = q[0][0]
    if change == "proposal":
        assert save(api, c, expected=proposal["id"]).status_code == 201
    elif change == "comparison":
        assert compare(api, c, proposal).status_code == 201
    else:
        assert (
            api.post(
                f"/api/bookings/{c['booking']}/sources/text",
                json={
                    "source_type": "message",
                    "original_text": "New evidence requires renewed review.",
                },
            ).status_code
            == 201
        )
    history = api.get(base(q) + "/correction-reviews").json()
    assert len(history) == 1 and history[0]["stale"]
    assert (
        history[0]["context"] == saved["context"]
        and history[0]["note"] == saved["note"]
    )
    retry = record(api, corrected)
    assert retry.status_code == 409


@pytest.mark.parametrize(
    "field",
    [
        "comparison_id",
        "reply_id",
        "proposal_id",
        "agreement_id",
        "confirmation_id",
        "original_comparison_id",
    ],
)
def test_unrelated_or_incorrect_bindings_rejected(api, corrected, field):
    bindings = {**corrected[3]["bindings"], field: str(uuid4())}
    assert record(api, corrected, bindings=bindings).status_code in {404, 409}
    assert api.get(base(corrected[0]) + "/correction-reviews").json() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewer_label", "  "),
        ("note", ""),
        ("note", "\t\n"),
        ("note", "x" * 5001),
        ("note", "bad\x00text"),
    ],
)
def test_explicit_reviewer_and_note_required(api, corrected, field, value):
    assert record(api, corrected, **{field: value}).status_code == 422


def test_remaining_discrepancy_blocks_review(api, question):
    assert reply(api, question).status_code == 201
    c, original, _ = question[0]
    data = content(c)
    data["equipment"][0]["quantity"] = 2
    proposal = save(api, c, data, expected=original["id"]).json()
    assert compare(api, c, proposal).status_code == 201
    ctx = api.get(base(question) + "/correction").json()
    assert not ctx["eligible"] and "all_comparison_terms_must_match" in ctx["blockers"]
    assert (
        api.post(base(question) + "/correction-reviews", json=payload(ctx)).status_code
        == 409
    )


def test_missing_or_ambiguous_reply_and_old_proposal_blocked(api, question):
    assert (
        "saved_merchant_reply_required"
        in api.get(base(question) + "/correction").json()["blockers"]
    )
    assert reply(api, question).status_code == 201
    assert (
        "newer_merchant_proposal_and_comparison_required"
        in api.get(base(question) + "/correction").json()["blockers"]
    )
    assert (
        reply(
            api, question, response="Another separate merchant statement."
        ).status_code
        == 201
    )
    ctx = api.get(base(question) + "/correction").json()
    assert (
        "select_one_saved_merchant_reply" in ctx["blockers"] and ctx["bindings"] is None
    )
    chosen = api.get(
        base(question) + "/correction", params={"reply_id": ctx["replies"][0]["id"]}
    ).json()
    assert chosen["selected_reply_id"] == ctx["replies"][0]["id"]


def test_concurrent_proposal_change_before_lock_rejected(api, corrected, monkeypatch):
    entered, proceed = Event(), Event()

    def delayed(session, booking_id):
        entered.set()
        assert proceed.wait(timeout=5)
        return lock_booking(session, booking_id)

    monkeypatch.setattr(corrections, "lock_booking", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(record, api, corrected)
        assert entered.wait(timeout=5)
        assert (
            save(api, corrected[0][0][0], expected=corrected[1]["id"]).status_code
            == 201
        )
        proceed.set()
        assert task.result(timeout=5).status_code == 409
    assert api.get(base(corrected[0]) + "/correction-reviews").json() == []


def test_unchanged_baseline_rejects_other_confirmed_agreement(api, corrected):
    from test_customer_review import confirm, revise

    q = corrected[0]
    c = q[0][0]
    response = revise(
        api,
        c,
        changes=[
            {
                "category": "equipment",
                "items": [{"name": "Camera", "quantity": 1, "ambiguous": False}],
                "reason": "Buyer explicitly restated equipment.",
            }
        ],
    )
    assert response.status_code == 201, response.text
    new_agreement = response.json()
    assert confirm(api, c, agreement=new_agreement).status_code == 201
    changed_context = {**c, "agreement": new_agreement}
    assert compare(api, changed_context, corrected[1]).status_code == 201
    ctx = api.get(base(q) + "/correction").json()
    assert "unchanged_buyer_baseline_and_confirmation_required" in ctx["blockers"]
    assert record(api, corrected).status_code == 409


def test_real_comparison_from_another_booking_rejected(api, corrected, postgres_engine):
    from test_customer_review import confirm, seed_review

    other = seed_review(api, postgres_engine)
    assert confirm(api, other).status_code == 201
    proposal = save(api, other).json()
    comparison = compare(api, other, proposal).json()
    bindings = {
        **corrected[3]["bindings"],
        "comparison_id": comparison["id"],
        "comparison_fingerprint": comparison["fingerprint"],
        "proposal_id": proposal["id"],
        "proposal_fingerprint": proposal["fingerprint"],
    }
    assert record(api, corrected, bindings=bindings).status_code == 409
    assert (
        api.get(
            base(corrected[0]).replace(corrected[0][0][0]["booking"], other["booking"])
            + "/correction"
        ).status_code
        == 404
    )


def test_newer_proposal_without_affected_correction_rejected(api, question):
    from test_booking_comparisons import fake_policy

    assert reply(api, question).status_code == 201
    c, original, _ = question[0]
    proposal = save(api, c, original["content"], expected=original["id"]).json()
    fake_policy("matches")
    assert compare(api, c, proposal).status_code == 201
    ctx = api.get(base(question) + "/correction").json()
    assert "affected_proposal_terms_unchanged" in ctx["blockers"]
    assert (
        api.post(base(question) + "/correction-reviews", json=payload(ctx)).status_code
        == 409
    )


def test_ambiguous_terms_cannot_be_reviewed(api, question):
    assert reply(api, question).status_code == 201
    c, old, _ = question[0]
    data = content(c)
    data["equipment"][0]["quantity"] = None
    proposal = save(api, c, data, expected=old["id"]).json()
    assert compare(api, c, proposal).status_code == 201
    ctx = api.get(base(question) + "/correction").json()
    assert (
        not ctx["eligible"]
        and "missing_ambiguous_or_differing_terms" in ctx["blockers"]
    )
    assert (
        api.post(base(question) + "/correction-reviews", json=payload(ctx)).status_code
        == 409
    )


def test_saved_semantic_policy_match_reused_without_new_inference(api, question):
    from test_booking_comparisons import fake_policy

    assert reply(api, question).status_code == 201
    c, old, _ = question[0]
    data = content(c)
    data["deposit_conditions"][0]["value"] = (
        "The deposit is refundable on an undamaged return."
    )
    proposal = save(api, c, data, expected=old["id"]).json()
    comparator = fake_policy("matches")
    assert compare(api, c, proposal).status_code == 201
    assert comparator.compare.call_count == 1
    ctx = api.get(base(question) + "/correction").json()
    assert ctx["eligible"], ctx
    assert (
        api.post(base(question) + "/correction-reviews", json=payload(ctx)).status_code
        == 201
    )
    assert comparator.compare.call_count == 1
    question[2].suggest.assert_not_called()


def test_multiple_reply_selection_binds_one_exact_statement(api, question):
    assert reply(api, question).status_code == 201
    chosen = reply(
        api, question, response="Second explicit statement for buyer review."
    ).json()
    c, old, _ = question[0]
    proposal = save(api, c, expected=old["id"]).json()
    assert compare(api, c, proposal).status_code == 201
    ambiguous = api.get(base(question) + "/correction").json()
    assert not ambiguous["eligible"] and ambiguous["bindings"] is None
    ctx = api.get(
        base(question) + "/correction", params={"reply_id": chosen["id"]}
    ).json()
    assert ctx["eligible"]
    saved = api.post(base(question) + "/correction-reviews", json=payload(ctx))
    assert saved.status_code == 201
    assert saved.json()["context"]["bindings"]["reply_id"] == chosen["id"]
