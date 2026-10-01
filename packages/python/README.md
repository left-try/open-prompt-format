# Open Prompt Format for Python

Load and render [OPF](../../README.md) prompt files from Python.

## Install

```sh
python -m pip install open-prompt-format
```

For the current source checkout, run `python -m pip install ./packages/python` from the repository root.

## Use

```python
from opf import load_by_id

prompt = load_by_id("support.reply", "prompts")
messages = prompt.render(customer_message="My order is late.")
print(prompt.source_digest)
```

`messages` is an ordered list of dictionaries with `role` and `content` strings. See the [syntax proposal](../../spec/SYNTAX.md) for file structure and validation rules.

## CLI

```sh
opf validate prompts/support.reply.md
opf validate-collection prompts
opf render prompts/support.reply.md --input customer_message="My order is late."
```

Licensed under MIT; see [LICENSE](LICENSE).
