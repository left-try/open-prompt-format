"""Aggregate local OPF validation and advisory checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .core import OPFError, load, parse
from .discovery import scan
from .registry import Registry
from .safety import analyze
from .adapters.jinja import JinjaAdapter


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    category: str | None = None
    recommendation: str | None = None

    def to_dict(self) -> dict:
        value = asdict(self)
        if self.category is None:
            value.pop("category")
        if self.recommendation is None:
            value.pop("recommendation")
        return value


def check(root: str | Path = ".", *, registry_path: str | Path | None = None, safety: bool = True) -> list[Finding]:
    base = Path(root).resolve()
    findings: list[Finding] = []
    registry_file = Path(registry_path).resolve() if registry_path else base / "opf.yaml"
    registered: set[Path] = set()
    ids: dict[str, str] = {}
    if registry_file.exists():
        try:
            registry = Registry.local(registry_file)
            for prompt_id, definition in registry.config["prompts"].items():
                sources = ([definition["source"]] if definition["renderer"] == "opf" else [item["file"] for item in definition["messages"]])
                for relative_source in sources:
                    registered.add((registry.root / relative_source).resolve())
                source = (registry.root / sources[0]).resolve()
                try:
                    registered_prompt = registry.get(prompt_id)
                    if definition["renderer"] == "opf":
                        prompt = parse(registry._read_local(definition["source"]), path=source)
                        if prompt.id != prompt_id:
                            raise OPFError("prompt id {!r} does not match registry id {!r}".format(prompt.id, prompt_id))
                        ids[prompt.id] = _rel(source, base)
                        findings.extend(_compatibility_findings(prompt, source, base))
                        if safety:
                            findings.extend(Finding(**item.to_dict()) for item in analyze(registry_prompt_source(registered_prompt), path=_rel(source, base), variables=prompt.metadata.get("inputs", {})))
                    else:
                        adapter = JinjaAdapter()
                        for message in definition["messages"]:
                            relative_source = message["file"]
                            source_path = registry.root / relative_source
                            migration_source = adapter.inspect(source_path, root=registry.root)
                            migration_plan = adapter.plan(migration_source, prompt_id, role=message["role"])
                            findings.extend(_report_findings(migration_plan.compatibility, source_path, base))
                        if safety:
                            for relative_source in sorted(registered_prompt.bundle["files"]):
                                findings.extend(Finding(**item.to_dict()) for item in analyze(registered_prompt.bundle["files"][relative_source], path=_rel(registry.root / relative_source, base), variables=definition.get("inputs", {})))
                except (OPFError, OSError, ValueError) as exc:
                    findings.append(Finding("check.prompt.invalid", "error", str(exc), _rel(source, base)))
        except (OPFError, OSError, ValueError) as exc:
            findings.append(Finding("check.registry.invalid", "error", str(exc), _rel(registry_file, base)))
    try:
        candidates = scan(base)
        for item in candidates:
            if item.source_kind != "opf":
                continue
            candidate = (base / item.path).resolve()
            if candidate in registered:
                continue
            try:
                prompt = load(candidate)
                previous = ids.get(prompt.id)
                if previous is not None:
                    findings.append(Finding("check.prompt.duplicate_id", "error", "duplicate prompt id {!r}; also defined at {}".format(prompt.id, previous), item.path))
                else:
                    ids[prompt.id] = item.path
                findings.extend(_compatibility_findings(prompt, candidate, base))
                if safety:
                    findings.extend(Finding(**finding.to_dict()) for finding in analyze(candidate.read_text(encoding="utf-8"), path=item.path, variables=prompt.metadata.get("inputs", {})))
            except (OPFError, OSError, ValueError) as exc:
                findings.append(Finding("check.prompt.invalid", "error", str(exc), item.path))
    except OPFError as exc:
        findings.append(Finding("check.scan.failed", "error", str(exc), _rel(base, base)))
    return _dedupe(findings)


def registry_prompt_source(prompt) -> str:
    definition = prompt.bundle["definition"]
    return prompt.bundle["files"][definition["source"]]


def _compatibility_findings(prompt, source: Path, root: Path) -> list[Finding]:
    return _report_findings(prompt.compatibility(), source, root)


def _report_findings(report, source: Path, root: Path) -> list[Finding]:
    path = _rel(source, root)
    return [
        Finding(
            item.code,
            item.severity,
            item.message,
            _rel(Path(item.source_path), root) if item.source_path else path,
            item.source_line,
            None,
            item.category,
            item.recommendation,
        )
        for item in report.findings
    ]


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _dedupe(items: list[Finding]) -> list[Finding]:
    seen: set[tuple] = set()
    result = []
    for item in items:
        key = (item.code, item.path, item.line, item.column, item.message)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return sorted(result, key=lambda item: (item.path or "", item.line or 0, item.code))
