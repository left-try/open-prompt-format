"""Shared conversion helpers for source formats with static messages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import yaml

from ..compatibility import CompatibilityFinding, CompatibilityReport
from ..core import OPFError, VARIABLE_RE, parse
from .base import MigrationOutput, MigrationPlan, SourcePrompt
from .markdown import ID_RE


def plan_messages(
    source: SourcePrompt,
    prompt_id: str,
    messages: list[dict[str, str]],
    *,
    converter: str,
    source_format_version: str | None = None,
    inputs: Iterable[str] = (),
    extensions: dict[str, Any] | None = None,
    findings: Iterable[CompatibilityFinding] = (),
) -> MigrationPlan:
    if not ID_RE.fullmatch(prompt_id):
        raise OPFError("prompt id must match [a-z0-9]+(?:[._-][a-z0-9]+)*")
    if not messages or any(not isinstance(item, dict) or set(item) != {"role", "content"} or not isinstance(item["role"], str) or item["role"] not in {"system", "developer", "user", "assistant"} or not isinstance(item["content"], str) for item in messages):
        raise OPFError("source must provide ordered text messages with supported roles")
    declared = set(inputs)
    for item in messages:
        declared.update(VARIABLE_RE.findall(item["content"]))
    metadata: dict[str, Any] = {"format": "opf/0.3", "id": prompt_id}
    if declared:
        metadata["inputs"] = {name: {"type": "string", "required": True} for name in sorted(declared)}
    if extensions:
        metadata["extensions"] = extensions
    body = "\n\n".join("## {}\n{}".format(item["role"], item["content"]) for item in messages)
    content = "---\n{}\n---\n\n{}".format(yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip(), body)
    parse(content)
    output_path = "prompts/{}.opf.md".format(prompt_id)
    all_findings = tuple(findings) + (CompatibilityFinding("messages.preserved", "info", "preserved", "Ordered text messages were mapped to OPF core", category="portable"),)
    report = CompatibilityReport(
        source.source_kind,
        "opf/0.3",
        all_findings,
        all(item.disposition == "preserved" and item.category != "data_loss" for item in all_findings),
        not any(item.severity == "error" or item.category == "data_loss" for item in all_findings),
    )
    record = {
        "source_path": source.relative_path,
        "source_kind": source.source_kind,
        **({"source_format_version": source_format_version or source.source_format_version} if (source_format_version or source.source_format_version) else {}),
        "source_digest": source.source_digest,
        "converter": converter,
        "converter_version": "0.3.0",
        "migrated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "findings": [item.to_dict() for item in all_findings],
    }
    return MigrationPlan(prompt_id, source, MigrationOutput({output_path: content}, {"renderer": "opf", "source": output_path}, record), report, converter)


def manual_plan(
    source: SourcePrompt,
    prompt_id: str,
    *,
    converter: str,
    findings: Iterable[CompatibilityFinding],
    source_format_version: str | None = None,
) -> MigrationPlan:
    all_findings = tuple(findings)
    report = CompatibilityReport(source.source_kind, "opf/0.3", all_findings, False, False)
    record = {
        "source_path": source.relative_path,
        "source_kind": source.source_kind,
        **({"source_format_version": source_format_version or source.source_format_version} if (source_format_version or source.source_format_version) else {}),
        "source_digest": source.source_digest,
        "converter": converter,
        "converter_version": "0.3.0",
        "migrated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "findings": [item.to_dict() for item in all_findings],
    }
    return MigrationPlan(prompt_id, source, MigrationOutput({}, None, record), report, converter)
