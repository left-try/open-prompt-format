# OPF Product Toolchain Implementation Plan

> **For agentic workers:** Execute this plan task by task in the current workspace. Preserve all pre-existing working-tree changes. Do not publish packages or call paid model APIs.

**Goal:** Deliver a versioned OPF v0.3 contract and a practical local workflow to validate, discover, migrate, version, and adapt repository prompts without silent loss.

**Architecture:** Keep the existing parser, renderer, Git registry, and Langfuse path. Add v0.3 as an additive format version with structured namespaced extensions; build source discovery and migration around a shared compatibility report; preserve migration provenance in registry bundle data; and expose framework conversion through explicit import/export adapters. Python is the initial CLI/reference migration implementation; TypeScript maintains format and bundle parity.

**Tech Stack:** Python 3.10+, PyYAML, optional Jinja2; TypeScript/Node.js 22.6+, `yaml`; JSON Schema 2020-12; existing Git-backed `opf.yaml` registry.

**Spec:** `docs/product-spec.md`, `spec/SYNTAX-0.3.md`, `spec/REGISTRY.md`.

## Global Constraints

- `opf/0.1` and `opf/0.2` parsing and rendering behavior remain unchanged.
- `opf/0.3` keeps the v0.2 core message headings, string inputs, simple interpolation, and `{role, content}` output.
- Unknown extension records are preserved; required unknown extensions fail strict compatibility checks.
- Validation, scan, migration preview, and local rendering do not make network calls.
- Migration never deletes or overwrites source files; application is explicit and idempotent.
- Framework adapters do not claim to convert agent orchestration, memory, or control flow.
- Current uncommitted repository changes are user work; inspect diffs before editing shared files and preserve unrelated hunks.
- Do not publish packages or make paid provider calls.

## Review Focus

- Old v0.1/v0.2 sources retain their current interpretation when v0.3 support is added.
- Unknown extension payloads survive parse, registry release, export, and adapter round trips.
- Dynamic Jinja dependencies and missing variables produce a report instead of an incomplete migration.
- Generated paths cannot escape the repository or overwrite existing files.
- Provider/framework-only features are named in compatibility output and are never silently dropped.

## File Map

- `spec/frontmatter-0.3.schema.json`: machine-readable v0.3 metadata validation.
- `spec/SYNTAX-0.3.md`: normative format and extension rules.
- `spec/REGISTRY.md`: bundle/provenance schema and digest coverage.
- `packages/python/src/opf/core.py`, `packages/typescript/src/index.ts`: parsers, metadata models, and extension validation.
- `packages/python/src/opf/registry.py`, `packages/typescript/src/registry.ts`: provenance-aware bundles and digest verification.
- `packages/python/src/opf/compatibility.py`: shared finding/result data types and strict-mode behavior.
- `packages/python/src/opf/discovery.py`: read-only repository scan.
- `packages/python/src/opf/migrate.py`: source inspection, migration plans, and explicit apply.
- `packages/python/src/opf/adapters/`: import/export adapters for supported source formats.
- `packages/python/src/opf/cli.py`: `scan`, `migrate`, and `compat` commands.
- `packages/python/README.md`, `packages/typescript/README.md`, `README.md`, `site/index.html`: current examples and user workflow.
- `examples/migration/`: small reproducible legacy-to-OPF workflow.

## Implementation Tasks

### Task 1: Finalize the v0.3 and provenance contracts

**Files:**
- Modify: `spec/SYNTAX-0.3.md`
- Create: `spec/frontmatter-0.3.schema.json`
- Modify: `spec/REGISTRY.md`
- Modify: `docs/product-spec.md`

- [ ] Define exact validation constraints for extension reverse-DNS identifiers, string versions, boolean `required`, JSON-compatible `data`, and unknown fields.
- [ ] Define `opf-migration-manifest/1` with a `migrations` mapping keyed by generated prompt ID. Each record contains `source_path`, `source_kind`, optional `source_format_version`, `source_digest`, `converter`, `converter_version`, UTC `migrated_at`, and `findings`.
- [ ] Define each finding as `{code, severity, disposition, message, path?}`; allowed severity values are `info`, `warning`, `error`, and dispositions are `preserved`, `approximated`, `dropped`, `manual`.
- [ ] Specify that the manifest is included in the prompt bundle digest and exported bundle, while migration timestamps do not affect rendering.
- [ ] Add schema examples for core-only v0.3 and a vendor extension; keep v0.1/v0.2 schemas unchanged.

### Task 2: Add v0.3 parser and model parity

**Files:**
- Modify: `packages/python/src/opf/core.py`
- Modify: `packages/typescript/src/index.ts`
- Modify: `packages/python/src/opf/__init__.py`

- [ ] Extend the metadata type and format dispatch to accept `opf/0.3` while retaining current `0.1`/`0.2` branches.
- [ ] Validate extension identifiers against `^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$` and records against exactly `version`, `required`, and `data`.
- [ ] Recursively reject non-JSON-compatible extension values, non-finite numbers, non-string mapping keys, and YAML-specific tagged values.
- [ ] Preserve extensions in parsed prompts and expose them read-only through the Python and TypeScript public APIs.
- [ ] Add an API-level compatibility method with the same result shape in both SDKs: `compatibility({strict?: boolean, supportedExtensions?: Record<string, string[]>})` returning extension findings without modifying rendered core messages.

### Task 3: Make bundles extension- and provenance-aware

**Files:**
- Modify: `packages/python/src/opf/registry.py`
- Modify: `packages/typescript/src/registry.ts`
- Modify: `spec/REGISTRY.md`
- Modify: `opf.yaml` only if existing config schema needs a compatible optional manifest path.

- [ ] Define the optional registry key `migration_manifest`, a normalized path relative to `opf.yaml`; reject paths outside the registry root.
- [ ] Include the normalized manifest contents in `opf-bundle/2` digest payloads when present; continue validating and loading existing `opf-bundle/1` bundles without changing their digest rules.
- [ ] Include v0.3 extension payloads in release/export digest identity through the prompt source text and canonical parsed validation.
- [ ] Carry migration manifest data into exported bundles and render receipts as source metadata and source digest references, without including inputs or rendered content.
- [ ] Update Python and TypeScript local, Git-release, and bundle-load paths to preserve the same fields and canonical digest.

### Task 4: Introduce shared compatibility reporting

**Files:**
- Create: `packages/python/src/opf/compatibility.py`
- Modify: `packages/python/src/opf/core.py`
- Modify: `packages/python/src/opf/publish.py`
- Modify: `packages/python/src/opf/cli.py`

- [ ] Define `CompatibilityFinding` with `code`, `severity`, `disposition`, `message`, optional `source_path`, and optional `capability`.
- [ ] Define `CompatibilityReport` with source kind, target kind, findings, `lossless`, and `can_apply`.
- [ ] Implement strict mode: `can_apply` is false when any finding is `error`, `dropped`, or unresolved `manual`; warnings are allowed only when behavior is preserved.
- [ ] Make Langfuse dry-run emit the same report representation, mapping its existing unsupported-role/Jinja conditions into stable finding codes.
- [ ] Serialize reports to stable JSON and human-readable CLI output.

### Task 5: Add repository discovery

**Files:**
- Create: `packages/python/src/opf/discovery.py`
- Modify: `packages/python/src/opf/cli.py`
- Modify: `packages/python/README.md`

- [ ] Implement `scan(root, include, exclude) -> list[PromptFinding]` for `.opf.md`, `.md`, `.j2`, `.txt`, `.json`, `.yaml`, `.yml`, and known references in `opf.yaml`, Promptfoo config, LangChain YAML, CrewAI config, and OpenAI prompt export JSON.
- [ ] Each `PromptFinding` contains repository-relative `path`, `source_kind`, confidence (`high`, `medium`, `low`), and detection reason.
- [ ] Exclude `.git`, virtual environments, dependency directories, build outputs, and user-specified globs by default.
- [ ] Add `opf scan [PATH] --format text|json --include GLOB --exclude GLOB`; default behavior is read-only and does not parse unrelated source as a valid prompt.
- [ ] Ensure symlinks resolving outside the scan root are skipped and reported.

### Task 6: Add legacy source inspection and migration planning

**Files:**
- Create: `packages/python/src/opf/migrate.py`
- Create: `packages/python/src/opf/adapters/base.py`
- Modify: `packages/python/src/opf/cli.py`

- [ ] Define adapter interface `inspect(path) -> SourcePrompt`, `plan(source, prompt_id) -> MigrationPlan`, and `convert(source, plan) -> MigrationOutput`.
- [ ] `MigrationPlan` contains destination files, generated OPF text, input mapping, compatibility report, and source digest; planning has no filesystem writes.
- [ ] Implement `opf migrate inspect PATH [--id ID] [--strict] --format text|json` to show the plan and compatibility report.
- [ ] Implement `opf migrate apply PATH [--id ID] [--output-dir DIR] [--strict]` to write only into absent destination paths, create/update the registry and provenance manifest only when explicitly requested, and fail on collisions.
- [ ] Make repeat apply idempotent when source digest, converter version, and options are unchanged.
- [ ] For templates with dynamic includes or unknown functions, emit manual/unsupported findings and do not claim render equivalence.

### Task 7: Implement Markdown/Jinja import

**Files:**
- Create: `packages/python/src/opf/adapters/markdown.py`
- Create: `packages/python/src/opf/adapters/jinja.py`
- Modify: `packages/python/src/opf/registry.py`
- Modify: `packages/python/pyproject.toml`

- [ ] Import Markdown role headings directly when they follow OPF's message syntax; otherwise require explicit `--role` or message mapping.
- [ ] Inspect Jinja variables and static include/import/extends dependencies; preserve the original Jinja source through a registry `jinja2` definition when exact conversion to core interpolation is not possible.
- [ ] Convert a Jinja file to OPF core interpolation only when the discovered syntax is limited to declared string variables and output equivalence can be established without evaluation.
- [ ] Record all source files and accepted findings in the migration manifest.
- [ ] Keep Jinja dependency optional; provide a clear error when inspection/render requires the extra but it is absent.

### Task 8: Implement OpenAI reusable-prompt import/export

**Files:**
- Create: `packages/python/src/opf/adapters/openai.py`
- Modify: `packages/python/src/opf/cli.py`
- Modify: `docs/product-spec.md`
- Modify: `packages/python/README.md`

- [ ] Define the supported OpenAI prompt export JSON shape and reject unknown structural variants rather than guessing.
- [ ] Map text/chat messages and named variables into OPF core.
- [ ] Preserve supported OpenAI-only fields such as tools, output format, and model-call settings in a namespaced extension with `required: true` when execution depends on them.
- [ ] Implement import preview and export generation; export reports exactly which fields the target API representation can preserve.
- [ ] Do not make network calls or require credentials for conversion.

### Task 9: Add framework adapters in a prioritized sequence

**Files:**
- Create: `packages/python/src/opf/adapters/langchain.py`
- Create: `packages/python/src/opf/adapters/crewai.py`
- Create: `packages/python/src/opf/adapters/autogen.py`
- Modify: `packages/python/src/opf/adapters/__init__.py`

- [ ] LangChain: support `PromptTemplate` and `ChatPromptTemplate` with declared inputs; preserve template-engine-specific syntax in a `com.langchain.prompt` extension when not representable in the core.
- [ ] CrewAI: support user-authored `system_template`, `prompt_template`, and `custom_prompts.json` slices; do not convert framework-generated agent orchestration.
- [ ] AutoGen: support explicit `system_message` and ordered message configuration; do not convert agent runtime, tools, or control flow.
- [ ] Every adapter consumes and produces the shared compatibility report and refuses lossy apply in strict mode.
- [ ] Keep framework packages optional and avoid making them runtime dependencies of the OPF parser.

### Task 10: Wire migration provenance into release operations

**Files:**
- Modify: `packages/python/src/opf/registry.py`
- Modify: `packages/python/src/opf/cli.py`
- Modify: `packages/typescript/src/registry.ts`
- Modify: `spec/REGISTRY.md`

- [ ] Validate manifest references, prompt IDs, digests, timestamps, converter metadata, and finding enumerations.
- [ ] Include the manifest and its referenced source artifacts in release verification and exported bundle identity.
- [ ] Ensure channel promotion, remote publication, and render receipts preserve release digest and provenance references.
- [ ] Keep existing registries without migration manifests valid and byte-for-byte compatible with current bundle rules.

### Task 11: Document and demonstrate the workflow

**Files:**
- Create: `examples/migration/legacy_prompt.j2`
- Create: `examples/migration/README.md`
- Modify: `README.md`
- Modify: `packages/python/README.md`
- Modify: `packages/typescript/README.md`
- Modify: `site/index.html`
- Modify: `PLAN.md`

- [ ] Document the three-step `scan → migrate inspect → migrate apply` workflow with examples and report output.
- [ ] Document v0.3 extension handling, compatibility categories, and limits of equivalence claims.
- [ ] Update the landing page example to match the current syntax and offer the migration/validation use case as the primary quick start.
- [ ] Distinguish current implemented capabilities from planned adapters and experimental format behavior.
- [ ] Document installation from published package versus local clone without claiming publication before it occurs.

### Task 12: Prepare release and user validation

**Files:**
- Modify: `docs/production-readiness.md`
- Modify: `PUBLISHING.md`
- Modify: `.github/workflows/ci.yml` only if format/schema packaging needs adjustment.

- [ ] Record supported source/target matrix and known lossy cases.
- [ ] Record whether the existing CI commands cover v0.3 format and bundle compatibility; do not claim checks passed unless run and observed.
- [ ] Prepare a no-credentials example path for users to try locally.
- [ ] Gather feedback from at least five independent developers and track migration failures before calling the format stable.

## Execution order

Tasks 1–4 define and implement the versioned data contracts. Task 5 can proceed once the source-kind list is fixed. Tasks 6–9 implement the migration path and adapters. Task 10 integrates provenance with releases. Tasks 11–12 prepare adoption and stability review. Do not publish stable packages until independent users have exercised the workflow.
