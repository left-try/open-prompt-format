import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { parseDocument } from "yaml";

export type Role = "system" | "developer" | "user" | "assistant";
export type RenderedMessage = { role: Role; content: string };
export type InputSpec = { type: "string"; required?: boolean };
export type Metadata = {
  format: "opf/0.1";
  id: string;
  version: string;
  description?: string;
  tags?: string[];
  inputs?: Record<string, InputSpec>;
  extensions?: Record<string, unknown>;
};

export class OPFError extends Error {
  override name = "OPFError";
}

const ID_RE = /^[a-z0-9]+(?:[._-][a-z0-9]+)*$/;
const VERSION_RE = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?$/;
const HEADING_RE = /^## (system|developer|user|assistant)$/;
const VARIABLE_RE = /(?<!\\)\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;

function splitFrontmatter(text: string): [Record<string, unknown>, string] {
  const normalized = text.startsWith("\uFEFF") ? text.slice(1) : text;
  const lines = normalized.split(/(?<=\n)/);
  if (!lines.length || lines[0].replace(/[\r\n]+$/, "") !== "---") {
    throw new OPFError("frontmatter opening delimiter '---' must be the first line");
  }
  const closing = lines.findIndex((line, index) => index > 0 && line.replace(/[\r\n]+$/, "") === "---");
  if (closing < 0) throw new OPFError("frontmatter closing delimiter '---' was not found");
  const source = lines.slice(1, closing).join("");
  const doc = parseDocument(source, { uniqueKeys: true, schema: "core" });
  if (doc.errors.length) throw new OPFError(`invalid YAML frontmatter: ${doc.errors[0].message}`);
  const value: unknown = doc.toJS();
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new OPFError("frontmatter must be a YAML mapping");
  }
  return [value as Record<string, unknown>, lines.slice(closing + 1).join("")];
}

function validateMetadata(value: Record<string, unknown>): asserts value is Metadata {
  const allowed = new Set(["format", "id", "version", "description", "tags", "inputs", "extensions"]);
  const unknown = Object.keys(value).filter((key) => !allowed.has(key));
  if (unknown.length) throw new OPFError(`unknown frontmatter field(s): ${unknown.join(", ")}`);
  for (const field of ["format", "id", "version"] as const) {
    if (!(field in value)) throw new OPFError(`missing required frontmatter field: ${field}`);
  }
  if (value.format !== "opf/0.1") throw new OPFError(`unsupported format ${String(value.format)}; expected 'opf/0.1'`);
  if (typeof value.id !== "string" || !ID_RE.test(value.id)) throw new OPFError("id must match [a-z0-9]+(?:[._-][a-z0-9]+)*");
  if (typeof value.version !== "string" || !VERSION_RE.test(value.version)) {
    throw new OPFError("version must be SemVer MAJOR.MINOR.PATCH without build metadata");
  }
  if (value.description !== undefined && typeof value.description !== "string") throw new OPFError("description must be a string");
  if (value.tags !== undefined && (!Array.isArray(value.tags) || value.tags.some((tag) => typeof tag !== "string"))) {
    throw new OPFError("tags must be a list of strings");
  }
  if (value.extensions !== undefined && (!value.extensions || typeof value.extensions !== "object" || Array.isArray(value.extensions))) {
    throw new OPFError("extensions must be a mapping");
  }
  const inputs = value.inputs ?? {};
  if (!inputs || typeof inputs !== "object" || Array.isArray(inputs)) throw new OPFError("inputs must be a mapping");
  for (const [name, spec] of Object.entries(inputs)) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) throw new OPFError(`invalid input name ${JSON.stringify(name)}`);
    if (!spec || typeof spec !== "object" || Array.isArray(spec)) throw new OPFError(`input '${name}' must be a mapping`);
    const item = spec as Record<string, unknown>;
    const extra = Object.keys(item).filter((key) => !["type", "required"].includes(key));
    if (extra.length) throw new OPFError(`unknown field(s) for input '${name}': ${extra.join(", ")}`);
    if (item.type !== "string") throw new OPFError(`input '${name}' must declare type: string`);
    if (item.required !== undefined && typeof item.required !== "boolean") throw new OPFError(`input '${name}' required must be a boolean`);
  }
}

function trimBlankEdges(lines: string[]): string {
  let start = 0;
  let end = lines.length;
  while (start < end && !lines[start].trim()) start++;
  while (end > start && !lines[end - 1].trim()) end--;
  return lines.slice(start, end).join("\n");
}

function parseMessages(body: string): Array<[Role, string]> {
  const messages: Array<[Role, string]> = [];
  let role: Role | undefined;
  let content: string[] = [];
  let fenceChar: string | undefined;
  let fenceLength = 0;
  for (const line of body.split(/\r\n|\r|\n/)) {
    const fence = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (fence) {
      const marker = fence[1];
      const char = marker[0];
      if (!fenceChar) {
        fenceChar = char;
        fenceLength = marker.length;
      } else if (char === fenceChar && marker.length >= fenceLength && !fence[2].trim()) {
        fenceChar = undefined;
        fenceLength = 0;
      } else if (role) {
        content.push(line);
        continue;
      }
      if (role) content.push(line);
      else if (line.trim()) throw new OPFError("non-whitespace content appears before the first message");
      continue;
    }
    const heading = fenceChar ? null : line.match(HEADING_RE);
    if (heading) {
      if (role) messages.push([role, trimBlankEdges(content)]);
      role = heading[1] as Role;
      content = [];
      continue;
    }
    if (!role) {
      if (line.trim()) throw new OPFError("non-whitespace content appears before the first message");
      continue;
    }
    const escapedHeading = fenceChar ? null : line.match(/^\\(## (?:system|developer|user|assistant))$/);
    content.push(escapedHeading ? escapedHeading[1] : line);
  }
  if (role) messages.push([role, trimBlankEdges(content)]);
  if (!messages.length) throw new OPFError("prompt must contain at least one message");
  return messages;
}

function validateTemplates(metadata: Metadata, messages: Array<[Role, string]>): void {
  const declared = new Set(Object.keys(metadata.inputs ?? {}));
  for (const [, template] of messages) {
    const withoutEscapedOpen = template.replace(/\\\{\{/g, "");
    const stripped = withoutEscapedOpen.replace(VARIABLE_RE, "");
    if (stripped.includes("{{") || stripped.includes("{%")) {
      throw new OPFError("unsupported or malformed template expression; use only {{ input_name }}");
    }
    const variables = new Set([...template.matchAll(VARIABLE_RE)].map((match) => match[1]));
    const unknown = [...variables].filter((name) => !declared.has(name));
    if (unknown.length) throw new OPFError(`template uses undeclared input(s): ${unknown.join(", ")}`);
  }
}

export class Prompt {
  readonly metadata: Metadata;
  readonly messages: ReadonlyArray<readonly [Role, string]>;
  readonly sourceDigest: string;
  readonly path?: string;

  constructor(
    metadata: Metadata,
    messages: ReadonlyArray<readonly [Role, string]>,
    sourceDigest: string,
    path?: string,
  ) {
    this.metadata = metadata;
    this.messages = messages;
    this.sourceDigest = sourceDigest;
    this.path = path;
  }

  render(inputs: Record<string, string> = {}): RenderedMessage[] {
    const declared = this.metadata.inputs ?? {};
    const unknown = Object.keys(inputs).filter((name) => !(name in declared));
    if (unknown.length) throw new OPFError(`undeclared input(s): ${unknown.join(", ")}`);
    for (const [name, spec] of Object.entries(declared)) {
      if ((spec.required ?? true) && !(name in inputs)) throw new OPFError(`missing required input: ${name}`);
    }
    for (const [name, value] of Object.entries(inputs)) {
      if (typeof value !== "string") throw new OPFError(`input '${name}' must be a string`);
    }
    return this.messages.map(([role, template]) => {
      const variables = new Set([...template.matchAll(VARIABLE_RE)].map((match) => match[1]));
      const missing = [...variables].filter((name) => !(name in inputs));
      if (missing.length) throw new OPFError(`missing template input(s): ${missing.join(", ")}`);
      const content = template
        .replace(VARIABLE_RE, (_match, name: string) => inputs[name])
        .replace(/\\\{\{/g, "{{");
      return { role, content };
    });
  }
}

export function parse(text: string, path?: string): Prompt {
  const normalizedSource = text.replace(/\r\n?/g, "\n");
  const [metadata, body] = splitFrontmatter(normalizedSource);
  validateMetadata(metadata);
  const messages = parseMessages(body);
  validateTemplates(metadata, messages);
  const sourceDigest = `sha256:${createHash("sha256").update(normalizedSource, "utf8").digest("hex")}`;
  return new Prompt(metadata, messages, sourceDigest, path);
}

export async function load(path: string): Promise<Prompt> {
  let text: string;
  try {
    text = await readFile(path, "utf8");
  } catch (error) {
    throw new OPFError(`cannot read prompt file ${path}: ${(error as Error).message}`);
  }
  return parse(text, path);
}

export async function loadById(promptId: string, collection: string): Promise<Prompt> {
  const prompts = await loadCollection(collection);
  const matches = prompts.filter((prompt) => prompt.metadata.id === promptId);
  if (!matches.length) throw new OPFError(`prompt id '${promptId}' not found in ${collection}`);
  return matches[0];
}

export async function loadCollection(collection: string): Promise<Prompt[]> {
  const { readdir } = await import("node:fs/promises");
  const { join } = await import("node:path");
  const files: string[] = [];
  async function walk(directory: string): Promise<void> {
    let entries;
    try {
      entries = await readdir(directory, { withFileTypes: true });
    } catch (error) {
      throw new OPFError(`cannot scan prompt collection ${directory}: ${(error as Error).message}`);
    }
    for (const entry of entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await walk(path);
      else if (entry.isFile() && entry.name.endsWith(".md")) files.push(path);
    }
  }
  await walk(collection);
  const prompts: Prompt[] = [];
  const seen = new Map<string, string>();
  for (const path of files) {
    const prompt = await load(path);
    const prior = seen.get(prompt.metadata.id);
    if (prior) throw new OPFError(`duplicate prompt id '${prompt.metadata.id}': ${prior}, ${path}`);
    seen.set(prompt.metadata.id, path);
    prompts.push(prompt);
  }
  return prompts;
}
