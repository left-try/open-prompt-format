"""Inspect Jinja sources and either simplify them or register them unchanged."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from ..compatibility import CompatibilityFinding, CompatibilityReport
from ..core import OPFError, VARIABLE_RE
from .base import MigrationOutput, MigrationPlan, SourceAdapter, SourcePrompt, read_source
from .markdown import MarkdownAdapter, ID_RE

INCLUDE_RE = re.compile(r"{%\s*(?:include|import|from)\s+['\"]([^'\"]+)['\"]")
DYNAMIC_INCLUDE_RE = re.compile(r"{%\s*(?:include|import|from)\s+(?!['\"])\S+")
SIMPLE_VARIABLE_RE = re.compile(r"{{\s*[A-Za-z_][A-Za-z0-9_]*\s*}}")


class JinjaAdapter(SourceAdapter):
    source_kind = "jinja2"
    converter = "opf-migrate-jinja"

    def inspect(self, path: str | Path, *, root: str | Path = ".") -> SourcePrompt:
        source = read_source(path, root, self.source_kind)
        if source.path.suffix.lower() != ".j2" and "{{" not in source.text and "{%" not in source.text:
            raise OPFError("source does not appear to use Jinja syntax")
        static = sorted(set(INCLUDE_RE.findall(source.text)))
        data = {"static_includes": static, "dynamic_include": bool(DYNAMIC_INCLUDE_RE.search(source.text))}
        return SourcePrompt(source.path, source.relative_path, source.source_kind, source.text, source.source_digest, "jinja2", data)

    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None) -> MigrationPlan:
        if not ID_RE.fullmatch(prompt_id):
            raise OPFError("prompt id must match [a-z0-9]+(?:[._-][a-z0-9]+)*")
        if role is None or role not in {"system", "developer", "user", "assistant"}:
            finding = CompatibilityFinding("jinja.role.required", "error", "manual", "Choose one explicit role with --role before importing a standalone Jinja file")
            report = CompatibilityReport(source.source_kind, "opf-registry/1", (finding,), False, False)
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record = {"source_path": source.relative_path, "source_kind": source.source_kind, "source_format_version": "jinja2", "source_digest": source.source_digest, "converter": self.converter, "converter_version": "0.3.0", "migrated_at": now, "findings": [{"code": finding.code, "severity": finding.severity, "disposition": finding.disposition, "message": finding.message}]}
            return MigrationPlan(prompt_id, source, MigrationOutput({}, None, record), report, self.converter)

        data = dict(source.data or {})
        findings = []
        if data.get("dynamic_include"):
            finding = CompatibilityFinding("jinja.include.dynamic", "error", "manual", "Dynamic Jinja include/import targets cannot be pinned into a reproducible bundle", source_path=source.relative_path)
            findings.append(finding)
        stripped = SIMPLE_VARIABLE_RE.sub("", source.text)
        simple = not data.get("dynamic_include") and not re.search(r"{%|{#|\|", source.text) and not re.search(r"{{|}}|[{}]", stripped)
        if simple:
            markdown = MarkdownAdapter()
            plan = markdown.plan(source, prompt_id, role=role)
            record = dict(plan.output.manifest_record)
            record["source_kind"] = self.source_kind
            record["source_format_version"] = "jinja2"
            record["converter"] = self.converter
            findings.extend(plan.compatibility.findings)
            findings.append(CompatibilityFinding("jinja.simple.variables", "warning", "approximated", "Simple Jinja variables were migrated to OPF interpolation; whitespace trimming may differ"))
            report = CompatibilityReport(self.source_kind, "opf/0.3", tuple(findings), False, not any(item.severity == "error" for item in findings))
            output = replace(plan.output, manifest_record=record)
            return MigrationPlan(prompt_id, source, output, report, self.converter)

        variable_names = sorted(set(VARIABLE_RE.findall(source.text)))
        inputs = {name: {"type": "string", "required": True} for name in variable_names}
        entry = {"renderer": "jinja2", "messages": [{"role": role, "file": source.relative_path}]}
        if inputs:
            entry["inputs"] = inputs
        findings.append(CompatibilityFinding("jinja.source.preserved", "info", "preserved", "Original Jinja source and its template semantics are kept in the OPF local registry", source_path=source.relative_path))
        if data.get("static_includes"):
            findings.append(CompatibilityFinding("jinja.dependencies.static", "info", "preserved", "Static template dependencies will be pinned when the registry releases the prompt", source_path=source.relative_path))
        findings.append(CompatibilityFinding("jinja.template.runtime", "warning", "preserved", "Rendering still requires the optional Python Jinja2 runtime", capability="jinja2"))
        report = CompatibilityReport(self.source_kind, "opf-registry/1", tuple(findings), not data.get("dynamic_include", False), not any(item.severity == "error" for item in findings))
        record = {
            "source_path": source.relative_path,
            "source_kind": source.source_kind,
            "source_format_version": "jinja2",
            "source_digest": source.source_digest,
            "converter": self.converter,
            "converter_version": "0.3.0",
            "migrated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "findings": [{"code": item.code, "severity": item.severity, "disposition": item.disposition, "message": item.message, **({"path": item.source_path} if item.source_path else {})} for item in findings],
        }
        return MigrationPlan(prompt_id, source, MigrationOutput({}, entry, record), report, self.converter)

    def convert(self, source: SourcePrompt, plan: MigrationPlan) -> MigrationOutput:
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
