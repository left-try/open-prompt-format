"""Compare prompt sources and report cache-prefix evidence without provider claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .core import OPFError, parse
from .registry import Registry


@dataclass(frozen=True)
class DiffReport:
    id: str
    base: str
    target: str
    changed: bool
    changes: tuple[dict[str, Any], ...]
    stable_prefix_messages: int | None
    cacheability: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _source(registry: Registry, prompt_id: str, ref: str) -> tuple[str, str, dict[str, str]]:
    if ref in {"working-tree", "worktree", "draft"}:
        prompt = registry.get(prompt_id)
        definition = prompt.bundle["definition"]
        if definition["renderer"] != "opf":
            raise OPFError("diff currently compares OPF sources; Jinja rendering is dynamic")
        path = definition["source"]
        return registry._read_local(path), path, prompt.bundle["files"]
    version = ref
    if ref.startswith("channel:"):
        channel = ref.split(":", 1)[1]
        registered = registry.get(prompt_id, channel=channel)
        version = registered.version or ""
        return _source_from_bundle(registered.bundle)
    registered = registry.get(prompt_id, version=version)
    return _source_from_bundle(registered.bundle)


def _source_from_bundle(bundle: dict) -> tuple[str, str, dict[str, str]]:
    definition = bundle["definition"]
    if definition["renderer"] != "opf":
        raise OPFError("diff currently compares OPF sources; Jinja rendering is dynamic")
    path = definition["source"]
    return bundle["files"][path], path, bundle["files"]


def compare(prompt_id: str, base: str, target: str, *, registry_path: str | Path = "opf.yaml") -> DiffReport:
    registry = Registry.local(registry_path)
    base_text, base_path, base_files = _source(registry, prompt_id, base)
    target_text, target_path, target_files = _source(registry, prompt_id, target)
    old, new = parse(base_text), parse(target_text)
    changes: list[dict[str, Any]] = []
    if base_path != target_path:
        changes.append({"kind": "source_path", "before": base_path, "after": target_path})
    if old.metadata.get("inputs", {}) != new.metadata.get("inputs", {}):
        changes.append({"kind": "inputs", "before": old.metadata.get("inputs", {}), "after": new.metadata.get("inputs", {})})
    metadata_keys = sorted((set(old.metadata) | set(new.metadata)) - {"id", "version", "inputs"})
    for key in metadata_keys:
        if old.metadata.get(key) != new.metadata.get(key):
            changes.append({"kind": "metadata", "field": key, "before": old.metadata.get(key), "after": new.metadata.get(key)})
    max_len = max(len(old.messages), len(new.messages))
    prefix = 0
    for i in range(max_len):
        before = old.messages[i] if i < len(old.messages) else None
        after = new.messages[i] if i < len(new.messages) else None
        if before == after and before is not None:
            if i == prefix:
                prefix += 1
            continue
        changes.append({"kind": "message", "index": i, "before": _msg(before), "after": _msg(after)})
    if base_files != target_files:
        paths = sorted(set(base_files) | set(target_files))
        for path in paths:
            if base_files.get(path) != target_files.get(path) and path not in {base_path, target_path}:
                changes.append({"kind": "dependency", "path": path, "before_present": path in base_files, "after_present": path in target_files})
    # Compare message prefix, not the full dynamic rendering. Variable-bearing prefix messages are conditional.
    from .core import VARIABLE_RE
    variable_prefix = any(VARIABLE_RE.search(content) for _, content in new.messages[:prefix])
    limitations = []
    if variable_prefix:
        limitations.append("shared prefix contains input variables; identical rendered content depends on runtime values")
    if old.metadata.get("format") != new.metadata.get("format"):
        limitations.append("format versions differ")
    if not prefix:
        cacheability = "no_shared_message_prefix"
    elif variable_prefix:
        cacheability = "conditional_shared_prefix"
    else:
        cacheability = "stable_prefix_candidate"
    return DiffReport(prompt_id, base, target, base_files != target_files or old.messages != new.messages or old.metadata.get("inputs") != new.metadata.get("inputs"), tuple(changes), prefix, cacheability, tuple(limitations))


def _msg(message: tuple[str, str] | None) -> dict | None:
    return None if message is None else {"role": message[0], "content": message[1]}
