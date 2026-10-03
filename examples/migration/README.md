# Local prompt migration

This example shows the no-network workflow. The scanner only reports likely sources; inspection builds a plan without writing; apply writes generated files only after checking all destination paths.

```sh
python -m pip install -e packages/python
opf scan examples/migration
opf migrate inspect examples/migration/legacy_prompt.j2 --id help.answer --role system --format json
opf migrate apply examples/migration/legacy_prompt.j2 --id help.answer --role system --register
```

For this Jinja example, the role-heading Markdown adapter preserves the two explicit roles. Simple `{{ name }}` interpolation can map to OPF core, with a warning that whitespace control may differ. Jinja filters, control blocks, attributes, and dynamic includes are not evaluated by the migrator. Complex static Jinja can be registered with the optional Jinja renderer; dynamic dependencies require manual work.

## Supported input boundaries

- **Markdown:** explicit `## system`, `## developer`, `## user`, and `## assistant` headings are preserved. Plain text needs `--role`.
- **Jinja:** only the limited simple variable form is eligible for core conversion; advanced syntax stays tied to the Python Jinja renderer.
- **OpenAI:** import accepts the local `openai-prompt-snapshot/1` JSON shape. It is not an API export reader and makes no network call. Messages and variables map to OPF core; tools, output format, and model settings remain in a required `com.openai.responses` extension.
- **LangChain:** static serialized `PromptTemplate` and role/content `ChatPromptTemplate` mappings are supported. Only simple declared `{name}` fields convert to `{{ name }}`. Dynamic Python constructors, partials, format specs, and nested format expressions need manual migration.
- **CrewAI:** static `system_template` and `prompt_template` strings are supported. Agent role/goal/backstory metadata can be retained as optional `com.crewai.agent` data; orchestration and tools do not transfer.
- **AutoGen:** exactly one literal string `system_message` in Python source is extracted using Python's AST. The module is never imported or executed. Dynamic values, multiple agents, tools, and conversation control flow need manual migration.

`--strict` refuses a migration with dropped or manual findings. Review the generated prompt and the report before committing. To register the result, `--register` updates the selected `opf.yaml` and `.opf/migrations.yaml`; it refuses an already registered ID or conflicting output files.
