"""Offline import of a deliberately small LangChain prompt configuration subset."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..compatibility import CompatibilityFinding
from ..core import OPFError
from .base import SourcePrompt, read_source
from .common import plan_messages
from .markdown import ID_RE

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
        findings = [CompatibilityFinding("langchain.template.converted", "warning", "approximated", "Only simple single-brace variables are converted to OPF interpolation")]
        kind = (source.data or {}).get("kind")
        if kind in {"prompt", "prompt_template"}:
            template = value.get("template")
            if not isinstance(template, str):
                raise OPFError("PromptTemplate requires a static string template")
            fields = set(_FIELD.findall(template))
            scrubbed = _FIELD.sub("", template)
            if "{" in scrubbed or "}" in scrubbed or fields - set(variables):
                raise OPFError("complex format fields or undeclared variables require manual migration")
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
                    raise OPFError("complex format fields or undeclared variables require manual migration")
                messages.append({"role": item["role"], "content": _FIELD.sub(lambda m: "{{ " + m.group(1) + " }}", content)})
        return plan_messages(source, prompt_id, messages, converter=self.converter, source_format_version=source.source_format_version, inputs=variables, findings=findings)

    def convert(self, source: SourcePrompt, plan):
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
