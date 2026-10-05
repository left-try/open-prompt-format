"""Prepare identical Promptfoo configs against base and candidate prompt files."""

from __future__ import annotations

import argparse
import subprocess
import tarfile
import io
import json
import tempfile
from pathlib import Path

import yaml


def prepare_pair(
    base_ref: str,
    prompt_file: str,
    config_path: str,
    output_dir: str,
    adapter_path: str | None = None,
    repo_root: str = ".",
    project_path: str = ".",
) -> tuple[Path, Path]:
    prompt = Path(prompt_file)
    if prompt.is_absolute() or ".." in prompt.parts or not prompt.parts:
        raise ValueError("prompt-file must be a repository-relative path without parent traversal")
    config_relative = Path(config_path)
    if config_relative.is_absolute() or ".." in config_relative.parts or not config_relative.parts:
        raise ValueError("eval-config must be a repository-relative path without parent traversal")
    project_relative = Path(project_path)
    if project_relative.is_absolute() or ".." in project_relative.parts:
        raise ValueError("project-path must stay inside the caller repository")
    repository = Path(repo_root).resolve()
    project_root = (repository / project_relative).resolve()
    try:
        project_root.relative_to(repository)
    except ValueError as exc:
        raise ValueError("project-path must stay inside the caller repository") from exc
    prompt = project_root / prompt
    config = project_root / config_relative
    if not config.is_file():
        raise ValueError("eval config does not exist")
    if not prompt.is_file():
        raise ValueError("candidate prompt file does not exist")
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", base_ref + "^{commit}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=repository,
        ).stdout.strip()
        git_prompt_path = (project_relative / Path(prompt_file)).as_posix()
        archive = subprocess.run(
            ["git", "archive", "--format=tar", revision, "--", git_prompt_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=repository,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            entry = tar.extractfile(git_prompt_path)
            if entry is None:
                raise ValueError("base prompt file is missing or base-ref is invalid")
            baseline = entry.read()
    except subprocess.CalledProcessError as exc:
        raise ValueError("base prompt file is missing or base-ref is invalid") from exc

    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    baseline_path = destination / "baseline-prompt.md"
    candidate_path = destination / "candidate-prompt.md"
    baseline_path.write_bytes(baseline)
    candidate_path.write_bytes(prompt.read_bytes())

    settings = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError("eval config must be a YAML mapping")
    env = settings.setdefault("env", {})
    if not isinstance(env, dict):
        raise ValueError("eval config env must be a mapping")
    if adapter_path:
        settings["prompts"] = [Path(adapter_path).resolve().as_uri()]
    baseline_config = dict(settings)
    candidate_config = dict(settings)
    baseline_config["env"] = {**env, "OPF_PROMPT_FILE": str(baseline_path.resolve())}
    candidate_config["env"] = {**env, "OPF_PROMPT_FILE": str(candidate_path.resolve())}
    # Keep config copies beside the caller's config so its relative vars/providers/functions
    # keep resolving from the same directory when Promptfoo loads them.
    config_directory = config.resolve().parent
    baseline_config_path = _write_temporary_config(config_directory, ".opf-baseline-", baseline_config)
    candidate_config_path = _write_temporary_config(config_directory, ".opf-candidate-", candidate_config)
    return baseline_config_path, candidate_config_path


def _write_temporary_config(directory: Path, prefix: str, settings: dict) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=prefix, suffix=".yaml", dir=directory, delete=False
    )
    path = Path(handle.name)
    try:
        with handle:
            yaml.safe_dump(settings, handle, sort_keys=False)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--adapter-path")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--project-path", default=".")
    args = parser.parse_args()
    try:
        baseline, candidate = prepare_pair(
            args.base_ref, args.prompt_file, args.config, args.output_dir, args.adapter_path,
            repo_root=args.repo_root, project_path=args.project_path,
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    print(json.dumps({"baseline_config": str(baseline), "candidate_config": str(candidate)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
