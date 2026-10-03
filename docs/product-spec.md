# OPF Product Specification

**Status:** Draft for review  
**Date:** 2026-10-02  
**Purpose:** Define the product direction for Open Prompt Format and the boundaries between its format, validation, migration, versioning, and adapter capabilities.

## 1. Product intent

OPF is an open, repository-first format and toolchain for describing, checking, migrating, versioning, and exporting prompts used by LLM applications.

The format is a first-class product component. It provides a durable, documented representation that tools can validate and transform. The surrounding tools make OPF useful in existing projects without requiring an immediate migration. An implementation must be honest about what it preserves when converting between OPF and framework-specific representations.

### Intended users

- Developers maintaining prompts in application code, Markdown, Jinja, JSON, YAML, or framework configuration.
- Teams that want prompt changes reviewed and versioned with their source code.
- Teams migrating from vendor-managed prompt objects or framework-specific prompt formats.
- Tool authors who need a documented interchange representation and conformance suite.

### User outcome

A developer can discover prompts in a repository, understand their behavior and dependencies, validate them before model calls, migrate supported sources to OPF with an explicit compatibility report, and reproduce the exact prompt bundle used by an application.

## 2. Product principles

1. **OPF is canonical, not merely an export target.** Its syntax, semantics, versioning policy, schemas, and conformance fixtures are independently specified.
2. **Portable core, explicit extensions.** Common prompt behavior belongs in the core. Vendor- or framework-specific behavior may be represented in namespaced extensions, with defined preservation rules.
3. **No silent semantic loss.** Migration and adapters report unsupported, approximated, and preserved capabilities before writing or publishing.
4. **Useful before migration.** Discovery and validation should help teams understand supported legacy prompts without first rewriting them as OPF.
5. **Source provenance is retained.** Converted artifacts record their source kind, source location, converter version, and relevant source digest where available.
6. **Reproducible behavior.** A release identifies all source files and settings that affect the rendered prompt, not just the primary file.
7. **Integrate before reimplementing.** Evaluation and provider execution should compose with established tools such as Promptfoo and existing SDKs where practical.
8. **Compatibility claims are tested.** Python and TypeScript implementations share fixtures for every behavior claimed to be portable.

## 3. Product components

### 3.1 OPF format

OPF defines a versioned prompt artifact with:

- stable identity and descriptive metadata;
- ordered messages and roles;
- declared input variables and rendering behavior;
- a portable core for common prompt structures;
- namespaced extensions for optional capabilities;
- deterministic source and bundle identity;
- explicit rules for how consumers handle unknown or unsupported capabilities.

Existing `opf/0.1` and `opf/0.2` artifacts remain readable. Any new semantic capability requires a new format version or a separately versioned extension contract. Format evolution must define compatibility, migration guidance, and shared conformance fixtures before implementation claims support.

### 3.2 Validator and renderer

The validator has two scopes:

- **OPF validation:** schema, syntax, semantic constraints, inputs, rendering, dependencies, extension declarations, and bundle integrity.
- **Source inspection:** recognized source formats can be checked in place for discoverable issues such as missing template inputs, malformed templates, or unresolved dependencies. Source inspection must distinguish definitive errors from heuristic findings.

The renderer exposes the exact ordered messages and supported structured capabilities consumed by an adapter. Validation and rendering must not make network calls or incur model charges.

### 3.3 Repository discovery

The scanner identifies likely prompt assets in supported file types and known framework configurations. Every finding includes a path, detected source type, confidence, and reason. Discovery is read-only by default and must avoid rewriting source files.

The scanner may report unsupported or uncertain content, but must not label heuristic detections as validated prompts. Exclusion paths and generated/vendor directories must be configurable.

### 3.4 Migration engine

Migration is a staged operation:

1. inspect candidate assets;
2. produce a migration plan and compatibility report;
3. apply only after an explicit user command;
4. validate and render the generated OPF;
5. compare source and target output on supplied or generated representative inputs when feasible.

Migration must not delete, overwrite, or silently mutate source assets. Generated files retain provenance metadata or a sidecar manifest. Applying a migration is repeatable: running it again without source changes must not create duplicates or drift.

Compatibility outcomes use at least these categories:

- **preserved:** behavior maps directly;
- **preserved with warning:** behavior is retained through a documented extension or constrained mapping;
- **manual action required:** output is generated only where safe, with unresolved items clearly listed;
- **unsupported:** no conversion is claimed.

The report names each feature that is dropped, approximated, or left unresolved. A strict mode can fail when any non-preserved behavior remains.

### 3.5 Versioning and registry

The existing local Git registry, immutable releases, channels, digest verification, portable export, receipts, and Langfuse publication remain part of the product direction.

The release identity must cover the main artifact, statically resolvable included files, rendering-affecting configuration, and extension payloads. Dynamic dependencies require explicit declaration or cause strict release verification to fail. The registry and adapters must preserve the OPF release identity and bundle digest across export and publication.

Version semantics must distinguish:

- format version (parser contract);
- prompt release version (user-managed SemVer);
- converter/adapter version (transformation implementation);
- source and bundle digests (content identity).

### 3.6 Adapters

Adapters transform between OPF and a named source, SDK, framework, or registry. Each adapter documents:

- supported source and target versions;
- capability mapping and unsupported features;
- import/export direction;
- whether the mapping is lossless;
- rendering equivalence checks available;
- provenance and digest handling.

Adapters must use a shared capability report model. They must not silently invent defaults for model settings, roles, tools, output schemas, or template behavior. Runtime integrations are optional and separate from import/export support.

Initial adapter candidates:

- existing Markdown and Jinja files;
- OpenAI reusable prompt objects and their migration to code-managed prompts;
- LangChain `PromptTemplate` and `ChatPromptTemplate`;
- CrewAI prompt templates and prompt-file overrides;
- AutoGen `system_message` and explicit message configurations;
- existing Langfuse publication/read integration and later MLflow integration.

This list is a research-backed candidate set, not a promise that all adapters are in the first release.

### 3.7 Evaluation integration

OPF provides integration points for evaluation tools rather than defining a competing evaluation platform. Promptfoo remains the first example integration. Eval datasets, assertions, model credentials, and run results stay with the selected evaluation system unless a later specification establishes a concrete need to standardize them.

## 4. Initial delivery scope

The first product release built under this direction should deliver a coherent narrow workflow rather than every candidate adapter:

1. A reviewed format contract for the portable core, extension namespace rules, and compatibility behavior.
2. Python and TypeScript conformance for that contract using shared fixtures.
3. OPF validation and deterministic preview of the exact rendered output.
4. Read-only repository scan for the first supported sources.
5. Migration inspect/apply for selected sources, initially plain Markdown/Jinja and OpenAI reusable prompt exports, with provenance and loss reports.
6. Render-equivalence checks for supported mappings.
7. Release/export integration that pins migrated prompt bundles to Git and digest identities.
8. At least one framework adapter selected from LangChain, CrewAI, or AutoGen after a representative fixture and user workflow have been gathered.
9. Documentation and a runnable example that takes a user from an existing prompt to a validated OPF release.

The initial adapter matrix and v0.3 extension additions are recorded in the decision log below and specified in `spec/SYNTAX-0.3.md`. Both remain experimental until user validation.

## 5. Out of scope for the initial release

- Replacing Langfuse, LangSmith, MLflow, Promptfoo, or provider SDKs.
- A hosted prompt registry or web editor.
- Full conversion of agent orchestration, tools, memory, control flow, and runtime state into OPF.
- Guaranteeing semantic equivalence across arbitrary Jinja, Python, JavaScript, or framework execution.
- Automatically executing migrated prompts against paid model APIs.
- Broad support for every prompt format or framework before conformance fixtures exist.
- Requiring all OPF consumers to understand every vendor extension.

## 6. Quality and safety requirements

- Network-free validation, scanning, migration preview, and local rendering by default.
- No API keys or prompt contents sent to external services by local commands unless the user explicitly runs a publication or evaluation action.
- No silent file deletion or overwrite during migration.
- Clear errors with source path and location when available.
- Deterministic conversion for identical source, options, and tool versions.
- Explicit trust boundary: templates are executable configuration; untrusted templates must not be rendered in unrestricted engines.
- Avoid logging input values or rendered prompt contents by default; receipts retain identifiers and digests unless content logging is explicitly enabled.

## 7. Success measures

### Product validation

- At least five independent developers try the discovery and migration workflow on real repositories.
- At least three users successfully migrate a real prompt without hand-editing generated files to repair silent behavior changes.
- At least three users keep OPF validation or render-diff checks enabled in CI after the trial.
- Interviewed users can explain the difference between the portable core and framework extensions without coaching.

### Engineering acceptance

- Python and TypeScript pass the same core format and rendering fixtures.
- Every advertised import/export mapping has fixtures for supported features and known losses.
- Migration is idempotent and preserves sources.
- Released bundle digests change whenever a render-affecting dependency changes.
- The quick start completes from a clean checkout without undocumented steps or paid API credentials.

These are validation targets, not claims about current adoption.

## 8. Open decisions for specification review

1. Which format capabilities belong in the next OPF version versus namespaced extensions?
2. How should extensions preserve opaque vendor payloads while remaining safe for unknown consumers?
3. Migration provenance lives in an optional registry sidecar manifest (`opf-migration-manifest/1`); it is not core prompt frontmatter in v0.3.
4. Initial adapter scope is the local offline set: Markdown, constrained Jinja, OPF-defined OpenAI snapshot JSON, static serialized LangChain prompts, static CrewAI templates, and literal AutoGen system messages. This is an experimental implementation scope, not evidence that these are the highest-demand integrations; prioritize future adapters using user migration reports.
5. What is the exact policy for comparing rendered behavior when source and target templating engines differ?
6. Should the public name and package namespace remain Open Prompt Format / `opf` before publishing stable packages?

## 9. Relationship to existing repository documents

- `spec/SYNTAX.md` remains the current `opf/0.1` proposal.
- `spec/frontmatter-0.2.schema.json` and `spec/REGISTRY.md` describe current experimental `opf/0.2` and registry behavior.
- `docs/registry-rfc.md` and `docs/versioning-rfc.md` remain implementation/design references for the local registry and release model.
- This product specification sets the direction; it does not silently change the normative behavior of existing OPF versions.
- Once approved, format-specific requirements should be written into versioned normative spec files before implementation planning.
