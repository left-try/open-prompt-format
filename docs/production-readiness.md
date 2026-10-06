# Production readiness

Status (2026-10-06): local release, offline bundle loading, promotion/rollback, and same-channel conflict behavior are exercised. The Langfuse publish/read path passed against a self-hosted Langfuse v4 test instance. Hosted-instance behavior, deployment-specific limits, and broader production operations remain unverified.

The v0.3 specification, compatibility reports, repository scanner, migration adapters, and the new init/check/diff workflows are experimental. Their behavior requires verification before production use. Do not interpret older evidence below as verification of these additions.

The GitHub consumer workflow and `opf init --github` are also experimental. The generated workflow is pinned to `stovo-team/open-prompt-format@v0.2.0` and installs `open-prompt-format==0.2.0`; it is not usable by consumer repositories until that GitHub ref and Python package are published. The package release is currently held until npm publishing and repository metadata are ready. Run the workflow contract test locally before release; do not create or push the release tag as part of this code change.

The Promptfoo sample is an eval example, not verified behavior. CI parses its four test cases and deterministic assertions without calling model providers. Live behavior, provider compatibility, and cost remain unverified until the opt-in paired eval runs against real providers. Its regex checks are guardrails for this sample, not a universal quality score.

The paired eval job is disabled unless `run-eval` is explicitly true. Consumer repositories must create a protected `prompt-eval` GitHub Environment with required reviewers and environment-scoped provider keys; this approval is required because caller-controlled eval configuration executes code while keys are available. Fork PRs are skipped. Each run calls every configured provider twice, and Promptfoo’s pinned `0.123.1` output is held temporarily before a sanitized comparison is written to the step summary. Raw outputs, logs, and pair files are removed. The sanitized report omits prompt text, input variables, model outputs, and detailed error payloads. Its states are `unchanged`, `regression`, `improved`, `changed`, `error`, and `ungraded`; mismatched test/provider/prompt matrices or missing baseline files stop comparison. Errors always fail; regressions fail only with `block-on-regression: true`. Ungraded outcomes remain ungraded. Model nondeterminism requires human review of regression signals, and a source diff alone does not establish behavior quality. The initial sample checks config structure locally and has no live behavior evidence.

Integration requests use explicit metadata and do not collect repository data automatically. Fixture submission is separate and requires public-use permission. Use the [triage rubric](integration-request-triage.md) to weigh repeated demand, migration blockers, portability, maintainability, and rights. The deferred `okf-aget` mention remains unprioritized until its identity and workflow are known.

## Starter template publication gate

`examples/starter-template/` is a source example inside this repository; GitHub cannot mark a subdirectory as a template repository. Before offering one-click template creation:

1. Resolve the public repository owner and package metadata, then publish the `v0.2.0` reusable-workflow ref and Python package required by the generated caller workflow.
2. Copy the contents of `examples/starter-template/` into a dedicated starter repository and verify every relative path and issue-form link there.
3. Run the clean-checkout Python install, `opf check`, `opf validate-collection`, and `opf verify-all` with no provider credentials. Keep the optional eval disabled in the default workflow.
4. In the dedicated repository, open **Settings → General → Template repository** and enable the setting. This must be done manually after the checks; this code does not change GitHub repository settings.
5. Use GitHub's **Use this template** flow once and confirm the generated repository can finish the documented quick start without maintainer help.

The checked-in example passed its local no-secret smoke test, but the reusable workflow/package release is still pending and no separate starter repository exists. Do not describe it as a one-click template until all five checks pass.

## Evidence in this repository

The Python CLI includes `opf init`, `opf check`, and `opf diff`. Static safety checks are advisory only. Prefix comparison describes cacheability evidence and never confirms a provider cache hit.

- Python integration tests create a temporary Git repository, release a prompt, promote a channel, render the tagged source after the working file changes, export and reload a bundle, and reject altered bundles, moved tags, and bad channel digests.
- The Jinja test covers a static include and rejects a dynamic include during release.
- The Langfuse test uses an in-process HTTP substitute to check repeat publication and remote bundle loading without external credentials.
- Python and TypeScript assert the same bundle digests for an ordinary prompt and a Unicode prompt with a numeric filename.
- TypeScript tests cover local channel resolution, export loading, receipts, and remote digest pinning. The real Git tag resolution test passed in an unsandboxed local run (`OPF_TEST_REAL_GIT=1 npm test`, 9/9 tests). CI is configured to run that same path.
- The Python wheel builds and imports from an isolated target directory. The npm package dry run contains `dist/index.js`, `dist/registry.js`, their declarations, and the package metadata.

Manual acceptance checks on 2026-10-06 also verified:

- `opf export` output loads and renders from a separate application artifact directory with no `.git` metadata.
- Two branches promoting different versions to the same channel from the same base produce a Git merge conflict. Promoting the prior version restores the channel; production use still depends on protecting the deployment branch and reviewing promotion commits.
- The real Langfuse smoke script created a unique prompt in a self-hosted v4 instance, repeated publication to confirm idempotency, and loaded/rendered it through Python and TypeScript using the expected bundle digest. It called no model provider and required no OpenAI API key. The test prompt remains in the test project.

Run the local checks:

```sh
python -m pip install -e 'packages/python[jinja]'
python -m unittest discover -s packages/python/tests -v
opf verify-all --registry opf.yaml
cd packages/typescript
npm install
npm test
```

## Deployment rule

Production code should load `channel="production"` or an exact release version, then retain the `bundle_digest` in the render receipt. A packaged application without `.git` should load an exported bundle. If it loads from Langfuse, pass the expected digest from deployment configuration so a remote label change cannot silently change the selected source.

The team must push release tags together with promotion commits. CI checks out full Git history and runs `opf verify-all`; in an application repository, protect `opf/*` tags and review changes to `opf.yaml` through the normal pull-request process.

## Remaining external gate

The Langfuse smoke check verifies API compatibility for one local self-hosted deployment. Hosted Langfuse configurations, provider size limits, sustained operation, and deployment-specific authentication or network policies still need validation before relying on them in production. The smoke script is opt-in and leaves its uniquely named prompt in the target project.

The migration adapters need automated coverage and review against real anonymized prompt examples. The current source matrix and known limits are documented in [the migration guide](../examples/migration/README.md). OpenAI import accepts only the project's offline `openai-prompt-snapshot/1` shape; it is not a vendor API export format.

Repository-scale adoption remains unverified until the adapters and findings are exercised against sanitized prompt and workflow examples from both mature repositories that motivated this work. Current tests use synthetic fixtures; they demonstrate parser and preservation behavior, not compatibility with those repositories' complete agent workflows. Preserve existing renderer execution where needed, review all `adapter_runtime`, `unsupported`, and `data_loss` findings, and migrate incrementally after comparing outputs in the source runtime.

To repeat the Langfuse check, use a non-production instance and set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` for that instance before running `PYTHONPATH=packages/python/src python3 scripts/langfuse_smoke.py --publish`. The adapter stores the canonical bundle in Langfuse prompt config. Langfuse prompt publication and retrieval do not invoke a model; configure a model-provider key only for a separate test that actually calls a model.

The Python `promote` command currently rewrites YAML formatting and comments. Review the generated `opf.yaml` diff before committing a promotion.

## GitHub consumer workflow release gate

Before recommending `opf init --github` to external repositories:

- confirm `stovo-team/open-prompt-format` is the final repository owner and the `v0.2.0` ref points to a reviewed commit containing `.github/workflows/opf-check.yml`;
- publish `open-prompt-format==0.2.0` to PyPI and verify a clean install;
- run a clean consumer-repository test that invokes the reusable workflow with read-only `contents` permission and full Git history;
- verify missing registries skip release verification while malformed registries and digest mismatches fail;
- keep model credentials out of this no-secret workflow.
