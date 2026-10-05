import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


class StarterTemplateTests(unittest.TestCase):
    def test_clean_copy_checks_prompts_registry_and_workflow_pin_without_provider_calls(self):
        template = ROOT / "examples/starter-template"
        self.assertTrue(template.is_dir(), "starter template is missing")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "starter"
            shutil.copytree(template, target)
            env = {**os.environ, "PYTHONPATH": str(ROOT / "packages/python/src")}
            run_cli = [sys.executable, "-c", "from opf.cli import main; main()"]
            checked = subprocess.run(run_cli + ["check", ".", "--registry", "opf.yaml"], cwd=target, env=env, capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            collection = subprocess.run(run_cli + ["validate-collection", "prompts"], cwd=target, env=env, capture_output=True, text=True)
            self.assertEqual(collection.returncode, 0, collection.stdout + collection.stderr)
            self.assertIn("valid: 1 prompt(s)", collection.stdout)
            verified = subprocess.run(run_cli + ["verify-all", "--registry", "opf.yaml"], cwd=target, env=env, capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            workflow = (target / ".github/workflows/opf.yml").read_text(encoding="utf-8")
            self.assertIn("stovo-team/open-prompt-format/.github/workflows/opf-check.yml@v0.2.0", workflow)
            self.assertIn("default: false", workflow)
            self.assertNotIn("OPENAI_API_KEY", workflow)
            self.assertNotIn("ANTHROPIC_API_KEY", workflow)
            eval_config = yaml.safe_load((target / "evals/promptfooconfig.yaml").read_text(encoding="utf-8"))
            self.assertNotIn("providers", eval_config, "providers are explicitly opt-in")
            self.assertEqual(len(eval_config["tests"]), 4)


if __name__ == "__main__":
    unittest.main()
