"""Local, Git-backed prompt registry and portable release bundles."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

import yaml

from .core import ID_RE, ROLES, VERSION_RE, OPFError, _UniqueSafeLoader, parse


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise OPFError("prompt path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {".", ".."} for part in value.split("/")) or str(path) != value:
        raise OPFError("prompt path must be normalized and stay inside the registry: {!r}".format(value))
    return value


def _yaml_mapping(raw: str, label: str) -> dict:
    try:
        value = yaml.load(raw, Loader=_UniqueSafeLoader)
    except OPFError:
        raise
    except yaml.YAMLError as exc:
        raise OPFError("invalid YAML in {}: {}".format(label, exc)) from exc
    if not isinstance(value, dict):
        raise OPFError("{} must be a YAML mapping".format(label))
    return value


def _definition(prompt_id: str, value: Any) -> dict:
    if not ID_RE.fullmatch(prompt_id):
        raise OPFError("invalid prompt id {!r}".format(prompt_id))
    if not isinstance(value, dict):
        raise OPFError("prompt {!r} must be a mapping".format(prompt_id))
    extra = set(value) - {"renderer", "source", "messages", "inputs", "channels"}
    if extra:
        raise OPFError("unknown registry field(s) for {!r}: {}".format(prompt_id, ", ".join(sorted(extra))))
    renderer = value.get("renderer", "opf")
    if renderer not in {"opf", "jinja2"}:
        raise OPFError("unsupported renderer {!r}".format(renderer))
    if renderer == "opf":
        if "messages" in value or "inputs" in value or "source" not in value:
            raise OPFError("opf renderer requires source and no messages or registry inputs")
        definition = {"renderer": "opf", "source": _path(value["source"])}
    else:
        if "source" in value or not isinstance(value.get("messages"), list) or not value["messages"]:
            raise OPFError("jinja2 renderer requires a non-empty messages list and no source")
        messages = []
        for item in value["messages"]:
            if not isinstance(item, dict) or set(item) != {"role", "file"} or not isinstance(item["role"], str) or item["role"] not in ROLES:
                raise OPFError("jinja2 messages require role and file")
            messages.append({"role": item["role"], "file": _path(item["file"])})
        definition = {"renderer": "jinja2", "messages": messages}
        if "inputs" in value:
            inputs = value["inputs"]
            if not isinstance(inputs, dict):
                raise OPFError("registry inputs must be a mapping")
            for name, spec in inputs.items():
                if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or not isinstance(spec, dict) or set(spec) - {"type", "required"} or spec.get("type") != "string" or not isinstance(spec.get("required", True), bool):
                    raise OPFError("invalid string input {!r} for {!r}".format(name, prompt_id))
            definition["inputs"] = inputs
    channels = value.get("channels", {})
    if not isinstance(channels, dict):
        raise OPFError("channels for {!r} must be a mapping".format(prompt_id))
    for name, pointer in channels.items():
        if not isinstance(name, str) or not ID_RE.fullmatch(name) or not isinstance(pointer, dict) or set(pointer) != {"version", "digest"}:
            raise OPFError("invalid channel pointer for {!r}".format(prompt_id))
        if not isinstance(pointer["version"], str) or not VERSION_RE.fullmatch(pointer["version"]) or not _valid_digest(pointer["digest"]):
            raise OPFError("invalid version or digest in channel {!r}".format(name))
    return definition


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(c in "0123456789abcdef" for c in value[7:])


def _config(raw: str) -> dict:
    value = _yaml_mapping(raw, "opf.yaml")
    if set(value) - {"schema", "prompts", "migration_manifest"} or value.get("schema") != "opf-registry/1" or not isinstance(value.get("prompts"), dict):
        raise OPFError("opf.yaml requires schema: opf-registry/1 and a prompts mapping")
    if "migration_manifest" in value:
        value["migration_manifest"] = _path(value["migration_manifest"])
    for prompt_id, item in value["prompts"].items():
        if not isinstance(prompt_id, str):
            raise OPFError("prompt ids must be strings")
        _definition(prompt_id, item)
    return value


def _migration_manifest(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != {"schema", "migrations"} or value.get("schema") != "opf-migration-manifest/1" or not isinstance(value.get("migrations"), dict):
        raise OPFError("migration manifest requires schema: opf-migration-manifest/1 and a migrations mapping")
    result = {"schema": "opf-migration-manifest/1", "migrations": {}}
    for prompt_id, raw in value["migrations"].items():
        if not isinstance(prompt_id, str) or not ID_RE.fullmatch(prompt_id) or not isinstance(raw, dict):
            raise OPFError("migration manifest contains an invalid prompt entry")
        required = {"source_path", "source_kind", "converter", "converter_version", "migrated_at", "findings"}
        optional = {"source_format_version", "source_digest", "accepted_losses"}
        if required - set(raw) or set(raw) - required - optional:
            raise OPFError("migration record for {!r} has missing or unknown fields".format(prompt_id))
        record = dict(raw)
        record["source_path"] = _path(record["source_path"])
        for field in ("source_kind", "converter", "converter_version"):
            if not isinstance(record[field], str) or not record[field] or any(ord(char) < 32 for char in record[field]):
                raise OPFError("migration field {} for {!r} must be a non-empty string without control characters".format(field, prompt_id))
        if "source_format_version" in record and (not isinstance(record["source_format_version"], str) or not record["source_format_version"]):
            raise OPFError("source_format_version for {!r} must be a non-empty string".format(prompt_id))
        if "source_digest" in record and not _valid_digest(record["source_digest"]):
            raise OPFError("source_digest for {!r} must be a sha256 digest".format(prompt_id))
        if not isinstance(record["migrated_at"], str):
            raise OPFError("migrated_at for {!r} must be an RFC 3339 UTC timestamp".format(prompt_id))
        try:
            parsed_time = datetime.fromisoformat(record["migrated_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise OPFError("migrated_at for {!r} must be an RFC 3339 UTC timestamp".format(prompt_id)) from exc
        if not record["migrated_at"].endswith("Z") or parsed_time.utcoffset() != timezone.utc.utcoffset(parsed_time):
            raise OPFError("migrated_at for {!r} must end in Z".format(prompt_id))
        if not isinstance(record["findings"], list):
            raise OPFError("findings for {!r} must be a list".format(prompt_id))
        normalized_findings = []
        data_loss_codes = set()
        for finding in record["findings"]:
            finding_fields = {"code", "severity", "disposition", "message", "path", "category", "source_line", "source_field", "source_path", "capability", "recommendation"}
            if not isinstance(finding, dict) or set(finding) - finding_fields or not {"code", "severity", "disposition", "message"} <= set(finding):
                raise OPFError("invalid migration finding for {!r}".format(prompt_id))
            code = finding.get("code")
            loss_code = re.fullmatch(r"metadata\.value\.not_json_compatible\[[A-Za-z0-9_.-]+\]", code) if isinstance(code, str) else None
            if not isinstance(code, str) or not (ID_RE.fullmatch(code) or loss_code):
                raise OPFError("migration finding code for {!r} is invalid".format(prompt_id))
            if not isinstance(finding["severity"], str) or finding["severity"] not in {"info", "warning", "error"} or not isinstance(finding["disposition"], str) or finding["disposition"] not in {"preserved", "approximated", "dropped", "manual"}:
                raise OPFError("migration finding severity or disposition for {!r} is invalid".format(prompt_id))
            if not isinstance(finding["message"], str):
                raise OPFError("migration finding message or path for {!r} is invalid".format(prompt_id))
            category = finding.get("category")
            if category is not None and (not isinstance(category, str) or category not in {"portable", "preserved_resource", "adapter_runtime", "unsupported", "data_loss"}):
                raise OPFError("migration finding category for {!r} is invalid".format(prompt_id))
            for field in ("path", "source_path", "source_field", "capability", "recommendation"):
                if field in finding and not isinstance(finding[field], str):
                    raise OPFError("migration finding {} for {!r} is invalid".format(field, prompt_id))
            if "source_line" in finding and (not isinstance(finding["source_line"], int) or isinstance(finding["source_line"], bool) or finding["source_line"] < 1):
                raise OPFError("migration finding source_line for {!r} is invalid".format(prompt_id))
            item = dict(finding)
            if "path" in item:
                item["path"] = _path(item["path"])
            if "source_path" in item:
                item["source_path"] = _path(item["source_path"])
            if finding.get("category") == "data_loss":
                data_loss_codes.add(finding["code"])
            normalized_findings.append(item)
        record["findings"] = normalized_findings
        if "accepted_losses" in record:
            accepted = record["accepted_losses"]
            if not isinstance(accepted, list) or any(not isinstance(code, str) for code in accepted) or len(set(accepted)) != len(accepted) or not set(accepted) <= data_loss_codes:
                raise OPFError("accepted_losses for {!r} must uniquely name data-loss findings".format(prompt_id))
        result["migrations"][prompt_id] = record
    return result


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and result.returncode:
        raise OPFError("git {}: {}".format(" ".join(args), result.stderr.strip() or result.stdout.strip()))
    return result.stdout


def _join(parent: str, child: str) -> str:
    if child.startswith("/") or "\\" in child:
        raise OPFError("Jinja include must use a relative path: {!r}".format(child))
    return _path(posixpath.normpath(posixpath.join(posixpath.dirname(parent), child)))


def _jinja_environment(files: Mapping[str, str]):
    try:
        from jinja2 import DictLoader, Environment, StrictUndefined
    except ImportError as exc:
        raise OPFError("Jinja2 prompts require: pip install 'open-prompt-format[jinja]'") from exc

    class EnvironmentWithRelativeIncludes(Environment):
        def join_path(self, template: str, parent: str) -> str:
            return _join(parent, template)

    return EnvironmentWithRelativeIncludes(loader=DictLoader(dict(files)), undefined=StrictUndefined, autoescape=False)


def _files_for(definition: dict, read: Callable[[str], str]) -> dict[str, str]:
    files: dict[str, str] = {}
    roots = [definition["source"]] if definition["renderer"] == "opf" else [item["file"] for item in definition["messages"]]
    if definition["renderer"] == "opf":
        for path in roots:
            files[path] = read(path).replace("\r\n", "\n").replace("\r", "\n")
        return files
    environment = _jinja_environment({})
    from jinja2 import TemplateSyntaxError, meta

    def collect(path: str) -> None:
        if path in files:
            return
        source = read(path).replace("\r\n", "\n").replace("\r", "\n")
        files[path] = source
        try:
            tree = environment.parse(source)
            references = meta.find_referenced_templates(tree)
            for child in references:
                if child is None:
                    raise OPFError("dynamic Jinja include in {} requires an explicit dependency list".format(path))
                collect(_join(path, child))
        except TemplateSyntaxError as exc:
            raise OPFError("Jinja syntax error in {}:{}: {}".format(path, exc.lineno, exc.message)) from exc

    for path in roots:
        collect(path)
    return files


def _bundle(prompt_id: str, definition: dict, read: Callable[[str], str], migration: dict | None = None) -> dict:
    files = _files_for(definition, read)
    if definition["renderer"] == "opf":
        prompt = parse(files[definition["source"]])
        if prompt.id != prompt_id:
            raise OPFError("registry id {!r} differs from prompt id {!r}".format(prompt_id, prompt.id))
    schema = "opf-bundle/2" if migration is not None else "opf-bundle/1"
    if migration is not None:
        source_path = migration["source_path"]
        source_text = read(source_path).replace("\r\n", "\n").replace("\r", "\n")
        source_digest = "sha256:" + hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if migration.get("source_digest") and migration["source_digest"] != source_digest:
            raise OPFError("migration source digest does not match {}".format(source_path))
        if source_path in files and files[source_path] != source_text:
            raise OPFError("migration source conflicts with rendered file {}".format(source_path))
        files[source_path] = source_text
    payload = {"schema": schema, "id": prompt_id, "definition": definition, "files": files}
    if migration is not None:
        payload["migration_manifest"] = {"schema": "opf-migration-manifest/1", "migrations": {prompt_id: migration}}
    return {**payload, "digest": _digest(payload)}


def _validate_bundle(bundle: Any) -> dict:
    if not isinstance(bundle, dict) or set(bundle) - {"schema", "id", "definition", "files", "digest", "version", "commit", "migration_manifest"} or bundle.get("schema") not in {"opf-bundle/1", "opf-bundle/2"}:
        raise OPFError("invalid OPF bundle")
    if (bundle["schema"] == "opf-bundle/1") != ("migration_manifest" not in bundle):
        raise OPFError("bundle schema and migration manifest do not match")
    if "version" in bundle and (not isinstance(bundle["version"], str) or not VERSION_RE.fullmatch(bundle["version"])):
        raise OPFError("invalid bundle release version")
    if "commit" in bundle and not isinstance(bundle["commit"], str):
        raise OPFError("invalid bundle commit")
    prompt_id = bundle.get("id")
    definition = _definition(prompt_id, bundle.get("definition")) if isinstance(prompt_id, str) else None
    if definition != bundle.get("definition") or not isinstance(bundle.get("files"), dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in bundle["files"].items()):
        raise OPFError("invalid OPF bundle definition or files")
    files = bundle["files"]
    def read(path: str) -> str:
        if path not in files:
            raise OPFError("bundle is missing dependency {}".format(path))
        return files[path]

    migration = None
    if bundle["schema"] == "opf-bundle/2":
        manifest = _migration_manifest(bundle["migration_manifest"])
        if set(manifest["migrations"]) != {prompt_id}:
            raise OPFError("bundle migration manifest must contain only its prompt id")
        migration = manifest["migrations"][prompt_id]
    rebuilt = _bundle(prompt_id, definition, read, migration)
    if rebuilt["files"] != files or rebuilt["digest"] != bundle.get("digest"):
        raise OPFError("bundle digest or file set does not match contents")
    return bundle


@dataclass(frozen=True)
class PreparedPrompt:
    messages: list[dict]
    receipt: dict

    def call_receipt(self, *, provider: str, model: str, parameters: Mapping[str, Any] | None = None, model_version: str | None = None) -> dict:
        """Add the resolved model call settings without recording prompt inputs."""
        if not provider or not model:
            raise OPFError("provider and resolved model are required for a call receipt")
        result = {**self.receipt, "provider": provider, "model": model, "parameters": dict(parameters or {})}
        if model_version is not None:
            result["model_version"] = model_version
        return result


@dataclass(frozen=True)
class RegisteredPrompt:
    bundle: dict
    version: str | None = None
    channel: str | None = None

    def render(self, inputs: Mapping[str, str] | None = None) -> PreparedPrompt:
        values = dict(inputs or {})
        definition = self.bundle["definition"]
        files = self.bundle["files"]
        if definition["renderer"] == "opf":
            messages = parse(files[definition["source"]]).render(**values)
        else:
            declared = definition.get("inputs")
            if declared is not None:
                unknown = set(values) - set(declared)
                if unknown:
                    raise OPFError("undeclared input(s): {}".format(", ".join(sorted(unknown))))
                for name, spec in declared.items():
                    if spec.get("required", True) and name not in values:
                        raise OPFError("missing required input: {}".format(name))
            for name, value in values.items():
                if not isinstance(value, str):
                    raise OPFError("input {!r} must be a string".format(name))
            environment = _jinja_environment(files)
            from jinja2 import TemplateError
            messages = []
            for item in definition["messages"]:
                try:
                    content = environment.get_template(item["file"]).render(**values)
                except TemplateError as exc:
                    raise OPFError("Jinja render failed in {}: {}".format(item["file"], exc)) from exc
                messages.append({"role": item["role"], "content": content})
        receipt = {"id": self.bundle["id"], "version": self.version, "channel": self.channel, "bundle_digest": self.bundle["digest"], "render_digest": _digest(messages)}
        if self.bundle.get("commit"):
            receipt["commit"] = self.bundle["commit"]
        migration = self.bundle.get("migration_manifest", {}).get("migrations", {}).get(self.bundle["id"])
        if migration:
            receipt["migration"] = {
                "source_path": migration["source_path"],
                "source_kind": migration["source_kind"],
                "source_digest": migration.get("source_digest"),
                "converter": migration["converter"],
                "converter_version": migration["converter_version"],
            }
        return PreparedPrompt(messages, receipt)


class Registry:
    def __init__(self, config_path: str | Path):
        self.path = Path(config_path).resolve()
        self.root = self.path.parent
        try:
            self.config = _config(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise OPFError("cannot read registry {}: {}".format(self.path, exc)) from exc
        self.migration_manifest = None
        manifest_path = self.config.get("migration_manifest")
        if manifest_path:
            self.migration_manifest = _migration_manifest(_yaml_mapping(self._read_local(manifest_path), "migration manifest"))

    @classmethod
    def local(cls, config_path: str | Path = "opf.yaml") -> "Registry":
        return cls(config_path)

    @staticmethod
    def langfuse(*, base_url: str | None = None, public_key: str | None = None, secret_key: str | None = None):
        from .publish import LangfuseRegistry

        return LangfuseRegistry(base_url=base_url, public_key=public_key, secret_key=secret_key)

    @staticmethod
    def from_bundle(path: str | Path) -> RegisteredPrompt:
        bundle = _validate_bundle(json.loads(Path(path).read_text(encoding="utf-8")))
        return RegisteredPrompt(bundle, version=bundle.get("version"))

    def _read_local(self, path: str) -> str:
        target = self.root / _path(path)
        if target.is_symlink() or not target.resolve().is_relative_to(self.root):
            raise OPFError("prompt path escapes registry: {}".format(path))
        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise OPFError("cannot read prompt {}: {}".format(path, exc)) from exc

    def _migration_for(self, prompt_id: str) -> dict | None:
        if self.migration_manifest is None:
            return None
        return self.migration_manifest["migrations"].get(prompt_id)

    def _repo(self) -> tuple[Path, str]:
        repo = Path(_git(self.root, "rev-parse", "--show-toplevel").strip()).resolve()
        try:
            relative = self.path.relative_to(repo).as_posix()
        except ValueError as exc:
            raise OPFError("opf.yaml must be inside the Git repository") from exc
        return repo, relative

    def _release(self, prompt_id: str, version: str) -> dict:
        if not VERSION_RE.fullmatch(version):
            raise OPFError("version must be SemVer MAJOR.MINOR.PATCH")
        repo, config_rel = self._repo()
        tag = "opf/{}/v{}".format(prompt_id, version)
        ref = "refs/tags/" + tag
        if not _git(repo, "rev-parse", "-q", "--verify", ref, check=False).strip():
            raise OPFError("release tag does not exist: {}".format(tag))
        annotation = _git(repo, "for-each-ref", "--format=%(contents)", ref).strip()
        try:
            metadata = json.loads(annotation)
        except json.JSONDecodeError as exc:
            raise OPFError("release tag has invalid metadata: {}".format(tag)) from exc
        if metadata.get("schema") != "opf-release/1" or metadata.get("id") != prompt_id or metadata.get("version") != version or not _valid_digest(metadata.get("digest")):
            raise OPFError("release tag has mismatched metadata: {}".format(tag))
        tagged_config = _config(_git(repo, "show", "{}:{}".format(ref, config_rel)))
        if prompt_id not in tagged_config["prompts"]:
            raise OPFError("prompt {!r} is missing from release commit".format(prompt_id))
        definition = _definition(prompt_id, tagged_config["prompts"][prompt_id])
        prefix = Path(config_rel).parent.as_posix()
        prefix = "" if prefix == "." else prefix + "/"
        read_tagged = lambda path: _git(repo, "show", "{}:{}{}".format(ref, prefix, path))
        migration = None
        manifest_path = tagged_config.get("migration_manifest")
        if manifest_path:
            manifest = _migration_manifest(_yaml_mapping(read_tagged(manifest_path), "migration manifest"))
            migration = manifest["migrations"].get(prompt_id)
        bundle = _bundle(prompt_id, definition, read_tagged, migration)
        if bundle["digest"] != metadata["digest"]:
            raise OPFError("release tag digest mismatch: {}".format(tag))
        if definition["renderer"] == "opf":
            prompt = parse(bundle["files"][definition["source"]])
            if prompt.version is not None and prompt.version != version:
                raise OPFError("opf/0.1 frontmatter version differs from release version")
        bundle["version"] = version
        bundle["commit"] = _git(repo, "rev-parse", ref + "^{}").strip()
        return bundle

    def get(self, prompt_id: str, *, channel: str | None = None, version: str | None = None) -> RegisteredPrompt:
        if prompt_id not in self.config["prompts"]:
            raise OPFError("unknown registry prompt id {!r}".format(prompt_id))
        if channel and version:
            raise OPFError("choose either channel or version")
        if channel:
            pointer = self.config["prompts"][prompt_id].get("channels", {}).get(channel)
            if pointer is None:
                raise OPFError("unknown channel {!r} for {!r}".format(channel, prompt_id))
            version = pointer["version"]
        if version:
            bundle = self._release(prompt_id, version)
            if channel and bundle["digest"] != pointer["digest"]:
                raise OPFError("channel digest mismatch for {!r}".format(channel))
            return RegisteredPrompt(bundle, version=version, channel=channel)
        definition = _definition(prompt_id, self.config["prompts"][prompt_id])
        bundle = _bundle(prompt_id, definition, self._read_local, self._migration_for(prompt_id))
        return RegisteredPrompt(bundle)

    def verify_all(self) -> list[dict]:
        """Verify every configured channel against its annotated Git release."""
        verified = []
        for prompt_id, entry in self.config["prompts"].items():
            for channel in entry.get("channels", {}):
                prompt = self.get(prompt_id, channel=channel)
                verified.append({"id": prompt_id, "channel": channel, "version": prompt.version, "digest": prompt.bundle["digest"]})
        return verified

    def release(self, prompt_id: str, version: str) -> dict:
        if not VERSION_RE.fullmatch(version):
            raise OPFError("version must be SemVer MAJOR.MINOR.PATCH")
        prompt = self.get(prompt_id)
        if prompt.bundle["definition"]["renderer"] == "opf":
            source = prompt.bundle["definition"]["source"]
            file_version = parse(prompt.bundle["files"][source]).version
            if file_version is not None and file_version != version:
                raise OPFError("opf/0.1 frontmatter version differs from release version")
        repo, config_rel = self._repo()
        tag = "opf/{}/v{}".format(prompt_id, version)
        if _git(repo, "rev-parse", "-q", "--verify", "refs/tags/" + tag, check=False).strip():
            raise OPFError("release tag already exists: {}".format(tag))
        prefix = Path(config_rel).parent
        tracked_paths = [config_rel] + [(prefix / path).as_posix() for path in prompt.bundle["files"]]
        if self.config.get("migration_manifest"):
            tracked_paths.append((prefix / self.config["migration_manifest"]).as_posix())
        tracked_paths = list(dict.fromkeys(tracked_paths))
        if _git(repo, "status", "--porcelain", "--untracked-files=all", "--", *tracked_paths).strip():
            raise OPFError("commit opf.yaml and all prompt dependencies before release")
        _git(repo, "ls-files", "--error-unmatch", "--", *tracked_paths)
        committed_config = _config(_git(repo, "show", "HEAD:" + config_rel))
        committed_definition = _definition(prompt_id, committed_config["prompts"][prompt_id])
        read_committed = lambda path: _git(repo, "show", "HEAD:{}".format((prefix / path).as_posix()))
        committed_migration = None
        committed_manifest_path = committed_config.get("migration_manifest")
        if committed_manifest_path:
            committed_manifest = _migration_manifest(_yaml_mapping(read_committed(committed_manifest_path), "migration manifest"))
            committed_migration = committed_manifest["migrations"].get(prompt_id)
        committed_bundle = _bundle(prompt_id, committed_definition, read_committed, committed_migration)
        if committed_bundle["digest"] != prompt.bundle["digest"]:
            raise OPFError("committed prompt differs from the working tree")
        metadata = {"schema": "opf-release/1", "id": prompt_id, "version": version, "digest": prompt.bundle["digest"]}
        _git(repo, "tag", "-a", tag, "-m", _canonical(metadata).decode("utf-8"), "HEAD")
        return metadata

    def promote(self, prompt_id: str, version: str, channel: str) -> dict:
        if not ID_RE.fullmatch(channel):
            raise OPFError("invalid channel name")
        repo, config_rel = self._repo()
        if _git(repo, "status", "--porcelain", "--", config_rel).strip():
            raise OPFError("commit opf.yaml before promoting a release")
        bundle = self._release(prompt_id, version)
        if prompt_id not in self.config["prompts"]:
            raise OPFError("unknown registry prompt id {!r}".format(prompt_id))
        pointer = {"version": version, "digest": bundle["digest"]}
        self.config["prompts"][prompt_id].setdefault("channels", {})[channel] = pointer
        serialized = yaml.safe_dump(self.config, allow_unicode=True, sort_keys=False)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        os.replace(temporary, self.path)
        return pointer

    def export(self, prompt_id: str, version: str, output: str | Path) -> dict:
        bundle = self._release(prompt_id, version)
        Path(output).write_bytes(_canonical(bundle) + b"\n")
        return bundle
