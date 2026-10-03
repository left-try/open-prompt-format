"""Best-effort static prompt safety advisories; not a security proof."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class SafetyFinding:
    code: str
    severity: str
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("safety.injection.override", re.compile(r"(?i)\b(ignore|disregard|override)\b.{0,60}\b(previous|prior|system|developer|above)\b"), "Possible instruction override language; review whether this is intentional."),
    ("safety.injection.secret", re.compile(r"(?i)\b(reveal|print|show|expose|dump)\b.{0,60}\b(hidden|system|developer|secret|internal)\b.{0,40}\b(prompt|instruction|message|key|data)s?\b"), "Possible request to expose hidden instructions or secrets."),
    ("safety.injection.tool", re.compile(r"(?i)\b(call|invoke|execute|use)\b.{0,40}\b(tool|function|browser|shell|python|terminal)\b"), "Prompt contains tool-execution language; verify tool access is constrained by the application."),
)


def analyze(text: str, *, path: str | None = None, variables: Iterable[str] = ()) -> list[SafetyFinding]:
    """Return heuristic findings with source locations. Findings are advisory."""
    findings: list[SafetyFinding] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for code, pattern, message in _RULES:
            match = pattern.search(line)
            if match:
                findings.append(SafetyFinding(code, "warning", message, path, line_no, match.start() + 1))
    names = set(variables)
    if names and not re.search(r"(?i)\b(untrusted|user[- ]provided|treat .* as data|quoted data|customer.?s words)\b", text):
        for match in re.finditer(r"(?<!\\)\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", text):
            if match.group(1) not in names:
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            column = match.start() - text.rfind("\n", 0, match.start())
            findings.append(SafetyFinding("safety.input.boundary_missing", "warning", "Dynamic input is not explicitly described as untrusted data; review the trust boundary.", path, line_no, column))
    return findings
