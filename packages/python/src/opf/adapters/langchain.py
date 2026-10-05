"""Offline import of a deliberately small LangChain prompt configuration subset."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..compatibility import CompatibilityFinding, data_loss_code
from ..core import OPFError
from .base import SourcePrompt, read_source
from .common import manual_plan, plan_messages
from .markdown import ID_RE, _json_compatible

_FIELD = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")


class LangChainAdapter:
    source_kind = "langchain-prompt"
    converter = "opf-migrate-langchain"

    def inspect(self, path: str | Path, *, root: str | Path = ".") -> SourcePrompt:
        source = read_source(path, root, self.source_kind)
        try:
            value = json.loads(source.text) if source.path.suffix.lower() == ".json" else yaml.safe_load(source.text)
        except Exception as exc:
            raise OPFError("LangChain prompt input must be static JSON or YAML: {}".format(exc)) from exc
        if not isinstance(value, dict):
            raise OPFError("LangChain prompt input must be a mapping")
        kind = value.get("_type", value.get("type"))
        if kind not in {"prompt", "prompt_template", "chat", "chat_prompt"}:
            raise OPFError("unsupported LangChain prompt type; expected PromptTemplate or ChatPromptTemplate")
        data: dict[str, Any] = {"value": value, "kind": kind}
        return SourcePrompt(source.path, source.relative_path, source.source_kind, source.text, source.source_digest, str(value.get("version", "unknown")), data)

    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None):
        if not ID_RE.fullmatch(prompt_id):
            raise OPFError("invalid prompt id")
        value = (source.data or {}).get("value", {})
        variables = value.get("input_variables", [])
        if not isinstance(variables, list) or not all(isinstance(x, str) for x in variables):
            raise OPFError("LangChain input_variables must be a list of names")
        findings = [CompatibilityFinding("langchain.template.converted", "warning", "approximated", "Only simple single-brace variables are converted to OPF interpolation", category="portable", recommendation="Review the generated text and whitespace before switching the source runtime." )]
        known_fields = {"_type", "type", "version", "template", "input_variables", "messages"}
        extra_fields = {key: item for key, item in value.items() if key not in known_fields}
        preserved_fields = {}
        for key, item in extra_fields.items():
            if _json_compatible(item):
                preserved_fields[key] = item
                findings.append(CompatibilityFinding("metadata.preserved.extension", "warning", "preserved", "unknown LangChain field {!r} is retained in a required extension".format(key), capability="com.langchain.prompt", source_path=source.relative_path, category="preserved_resource", source_field=str(key), recommendation="Keep the field preserved or define an explicit adapter mapping before relying on its behavior."))
            else:
                code = data_loss_code(str(key))
                findings.append(CompatibilityFinding(code, "error", "dropped", "LangChain field {!r} cannot be represented in a JSON-compatible OPF extension".format(key), source_path=source.relative_path, category="data_loss", source_field=str(key), recommendation="Convert this value to JSON-compatible data or explicitly accept this named loss."))
        extensions = {"com.langchain.prompt": {"version": "1", "required": True, "data": {"source_kind": "langchain-prompt/1", "fields": preserved_fields}}} if preserved_fields else None
        kind = (source.data or {}).get("kind")
        if kind in {"prompt", "prompt_template"}:
            template = value.get("template")
            if not isinstance(template, str):
                raise OPFError("PromptTemplate requires a static string template")
            fields = set(_FIELD.findall(template))
            scrubbed = _FIELD.sub("", template)
            if "{" in scrubbed or "}" in scrubbed or fields - set(variables):
                finding = CompatibilityFinding("langchain.template.syntax.unsupported", "error", "manual", "Complex format fields or undeclared variables cannot be converted without changing template behavior", source_path=source.relative_path, category="unsupported", recommendation="Keep the LangChain renderer or simplify the template to declared string variables before migrating.")
                return manual_plan(source, prompt_id, converter=self.converter, source_format_version=source.source_format_version, findings=[*findings, finding])
            converted = _FIELD.sub(lambda m: "{{ " + m.group(1) + " }}", template)
            messages = [{"role": role or "user", "content": converted}]
        else:
            raw_messages = value.get("messages")
            if not isinstance(raw_messages, list) or not raw_messages:
                raise OPFError("ChatPromptTemplate requires a static ordered messages list")
            messages = []
            for item in raw_messages:
                if not isinstance(item, dict) or not isinstance(item.get("role"), str) or item.get("role") not in {"system", "developer", "user", "assistant"} or not isinstance(item.get("content"), str):
                    raise OPFError("ChatPromptTemplate supports only static role/content message mappings")
                content = item["content"]
                fields = set(_FIELD.findall(content))
                scrubbed = _FIELD.sub("", content)
                if "{" in scrubbed or "}" in scrubbed or fields - set(variables):
                    finding = CompatibilityFinding("langchain.template.syntax.unsupported", "error", "manual", "Complex format fields or undeclared variables cannot be converted without changing template behavior", source_path=source.relative_path, category="unsupported", recommendation="Keep the LangChain renderer or simplify the message to declared string variables before migrating.")
                    return manual_plan(source, prompt_id, converter=self.converter, source_format_version=source.source_format_version, findings=[*findings, finding])
                messages.append({"role": item["role"], "content": _FIELD.sub(lambda m: "{{ " + m.group(1) + " }}", content)})
        return plan_messages(source, prompt_id, messages, converter=self.converter, source_format_version=source.source_format_version, inputs=variables, extensions=extensions, findings=findings)

    def convert(self, source: SourcePrompt, plan):
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
