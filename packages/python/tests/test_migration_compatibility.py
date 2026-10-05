import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import yaml

from opf import parse
from opf.core import OPFError
from opf.adapters.crewai import CrewAIAdapter
from opf.adapters.langchain import LangChainAdapter
from opf.adapters.openai import OpenAIPromptAdapter
from opf.compatibility import CompatibilityFinding, CompatibilityReport
from opf.migrate import apply_migration, plan_migration


ROOT = Path(__file__).resolve().parents[3]
SOURCE_NAMESPACE = "com.github.stovo-team.open-prompt-format.source"
LOSS_CODE = "metadata.value.not_json_compatible[created_at]"


class MigrationCompatibilityTests(unittest.TestCase):
    def test_markdown_migration_preserves_nested_frontmatter_and_canonicalizes_roles(self):
        source = ROOT / "packages/python/tests/fixtures/migration/legacy-style-frontmatter.md"
        plan = plan_migration(source, root=ROOT, prompt_id="content.post")
        output = next(iter(plan.output.files.values()))
        prompt = parse(output)
        data = prompt.extensions[SOURCE_NAMESPACE]["data"]
        self.assertEqual(data["source_kind"], "markdown-frontmatter/1")
        self.assertEqual(data["metadata"]["style"]["colors"], {"primary": "#284b63", "accent": "#d98e32"})
        self.assertEqual(data["metadata"]["style"]["chart_style"]["palette"], ["blue", "orange", "gray"])
        self.assertEqual(data["metadata"]["tones"][0], {"label": "Direct", "slot": "linkedin"})
        self.assertIn("## system", output)
        self.assertIn("## user", output)
        self.assertNotIn("\n# system", output)
        self.assertTrue(all("model_alias" not in content for _, content in prompt.messages))
        fields = {finding.source_field for finding in plan.compatibility.findings if finding.category == "preserved_resource"}
        self.assertTrue({"model_alias", "default_model", "response_format", "max_completion_tokens", "style", "tones"}.issubset(fields))

    def test_markdown_role_heading_inside_code_fence_does_not_count_as_a_message(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "example.md"
            path.write_text("```md\n# system\nExample only.\n```", encoding="utf-8")
            plan = plan_migration(path, root=root, prompt_id="example")
            finding = next(item for item in plan.compatibility.findings if item.code == "markdown.role.required")
            self.assertEqual(finding.category, "unsupported")
            self.assertIn("## user", next(iter(plan.output.files.values())))
            self.assertIn("```md\n# system", next(iter(plan.output.files.values())))

    def test_openai_unknown_structured_settings_are_preserved_and_reported(self):
        snapshot = {
            "schema": "openai-prompt-snapshot/1",
            "id": "support",
            "messages": [{"role": "system", "content": "Answer briefly."}],
            "model_settings": {"temperature": 0.2, "format": {"type": "json", "keys": ["state", "detail"]}},
            "custom_ui": {"label": "Support reply", "order": 7, "color": "blue"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            adapter = OpenAIPromptAdapter()
            source = adapter.inspect(path, root=root)
            plan = adapter.plan(source, "support.reply")
            output = parse(next(iter(plan.output.files.values())))
            data = output.extensions["com.openai.responses"]["data"]
            self.assertEqual(data["model_settings"], snapshot["model_settings"])
            self.assertEqual(data["custom_ui"], snapshot["custom_ui"])
            finding = next(item for item in plan.compatibility.findings if item.code == "metadata.preserved.extension")
            self.assertEqual(finding.category, "preserved_resource")
            self.assertEqual(finding.source_field, "custom_ui")
            self.assertNotIn("Support reply", finding.message)

    def test_langchain_unknown_fields_are_kept_as_structured_extension_data(self):
        source_data = {
            "_type": "prompt",
            "template": "Write about {topic}.",
            "input_variables": ["topic"],
            "template_format": "f-string",
            "partial_variables": {"signature": "The team"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "prompt.json"
            path.write_text(json.dumps(source_data), encoding="utf-8")
            adapter = LangChainAdapter()
            source = adapter.inspect(path, root=root)
            plan = adapter.plan(source, "blog.draft")
            prompt = parse(next(iter(plan.output.files.values())))
            extension = prompt.extensions["com.langchain.prompt"]["data"]["fields"]
            self.assertEqual(extension, {"template_format": "f-string", "partial_variables": {"signature": "The team"}})
            finding = next(item for item in plan.compatibility.findings if item.source_field == "partial_variables")
            self.assertEqual(finding.category, "preserved_resource")
            self.assertNotIn("The team", finding.message)

    def test_langchain_complex_template_returns_actionable_manual_finding(self):
        source_data = {"_type": "prompt", "template": "Use {topic!r}.", "input_variables": ["topic"]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "prompt.json"
            path.write_text(json.dumps(source_data), encoding="utf-8")
            adapter = LangChainAdapter()
            source = adapter.inspect(path, root=root)
            plan = adapter.plan(source, "blog.draft")
            finding = next(item for item in plan.compatibility.findings if item.code == "langchain.template.syntax.unsupported")
            self.assertEqual(finding.category, "unsupported")
            self.assertTrue(finding.recommendation)
            self.assertFalse(plan.compatibility.can_apply)
            self.assertEqual(plan.output.files, {})

    def test_crewai_unknown_nested_data_is_preserved_without_becoming_a_message(self):
        source_data = {
            "role": "Writer",
            "goal": "Draft posts",
            "system_template": "Write about {topic}.",
            "brand_style": {"label": "Warm", "order": 2, "palette": ["blue", "gold"]},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "agent.json"
            path.write_text(json.dumps(source_data), encoding="utf-8")
            adapter = CrewAIAdapter()
            source = adapter.inspect(path, root=root)
            plan = adapter.plan(source, "social.writer")
            prompt = parse(next(iter(plan.output.files.values())))
            extension = prompt.extensions["com.crewai.agent"]["data"]
            self.assertEqual(extension["brand_style"], source_data["brand_style"])
            self.assertTrue(all("brand_style" not in content for _, content in prompt.messages))

    def test_non_json_legacy_frontmatter_field_is_named_loss_and_blocks_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "legacy.md"
            path.write_text("---\ncreated_at: !!timestamp 2026-10-05\nlabel: Sample\n---\n\n## system\nReply.", encoding="utf-8")
            plan = plan_migration(path, root=root, prompt_id="reply")
            finding = next(item for item in plan.compatibility.findings if item.category == "data_loss")
            self.assertEqual(finding.code, "metadata.value.not_json_compatible[created_at]")
            self.assertEqual(finding.source_field, "created_at")
            self.assertFalse(plan.compatibility.can_apply)
            self.assertNotIn("2026-10-05", json.dumps(plan.compatibility.to_dict()))
            with self.assertRaisesRegex(ValueError, "not applicable"):
                apply_migration(plan, root=root)
            self.assertFalse((root / "prompts").exists())

    def test_duplicate_frontmatter_keys_are_rejected_without_echoing_private_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.md"
            for frontmatter, secrets in (
                ("private: FIRST_SECRET\nprivate: SECOND_SECRET", ("FIRST_SECRET", "SECOND_SECRET")),
                ("private: [MALFORMED_SECRET", ("MALFORMED_SECRET",)),
            ):
                with self.subTest(frontmatter=frontmatter):
                    source.write_text("---\n{}\n---\n## system\nReply.\n".format(frontmatter), encoding="utf-8")
                    with self.assertRaises(OPFError) as raised:
                        plan_migration(source, root=root, prompt_id="reply")
                    for secret in secrets:
                        self.assertNotIn(secret, str(raised.exception))

    def test_jinja_runtime_limits_have_categories_and_migration_recommendations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "draft.j2"
            path.write_text("{% if company_name %}Hello {{ company_name | title }}{% endif %}", encoding="utf-8")
            plan = plan_migration(path, root=root, prompt_id="draft", role="system", kind="jinja2")
            findings = {finding.code: finding for finding in plan.compatibility.findings}
            self.assertEqual(findings["jinja.template.runtime_required"].category, "adapter_runtime")
            self.assertIn("Jinja", findings["jinja.template.runtime_required"].recommendation)
            self.assertEqual(findings["jinja.template.control_flow"].category, "adapter_runtime")
            self.assertEqual(findings["jinja.template.filter"].category, "adapter_runtime")
            self.assertNotIn("company_name", json.dumps(plan.compatibility.to_dict()))

    def test_jinja_dynamic_include_is_reported_as_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "draft.j2"
            path.write_text("{% include template_path %}", encoding="utf-8")
            plan = plan_migration(path, root=root, prompt_id="draft", role="system", kind="jinja2")
            finding = next(item for item in plan.compatibility.findings if item.code == "jinja.include.dynamic")
            self.assertEqual(finding.category, "unsupported")
            self.assertIn("static include", finding.recommendation)

    def test_strict_apply_refuses_unaccepted_data_loss_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.md"
            source.write_text("## system\nReply.", encoding="utf-8")
            plan = plan_migration(source, root=root, prompt_id="reply")
            finding = CompatibilityFinding(LOSS_CODE, "error", "dropped", "A non-JSON metadata value would be omitted", category="data_loss", source_field="created_at")
            report = CompatibilityReport("markdown", "opf/0.3", (finding,), False, False)
            lossy_plan = replace(plan, compatibility=report)
            with self.assertRaisesRegex(ValueError, "not applicable"):
                apply_migration(lossy_plan, root=root, strict=True)
            self.assertFalse((root / "prompts").exists())

    def test_strict_apply_accepts_only_named_data_loss_and_records_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.md"
            source.write_text("## system\nReply.", encoding="utf-8")
            plan = plan_migration(source, root=root, prompt_id="reply")
            accepted = CompatibilityFinding(LOSS_CODE, "error", "dropped", "A non-JSON value is omitted", category="data_loss", source_field="created_at")
            report = CompatibilityReport("markdown", "opf/0.3", (accepted,), False, False)
            lossy_plan = replace(plan, compatibility=report)
            with self.assertRaisesRegex(ValueError, "requires --register"):
                apply_migration(lossy_plan, root=root, strict=True, accepted_losses={LOSS_CODE})
            self.assertFalse((root / "prompts").exists())
            result = apply_migration(lossy_plan, root=root, strict=True, register=True, accepted_losses={LOSS_CODE})
            self.assertTrue((root / "prompts/reply.opf.md").is_file())
            self.assertEqual(result["manifest_record"]["accepted_losses"], [LOSS_CODE])

    def test_registered_accepted_loss_manifest_round_trips_through_registry(self):
        from opf.registry import Registry

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.md"
            source.write_text("---\ncreated_at: !!timestamp 2026-10-05\n---\n## system\nReply.\n", encoding="utf-8")
            plan = plan_migration(source, root=root, prompt_id="reply")
            code = next(item.code for item in plan.compatibility.findings if item.category == "data_loss")
            result = apply_migration(plan, root=root, strict=True, register=True, accepted_losses={code})
            manifest_path = root / ".opf/migrations.yaml"
            manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest_data["migrations"]["reply"].pop("accepted_losses")
            manifest_data["migrations"]["reply"]["findings"] = []
            manifest_path.write_text(yaml.safe_dump(manifest_data, sort_keys=False), encoding="utf-8")
            # An older record may lack both approval and the newly categorized loss finding.
            apply_migration(plan, root=root, strict=True, register=True, accepted_losses={code})
            loaded = Registry.local(root / "opf.yaml")
            record = loaded.config["migration_manifest"]
            self.assertEqual(result["manifest_record"]["accepted_losses"], [code])
            self.assertEqual(record, ".opf/migrations.yaml")
            manifest = loaded.migration_manifest["migrations"]["reply"]
            self.assertEqual(manifest["accepted_losses"], [code])
            finding = next(item for item in manifest["findings"] if item["code"] == code)
            self.assertEqual(finding["category"], "data_loss")
            self.assertEqual(finding["source_field"], "created_at")

    def test_accepting_one_loss_does_not_bypass_another_finding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.md"
            source.write_text("## system\nReply.", encoding="utf-8")
            plan = plan_migration(source, root=root, prompt_id="reply")
            findings = (
                CompatibilityFinding(LOSS_CODE, "error", "dropped", "Field omitted", category="data_loss"),
                CompatibilityFinding("jinja.include.dynamic", "error", "manual", "Dynamic dependency is unresolved", category="unsupported"),
            )
            report = CompatibilityReport("markdown", "opf/0.3", findings, False, False)
            lossy_plan = replace(plan, compatibility=report)
            with self.assertRaisesRegex(ValueError, "not applicable"):
                apply_migration(lossy_plan, root=root, strict=True, register=True, accepted_losses={LOSS_CODE})
            self.assertFalse((root / "prompts").exists())

    def test_cli_accept_loss_passes_exact_codes_to_apply(self):
        from opf.cli import main
        import contextlib
        import io
        import sys

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.md"
            source.write_text("## system\nReply.", encoding="utf-8")
            output = io.StringIO()
            argv = ["opf", "migrate", "apply", str(source), "--root", str(root), "--strict", "--accept-loss", LOSS_CODE]
            with patch.object(sys, "argv", argv), patch("opf.cli.apply_migration", return_value={"prompt_id": "reply", "written": []}) as apply:
                with contextlib.redirect_stdout(output):
                    main()
            self.assertEqual(apply.call_args.kwargs["accepted_losses"], {LOSS_CODE})


if __name__ == "__main__":
    unittest.main()
