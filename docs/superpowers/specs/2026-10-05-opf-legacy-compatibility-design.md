# OPF Legacy Compatibility and Migration Diagnostics

## Status

Design proposal for review. This document does not change current OPF behavior.

## Purpose

Let teams connect existing prompt repositories without first rewriting every file, while keeping OPF's purpose clear: one Markdown file should contain the prompt and the structured data that belongs to that prompt. Compatibility is an adoption path, not a claim that every source syntax is portable OPF.

The compatibility path must preserve source structure where possible, identify every material mismatch with portable OPF, and recommend a concrete migration path. It must never silently discard data or imply that an adapter-specific runtime is portable.

## Goals

- Recognize both `# role` and `## role` headings for every core role: `system`, `developer`, `user`, and `assistant`.
- Keep `## role` as the canonical form in OPF examples and generated migrations.
- Preserve structured prompt-associated data such as styles, tones, templates, media types, UI labels, ordering, slots, colors, and rendering parameters.
- Continue to support compatible legacy sources through explicit adapters, including Jinja where required.
- Report source incompatibilities, adapter requirements, portability limits, and data loss with actionable recommendations.
- Keep Python and TypeScript implementations behaviorally aligned.

## Non-goals

- Treat arbitrary application data as model messages.
- Claim that Jinja control flow is part of the portable OPF template language.
- Invent one universal schema for all application-specific data before reviewing representative real examples.
- Silently rewrite legacy prompt meaning or discard unsupported metadata.

## Compatibility model

The tooling distinguishes three independent properties:

1. **Loadable:** the source can be parsed or executed by a named OPF adapter.
2. **Preserved:** source fields and structure survive registration or migration, either in portable core fields or in a namespaced extension.
3. **Portable:** the prompt uses semantics defined by the OPF core and can be rendered consistently without its source framework/runtime.

An input may be loadable and preserved while not being portable. Reports must state these properties separately.

## Message heading syntax

For each supported core role, a role marker is either an exact `# role` or `## role` heading at the beginning of a line. The two forms have identical role semantics. The parser must not infer roles from `### role`, different capitalization, or headings with trailing text. Existing protections for fenced code blocks and escaped role headings continue to apply to both forms.

Canonical OPF syntax and generated migration output use `## role`. A `# role` input is accepted but receives a non-blocking style diagnostic recommending the canonical spelling. Other malformed heading-like lines remain ordinary content unless another validation rule rejects them.

The implementation must first determine whether the existing parser can support both heading levels without ambiguity with ordinary Markdown headings. Any ambiguity found in representative prompts must be documented and resolved with shared fixtures before implementation is considered complete.

## Structured associated data

Application data that is not a model message must remain data. Catalog entries such as styles, tones, formatting presets, media types, and templates must not be wrapped in artificial `system` sections merely to pass prompt validation.

The migration and compatibility layer must preserve the original nested shape and values when representing such data. Where a portable core schema does not yet exist, a registered namespaced extension or adapter-owned resource representation may carry the data. The chosen representation must:

- retain nested mappings, arrays, scalar types, labels, identifiers, order, slots, and presentation values;
- identify its source adapter and data/resource kind;
- make clear which consumer understands its semantics;
- avoid claiming cross-runtime portability unless that behavior is specified and tested;
- preserve unknown data through read/write transformations, or refuse the write unless the user explicitly permits a named loss.

Before defining a normative resource schema, implementation work must inspect representative sanitized examples from both mature repositories. If no examples are available, the first implementation must preserve them opaquely and document that semantic normalization is deferred.

## Compatibility and migration diagnostics

`opf check` and migration inspection must provide findings with, where available:

- source path and line/field location;
- stable finding code and severity;
- compatibility category: portable, preserved extension/resource, adapter/runtime dependency, unsupported, or data loss;
- concise explanation of the effect on loading, rendering, or portability;
- a recommended action toward canonical OPF.

At minimum, diagnostics cover non-canonical single-hash role headings, Jinja control flow or filters, adapter-specific runtime settings, structured application data outside message syntax, unknown metadata, and any field or behavior that cannot be preserved.

The default check may succeed with warnings when the source remains loadable and all data is preserved. Strict migration must fail when conversion would lose or ambiguously change data unless the user explicitly opts into the reported loss. Reports must not expose prompt values, runtime inputs, secrets, or rendered model outputs.

## Legacy rendering adapters

Adapters may retain the original source and invoke a source-specific renderer, including Jinja. They must declare the runtime dependency and any unsupported constructs or dynamic dependencies they encounter. They must not describe adapter execution as portable core rendering.

When a source can be represented using core inputs and interpolation, the migration report should identify that path. When behavior depends on conditionals, loops, filters, includes, or framework execution, the report must retain the adapter path and recommend manual or staged conversion rather than silently flattening behavior.

## Cross-language behavior

Python and TypeScript implementations must share fixtures for heading recognition, message extraction, escaped/fenced literals, diagnostics, and source/resource preservation wherever those features are implemented in both SDKs. Stable finding codes and category semantics must match across implementations; wording may vary if the meaning is equivalent.

## Acceptance criteria

- All four core roles parse identically with one- and two-hash headings in Python and TypeScript.
- Canonical examples and migration output use two-hash headings.
- Headings inside code fences and escaped headings remain literal for both heading levels.
- Structured associated data is never converted into fake model messages.
- A migration/read-write path preserves representative nested catalog data, or refuses a write that would lose it unless explicit loss is selected.
- Check and migration reports identify every detected incompatibility, its impact, and a recommended next step.
- A legacy source may be loadable through an adapter while being clearly marked non-portable.
- Existing OPF syntax and registry behavior remain compatible unless a separate versioned specification explicitly changes them.

## Open design decision

The exact representation for associated data (namespaced extension versus an adapter-owned resource record) must be selected after examining sanitized examples from both repositories. The design must preserve the single-file-per-task goal and must not force catalog resources into message sections.
