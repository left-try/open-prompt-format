import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


class PromptfooConfigTests(unittest.TestCase):
    def test_sample_eval_has_four_cost_bounded_cases_with_assertions(self):
        config = yaml.safe_load((ROOT / "evals/promptfooconfig.yaml").read_text(encoding="utf-8"))

        self.assertEqual(config["prompts"], ["file://../adapters/promptfoo.cjs"])
        self.assertEqual(config["env"]["OPF_PROMPT_FILE"], "examples/support.reply.md")
        self.assertEqual(config["providers"], ["openai:gpt-4.1-mini", "anthropic:messages:claude-haiku-4-5-20251001"])
        self.assertEqual(len(config["tests"]), 4)
        self.assertEqual(len({case["description"] for case in config["tests"]}), 4)
        for case in config["tests"]:
            self.assertIn("customer_message", case["vars"])
            self.assertTrue(case["assert"], case["description"])
            self.assertTrue(all(assertion["type"] != "llm-rubric" for assertion in case["assert"]))
        self.assertTrue(
            any(assertion["type"] == "not-regex" for case in config["tests"] for assertion in case["assert"]),
            "the suite must check that fabricated tracking details are absent",
        )
        self.assertTrue(
            any(assertion["type"] == "regex" for case in config["tests"] for assertion in case["assert"]),
            "the suite must check for a clarification question when information is missing",
        )


if __name__ == "__main__":
    unittest.main()
