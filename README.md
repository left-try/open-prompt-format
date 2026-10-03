# Open Prompt Format

**A repo-first way to write, version, load, and evaluate prompts.** Keep each prompt in one readable file, commit it with your application, and load it from Python or TypeScript.

[Project site](https://left-try.github.io/open-prompt-format/) · [Syntax proposal](spec/SYNTAX.md) · [OPF v0.3 draft](spec/SYNTAX-0.3.md) · [Release setup](PUBLISHING.md)

> Early proposal and experimental libraries. OPF is not yet an established industry standard.

## Why OPF?

- **One source file per prompt:** metadata, inputs, and chat messages stay together.
- **Git is the source of truth:** review changes, trace releases, and roll back with normal development tools.
- **Portable output:** loaders return ordered `{ role, content }` messages for your provider client.
- **Reproducible identity:** source digests identify files; Git-tagged registry releases identify complete prompt bundles.
- **Bring your own tools:** use Promptfoo for evals; provider and registry integrations remain optional.

## A prompt file

```md
---
format: opf/0.2
id: support.reply
description: Draft a response to a customer support message.
tags: [support, customer-facing]
inputs:
  customer_message:
    type: string
    required: true
---

## system
You help customers with order questions. Be concise, kind, and factual.
Do not invent order details.

## user
{{ customer_message }}
```

The message and input rules are shared by `opf/0.2` and the experimental [v0.3 draft](spec/SYNTAX-0.3.md). v0.3 adds namespaced extension records and compatibility reports; older prompts retain their existing interpretation. Frontmatter schemas are available for [v0.1](spec/frontmatter.schema.json), [v0.2](spec/frontmatter-0.2.schema.json), and [v0.3](spec/frontmatter-0.3.schema.json).

## Start and check a prompt project

The Python package also installs the `opf` command. Create a starter prompt, registry entry, and OPF guidance in `AGENTS.md`:

```sh
python -m pip install ./packages/python
opf init . --id support.reply
opf check .
```

`opf init` preserves existing files and only manages its marked section in `AGENTS.md`; use `--agents no` to skip agent guidance. `opf check --format json` is suitable for CI. Safety findings are heuristic advisories, not a prompt-injection guarantee.

Compare a release with the current working tree:

```sh
opf diff support.reply --base 1.0.0 --target working-tree
```

The report identifies a stable shared message prefix as evidence that a provider cache may be usable. It does not claim a cache hit; only provider runtime signals can confirm that.

## Find and migrate existing prompts

The Python CLI can scan a repository and preview a conversion locally. A preview does not write files:

```sh
opf scan .
opf migrate inspect prompts/legacy.md --role system --format json
opf migrate apply prompts/legacy.md --role system
```

The first adapters cover plain Markdown, simple Jinja, a documented offline OpenAI snapshot JSON shape, LangChain serialized prompt templates, static CrewAI templates, and literal AutoGen `system_message` values. Framework runtime behavior, dynamic expressions, tools, and orchestration are not converted automatically. Review compatibility findings before applying; `--strict` refuses plans that drop or require manual work. See [migration examples and limits](examples/migration/README.md).

## Install

The packages are prepared for their first release. Until they are published, install from a clone:

### Python

```sh
python -m pip install ./packages/python
```

After publication:

```sh
python -m pip install open-prompt-format
```

### TypeScript / JavaScript

Build the package from the clone:

```sh
cd packages/typescript
npm install
npm run build
```

Then add the local package to your application with `npm install /path/to/open-prompt-format/packages/typescript`.

After publication:

```sh
npm install open-prompt-format
```

## Load and render

Python loads a file directly or looks up an ID in a prompt directory:

```python
from opf import load_by_id

prompt = load_by_id("support.reply", "examples")
messages = prompt.render(customer_message="My order is late.")

print(messages)
# [
#   {"role": "system", "content": "You help customers ..."},
#   {"role": "user", "content": "My order is late."},
# ]
print(prompt.source_digest)  # sha256:<64 lowercase hex characters>
```

TypeScript offers the same operations:

```ts
import { loadById } from "open-prompt-format";

const prompt = await loadById("support.reply", "examples");
const messages = prompt.render({ customer_message: "My order is late." });
console.log(prompt.sourceDigest);
```

Your application passes `messages` to its provider SDK. OPF does not select a model or silently translate provider-specific settings. v0.1 supports string inputs and simple `{{ variable }}` substitution; unsupported template expressions fail validation.

## Local registry

Add one `opf.yaml` to your repository. The included [example config](opf.yaml) maps `support.reply` to the Markdown file. Load the current draft or an exact Git release:

```python
import os
from opf import Registry

registry = Registry.local("opf.yaml")
prepared = registry.get("support.reply").render({"customer_message": "My order is late."})
messages = prepared.messages
receipt = prepared.call_receipt(provider="openai", model=os.environ["LLM_MODEL"], parameters={"temperature": 0.2})
```

```ts
import { Registry } from "open-prompt-format";

const registry = await Registry.local("opf.yaml");
const prepared = (await registry.get("support.reply")).render({ customer_message: "My order is late." });
const messages = prepared.messages;
const receipt = prepared.callReceipt({ provider: "openai", model: process.env.LLM_MODEL!, parameters: { temperature: 0.2 } });
```

The model comes from your application or deployment config. The receipt records its resolved value; OPF does not require a model in the prompt file.

After committing `opf.yaml` and the prompt, create and promote a release:

```sh
opf release support.reply --version 1.0.0
opf promote support.reply@1.0.0 --channel production
git add opf.yaml && git commit -m 'Promote support.reply 1.0.0'
opf verify support.reply --channel production
opf verify-all --registry opf.yaml
opf export support.reply@1.0.0 --output support.reply.json
```

The Python and TypeScript SDKs can load the exported bundle without Git. The Python SDK also wraps existing `.md`/`.j2` files with `renderer: jinja2` when installed with `open-prompt-format[jinja]`; TypeScript explicitly rejects Jinja rendering. Jinja migration can preserve a source as a local registry entry when it cannot prove a core conversion.

To publish a verified OPF release to Langfuse, inspect the mapping first:

```sh
opf publish support.reply@1.0.0 --to langfuse --dry-run
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
opf publish support.reply@1.0.0 --to langfuse
```

The adapter checks for an existing `opf-v1.0.0` label, verifies matching remote content, and does not move Langfuse's `production` label. `LANGFUSE_BASE_URL` selects a region or self-hosted instance. Jinja2 composites and the `developer` role are rejected because this adapter cannot preserve their behavior.

The adapter also stores the canonical OPF bundle in Langfuse's prompt config. Choose the remote source explicitly when your application needs it:

```python
prepared = Registry.langfuse().get("support.reply", version="1.0.0").render({"customer_message": "Hello"})
```

```ts
const remote = Registry.langfuse();
const prepared = (await remote.get("support.reply", { version: "1.0.0" })).render({ customer_message: "Hello" });
```

Both SDKs verify the bundle digest and compare Langfuse's chat template with the stored source. Choosing a remote registry never happens automatically from environment variables.

## Promptfoo evals

The example config evaluates the checked-in prompt against OpenAI and Anthropic through a small local adapter. The prompt body is not copied into the eval config.

```sh
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
cd packages/typescript && npm install && npm run build
cd ../..
npx promptfoo eval -c evals/promptfooconfig.yaml
```

Model requests may incur provider charges. Change the providers and test cases in [the Promptfoo config](evals/promptfooconfig.yaml) to match your setup.

## Version and digest

In `opf/0.1`, `version` is a human-managed file-level SemVer. In `opf/0.2`, the file omits `version`; `opf release` binds a SemVer to a committed bundle using an annotated Git tag and SHA-256 digest. `source_digest` / `sourceDigest` still identifies one normalized source file. See the [registry contract](spec/REGISTRY.md) for exact rules.

## Development

```sh
python -m pip install -e packages/python
python -m unittest discover -s packages/python/tests -v

cd packages/typescript
npm install
npm test
npm run build
```

GitHub Actions runs the Python and TypeScript checks on pushes and pull requests. More detail and the remaining roadmap are in [PLAN.md](PLAN.md).

## Project status

This repository contains experimental v0.1/v0.2 readers, a v0.3 draft, and local registry and migration implementations. The live Promptfoo eval and independent implementations have not yet been run. The format may change before a stable release; migration adapters are intentionally limited and have not been independently validated.

The [registry RFC](docs/registry-rfc.md) describes the wider direction. The local config, Git releases, channels, Python Jinja wrapper, portable export, and initial Langfuse publish/read adapter are implemented. Live remote publication and other provider adapters remain pending.

The [production readiness note](docs/production-readiness.md) records the checks that now run in CI and the remaining live Langfuse gate.

## License

The software and specification are released under the [MIT License](LICENSE).
