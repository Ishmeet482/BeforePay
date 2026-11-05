"""Dataset/scoring mechanics only. Fake observations do not measure AI accuracy."""

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from evaluations.policy_eval import (
    DATASET,
    Case,
    Dataset,
    dataset_digest,
    load_dataset,
    main,
    plan_report,
    preflight,
    score,
    verify_freeze,
)


@pytest.fixture
def dataset():
    return load_dataset()


def labelled_observations(dataset):
    """Deliberately copy labels to exercise arithmetic, never simulate real quality."""
    rows = []
    for case in dataset.cases:
        if case.expected_path == "local_guard":
            output = {"status": preflight(case)["status"]}
        elif case.task == "comparison":
            output = {
                "results": [
                    {
                        "category": case.category,
                        "status": case.expected_status,
                        "agreement_quote": next(
                            c.text for c in case.clauses if c.side == "agreement"
                        ),
                        "proposal_quote": next(
                            c.text for c in case.clauses if c.side == "merchant"
                        ),
                    }
                ]
            }
        else:
            output = {
                "findings": [
                    {
                        "status": case.expected_status,
                        "explanation": case.rationale,
                        "references": [s.model_dump() for s in case.expected_support],
                    }
                ]
            }
        rows.append({"case_id": case.id, "path": case.expected_path, "output": output})
    return rows


def test_dataset_and_existing_preflight(dataset):
    report = plan_report(dataset)
    assert len(dataset.cases) == 20 and report["planned_calls"] == 18
    for task, positive, negative in (
        ("comparison", "differs", "matches"),
        ("consistency", "potential_contradiction", "no_contradiction_found"),
    ):
        section = report["tasks"][task]
        assert section["labels"] == {positive: 4, negative: 4, "needs_clarification": 2}
        assert section["planned_calls"] == 9
        assert section["metrics"]["citation_validity"] == {
            "numerator": None,
            "denominator": 9,
            "rate": None,
        }
        assert section["metrics"]["correct_uncertainty_handling"]["denominator"] == 1
    assert "NOT EVALUATED" in report["model_accuracy"]


def test_revised_inputs_preserve_original_labels_and_v1(dataset):
    original = Dataset.model_validate_json(
        DATASET.with_name("policy_cases.v1.json").read_text()
    )
    changed = {
        new.id
        for old, new in zip(original.cases, dataset.cases, strict=True)
        if old != new
    }
    assert changed == {"cmp-04", "cmp-05", "cmp-06", "cmp-08", "con-08"}
    assert [c.expected_status for c in original.cases] == [
        c.expected_status for c in dataset.cases
    ]
    cases = {c.id: c for c in dataset.cases}
    assert all("all rented equipment" in c.text for c in cases["cmp-04"].clauses)
    assert all(
        all(term in c.text for term in ("full refund", "rental fee", "deposit"))
        for c in cases["cmp-05"].clauses
    )
    assert "full deposit is returned" in cases["cmp-06"].clauses[0].text
    assert "deposit is returned in full" in cases["cmp-06"].clauses[1].text
    assert "unresolved discretion" in cases["cmp-08"].rationale
    assert "deposit refund" in cases["con-08"].clauses[1].text
    assert (
        cases["cmp-07"].expected_path == cases["con-07"].expected_path == "local_guard"
    )


def test_freeze_binds_dataset_version_and_inputs(dataset):
    manifest = verify_freeze(dataset)
    assert manifest["dataset_version"] == 2
    assert manifest["dataset_sha256"] == dataset_digest(dataset)
    assert manifest["model_excluded_case_ids"] == ["cmp-07", "con-07"]


@pytest.mark.parametrize(
    "change",
    ["label", "input", "whitespace", "version", "local_exclusion", "calls", "missing"],
)
def test_modified_or_unfrozen_dataset_rejected_before_inference(
    dataset, tmp_path, change
):
    path = tmp_path / DATASET.name
    path.write_bytes(DATASET.read_bytes())
    manifest = json.loads(DATASET.with_suffix(".freeze.json").read_text())
    if change == "label":
        data = json.loads(path.read_text())
        data["cases"][7]["expected_status"] = "matches"
        path.write_text(json.dumps(data))
    elif change == "input":
        data = json.loads(path.read_text())
        data["cases"][0]["clauses"][0]["text"] += " Revised condition."
        data["cases"][0]["expected_support"][0]["quotation"] += " Revised condition."
        path.write_text(json.dumps(data))
    elif change == "whitespace":
        path.write_text(path.read_text() + "\n")
    elif change == "version":
        manifest["dataset_version"] = 3
    elif change == "local_exclusion":
        manifest["model_excluded_case_ids"] = []
    elif change == "calls":
        manifest["planned_provider_calls"] = 20
    if change != "missing":
        path.with_suffix(".freeze.json").write_text(json.dumps(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        load_dataset(path)


@pytest.mark.parametrize("prediction", ["matches", "differs"])
def test_cmp08_uncertainty_is_never_scored_as_a_match(dataset, prediction):
    rows = labelled_observations(dataset)
    rows[7]["output"]["results"][0]["status"] = prediction
    result = score(dataset, rows)
    case = result["cases"][7]
    task = result["tasks"]["comparison"]
    assert case["expected"] == "needs_clarification" and case["passed"] is False
    assert task["correct_uncertainty_handling"] == {
        "numerator": 0,
        "denominator": 1,
        "rate": 0.0,
    }
    assert task["false_positive_rate"]["eligible_negative_cases"] == 4
    assert task["failure_ids"] == ["cmp-08"]
    assert task["definitive_clean_on_uncertain_ids"] == (
        ["cmp-08"] if prediction == "matches" else []
    )


def test_comparison_schema_cannot_report_combined_status_or_category(dataset):
    for field, value in (
        ("status", "differs_and_needs_clarification"),
        ("category", "material_change"),
    ):
        rows = labelled_observations(dataset)
        rows[7]["output"]["results"][0][field] = value
        assert score(dataset, rows)["cases"][7]["error_code"]


def test_local_missing_inputs_never_enter_any_model_metric(dataset):
    baseline = score(dataset, labelled_observations(dataset))
    rows = [r for r in labelled_observations(dataset) if r["path"] == "provider"]
    missing_local = score(dataset, rows)
    for task in ("comparison", "consistency"):
        before, after = (report["tasks"][task] for report in (baseline, missing_local))
        for key in before.keys() - {"local_guard_checks"}:
            assert before[key] == after[key]
        assert len(after["local_guard_checks"]["failure_ids"]) == 1
        assert after["correct_uncertainty_handling"]["denominator"] == 1
        assert after["citation_validity"]["denominator"] == 9


def test_declared_provider_path_cannot_hide_preflight_drift(dataset, tmp_path):
    data = dataset.model_dump_json()
    path = tmp_path / "drift.json"
    path.write_text(
        data.replace('"expected_path":"provider"', '"expected_path":"local_guard"', 1)
    )
    with pytest.raises(ValueError, match="Preflight drift"):
        load_dataset(path)


def test_embedded_instructions_remain_untrusted_input_data(dataset):
    for case in dataset.cases:
        if "embedded_instructions" not in case.tags:
            continue
        plan = preflight(case)
        assert plan["path"] == "provider"
        if case.task == "comparison":
            text = plan["pending"][0]["proposal_text"]
            assert all(c.text in text for c in case.clauses if c.side == "merchant")
        else:
            assert [c["text"] for c in plan["clauses"]] == [
                c.text for c in case.clauses
            ]
    # This only checks fixture preservation, not a model's resistance to instructions.


def test_dataset_digest_binds_validated_labels_and_exact_clauses(dataset):
    copied = Dataset.model_validate_json(dataset.model_dump_json())
    assert dataset_digest(copied) == dataset_digest(dataset)
    data = copied.model_dump()
    data["cases"][0]["expected_status"] = "needs_clarification"
    changed = Dataset.model_validate(data)
    assert dataset_digest(changed) != dataset_digest(dataset)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "support", "status", "category", "blank", "coverage"]
)
def test_invalid_dataset_rejected(dataset, mutation):
    data = dataset.model_dump()
    if mutation == "duplicate":
        data["cases"][1]["id"] = data["cases"][0]["id"]
    elif mutation == "support":
        data["cases"][0]["expected_support"][0]["quotation"] = "Invented clause"
    elif mutation == "status":
        data["cases"][0]["expected_status"] = "no_contradiction_found"
    elif mutation == "category":
        data["cases"][0]["category"] = None
    elif mutation == "blank":
        data["cases"][0]["clauses"][0]["text"] = " "
    else:
        data["cases"] = data["cases"][:-1]
    with pytest.raises(ValidationError):
        Dataset.model_validate(data)


def test_reference_side_and_duplicate_ids_rejected(dataset):
    case = dataset.cases[0].model_dump()
    case["clauses"][1]["id"] = "agreement:0"
    with pytest.raises(ValidationError):
        Case.model_validate(case)


def test_scoring_math_with_label_copies_is_explicitly_not_ai_accuracy(dataset):
    result = score(dataset, labelled_observations(dataset))
    assert result["evaluation_kind"] == "offline_scoring_check_not_ai_accuracy"
    for task, section in result["tasks"].items():
        recall = section[
            "material_change_recall" if task == "comparison" else "contradiction_recall"
        ]
        assert recall == {"numerator": 4, "denominator": 4, "rate": 1.0}
        assert section["false_positive_rate"]["numerator"] == 0
        assert section["false_positive_rate"]["denominator"] == 4
        assert section["citation_validity"]["numerator"] == 9
        assert section["citation_validity"]["denominator"] == 9
        assert section["correct_uncertainty_handling"]["numerator"] == 1
        assert (
            section["local_guard_checks"]["correct_uncertainty_handling"]["numerator"]
            == 1
        )
        assert not section["failure_ids"]
    assert result["tasks"]["consistency"]["material_change_recall"]["rate"] is None


def test_false_negatives_false_positives_uncertainty_and_errors_visible(dataset):
    observations = labelled_observations(dataset)
    observations[0]["output"]["results"][0]["status"] = "matches"
    observations[3]["output"]["results"][0]["status"] = "differs"
    observations[7]["output"]["results"][0]["status"] = "matches"
    observations[10] = {
        "case_id": "con-01",
        "path": "provider",
        "error_code": "ai_timeout",
    }
    observations[13]["output"]["findings"][0]["status"] = "potential_contradiction"
    observations[17]["output"]["findings"][0]["status"] = "no_contradiction_found"
    result = score(dataset, observations)
    comparison, consistency = (
        result["tasks"][task] for task in ("comparison", "consistency")
    )
    assert comparison["material_change_recall"]["numerator"] == 3
    assert comparison["false_positive_rate"]["rate"] == 0.25
    assert comparison["correct_uncertainty_handling"]["numerator"] == 0
    assert set(comparison["failure_ids"]) == {"cmp-01", "cmp-04", "cmp-08"}
    assert consistency["contradiction_recall"]["numerator"] == 3
    assert consistency["false_positive_rate"]["rate"] == 0.25
    assert consistency["citation_validity"]["numerator"] == 8
    assert consistency["correct_uncertainty_handling"]["numerator"] == 0
    assert consistency["error_ids"] == ["con-01"]


@pytest.mark.parametrize("task", ["comparison", "consistency"])
def test_bad_citations_fail_closed_and_do_not_silently_drop_denominator(dataset, task):
    rows = labelled_observations(dataset)
    index = 0 if task == "comparison" else 10
    if task == "comparison":
        rows[index]["output"]["results"][0]["agreement_quote"] = "Not in the source"
    else:
        rows[index]["output"]["findings"][0]["references"][0]["clause_id"] = "unknown:9"
    result = score(dataset, rows)
    section = result["tasks"][task]
    assert section["citation_validity"]["numerator"] == 8
    assert section["citation_validity"]["denominator"] == 9
    assert result["cases"][index]["predicted"] is None
    assert result["cases"][index]["error_code"] == "unsupported_output_or_references"


def test_clean_consistency_must_cover_all_clauses(dataset):
    rows = labelled_observations(dataset)
    rows[13]["output"]["findings"][0]["references"].pop()
    assert score(dataset, rows)["cases"][13]["citation_valid"] is False


def test_duplicate_category_or_wrong_side_comparison_rejected(dataset):
    rows = labelled_observations(dataset)
    rows[0]["output"]["results"].append(deepcopy(rows[0]["output"]["results"][0]))
    assert score(dataset, rows)["cases"][0]["error_code"]
    rows = labelled_observations(dataset)
    rows[0]["output"]["results"][0]["agreement_quote"] = rows[0]["output"]["results"][
        0
    ]["proposal_quote"]
    assert score(dataset, rows)["cases"][0]["error_code"]


def test_missing_and_invalid_negative_results_expose_coverage(dataset):
    rows = labelled_observations(dataset)
    rows.pop(3)
    result = score(dataset, rows)["tasks"]["comparison"]
    assert result["false_positive_rate"]["denominator"] == 3
    assert result["false_positive_rate"]["eligible_negative_cases"] == 4
    assert result["false_positive_rate"]["unclassified_negative_ids"] == ["cmp-04"]
    assert result["failure_ids"] == ["cmp-04"]
    empty = score(dataset, [])
    for section in empty["tasks"].values():
        assert section["false_positive_rate"]["rate"] is None
        assert section["citation_validity"]["rate"] == 0
        assert len(section["failure_ids"]) == 9


def test_unnecessary_uncertainty_is_not_hidden_in_false_positive_rate(dataset):
    rows = labelled_observations(dataset)
    rows[3]["output"]["results"][0]["status"] = "needs_clarification"
    result = score(dataset, rows)["tasks"]["comparison"]
    assert result["false_positive_rate"]["numerator"] == 0
    assert result["false_positive_rate"]["unnecessary_uncertainty_ids"] == ["cmp-04"]
    assert result["failure_ids"] == ["cmp-04"]


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown", "wrong_path", "fake_local"]
)
def test_result_binding_and_local_guard_cannot_be_faked(dataset, mutation):
    rows = labelled_observations(dataset)
    if mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "unknown":
        rows[0]["case_id"] = "unrelated"
    elif mutation == "wrong_path":
        rows[0]["path"] = "local_guard"
    else:
        rows[6]["output"]["status"] = "matches"
    if mutation in {"duplicate", "unknown"}:
        with pytest.raises(ValueError):
            score(dataset, rows)
    else:
        assert score(dataset, rows)["cases"][0 if mutation == "wrong_path" else 6][
            "error_code"
        ]


def test_default_command_never_loads_settings_or_constructs_provider(
    monkeypatch, capsys
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Evaluation must not load credentials or call providers")

    monkeypatch.setattr("app.core.config.Settings", forbidden)
    monkeypatch.setattr(
        "app.comparisons.provider.GeminiPolicyComparator.compare", forbidden
    )
    assert main([]) == 0
    assert '"planned_calls": 18' in capsys.readouterr().out


@pytest.mark.parametrize(
    "args",
    [
        ["--live"],
        ["--authorize-live-gemini"],
        ["--live", "--authorize-live-gemini"],
        ["--live", "--authorize-live-gemini", "--max-calls", "19"],
        ["--live", "--authorize-live-gemini", "--max-calls", "18"],
        ["--max-calls", "18"],
    ],
)
def test_opt_in_and_cap_rejected_before_any_settings_access(monkeypatch, args):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unauthorized live configuration access")

    monkeypatch.setattr("app.core.config.Settings", forbidden)
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
