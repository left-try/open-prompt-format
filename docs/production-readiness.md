# Production readiness

Status: local release workflow and both SDKs' real Git paths are exercised; external publication still needs a live service check.

The v0.3 specification, compatibility reports, repository scanner, and initial local migration adapters are experimental additions. This implementation turn did not run automated tests or builds. Do not interpret the older evidence below as verification of the v0.3 and migration changes.

## Evidence in this repository

- Python integration tests create a temporary Git repository, release a prompt, promote a channel, render the tagged source after the working file changes, export and reload a bundle, and reject altered bundles, moved tags, and bad channel digests.
- The Jinja test covers a static include and rejects a dynamic include during release.
- The Langfuse test uses an in-process HTTP substitute to check repeat publication and remote bundle loading without external credentials.
- Python and TypeScript assert the same bundle digests for an ordinary prompt and a Unicode prompt with a numeric filename.
- TypeScript tests cover local channel resolution, export loading, receipts, and remote digest pinning. The real Git tag resolution test passed in an unsandboxed local run (`OPF_TEST_REAL_GIT=1 npm test`, 9/9 tests). CI is configured to run that same path.
- The Python wheel builds and imports from an isolated target directory. The npm package dry run contains `dist/index.js`, `dist/registry.js`, their declarations, and the package metadata.

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

The migration adapters need automated coverage and review against real anonymized prompt examples. The current source matrix and known limits are documented in [the migration guide](../examples/migration/README.md). OpenAI import accepts only the project's offline `openai-prompt-snapshot/1` shape; it is not a vendor API export format.

Use a non-production Langfuse project to run `PYTHONPATH=packages/python/src python3 scripts/langfuse_smoke.py` for a local preview, then set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and optionally `LANGFUSE_BASE_URL` and run the same script with `--publish`. It creates a uniquely named test prompt, repeats publication to check idempotency, and compares local and remote rendering in both SDKs. It does not delete the test prompt. The live mode has not run because no Langfuse project and credentials are available in this workspace. The adapter stores the canonical bundle in Langfuse prompt config; provider size limits and behavior must be checked against the chosen hosted or self-hosted instance before relying on it in production.

The Python `promote` command currently rewrites YAML formatting and comments. Review the generated `opf.yaml` diff before committing a promotion.
