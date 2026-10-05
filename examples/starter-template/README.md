# OPF starter project

This small example keeps one prompt in Git, validates it locally, and shows where an optional paid eval fits. The default quick start makes no model-provider calls.

## Try it locally

From an OPF source checkout, copy this folder to a clean directory and install the local Python package:

```sh
python -m pip install ./packages/python
cp -R examples/starter-template /tmp/starter-project
cd /tmp/starter-project
opf check . --registry opf.yaml
opf validate-collection prompts
opf verify-all --registry opf.yaml
```

After the package release gate is complete and you create a repository from the published template, install `open-prompt-format` from PyPI instead of the local path above.

The generated GitHub workflow calls the reusable [OPF checks workflow](../../.github/workflows/opf-check.yml) with read-only repository permission. It needs the published `v0.2.0` ref and package; until release prerequisites are complete, use the local commands above. If `.github/workflows/opf.yml` already exists, `opf init --github` safely refuses to overwrite it.

## Release and roll back

Commit a reviewed prompt change, then create a Git-backed release and promote it:

```sh
git add prompts/support.reply.md
git commit -m "Update support reply prompt"
opf release starter.support.reply --version 1.0.0
git push origin main --tags
opf promote starter.support.reply@1.0.0 --channel production
git add opf.yaml && git commit -m "Promote support reply 1.0.0"
opf verify starter.support.reply --channel production
```

To roll back, promote the previous verified version to `production`, commit the registry change, and verify again:

```sh
opf promote starter.support.reply@0.9.0 --channel production
git add opf.yaml && git commit -m "Roll back support reply"
opf verify starter.support.reply --channel production
```

## Optional model eval

The four sample cases illustrate deterministic checks only; they do not establish live model quality. The included workflow exposes a manual `run-eval` input, default false. Add provider IDs to `evals/promptfooconfig.yaml`, then configure the `prompt-eval` GitHub Environment with required reviewers and matching provider keys. The paired eval calls each provider twice and may cost money. Pull request evals require an explicit workflow change to set `run-eval: true` in the reusable-workflow call; this avoids accidentally enabling paid calls for every PR. See [the eval setup](../../README.md#optional-paired-promptfoo-eval) and [production readiness notes](../../docs/production-readiness.md).

## Request an integration

Use the [Adapter or migration request form](https://github.com/stovo-team/open-prompt-format/issues/new?template=adapter-request.yml) to report a source format, framework, and blocker. Do not include private prompts, customer data, credentials, or proprietary content. Sharing a sanitized fixture is a separate, optional [fixture contribution form](https://github.com/stovo-team/open-prompt-format/issues/new?template=sanitized-fixture.yml) with a license acknowledgement.
