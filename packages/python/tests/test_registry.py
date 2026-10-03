import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from opf import OPFError, Registry
from opf.publish import langfuse_plan, publish_langfuse

ROOT = Path(__file__).resolve().parents[3]


PROMPT = """---
format: opf/0.2
id: support.reply
inputs:
  question:
    type: string
---

## system
Answer briefly.

## user
{{ question }}
"""


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


class RegistryTests(unittest.TestCase):
    def test_shared_bundle_digest(self):
        for relative in ("fixtures/registry-digest.json", "fixtures/registry-unicode/digest.json"):
            with self.subTest(fixture=relative):
                fixture = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                bundle = Registry.local(ROOT / fixture["config"]).get(fixture["id"]).bundle
                self.assertEqual(bundle["digest"], fixture["bundle_digest"])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "prompts").mkdir()
        (self.root / "prompts/reply.md").write_text(PROMPT, encoding="utf-8")
        (self.root / "opf.yaml").write_text(
            "schema: opf-registry/1\nprompts:\n  support.reply:\n    renderer: opf\n    source: prompts/reply.md\n",
            encoding="utf-8",
        )
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "OPF Tests")
        git(self.root, "config", "user.email", "opf@example.invalid")
        git(self.root, "add", "opf.yaml", "prompts")
        git(self.root, "commit", "-qm", "initial prompt")

    def test_release_channel_export_and_receipt(self):
        registry = Registry.local(self.root / "opf.yaml")
        release = registry.release("support.reply", "1.0.0")
        self.assertRegex(release["digest"], r"^sha256:[0-9a-f]{64}$")
        with self.assertRaisesRegex(OPFError, "already exists"):
            registry.release("support.reply", "1.0.0")
        registry.promote("support.reply", "1.0.0", "production")
        released = Registry.local(self.root / "opf.yaml").get("support.reply", channel="production")
        prepared = released.render({"question": "Hello"})
        self.assertEqual(prepared.messages[1]["content"], "Hello")
        self.assertEqual(prepared.receipt["bundle_digest"], release["digest"])
        self.assertEqual(prepared.call_receipt(provider="openai", model="chosen-model")["model"], "chosen-model")
        self.assertNotIn("question", prepared.receipt)

        cli = subprocess.run(
            [sys.executable, "-m", "opf.cli", "render", "support.reply", "--registry", "opf.yaml", "--channel", "production", "--input", "question=Hello", "--receipt"],
            cwd=self.root,
            env={**os.environ, "PYTHONPATH": str(ROOT / "packages/python/src")},
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(cli.stdout)["receipt"]["bundle_digest"], release["digest"])
        verified = subprocess.run(
            [sys.executable, "-m", "opf.cli", "verify-all", "--registry", "opf.yaml"],
            cwd=self.root,
            env={**os.environ, "PYTHONPATH": str(ROOT / "packages/python/src")},
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(verified.stdout)[0]["digest"], release["digest"])

        (self.root / "prompts/reply.md").write_text(PROMPT.replace("Answer briefly.", "Answer at length."), encoding="utf-8")
        still_released = Registry.local(self.root / "opf.yaml").get("support.reply", channel="production")
        self.assertEqual(still_released.render({"question": "Hello"}).messages[0]["content"], "Answer briefly.")

        output = self.root / "release.json"
        registry.export("support.reply", "1.0.0", output)
        self.assertEqual(Registry.from_bundle(output).render({"question": "Hello"}).messages, prepared.messages)
        altered = json.loads(output.read_text(encoding="utf-8"))
        altered["files"]["prompts/reply.md"] = altered["files"]["prompts/reply.md"].replace("briefly", "badly")
        output.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaisesRegex(OPFError, "digest"):
            Registry.from_bundle(output)

        config = self.root / "opf.yaml"
        config.write_text(config.read_text(encoding="utf-8").replace(release["digest"], "sha256:" + "0" * 64), encoding="utf-8")
        with self.assertRaisesRegex(OPFError, "channel digest mismatch"):
            Registry.local(config).get("support.reply", channel="production")

    def test_dirty_source_cannot_be_released(self):
        (self.root / "prompts/reply.md").write_text(PROMPT.replace("briefly", "clearly"), encoding="utf-8")
        with self.assertRaisesRegex(OPFError, "commit"):
            Registry.local(self.root / "opf.yaml").release("support.reply", "1.0.0")

    def test_moved_tag_with_old_digest_is_rejected(self):
        registry = Registry.local(self.root / "opf.yaml")
        release = registry.release("support.reply", "1.0.0")
        (self.root / "prompts/reply.md").write_text(PROMPT.replace("briefly", "differently"), encoding="utf-8")
        git(self.root, "add", "prompts/reply.md")
        git(self.root, "commit", "-qm", "change prompt")
        git(self.root, "tag", "-fa", "opf/support.reply/v1.0.0", "-m", json.dumps(release), "HEAD")
        with self.assertRaisesRegex(OPFError, "digest mismatch"):
            registry.get("support.reply", version="1.0.0")

    def test_jinja_includes_and_dynamic_dependency(self):
        (self.root / "prompts/system.md").write_text("You are {{ name }}.", encoding="utf-8")
        (self.root / "prompts/user.j2").write_text('{% include "fragment.j2" %}', encoding="utf-8")
        (self.root / "prompts/fragment.j2").write_text("Hello {{ name }}", encoding="utf-8")
        (self.root / "opf.yaml").write_text(
            "schema: opf-registry/1\nprompts:\n  legacy:\n    renderer: jinja2\n    messages:\n      - role: system\n        file: prompts/system.md\n      - role: user\n        file: prompts/user.j2\n",
            encoding="utf-8",
        )
        git(self.root, "add", "opf.yaml", "prompts")
        git(self.root, "commit", "-qm", "add Jinja prompt")
        registry = Registry.local(self.root / "opf.yaml")
        self.assertEqual(registry.get("legacy").render({"name": "Ada"}).messages[1]["content"], "Hello Ada")
        registry.release("legacy", "1.0.0")
        (self.root / "prompts/fragment.j2").write_text("Goodbye {{ name }}", encoding="utf-8")
        self.assertEqual(registry.get("legacy", version="1.0.0").render({"name": "Ada"}).messages[1]["content"], "Hello Ada")
        (self.root / "prompts/user.j2").write_text("{% include selected %}", encoding="utf-8")
        with self.assertRaisesRegex(OPFError, "dynamic Jinja include"):
            registry.release("legacy", "1.0.1")

    def test_langfuse_publish_is_idempotent_and_remote_bundle_loads(self):
        registry = Registry.local(self.root / "opf.yaml")
        registry.release("support.reply", "1.0.0")
        plan = langfuse_plan(registry, "support.reply", "1.0.0")
        state = {"remote": None, "posts": 0}

        class Response:
            status = 200

            def __init__(self, body):
                self.body = json.dumps(body).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def read(self):
                return self.body

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 20)
            if request.get_method() == "GET":
                if state["remote"] is None:
                    raise HTTPError(request.full_url, 404, "not found", None, None)
                return Response(state["remote"])
            payload = json.loads(request.data)
            state["posts"] += 1
            state["remote"] = {"type": payload["type"], "prompt": payload["prompt"], "config": payload["config"], "version": state["posts"]}
            return Response(state["remote"])

        base = "http://127.0.0.1:1234"
        with patch("opf.publish.urlopen", side_effect=fake_urlopen):
            first = publish_langfuse(plan, base_url=base, public_key="pk", secret_key="sk")
            second = publish_langfuse(plan, base_url=base, public_key="pk", secret_key="sk")
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(state["posts"], 1)
            remote = Registry.langfuse(base_url=base, public_key="pk", secret_key="sk")
            prompt = remote.get("support.reply", version="1.0.0", expected_digest=plan["digest"])
            self.assertEqual(prompt.render({"question": "Hi"}).messages[1]["content"], "Hi")
            with self.assertRaisesRegex(OPFError, "pinned local release"):
                remote.get("support.reply", version="1.0.0", expected_digest="sha256:" + "0" * 64)


if __name__ == "__main__":
    unittest.main()
