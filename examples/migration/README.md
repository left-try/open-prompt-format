# Local prompt migration

This example shows the no-network workflow. The scanner only reports likely sources; inspection builds a plan without writing; apply writes generated files only after checking all destination paths.

```sh
python -m pip install -e packages/python
opf scan examples/migration
opf migrate inspect examples/migration/legacy_prompt.j2 --id help.answer --role system --format json
opf migrate apply examples/migration/legacy_prompt.j2 --id help.answer --role system --register
```

For this Jinja example, the role-heading Markdown adapter preserves the two explicit roles. Both `# role` and `## role` are accepted for all four OPF roles; generated prompts use canonical `## role`. Simple `{{ name }}` interpolation can map to OPF core, with a warning that whitespace control may differ. Jinja filters and control blocks are runtime-dependent; dynamic includes need manual work. A prompt can remain loadable through the Jinja renderer without becoming portable core OPF.

## Reading compatibility reports

```sh
opf compat migrated.opf.md
opf check . --format json
```

Findings use these categories: `portable` (valid core behavior, possibly with a canonicalization recommendation), `preserved_resource` (source data is retained but not interpreted by core), `adapter_runtime` (the legacy renderer remains required), `unsupported` (manual migration is needed), and `data_loss` (apply is blocked). For example, `heading.noncanonical.single_hash` recommends changing `# system` to `## system`; this is informational and does not block `--strict`.

An informational heading report looks like this:

```text
opf/0.3 -> opf-core (lossless=True, can_apply=True)
INFO heading.noncanonical.single_hash [preserved] [portable]: single-hash role heading is accepted; use '## system' as the canonical form
  Recommendation: Use '## system' for canonical OPF role headings.
```

When an input value cannot be preserved in the target's JSON-compatible extension record, inspect the exact `data_loss` code and report first. Apply only after accepting that named omission explicitly:

```sh
opf migrate apply prompts/legacy.md --register --accept-loss 'metadata.value.not_json_compatible[created_at]'
```

Accepted loss codes are written to the migration manifest. This option does not bypass unsupported behavior or unrelated errors. Review both the generated prompt and its preserved extension/resource records; preservation keeps associated structure and values, but does not make framework-specific data portable or executable in a generic core renderer.

For an incremental migration, first inspect and keep the existing framework renderer active; then preserve associated data and convert only core-compatible messages; compare rendered output in the source runtime; finally switch consumers to the OPF core only after runtime-dependent and unsupported findings are resolved.

## Supported input boundaries

- **Markdown:** explicit `#` or `##` headings for `system`, `developer`, `user`, and `assistant` are preserved. Plain text needs `--role`; generated output uses `##`.
- **Jinja:** only the limited simple variable form is eligible for core conversion; advanced syntax stays tied to the Python Jinja renderer.
- **OpenAI:** import accepts the local `openai-prompt-snapshot/1` JSON shape. It is not an API export reader and makes no network call. Messages and variables map to OPF core; tools, output format, and model settings remain in a required `com.openai.responses` extension.
- **LangChain:** static serialized `PromptTemplate` and role/content `ChatPromptTemplate` mappings are supported. Only simple declared `{name}` fields convert to `{{ name }}`. Dynamic Python constructors, partials, format specs, and nested format expressions need manual migration.
- **CrewAI:** static `system_template` and `prompt_template` strings are supported. Agent role/goal/backstory metadata can be retained as optional `com.crewai.agent` data; orchestration and tools do not transfer.
- **AutoGen:** exactly one literal string `system_message` in Python source is extracted using Python's AST. The module is never imported or executed. Dynamic values, multiple agents, tools, and conversation control flow need manual migration.

`--strict` refuses a migration with dropped or manual findings. Review the generated prompt and the report before committing. To register the result, `--register` updates the selected `opf.yaml` and `.opf/migrations.yaml`; it refuses an already registered ID or conflicting output files.
