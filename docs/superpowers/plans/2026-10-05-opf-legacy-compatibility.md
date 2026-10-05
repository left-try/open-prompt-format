# OPF Legacy Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept common legacy role-heading syntax, preserve associated structured data through adapters, and report compatibility gaps with actionable migration guidance.

**Architecture:** Extend the existing Python and TypeScript parsers and compatibility report model rather than creating a parallel validation system. Keep the portable core strict about runtime semantics, while migration adapters preserve application-specific data in structured extensions/resources and report when execution still depends on a legacy runtime. Shared conformance fixtures define cross-language behavior.

**Tech Stack:** Python 3.10+, PyYAML, TypeScript/Node, existing Python unittest suite, existing TypeScript node:test suite, shared fixture-driven conformance tests.

**Spec:** `docs/superpowers/specs/2026-10-05-opf-legacy-compatibility-design.md`

## Global Constraints

- Accept exact `# role` and `## role` for `system`, `developer`, `user`, and `assistant`; canonical generated output is `## role`.
- Do not wrap application data in artificial model messages.
- Preserve unknown structured data, or refuse a write unless the user explicitly permits a named loss.
- An adapter-specific runtime may make a source loadable without making it portable.
- Python and TypeScript must agree on finding codes and category semantics.
- Reports must not include prompt values, runtime inputs, secrets, or rendered model outputs.
- Keep existing OPF syntax and registry behavior compatible.

## Review Focus

- Single-hash role headings inside fenced code or escaped as literals: they remain content; add cases to shared fixtures and both SDK conformance tasks.
- Ordinary Markdown headings such as `### user`, `## User`, and `## user extra`: they do not become message markers; add cases to both SDK conformance tasks.
- Metadata/resources with nested mappings, arrays, scalar types, and order: round-trip without coercion or loss; add to the adapter preservation task.
- Legacy renderer constructs such as Jinja conditionals, filters, and dynamic includes: reports identify runtime dependence or manual work; add adapter report tests.
- Strict migration with a lossy/ambiguous finding: refuses apply unless explicit loss is selected; add migration tests.

---

## File Map

- `packages/python/src/opf/core.py`: recognize both role heading levels and expose parser findings for non-canonical heading spelling without changing message rendering.
- `packages/typescript/src/index.ts`: implement the same heading and finding behavior in the TypeScript parser.
- `packages/python/src/opf/compatibility.py`: define the shared Python finding categories and optional source location/recommendation fields.
- `packages/python/src/opf/check.py`, `packages/python/src/opf/cli.py`: surface compatibility findings in check and migration inspection output, preserving current exit behavior except strict-mode findings.
- `packages/python/src/opf/adapters/base.py`, `packages/python/src/opf/adapters/common.py`, and focused adapter modules: carry structured source data without converting it to messages; annotate adapter/runtime limits.
- `packages/python/src/opf/migrate.py`: enforce preservation and explicit loss decisions before filesystem writes.
- `fixtures/conformance.json` and `fixtures/prompts/`: shared parse fixtures consumed by both SDK suites.
- `packages/python/tests/test_conformance.py`, `packages/python/tests/test_compatibility.py`, `packages/python/tests/test_migration_compatibility.py`, `packages/typescript/test/conformance.test.js`: assert parser, report, and migration behavior.
- `spec/SYNTAX-0.3.md`, `spec/REGISTRY.md`, `examples/migration/README.md`, `README.md`, `docs/production-readiness.md`: document canonical versus compatible syntax, preserved data, report categories, and migration steps.

## Interfaces

Python `CompatibilityFinding` gains optional `category`, `source_line`, `source_field`, and `recommendation` fields. `category` is one of `portable`, `preserved_resource`, `adapter_runtime`, `unsupported`, or `data_loss`. Existing `code`, `severity`, `disposition`, `message`, `capability`, and `source_path` fields remain supported. JSON serialization omits unset optional fields. `opf check`'s `Finding` also gains optional `category` and `recommendation`; it copies those values and source location from compatibility findings.

TypeScript `CompatibilityFinding` uses the same optional property names and category literals. Both implementations retain existing severity and disposition meanings. Finding codes introduced by this plan use stable dotted names, including `heading.noncanonical.single_hash`, `template.jinja.runtime_required`, `metadata.preserved.extension`, `resource.preserved.opaque`, and `migration.data_loss.refused` where applicable.

Migration apply gains repeatable `--accept-loss CODE`. The apply function receives `accepted_losses: set[str]`; it may bypass only matching findings categorized `data_loss`, and `--register` is required so the resulting manifest durably records each accepted code. `--accept-loss` does not bypass `unsupported`, `manual`, or error findings unrelated to the explicitly accepted loss. Strict apply without a matching acceptance remains blocked.

Migration adapters preserve unknown structured values in a namespaced extension or adapter-owned resource record. Before implementing that representation, inspect all checked-in migration examples and current adapter inputs. If no representative source catalog files are available, use an opaque JSON-compatible payload under the source adapter's existing namespace and report `preserved_resource`; do not define a new universal resource schema in this change.

For legacy Markdown YAML frontmatter without real source catalog fixtures, store all JSON-compatible fields in the required `com.github.stovo-team.open-prompt-format.source` extension, under `data: {source_kind: markdown-frontmatter/1, metadata: ...}`. Report each field without exposing its value. Preserve OpenAI snapshot fields outside `schema`, `variables`, and `messages` in `com.openai.responses`; preserve analogous unknown LangChain and CrewAI fields in their vendor namespaces. A non-JSON-compatible field is omitted only with a unique finding code of the form `metadata.value.not_json_compatible[FIELD]`; it blocks apply until that exact code is passed via `--accept-loss` and is recorded in the migration manifest.

---

### Task 1: Add role-heading compatibility and shared fixtures

**Files:**
- Modify: `packages/python/src/opf/core.py`
- Modify: `packages/typescript/src/index.ts`
- Modify: `packages/python/tests/test_conformance.py`
- Modify: `packages/typescript/test/conformance.test.js`
- Modify: `fixtures/conformance.json`
- Modify: `spec/SYNTAX-0.3.md`

**Interfaces:**
- Produces parser behavior accepting `# role` and `## role` for all four core roles.
- Parsing and rendering continue to return the same ordered role/content messages.
- Parser compatibility findings expose noncanonical single-hash usage without making parse fail.

- [x] Add shared valid fixtures for each of the four roles with both heading levels; assert expected role/content output.
- [x] Add fixtures proving `### user`, `## User`, and `## user extra` are not role markers, and single-hash headings in fenced/escaped content remain literal.
- [x] Run `python -m unittest discover -s packages/python/tests -p 'test_conformance.py' -v` and confirm new fixtures fail for the current one-level parser.
- [x] Update both parsers to recognize exactly `^#{1,2} (system|developer|user|assistant)$` outside fences; retain escaped-literal behavior for both accepted forms.
- [x] Emit `heading.noncanonical.single_hash` as an informational compatibility finding for each source occurrence, without including prompt body content.
- [x] Run the focused Python and TypeScript conformance tests and confirm parity.
- [x] Document both accepted spellings and canonical `## role` in `spec/SYNTAX-0.3.md`.

### Task 2: Extend compatibility finding contract and CLI reports

**Files:**
- Modify: `packages/python/src/opf/compatibility.py`
- Modify: `packages/python/src/opf/core.py`
- Modify: `packages/python/src/opf/check.py`
- Modify: `packages/python/src/opf/cli.py`
- Modify: `packages/typescript/src/index.ts`
- Modify: `packages/python/tests/test_conformance.py` and focused CLI/check tests
- Modify: `packages/typescript/test/conformance.test.js`

**Interfaces:**
- Produces stable categories `portable`, `preserved_resource`, `adapter_runtime`, `unsupported`, and `data_loss`.
- Finding serialization includes optional `source_line`, `source_field`, and `recommendation`, omitting absent values.
- Default checks may return warnings; strict checks fail on warnings as currently specified by CLI strict behavior and always fail on errors.

- [x] Add Python serialization tests for every category, optional location/recommendation fields, and omission of unset values.
- [x] Add equivalent TypeScript type/runtime fixture checks for the same finding objects and stable category values.
- [x] Add CLI tests proving text and JSON outputs surface findings without printing message bodies or inputs.
- [x] Implement the extended finding type and serializers in Python and TypeScript.
- [x] Thread findings from prompt parsing and migration inspection through `opf check`/CLI output while preserving existing command contracts.
- [x] Verify ordinary non-strict checks remain successful for informational and warning findings and strict behavior remains consistent with existing CLI semantics.

### Task 3: Preserve structured associated data and report adapter limits

**Files:**
- Modify: `packages/python/src/opf/adapters/base.py`
- Modify: `packages/python/src/opf/adapters/common.py`
- Modify: focused source adapters under `packages/python/src/opf/adapters/`
- Modify: `packages/python/src/opf/migrate.py`
- Modify: existing Python adapter and migration tests
- Create or modify: sanitized fixtures under `packages/python/tests/fixtures/migration/`

**Interfaces:**
- Adapter output stores structured application data without synthesizing `system` or other model messages.
- Data payloads use JSON-compatible values and preserve nested shape, array order, scalar types, and keys.
- Adapter findings use the Task 2 categories and include actionable recommendations for Jinja/runtime dependencies, unknown metadata, preserved resources, unsupported behavior, and data loss.
- Strict apply refuses any `data_loss` finding unless its exact stable code is explicitly accepted with repeatable `--accept-loss CODE`; it always refuses ambiguous/manual or unrelated error findings.

- [x] Inspect existing adapters and repository fixtures; record the concrete source-data shapes already present and select the narrowest representation that preserves them.
- [x] Add synthetic sanitized nested resource fixtures covering mappings, arrays, scalar types, ordering metadata, UI fields, and opaque unknown fields.
- [x] Add failing adapter tests proving associated data is preserved in the generated artifact and is never emitted as a model message.
- [x] Add failing tests for Jinja conditionals/filters/dynamic includes and adapter-specific runtime settings; assert category, impact, and migration recommendation.
- [x] Add failing strict-apply tests proving lossy writes stop before filesystem changes, `--accept-loss CODE` permits only the named data-loss finding, and the accepted code is recorded in the manifest.
- [x] Implement preservation using existing extension/resource mechanisms; avoid introducing a new universal schema in this change.
- [x] Implement stable adapter findings and strict preflight checks before any migration writes; thread `accepted_losses` through CLI to `apply_migration` and manifest provenance.
- [x] Run focused Python adapter/migration tests and verify generated extension/resource payloads round-trip exactly at the parsed-data level.

### Task 4: Publish the compatibility and migration contract

**Files:**
- Modify: `spec/SYNTAX-0.3.md`
- Modify: `spec/REGISTRY.md`
- Modify: `examples/migration/README.md`
- Modify: `README.md`
- Modify: `docs/production-readiness.md`
- Modify: Python and TypeScript conformance tests only if documentation examples need executable fixtures

**Interfaces:**
- Documentation distinguishes loadable, preserved, and portable.
- Migration guidance shows canonical `## role`, accepted legacy `# role`, structured resource preservation, adapter runtime requirements, and strict loss behavior.
- Examples do not imply that Jinja or opaque resources are portable core semantics.

- [x] Add docs assertions/fixture checks for exact heading rules and category names where existing documentation tests support them (no documentation test harness exists in this repository).
- [x] Document the compatibility model and stable findings in the syntax and registry specs.
- [x] Update migration guidance with a sample report and a staged migration flow that keeps existing runtime behavior when needed.
- [x] Add a production-readiness note that repository-scale adoption remains unverified until the adapters are exercised against sanitized examples from both mature repositories.
- [x] Run Python conformance and adapter/migration tests, TypeScript conformance tests, and the documented local validation commands; review final diffs for privacy-safe reports and backward compatibility.

## Acceptance

- All core roles parse the one-hash and two-hash forms identically in Python and TypeScript; generated/canonical content remains two-hash.
- Fenced and escaped headings remain literal, while malformed or unrelated Markdown headings do not create messages.
- Structured associated data is preserved or the write is refused before filesystem mutation; it is never fabricated into a model message.
- Compatibility reports carry stable category codes and actionable recommendations for all detected gaps without exposing prompt contents or runtime values.
- Legacy renderers can remain available while reports distinguish loadability from portability.
- Existing OPF syntax and registry tests pass without behavior changes outside the specified compatibility additions.
