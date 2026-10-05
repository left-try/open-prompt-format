# OPF GitHub Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an application repository add an OPF pull request check with one small generated workflow and no model credentials.

**Architecture:** Use a reusable GitHub workflow in the OPF repository for the no-secret gate; consumers call it from a generated workflow. Extend the existing Python `opf init` command to create that caller file safely. Keep the commands visible and runnable locally.

**Tech Stack:** Python 3.10+, existing `opf` CLI, GitHub Actions reusable workflows, PyYAML, Git.

**Spec:** `docs/superpowers/specs/2026-10-04-opf-adoption-workflow-design.md`

## Global Constraints

- Structural checks and release verification run without model API keys.
- Prompt source and release identity stay in Git; Langfuse publication is an explicit deployment step.
- Existing files are never overwritten silently; generated workflow paths are collision-checked before any writes.
- Reusable workflow/runtime versions are pinned; no generated workflow depends on unpublished source code.
- No raw prompt inputs, rendered prompt contents, secrets, or model outputs are emitted to the workflow summary.
- Eval remains disabled by default; this plan delivers only the no-secret check job.

## Review Focus

- Existing `.github/workflows/opf.yml`: initialization refuses to overwrite it and writes nothing else.
- Existing registry with an unrelated or malformed prompts mapping: initialization leaves it unchanged and reports the conflict.
- Repeated initialization with the OPF-generated workflow: produces no duplicate workflow or AGENTS block.
- Missing registry, no configured channels, and a registry with channels: workflow succeeds or fails according to the actual check contract, without inventing release pointers.
- Pull requests from forks: the no-secret workflow requests read-only repository permission and has no provider secrets.

---

## File Map

- `.github/workflows/opf-check.yml`: reusable no-secret workflow called by consumer repositories.
- `packages/python/src/opf/init.py`: render and preflight the generated caller workflow alongside existing starter files.
- `packages/python/src/opf/cli.py`: expose `opf init --github` and pass it to `initialize`.
- `packages/python/tests/test_init.py`: workflow creation, collision, repeatability, and atomic preflight tests.
- `packages/python/tests/test_cli.py`: command-line flag and JSON result coverage if a dedicated CLI test file exists; otherwise extend the existing CLI coverage file.
- `README.md`, `packages/python/README.md`, `docs/production-readiness.md`: local commands, generated workflow, version pin, and release gate.
- `.github/workflows/ci.yml`: validate the reusable workflow contract and generated fixture behavior in project CI.

## Interfaces

`initialize` gains `install_github_workflow: bool = False`. `InitResult.created` includes `.github/workflows/opf.yml` only when that file is newly created. `opf init --github` sets the option; existing invocations retain current behavior.

The reusable workflow `.github/workflows/opf-check.yml` exposes `workflow_call` inputs:

- `project-path`: string, default `.`
- `registry`: string, default `opf.yaml`
- `opf-version`: string, required by the caller file, pinned to a released OPF version

It checks out full Git history, installs the requested released Python package, runs `opf check` and `opf verify-all`, and writes a sanitized result summary to `$GITHUB_STEP_SUMMARY`. A missing registry skips registry verification; a malformed existing registry fails.

## Tasks

### Task 1: Specify and test the generated workflow contract

**Files:**
- Modify: `packages/python/tests/test_init.py`
- Test: `packages/python/tests/test_init.py`

- [ ] Add a failing test `test_init_github_creates_read_only_workflow_call` asserting generated workflow has `pull_request`, only `contents: read`, calls the OPF reusable workflow at a pinned release ref, and enables the no-secret check.
- [ ] Run `python -m unittest discover -s packages/python/tests -p 'test_init.py' -v` and confirm the new test fails because the option is not implemented.
- [ ] Add failing tests `test_init_github_refuses_existing_workflow_without_partial_writes` and `test_init_github_is_idempotent`; assert collision leaves prompt, registry, and AGENTS files untouched and repeated invocation reports no new workflow.
- [ ] Run `python -m unittest discover -s packages/python/tests -p 'test_init.py' -v` and confirm the new cases fail for the expected missing workflow behavior.

### Task 2: Render the caller workflow safely

**Files:**
- Modify: `packages/python/src/opf/init.py`
- Modify: `packages/python/tests/test_init.py`

**Interfaces:** Consumes the tests from Task 1. Produces `initialize(..., install_github_workflow: bool = False) -> InitResult`.

- [ ] Implement workflow content generation for `.github/workflows/opf.yml`; pin the reusable workflow reference to the published immutable OPF release selected for the initial launch, and pin `opf-version` to its matching Python package version.
- [ ] Add the generated workflow to the existing all-path preflight list, reject symlinks and conflicting contents, and create no directories/files until all outputs pass preflight.
- [ ] Make a second identical init a no-op for the workflow and ensure `InitResult.created` lists only paths written during that invocation.
- [ ] Run `python -m unittest discover -s packages/python/tests -p 'test_init.py' -v` and confirm all init tests pass.

### Task 3: Expose the opt-in CLI switch

**Files:**
- Modify: `packages/python/src/opf/cli.py`
- Modify: `packages/python/tests/test_cli.py` or the repository's existing CLI test file

**Interfaces:** `opf init [PATH] --github` maps to `initialize(path, install_github_workflow=True)`.

- [ ] Add a failing CLI test proving `opf init <temp-dir> --github` creates the caller workflow and includes it in JSON output.
- [ ] Run the focused CLI test and confirm it fails on the unrecognized flag.
- [ ] Add `--github` as a `store_true` option and pass it to `initialize` without changing behavior of existing CLI flags.
- [ ] Run the focused CLI test and `python -m unittest discover -s packages/python/tests -v`.

### Task 4: Add the reusable no-secret workflow

**Files:**
- Create: `.github/workflows/opf-check.yml`
- Modify: `.github/workflows/ci.yml`
- Create: `packages/python/tests/fixtures/opf-init-workflow.yml` only if a stable checked-in fixture improves review; otherwise assert parsed YAML in `test_init.py`.

- [ ] Add a workflow-call contract test that parses the YAML and asserts required inputs, read-only contents permission, full-history checkout, pinned Python version, CLI installation by exact package version, and calls to `opf check` and `opf verify-all`.
- [ ] Run that test and confirm it fails because `.github/workflows/opf-check.yml` does not exist.
- [ ] Implement the reusable workflow. Skip `verify-all` only when the configured registry file is absent; let validation errors from a present registry fail the job. Do not request write permissions or read provider secrets.
- [ ] Add a sanitized job summary with pass/fail statuses and the registry path. Never print prompt bodies or inputs.
- [ ] Add CI coverage for the workflow contract and run the focused tests, Python suite, `opf check .`, and `opf verify-all --registry opf.yaml`.

### Task 5: Document setup and release prerequisites

**Files:**
- Modify: `README.md`
- Modify: `packages/python/README.md`
- Modify: `docs/production-readiness.md`

- [ ] Document the two commands for a new consumer (`pip install` the released package, then `opf init --github`) and show the generated files and local equivalents.
- [ ] Explain the no-secret default, required read-only permissions, pinned reusable workflow/package versions, and how maintainers update those versions deliberately.
- [ ] Add a release checklist requiring the reusable workflow ref and Python package version to exist and correspond before the generated path is advertised as production-ready.
- [ ] Run Markdown link checks if the repository already has them; otherwise review every added link and command against current CLI help and paths.

## Acceptance

- `opf init --github` creates a runnable pinned caller workflow on a clean repository and refuses conflicts without partial writes.
- The called workflow runs `opf check` and verifies configured releases without credentials or write permissions.
- The package and workflow release are both published before generated setup is described as ready for outside users.
- Existing `opf init` and Git release behavior remain unchanged.
