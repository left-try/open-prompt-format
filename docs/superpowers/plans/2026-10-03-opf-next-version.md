# OPF Next Version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a practical OPF onboarding and local quality workflow with safe initialization, static validation, release comparison, cacheability evidence, and prompt-injection advisories.

**Architecture:** Keep the `opf` CLI in the Python package and build these workflows as local, deterministic operations around the existing parser and Git registry. Reuse shared parsing/conformance contracts where behavior is portable; do not change current bundle identity. Keep user-agent integration outside init: update only an OPF-owned block in `AGENTS.md`.

**Tech Stack:** Python 3.10+, PyYAML, existing Python CLI and Git registry; TypeScript package and shared fixtures only for any new portable prompt semantics; Markdown/YAML documentation.

**Spec:** `docs/superpowers/specs/2026-10-03-opf-next-version-design.md`

## Global Constraints

- Existing OPF 0.1/0.2/0.3 interpretation, Python/TypeScript parity, and bundle digests remain compatible.
- `init`, checks, diff, and static analysis make no network calls.
- Existing files and `AGENTS.md` text outside OPF-owned markers are preserved.
- Local cache-prefix comparison is never reported as a provider cache hit.
- Prompt-injection analysis is best-effort and never represented as a security guarantee.
- Do not add raw prompt inputs, rendered content, secrets, or model outputs to receipts or reports by default.
- Defer the `okf-aget` integration until its workflow and interface are inspected.

## Review Focus

- Existing `AGENTS.md` with no markers, complete markers, partial markers, and repeated markers; preserve unrelated bytes and fail safely on ambiguity.
- Existing prompt/config destinations during repeated and non-interactive init; never overwrite silently.
- CRLF, bare CR, Unicode, fenced examples, escaped interpolation, and Markdown role headings in checks and comparisons.
- Dynamic Jinja, static dependencies, missing variables, and working-tree targets; report unknown comparison behavior rather than infer a shared prefix.
- User-controlled input containing template delimiters, role-like text, and common injection phrases; do not re-parse substituted input as template or claim complete detection.

## File Map

- `packages/python/src/opf/init.py`: starter project/prompt generation and marker-managed `AGENTS.md` update.
- `packages/python/src/opf/check.py`: aggregate deterministic validation and safety findings.
- `packages/python/src/opf/diff.py`: release/source comparison and stable-prefix evidence.
- `packages/python/src/opf/cli.py`: `init`, `check`, and `diff` argument parsing, output, and exit codes.
- `packages/python/src/opf/core.py`: only if input-trust metadata is approved as a core semantic; preserve existing rendering contract.
- `packages/typescript/src/index.ts`, `spec/frontmatter-0.3.schema.json`, `fixtures/conformance.json`: update only if shared trust metadata is introduced.
- `packages/python/tests/`, `packages/typescript/test/`: regression and conformance coverage for new behavior.
- `README.md`, `packages/python/README.md`, `packages/typescript/README.md`, `docs/production-readiness.md`, `PLAN.md`: onboarding, workflow, and maturity claims.

## Implementation Tasks

### Task 1: Define command contracts and finding format

**Files:**
- Create: `packages/python/src/opf/check.py`
- Create: `packages/python/tests/test_check.py`
- Modify: `packages/python/src/opf/cli.py`

- [ ] Define a serializable finding with stable `code`, `severity`, `message`, optional `path`, and optional line/column.
- [ ] Implement `check(root, registry_path=None, safety=True) -> list[Finding]` using existing file loaders, registry validation, and collection validation.
- [ ] Add `opf check [PATH] [--registry PATH] [--format text|json] [--strict] [--no-safety]`; default discovery excludes generated/dependency directories and validates registered OPF prompts plus likely unregistered OPF files.
- [ ] Return nonzero for errors; in strict mode also return nonzero for warning findings. Keep ordinary safety heuristics advisory by default.
- [ ] Cover invalid frontmatter, duplicate IDs, unresolved registry paths, undeclared/missing inputs, deterministic JSON shape, and exit-code policy.

### Task 2: Implement safe, repeatable initialization

**Files:**
- Create: `packages/python/src/opf/init.py`
- Create: `packages/python/tests/test_init.py`
- Modify: `packages/python/src/opf/cli.py`
- Modify: `packages/python/README.md`

- [ ] Define `initialize(root, prompt_id, prompt_path, update_agents, force=False) -> InitResult` with a dry planning phase and explicit writes only after collision checks.
- [ ] Add `opf init [PATH] [--id ID] [--prompt PATH] [--agents auto|yes|no]`; non-interactive behavior is deterministic and does not prompt.
- [ ] Generate a valid minimal OPF prompt and registry only when destinations do not exist; never overwrite existing files by default.
- [ ] Manage only a unique `<!-- opf:begin -->` / `<!-- opf:end -->` section in `AGENTS.md`; append when markers are absent, update inside one valid block, and refuse incomplete/duplicate markers without writing.
- [ ] Ensure repeated init produces no duplicate block and preserve all bytes outside the managed block.
- [ ] Cover empty repository, existing unrelated agent guidance, repeat invocation, file collision, invalid ID/path, and malformed markers.

### Task 3: Add prompt-injection and trust-boundary advisories

**Files:**
- Create: `packages/python/src/opf/safety.py`
- Create: `packages/python/tests/test_safety.py`
- Modify: `packages/python/src/opf/check.py`
- Modify: `README.md`
- Modify: `docs/production-readiness.md`

- [ ] Define versioned heuristic rules with stable finding codes, advisory severity, and source locations.
- [ ] Detect a deliberately small set of review-worthy patterns (for example, instructions to ignore prior instructions, attempts to reveal hidden system/developer prompts, and tool-use directives embedded in prompt content); document false-positive limits.
- [ ] Detect prompts interpolating declared external/user input without an explicit boundary cue and recommend treating values as untrusted data.
- [ ] Ensure render-time input values remain literal strings and are never recursively interpreted as templates.
- [ ] Include clear guidance that delimiters and wording do not enforce security; application authorization, tool controls, and output checks remain necessary.
- [ ] Cover positive and negative examples, source locations, JSON/text parity, and proof that runtime input is not scanned as executable OPF syntax.

### Task 4: Compare releases and calculate cache-prefix evidence

**Files:**
- Create: `packages/python/src/opf/diff.py`
- Create: `packages/python/tests/test_diff.py`
- Modify: `packages/python/src/opf/registry.py` only to expose existing pinned source/dependency data through a read-only helper if needed.
- Modify: `packages/python/src/opf/cli.py`

- [ ] Define `compare(prompt_id, base, target, registry_path) -> DiffReport`; resolve base releases/channels from Git and target as an exact release or working tree.
- [ ] Compare normalized source, registry definition, declared inputs, message roles/content, and static dependencies without changing existing digest schemas.
- [ ] Report the longest identical leading static message sequence and the message-level common prefix where exact comparison is possible; variable-dependent or dynamic Jinja prefixes must be marked unknown/conditional.
- [ ] Use language such as `stable_prefix_candidate` or `cacheability_evidence`; never emit `cache_hit` or equivalent.
- [ ] Add `opf diff ID --base VERSION_OR_CHANNEL --target VERSION_OR_WORKTREE [--registry PATH] [--format text|json]`.
- [ ] Cover unchanged content, changed system prefix, user-only change, CRLF normalization, dependency changes, unknown Jinja behavior, missing release, and JSON determinism.

### Task 5: Decide and, if justified, add portable input trust metadata

**Files:**
- Modify: `spec/SYNTAX-0.3.md`
- Modify: `spec/frontmatter-0.3.schema.json`
- Modify: `packages/python/src/opf/core.py`
- Modify: `packages/typescript/src/index.ts`
- Modify: `fixtures/conformance.json`
- Modify: Python and TypeScript conformance tests.

- [ ] First decide from Tasks 1 and 3 whether convention-based linting is sufficient; do not add schema surface without a concrete validator/runtime use.
- [ ] If needed, specify an optional `trust` label with a finite allowed set and define its exact semantics as descriptive metadata, not a sanitization guarantee.
- [ ] Keep old versions unchanged and keep interpolation/rendered `{role, content}` output unchanged.
- [ ] Add shared valid/invalid fixtures and assert Python/TypeScript metadata parity.
- [ ] If not justified, document the convention in generated `AGENTS.md` and skip schema/runtime changes.

### Task 6: Documentation, CLI help, and release status

**Files:**
- Modify: `README.md`
- Modify: `packages/python/README.md`
- Modify: `packages/typescript/README.md`
- Modify: `docs/production-readiness.md`
- Modify: `PLAN.md`
- Modify: `site/index.html` if it mirrors the quick start.

- [ ] Document Python CLI installation separately from the TypeScript library installation.
- [ ] Document init, generated AGENTS block, check modes, stable finding codes, diff targets, and cacheability limits.
- [ ] Document injection advisory limits and application-level responsibilities without promising immunity.
- [ ] Mark `okf-aget` and usage mapping as follow-up work pending interface discovery.
- [ ] Update project maturity claims only to reflect implemented and independently verified behavior.

## Execution Order

Tasks 1–2 provide the onboarding/validation foundation. Task 3 plugs into the check finding contract from Task 1. Task 4 uses the existing registry contract but remains independent of safety heuristics. Task 5 is gated on evidence from the actual implementation; preserve convention-only metadata if that is sufficient. Task 6 follows completed behavior.

## Acceptance Criteria

- `opf init` is safe on existing repositories, repeatable, and creates output that passes the local check.
- `opf check` is deterministic, offline, machine-readable, and suitable for CI.
- Safety findings are advisory by default and never claim complete prompt-injection prevention.
- `opf diff` compares releases and working trees, reports stable-prefix evidence when it can prove it, and clearly reports unknown cases.
- No cache-hit claim is made without provider runtime evidence.
- Existing releases, bundle verification, and Python/TypeScript prompt behavior remain compatible.
