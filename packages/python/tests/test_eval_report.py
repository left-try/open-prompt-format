import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.compare_promptfoo_results import compare_results, exit_code_for_report


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "packages/python/tests/fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class PromptfooComparisonTests(unittest.TestCase):
    def test_exit_policy_is_opt_in_for_regressions_and_always_fails_errors(self):
        report = compare_results(load_fixture("promptfoo-baseline-v3.json"), load_fixture("promptfoo-candidate-v3.json"))
        report["summary"]["errors"] = 0
        self.assertEqual(exit_code_for_report(report), 0)
        self.assertEqual(exit_code_for_report(report, block_on_regression=True), 1)
        report["summary"]["errors"] = 1
        self.assertEqual(exit_code_for_report(report), 1)

    def test_classifies_unchanged_regression_recovery_error_and_ungraded_cases(self):
        baseline = load_fixture("promptfoo-baseline-v3.json")
        candidate = load_fixture("promptfoo-candidate-v3.json")

        report = compare_results(baseline, candidate)
        states = {
            (item["case_id"], item["provider_id"]): item["change"]
            for item in report["cases"]
        }

        self.assertEqual(report["schema"], "opf-eval-comparison/1")
        self.assertEqual(report["status"], "regression")
        self.assertEqual(
            states,
            {
                ("test-0000", "anthropic:mock-model"): "regression",
                ("test-0000", "openai:mock-model"): "unchanged",
                ("test-0001", "anthropic:mock-model"): "error",
                ("test-0001", "openai:mock-model"): "recovered",
                ("test-0002", "openai:mock-model"): "ungraded",
            },
        )
        self.assertEqual(report["summary"]["regressions"], 1)
        self.assertEqual(report["summary"]["recovered"], 1)
        self.assertEqual(report["summary"]["errors"], 1)

    def test_unchanged_passing_results_have_zero_deltas(self):
        baseline = load_fixture("promptfoo-baseline-v3.json")
        for row in baseline["results"]["results"]:
            row["success"] = True
            row["score"] = 1.0
            row["gradingResult"] = {"pass": True, "score": 1.0}
        candidate = copy.deepcopy(baseline)

        report = compare_results(baseline, candidate)

        self.assertEqual(report["status"], "unchanged")
        self.assertTrue(all(item["change"] == "unchanged" for item in report["cases"]))
        self.assertEqual(report["summary"]["regressions"], 0)

    def test_all_ungraded_rows_are_not_reported_as_unchanged(self):
        baseline = load_fixture("promptfoo-baseline-v3.json")
        for row in baseline["results"]["results"]:
            row["success"] = None
            row["gradingResult"] = None
        report = compare_results(baseline, copy.deepcopy(baseline))
        self.assertEqual(report["status"], "ungraded")
        self.assertEqual(report["summary"]["ungraded"], len(report["cases"]))

    def test_baseline_provider_error_is_not_hidden_as_a_behavior_change(self):
        baseline = load_fixture("promptfoo-baseline-v3.json")
        candidate = load_fixture("promptfoo-candidate-v3.json")
        baseline_row = baseline["results"]["results"][1]
        baseline_row["success"] = False
        baseline_row["error"] = "PRIVATE_BASELINE_ERROR"
        baseline_row.pop("gradingResult", None)
        report = compare_results(baseline, candidate)
        self.assertEqual(report["cases"][0]["change"], "error")
        self.assertGreater(report["summary"]["errors"], 0)
        self.assertNotIn("PRIVATE_BASELINE_ERROR", json.dumps(report))

    def test_rejects_different_provider_or_test_matrices(self):
        baseline = load_fixture("promptfoo-baseline-v3.json")
        candidate = load_fixture("promptfoo-candidate-v3.json")
        candidate["results"]["providers"].pop()

        with self.assertRaisesRegex(ValueError, "provider matrix"):
            compare_results(baseline, candidate)

        candidate = load_fixture("promptfoo-candidate-v3.json")
        for row in candidate["results"]["results"]:
            row["promptIdx"] = 1
        with self.assertRaisesRegex(ValueError, "prompt index matrix"):
            compare_results(baseline, candidate)

        candidate = load_fixture("promptfoo-candidate-v3.json")
        candidate["results"]["results"].pop()
        with self.assertRaisesRegex(ValueError, "test/provider matrix"):
            compare_results(baseline, candidate)

    def test_rejects_unsupported_promptfoo_result_schema(self):
        baseline = load_fixture("promptfoo-baseline-v3.json")
        candidate = load_fixture("promptfoo-candidate-v3.json")
        candidate["results"]["version"] = 2

        with self.assertRaisesRegex(ValueError, "version 3"):
            compare_results(baseline, candidate)

    def test_cli_writes_only_sanitized_comparison_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/compare_promptfoo_results.py"),
                    "--baseline",
                    str(FIXTURES / "promptfoo-baseline-v3.json"),
                    "--candidate",
                    str(FIXTURES / "promptfoo-candidate-v3.json"),
                    "--baseline-commit",
                    "base-sha",
                    "--candidate-commit",
                    "candidate-sha",
                    "--block-on-regression",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.strip(), "")
            report_text = output.read_text(encoding="utf-8")
            report = json.loads(report_text)
            self.assertEqual(report["baseline_commit"], "base-sha")
            self.assertEqual(report["candidate_commit"], "candidate-sha")
            for private_value in ("PRIVATE_PROMPT", "PRIVATE_INPUT", "PRIVATE_OUTPUT", "PRIVATE_REASON", "PRIVATE_ERROR", "PRIVATE_KEY"):
                self.assertNotIn(private_value, report_text)

    def test_cli_returns_distinct_error_code_for_invalid_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            malformed = Path(temporary) / "bad.json"
            output = Path(temporary) / "comparison.json"
            malformed.write_text("{}", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/compare_promptfoo_results.py"),
                    "--baseline",
                    str(malformed),
                    "--candidate",
                    str(FIXTURES / "promptfoo-candidate-v3.json"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())

    def test_cli_rejects_oversized_promptfoo_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            malformed = Path(temporary) / "large.json"
            output = Path(temporary) / "comparison.json"
            malformed.write_bytes(b" " * (25 * 1024 * 1024 + 1))
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/compare_promptfoo_results.py"),
                 "--baseline", str(malformed), "--candidate", str(FIXTURES / "promptfoo-candidate-v3.json"),
                 "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("25 MiB", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
