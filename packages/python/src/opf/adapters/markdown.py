"""Import ordinary Markdown prompt files into the OPF portable core."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..compatibility import CompatibilityFinding, CompatibilityReport, data_loss_code
from ..core import HEADING_RE, OPFError, VARIABLE_RE, _UniqueSafeLoader, parse
from .base import MigrationOutput, MigrationPlan, SourceAdapter, SourcePrompt, read_source

ROLE_SET = {"system", "developer", "user", "assistant"}
ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SOURCE_EXTENSION = "com.github.stovo-team.open-prompt-format.source"
SOURCE_FRONTMATTER_FORMAT = "markdown-frontmatter/1"


def _split_legacy_frontmatter(text: str) -> tuple[dict[str, Any], str, int]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").removeprefix("\ufeff")
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        return {}, normalized, 0
    closing = next((index for index in range(1, len(lines)) if lines[index].rstrip("\n") == "---"), None)
    if closing is None:
        raise OPFError("legacy Markdown frontmatter closing delimiter '---' was not found")
    try:
        metadata = yaml.load("".join(lines[1:closing]), Loader=_UniqueSafeLoader)
    except (yaml.YAMLError, OPFError) as exc:
        # Parser diagnostics can quote source lines and disclose prompt metadata.
        raise OPFError("invalid legacy Markdown YAML frontmatter; inspect its syntax and duplicate keys") from exc
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise OPFError("legacy Markdown frontmatter must be a mapping")
    return metadata, "".join(lines[closing + 1 :]), closing + 1


def _json_compatible(value: Any, active: set[int] | None = None) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    active = active if active is not None else set()
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            return False
        active.add(identity)
        try:
            return all(_json_compatible(item, active) for item in value)
        finally:
            active.remove(identity)
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            return False
        active.add(identity)
        try:
            return all(isinstance(key, str) and _json_compatible(item, active) for key, item in value.items())
        finally:
            active.remove(identity)
    return False


def _canonicalize_role_headings(body: str, *, line_offset: int = 0) -> tuple[str, list[CompatibilityFinding]]:
    lines = body.split("\n")
    findings = []
    fence_char: str | None = None
    fence_length = 0
    fence_re = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
    single_heading_re = re.compile(r"^# (system|developer|user|assistant)$")
    for index, line in enumerate(lines):
        fence = fence_re.match(line)
        if fence:
            marker = fence.group(1)
            char = marker[0]
            if fence_char is None:
                fence_char, fence_length = char, len(marker)
            elif char == fence_char and len(marker) >= fence_length and not fence.group(2).strip():
                fence_char, fence_length = None, 0
            continue
        if fence_char is not None:
            continue
        heading = single_heading_re.fullmatch(line)
        if heading:
            role = heading.group(1)
            lines[index] = "## " + role
            findings.append(
                CompatibilityFinding(
                    "heading.noncanonical.single_hash",
                    "info",
                    "preserved",
                    "single-hash role heading is accepted and normalized in generated OPF",
                    category="portable",
                    source_line=line_offset + index + 1,
                    recommendation="Use '## {}' as the canonical role heading.".format(role),
                )
            )
    return "\n".join(lines), findings


def _has_role_headings(body: str) -> bool:
    fence_char: str | None = None
    fence_length = 0
    fence_re = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
    for line in body.split("\n"):
        fence = fence_re.match(line)
        if fence:
            marker = fence.group(1)
            char = marker[0]
            if fence_char is None:
                fence_char, fence_length = char, len(marker)
            elif char == fence_char and len(marker) >= fence_length and not fence.group(2).strip():
                fence_char, fence_length = None, 0
            continue
        if fence_char is None and HEADING_RE.fullmatch(line):
            return True
    return False


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
        metadata, body, line_offset = _split_legacy_frontmatter(source.text)
        return SourcePrompt(
            source.path,
            source.relative_path,
            source.source_kind,
            source.text,
            source.source_digest,
            source.source_format_version,
            {"frontmatter": metadata, "body": body, "body_line_offset": line_offset},
        )

    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None) -> MigrationPlan:
        if not ID_RE.fullmatch(prompt_id):
            raise OPFError("prompt id must match [a-z0-9]+(?:[._-][a-z0-9]+)*")
        if role is not None and role not in ROLE_SET:
            raise OPFError("role must be one of system, developer, user, assistant")
        source_data = dict(source.data or {})
        body = str(source_data.get("body", source.text.replace("\r\n", "\n").replace("\r", "\n")))
        line_offset = int(source_data.get("body_line_offset", 0))
        has_roles = _has_role_headings(body)
        findings = []
        if not has_roles:
            if role is None:
                findings.append(CompatibilityFinding("markdown.role.required", "error", "manual", "Markdown has no explicit OPF role headings; choose --role", category="unsupported", recommendation="Choose --role for a single-message prompt, or add explicit role headings."))
                rendered_body = "## user\n" + body
            else:
                rendered_body = "## {}\n{}".format(role, body)
            findings.append(CompatibilityFinding("markdown.single_role", "info", "preserved", "The source was assigned one explicit message role", category="portable"))
        else:
            rendered_body, heading_findings = _canonicalize_role_headings(body, line_offset=line_offset)
            findings.extend(heading_findings)
            findings.append(CompatibilityFinding("markdown.roles.preserved", "info", "preserved", "Explicit message headings were preserved", category="portable"))
        legacy_metadata = source_data.get("frontmatter", {})
        extensions = {}
        if legacy_metadata:
            preserved_metadata: dict[str, Any] = {}
            for key, value in legacy_metadata.items():
                if _json_compatible(value):
                    preserved_metadata[key] = value
                    findings.append(
                        CompatibilityFinding(
                            "metadata.preserved.extension",
                            "warning",
                            "preserved",
                            "legacy metadata field {!r} is retained opaquely; OPF core does not interpret its semantics".format(key),
                            capability=SOURCE_EXTENSION,
                            source_path=source.relative_path,
                            category="preserved_resource",
                            source_field=str(key),
                            recommendation="Keep the preserved field while migrating its consumer to an explicit OPF extension or resource adapter.",
                        )
                    )
                else:
                    code = data_loss_code(str(key))
                    findings.append(
                        CompatibilityFinding(
                            code,
                            "error",
                            "dropped",
                            "legacy metadata field {!r} cannot be represented in a JSON-compatible OPF extension".format(key),
                            source_path=source.relative_path,
                            category="data_loss",
                            source_field=str(key),
                            recommendation="Convert this value to JSON-compatible data or explicitly accept this named loss.",
                        )
                    )
            if preserved_metadata:
                extensions[SOURCE_EXTENSION] = {
                    "version": "1",
                    "required": True,
                    "data": {"source_kind": SOURCE_FRONTMATTER_FORMAT, "metadata": preserved_metadata},
                }
        unsupported = re.sub(r"\\\{\{", "", rendered_body)
        unsupported = VARIABLE_RE.sub("", unsupported)
        if "{{" in unsupported or "{%" in unsupported:
            findings.append(CompatibilityFinding("template.syntax.unsupported", "error", "manual", "Template syntax exceeds OPF v0.3 string-variable interpolation", category="unsupported", recommendation="Keep the source renderer or manually simplify the template to declared string inputs."))
        content = _frontmatter(prompt_id, rendered_body, extensions=extensions or None)
        output_path = "prompts/{}.opf.md".format(prompt_id)
        generated = {output_path: content}
        try:
            prompt = parse(content)
            if prompt.id != prompt_id:
                raise OPFError("migration output id does not match plan")
        except OPFError as exc:
            findings.append(CompatibilityFinding("opf.output.invalid", "error", "manual", "Generated OPF cannot be validated: {}".format(exc), category="unsupported", recommendation="Resolve the reported syntax issue or retain the source adapter."))
        report = CompatibilityReport(
            source_kind=source.source_kind,
            target_kind="opf/0.3",
            findings=tuple(findings),
            lossless=all(item.category != "data_loss" for item in findings),
            can_apply=not any(item.category == "data_loss" or item.severity == "error" for item in findings),
        )
        manifest = {
            "source_path": source.relative_path,
            "source_kind": source.source_kind,
            "source_digest": source.source_digest,
            "converter": self.converter,
            "converter_version": "0.3.0",
            "migrated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "findings": [
                item.to_dict()
                for item in findings
            ],
        }
        output = MigrationOutput(generated, {"renderer": "opf", "source": output_path}, manifest)
        return MigrationPlan(prompt_id, source, output, report, self.converter)

    def convert(self, source: SourcePrompt, plan: MigrationPlan) -> MigrationOutput:
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
