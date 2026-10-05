import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
FORMS = ROOT / ".github/ISSUE_TEMPLATE"


def load_form(name):
    return yaml.safe_load((FORMS / name).read_text(encoding="utf-8"))


class FeedbackFormTests(unittest.TestCase):
    def test_adapter_request_collects_minimal_migration_metadata_with_privacy_warning(self):
        form = load_form("adapter-request.yml")
        self.assertEqual(form["name"], "Adapter or migration request")
        fields = {field.get("id"): field for field in form["body"] if "id" in field}
        for field_id in ("source_format", "framework", "framework_version", "target_language", "migration_outcome", "missing_capability", "share_sanitized_fixture"):
            self.assertIn(field_id, fields)
        sharing = fields["share_sanitized_fixture"]
        self.assertEqual(sharing["type"], "checkboxes")
        self.assertFalse(sharing["attributes"]["options"][0].get("required", False))
        warning_text = " ".join(str(value) for field in form["body"] for value in field.values())
        for warning in ("Do not include", "customer data", "credentials", "proprietary prompts"):
            self.assertIn(warning.lower(), warning_text.lower())

    def test_fixture_submission_is_separate_optional_and_requires_public_license(self):
        form = load_form("sanitized-fixture.yml")
        fields = {field.get("id"): field for field in form["body"] if "id" in field}
        self.assertEqual(fields["fixture"]["type"], "textarea")
        self.assertFalse(fields["fixture"].get("required", False))
        license_field = fields["public_license_acknowledgement"]
        self.assertEqual(license_field["type"], "checkboxes")
        self.assertTrue(license_field["attributes"]["options"][0]["required"])
        config = load_form("config.yml")
        self.assertFalse(config["blank_issues_enabled"])


if __name__ == "__main__":
    unittest.main()
