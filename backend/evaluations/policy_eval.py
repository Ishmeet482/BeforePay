"""Opt-in policy evaluation; default mode validates/plans without provider calls."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DATASET_VERSION = 2
DATASET = Path(__file__).with_name(f"policy_cases.v{DATASET_VERSION}.json")
CATEGORIES = ("deposit_conditions", "cancellation_conditions")
STATUSES = {
    "comparison": {"matches", "differs", "needs_clarification"},
    "consistency": {
        "potential_contradiction",
        "needs_clarification",
        "no_contradiction_found",
    },
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Clause(Strict):
    id: str = Field(min_length=1)
    side: Literal["agreement", "merchant"]
    category: Literal["deposit_conditions", "cancellation_conditions"]
    text: str = Field(min_length=1, max_length=10000)
    ambiguous: bool


class Support(Strict):
    clause_id: str
    quotation: str = Field(min_length=1)


class Case(Strict):
    id: str = Field(pattern=r"^(cmp|con)-\d{2}$")
    task: Literal["comparison", "consistency"]
    tags: list[
        Literal[
            "material_change",
            "equivalent_wording",
            "internal_contradiction",
            "compatible_exception",
            "missing_terms",
            "ambiguous_terms",
            "embedded_instructions",
        ]
    ] = Field(min_length=1)
    category: Literal["deposit_conditions", "cancellation_conditions"] | None
    clauses: list[Clause] = Field(min_length=1, max_length=100)
    expected_status: str
    expected_support: list[Support]
    expected_path: Literal["provider", "local_guard"]
    rationale: str = Field(min_length=20)

    @model_validator(mode="after")
    def validate_label_and_support(self):
        if not self.rationale.strip() or not self.id.startswith(
            "cmp-" if self.task == "comparison" else "con-"
        ):
            raise ValueError("Require a nonblank rationale and task-specific ID")
        if self.expected_status not in STATUSES[self.task]:
            raise ValueError("Label does not belong to task")
        clauses = {c.id: c for c in self.clauses}
        if len(clauses) != len(self.clauses):
            raise ValueError("Duplicate clause ID")
        support = {s.clause_id: s.quotation for s in self.expected_support}
        if len(support) != len(self.expected_support) or support != {
            c.id: c.text for c in self.clauses
        }:
            raise ValueError("Gold support must contain every exact available clause")
        if any(not c.text.strip() for c in self.clauses):
            raise ValueError("Blank clause")
        if self.task == "comparison":
            if self.category is None or any(
                c.category != self.category for c in self.clauses
            ):
                raise ValueError("Comparison needs one declared policy category")
            for side in ("agreement", "merchant"):
                for i, clause in enumerate(c for c in self.clauses if c.side == side):
                    if clause.id != f"{side}:{i}":
                        raise ValueError("Comparison clause IDs must retain side/index")
        else:
            if self.category is not None or any(
                c.side != "merchant" for c in self.clauses
            ):
                raise ValueError("Consistency is one merchant proposal, no baseline")
            for category in CATEGORIES:
                for i, clause in enumerate(
                    c for c in self.clauses if c.category == category
                ):
                    if clause.id != f"{category}:{i}":
                        raise ValueError("Consistency IDs must retain category/index")
        return self


class Dataset(Strict):
    schema_version: Literal[1]
    name: str
    provenance: str
    cases: list[Case] = Field(min_length=20, max_length=20)

    @model_validator(mode="after")
    def coverage(self):
        if len({c.id for c in self.cases}) != 20:
            raise ValueError("Case IDs must be unique")
        for task in STATUSES:
            cases = [c for c in self.cases if c.task == task]
            if len(cases) != 10 or {c.expected_status for c in cases} != STATUSES[task]:
                raise ValueError("Each task needs ten cases covering every status")
            tags = {tag for c in cases for tag in c.tags}
            if (
                not {"missing_terms", "ambiguous_terms", "embedded_instructions"}
                <= tags
            ):
                raise ValueError("Each task needs missing/ambiguous/adversarial cases")
        return self


def load_dataset(path=DATASET, *, require_frozen=True):
    path = Path(path)
    dataset = Dataset.model_validate_json(Path(path).read_text())
    for case in dataset.cases:
        if preflight(case)["path"] != case.expected_path:
            raise ValueError(f"Preflight drift: {case.id}")
    if require_frozen:
        verify_freeze(dataset, path)
    return dataset


def verify_freeze(dataset, path=DATASET):
    """Refuse edited/unfrozen evaluation inputs before configuration or inference."""
    path = Path(path)
    manifest = json.loads(path.with_suffix(".freeze.json").read_text())
    if (
        manifest.get("dataset_file") != path.name
        or manifest.get("dataset_version") != DATASET_VERSION
        or manifest.get("case_count") != len(dataset.cases)
        or manifest.get("dataset_name") != dataset.name
        or manifest.get("model_excluded_case_ids")
        != [c.id for c in dataset.cases if c.expected_path == "local_guard"]
        or manifest.get("planned_provider_calls")
        != sum(c.expected_path == "provider" for c in dataset.cases)
        or manifest.get("dataset_sha256") != dataset_digest(dataset)
        or manifest.get("file_sha256") != hashlib.sha256(path.read_bytes()).hexdigest()
        or manifest.get("status") != "frozen_for_evaluation_not_live_authorization"
    ):
        raise ValueError("Frozen dataset hash/version mismatch; review a new revision")
    return manifest


def preflight(case):
    """Reuse real pure planners/guards; never instantiate a session or provider."""
    if case.task == "comparison":
        from app.comparisons.service import plan_comparison
        from app.drafts.schemas import Extraction

        proposal = {category: [] for category in Extraction.model_fields}
        agreement = {category: [] for category in Extraction.model_fields}
        for clause in case.clauses:
            claim = {"value": clause.text, "ambiguous": clause.ambiguous}
            if clause.side == "merchant":
                proposal[clause.category].append(claim)
            else:
                agreement[clause.category].append(
                    {
                        "origin": "customer_entered",
                        "reason": "Synthetic evaluation clause; not booking evidence.",
                        "claim": claim,
                    }
                )
        results, pending = plan_comparison({"extraction": agreement}, proposal)
        row = next(r for r in results if r["category"] == case.category)
        pending = [p for p in pending if p["category"] == case.category]
        return {
            "path": "provider" if pending else "local_guard",
            "status": row["status"],
            "pending": pending,
            "row": row,
        }
    from app.policy_consistency.service import clause_context

    content = {category: [] for category in CATEGORIES}
    for clause in case.clauses:
        content[clause.category].append(
            {"value": clause.text, "ambiguous": clause.ambiguous}
        )
    clauses, complete = clause_context(SimpleNamespace(content=content))
    return {
        "path": "provider" if complete else "local_guard",
        "status": "needs_clarification" if not complete else None,
        "clauses": clauses,
    }


class Observation(Strict):
    case_id: str
    path: Literal["provider", "local_guard"]
    output: dict | None = None
    error_code: str | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def output_or_error(self):
        if (self.output is None) == (self.error_code is None):
            raise ValueError("Supply exactly one output or error code")
        return self


def accepted_result(case, observation):
    """Use production output/reference validation, not matching invented citations."""
    plan = preflight(case)
    if observation.path != plan["path"]:
        raise ValueError("Observation path does not match existing guard")
    if observation.path == "local_guard":
        if observation.output != {"status": plan["status"]}:
            raise ValueError("Local result differs from actual deterministic guard")
        return plan["status"], None
    if case.task == "comparison":
        from app.comparisons.schemas import PolicyOutput
        from app.comparisons.service import apply_policies

        output = PolicyOutput.model_validate(observation.output)
        row = dict(plan["row"])
        apply_policies([row], plan["pending"], output)
        return row["status"], True
    from app.policy_consistency.schemas import Output
    from app.policy_consistency.service import validate_references

    output = Output.model_validate(observation.output)
    validate_references(output, plan["clauses"])
    statuses = {finding.status for finding in output.findings}
    status = next(
        s
        for s in (
            "potential_contradiction",
            "needs_clarification",
            "no_contradiction_found",
        )
        if s in statuses
    )
    return status, True


def fraction(numerator, denominator, **extra):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator
        if denominator and numerator is not None
        else None,
        **extra,
    }


def score(dataset, observations, *, live=False):
    indexed = {}
    ids = {case.id for case in dataset.cases}
    for raw in observations:
        obs = Observation.model_validate(raw)
        if obs.case_id not in ids or obs.case_id in indexed:
            raise ValueError("Unknown or duplicate result case ID")
        indexed[obs.case_id] = obs
    rows = []
    for case in dataset.cases:
        obs = indexed.get(case.id)
        predicted, citations, error = None, None, "missing_result"
        if obs:
            error = obs.error_code
            if not error:
                try:
                    predicted, citations = accepted_result(case, obs)
                except ValueError, KeyError, TypeError:
                    error = "unsupported_output_or_references"
            if case.expected_path == "provider" and error:
                citations = False
        elif case.expected_path == "provider":
            citations = False
        rows.append(
            {
                "id": case.id,
                "task": case.task,
                "expected": case.expected_status,
                "predicted": predicted,
                "path": case.expected_path,
                "citation_valid": citations,
                "error_code": error,
                "passed": error is None and predicted == case.expected_status,
            }
        )
    tasks = {}
    for task in STATUSES:
        workflow_group = [r for r in rows if r["task"] == task]
        group = [r for r in workflow_group if r["path"] == "provider"]
        local = [r for r in workflow_group if r["path"] == "local_guard"]
        positive = "differs" if task == "comparison" else "potential_contradiction"
        negative = "matches" if task == "comparison" else "no_contradiction_found"
        positives = [r for r in group if r["expected"] == positive]
        negatives = [r for r in group if r["expected"] == negative]
        classified_negatives = [r for r in negatives if r["predicted"] is not None]
        uncertain = [r for r in group if r["expected"] == "needs_clarification"]
        provider_rows = [r for r in group if r["path"] == "provider"]
        recall = fraction(
            sum(r["predicted"] == positive for r in positives), len(positives)
        )
        tasks[task] = {
            "material_change_recall": recall
            if task == "comparison"
            else fraction(
                None, 0, reason="Not applicable: one proposal, no change baseline"
            ),
            **({"contradiction_recall": recall} if task == "consistency" else {}),
            "false_positive_rate": fraction(
                sum(r["predicted"] == positive for r in classified_negatives),
                len(classified_negatives),
                eligible_negative_cases=len(negatives),
                unclassified_negative_ids=[
                    r["id"] for r in negatives if r["predicted"] is None
                ],
                unnecessary_uncertainty_ids=[
                    r["id"]
                    for r in negatives
                    if r["predicted"] == "needs_clarification"
                ],
            ),
            "citation_validity": fraction(
                sum(r["citation_valid"] is True for r in provider_rows),
                len(provider_rows),
                unit="provider-eligible cases passing full literal-reference contract",
            ),
            "correct_uncertainty_handling": fraction(
                sum(r["predicted"] == "needs_clarification" for r in uncertain),
                len(uncertain),
            ),
            "definitive_clean_on_uncertain_ids": [
                r["id"] for r in uncertain if r["predicted"] == negative
            ],
            "local_guard_checks": {
                "case_ids": [r["id"] for r in local],
                "correct_uncertainty_handling": fraction(
                    sum(r["passed"] for r in local), len(local)
                ),
                "failure_ids": [r["id"] for r in local if not r["passed"]],
                "error_ids": [r["id"] for r in local if r["error_code"]],
            },
            "failure_ids": [r["id"] for r in group if not r["passed"]],
            "error_ids": [r["id"] for r in group if r["error_code"]],
        }
    return {
        "evaluation_kind": "live_model_and_local_guards"
        if live
        else "offline_scoring_check_not_ai_accuracy",
        "dataset_name": dataset.name,
        "local_guard_excluded_from_model_metrics": True,
        "tasks": tasks,
        "cases": rows,
    }


def plan_report(dataset):
    tasks = {}
    for task in STATUSES:
        cases = [c for c in dataset.cases if c.task == task]
        labels = Counter(c.expected_status for c in cases)
        model_cases = [c for c in cases if c.expected_path == "provider"]
        local = [c for c in cases if c.expected_path == "local_guard"]
        model_labels = Counter(c.expected_status for c in model_cases)
        count = len(model_cases)
        tasks[task] = {
            "cases": len(cases),
            "labels": dict(labels),
            "planned_calls": count,
            "local_guard_ids": [
                c.id for c in cases if c.expected_path == "local_guard"
            ],
            "local_guard_checks": {
                "case_ids": [c.id for c in local],
                "correct_uncertainty_handling": fraction(None, len(local)),
            },
            "metrics": {
                "material_change_recall": fraction(
                    None, model_labels["differs"] if task == "comparison" else 0
                ),
                **(
                    {
                        "contradiction_recall": fraction(
                            None, model_labels["potential_contradiction"]
                        )
                    }
                    if task == "consistency"
                    else {}
                ),
                "false_positive_rate": fraction(
                    None,
                    model_labels["matches"]
                    if task == "comparison"
                    else model_labels["no_contradiction_found"],
                ),
                "citation_validity": fraction(None, count),
                "correct_uncertainty_handling": fraction(
                    None,
                    model_labels["needs_clarification"],
                ),
            },
        }
    return {
        "evaluation_kind": "not_run_dataset_validation_and_call_plan_only",
        "model_accuracy": "NOT EVALUATED; no provider responses collected",
        "dataset_name": dataset.name,
        "local_guard_excluded_from_model_metrics": True,
        "dataset_sha256": dataset_digest(dataset),
        "planned_calls": sum(t["planned_calls"] for t in tasks.values()),
        "tasks": tasks,
    }


def dataset_digest(dataset):
    """Hash validated in-memory inputs/labels, never a later edited file."""
    canonical = json.dumps(dataset.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def live_observations(dataset, settings, max_calls):
    """Only called after CLI opt-in; environment-only settings supplied by caller."""
    verify_freeze(dataset)
    from fastapi import HTTPException

    from app.comparisons.provider import GeminiPolicyComparator
    from app.drafts.diagnostics import PROVIDER_CODES
    from app.policy_consistency.provider import GeminiConsistencyChecker

    planned = sum(c.expected_path == "provider" for c in dataset.cases)
    if max_calls != planned:
        raise ValueError(f"Explicit --max-calls must equal planned count {planned}")
    observations, calls = [], 0
    with patch("app.drafts.provider.get_settings", lambda: settings):
        for case in dataset.cases:
            plan = preflight(case)
            if plan["path"] == "local_guard":
                observations.append(
                    Observation(
                        case_id=case.id,
                        path="local_guard",
                        output={"status": plan["status"]},
                    )
                )
                continue
            calls += 1
            if calls > max_calls:
                raise RuntimeError("Call cap exceeded")
            try:
                result = (
                    GeminiPolicyComparator().compare(plan["pending"])
                    if case.task == "comparison"
                    else GeminiConsistencyChecker().check(plan["clauses"])
                )
                observations.append(
                    Observation(
                        case_id=case.id,
                        path="provider",
                        output=result.output.model_dump(mode="json"),
                        metadata={
                            k: v
                            for k, v in result.metadata.items()
                            if k
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
                )
            except HTTPException as error:
                code = (
                    error.detail.get("code") if isinstance(error.detail, dict) else None
                )
                observations.append(
                    Observation(
                        case_id=case.id,
                        path="provider",
                        error_code=code
                        if code in PROVIDER_CODES
                        else "provider_failure",
                    )
                )
            except Exception:
                observations.append(
                    Observation(
                        case_id=case.id,
                        path="provider",
                        error_code="runner_failure",
                    )
                )
    return observations, calls


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--authorize-live-gemini", action="store_true")
    parser.add_argument("--max-calls", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.live != args.authorize_live_gemini:
        parser.error("Live inference requires both explicit live opt-in flags")
    dataset = load_dataset()
    report = plan_report(dataset)
    if args.live:
        if args.max_calls != report["planned_calls"]:
            parser.error("Live call cap must explicitly equal the reported plan")
        if args.output is None:
            parser.error("Live evaluation requires a new --output artifact path")
        from app.core.config import Settings

        try:
            # Process environment only; no secret files.
            settings = Settings(_env_file=None)
        except ValidationError:
            parser.error("Invalid environment configuration; values are not printed")
        if (
            not settings.gemini_api_key
            or not settings.gemini_api_key.get_secret_value().strip()
            or not settings.gemini_model.strip()
        ):
            parser.error("Backend Gemini environment configuration is required")
        # Reserve output before any inference, avoiding accidental repeated paid runs
        # caused by an existing/unwritable report path.
        with args.output.open("x") as handle:
            started_at = datetime.now(UTC).isoformat()
            freeze_manifest = verify_freeze(dataset)
            observations, calls = live_observations(dataset, settings, args.max_calls)
            report = score(dataset, observations, live=True)
            report.update(
                {
                    "freeze_manifest": freeze_manifest,
                    "attempted_provider_calls": calls,
                    "dataset_sha256": dataset_digest(dataset),
                    "dataset": dataset.model_dump(mode="json"),
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "observations": [o.model_dump(mode="json") for o in observations],
                }
            )
            handle.write(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in {"observations", "dataset"}
                },
                indent=2,
            )
        )
    else:
        if args.max_calls:
            parser.error("Default offline mode cannot request provider calls")
        encoded = json.dumps(report, indent=2) + "\n"
        if args.output:
            with args.output.open("x") as handle:
                handle.write(encoded)
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
