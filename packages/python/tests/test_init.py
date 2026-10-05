import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from opf.core import OPFError
from opf.init import initialize

ROOT = Path(__file__).resolve().parents[3]


class InitGitHubTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_init_github_creates_read_only_workflow_call(self):
        result = initialize(self.root, install_github_workflow=True, update_agents=False)
        workflow_path = self.root / ".github/workflows/opf.yml"
        workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

        self.assertEqual(result.created, ("prompts/example.prompt.md", "opf.yaml", ".github/workflows/opf.yml"))
        self.assertIn("pull_request", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        called = workflow["jobs"]["opf-check"]
        self.assertEqual(
            called["uses"],
            "stovo-team/open-prompt-format/.github/workflows/opf-check.yml@v0.2.0",
        )
        self.assertEqual(
            called["with"],
            {"project-path": ".", "registry": "opf.yaml", "opf-version": "0.2.0"},
        )
        self.assertNotIn("secrets", called)

    def test_init_github_refuses_existing_workflow_without_partial_writes(self):
        workflow_path = self.root / ".github/workflows/opf.yml"
        workflow_path.parent.mkdir(parents=True)
        workflow_path.write_text("name: my existing workflow\n", encoding="utf-8")

        with self.assertRaisesRegex(OPFError, "refusing to overwrite existing file"):
            initialize(self.root, install_github_workflow=True)

        self.assertFalse((self.root / "prompts/example.prompt.md").exists())
        self.assertFalse((self.root / "opf.yaml").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(workflow_path.read_text(encoding="utf-8"), "name: my existing workflow\n")

    def test_init_github_is_idempotent(self):
        first = initialize(self.root, install_github_workflow=True)
        second = initialize(self.root, install_github_workflow=True)

        self.assertIn(".github/workflows/opf.yml", first.created)
        self.assertEqual(second.created, ())
        self.assertFalse(second.agents_updated)
        self.assertEqual(len(list((self.root / ".github/workflows").glob("opf.yml"))), 1)

    def test_cli_init_github_reports_created_workflow(self):
        result = subprocess.run(
            [sys.executable, "-m", "opf.cli", "init", str(self.root), "--github", "--agents", "no"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "packages/python/src")},
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(".github/workflows/opf.yml", json.loads(result.stdout)["created"])
        self.assertTrue((self.root / ".github/workflows/opf.yml").exists())


if __name__ == "__main__":
    unittest.main()
