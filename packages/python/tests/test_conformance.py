import json
import shutil
import tempfile
import unittest
from pathlib import Path

from opf import OPFError, load, load_by_id, load_collection, parse


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((ROOT / "fixtures/conformance.json").read_text(encoding="utf-8"))


class ConformanceTests(unittest.TestCase):
    def test_shared_valid_render(self):
        for case in FIXTURE["valid"]:
            with self.subTest(file=case["file"]):
                prompt = load(ROOT / "fixtures" / case["file"])
                self.assertEqual(prompt.render(**case["inputs"]), case["expected"])
                self.assertRegex(prompt.source_digest, r"^sha256:[0-9a-f]{64}$")
                self.assertEqual(prompt.metadata["tags"], ["conformance", "on", "2026-10-02"])

    def test_shared_invalid_files(self):
        for relative in FIXTURE["invalid"]:
            with self.subTest(file=relative):
                with self.assertRaises(OPFError):
                    load(ROOT / "fixtures" / relative)

    def test_collection_lookup_and_duplicates(self):
        prompt_dir = ROOT / "examples"
        prompt = load_by_id("support.reply", prompt_dir)
        self.assertEqual(prompt.id, "support.reply")
        self.assertIn("support.reply", [prompt.id for prompt in load_collection(prompt_dir)])
        with tempfile.TemporaryDirectory() as temporary:
            duplicate_dir = Path(temporary)
            shutil.copy(ROOT / "examples/support.reply.md", duplicate_dir / "first.md")
            shutil.copy(ROOT / "examples/support.reply.md", duplicate_dir / "second.md")
            with self.assertRaisesRegex(OPFError, "duplicate prompt id"):
                load_collection(duplicate_dir)

    def test_newline_normalization_keeps_digest_stable(self):
        source = (ROOT / "examples/support.reply.md").read_text(encoding="utf-8")
        lf = parse(source)
        crlf = parse(source.replace("\n", "\r\n"))
        cr = parse(source.replace("\n", "\r"))
        self.assertEqual(lf.source_digest, crlf.source_digest)
        self.assertEqual(lf.source_digest, cr.source_digest)

    def test_missing_and_extra_inputs_are_errors(self):
        prompt = load(ROOT / "examples/support.reply.md")
        with self.assertRaisesRegex(OPFError, "missing required input"):
            prompt.render()
        with self.assertRaisesRegex(OPFError, "undeclared input"):
            prompt.render(customer_message="hello", extra="no")

    def test_frontmatter_schema_is_valid_json(self):
        schema = json.loads((ROOT / "spec/frontmatter.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["format"]["const"], "opf/0.1")


if __name__ == "__main__":
    unittest.main()
