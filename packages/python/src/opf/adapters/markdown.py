"""Import ordinary Markdown prompt files into the OPF portable core."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..compatibility import CompatibilityFinding, CompatibilityReport
from ..core import HEADING_RE, OPFError, VARIABLE_RE, parse
from .base import MigrationOutput, MigrationPlan, SourceAdapter, SourcePrompt, read_source

ROLE_SET = {"system", "developer", "user", "assistant"}
ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def generated_id(path: str) -> str:
    stem = Path(path).stem.lower()
    value = re.sub(r"[^a-z0-9]+", ".", stem).strip(".")
    if not value or not value[0].isalnum():
        value = "prompt." + value
    if not ID_RE.fullmatch(value):
        raise OPFError("cannot derive a valid prompt id from {}; pass --id".format(path))
    return value


def _frontmatter(prompt_id: str, body: str, *, extensions: dict[str, Any] | None = None) -> str:
    variables = sorted(set(VARIABLE_RE.findall(body)))
    metadata: dict[str, Any] = {"format": "opf/0.3", "id": prompt_id}
    if variables:
        metadata["inputs"] = {name: {"type": "string", "required": True} for name in variables}
    if extensions:
        metadata["extensions"] = extensions
    header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip()
    return "---\n{}\n---\n\n{}".format(header, body.replace("\r\n", "\n").replace("\r", "\n").strip("\n"))


class MarkdownAdapter(SourceAdapter):
    source_kind = "markdown"
    converter = "opf-migrate-markdown"

    def inspect(self, path: str | Path, *, root: str | Path = ".") -> SourcePrompt:
        source = read_source(path, root, self.source_kind)
        if re.match(r"^---\s*\n(?:(?!\n---).)*\nformat:\s*opf/0\.[123](?:\s|$)", source.text, re.DOTALL):
            raise OPFError("{} already appears to be an OPF prompt".format(source.relative_path))
        return source

    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None) -> MigrationPlan:
        if not ID_RE.fullmatch(prompt_id):
            raise OPFError("prompt id must match [a-z0-9]+(?:[._-][a-z0-9]+)*")
        if role is not None and role not in ROLE_SET:
            raise OPFError("role must be one of system, developer, user, assistant")
        body = source.text.replace("\r\n", "\n").replace("\r", "\n")
        has_roles = any(HEADING_RE.fullmatch(line) for line in body.splitlines())
        findings = []
        if not has_roles:
            if role is None:
                findings.append(CompatibilityFinding("markdown.role.required", "error", "manual", "Markdown has no explicit OPF role headings; choose --role"))
                rendered_body = "## user\n" + body
            else:
                rendered_body = "## {}\n{}".format(role, body)
            findings.append(CompatibilityFinding("markdown.single_role", "info", "preserved", "The source was assigned one explicit message role"))
        else:
            rendered_body = body
            findings.append(CompatibilityFinding("markdown.roles.preserved", "info", "preserved", "Explicit message headings were preserved"))
        unsupported = re.sub(r"\\\{\{", "", rendered_body)
        unsupported = VARIABLE_RE.sub("", unsupported)
        if "{{" in unsupported or "{%" in unsupported:
            findings.append(CompatibilityFinding("template.syntax.unsupported", "error", "manual", "Template syntax exceeds OPF v0.3 string-variable interpolation"))
        content = _frontmatter(prompt_id, rendered_body)
        output_path = "prompts/{}.opf.md".format(prompt_id)
        generated = {output_path: content}
        try:
            prompt = parse(content)
            if prompt.id != prompt_id:
                raise OPFError("migration output id does not match plan")
        except OPFError as exc:
            findings.append(CompatibilityFinding("opf.output.invalid", "error", "manual", "Generated OPF cannot be validated: {}".format(exc)))
        report = CompatibilityReport(
            source_kind=source.source_kind,
            target_kind="opf/0.3",
            findings=tuple(findings),
            lossless=all(item.disposition == "preserved" for item in findings),
            can_apply=not any(item.severity == "error" for item in findings),
        )
        manifest = {
            "source_path": source.relative_path,
            "source_kind": source.source_kind,
            "source_digest": source.source_digest,
            "converter": self.converter,
            "converter_version": "0.3.0",
            "migrated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "findings": [
                {"code": item.code, "severity": item.severity, "disposition": item.disposition, "message": item.message, **({"path": item.source_path} if item.source_path else {})}
                for item in findings
            ],
        }
        output = MigrationOutput(generated, {"renderer": "opf", "source": output_path}, manifest)
        return MigrationPlan(prompt_id, source, output, report, self.converter)

    def convert(self, source: SourcePrompt, plan: MigrationPlan) -> MigrationOutput:
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
