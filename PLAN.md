# Implementation Plan

## Goal

Make a prompt stored in one repository file portable across Python and TypeScript applications, with a shared parse/render contract and a practical evaluation path through Promptfoo.

## Phase 0: settle the proposal

- [x] Choose one-file Markdown plus YAML frontmatter.
- [x] Define message section markers and roles.
- [x] Define input declarations and deliberately limited interpolation.
- [x] Define a provider-neutral rendered message array.
- [x] Define a derived source digest for content identity.
- [ ] Review syntax against more real prompts, including code samples and literal delimiter cases.
- [ ] Decide project name and whether the acronym is OPF or OPM before publishing packages.

**Deliverable:** reviewed v0.1 syntax document and examples.

## Phase 1: language-neutral conformance material

- [x] Define a JSON Schema for frontmatter metadata, with a documented YAML-to-JSON parsing boundary.
- [x] Create shared valid and invalid prompt fixtures for core parsing/rendering behavior.
- [x] Specify duplicate YAML keys as errors in both loaders.
- [ ] Expand the fixtures and define canonical error categories for every normative rule.
- [x] Normalize LF, CRLF, and bare CR consistently in the loaders.

The JSON Schema validates the parsed frontmatter object; YAML parsing and duplicate-key rejection happen before schema validation.

Shared fixtures cover normal rendering, an unquoted `on` tag under YAML 1.2 Core, fenced and escaped role headings, malformed templates, undeclared inputs, and duplicate YAML keys. More edge cases are still needed before a stable format release.

**Deliverable:** fixture corpus usable by both language implementations.

## Phase 2: Python reference library

- [x] Package a small library with file loading, collection lookup, and rendering APIs.
- [x] Validate frontmatter, collection-level unique IDs, message sections, template declarations, and render inputs.
- [x] Provide a CLI for `validate`, `validate-collection`, and `render`.
- [x] Keep the runtime dependency surface small and document deterministic behavior.

The Python wheel builds successfully; all six unit checks pass.

**Deliverable:** installable library and CLI for local repository prompts.

## Phase 3: TypeScript implementation

- [x] Implement the same public concepts and behavior as the Python library.
- [x] Add a shared fixture-driven TypeScript test suite.
- [x] Run both implementations against the same fixtures and expected outputs.
- [x] Document exact parity limits and errors in the syntax spec.

The TypeScript build and all five fixture-driven checks pass. Python and TypeScript produce the same source digest for the example prompt.

**Deliverable:** TypeScript package with demonstrated conformance to the shared fixtures.

## Phase 4: Promptfoo evaluation integration

- [x] Add a small dynamic-prompt adapter that renders the repo file through the TypeScript loader.
- [x] Keep provider IDs, test cases, assertions, and eval settings in Promptfoo's own configuration.
- [x] Ensure prompt content stays in the OPF file; avoid a second hand-maintained prompt copy.
- [x] Configure an example eval against two providers.
- [ ] Run an eval when provider credentials are configured.

Promptfoo supports repo-local text and JSON chat prompts, but it does not natively define this frontmatter format. The adapter was exercised directly and the YAML config parses. The actual model evaluation is still pending API credentials and an explicit run because it sends paid external requests.

**Deliverable:** reproducible eval example using the same checked-in OPF source.

## Phase 5: provider adapters

- Start with providers needed by example consumers.
- Translate the common `role`/`content` messages and report unsupported roles or message features.
- Keep provider-specific model parameters outside the portable prompt core.
- Add provider-specific fields only through explicit, namespaced extensions with clear fallback behavior.

**Deliverable:** documented provider mappings and clear unsupported-feature errors.

## Phase 6: registry drivers and release workflow

- Define an optional driver interface for publishing/fetching prompt artifacts.
- Keep Git as the canonical source for repo-first use; registry support is optional.
- Preserve prompt ID, version, and content digest when publishing and fetching.
- Add integrations only after a target registry and user need are identified.

**Deliverable:** one optional registry driver, with round-trip behavior documented.

## Phase 7: community validation

- Publish the syntax proposal and example repository.
- Invite feedback from prompt tooling maintainers and teams using multiple providers.
- Revise based on working implementations, not hypothetical completeness.
- Only call the format stable after independent implementation experience.

**Deliverable:** an implementation-backed specification with compatibility policy.

## Acceptance criteria for the first usable release

- [x] One Markdown file contains metadata, inputs, and all messages.
- [x] Python and TypeScript produce equivalent ordered role/content messages from it.
- [x] Invalid files and inputs fail with actionable errors.
- [x] Promptfoo adapter uses the same prompt source without a manually duplicated prompt body.
- [x] A basic repository can validate prompts locally and in CI.
- [x] Both language loaders expose the same source digest for the same normalized file content.
- [ ] Run the configured Promptfoo eval against live providers.
