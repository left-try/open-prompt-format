"""Compare two Promptfoo JSON exports and write a report without private eval data."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 25 * 1024 * 1024


def _require_object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError("{} must be a JSON object".format(label))
    return value


def _provider_ids(payload: dict, label: str) -> tuple[str, ...]:
    results = _require_object(payload.get("results"), "{}.results".format(label))
    if results.get("version") != 3:
        raise ValueError("{} must use Promptfoo result JSON version 3".format(label))
    providers = results.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError("{}.results.providers must be a non-empty list".format(label))
    ids = []
    for index, provider in enumerate(providers):
        provider = _require_object(provider, "{}.results.providers[{}]".format(label, index))
        identifier = provider.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("{}.results.providers[{}].id must be a non-empty string".format(label, index))
        ids.append(identifier)
    if len(set(ids)) != len(ids):
        raise ValueError("{}.results.providers contains duplicate provider ids".format(label))
    return tuple(sorted(ids))


def _row_provider(row: dict, label: str, index: int) -> str:
    value = row.get("providerId", row.get("provider"))
    if isinstance(value, dict):
        value = value.get("id")
    if not isinstance(value, str) or not value:
        raise ValueError("{} result {} is missing provider identity".format(label, index))
    return value


def _result_rows(payload: dict, label: str, provider_ids: tuple[str, ...]) -> dict[tuple[int, str], dict]:
    results = payload["results"].get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("{}.results.results must be a non-empty list".format(label))
    rows = {}
    prompt_indices = set()
    for index, value in enumerate(results):
        row = _require_object(value, "{}.results.results[{}]".format(label, index))
        test_index = row.get("testIdx")
        prompt_index = row.get("promptIdx")
        if isinstance(test_index, bool) or not isinstance(test_index, int) or test_index < 0:
            raise ValueError("{} result {} has an invalid testIdx".format(label, index))
        if isinstance(prompt_index, bool) or not isinstance(prompt_index, int) or prompt_index < 0:
            raise ValueError("{} result {} has an invalid promptIdx".format(label, index))
        prompt_indices.add(prompt_index)
        provider_id = _row_provider(row, label, index)
        if provider_id not in provider_ids:
            raise ValueError("{} result {} references an unknown provider".format(label, index))
        key = (test_index, provider_id)
        if key in rows:
            raise ValueError("{} contains duplicate test/provider results".format(label))
        score = row.get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score)):
            raise ValueError("{} result {} has an invalid score".format(label, index))
        rows[key] = row
    if len(prompt_indices) != 1:
        raise ValueError("{} must contain exactly one prompt per eval".format(label))
    return rows


def _state(row: dict) -> str:
    if row.get("error"):
        return "error"
    grading = row.get("gradingResult")
    if not isinstance(grading, dict) or not isinstance(grading.get("pass"), bool):
        return "ungraded"
    return "passed" if row.get("success") is True and grading["pass"] else "failed"


def _change(before: str, after: str, before_score: float | None, after_score: float | None) -> str:
    if before == "error" or after == "error":
        return "error"
    if before == "passed" and after == "failed":
        return "regression"
    if before == "failed" and after == "passed":
        return "recovered"
    if before == "ungraded" and after == "ungraded":
        return "ungraded"
    if before != after or before_score != after_score:
        return "changed"
    return "unchanged"


def _score(row: dict) -> float | None:
    score = row.get("score")
    return float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None


def compare_results(
    baseline: dict,
    candidate: dict,
    *,
    baseline_commit: str | None = None,
    candidate_commit: str | None = None,
) -> dict:
    """Compare Promptfoo v3 JSON exports and retain only non-sensitive result fields."""
    baseline = _require_object(baseline, "baseline")
    candidate = _require_object(candidate, "candidate")
    baseline_providers = _provider_ids(baseline, "baseline")
    candidate_providers = _provider_ids(candidate, "candidate")
    if baseline_providers != candidate_providers:
        raise ValueError("baseline and candidate provider matrix differs")
    before_rows = _result_rows(baseline, "baseline", baseline_providers)
    after_rows = _result_rows(candidate, "candidate", candidate_providers)
    baseline_prompt_indices = {row["promptIdx"] for row in before_rows.values()}
    candidate_prompt_indices = {row["promptIdx"] for row in after_rows.values()}
    if baseline_prompt_indices != candidate_prompt_indices:
        raise ValueError("baseline and candidate prompt index matrix differs")
    if before_rows.keys() != after_rows.keys():
        raise ValueError("baseline and candidate test/provider matrix differs")

    cases = []
    counts = {"unchanged": 0, "regression": 0, "recovered": 0, "changed": 0, "error": 0, "ungraded": 0}
    outcome_counts = {
        label: {"passed": 0, "failed": 0, "error": 0, "ungraded": 0}
        for label in ("baseline", "candidate")
    }
    for test_index, provider_id in sorted(before_rows):
        before = before_rows[(test_index, provider_id)]
        after = after_rows[(test_index, provider_id)]
        before_state = _state(before)
        after_state = _state(after)
        change = _change(before_state, after_state, _score(before), _score(after))
        counts[change] += 1
        outcome_counts["baseline"][before_state] += 1
        outcome_counts["candidate"][after_state] += 1
        cases.append(
            {
                "case_id": "test-{:04d}".format(test_index),
                "provider_id": provider_id,
                "baseline": {"state": before_state, "score": _score(before)},
                "candidate": {"state": after_state, "score": _score(after)},
                "change": change,
            }
        )
    if counts["regression"]:
        status = "regression"
    elif counts["error"]:
        status = "error"
    elif counts["ungraded"] == len(cases):
        status = "ungraded"
    elif counts["recovered"]:
        status = "improved"
    elif counts["changed"]:
        status = "changed"
    else:
        status = "unchanged"

    def eval_id(payload):
        value = payload.get("evalId")
        return value if isinstance(value, str) else None

    return {
        "schema": "opf-eval-comparison/1",
        "status": status,
        "baseline_eval_id": eval_id(baseline),
        "candidate_eval_id": eval_id(candidate),
        "baseline_commit": baseline_commit,
        "candidate_commit": candidate_commit,
        "matrix": {
            "providers": list(baseline_providers),
            "prompt_index": next(iter(baseline_prompt_indices)),
            "tests": sorted({key[0] for key in before_rows}),
        },
        "summary": {
            "baseline": outcome_counts["baseline"],
            "candidate": outcome_counts["candidate"],
            "regressions": counts["regression"],
            "recovered": counts["recovered"],
            "changed": counts["changed"],
            "errors": counts["error"],
            "ungraded": counts["ungraded"],
        },
        "cases": cases,
    }


def exit_code_for_report(report: dict, *, block_on_regression: bool = False) -> int:
    """Errors always fail; valid regressions fail only when explicitly blocking."""
    summary = report["summary"]
    if summary["errors"] or block_on_regression and summary["regressions"]:
        return 1
    return 0


def _read(path: str) -> dict:
    try:
        if Path(path).stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("Promptfoo JSON exceeds the 25 MiB safety limit")
        with open(path, "r", encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read {}: {}".format(path, exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Promptfoo v3 baseline JSON export")
    parser.add_argument("--candidate", required=True, help="Promptfoo v3 candidate JSON export")
    parser.add_argument("--baseline-commit")
    parser.add_argument("--candidate-commit")
    parser.add_argument("--output", required=True, help="path for sanitized comparison JSON")
    parser.add_argument("--block-on-regression", action="store_true", help="return nonzero for a valid comparison with regressions")
    args = parser.parse_args()
    try:
        report = compare_results(
            _read(args.baseline),
            _read(args.candidate),
            baseline_commit=args.baseline_commit,
            candidate_commit=args.candidate_commit,
        )
        destination = Path(args.output)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print("compare_promptfoo_results: {}".format(exc), file=sys.stderr)
        return 2
    return exit_code_for_report(report, block_on_regression=args.block_on_regression)


if __name__ == "__main__":
    raise SystemExit(main())
