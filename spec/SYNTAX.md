# OPF Syntax v0.1 (Proposal)

This document defines the first proposed syntax for a prompt stored in one Markdown file. “MUST”, “MUST NOT”, “SHOULD”, and “MAY” are normative requirements for implementations of this proposal.

## File structure

A prompt file consists of YAML frontmatter, a separator, then an ordered Markdown message body:

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
You help customers with order questions.

## user
{{ customer_message }}
```

The opening `---` MUST be the first line. The closing `---` MUST appear on a line by itself. The text after the closing separator is the message body and is not part of the YAML document. Parsers MUST recognize LF, CRLF, and bare CR as line endings and treat them equivalently.

UTF-8 is required. Implementations MUST preserve message order and the text within each message, apart from the explicitly defined trimming and template substitutions below.

Frontmatter uses the YAML 1.2 Core Schema. Duplicate mapping keys MUST be rejected. This keeps plain values such as `on` and `yes` as strings rather than YAML 1.1 booleans; authors MUST quote values when they want a string that YAML 1.2 Core interprets as another scalar type (for example, `"1"`).

## Frontmatter fields

| Field | Required | Meaning |
| --- | --- | --- |
| `format` | Yes | Format identifier. For this proposal, exactly `opf/0.1`. |
| `id` | Yes | Stable prompt identifier, unique within a prompt collection. |
| `version` | Yes | Prompt version using `MAJOR.MINOR.PATCH` SemVer syntax. |
| `description` | No | Short human-readable purpose. |
| `tags` | No | List of strings for discovery and filtering. |
| `inputs` | No | Map of declared template inputs. |
| `extensions` | No | Map of namespaced, implementation-specific metadata. |

Unknown fields at the top level MUST cause a validation error. Extension keys SHOULD be namespaced (for example, `com.example.tool`). Portable meaning MUST NOT depend on an extension.

Each input is an object with `type: string` and optional `required: true|false`. `required` defaults to `true`. v0.1 supports string inputs only. Unknown input properties MUST cause a validation error.

IDs MUST match `[a-z0-9]+(?:[._-][a-z0-9]+)*`. IDs are case-sensitive. A collection MUST reject duplicate IDs.

Versions MUST be valid SemVer without build metadata. A changed prompt SHOULD receive a new version before release. Git remains the source of edit history; `version` identifies the prompt artifact release.

## Source digest

Implementations MUST compute a source digest as `sha256:<lowercase-hex>`, where the hex value is SHA-256 over the complete prompt file encoded as UTF-8 after newline normalization. CRLF and bare CR line endings MUST be converted to LF before hashing. No other normalization is performed: whitespace, comments, YAML key order, and a UTF-8 BOM (if present) affect the digest. The digest is derived and MUST NOT be authored in frontmatter.

The source digest identifies the exact source artifact under these normalization rules. It is not a semantic-equivalence hash and does not replace the prompt ID or version. Implementations SHOULD expose it to callers so traces and registry transfers can record which source artifact was used. A digest of rendered messages is outside the v0.1 contract.

## Messages

Messages are delimited by exact headings at the beginning of a line:

- `## system`
- `## developer`
- `## user`
- `## assistant`

At least one message MUST be present. Any number of messages MAY be used, including repeated roles. The headings define roles and are not sent as message text.

The message content starts on the line after its heading and continues to the next recognized message heading or end of file. Other Markdown headings are message content. Leading and trailing blank lines around each message body are removed; remaining content and internal whitespace are preserved. Empty messages are allowed.

Recognized message headings inside a fenced Markdown code block (backtick or tilde fences) are literal text. To include an otherwise recognized heading as literal text outside a code block, prefix it with one backslash, for example `\## user`. The backslash is removed in rendered content. A line containing a heading with any other spacing or capitalization is ordinary content.

Implementations MUST reject non-whitespace text before the first message heading. A file with no messages is invalid.

## Template interpolation

The only interpolation syntax in v0.1 is `{{ input_name }}`, where whitespace inside the braces is optional. Names MUST match a declared input. Rendering substitutes the input's string value literally; substituted values are not parsed as templates.

All declared required inputs MUST be provided. Missing required inputs, undeclared variables used in a template, and supplied but undeclared input names MUST produce errors. There are no implicit defaults.

Conditionals, loops, filters, function calls, attribute access, and environment-variable access are unsupported. Literal `{{` can be written as `\{{`; the backslash is removed during rendering. Literal `}}` needs no escape.

## Rendered representation

Rendering produces an ordered array of objects. Each object has exactly `role` and `content` string properties. The parsed prompt object also exposes its computed source digest separately from the rendered messages:

```json
[
  {"role": "system", "content": "You help customers with order questions."},
  {"role": "user", "content": "My order is late."}
]
```

This representation is the boundary between OPF and provider-specific SDKs. A provider adapter MAY translate roles, reject unsupported roles or features, and apply provider-specific configuration. Such configuration MUST NOT change the meaning of the OPF prompt silently.

## Errors

Implementations MUST report actionable errors for malformed YAML, missing required fields, unsupported format versions, invalid IDs or versions, invalid message structure, unknown template variables, and missing inputs. Error messages SHOULD identify the file and relevant field or line when available.

## Deliberate exclusions in v0.1

The core format does not define model selection, temperature, tool schemas, output schemas, eval datasets, deployment labels, permissions, workflow graphs, registry APIs, or tracing. These may be addressed by later proposals or namespaced extensions. They MUST NOT be required to parse or render a v0.1 prompt.
