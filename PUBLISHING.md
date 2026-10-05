# Repository and release setup

This file records the intended public metadata and the one-time account setup needed to make releases work.

## Current release readiness (2026-10-05)

- **PyPI:** version `0.2.0` published successfully through the trusted publisher on 2026-10-05.
- **npm trusted publisher:** not ready; the maintainer reports setup problems.
- **Repository metadata:** package repository URLs now point to `stovo-team/open-prompt-format`.
- **npm package:** not published. Run the release workflow with `publish_python=false` and `publish_npm=true` after its Trusted Publisher is configured.

## Public project metadata

- **Repository:** `stovo-team/open-prompt-format`
- **Description:** A repo-first prompt format with Python and TypeScript loaders.
- **License:** MIT
- **Topics:** `prompt-engineering`, `llm`, `prompt-format`, `prompt-management`, `python`, `typescript`, `promptfoo`, `developer-tools`
- **PyPI distribution:** `open-prompt-format`
- **npm package:** `open-prompt-format` (public)

## One-time package publisher setup

The release workflow publishes both packages when a `v*` tag is pushed. For a registry that is not ready yet, use `workflow_dispatch` to select one package at a time. The workflow deliberately uses OIDC rather than long-lived registry tokens.

### PyPI

Create the `open-prompt-format` project on PyPI (or reserve its publisher before the first upload), then configure a **Trusted Publisher** with:

- Owner: `stovo-team`
- Repository: `open-prompt-format`
- Workflow: `publish.yml`
- Environment: `pypi`

### npm

Create/reserve the public `open-prompt-format` package under the appropriate npm account or organization. In package settings, configure a **Trusted Publisher** for GitHub Actions with:

- Organization/user: `stovo-team`
- Repository: `open-prompt-format`
- Workflow: `publish.yml`
- Environment: `npm`

Use a current npm account with permission to publish that package name. npm trusted publishing also emits provenance through the `npm publish --provenance` command.

## Release procedure

1. Update the version in `packages/python/pyproject.toml` and `packages/typescript/package.json` to the same release version. Never republish a version that is already present in either registry.
2. Review the changes and ensure CI passes on the commit to release.
3. Create and push the matching tag, for example:

   ```sh
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. The tag workflow reruns CI, builds both distributions, then publishes to PyPI and npm.

Package tags use `vX.Y.Z` and trigger PyPI/npm publishing. Prompt release tags use `opf/<id>/vX.Y.Z`; they are created by `opf release` and do **not** trigger package publishing. Push prompt tags together with their `opf.yaml` promotion commits. Do not reuse a published version; use a new patch version to correct a package release.

## Before announcing the first release

- Verify the public repo URL, Pages deployment, and package names are available and owned by the intended account.
- Configure both trusted publishers and environments exactly as above.
- Run the release workflow against a deliberate version tag only after the package metadata and APIs are ready.
- Treat v0.2 as experimental: the local registry has integration coverage, but the Langfuse adapter still needs a live-service check and the format has not been validated by independent implementations. See [production readiness](docs/production-readiness.md).
- Before offering a starter repository, publish the pinned reusable-workflow ref and PyPI version, then copy `examples/starter-template/` into a dedicated repository and manually enable **Settings → General → Template repository** only after the [starter template publication gate](docs/production-readiness.md#starter-template-publication-gate) passes.
