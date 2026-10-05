import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opf.check import check
from opf.cli import main
from opf.compatibility import CompatibilityFinding


PROMPT = """---
format: opf/0.3
id: demo.heading
---

# system
PRIVATE PROMPT BODY
"""


class CompatibilityTests(unittest.TestCase):
    def test_findings_serialize_each_category_and_optional_context(self):
        categories = ("portable", "preserved_resource", "adapter_runtime", "unsupported", "data_loss")
        for category in categories:
            with self.subTest(category=category):
                finding = CompatibilityFinding(
                    code="sample.finding",
                    severity="warning",
                    disposition="preserved",
                    message="A safe summary",
                    category=category,
                    source_path="prompt.md",
                    source_line=6,
                    source_field="extensions.example.data",
                    recommendation="Use the portable core form.",
                )
                value = finding.to_dict()
                self.assertEqual(value["category"], category)
                self.assertEqual(value["source_line"], 6)
                self.assertEqual(value["source_field"], "extensions.example.data")
                self.assertEqual(value["recommendation"], "Use the portable core form.")

    def test_findings_omit_unset_optional_context(self):
        finding = CompatibilityFinding("sample.finding", "info", "preserved", "Safe summary")
        value = finding.to_dict()
        self.assertNotIn("category", value)
        self.assertNotIn("source_line", value)
        self.assertNotIn("source_field", value)
        self.assertNotIn("recommendation", value)

    def test_check_exposes_heading_advisory_with_location_without_prompt_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "prompt.opf.md").write_text(PROMPT, encoding="utf-8")
            findings = check(root, safety=False)
            finding = next(item for item in findings if item.code == "heading.noncanonical.single_hash")
            value = finding.to_dict()
            self.assertEqual(value["category"], "portable")
            self.assertEqual(value["line"], 6)
            self.assertIn("## system", value["recommendation"])
            self.assertNotIn("PRIVATE PROMPT BODY", json.dumps(value))

    def test_check_json_does_not_fail_strict_mode_for_info_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "prompt.opf.md").write_text(PROMPT, encoding="utf-8")
            output = io.StringIO()
            argv = ["opf", "check", str(root), "--format", "json", "--no-safety", "--strict"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
                main()
            report = json.loads(output.getvalue())
            self.assertTrue(any(item["code"] == "heading.noncanonical.single_hash" for item in report))
            self.assertNotIn("PRIVATE PROMPT BODY", output.getvalue())

    def test_check_text_includes_actionable_recommendation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "prompt.opf.md").write_text(PROMPT, encoding="utf-8")
            output = io.StringIO()
            argv = ["opf", "check", str(root), "--no-safety"]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
                main()
            self.assertIn("heading.noncanonical.single_hash", output.getvalue())
            self.assertIn("Recommendation: Use '## system'", output.getvalue())
            self.assertNotIn("PRIVATE PROMPT BODY", output.getvalue())

    def test_compat_text_includes_category_and_recommendation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prompt.opf.md"
            path.write_text(PROMPT, encoding="utf-8")
            output = io.StringIO()
            argv = ["opf", "compat", str(path)]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
                main()
            self.assertIn("[portable]", output.getvalue())
            self.assertIn("Recommendation:", output.getvalue())
            self.assertNotIn("PRIVATE PROMPT BODY", output.getvalue())

    def test_check_reports_registered_jinja_runtime_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompts = root / "prompts"
            prompts.mkdir()
            (prompts / "system.j2").write_text("{% if company %}Hello {{ company | title }}{% endif %}", encoding="utf-8")
            (root / "opf.yaml").write_text(
                "schema: opf-registry/1\nprompts:\n  demo.reply:\n    renderer: jinja2\n    messages:\n      - role: system\n        file: prompts/system.j2\n",
                encoding="utf-8",
            )
            findings = check(root, safety=False)
            codes = {item.code for item in findings}
            self.assertIn("jinja.template.runtime_required", codes)
            self.assertIn("jinja.template.control_flow", codes)
            self.assertIn("jinja.template.filter", codes)
            self.assertTrue(all(item.category == "adapter_runtime" for item in findings if item.code.startswith("jinja.template.")))
            self.assertNotIn("Hello", json.dumps([item.to_dict() for item in findings]))


if __name__ == "__main__":
    unittest.main()
