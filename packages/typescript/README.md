# Open Prompt Format for TypeScript

Load and render [OPF](../../README.md) prompt files from TypeScript and JavaScript.

## Install

```sh
npm install open-prompt-format
```

For the current source checkout, run `npm install` and `npm run build` in this directory, then install the directory into your application.

## Use

```ts
import { loadById } from "open-prompt-format";

const prompt = await loadById("support.reply", "prompts");
const messages = prompt.render({ customer_message: "My order is late." });
console.log(prompt.sourceDigest);
```

`messages` is an ordered array with `role` and `content` strings. See the [syntax proposal](../../spec/SYNTAX.md) for file structure and validation rules.

Licensed under MIT; see [LICENSE](LICENSE).

## Git-backed registry

```ts
import { Registry } from "open-prompt-format";

const registry = await Registry.local("opf.yaml");
const prepared = (await registry.get("support.reply", { channel: "production" })).render({ customer_message: "Hello" });
console.log(prepared.messages, prepared.receipt);
```

`Registry.fromBundle("prompt.json")` loads a portable exported release without Git. TypeScript supports the OPF renderer; Python handles optional Jinja2 templates. Model selection stays in your application. See the [registry contract](../../spec/REGISTRY.md).

After publication, `await Registry.langfuse().get("support.reply", { version: "1.0.0" })` explicitly loads the remote canonical bundle using Langfuse credentials from the environment.
# Experimental format and migration note

The TypeScript library reads the experimental `opf/0.3` core and reports extension compatibility. Repository scanning and legacy migration commands currently live in the Python CLI (`opf scan` and `opf migrate`); the TypeScript package does not yet provide migration adapters.
