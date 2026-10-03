"""Common types and interfaces for prompt import adapters."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from ..compatibility import CompatibilityReport
from ..core import OPFError


def normalized_digest(source: str) -> str:
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourcePrompt:
    path: Path
    relative_path: str
    source_kind: str
    text: str
    source_digest: str
    source_format_version: Optional[str] = None
    data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class MigrationOutput:
    files: Mapping[str, str]
    registry_entry: Mapping[str, Any] | None
    manifest_record: Mapping[str, Any]


@dataclass(frozen=True)
class MigrationPlan:
    prompt_id: str
    source: SourcePrompt
    output: MigrationOutput
    compatibility: CompatibilityReport
    converter: str
    converter_version: str = "0.3.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "source": {
                "path": self.source.relative_path,
                "kind": self.source.source_kind,
                "format_version": self.source.source_format_version,
                "digest": self.source.source_digest,
            },
            "generated_files": dict(self.output.files),
            "registry_entry": dict(self.output.registry_entry) if self.output.registry_entry is not None else None,
            "manifest_record": dict(self.output.manifest_record),
            "compatibility": self.compatibility.to_dict(),
            "converter": self.converter,
            "converter_version": self.converter_version,
        }


class SourceAdapter(ABC):
    source_kind = "unknown"
    converter = "opf-migrate-unknown"

    @abstractmethod
    def inspect(self, path: str | Path, *, root: str | Path = ".") -> SourcePrompt:
        """Read a source prompt without modifying it."""

    @abstractmethod
    def plan(self, source: SourcePrompt, prompt_id: str, *, role: str | None = None) -> MigrationPlan:
        """Build a deterministic migration plan without filesystem writes."""

    @abstractmethod
    def convert(self, source: SourcePrompt, plan: MigrationPlan) -> MigrationOutput:
        """Return generated files and metadata for the previously inspected source."""


def read_source(path: str | Path, root: str | Path, source_kind: str) -> SourcePrompt:
    base = Path(root).resolve()
    source_path = Path(path)
    if not source_path.is_absolute():
        source_path = base / source_path
    try:
        resolved = source_path.resolve(strict=True)
        relative_path = resolved.relative_to(base).as_posix()
    except (OSError, ValueError) as exc:
        raise OPFError("source prompt must exist inside the migration root: {}".format(path)) from exc
    if source_path.is_symlink() or not resolved.is_file():
        raise OPFError("source prompt must be a regular file: {}".format(path))
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise OPFError("cannot read source prompt {}: {}".format(relative_path, exc)) from exc
    return SourcePrompt(resolved, relative_path, source_kind, text, normalized_digest(text))
