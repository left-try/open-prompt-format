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
