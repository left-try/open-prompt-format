# OPF local registry, release, and bundle contract

Status: experimental implementation. `opf/0.1` remains valid. `opf/0.2` uses the same message syntax and input rules, but removes the required frontmatter `version`; a `version` field in a `opf/0.2` file is an error. Its [frontmatter schema](frontmatter-0.2.schema.json) reflects this change. The registry assigns a SemVer version when releasing a committed prompt.

## One human-maintained config

`opf.yaml` contains `schema: opf-registry/1` and a `prompts` mapping. A prompt entry has either `renderer: opf` and `source`, or `renderer: jinja2`, `messages` with `role` and `file`, and optional string `inputs`. When Jinja `inputs` is omitted, the Python renderer accepts string values and `StrictUndefined` reports missing variables; an explicit `inputs` mapping enforces declared names and required flags. Each entry can have `channels`, mapping a channel name to `{version, digest}`. All paths are normalized POSIX paths relative to `opf.yaml` and must stay inside that directory.

The Markdown source for an `opf` entry still declares its `id`, which must match the mapping key. `opf/0.1` sources also declare `version`; release checks it against the requested version. New sources should use `opf/0.2` and omit it. `jinja2` entries can wrap existing `.md` and `.j2` files without changing their contents. Python requires the optional `jinja` extra for this renderer; TypeScript explicitly rejects Jinja rendering.

The registry does not contain a required model or provider. Application or deployment configuration selects them. A call receipt should add the **resolved** model and provider and generation parameters to the prompt receipt.

## Releasing

`opf release ID --version X.Y.Z` requires `opf.yaml` and all source dependencies to be committed and unchanged in the working tree. It computes a bundle digest and creates an annotated tag `opf/ID/vX.Y.Z` pointing to `HEAD`. The annotation is compact JSON with `schema: opf-release/1`, `id`, `version`, and `digest`. Existing tags are never overwritten. Git tags can still be force-moved outside OPF; verification detects a content mismatch, while protected or signed tags provide stronger provenance.

The bundle digest is SHA-256 of UTF-8 compact JSON with recursively sorted object keys, no ASCII escaping, and no insignificant spaces. Its payload is `{schema: "opf-bundle/1", id, definition, files}`. `definition` is the normalized registry entry without channels; `files` maps relative paths to source text with CRLF and bare CR normalized to LF. The digest covers all static Jinja dependencies discovered from `include`, `import`, and `extends`; dynamic template names cause release to fail. Version and Git commit are **outside** this content digest, so two release numbers can name the same content without changing its hash.

`opf promote ID@X.Y.Z --channel production` checks the tag, then updates the pointer in `opf.yaml`. Commit that change to record the promotion. Promotion currently rewrites YAML formatting and comments. `opf verify ID --channel production` checks the pointer, annotated tag, all files in the tagged commit, and the bundle digest. A release is loaded from its tagged commit, never by applying a channel pointer to current working files.

`opf verify-all --registry opf.yaml` checks every channel pointer and is suitable for CI. CI must fetch the release tags; GitHub Actions should use `actions/checkout` with `fetch-depth: 0`. Push a new `opf/<id>/v<version>` tag together with the commit that promotes it so other machines can resolve the channel.

## Export and runtime

`opf export ID@X.Y.Z --output prompt.json` creates a portable JSON bundle. It includes the source files, definition, digest, version, and release commit. Python `Registry.from_bundle(path)` and TypeScript `Registry.fromBundle(path)` verify the content digest before rendering. This lets wheel and container deployments load the release without `.git`. The exported version and commit are informational unless independently checked against a trusted Git tag; the content digest alone proves integrity relative to that value, not the identity of its publisher.

Both SDKs expose local draft and released OPF prompts. Python also supports Jinja2 composites. Rendering returns `{messages, receipt}`; the receipt has `id`, `version`, `channel`, `bundle_digest`, `render_digest`, and the release commit when available. `render_digest` uses the same canonical JSON hashing over the final `{role, content}` message array. Inputs and rendered content are not included in the receipt by default.

`opf publish ID@X.Y.Z --to langfuse --dry-run` shows the exact chat prompt payload and capability warning without a network request. Remove `--dry-run` to publish using `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and optional `LANGFUSE_BASE_URL`. The adapter uses Langfuse's [public prompt API](https://langfuse.com/changelog/2024-05-07-prompts-api-and-deployment-labels), assigns the deterministic `opf-vX.Y.Z` label without moving `production`, and verifies the remote copy after creation. It refuses Jinja2 and the `developer` role. Langfuse stores OPF input declarations and the canonical bundle in its [prompt config](https://langfuse.com/docs/prompt-management/features/config). Python `Registry.langfuse()` and TypeScript `Registry.langfuse()` explicitly fetch and verify that bundle before OPF rendering. An optional `expected_digest` / `expectedDigest` lets the application pin the remote copy to a digest from its local release config. Langfuse's own compile method does not enforce OPF's required input flags. MLflow and other provider adapters remain planned. No live publication was performed in this repository.

## OPF v0.3 extensions and migration provenance

`opf/0.3` retains the current core message and input behavior and defines a strict record shape for namespaced extensions. An extension key is a lowercase reverse-DNS name; its value is `{version, required, data}`. The normative field constraints and JSON-compatible payload rules are in [SYNTAX-0.3.md](SYNTAX-0.3.md). Consumers preserve unknown extension records. In strict compatibility mode, an unknown required extension prevents a claim of full compatibility and blocks a lossy adapter operation.

### Compatibility findings

`opf check` and `opf compat` report compatibility findings as well as validity. Stable categories are `portable`, `preserved_resource`, `adapter_runtime`, `unsupported`, and `data_loss`. A `preserved_resource` finding means associated source data remains available in a namespaced record; it does not mean a generic OPF renderer consumes it. An `adapter_runtime` finding means the configured legacy renderer can remain loadable while execution still depends on that runtime. `unsupported` identifies behavior requiring manual migration. A `data_loss` finding blocks migration apply unless the operator names that exact finding with `--accept-loss CODE` and uses `--register`; accepted codes are recorded in migration provenance. `--strict` does not turn informational, portable recommendations into failures.

Use `opf compat prompt.opf.md` for a prompt-level report or `opf check .` for a repository report. Both text and JSON output include recommendations where available. Reports identify source paths and lines without printing prompt bodies or preserved field values.

Registries MAY declare a migration manifest path:

```yaml
schema: opf-registry/1
migration_manifest: .opf/migrations.yaml
prompts:
  support.reply:
    source: prompts/support-reply.md
    renderer: opf
```

The path is a normalized POSIX relative path resolved from `opf.yaml`. It MUST remain inside the registry root and MUST NOT resolve through a symlink outside that root. A missing declared manifest is an error. Registries without this field remain valid and retain their existing behavior.

The manifest is UTF-8 YAML with this shape:

```yaml
schema: opf-migration-manifest/1
migrations:
  support.reply:
    source_path: legacy/support.md
    source_kind: markdown
    source_format_version: "1"
    source_digest: sha256:0000000000000000000000000000000000000000000000000000000000000000
    converter: opf-migrate-markdown
    converter_version: 0.3.0
    migrated_at: "2026-10-03T12:00:00Z"
    findings:
      - code: role-headings-preserved
        severity: info
        disposition: preserved
        message: Message roles were preserved.
        path: legacy/support.md
```

The top-level mapping has exactly `schema` and `migrations`. Each migration is keyed by an OPF prompt ID and has required `source_path`, `source_kind`, `converter`, `converter_version`, `migrated_at`, and `findings`; `source_format_version`, `source_digest`, and `accepted_losses` are optional. `accepted_losses`, when present, is a unique list of finding codes categorized as `data_loss`; these are the exact source omissions explicitly accepted by the operator. Paths use the same normalized POSIX relative-path rules as prompt files. `source_digest`, when present, is `sha256:` followed by 64 lowercase hexadecimal characters. `migrated_at` is an RFC 3339 UTC timestamp ending in `Z`. Converter identifiers and source kinds are non-empty strings without control characters; converter versions are non-empty strings.

Each finding has required `code`, `severity`, `disposition`, and `message`, with optional `path`, `category`, `source_line`, `source_field`, `source_path`, `capability`, and `recommendation`. Codes are stable lowercase identifiers matching `[a-z0-9]+(?:[._-][a-z0-9]+)*`, except named field-loss codes use `metadata.value.not_json_compatible[FIELD]` where `FIELD` contains ASCII letters, digits, dots, underscores, or hyphens. Severity is one of `info`, `warning`, or `error`; category is one of `portable`, `preserved_resource`, `adapter_runtime`, `unsupported`, or `data_loss`; disposition is one of `preserved`, `approximated`, `dropped`, or `manual`. `source_line`, when present, is a positive integer. Findings and manifests MUST reject unknown fields and duplicate YAML keys. The manifest MUST NOT contain prompt input values, rendered prompt contents, credentials, or runtime secrets.

The normalized manifest object is included in new `opf-bundle/2` payloads under `migration_manifest`; it contributes to the bundle digest and is included in exported bundles. The source file named by the prompt's provenance record is also included in the bundle file map, so it remains available for audit; it is not automatically rendered. Render-affecting files still have to be captured by the registry definition and bundle dependency set. Existing `opf-bundle/1` payload validation and digest computation remain unchanged. The manifest timestamp affects bundle identity as provenance, but MUST NOT affect prompt rendering or `render_digest`. Every manifest key MUST refer to a prompt in the registry.

## Bundle version compatibility

`opf-bundle/1` remains the required format for registries without a migration manifest. `opf-bundle/2` is used when a bundle carries normalized migration provenance. Readers MUST dispatch digest validation by the bundle's `schema` value and MUST reject unknown bundle schema versions. Exporters MUST NOT discard a manifest to downgrade a v2 bundle implicitly. A user may explicitly export a prompt without provenance only with a warning that identifies the omitted source history.
