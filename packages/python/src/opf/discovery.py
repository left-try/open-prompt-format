"""Read-only discovery of likely prompt assets in a repository."""

from __future__ import annotations

import ast
import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

from .core import OPFError

DEFAULT_EXCLUDED = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "vendor",
    "dist", "build", "target", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
}
PROMPT_SUFFIXES = {".md", ".j2", ".txt", ".json", ".yaml", ".yml", ".py"}
ROLE_HEADING = re.compile(r"(?m)^## (?:system|developer|user|assistant)\s*$")


@dataclass(frozen=True)
class PromptFinding:
    path: str
    source_kind: str
    confidence: Literal["high", "medium", "low"]
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _python_kind(source: str) -> tuple[str, str, str] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        if re.search(r"\b(?:system_message|system_template|prompt_template)\s*=", source):
            return "python.prompt", "low", "prompt-like assignment in Python source; file did not parse"
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            name = function.id if isinstance(function, ast.Name) else function.attr if isinstance(function, ast.Attribute) else ""
            if name in {"PromptTemplate", "ChatPromptTemplate", "SystemMessagePromptTemplate"}:
                return "langchain.python", "high", "uses {}".format(name)
            if name == "AssistantAgent" and any(keyword.arg in {"system_message", "system_prompt"} for keyword in node.keywords):
                return "autogen.python", "high", "configures an agent system message"
            if name == "Agent" and any(keyword.arg in {"system_template", "prompt_template"} for keyword in node.keywords):
                return "crewai.python", "high", "configures a CrewAI prompt template"
        if isinstance(node, ast.keyword) and node.arg in {"system_message", "system_template", "prompt_template"}:
            return "python.prompt", "medium", "contains a framework prompt field: {}".format(node.arg)
    if re.search(r"(?i)\b(?:system prompt|prompt template|you are an? (?:helpful|expert|assistant))\b", source):
        return "python.prompt", "low", "prompt-like text in Python source"
    return None


def _classify(path: Path, relative: str, source: str) -> tuple[str, str, str] | None:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".md":
        if source.startswith(("---\n", "---\r\n", "---\r")) and re.search(r"(?m)^format:\s*opf/0\.[123]\s*$", source):
            return "opf", "high", "OPF format frontmatter"
        if ROLE_HEADING.search(source):
            return "markdown.chat", "high", "contains explicit role message headings"
        if "prompt" in name or "system" in name or "instruction" in name:
            return "markdown.prompt", "medium", "prompt-like filename"
        return None
    if suffix == ".j2":
        return "jinja2", "high", "Jinja template file"
    if suffix == ".txt":
        if "prompt" in name or "system" in name or "instruction" in name:
            return "text.prompt", "medium", "prompt-like filename"
        return None
    if suffix in {".yaml", ".yml"}:
        lower = source.lower()
        if name == "opf.yaml" and "schema: opf-registry/1" in lower:
            return "opf.registry", "high", "OPF local registry configuration"
        if name in {"promptfooconfig.yaml", "promptfoo.yaml"} or "providers:" in lower and "prompts:" in lower:
            return "promptfoo.yaml", "high", "Promptfoo evaluation configuration"
        if any(key in lower for key in ("system_template:", "prompt_template:", "custom_prompts.json")):
            return "crewai.yaml", "high", "CrewAI prompt configuration field"
        if "_type: prompt" in lower or "input_variables:" in lower and "template:" in lower:
            return "langchain.yaml", "high", "LangChain serialized prompt"
        if ROLE_HEADING.search(source) or "{{" in source:
            return "yaml.prompt", "low", "contains prompt-like template syntax"
        return None
    if suffix == ".json":
        try:
            value = json.loads(source)
        except (json.JSONDecodeError, RecursionError):
            return None
        if isinstance(value, dict) and isinstance(value.get("slices"), dict):
            return "crewai.json", "high", "contains custom prompt slices"
        if isinstance(value, dict) and ("prompt_id" in value or "prompt" in value and any(key in value for key in ("version", "variables", "tools", "text_format"))):
            return "openai.prompt.json", "high", "resembles an exported vendor prompt object"
        if isinstance(value, list) and value and all(isinstance(item, dict) and item.get("role") in {"system", "developer", "user", "assistant"} and isinstance(item.get("content"), (str, list)) for item in value):
            return "chat-messages.json", "high", "ordered role/content message array"
        if isinstance(value, dict) and value.get("_type") in {"prompt", "chat"}:
            return "langchain.json", "high", "serialized LangChain prompt"
        return None
    if suffix == ".py":
        return _python_kind(source)
    return None


def scan(
    root: str | Path = ".",
    *,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> list[PromptFinding]:
    """Find likely prompts without modifying files or following directory symlinks."""
    base = Path(root).resolve()
    if not base.is_dir():
        raise OPFError("scan root is not a directory: {}".format(base))
    include_patterns = tuple(include)
    exclude_patterns = tuple(exclude)
    findings: list[PromptFinding] = []
    for current, directories, filenames in os.walk(base, followlinks=False):
        current_path = Path(current)
        kept = []
        for directory in sorted(directories):
            candidate = current_path / directory
            relative = candidate.relative_to(base).as_posix()
            if directory in DEFAULT_EXCLUDED or _matches(relative, exclude_patterns):
                continue
            if candidate.is_symlink():
                try:
                    candidate.resolve().relative_to(base)
                except ValueError:
                    findings.append(PromptFinding(relative, "symlink", "low", "directory symlink escapes scan root and was not followed"))
                    continue
                continue
            kept.append(directory)
        directories[:] = kept
        for filename in sorted(filenames):
            path = current_path / filename
            relative = path.relative_to(base).as_posix()
            if path.suffix.lower() not in PROMPT_SUFFIXES and filename not in {"opf.yaml", "promptfooconfig.yaml"}:
                continue
            if include_patterns and not _matches(relative, include_patterns):
                continue
            if _matches(relative, exclude_patterns):
                continue
            try:
                if path.is_symlink():
                    path.resolve().relative_to(base)
                    continue
                if path.stat().st_size > 1_000_000:
                    findings.append(PromptFinding(relative, "oversized", "low", "file exceeds the 1 MB inspection limit"))
                    continue
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError, ValueError):
                findings.append(PromptFinding(relative, "unreadable", "low", "file could not be safely inspected as UTF-8 text"))
                continue
            detected = _classify(path, relative, source)
            if detected:
                source_kind, confidence, reason = detected
                findings.append(PromptFinding(relative, source_kind, confidence, reason))
    return sorted(findings, key=lambda item: item.path)
