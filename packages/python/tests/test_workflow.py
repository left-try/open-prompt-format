import unittest
import tempfile
import subprocess
import os
from pathlib import Path

import yaml
from scripts.prepare_promptfoo_pair import prepare_pair


ROOT = Path(__file__).resolve().parents[3]


class ReusableWorkflowTests(unittest.TestCase):
    def test_reusable_workflow_checks_consumer_without_secrets(self):
        workflow_path = ROOT / ".github/workflows/opf-check.yml"
        self.assertTrue(workflow_path.is_file(), "reusable OPF workflow is missing")
        workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

        call = workflow["on"]["workflow_call"]
        self.assertEqual(call["inputs"]["project-path"]["default"], ".")
        self.assertEqual(call["inputs"]["registry"]["default"], "opf.yaml")
        self.assertTrue(call["inputs"]["opf-version"]["required"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})

        job = workflow["jobs"]["opf-check"]
        checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["fetch-depth"], "0")
        self.assertEqual(job["defaults"]["run"]["working-directory"], "${{ inputs.project-path }}")
        install = next(step for step in job["steps"] if step.get("name") == "Install the pinned OPF package")
        self.assertEqual(install["env"]["OPF_VERSION"], "${{ inputs.opf-version }}")
        commands = "\n".join(step.get("run", "") for step in job["steps"])
        self.assertIn("open-prompt-format==$OPF_VERSION", commands)
        self.assertIn("opf check", commands)
        self.assertIn("opf verify-all", commands)
        self.assertNotIn("OPENAI_API_KEY", str(job))
        self.assertNotIn("ANTHROPIC_API_KEY", str(job))

    def test_opt_in_eval_uses_paired_pinned_prompts_and_protected_environment(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/opf-check.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        call = workflow["on"]["workflow_call"]["inputs"]
        self.assertEqual(call["run-eval"]["default"], "false")
        self.assertEqual(call["block-on-regression"]["default"], "false")
        dispatch = workflow["on"]["workflow_dispatch"]["inputs"]
        self.assertIn("base-ref", dispatch)
        self.assertEqual(dispatch["opf-version"]["default"], "0.2.0")

        job = workflow["jobs"]["prompt-eval"]
        self.assertEqual(job["environment"]["name"], "prompt-eval")
        self.assertIn("github.event_name == 'workflow_dispatch'", job["if"])
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", job["if"])
        commands = "\n".join(step.get("run", "") for step in job["steps"])
        self.assertEqual(commands.count("compare_promptfoo_results.py"), 1)
        expressions = "\n".join(str(step.get("env", {})) for step in job["steps"])
        self.assertIn("github.event.pull_request.base.sha", expressions + commands)
        self.assertIn("inputs.base-ref", expressions + commands)
        self.assertIn('["git", "archive"', (ROOT / "scripts/prepare_promptfoo_pair.py").read_text(encoding="utf-8"))
        self.assertIn("github.sha", expressions + commands)
        self.assertIn("promptfoo@0.123.1 eval", commands)
        self.assertIn("--no-share", commands)
        self.assertIn("BLOCK_ON_REGRESSION", commands)
        self.assertIn("summary']['regressions", commands)
        fork_note = next(step for step in workflow["jobs"]["opf-check"]["steps"] if step.get("name") == "Note that fork evaluations are skipped")
        self.assertIn("github.event.pull_request.head.repo.full_name != github.repository", fork_note["if"])
        self.assertIn("OPF_PROMPT_FILE", (ROOT / "scripts/prepare_promptfoo_pair.py").read_text(encoding="utf-8"))
        self.assertNotIn("production", commands)
        self.assertIn("OPENAI_API_KEY", str(job))
        self.assertIn("ANTHROPIC_API_KEY", str(job))

    def test_pair_preparation_uses_base_and_candidate_files_with_same_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "prompt.md").write_text("base prompt\n", encoding="utf-8")
            (root / "eval.yaml").write_text(
                "providers:\n  - openai:test\ntests:\n  - vars: {x: y}\n", encoding="utf-8"
            )
            subprocess.run(["git", "add", "prompt.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base_ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            (root / "prompt.md").write_text("candidate prompt\n", encoding="utf-8")
            original_cwd = os.getcwd()
            try:
                os.chdir(root)
                baseline_config, candidate_config = prepare_pair(
                    base_ref, "prompt.md", "eval.yaml", "tmp-pair", adapter_path="adapter.cjs"
                )
            finally:
                os.chdir(original_cwd)
            baseline = yaml.safe_load(baseline_config.read_text(encoding="utf-8"))
            candidate = yaml.safe_load(candidate_config.read_text(encoding="utf-8"))
            self.assertEqual(baseline_config.parent, root)
            self.assertEqual(candidate_config.parent, root)
            self.assertEqual(baseline["providers"], candidate["providers"])
            self.assertEqual(baseline["tests"], candidate["tests"])
            self.assertEqual(Path(baseline["env"]["OPF_PROMPT_FILE"]).read_text(), "base prompt\n")
            self.assertEqual(Path(candidate["env"]["OPF_PROMPT_FILE"]).read_text(), "candidate prompt\n")
            self.assertEqual(len(baseline["prompts"]), 1)
            self.assertEqual(baseline["prompts"], candidate["prompts"])

    def test_pair_preparation_supports_a_project_nested_in_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "service"
            project.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (project / "prompt.md").write_text("base nested prompt\n", encoding="utf-8")
            (project / "eval.yaml").write_text("providers: [openai:test]\ntests: [{vars: {x: y}}]\n", encoding="utf-8")
            subprocess.run(["git", "add", "service/prompt.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base_ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            (project / "prompt.md").write_text("candidate nested prompt\n", encoding="utf-8")
            baseline_config, candidate_config = prepare_pair(
                base_ref, "prompt.md", "eval.yaml", str(root / "pair"),
                repo_root=str(root), project_path="service",
            )
            baseline = yaml.safe_load(baseline_config.read_text(encoding="utf-8"))
            candidate = yaml.safe_load(candidate_config.read_text(encoding="utf-8"))
            self.assertEqual(Path(baseline["env"]["OPF_PROMPT_FILE"]).read_text(), "base nested prompt\n")
            self.assertEqual(Path(candidate["env"]["OPF_PROMPT_FILE"]).read_text(), "candidate nested prompt\n")


if __name__ == "__main__":
    unittest.main()
