# OPF Template and Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give new users a runnable starter repository and a safe way to report migration gaps that informs future adapter work.

**Architecture:** Keep a small starter template in the repository and mark/publish it as a GitHub template repository only after its workflow and package refs are released. Collect feedback through explicit GitHub issue forms; add no telemetry or automatic prompt collection.

**Tech Stack:** Markdown, YAML, OPF Python/TypeScript packages, Promptfoo, GitHub repository template and issue forms.

**Spec:** `docs/superpowers/specs/2026-10-04-opf-adoption-workflow-design.md`

## Global Constraints

- Template can be completed from a clean checkout without model API credentials.
- Model evaluation is optional, clearly marked as potentially chargeable, and uses the paired eval workflow from `2026-10-05-opf-eval-comparison.md`.
- No telemetry or automatic uploads of prompt text, test inputs, outputs, credentials, or private repository files.
- Fixture contributions are a separate explicit choice and require sanitization and license confirmation.
- Keep the template application-neutral and small enough to complete in a few minutes.

## Review Focus

- Clean clone without Node/Python packages installed: documented commands install only required dependencies and explain optional extras.
- Existing user or sample paths collide with `opf init --github`: onboarding instructions explain the no-overwrite behavior and recovery.
- Template workflow references unreleased package or action versions: pre-publication check blocks marking the repository as a template.
- Feedback includes proprietary prompts, customer data, or credentials: issue form warns against sharing and does not require raw prompt text.
- User declines fixture sharing: the report form remains useful with only metadata and does not imply consent to public reuse.

---

## File Map

- `examples/starter-template/README.md`: short time-to-first-check guide.
- `examples/starter-template/opf.yaml`, `prompts/support.reply.md`: minimal prompt and registry example.
- `examples/starter-template/evals/promptfooconfig.yaml`: small eval suite with assertions and no default paid execution.
- `examples/starter-template/.github/workflows/opf.yml`: generated/reusable workflow caller from the GitHub checks plan.
- `examples/starter-template/src/` or an equivalent tiny consumer example: show Python and TypeScript loading only if both fit without unrelated app scaffolding.
- `.github/ISSUE_TEMPLATE/config.yml`: contact links and issue-form settings.
- `.github/ISSUE_TEMPLATE/adapter-request.yml`: structured integration/migration feedback.
- `.github/ISSUE_TEMPLATE/sanitized-fixture.yml`: separate optional fixture contribution path and licensing acknowledgement.
- `README.md`, `docs/production-readiness.md`: template usage, feedback privacy, and template publication checklist.

## Interfaces

The feedback form records only:

- `source_format` (required enum plus `other` text)
- `framework` and version (optional)
- `target_language` (required enum)
- `migration_outcome` (`success|partial|blocked|not_attempted`)
- `missing_capability` (required short text)
- `share_sanitized_fixture` (boolean, default false)

The fixture issue form is separate, explicitly warns users to remove sensitive content, requires an affirmative license confirmation before submission, and never asks for API keys or real customer data.

## Tasks

### Task 1: Build the clean starter repository

**Files:**
- Create: `examples/starter-template/README.md`
- Create: `examples/starter-template/opf.yaml`
- Create: `examples/starter-template/prompts/support.reply.md`
- Create: `examples/starter-template/evals/promptfooconfig.yaml`
- Create: `examples/starter-template/.github/workflows/opf.yml`
- Add tests or scripts under `packages/python/tests/` and `packages/typescript/test/` only if the existing check infrastructure can validate the sample without model calls.

- [ ] Add a clean-checkout smoke test that copies the starter tree to a temporary directory, runs `opf check`, validates its prompt collection and registry, and proves the sample workflow pin is present.
- [ ] Run the smoke test and confirm it fails because the starter tree does not yet exist.
- [ ] Add one provider-neutral starter prompt with declared inputs, one registry entry, and a rollback walkthrough showing draft → release → promote → verify → previous release.
- [ ] Add a handful of simple test cases and deterministic assertions; place real provider IDs in an explicitly optional section and do not run them by default.
- [ ] Add a README with a short clean-checkout sequence and direct links to the generated GitHub workflow behavior and paid-eval instructions.
- [ ] Run the starter smoke test and `opf verify-all --registry examples/starter-template/opf.yaml` (or the supported validation command if it has no release channel yet).

### Task 2: Validate the user journey in both SDKs

**Files:**
- Modify: `examples/starter-template/README.md`
- Create: `examples/starter-template/src/python_example.py` and/or `examples/starter-template/src/typescript_example.ts` only if those examples are both minimal and runnable.
- Modify: existing Python/TypeScript package tests only for demonstrated API coverage.

- [ ] Decide based on the current CLI/library interfaces whether code samples improve the minimal quick start; avoid adding an application scaffold that obscures prompt adoption.
- [ ] If adding the examples, write failing smoke tests for the Python and TypeScript documented load/render calls using the same example inputs.
- [ ] Add the language examples and ensure both produce the same ordered `{role, content}` messages and release digest.
- [ ] Run the relevant package tests and record any Jinja or Node version prerequisites in the guide.

### Task 3: Add structured opt-in feedback forms

**Files:**
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/ISSUE_TEMPLATE/adapter-request.yml`
- Create: `.github/ISSUE_TEMPLATE/sanitized-fixture.yml`
- Modify: `README.md`

- [ ] Add a contract test or lint script that parses the YAML forms and asserts the required metadata fields, default-false fixture sharing, warning copy, and affirmative license checkbox.
- [ ] Run the form validation check and confirm it fails before the forms exist.
- [ ] Implement the adapter request form with the specified fields and explicit warning not to include prompts, customer data, credentials, or proprietary content.
- [ ] Implement the separate fixture submission form. Make a fixture optional and require a separate affirmative license acknowledgement for any attached public-use example.
- [ ] Add contact links from the main README and starter guide; do not add network telemetry, post-install callbacks, or auto-created issues.
- [ ] Run the form validation check and inspect rendered YAML locally or in GitHub after publishing.

### Task 4: Prioritize integration requests from evidence

**Files:**
- Create: `docs/integration-request-triage.md`
- Modify: `docs/production-readiness.md`

- [ ] Define a lightweight triage rubric: repeated demand, number/severity of migration blockers, relevance to the portable core, maintainable conformance tests, and source licensing/sensitivity.
- [ ] Define explicit disposition labels (`needs-example`, `candidate-adapter`, `candidate-format-extension`, `out-of-scope`) and require a real fixture or documented workflow before accepting a new normative capability.
- [ ] Document that an individual request is not a commitment and that a vendor-specific feature should remain an adapter or namespaced extension unless a cross-provider use case is demonstrated.
- [ ] Review the rubric against the deferred `okf-aget` mention; leave it unprioritized until its identity and workflow are known.

### Task 5: Prepare template repository publication

**Files:**
- Modify: `README.md`
- Modify: `docs/production-readiness.md`
- Modify: `PUBLISHING.md` only if package/workflow/template release ordering belongs there.

- [ ] Add a release checklist verifying all package and reusable-workflow refs exist, all links resolve, the clean-checkout smoke passes, and the optional eval is clearly separated from default setup.
- [ ] Document the manual GitHub repository setting required to mark the starter path as a template; do not automate repository settings from local code.
- [ ] Run the complete documented clean-checkout path without provider credentials and record that as the first-user acceptance check.

## Acceptance

- A developer can create a repository from the starter template, complete the no-secret check, and understand the next step without maintainer assistance.
- The eval path is clearly optional and does not make provider calls during the default quick start.
- Feedback can be filed without prompt text or any automatic data transfer; sharing a fixture is separately opted into and licensed.
- New integrations are prioritized from anonymized real workflows and migration evidence rather than speculative format growth.
