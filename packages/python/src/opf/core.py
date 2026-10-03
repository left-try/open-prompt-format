"""Parsing and rendering for OPF 0.1 and the versionless OPF 0.2 syntax."""

from __future__ import annotations

import hashlib
import copy
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from .compatibility import CompatibilityFinding, CompatibilityReport


class OPFError(ValueError):
    """Raised when an OPF file is invalid or cannot be rendered."""


ROLES = {"system", "developer", "user", "assistant"}
ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?$"
)
VARIABLE_RE = re.compile(r"(?<!\\)\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
ESCAPED_OPEN_RE = re.compile(r"\\\{\{")
HEADING_RE = re.compile(r"^## (system|developer|user|assistant)$")


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    """Reject duplicate YAML keys so metadata cannot silently change meaning."""
    mapping: Dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise OPFError("duplicate YAML key: {!r}".format(key))
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


_UniqueSafeLoader.yaml_implicit_resolvers = {
    first: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag not in {
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:timestamp",
            "tag:yaml.org,2002:merge",
            "tag:yaml.org,2002:value",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:float",
        }
    ]
    for first, resolvers in copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers).items()
}
_UniqueSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)
_UniqueSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^[-+]?(?:0|[1-9][0-9_]*|0o[0-7_]+|0x[0-9a-fA-F_]+|0b[0-1_]+)$"),
    list("-+0123456789"),
)
_UniqueSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:(?:(?:[0-9][0-9_]*)?\.[0-9_]+|[0-9][0-9_]*\.)(?:[eE][-+]?[0-9]+)?|[0-9][0-9_]*[eE][-+]?[0-9]+|\.(?:inf|Inf|INF|nan|NaN|NAN))$"),
    list("-+0123456789."),
)


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _split_frontmatter(text: str) -> Tuple[dict, str]:
    if text.startswith("\ufeff"):
        text = text[1:]
    if text.startswith("\r\n"):
        raise OPFError("frontmatter opening delimiter must be the first line")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise OPFError("frontmatter opening delimiter '---' must be the first line")
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"),
        None,
    )
    if closing is None:
        raise OPFError("frontmatter closing delimiter '---' was not found")
    raw = "".join(lines[1:closing])
    body = "".join(lines[closing + 1 :])
    try:
        metadata = yaml.load(raw, Loader=_UniqueSafeLoader)
    except OPFError:
        raise
    except yaml.YAMLError as exc:
        raise OPFError("invalid YAML frontmatter: {}".format(exc)) from exc
    if not isinstance(metadata, dict):
        raise OPFError("frontmatter must be a YAML mapping")
    return metadata, body


def _validate_metadata(metadata: dict) -> None:
    allowed = {"format", "id", "version", "description", "tags", "inputs", "extensions"}
    unknown = set(metadata) - allowed
    if unknown:
        raise OPFError("unknown frontmatter field(s): {}".format(", ".join(sorted(map(str, unknown)))))
    for field in ("format", "id"):
        if field not in metadata:
            raise OPFError("missing required frontmatter field: {}".format(field))
    if metadata["format"] not in {"opf/0.1", "opf/0.2", "opf/0.3"}:
        raise OPFError("unsupported format {!r}; expected 'opf/0.1', 'opf/0.2', or 'opf/0.3'".format(metadata["format"]))
    if metadata["format"] == "opf/0.1" and "version" not in metadata:
        raise OPFError("missing required frontmatter field: version")
    if metadata["format"] in {"opf/0.2", "opf/0.3"} and "version" in metadata:
        raise OPFError("{} keeps release versions in the registry; remove frontmatter version".format(metadata["format"]))
    if not isinstance(metadata["id"], str) or not ID_RE.fullmatch(metadata["id"]):
        raise OPFError("id must match [a-z0-9]+(?:[._-][a-z0-9]+)*")
    if "version" in metadata and (not isinstance(metadata["version"], str) or not VERSION_RE.fullmatch(metadata["version"])):
        raise OPFError("version must be SemVer MAJOR.MINOR.PATCH without build metadata")
    if "description" in metadata and not isinstance(metadata["description"], str):
        raise OPFError("description must be a string")
    if "tags" in metadata and (
        not isinstance(metadata["tags"], list)
        or any(not isinstance(tag, str) for tag in metadata["tags"])
    ):
        raise OPFError("tags must be a list of strings")
    inputs = metadata.get("inputs", {})
    if not isinstance(inputs, dict):
        raise OPFError("inputs must be a mapping")
    for name, spec in inputs.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise OPFError("invalid input name {!r}".format(name))
        if not isinstance(spec, dict):
            raise OPFError("input {!r} must be a mapping".format(name))
        extra = set(spec) - {"type", "required"}
        if extra:
            raise OPFError("unknown field(s) for input {!r}: {}".format(name, ", ".join(sorted(extra))))
        if spec.get("type") != "string":
            raise OPFError("input {!r} must declare type: string".format(name))
        if "required" in spec and not isinstance(spec["required"], bool):
            raise OPFError("input {!r} required must be a boolean".format(name))
    if "extensions" in metadata:
        if not isinstance(metadata["extensions"], dict):
            raise OPFError("extensions must be a mapping")
        if metadata["format"] == "opf/0.3":
            _validate_extensions(metadata["extensions"])


EXTENSION_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
EXTENSION_VERSION_RE = re.compile(r"^[!-~]{1,64}$")


def _validate_json_value(value: Any, path: str, active: set[int]) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OPFError("{} must not contain a non-finite number".format(path))
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise OPFError("{} must not contain cyclic YAML aliases".format(path))
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _validate_json_value(item, "{}[{}]".format(path, index), active)
        finally:
            active.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise OPFError("{} must not contain cyclic YAML aliases".format(path))
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise OPFError("{} must use string mapping keys".format(path))
                _validate_json_value(item, "{}.{}".format(path, key), active)
        finally:
            active.remove(identity)
        return
    raise OPFError("{} contains a value that is not JSON-compatible".format(path))


def _validate_extensions(extensions: dict) -> None:
    for identifier, record in extensions.items():
        if not isinstance(identifier, str) or len(identifier.encode("utf-8")) > 255 or not EXTENSION_ID_RE.fullmatch(identifier):
            raise OPFError("invalid extension identifier {!r}".format(identifier))
        if not isinstance(record, dict):
            raise OPFError("extension {!r} must be a mapping".format(identifier))
        if set(record) != {"version", "required", "data"}:
            raise OPFError("extension {!r} requires exactly version, required, and data".format(identifier))
        version = record["version"]
        if not isinstance(version, str) or not EXTENSION_VERSION_RE.fullmatch(version):
            raise OPFError("extension {!r} version must be 1-64 printable non-space ASCII characters".format(identifier))
        if not isinstance(record["required"], bool):
            raise OPFError("extension {!r} required must be a boolean".format(identifier))
        if not isinstance(record["data"], dict):
            raise OPFError("extension {!r} data must be a mapping".format(identifier))
        _validate_json_value(record["data"], "extension {!r} data".format(identifier), set())


def _parse_messages(body: str) -> List[Tuple[str, str]]:
    messages: List[Tuple[str, str]] = []
    role: Optional[str] = None
    content: List[str] = []
    fence_char: Optional[str] = None
    fence_len = 0

    def message_text(lines: List[str]) -> str:
        start, end = 0, len(lines)
        while start < end and not lines[start].strip():
            start += 1
        while end > start and not lines[end - 1].strip():
            end -= 1
        return "\n".join(lines[start:end])

    for line in re.split(r"\r\n|\r|\n", body):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            marker = fence.group(1)
            char = marker[0]
            if fence_char is None:
                fence_char, fence_len = char, len(marker)
            elif char == fence_char and len(marker) >= fence_len and not fence.group(2).strip():
                fence_char, fence_len = None, 0
            elif role is not None:
                content.append(line)
                continue
            if role is not None:
                content.append(line)
            elif line.strip():
                raise OPFError("non-whitespace content appears before the first message")
            continue
        heading = None if fence_char else HEADING_RE.fullmatch(line)
        if heading:
            if role is not None:
                messages.append((role, message_text(content)))
            role = heading.group(1)
            content = []
            continue
        if role is None:
            if line.strip():
                raise OPFError("non-whitespace content appears before the first message")
            continue
        escaped = None if fence_char else re.fullmatch(r"\\(## (?:system|developer|user|assistant))", line)
        content.append(escaped.group(1) if escaped else line)
    if role is not None:
        messages.append((role, message_text(content)))
    if not messages:
        raise OPFError("prompt must contain at least one message")
    return messages


def _validate_templates(metadata: Mapping[str, Any], messages: Sequence[Tuple[str, str]]) -> None:
    declared = set(metadata.get("inputs", {}))
    for _role, template in messages:
        without_escaped_open = ESCAPED_OPEN_RE.sub("", template)
        stripped = VARIABLE_RE.sub("", without_escaped_open)
        if "{{" in stripped or "{%" in stripped:
            raise OPFError("unsupported or malformed template expression; use only {{ input_name }}")
        variables = set(VARIABLE_RE.findall(template))
        unknown = variables - declared
        if unknown:
            raise OPFError("template uses undeclared input(s): {}".format(", ".join(sorted(unknown))))


@dataclass(frozen=True)
class Prompt:
    """Parsed OPF prompt, ready to render with declared string inputs."""

    metadata: Mapping[str, Any]
    messages: Sequence[Tuple[str, str]]
    source_digest: str
    path: Optional[Path] = None

    @property
    def id(self) -> str:
        return self.metadata["id"]

    @property
    def version(self) -> Optional[str]:
        return self.metadata.get("version")

    @property
    def extensions(self) -> Mapping[str, Any]:
        """Return a detached copy so callers cannot mutate the parsed extension payload."""
        return copy.deepcopy(self.metadata.get("extensions", {}))

    def compatibility(
        self,
        *,
        strict: bool = False,
        supported_extensions: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> CompatibilityReport:
        """Report extension support without changing portable-core rendering."""
        supported = supported_extensions or {}
        findings = []
        for identifier, record in self.metadata.get("extensions", {}).items():
            versions = supported.get(identifier, ())
            if record["version"] in versions:
                continue
            required = record["required"]
            findings.append(
                CompatibilityFinding(
                    code="extension.unsupported",
                    severity="error" if required and strict else "warning",
                    disposition="manual" if required else "preserved",
                    message=(
                        "required extension {!r} version {!r} is not supported by this consumer".format(
                            identifier, record["version"]
                        )
                        if required
                        else "optional extension {!r} version {!r} is preserved but not interpreted".format(
                            identifier, record["version"]
                        )
                    ),
                    capability=identifier,
                )
            )
        return CompatibilityReport(
            source_kind=str(self.metadata.get("format", "unknown")),
            target_kind="opf-core",
            findings=tuple(findings),
            lossless=all(item.disposition == "preserved" for item in findings),
            can_apply=not any(item.severity == "error" for item in findings),
        )

    def render(self, **inputs: str) -> List[dict]:
        declared = self.metadata.get("inputs", {})
        unknown = set(inputs) - set(declared)
        if unknown:
            raise OPFError("undeclared input(s): {}".format(", ".join(sorted(unknown))))
        for name, spec in declared.items():
            if spec.get("required", True) and name not in inputs:
                raise OPFError("missing required input: {}".format(name))
        for name, value in inputs.items():
            if not isinstance(value, str):
                raise OPFError("input {!r} must be a string".format(name))
        rendered = []
        for role, template in self.messages:
            names = set(VARIABLE_RE.findall(template))
            missing = names - set(inputs)
            if missing:
                raise OPFError("missing template input(s): {}".format(", ".join(sorted(missing))))
            content = VARIABLE_RE.sub(lambda match: inputs[match.group(1)], template)
            content = ESCAPED_OPEN_RE.sub("{{", content)
            rendered.append({"role": role, "content": content})
        return rendered


def parse(text: str, *, path: Optional[Path] = None) -> Prompt:
    """Parse prompt text according to OPF 0.1."""
    metadata, body = _split_frontmatter(text)
    _validate_metadata(metadata)
    messages = _parse_messages(body)
    _validate_templates(metadata, messages)
    normalized_source = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    digest = "sha256:" + hashlib.sha256(normalized_source).hexdigest()
    return Prompt(metadata=metadata, messages=messages, source_digest=digest, path=path)


def load(path: str | Path) -> Prompt:
    """Load one OPF prompt file from disk."""
    prompt_path = Path(path)
    try:
        text = prompt_path.read_bytes().decode("utf-8")
    except OSError as exc:
        raise OPFError("cannot read prompt file {}: {}".format(prompt_path, exc)) from exc
    return parse(text, path=prompt_path)


def load_by_id(prompt_id: str, collection: str | Path) -> Prompt:
    """Load a prompt by stable ID from a directory tree; reject duplicate IDs."""
    root = Path(collection)
    prompts = load_collection(root)
    matches = [prompt for prompt in prompts if prompt.id == prompt_id]
    if not matches:
        raise OPFError("prompt id {!r} not found in {}".format(prompt_id, root))
    return matches[0]


def load_collection(collection: str | Path) -> List[Prompt]:
    """Load all Markdown prompts recursively and reject duplicate IDs."""
    root = Path(collection)
    try:
        files = sorted(root.rglob("*.md"))
    except OSError as exc:
        raise OPFError("cannot scan prompt collection {}: {}".format(root, exc)) from exc
    prompts: List[Prompt] = []
    seen: Dict[str, Path] = {}
    for file_path in files:
        candidate = load(file_path)
        if candidate.id in seen:
            raise OPFError(
                "duplicate prompt id {!r}: {}, {}".format(candidate.id, seen[candidate.id], file_path)
            )
        seen[candidate.id] = file_path
        prompts.append(candidate)
    return prompts
