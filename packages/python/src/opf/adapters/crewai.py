"""Import explicit static CrewAI agent prompt templates from YAML or JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..compatibility import CompatibilityFinding, data_loss_code
from ..core import OPFError
from .base import SourcePrompt, read_source
from .common import plan_messages
from .markdown import ID_RE, _json_compatible

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class CrewAIAdapter:
    source_kind = "crewai-agent-template"
    converter = "opf-migrate-crewai"

    def inspect(self, path: str | Path, *, root: str | Path = ".") -> SourcePrompt:
        source = read_source(path, root, self.source_kind)
        try:
            value = json.loads(source.text) if source.path.suffix.lower() == ".json" else yaml.safe_load(source.text)
        except Exception as exc:
            raise OPFError("CrewAI input must be static JSON or YAML: {}".format(exc)) from exc
        if not isinstance(value, dict):
            raise OPFError("CrewAI input must be a mapping")
        return SourcePrompt(source.path, source.relative_path, source.source_kind, source.text, source.source_digest, "static-agent-template/1", {"value": value})

    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None):
        if not ID_RE.fullmatch(prompt_id):
            raise OPFError("invalid prompt id")
        value: dict[str, Any] = (source.data or {}).get("value", {})
        known = {"role", "goal", "backstory", "system_template", "prompt_template", "custom_prompts"}
        unknown = set(value) - known
        messages = []
        findings = [CompatibilityFinding("crewai.orchestration.excluded", "warning", "manual", "Agent execution, tools, and orchestration are outside the portable prompt core", category="unsupported", recommendation="Keep orchestration in the application and migrate only its prompt content into OPF.")]
        for key, message_role in (("system_template", "system"), ("prompt_template", role or "user")):
            template = value.get(key)
            if template is None:
                continue
            if not isinstance(template, str):
                raise OPFError("{} must be a static string".format(key))
            scrubbed = PLACEHOLDER_RE.sub("", template)
            if "{" in scrubbed or "}" in scrubbed:
                raise OPFError("unsupported CrewAI placeholder syntax in {}".format(key))
            text = PLACEHOLDER_RE.sub(lambda m: "{{ " + m.group(1) + " }}", template)
            messages.append({"role": message_role, "content": text})
        if not messages:
            for key in ("backstory", "goal"):
                if key in value:
                    raise OPFError("CrewAI {} is agent configuration; provide system_template or prompt_template for migration".format(key))
            raise OPFError("CrewAI input requires system_template or prompt_template")
        extension_data = {key: value[key] for key in ("role", "goal", "backstory", "custom_prompts") if key in value}
        for key in sorted(unknown):
            extension_data[key] = value[key]
            findings.append(CompatibilityFinding("metadata.preserved.extension", "warning", "preserved", "unknown CrewAI field {!r} is retained in the agent extension".format(key), capability="com.crewai.agent", source_path=source.relative_path, category="preserved_resource", source_field=str(key), recommendation="Keep the field preserved or define an explicit adapter mapping before relying on its behavior."))
        preserved_data = {}
        for key, item in extension_data.items():
            if _json_compatible(item):
                preserved_data[key] = item
            else:
                code = data_loss_code(str(key))
                findings.append(CompatibilityFinding(code, "error", "dropped", "CrewAI field {!r} cannot be represented in a JSON-compatible OPF extension".format(key), source_path=source.relative_path, category="data_loss", source_field=str(key), recommendation="Convert this value to JSON-compatible data or explicitly accept this named loss."))
        extensions = {"com.crewai.agent": {"version": "1", "required": True, "data": preserved_data}} if preserved_data else None
        return plan_messages(source, prompt_id, messages, converter=self.converter, source_format_version=source.source_format_version, extensions=extensions, findings=findings)

    def convert(self, source: SourcePrompt, plan):
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
