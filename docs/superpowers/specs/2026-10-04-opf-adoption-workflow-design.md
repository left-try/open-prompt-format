# OPF adoption workflow design

**Status:** Draft for review  
**Date:** 2026-10-04  
**Purpose:** Define a fast, low-friction path for a repository to adopt OPF, validate prompt changes in pull requests, compare evaluation behavior, and provide opt-in feedback that guides future integrations.

## 1. Product intent

OPF should be easy to try in an existing GitHub repository without introducing a hosted service or requiring model credentials for the first successful run. A developer should be able to start from a template or initialize an existing repository, receive useful local and pull request checks, and understand how a prompt change affected both the source and its evaluated behavior.

The product remains repository-first: Git and OPF releases identify the prompt source of truth. GitHub Actions orchestrate checks; Promptfoo executes evaluations; Langfuse remains an optional publication and observability target. The workflow must not silently create a second production source of truth.

## 2. Intended users and outcome

The initial user is a developer or small application team maintaining LLM prompts in a GitHub repository. They may have existing Markdown/Jinja or supported framework prompt assets and want a safe incremental adoption path.

The user outcome is a pull request that clearly answers:

1. Is the prompt repository structurally valid and are deployed OPF releases verifiable?
2. What changed between the baseline and proposed prompt release?
3. Did the behavior measured by the configured eval suite improve, regress, or remain within the team's acceptance criteria?
4. How can a maintainer share an integration gap or anonymized migration example with OPF maintainers?

## 3. Product principles

1. **Useful before credentials.** Structural checks, release verification, and deterministic rendering run without model API keys.
2. **Paid calls are explicit.** Provider eval is opt-in, clearly documented, bounded in scope, and uses repository/environment secrets only where available.
3. **One source of truth.** Prompt source and release identity stay in Git; Langfuse publication is an explicit deployment step.
4. **Evidence over a single score.** Eval reports expose cases, providers, assertions, and run metadata; they do not reduce quality to an unexplained aggregate.
5. **No surprise data collection.** Feedback is user-initiated. Prompt text, inputs, outputs, credentials, and private repository content are never automatically uploaded as telemetry.
6. **Incremental adoption.** Users can run checks on existing OPF files and supported sources before converting an entire prompt repository.
7. **Pin what runs.** Reusable actions, packages, prompt releases, and eval configurations must support version pinning and traceable run metadata.

## 4. User journey

### 4.1 Start

Offer two entry points:

- **Template repository:** a minimal sample application, one representative OPF prompt, a small Promptfoo suite, a local check command, and a ready-to-run GitHub workflow.
- **Existing repository:** `opf init --github` (or an equivalent explicit option) previews and then creates only missing starter files and the OPF workflow. It preserves existing project files and reports collisions rather than overwriting them.

Both entry points link to one short quick start. The template is the quickest demo; init is the migration path for real repositories.

### 4.2 Pull request checks

On changes to registered prompts, `opf.yaml`, eval config, or the workflow, the action runs the no-secret gate:

- install a pinned OPF CLI/runtime;
- run `opf check`;
- run `opf verify-all` when the repository has registered releases/channels;
- build or validate the selected Promptfoo adapter/config without calling paid providers;
- produce a concise report with stable finding codes and links to relevant files.

An optional eval job runs only when explicitly enabled and its credentials are available. It evaluates the base and proposed prompt using the same test cases, provider configuration, and model settings. It stores the baseline and candidate run identifiers, prompt release/digests, test/config identity, provider/model names, assertion outcomes, and a link or artifact for detailed results. It must not store raw user data or prompt outputs in the Git diff by default.

For pull requests from forks, the workflow skips credentialed evaluation and clearly reports why; it still runs the no-secret gate. Maintainers can trigger the paid eval from a trusted branch or approved environment.

### 4.3 Feedback

The template, CLI summary, and documentation link to an opt-in feedback form or GitHub issue form. Ask for structured, non-sensitive details: source format/framework, language, migration outcome, missing capability, and willingness to share a sanitized fixture. Clearly instruct users not to include secrets, customer data, or proprietary prompt text. Fixture contributions require a separate explicit choice and license confirmation.

## 5. GitHub Action design

### 5.1 Interface

Provide one supported setup path for the first release:

- `opf init --github` creates a workflow using a tagged reusable action (or a reusable workflow if that proves simpler to maintain).
- The generated workflow has a no-secret `check` job enabled by default.
- A separate `eval` job is disabled by default and can be enabled through explicit configuration. The generated file documents provider secret names, expected spend, and how to restrict runs to trusted branches or approved environments.
- Users can invoke the same commands locally, so CI does not hide behavior in a black box.

Avoid a matrix of multiple action types and complex configuration formats in the initial release. Start with a small set of stable inputs: working directory, registry path, whether to run eval, eval config path, and output/report path.

### 5.2 Versioning and maintenance

The action must be versioned and documented. Consumers should be able to pin an immutable release tag or commit SHA. The generated example should use a stable major tag only after the action contract is ready for that promise. The workflow should pin runtime versions and install a released OPF package; it must not depend on the repository's unpublished source tree in normal consumer use.

### 5.3 Failure behavior

- Invalid prompts or registry integrity failures fail the required check.
- Missing optional credentials skip eval with an explicit neutral status, not a misleading pass.
- Provider or Promptfoo errors fail the eval job and preserve enough sanitized diagnostics to reproduce the run.
- Evaluation assertions use a documented threshold and make the comparison baseline explicit.
- A failed eval blocks merge only when the repository owner explicitly enables that policy.

## 6. Prompt diff and eval comparison

The existing `opf diff` provides source/release comparison and cacheability evidence. The adoption workflow should add a human-readable pull request summary that pairs:

- changed prompt files, metadata, declared inputs, and release identity;
- baseline versus candidate eval outcomes per provider and test case;
- new failures, recovered failures, score/metric changes, and provider errors;
- limitations such as nondeterminism, judge variance, or unavailable baseline results.

Promptfoo remains the evaluator. OPF should orchestrate two comparable prompt versions through the existing adapter/config where practical and normalize run metadata for the PR summary; it should not implement a competing eval engine or invent a universal quality score. The same provider/model settings and test set must be used for both sides. Results are comparable only when those inputs match, and any mismatch is called out.

Baselines should be reproducible from the base commit or a recorded immutable eval artifact. Do not treat a mutable `production` label as a reproducible baseline. If a baseline cannot be reconstructed, report that explicitly and evaluate the candidate without claiming a regression comparison.

## 7. Template repository

The official template should be intentionally small and runnable in a clean checkout. It contains:

- one application-neutral OPF prompt and a small declared input set;
- one registry/release example with a safe rollback walkthrough;
- a handful of Promptfoo test cases and assertions;
- local setup commands and the generated no-secret GitHub workflow;
- an optional, clearly marked paid-eval setup;
- a worked PR report showing source diff and eval comparison;
- a link to report missing formats/adapters through the opt-in feedback channel.

The template must label example model/provider settings as examples and explain any credentials or charges before the user enables live eval.

## 8. Feedback and prioritization

Feedback is collected through an explicit issue/form workflow rather than background telemetry. Submissions should map to a small schema: source type, framework/version if known, target language, capability requested, migration result category, and optional sanitized fixture. Public examples must be reviewed for sensitive content and licensing before inclusion.

Prioritize future format or adapter work using repeated user demand, migration failure frequency, impact on the core workflow, and ability to define shared conformance fixtures. Do not expand the normative format solely to encode one vendor's transient API surface; prefer a namespaced extension or adapter where the behavior is provider-specific.

## 9. Delivery phases

### Phase A: adoption foundation

- finalize the supported quick-start path and sample prompt/eval;
- make the no-secret workflow run on a clean consumer repository;
- define stable action inputs, versioning, reports, and failure semantics;
- add `opf init --github` only after its file-preservation behavior is specified.

### Phase B: paired eval reporting

- resolve base and candidate prompt versions reproducibly;
- run both against the same Promptfoo test/provider configuration;
- produce a PR summary and downloadable detailed result artifact;
- document nondeterminism, cost, privacy, and fork/secret behavior.

### Phase C: template and user feedback

- publish the template repository and quick-start guide;
- add the opt-in feedback/issue form and sanitized fixture contribution path;
- run the workflow with external pilot users and prioritize based on evidence.

### Phase D: broader release

- publish/pin the OPF packages and action;
- add compatibility and security review for workflow permissions and dependency pinning;
- graduate features from experimental only after real repository examples and failure cases are covered.

## 10. Success measures

Initial success is measured by whether a new user can complete the template quick start without maintainer help, whether the no-secret action works on a clean GitHub repository, whether the paired report identifies a known intentional regression, and whether users can provide useful feedback without sharing private prompt content.

Track adoption through opt-in templates/feedback and public repository signals where appropriate. Do not add automatic usage telemetry for the initial release.

## 11. Scope boundaries and open decisions

- No hosted prompt registry, editor, or analytics service in this project slice.
- No automatic publishing to Langfuse or moving a remote production label from a pull request.
- No mandatory model calls or credentials in default CI.
- No universal eval metric or replacement for Promptfoo.
- No automatic upload of prompt text, test inputs, or outputs.
- OKF/`okf-aget` is excluded until its identity, interface, and intended workflow are clarified.
- Before implementation planning, confirm whether the initial GitHub integration should be a composite action or reusable workflow, and confirm which eval runner/model budget is available for pilot use.

## 12. Relationship to current repository

The repository already has `opf check`, `opf diff`, a TypeScript Promptfoo adapter, a Promptfoo config, local Git release verification, and a draft production readiness guide. The new design should reuse these capabilities, add missing user-facing orchestration, and update maturity claims only after the external and consumer-repository checks have run. The current Promptfoo config has a single test without explicit assertions; it is a smoke example, not yet a regression suite.
