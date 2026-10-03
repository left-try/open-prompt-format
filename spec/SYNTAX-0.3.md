# OPF Syntax v0.3 (Draft)

**Status:** Draft for review. This document does not change the behavior of `opf/0.1` or `opf/0.2`.  
**Purpose:** Specify the next compatible step for a portable prompt core and vendor/framework extensions.

## 1. Goals and non-goals

OPF v0.3 keeps the current readable Markdown representation and simple string-input renderer. It adds a normative contract for namespaced extension data so importers and exporters can preserve framework-specific configuration without pretending that every consumer can execute it.

This version does not standardize agent orchestration, tools, model selection, output schemas, arbitrary template languages, or framework runtime behavior. Those may be preserved in extensions but are not portable-core semantics in v0.3.

## 2. Compatibility

- Existing v0.1 and v0.2 documents remain valid under their existing rules.
- A v0.3 implementation MUST NOT reinterpret v0.1 or v0.2 files using v0.3 extension rules.
- The v0.3 message headings, role set, input declarations, interpolation, trimming, line-ending normalization, and rendered `{role, content}` representation are unchanged from v0.2.
- A v0.3 file MUST declare `format: opf/0.3` and MUST NOT declare a file-level `version`. Prompt release versions remain in the registry.

## 3. Frontmatter

The v0.3 frontmatter fields are `format`, `id`, `description`, `tags`, `inputs`, and `extensions`. Existing v0.2 constraints remain in force for every field except `format` and the extension payload shape.

`extensions` is optional. When present it MUST be a mapping from an extension identifier to an extension record:

```yaml
extensions:
  com.openai.responses:
    version: "1"
    required: true
    data:
      tools:
        - type: function
          name: lookup_order
      text_format:
        type: json_schema
        name: order_status
```

Each extension identifier MUST be a reverse-DNS name matching `^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$`. Names are case-sensitive and MUST be lowercase ASCII. Publishers SHOULD use a domain they control and MAY append a product or capability segment. Identifiers are limited to 255 UTF-8 bytes.

Each extension record MUST contain:

- `version`: a non-empty string identifying that extension's schema version;
- `required`: a boolean;
- `data`: a YAML mapping containing only JSON-compatible values.

`version` MUST contain between 1 and 64 non-space printable ASCII characters. It is an extension schema label, not necessarily SemVer. `data` MUST be a mapping; arrays and scalars are not valid at its root.

Unknown extension-record fields MUST cause validation failure. Duplicate extension identifiers MUST be rejected by the duplicate-key rule already used for YAML mappings. The canonical JSON representation of `data` is part of the prompt bundle digest.

Extension payloads MUST NOT override the semantics of core fields. For example, an extension cannot redefine the meaning of `system` or change how core inputs are interpolated. Extension namespaces MUST NOT collide with one another.

The JSON Schema for this metadata contract is [frontmatter-0.3.schema.json](frontmatter-0.3.schema.json). Implementations MUST also enforce YAML duplicate-key rejection and the runtime JSON-value restrictions described below; JSON Schema validation alone does not replace those checks.

## 4. Unknown extensions and capability handling

Parsing and preserving an unknown extension is different from executing it:

- A parser MUST preserve the complete extension identifier, version, `required` value, and `data` in the parsed metadata.
- A generic renderer MAY render the portable core messages when the extension does not alter their content or input rules.
- A validator MUST report unknown extensions. In strict mode, it MUST fail on an unknown extension whose `required` value is `true`.
- A target adapter MUST report whether it supports each extension. It MUST fail in strict mode when it cannot preserve or execute a required extension.
- A transformer MUST preserve unknown extensions byte-semantically at the parsed data level. It MUST NOT drop them by default.
- A tool that cannot preserve an extension MUST refuse a write operation unless the user explicitly selects an option that permits dropping it; the report must name the dropped extension.

`required: true` means a consumer claiming full compatibility for the artifact needs to understand the extension. It does not mean that the portable core parser cannot read the document.

## 5. Canonical extension data and bundle identity

Extension data MUST be JSON-compatible: null, booleans, strings, finite numbers, arrays, and mappings with string keys. YAML tags, binary values, non-finite numbers, and cyclic aliases are invalid. Implementations MUST reject values that cannot be represented in canonical JSON and MUST reject YAML aliases that create cyclic structures.

Bundle digest input MUST include normalized extension identifiers and records. Canonical serialization uses UTF-8 JSON, recursively sorted mapping keys, no insignificant whitespace, and no ASCII escaping, matching the existing registry bundle contract. Extension data that affects target execution therefore changes bundle identity.

Source digest continues to identify the normalized source file. It is not a semantic-equivalence digest. A rendered digest continues to identify only the final core message array unless an adapter explicitly defines and records an additional target-payload digest.

## 6. Migration provenance

Migration provenance is registry metadata, not core prompt frontmatter in v0.3. A migration manifest entry MUST be associated with the generated prompt ID and record:

- source path relative to the repository root;
- detected source kind and source-format version when known;
- source digest when a deterministic digest can be computed;
- converter name and version;
- migration timestamp in UTC;
- compatibility findings and any explicitly accepted losses.

Provenance MUST NOT include input values, rendered prompt contents, API credentials, or other runtime secrets. Provenance contributes to an audit report but does not affect prompt rendering. The registry specification will define its exact manifest schema before implementation.

## 7. Error behavior

Implementations MUST provide actionable validation errors for malformed extension identifiers, missing extension fields, invalid versions, non-JSON-compatible values, duplicate keys, and unsupported required extensions in strict mode. Where possible, errors identify the extension identifier and YAML location.

## 8. Shared conformance expectations

Before an implementation claims v0.3 support, it MUST demonstrate equivalent Python and TypeScript behavior for:

- valid extension records and canonical bundle digests;
- missing or unknown extension fields;
- invalid identifiers and extension versions;
- unknown optional versus unknown required extensions;
- round-trip preservation of unknown payload data;
- v0.1 and v0.2 compatibility without reinterpretation.

## 9. Example

A core-only v0.3 prompt is valid and needs no extension block:

```md
---
format: opf/0.3
id: summarize.text
inputs:
  text:
    type: string
---

## system
Summarize the supplied text in three sentences.

## user
{{ text }}
```

The following example includes a non-core extension:

```md
---
format: opf/0.3
id: support.reply
description: Draft a response to a customer support message.
inputs:
  customer_message:
    type: string
    required: true
extensions:
  com.crewai.agent:
    version: "1"
    required: false
    data:
      role: Support specialist
      goal: Resolve customer questions accurately
---

## system
You help customers with order questions. Be concise, kind, and factual.
Do not invent order details.

## user
{{ customer_message }}
```

The core renderer returns the two messages above. A CrewAI adapter may use the optional extension to populate supported agent configuration fields. A generic consumer preserves the extension and renders the portable core without claiming that it has constructed a CrewAI agent.
