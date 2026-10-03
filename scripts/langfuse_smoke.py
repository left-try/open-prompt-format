"""Create and verify one unique OPF prompt in a test Langfuse project."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from opf import Registry
from opf.publish import langfuse_plan, publish_langfuse


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "packages/typescript/dist/index.js"
VERSION = "0.0.1"


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="create a uniquely named prompt in Langfuse")
    args = parser.parse_args()
    if args.publish:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY") or not os.environ.get("LANGFUSE_SECRET_KEY"):
            parser.error("set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in the environment")
        if not DIST.exists() or not shutil.which("node"):
            parser.error("build packages/typescript and make Node.js available before publishing")

    prompt_id = "opf-smoke-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="opf-langfuse-smoke-") as temporary:
        root = Path(temporary)
        (root / "prompts").mkdir()
        (root / "prompts/smoke.md").write_text(
            "---\nformat: opf/0.2\nid: {}\ninputs:\n  value:\n    type: string\n---\n\n## system\nReply briefly.\n\n## user\n{{{{ value }}}}\n".format(prompt_id),
            encoding="utf-8",
        )
        (root / "opf.yaml").write_text(
            "schema: opf-registry/1\nprompts:\n  {}:\n    renderer: opf\n    source: prompts/smoke.md\n".format(prompt_id),
            encoding="utf-8",
        )
        git(root, "init", "-q")
        git(root, "config", "user.name", "OPF Smoke")
        git(root, "config", "user.email", "opf-smoke@example.invalid")
        git(root, "add", "opf.yaml", "prompts/smoke.md")
        git(root, "commit", "-qm", "smoke prompt")
        registry = Registry.local(root / "opf.yaml")
        registry.release(prompt_id, VERSION)
        plan = langfuse_plan(registry, prompt_id, VERSION)
        summary = {"id": prompt_id, "version": VERSION, "digest": plan["digest"], "target": "langfuse", "dry_run": not args.publish}
        if not args.publish:
            print(json.dumps(summary, ensure_ascii=False))
            return

        first = publish_langfuse(plan)
        second = publish_langfuse(plan)
        if not first["created"] or second["created"]:
            raise RuntimeError("Langfuse publication was not idempotent")
        expected = registry.get(prompt_id, version=VERSION).render({"value": "hello"}).messages
        actual = Registry.langfuse().get(prompt_id, version=VERSION, expected_digest=plan["digest"]).render({"value": "hello"}).messages
        if actual != expected:
            raise RuntimeError("Python remote rendering differs from the local release")

        node_script = """
import { pathToFileURL } from 'node:url';
const { Registry } = await import(pathToFileURL(process.env.OPF_SMOKE_DIST).href);
const prompt = await Registry.langfuse().get(process.env.OPF_SMOKE_ID, { version: '0.0.1', expectedDigest: process.env.OPF_SMOKE_DIGEST });
const messages = prompt.render({ value: 'hello' }).messages;
if (messages[0].content !== 'Reply briefly.' || messages[1].content !== 'hello') throw new Error('TypeScript remote rendering differs from the local release');
"""
        environment = {**os.environ, "OPF_SMOKE_DIST": str(DIST), "OPF_SMOKE_ID": prompt_id, "OPF_SMOKE_DIGEST": plan["digest"]}
        subprocess.run(["node", "--input-type=module", "-e", node_script], env=environment, check=True)
        print(json.dumps({**summary, "dry_run": False, "remote_version": first["remote_version"], "python": "ok", "typescript": "ok"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
