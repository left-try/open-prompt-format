# OPF Eval Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show in a pull request whether a proposed prompt version changed measured behavior compared with the same prompt at the base commit.

**Architecture:** Reuse the generated reusable workflow from `2026-10-05-opf-github-checks.md` and keep Promptfoo as the evaluator. Run the same configured suite against base and candidate prompt files, then normalize the pinned Promptfoo JSON outputs into a small sanitized summary; raw model outputs remain temporary and are not uploaded.

**Tech Stack:** GitHub Actions, Node.js 22, Promptfoo CLI, existing TypeScript Promptfoo adapter, Python 3.10+ for the result summarizer, shared unit-test fixtures.

**Spec:** `docs/superpowers/specs/2026-10-04-opf-adoption-workflow-design.md`

## Global Constraints

- Eval is disabled by default and only runs when `run-eval` is explicitly enabled.
- Both runs use the same Promptfoo config, test cases, providers, and model settings.
- Base prompt content is loaded from the pull request base commit; mutable `production` labels are not used as baselines.
- Fork pull requests never receive provider secrets; absence of keys produces a neutral skipped result.
- Provider credentials are environment-scoped to a protected `prompt-eval` environment with required reviewer approval; a PR-controlled config or adapter never receives them before approval.
- No prompt, test inputs, raw outputs, provider errors with payloads, or secrets are uploaded in the workflow summary or artifact.
- Promptfoo remains the evaluation engine; OPF reports observed outcomes and does not define a universal quality score.

## Review Focus

- Different test/provider matrices or missing base prompts: refuse to claim a paired regression comparison.
- Promptfoo rows without assertions, with `gradingResult: null`, or with provider errors: distinguish ungraded, failed, and errored cases.
- A baseline succeeds while candidate fails, and vice versa: report regression/recovery using stable case/provider identity.
- Eval JSON contains prompts, vars, config, outputs, secrets, or provider error payloads: summary and uploaded artifact exclude them.
- Eval is enabled on fork PRs without credentials or manually on trusted branches: skip without leaking a secret or misreporting a pass.
- A same-repository PR changes its eval config or adapter while provider credentials exist: require protected environment approval before the eval job starts.

---

## File Map

- `.github/workflows/opf-check.yml`: optional isolated eval job and optional secrets declaration; default `run-eval` is false.
- `adapters/promptfoo.cjs`: continue using `OPF_PROMPT_FILE`; no prompt duplication.
- `evals/promptfooconfig.yaml`: add representative cases and explicit assertions; keep providers and model settings in Promptfoo.
- `scripts/compare_promptfoo_results.py`: normalize two Promptfoo JSON outputs and produce sanitized aggregate/per-case outcomes.
- `packages/python/tests/test_eval_report.py`: parser and comparison cases using synthetic Promptfoo fixtures.
- `packages/python/pyproject.toml` or a standalone script runtime: use only stdlib for summary parsing unless an existing dependency is essential.
- `README.md`, `docs/production-readiness.md`: opt-in setup, cost, privacy, base comparison rules, and skipped states.

## Interfaces

Reusable workflow additions:

- Boolean input `run-eval`, default `false`.
- Boolean input `block-on-regression`, default `false`.
- String input `eval-config`, default `evals/promptfooconfig.yaml`.
- String input `prompt-file`, required only when eval is enabled; it names one OPF prompt path relative to the consumer repository.
- String input `base-ref`, optional for trusted manual runs; pull requests use the event's base SHA.
- Environment-scoped secrets `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`; configure them in protected environment `prompt-eval` with required reviewers. Do not forward repository secrets directly through `workflow_call`.

Summarizer API:

```python
compare_results(baseline: dict, candidate: dict) -> dict
```

Return schema `opf-eval-comparison/1` with `status`, `baseline_eval_id`, `candidate_eval_id`, `baseline_commit`, `candidate_commit`, `matrix`, `summary`, and sorted `cases`. Each case records `case_id`, `provider_id`, baseline/candidate state and score, and `change` in `unchanged|regression|recovered|changed|error|ungraded`. The report contains no raw prompts, variables, outputs, assertion reasons, or provider payloads. Pair rows by stable test index and provider identity; reject mismatched matrices rather than pairing by array order alone.

## Tasks

### Task 1: Add a deterministic eval report contract

**Files:**
- Create: `packages/python/tests/test_eval_report.py`
- Create: `packages/python/tests/fixtures/promptfoo-baseline-v3.json`
- Create: `packages/python/tests/fixtures/promptfoo-candidate-v3.json`
- Create: `scripts/compare_promptfoo_results.py`

- [ ] Add failing tests for unchanged pass, regression, recovered failure, provider error, ungraded row, null grading result, and mismatched provider/test matrices.
- [ ] Include fixture values for the documented Promptfoo v3 output shape: `evalId`, `results.version`, `results.providers`, `results.results[]`, `testIdx`, `promptIdx`, `success`, `score`, and optional `gradingResult`/error fields. Fixtures use synthetic prompt data only.
- [ ] Run `python -m unittest discover -s packages/python/tests -p 'test_eval_report.py' -v` and confirm failure because the summarizer is absent.
- [ ] Implement `compare_results(baseline: dict, candidate: dict) -> dict` with strict shape checks, provider/test pairing, and report schema `opf-eval-comparison/1`.
- [ ] Add CLI arguments `--baseline`, `--candidate`, and `--output`; write only the sanitized report. Use distinct exit codes for malformed inputs and a valid comparison containing regressions.
- [ ] Run the focused suite and inspect generated report fixtures to confirm no synthetic prompt text, vars, outputs, assertion reasons, or provider errors are copied.

### Task 2: Strengthen the sample eval suite

**Files:**
- Modify: `evals/promptfooconfig.yaml`
- Modify: `examples/support.reply.md` only if the currently declared behavior cannot support deterministic assertions.
- Modify: `PLAN.md` and `docs/production-readiness.md`

- [ ] Add at least four representative support cases: ordinary delayed order, missing order facts, ambiguous request, and a request to invent/order data not supplied.
- [ ] Add explicit assertions for stable requirements (for example, no invented tracking details and a concise next step); prefer deterministic string/regex/schema assertions over model-graded assertions for the first sample.
- [ ] Add a config-validation check to CI that does not call live model providers, if supported by the pinned Promptfoo CLI; otherwise validate by parsing the YAML and executing the local adapter against a fixture provider.
- [ ] Run only the non-provider validation command and confirm model keys are not consulted; then update maturity text to call this an eval example rather than verified behavior until the live gate is run.

### Task 3: Resolve base and candidate prompt snapshots safely

**Files:**
- Modify: `.github/workflows/opf-check.yml`
- Create: `scripts/prepare_promptfoo_pair.py` only if shell/Git steps cannot safely express the operation.
- Modify: `packages/python/tests/test_eval_report.py` or add workflow fixture coverage.

- [ ] Add workflow contract tests asserting pull requests use `github.event.pull_request.base.sha`, trusted `workflow_dispatch` runs accept an explicit `base-ref`, candidate is the checked-out commit, both run with the same config/provider matrix, neither uses a mutable remote channel as baseline, and the eval job targets the protected `prompt-eval` environment.
- [ ] Run the workflow contract test and verify it fails before adding the eval job.
- [ ] Implement an eval job gated by `run-eval` and protected by environment `prompt-eval`; require environment reviewers before any provider secret becomes available. Add a trusted `workflow_dispatch` path with inputs for `run-eval`, `base-ref`, and `block-on-regression`; pull requests derive `base-ref` from the PR event. Use `git archive <base-ref> <prompt-file>` into `$RUNNER_TEMP`, keep the candidate at the checked-out path, and set `OPF_PROMPT_FILE` separately for each Promptfoo run. Reject a missing base file or candidate file with an explicit error.
- [ ] Pin Node runtime and Promptfoo CLI version. Run `promptfoo eval --no-cache --no-share --output <temp-json> -c <eval-config>` once for each side; capture nonzero outcomes while allowing the summarizer to emit a regression report.
- [ ] If the event is from a fork or required environment secrets are unavailable, write an explicit `skipped_no_credentials` summary and do not invoke Promptfoo. Never forward ordinary repository secrets to PR-controlled eval code.
- [ ] Run YAML/workflow tests and test the pair preparation against a temporary Git repository with a changed prompt file.

### Task 4: Publish a sanitized comparison summary

**Files:**
- Modify: `.github/workflows/opf-check.yml`
- Modify: `scripts/compare_promptfoo_results.py`
- Modify: `packages/python/tests/test_eval_report.py`

- [ ] Add tests asserting the report lists per-case status/score deltas and aggregate regression/recovery counts without text from prompts, vars, outputs, config, assertion reasons, or errors.
- [ ] Add a file-size and schema guard that rejects unexpected Promptfoo JSON versions rather than silently producing a partial comparison.
- [ ] Append the sanitized report to `$GITHUB_STEP_SUMMARY`; upload only the sanitized comparison JSON as an artifact when artifact upload is available and configured.
- [ ] Delete baseline and candidate raw result files at the end of the job, including on failures where possible; never enable Promptfoo share by default.
- [ ] Run synthetic regression/recovery fixtures end to end and confirm a valid regression marks the eval job failed only when `block-on-regression` is true.

### Task 5: Document opt-in, cost, and data handling

**Files:**
- Modify: `README.md`
- Modify: `packages/python/README.md`
- Modify: `docs/production-readiness.md`

- [ ] Document that `run-eval` defaults false, provider keys belong only in protected environment `prompt-eval`, reviewer approval is required, fork PRs skip the model job, and the same suite is run twice.
- [ ] Explain that provider calls may cost money and that model grading is excluded from the default sample unless explicitly configured.
- [ ] Document report states and exact limits: comparable provider/test matrix required; nondeterminism remains; ungraded rows are not passes; source diff alone does not establish behavior quality.
- [ ] Document that raw eval files are ephemeral and sanitized summaries omit prompt text, inputs, outputs, and detailed error payloads.

## Acceptance

- A fixture-based test proves regression/recovery classification against the pinned Promptfoo output format.
- Base and candidate runs use identical eval inputs except for prompt source.
- Default workflow performs no provider calls; fork PRs never receive provider credentials.
- The uploaded report is sanitized and identifies missing/mismatched baselines explicitly.
- A deliberate known regression is detected in an external pilot before eval is marked as a blocking release gate.

## Primary reference

- Promptfoo output schema and privacy characteristics: https://www.promptfoo.dev/docs/configuration/outputs/
