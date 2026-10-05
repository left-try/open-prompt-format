"""Stable compatibility report structures shared by OPF adapters."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

Severity = Literal["info", "warning", "error"]
Disposition = Literal["preserved", "approximated", "dropped", "manual"]
Category = Literal["portable", "preserved_resource", "adapter_runtime", "unsupported", "data_loss"]


def data_loss_code(field: str) -> str:
    safe_field = field if re.fullmatch(r"[A-Za-z0-9_.-]+", field) else "field-" + hashlib.sha256(field.encode("utf-8")).hexdigest()[:16]
    return "metadata.value.not_json_compatible[{}]".format(safe_field)


@dataclass(frozen=True)
class CompatibilityFinding:
    code: str
    severity: Severity
    disposition: Disposition
    message: str
    capability: Optional[str] = None
    source_path: Optional[str] = None
    category: Optional[Category] = None
    source_line: Optional[int] = None
    source_field: Optional[str] = None
    recommendation: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class CompatibilityReport:
    source_kind: str
    target_kind: str
    findings: tuple[CompatibilityFinding, ...]
    lossless: bool
    can_apply: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "target_kind": self.target_kind,
            "findings": [finding.to_dict() for finding in self.findings],
            "lossless": self.lossless,
            "can_apply": self.can_apply,
        }
