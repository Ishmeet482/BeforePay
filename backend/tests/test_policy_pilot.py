"""Offline pilot safety only; real adapters are never invoked here."""

import json

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from evaluations.policy_eval import load_dataset
from evaluations.policy_pilot import CASE_IDS, main, run_pilot


@pytest.mark.parametrize("code", ["ai_rate_limited", "ai_credentials_rejected"])
def test_fatal_error_stops_and_preserves_checkpoint(monkeypatch, tmp_path, code):
    calls = []

    def fail(*args):
        calls.append(1)
        raise HTTPException(503, {"code": code, "message": "not persisted"})

    monkeypatch.setattr("app.comparisons.provider.GeminiPolicyComparator.compare", fail)
    path = tmp_path / "pilot.jsonl"
    with path.open("x") as handle:
        report = run_pilot(
            load_dataset(),
            Settings(_env_file=None, gemini_api_key="offline-test"),
            handle,
        )
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(calls) == 1
    assert report["stop_reason"] == code
    assert report["not_run_case_ids"] == list(CASE_IDS[1:])
    assert records[2]["observation"]["error_code"] == code
    assert "offline-test" not in path.read_text()
    assert records[-1]["record"] == "pilot_finished"


def test_exact_six_scope_and_no_retry_on_other_failure(monkeypatch, tmp_path):
    calls = []

    def respond(self, inputs):
        calls.append(inputs)
        if len(calls) == 2:
            raise HTTPException(504, {"code": "ai_timeout"})
        raise HTTPException(502, {"code": "ai_invalid_output"})

    monkeypatch.setattr(
        "app.comparisons.provider.GeminiPolicyComparator.compare", respond
    )
    with (tmp_path / "pilot.jsonl").open("x") as handle:
        report = run_pilot(
            load_dataset(),
            Settings(_env_file=None, gemini_api_key="offline-test"),
            handle,
        )
    assert len(calls) == 6
    assert report["attempted_case_ids"] == list(CASE_IDS)
    assert report["stop_reason"] is None
    assert not report["not_run_case_ids"]
    assert (
        report["tasks"]["comparison"]["correct_uncertainty_handling"]["denominator"]
        == 1
    )


def test_default_plan_does_not_load_configuration(monkeypatch, capsys):
    def forbidden():
        raise AssertionError("Default must not access configuration")

    monkeypatch.setattr("app.core.config.get_settings", forbidden)
    assert main([]) == 0
    assert '"live": false' in capsys.readouterr().out
