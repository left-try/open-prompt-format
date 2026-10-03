"""Extract only literal system_message values from AutoGen Python source."""

from __future__ import annotations

import ast
from pathlib import Path

from ..compatibility import CompatibilityFinding
from ..core import OPFError
from .base import SourcePrompt, read_source
from .common import plan_messages
from .markdown import ID_RE


class AutoGenAdapter:
    source_kind = "autogen-python"
    converter = "opf-migrate-autogen"

    def inspect(self, path: str | Path, *, root: str | Path = ".") -> SourcePrompt:
        source = read_source(path, root, self.source_kind)
        try:
            ast.parse(source.text, filename=source.relative_path)
        except SyntaxError as exc:
            raise OPFError("AutoGen source is not valid Python: {}".format(exc)) from exc
        return SourcePrompt(source.path, source.relative_path, source.source_kind, source.text, source.source_digest, "python-ast-static/1")

    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None):
        if not ID_RE.fullmatch(prompt_id):
            raise OPFError("invalid prompt id")
        tree = ast.parse(source.text)
        candidates: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "system_message":
                    continue
                try:
                    value = ast.literal_eval(keyword.value)
                except (ValueError, TypeError):
                    raise OPFError("dynamic AutoGen system_message requires manual migration")
                if not isinstance(value, str):
                    raise OPFError("AutoGen system_message must be a string literal")
                candidates.append(value)
        if len(candidates) != 1:
            raise OPFError("expected exactly one explicit system_message; found {}".format(len(candidates)))
        findings = [CompatibilityFinding("autogen.runtime.excluded", "warning", "dropped", "AutoGen tools, agent runtime, and control flow are not part of this migration")]
        return plan_messages(source, prompt_id, [{"role": "system", "content": candidates[0]}], converter=self.converter, source_format_version=source.source_format_version, findings=findings)

    def convert(self, source: SourcePrompt, plan):
        if source.source_digest != plan.source.source_digest:
            raise OPFError("source changed after migration plan was created")
        return plan.output
