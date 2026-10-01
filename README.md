# Open Prompt Format

**A repo-first way to write, version, load, and evaluate prompts.** Keep each prompt in one readable file, commit it with your application, and load it from Python or TypeScript.

[Project site](https://left-try.github.io/open-prompt-format/) · [Syntax proposal](spec/SYNTAX.md) · [Release setup](PUBLISHING.md)

> Early proposal and experimental libraries. OPF is not yet an established industry standard.

## Why OPF?

- **One source file per prompt:** metadata, inputs, and chat messages stay together.
- **Git is the source of truth:** review changes, trace releases, and roll back with normal development tools.
- **Portable output:** loaders return ordered `{ role, content }` messages for your provider client.
- **Reproducible identity:** each file has an explicit version and a derived SHA-256 source digest.
- **Bring your own tools:** use Promptfoo for evals; provider and registry integrations remain optional.

## A prompt file

```md
---
format: opf/0.1
id: support.reply
version: 1.0.0
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

The full rules are in the [v0.1 syntax proposal](spec/SYNTAX.md). The machine-readable frontmatter schema is [here](spec/frontmatter.schema.json).

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

`version` is a human-managed SemVer release. `source_digest` / `sourceDigest` is computed by the loaders as SHA-256 over the UTF-8 file with CRLF and bare CR normalized to LF. The digest identifies source content; it does not replace Git history or the release version.

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

This repository contains a v0.1 proposal and early Python/TypeScript implementations. Shared fixtures cover core parsing, rendering, and digest behavior. The live Promptfoo eval and independent implementations have not yet been run. The format may change before a stable release.

## License

The software and specification are released under the [MIT License](LICENSE).
