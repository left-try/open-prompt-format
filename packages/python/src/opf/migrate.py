"""Safe, local-only source prompt inspection and migration application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .adapters import AutoGenAdapter, CrewAIAdapter, JinjaAdapter, LangChainAdapter, MarkdownAdapter, OpenAIPromptAdapter
from .adapters.base import MigrationPlan, SourceAdapter
from .adapters.markdown import generated_id
from .core import OPFError

ADAPTERS: dict[str, SourceAdapter] = {
    "markdown": MarkdownAdapter(),
    "jinja2": JinjaAdapter(),
    "openai": OpenAIPromptAdapter(),
    "langchain": LangChainAdapter(),
    "crewai": CrewAIAdapter(),
    "autogen": AutoGenAdapter(),
}


def adapter_for(path: str | Path, kind: str | None = None, *, root: str | Path = ".") -> SourceAdapter:
    if kind:
        try:
            return ADAPTERS[kind]
        except KeyError as exc:
            raise OPFError("unknown source adapter {!r}; choose {}".format(kind, ", ".join(sorted(ADAPTERS)))) from exc
    suffix = Path(path).suffix.lower()
    if suffix == ".j2":
        return ADAPTERS["jinja2"]
    if suffix == ".py":
        return ADAPTERS["autogen"]
    if suffix in {".yaml", ".yml", ".json"}:
        if suffix == ".json":
            try:
                candidate = Path(path)
                if not candidate.is_absolute():
                    candidate = Path(root) / candidate
                if json.loads(candidate.read_text(encoding="utf-8")).get("schema") == "openai-prompt-snapshot/1":
                    return ADAPTERS["openai"]
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                pass
        return ADAPTERS["langchain"]
    return ADAPTERS["markdown"]


def plan_migration(path: str | Path, *, root: str | Path = ".", prompt_id: str | None = None, role: str | None = None, kind: str | None = None) -> MigrationPlan:
    adapter = adapter_for(path, kind, root=root)
    source = adapter.inspect(path, root=root)
    identifier = prompt_id or generated_id(source.relative_path)
    return adapter.plan(source, identifier, role=role)


def apply_migration(plan: MigrationPlan, *, root: str | Path = ".", strict: bool = False, register: bool = False, registry_path: str = "opf.yaml") -> dict[str, Any]:
    report = plan.compatibility
    blocked = not report.can_apply or (strict and any(f.disposition in {"dropped", "manual"} or f.severity == "error" for f in report.findings))
    if blocked:
        raise OPFError("migration is not applicable under the selected compatibility policy")
    base = Path(root).resolve()
    files = dict(plan.output.files)
    intentional_updates: set[str] = set()
    if plan.output.registry_entry is not None:
        registry = plan.output.registry_entry
        for message in registry.get("messages", []):
            rel = Path(message["file"])
            if rel.is_absolute() or ".." in rel.parts:
                raise OPFError("registry source path escapes migration root")
            files[rel.as_posix()] = plan.source.text
    if register:
        files.setdefault(plan.source.relative_path, plan.source.text)
        registry_rel = Path(registry_path)
        if registry_rel.is_absolute() or ".." in registry_rel.parts:
            raise OPFError("registry path must stay inside the migration root")
        registry_file = base / registry_rel
        try:
            config = yaml.safe_load(registry_file.read_text(encoding="utf-8")) if registry_file.exists() else {"schema": "opf-registry/1", "prompts": {}}
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise OPFError("cannot read registry configuration: {}".format(exc)) from exc
        if not isinstance(config, dict) or config.get("schema") != "opf-registry/1" or not isinstance(config.get("prompts"), dict):
            raise OPFError("registry configuration must contain schema: opf-registry/1 and a prompts mapping")
        entry = plan.output.registry_entry
        if entry is None:
            generated = next(iter(plan.output.files), None)
            if generated is None:
                raise OPFError("migration plan has no generated prompt to register")
            entry = {"renderer": "opf", "source": generated}
        existing_entry = config["prompts"].get(plan.prompt_id)
        if existing_entry is not None and existing_entry != entry:
            raise OPFError("prompt id {} is already registered with a different definition".format(plan.prompt_id))
        config["prompts"][plan.prompt_id] = dict(entry)
        manifest_rel = Path(config.get("migration_manifest", ".opf/migrations.yaml"))
        if manifest_rel.is_absolute() or ".." in manifest_rel.parts:
            raise OPFError("configured migration manifest path must stay inside the registry root")
        config["migration_manifest"] = manifest_rel.as_posix()
        manifest_file = base / manifest_rel
        if manifest_file.exists():
            try:
                manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, yaml.YAMLError) as exc:
                raise OPFError("cannot read migration manifest: {}".format(exc)) from exc
        else:
            manifest = {"schema": "opf-migration-manifest/1", "migrations": {}}
        if not isinstance(manifest, dict) or manifest.get("schema") != "opf-migration-manifest/1" or not isinstance(manifest.get("migrations"), dict):
            raise OPFError("migration manifest must use schema: opf-migration-manifest/1")
        prior_record = manifest["migrations"].get(plan.prompt_id)
        next_record = dict(plan.output.manifest_record)
        if prior_record is not None:
            identity = ("source_path", "source_digest", "converter", "converter_version")
            if not isinstance(prior_record, dict) or any(prior_record.get(key) != next_record.get(key) for key in identity):
                raise OPFError("prompt id {} already has different migration provenance".format(plan.prompt_id))
            next_record = dict(prior_record)
        manifest["migrations"][plan.prompt_id] = next_record
        files[registry_rel.as_posix()] = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
        files[manifest_rel.as_posix()] = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
        intentional_updates.update({registry_rel.as_posix(), manifest_rel.as_posix()})
    destinations: list[tuple[Path, str, str]] = []
    for relative, content in files.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise OPFError("generated path escapes migration root: {}".format(relative))
        destination = (base / rel).resolve()
        try:
            destination.relative_to(base)
        except ValueError as exc:
            raise OPFError("generated path escapes migration root: {}".format(relative)) from exc
        if destination.exists() and relative not in intentional_updates:
            try:
                existing = destination.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise OPFError("destination exists but is not a readable UTF-8 file: {}".format(rel.as_posix())) from exc
            if existing != content:
                raise OPFError("destination collision; refusing to overwrite {}".format(rel.as_posix()))
        destinations.append((destination, content, relative))
    # Preflight all destinations before making any filesystem changes.
    for destination, content, relative in destinations:
        if destination.exists() and relative not in intentional_updates:
            continue
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise OPFError("cannot write migration output {}: {}".format(relative, exc)) from exc
    return {"prompt_id": plan.prompt_id, "written": [str(path.relative_to(base)) for path, _, _ in destinations], "manifest_record": dict(plan.output.manifest_record), "compatibility": report.to_dict()}


def dump_plan(plan: MigrationPlan) -> str:
    return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
