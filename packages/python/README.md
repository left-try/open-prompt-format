# Open Prompt Format for Python

Load and render [OPF](../../README.md) prompt files from Python.

## Install

Version 0.2.0 is published on PyPI:

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
opf scan .
opf migrate inspect prompts/legacy.md --role system
opf migrate apply prompts/legacy.md --role system
```

Migration inspection is read-only. Apply writes only generated paths that are absent or already identical. Supported adapter inputs are intentionally narrow; consult the [migration guide](../../examples/migration/README.md) for limits and compatibility findings.

Licensed under MIT; see [LICENSE](LICENSE).

## Git-backed registry

```python
from opf import Registry

registry = Registry.local("opf.yaml")
prepared = registry.get("support.reply", channel="production").render({"customer_message": "Hello"})
print(prepared.messages)
print(prepared.receipt)
```

The registry also supports `release`, `promote`, `verify`, `verify-all`, and `export` through the `opf` CLI. Run `opf verify-all --registry opf.yaml` in CI after fetching Git tags. `Registry.from_bundle("prompt.json")` loads an exported release without Git. Existing Markdown/Jinja projects can use the `jinja2` renderer with `pip install 'open-prompt-format[jinja]'`. The model is selected by the application and can be attached with `prepared.call_receipt(provider=..., model=...)`. See the [registry contract](../../spec/REGISTRY.md).

After `opf publish ID@VERSION --to langfuse`, `Registry.langfuse().get(ID, version=VERSION)` explicitly loads the verified remote bundle using Langfuse credentials from the environment.


## CLI onboarding and review

The Python distribution includes the `opf` CLI. `opf init . --id support.reply` creates a sample prompt, registry entry, and an OPF-owned guidance block in `AGENTS.md`. Add `--github` to also create a read-only GitHub Actions workflow that calls the published reusable OPF check workflow. It does not replace existing prompt files or content outside its markers; any conflicting target causes init to stop without partial writes. The generated workflow requires the matching OPF GitHub release and Python package to be published. `opf check .` validates discovered OPF prompts and registry references locally; `--format json` and `--strict` are available for CI.

Use `opf diff ID --base VERSION_OR_CHANNEL --target VERSION_OR_WORKING_TREE` to inspect source changes and shared prefix evidence. A stable prefix is only a cacheability candidate; it cannot establish a provider cache hit. Heuristic injection findings need human review and do not guarantee safety.

The reusable GitHub workflow has an optional paired Promptfoo job (`run-eval`, default false). It requires a protected `prompt-eval` environment with required reviewers and environment-scoped provider keys. It runs the same eval config against the PR base prompt and candidate prompt, writes a sanitized comparison to the workflow summary, skips forks, and deletes raw files. Each comparison makes two sets of provider calls and can cost money. `block-on-regression` also defaults false; ungraded rows are never counted as passes. Report states are `unchanged`, `regression`, `improved`, `changed`, `error`, and `ungraded`; provider/test/prompt matrix mismatches or missing base files abort comparison. Nondeterminism means a measured regression needs review, and a source diff by itself does not establish behavior quality. The included sample cases validate config wiring only; live model behavior is not verified by ordinary CI.
