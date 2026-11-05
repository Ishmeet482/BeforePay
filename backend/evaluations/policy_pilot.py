"""The explicitly requested six-case v2 pilot. No calls without live opt-in."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from evaluations.policy_eval import (
    Observation,
    load_dataset,
    preflight,
    score,
    verify_freeze,
)

CASE_IDS = ("cmp-01", "cmp-04", "cmp-08", "con-01", "con-04", "con-08")
SAFE_ERRORS = {
    "ai_rate_limited",
    "ai_credentials_rejected",
    "ai_not_configured",
    "ai_timeout",
    "ai_invalid_output",
    "ai_unavailable",
}
STOP_ERRORS = {"ai_rate_limited", "ai_credentials_rejected", "ai_not_configured"}


def now():
    return datetime.now(UTC).isoformat()


def checkpoint(handle, record):
    handle.write(json.dumps(record) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def run_pilot(dataset, settings, handle):
    from app.comparisons.provider import GeminiPolicyComparator
    from app.policy_consistency.provider import GeminiConsistencyChecker

    frozen = verify_freeze(dataset)
    by_id = {case.id: case for case in dataset.cases}
    cases = [by_id[case_id] for case_id in CASE_IDS]
    if any(preflight(case)["path"] != "provider" for case in cases):
        raise ValueError("Pilot scope changed; no calls permitted")
    model = settings.gemini_model.strip()
    if (
        not model
        or not settings.gemini_api_key
        or not settings.gemini_api_key.get_secret_value().strip()
    ):
        raise ValueError("Existing Gemini configuration is unavailable")
    checkpoint(
        handle,
        {
            "record": "pilot_started",
            "started_at": now(),
            "kind": "small_synthetic_pilot_not_general_accuracy",
            "dataset_hash": frozen["dataset_sha256"],
            "freeze_manifest": frozen,
            "requested_case_ids": list(CASE_IDS),
            "maximum_calls": 6,
            "configured_model": model,
            "cases": [c.model_dump(mode="json") for c in cases],
        },
    )
    observations, stop_reason = [], None
    with patch("app.drafts.provider.get_settings", lambda: settings):
        for case in cases:
            # Recheck the full frozen dataset before every distinct request.
            verify_freeze(dataset)
            plan = preflight(case)
            checkpoint(
                handle,
                {
                    "record": "case_started",
                    "case_id": case.id,
                    "started_at": now(),
                    "requested_model": model,
                    "dataset_hash": frozen["dataset_sha256"],
                },
            )
            try:
                result = (
                    GeminiPolicyComparator().compare(plan["pending"])
                    if case.task == "comparison"
                    else GeminiConsistencyChecker().check(plan["clauses"])
                )
                observation = Observation(
                    case_id=case.id,
                    path="provider",
                    output=result.output.model_dump(mode="json"),
                    metadata={
                        key: value
                        for key, value in result.metadata.items()
                        if key
                        in {
                            "provider",
                            "requested_model",
                            "response_model",
                            "response_id",
                            "sdk_version",
                            "prompt_version",
                        }
                    },
                )
            except HTTPException as error:
                code = (
                    error.detail.get("code") if isinstance(error.detail, dict) else None
                )
                if error.status_code in {401, 403, 429}:
                    code = (
                        "ai_rate_limited"
                        if error.status_code == 429
                        else "ai_credentials_rejected"
                    )
                code = code if code in SAFE_ERRORS else "provider_failure"
                observation = Observation(
                    case_id=case.id, path="provider", error_code=code
                )
                if code in STOP_ERRORS:
                    stop_reason = code
            except Exception, KeyboardInterrupt:
                observation = Observation(
                    case_id=case.id,
                    path="provider",
                    error_code="runner_failure_or_interruption",
                )
                stop_reason = observation.error_code
            observations.append(observation)
            checkpoint(
                handle,
                {
                    "record": "case_finished",
                    "finished_at": now(),
                    "requested_model": model,
                    "dataset_hash": frozen["dataset_sha256"],
                    "observation": observation.model_dump(mode="json"),
                },
            )
            print(
                f"Recorded {case.id}: {observation.error_code or 'response received'}",
                flush=True,
            )
            if stop_reason:
                break
    attempted_ids = [o.case_id for o in observations]
    # Score only attempted cases; unattempted cases remain explicit, not fake misses.
    attempted = dataset.model_copy(
        update={"cases": [c for c in cases if c.id in attempted_ids]}
    )
    report = score(attempted, observations, live=True)
    report.update(
        {
            "evaluation_kind": "small_synthetic_live_pilot_not_general_accuracy",
            "configured_model": model,
            "dataset_hash": frozen["dataset_sha256"],
            "requested_case_ids": list(CASE_IDS),
            "attempted_case_ids": attempted_ids,
            "not_run_case_ids": [i for i in CASE_IDS if i not in attempted_ids],
            "attempted_adapter_calls": len(observations),
            "maximum_calls": 6,
            "stop_reason": stop_reason,
            "finished_at": now(),
        }
    )
    checkpoint(handle, {"record": "pilot_finished", "report": report})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--authorize-live-gemini", action="store_true")
    parser.add_argument("--max-calls", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    dataset = load_dataset()  # Frozen hash verified before configuration access.
    if not args.live and not args.authorize_live_gemini and args.max_calls == 0:
        print(
            json.dumps(
                {
                    "hash_verified": verify_freeze(dataset)["dataset_sha256"],
                    "cases": CASE_IDS,
                    "planned_calls": 6,
                    "live": False,
                }
            )
        )
        return 0
    if not (
        args.live and args.authorize_live_gemini and args.max_calls == 6 and args.output
    ):
        parser.error("Require explicit live flags, --max-calls 6 and new --output")
    from app.core.config import get_settings

    # Normal backend runtime loader uses the existing configured model/credentials.
    # Never display, export or edit credential values.
    settings = get_settings()
    with args.output.open("x") as handle:
        os.chmod(args.output, 0o600)
        report = run_pilot(dataset, settings, handle)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
