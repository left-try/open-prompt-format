# Repository and release setup

This file records the intended public metadata and the one-time account setup needed to make releases work.

## Public project metadata

- **Repository:** `left-try/open-prompt-format`
- **Description:** A repo-first prompt format with Python and TypeScript loaders.
- **Homepage:** <https://left-try.github.io/open-prompt-format/>
- **License:** MIT
- **Topics:** `prompt-engineering`, `llm`, `prompt-format`, `prompt-management`, `python`, `typescript`, `promptfoo`, `developer-tools`
- **PyPI distribution:** `open-prompt-format`
- **npm package:** `open-prompt-format` (public)

## First-time hosting setup

1. Create the public GitHub repository `left-try/open-prompt-format` and push this project.
2. In **Settings → Pages**, select **GitHub Actions** as the build and deployment source. The workflow in `.github/workflows/pages.yml` publishes `site/`.
3. In **Settings → Actions → General**, allow GitHub Actions to create Pages deployments. The workflow has the minimum `pages: write` and `id-token: write` permissions for deployment.
4. Confirm the public description, homepage, and topics above on the repository.

## One-time package publisher setup

The release workflow publishes both packages when a `v*` tag is pushed. Configure trusted publishing before the first release; the workflow deliberately uses OIDC rather than long-lived registry tokens.

### PyPI

Create the `open-prompt-format` project on PyPI (or reserve its publisher before the first upload), then configure a **Trusted Publisher** with:

- Owner: `left-try`
- Repository: `open-prompt-format`
- Workflow: `publish.yml`
- Environment: `pypi`

### npm

Create/reserve the public `open-prompt-format` package under the appropriate npm account or organization. In package settings, configure a **Trusted Publisher** for GitHub Actions with:

- Organization/user: `left-try`
- Repository: `open-prompt-format`
- Workflow: `publish.yml`
- Environment: `npm`

Use a current npm account with permission to publish that package name. npm trusted publishing also emits provenance through the `npm publish --provenance` command.

## Release procedure

1. Update the version in `packages/python/pyproject.toml` and `packages/typescript/package.json` to the same release version.
2. Review the changes and ensure CI passes on the commit to release.
3. Create and push the matching tag, for example:

   ```sh
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. The tag workflow reruns CI, builds both distributions, then publishes to PyPI and npm.

Do not reuse a published version. Registry releases are immutable in normal publishing workflows; use a new patch version to correct a release.

## Before announcing the first release

- Verify the public repo URL, Pages deployment, and package names are available and owned by the intended account.
- Configure both trusted publishers and environments exactly as above.
- Run the release workflow against a deliberate version tag only after the package metadata and APIs are ready.
- Treat v0.1 as an early proposal: the format has not yet been validated by independent implementations.
