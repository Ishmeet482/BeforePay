from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_booking_comparisons import compare, content, fake_policy, save
from test_clarifications import discrepancy as discrepancy
from test_clarifications import generate, install, path
from test_customer_review import state

from app.clarifications.models import MerchantReply
from app.clarifications.provider import get_clarifier
from app.main import app


@pytest.fixture
def question(api, discrepancy):
    install()
    response = generate(api, discrepancy)
    assert response.status_code == 201
    provider = Mock()
    provider.suggest.side_effect = AssertionError("Replies must never invoke AI")
    app.dependency_overrides[get_clarifier] = lambda: provider
    return discrepancy, response.json(), provider


def reply_path(q):
    return path(q[0]) + f"/{q[1]['id']}/replies"


def reply(api, q, **overrides):
    s = q[1]
    return api.post(
        reply_path(q),
        json={
            "suggestion_fingerprint": s["fingerprint"],
            "comparison_fingerprint": s["comparison_fingerprint"],
            "proposal_id": s["proposal_id"],
            "proposal_fingerprint": s["proposal_fingerprint"],
            "merchant_label": "Provisional merchant",
            "response": (
                "I will prepare a revised proposal.\n"
                "This message does not amend the saved terms."
            ),
            **overrides,
        },
    )


def test_reply_persistence_append_only_and_checkout_unchanged(
    api, question, postgres_engine
):
    d, suggestion, provider = question
    base = f"/api/bookings/{d[0]['booking']}"
    original = state(api, d[0])
    eligibility = api.get(base + "/checkout/eligibility").json()
    first = reply(api, question)
    assert first.status_code == 201, first.text
    record = first.json()
    assert record["identity_provisional"] is True and not record["stale"]
    for field in (
        "comparison_id",
        "comparison_fingerprint",
        "proposal_id",
        "proposal_fingerprint",
    ):
        assert record[field] == suggestion[field]
    assert record["suggestion_id"] == suggestion["id"]
    assert record["suggestion_fingerprint"] == suggestion["fingerprint"]
    second = reply(
        api, question, response="A second explicit statement, not an overwrite."
    )
    assert second.status_code == 201 and second.json()["id"] != record["id"]
    history = api.get(reply_path(question)).json()
    assert (
        len(history) == 2
        and next(r for r in history if r["id"] == record["id"]) == record
    )
    assert api.get(base + "/clarifications").json()[0] == suggestion
    assert api.get(base + "/checkout/eligibility").json() == eligibility
    assert state(api, d[0]) == original
    assert api.get(base + "/checkout/attempts").json() == []
    assert api.get(base + f"/comparisons/{d[2]['id']}").json() == d[2]
    assert api.get(base + f"/merchant-bookings/{d[1]['id']}").json() == d[1]
    provider.suggest.assert_not_called()
    for statement in (
        update(MerchantReply).values(response="overwrite"),
        delete(MerchantReply),
    ):
        with Session(postgres_engine) as session:
            with pytest.raises(DBAPIError):
                session.execute(statement.where(MerchantReply.id == UUID(record["id"])))
                session.commit()
            session.rollback()


@pytest.mark.parametrize(
    "field,value",
    [
        ("merchant_label", ""),
        ("merchant_label", "  "),
        ("response", ""),
        ("response", "\n\t"),
        ("response", "bad\x00text"),
        ("response", "x" * 5001),
    ],
)
def test_empty_or_invalid_reply_rejected(api, question, field, value):
    assert reply(api, question, **{field: value}).status_code == 422
    assert api.get(reply_path(question)).json() == []
    question[2].suggest.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("suggestion_fingerprint", "0" * 64),
        ("comparison_fingerprint", "0" * 64),
        ("proposal_id", str(uuid4())),
        ("proposal_fingerprint", "0" * 64),
    ],
)
def test_exact_context_guards(api, question, field, value):
    assert reply(api, question, **{field: value}).status_code == 409
    assert api.get(reply_path(question)).json() == []


@pytest.mark.parametrize("change", ["proposal", "comparison", "evidence"])
def test_stale_submission_rejected_but_reply_history_preserved(api, question, change):
    d, _, provider = question
    original = reply(api, question).json()
    c, proposal, _ = d
    if change == "proposal":
        assert save(api, c, content(c), expected=proposal["id"]).status_code == 201
    elif change == "comparison":
        fake_policy("differs")
        assert compare(api, c, proposal).status_code == 201
    else:
        assert (
            api.post(
                f"/api/bookings/{c['booking']}/sources/text",
                json={
                    "source_type": "message",
                    "original_text": "New terms need buyer review.",
                },
            ).status_code
            == 201
        )
    assert reply(api, question).status_code == 409
    records = api.get(reply_path(question)).json()
    assert len(records) == 1 and records[0]["id"] == original["id"]
    assert records[0]["response"] == original["response"] and records[0]["stale"]
    assert api.get(f"/api/bookings/{c['booking']}/clarifications").json()[0]["stale"]
    provider.suggest.assert_not_called()


def test_cross_booking_and_wrong_suggestion_rejected(api, question):
    other = api.post("/api/bookings", json={"title": "Other synthetic booking"}).json()[
        "id"
    ]
    url = reply_path(question)
    assert api.get(url.replace(question[0][0]["booking"], other)).status_code == 404
    assert api.get(url.replace(question[1]["id"], str(uuid4()))).status_code == 404
    assert api.patch(url, json={"response": "overwrite"}).status_code == 405
    assert api.delete(url).status_code == 405


def test_needs_information_entry_is_not_a_question(api, discrepancy):
    def insufficient(output):
        output.update(status="needs_more_information", question=None, references=[])

    install(modify=insufficient)
    suggestion = generate(api, discrepancy).json()
    q = discrepancy, suggestion, Mock()
    assert reply(api, q).status_code == 422
    assert api.get(reply_path(q)).json() == []
