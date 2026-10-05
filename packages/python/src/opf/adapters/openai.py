"""Import an offline OpenAI prompt snapshot without contacting the API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..compatibility import CompatibilityFinding, CompatibilityReport
from ..core import OPFError, VARIABLE_RE, parse
from .base import MigrationOutput, MigrationPlan, SourceAdapter, SourcePrompt, read_source
from .markdown import ID_RE

SNAPSHOT_SCHEMA = "openai-prompt-snapshot/1"
ALLOWED_FIELDS = {"schema", "id", "name", "version", "variables", "messages", "tools", "text_format", "model_settings"}


class OpenAIPromptAdapter(SourceAdapter):
    source_kind = "openai-prompt-snapshot"
    converter = "opf-migrate-openai"

    def inspect(self, path: str | Path, *, root: str | Path = ".") -> SourcePrompt:
        source = read_source(path, root, self.source_kind)
        try:
            value = json.loads(source.text)
        except json.JSONDecodeError as exc:
            raise OPFError("OpenAI migration input must be an offline JSON snapshot: {}".format(exc)) from exc
        if not isinstance(value, dict) or value.get("schema") != SNAPSHOT_SCHEMA:
            raise OPFError("OpenAI input must declare schema: {}".format(SNAPSHOT_SCHEMA))
        unknown = set(value) - ALLOWED_FIELDS
        if not isinstance(value.get("messages"), list) or not value["messages"]:
            raise OPFError("OpenAI snapshot requires an ordered messages list")
        for item in value["messages"]:
            if not isinstance(item, dict) or set(item) != {"role", "content"} or not isinstance(item["role"], str) or item["role"] not in {"system", "developer", "user", "assistant"} or not isinstance(item["content"], str):
                raise OPFError("OpenAI snapshot messages require supported role and string content fields")
        return SourcePrompt(source.path, source.relative_path, source.source_kind, source.text, source.source_digest, "1", value)

    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None) -> MigrationPlan:
        if not ID_RE.fullmatch(prompt_id):
            raise OPFError("prompt id must match [a-z0-9]+(?:[._-][a-z0-9]+)*")
        value = dict(source.data or {})
        unknown = set(value) - ALLOWED_FIELDS
        messages = value["messages"]
        variables = value.get("variables", [])
        if isinstance(variables, dict):
            declared = set(variables)
            if any(not isinstance(name, str) for name in variables):
                raise OPFError("OpenAI snapshot variable names must be strings")
        elif isinstance(variables, list) and all(isinstance(name, str) for name in variables):
            declared = set(variables)
        else:
            raise OPFError("OpenAI snapshot variables must be a list or mapping of names")
        body_parts = []
        for item in messages:
            body_parts.extend(["## {}".format(item["role"]), item["content"], ""])
            declared.update(VARIABLE_RE.findall(item["content"]))
        body = "\n".join(body_parts).rstrip()
        vendor_data = {key: item for key, item in value.items() if key not in {"schema", "variables", "messages"}}
        extensions = {}
        if vendor_data:
            needs_vendor_execution = bool(vendor_data)
            extensions["com.openai.responses"] = {
                "version": "1",
                "required": needs_vendor_execution,
                "data": vendor_data,
            }
        metadata = {"format": "opf/0.3", "id": prompt_id}
        if declared:
            metadata["inputs"] = {name: {"type": "string", "required": True} for name in sorted(declared)}
        if extensions:
            metadata["extensions"] = extensions
        header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip()
        content = "---\n{}\n---\n\n{}".format(header, body)
        output_path = "prompts/{}.opf.md".format(prompt_id)
        generated = {output_path: content}
        findings = [CompatibilityFinding("openai.messages.preserved", "info", "preserved", "Ordered text messages and declared variables were mapped to OPF core", category="portable")]
        if vendor_data:
            findings.append(
                CompatibilityFinding(
                    "openai.extensions.preserved",
                    "warning",
                    "preserved",
                    "OpenAI-specific and source metadata are preserved in a required extension; target behavior still needs an OpenAI-aware consumer",
                    capability="com.openai.responses",
                    category="adapter_runtime",
                    recommendation="Keep the extension and use an OpenAI-aware adapter for provider-specific settings.",
                )
            )
        for field in sorted(unknown):
            findings.append(
                CompatibilityFinding(
                    "metadata.preserved.extension",
                    "warning",
                    "preserved",
                    "unknown OpenAI snapshot field {!r} is retained in the source extension".format(field),
                    capability="com.openai.responses",
                    source_path=source.relative_path,
                    category="preserved_resource",
                    source_field=field,
                    recommendation="Keep the field preserved or define an explicit adapter mapping before relying on its behavior.",
                )
            )
        parse(content)
        report = CompatibilityReport("openai-prompt-snapshot/1", "opf/0.3", tuple(findings), True, True)
        record = {
            "source_path": source.relative_path,
            "source_kind": source.source_kind,
            **({"source_format_version": source.source_format_version} if source.source_format_version else {}),
            "source_digest": source.source_digest,
            "converter": self.converter,
            "converter_version": "0.3.0",
            "migrated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "findings": [item.to_dict() for item in findings],
        }
        return MigrationPlan(prompt_id, source, MigrationOutput(generated, {"renderer": "opf", "source": output_path}, record), report, self.converter)

    def convert(self, source: SourcePrompt, plan: MigrationPlan) -> MigrationOutput:
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
