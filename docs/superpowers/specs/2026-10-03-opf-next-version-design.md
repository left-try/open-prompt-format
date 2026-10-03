# OPF Next Version Design

**Status:** Proposed for review  
**Date:** 2026-10-03

## Purpose

Make OPF easier to adopt and safer to use in application repositories. The next release should provide a guided way to start using OPF, reliable local checks, and useful evidence about prompt changes and cacheability. It must state clearly what it can verify and what still depends on the model provider or application.

## Product direction

OPF remains a repository-first prompt format and toolchain. Python continues to provide the `opf` CLI and Python library; TypeScript continues to provide the TypeScript library. The CLI is distributed with the Python package. The prompt artifact remains Markdown with YAML frontmatter.

The release has two scopes:

### Next release

1. `opf init` scaffolds a prompt repository or a new prompt and can add or update an OPF guidance section in `AGENTS.md`.
2. A unified local check validates OPF files, registry references, declared inputs, and selected safety rules; it is suitable for CI and makes no network calls.
3. Release comparison reports changed prompt content, declared inputs, dependencies, and the shared static message prefix. A stable shared prefix is evidence that provider prompt caching may be possible, not proof that a provider cache was used.
4. Prompt-injection checks provide actionable findings and explicit treatment of untrusted input. They are best-effort static checks, not a security guarantee.

### Later releases

5. Usage mapping connects prompt IDs and pinned versions/channels to application references and runtime receipts. Repository scanning can provide candidate references; explicit application references and receipts are the reliable source of usage evidence.
6. An optional integration point for the `okf-aget` repository in the `left-try` organization can be designed after its intended workflow and interface are confirmed. It is not a dependency of the next release.

## Goals

- A developer can start with `opf init`, get a valid example prompt, and receive agent guidance that explains how to create and edit OPF prompts.
- A single local command can check prompt files and registry configuration before commit or model invocation.
- Developers can compare a candidate release with a baseline and understand which stable prefix is eligible for a provider's prompt-cache mechanism.
- Static safety findings distinguish trusted prompt instructions from untrusted runtime input and explain limitations.
- Existing OPF 0.1/0.2/0.3 behavior, Python/TypeScript parsing parity, and current registry bundle digest rules remain compatible.

## Non-goals

- Guaranteeing prompt-injection immunity through prompt wording or a static scanner.
- Claiming that a provider cache hit occurred based only on local content comparison.
- Choosing a model/provider or changing application tool permissions.
- Requiring `okf-aget` or making network calls during init, validation, or diff.
- Building a hosted prompt-management service or replacing Git as the source of truth.
- Automatically rewriting arbitrary existing `AGENTS.md` instructions.

## Proposed user workflows

### Initialize

`opf init` supports creating a starter prompt and optional registry/configuration in the current repository. It offers to add a clearly delimited OPF section to `AGENTS.md`; when run non-interactively, flags control these choices. Existing user text is preserved. Re-running init is idempotent and does not overwrite prompt files or replace unrelated agent instructions. Conflicts are reported with a suggested manual resolution.

The generated agent guidance should explain the repository's canonical prompt location, frontmatter and role syntax, input declaration and validation rules, how to run checks, and the rule to keep dynamic/user-provided content as data. It should avoid pretending the instructions alone prevent prompt injection.

### Validate and check

`opf check` (or an agreed equivalent) runs deterministic, local checks and returns nonzero on errors. It supports text and JSON output. Findings have stable codes, severity, message, and source location where available. Initial checks include format/schema validity, unique IDs, registry target existence and path confinement, required/declaration consistency, unsupported template syntax, and enabled injection-risk heuristics. The command does not call model providers.

Safety checks distinguish errors from advisories. A heuristic match alone should not silently block ordinary development; CI strictness is configurable and documented. Rules should detect likely risky constructs and missing trust-boundary annotations, not attempt to prove semantic safety.

### Compare releases and cacheability

`opf diff ID --base <version-or-channel> --target <version-or-working-tree>` compares normalized prompt/release content, registry definitions, and dependencies. Output identifies changed messages and variables, plus the longest identical leading sequence of rendered message content that can be established without runtime values. If the format cannot establish a precise shared prefix (for example due to unsupported/dynamic Jinja behavior), the report says so rather than guessing.

The cacheability section is provider-neutral and conditional: it reports whether a stable prefix exists and which portions vary. Provider-specific cache requirements and runtime cache-hit indicators belong to explicit adapters/receipts later. A local prefix match is never labeled a cache hit.

### Runtime use and injection boundary

Prompt variables remain simple string substitutions. Documentation and generated guidance describe user inputs as untrusted data. The core renderer does not execute input values as templates. Optional metadata may identify input trust as `untrusted` and expected placement, but any schema addition must preserve old prompt interpretation and be justified by conformance fixtures. Delimiting data in a message can improve clarity but is not a security boundary by itself.

Applications remain responsible for authorization, tool access, output validation, and human approval for consequential actions. Receipts must avoid recording raw inputs or rendered content by default.

## Compatibility and implementation shape

- Keep CLI implementation in the Python package and add the command to the existing `opf` entry point.
- Keep core format parsing/rendering behavior aligned between Python and TypeScript; new shared semantics require fixtures consumed by both SDKs.
- Keep init, check, diff, and static analysis offline and deterministic.
- Do not introduce a new mandatory runtime dependency without a clear need; use existing parsers and report unsupported cases.
- Version comparison uses normalized source and the existing canonical bundle digest contract. Any change to bundle identity requires an explicit schema/version decision and compatibility coverage.
- `AGENTS.md` updates use an OPF-owned marker block. Updates may replace content inside that block only; content outside remains byte-for-byte unchanged.
- No secrets, raw prompt inputs, or model outputs are written by default.

## Success criteria

1. A new repository can run init twice without duplicate sections or destructive changes and can validate the generated prompt.
2. Init preserves existing `AGENTS.md` content and refuses ambiguous marker conflicts without overwriting.
3. Python and TypeScript agree on any newly introduced portable format semantics using shared fixtures.
4. CI can run the local check with stable machine-readable findings and reliable exit codes.
5. A diff correctly identifies unchanged and changed message prefixes, including CRLF normalization and relevant dependencies; dynamic unsupported cases are explicit.
6. Safety output never presents a heuristic scan as a proof or local prefix match as confirmation of provider caching.
7. Existing releases and bundle verification remain valid.

## Open decisions for implementation planning

- Exact CLI syntax and whether the unified command is `opf check`, `opf validate --all`, or both.
- Whether input trust labels are added to the core schema in this release or the first release uses conventions and static findings only.
- How to report provider-independent cache prefixes for templates whose rendered prefix depends on variables.
- Whether init creates `AGENTS.md` by default, only with an option, or via an interactive prompt; non-interactive behavior must be explicit.
- Concrete integration contract and use case for `okf-aget` remain deferred until that repository's interface is inspected.
