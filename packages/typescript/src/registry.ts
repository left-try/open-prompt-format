import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { readFile, lstat, realpath } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { promisify } from "node:util";
import { parseDocument } from "yaml";
import { OPFError, parse, type RenderedMessage, type Role } from "./index.js";

const execFileAsync = promisify(execFile);
const ID_RE = /^[a-z0-9]+(?:[._-][a-z0-9]+)*$/;
const VERSION_RE = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?$/;
const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
const ROLES = new Set<Role>(["system", "developer", "user", "assistant"]);

type Pointer = { version: string; digest: string };
type OpfDefinition = { renderer: "opf"; source: string };
type JinjaDefinition = { renderer: "jinja2"; messages: Array<{ role: Role; file: string }>; inputs?: Record<string, { type: "string"; required?: boolean }> };
type Definition = OpfDefinition | JinjaDefinition;
type Entry = Definition & { channels?: Record<string, Pointer> };
type MigrationFinding = { code: string; severity: "info" | "warning" | "error"; disposition: "preserved" | "approximated" | "dropped" | "manual"; message: string; path?: string };
type MigrationRecord = { source_path: string; source_kind: string; source_format_version?: string; source_digest?: string; converter: string; converter_version: string; migrated_at: string; findings: MigrationFinding[] };
type MigrationManifest = { schema: "opf-migration-manifest/1"; migrations: Record<string, MigrationRecord> };
type Config = { schema: "opf-registry/1"; prompts: Record<string, Entry>; migration_manifest?: string };
export type Bundle = { schema: "opf-bundle/1" | "opf-bundle/2"; id: string; definition: Definition; files: Record<string, string>; digest: string; version?: string; commit?: string; migration_manifest?: MigrationManifest };

function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function pathName(value: unknown): string {
  if (typeof value !== "string" || !value || value.includes("\\") || value.includes(":") || value.includes("\0") || value.startsWith("/") || value.split("/").some((part) => !part || part === "." || part === "..")) {
    throw new OPFError(`prompt path must be normalized and stay inside the registry: ${String(value)}`);
  }
  return value;
}

function definition(id: string, value: unknown): Definition {
  if (!ID_RE.test(id) || !isObject(value)) throw new OPFError(`invalid registry prompt ${id}`);
  const extra = Object.keys(value).filter((key) => !["renderer", "source", "messages", "inputs", "channels"].includes(key));
  if (extra.length) throw new OPFError(`unknown registry field(s) for '${id}': ${extra.join(", ")}`);
  const renderer = value.renderer ?? "opf";
  if (renderer === "opf") {
    if (value.messages !== undefined || value.inputs !== undefined) throw new OPFError("opf renderer accepts source only");
    return { renderer, source: pathName(value.source) };
  }
  if (renderer !== "jinja2" || value.source !== undefined || !Array.isArray(value.messages) || !value.messages.length) {
    throw new OPFError(`unsupported or invalid renderer for '${id}'`);
  }
  const messages = value.messages.map((item: unknown) => {
    if (!isObject(item) || Object.keys(item).sort().join(",") !== "file,role" || !ROLES.has(item.role as Role)) throw new OPFError("jinja2 messages require role and file");
    return { role: item.role as Role, file: pathName(item.file) };
  });
  if ("inputs" in value) {
    const inputs = value.inputs;
    if (!isObject(inputs)) throw new OPFError("registry inputs must be a mapping");
    for (const [name, spec] of Object.entries(inputs)) {
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || !isObject(spec) || Object.keys(spec).some((key) => !["type", "required"].includes(key)) || spec.type !== "string" || (spec.required !== undefined && typeof spec.required !== "boolean")) {
        throw new OPFError(`invalid string input '${name}'`);
      }
    }
    return { renderer: "jinja2", messages, inputs: inputs as JinjaDefinition["inputs"] };
  }
  return { renderer: "jinja2", messages };
}

function yamlMapping(raw: string): Record<string, unknown> {
  const doc = parseDocument(raw, { uniqueKeys: true, schema: "core" });
  if (doc.errors.length) throw new OPFError(`invalid opf.yaml: ${doc.errors[0].message}`);
  const value: unknown = doc.toJS();
  if (!isObject(value)) throw new OPFError("opf.yaml must be a YAML mapping");
  return value;
}

function config(raw: string): Config {
  const value = yamlMapping(raw);
  if (Object.keys(value).some((key) => !["prompts", "schema", "migration_manifest"].includes(key)) || !["prompts,schema", "migration_manifest,prompts,schema"].includes(Object.keys(value).sort().join(",")) || value.schema !== "opf-registry/1" || !isObject(value.prompts)) {
    throw new OPFError("opf.yaml requires schema: opf-registry/1 and a prompts mapping");
  }
  if (value.migration_manifest !== undefined) value.migration_manifest = pathName(value.migration_manifest);
  for (const [id, entry] of Object.entries(value.prompts)) {
    definition(id, entry);
    const channels = (entry as Record<string, unknown>).channels ?? {};
    if (!isObject(channels)) throw new OPFError(`channels for '${id}' must be a mapping`);
    for (const [name, pointer] of Object.entries(channels)) {
      if (!ID_RE.test(name) || !isObject(pointer) || Object.keys(pointer).sort().join(",") !== "digest,version" || typeof pointer.version !== "string" || !VERSION_RE.test(pointer.version) || typeof pointer.digest !== "string" || !DIGEST_RE.test(pointer.digest)) {
        throw new OPFError(`invalid channel pointer for '${id}'`);
      }
    }
  }
  return value as Config;
}

function compareUtf8(a: string, b: string): number {
  const left = new TextEncoder().encode(a);
  const right = new TextEncoder().encode(b);
  for (let index = 0; index < Math.min(left.length, right.length); index++) {
    if (left[index] !== right[index]) return left[index] - right[index];
  }
  return left.length - right.length;
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (isObject(value)) return `{${Object.keys(value).sort(compareUtf8).map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

function digest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonicalJson(value), "utf8").digest("hex")}`;
}

function makeBundle(id: string, item: Definition, files: Record<string, string>, migration?: MigrationRecord): Bundle {
  if (migration) {
    if (typeof files[migration.source_path] !== "string") throw new OPFError(`migration source file '${migration.source_path}' is missing from bundle`);
    const sourceDigest = `sha256:${createHash("sha256").update(files[migration.source_path].replace(/\r\n?/g, "\n"), "utf8").digest("hex")}`;
    if (migration.source_digest && migration.source_digest !== sourceDigest) throw new OPFError(`migration source digest does not match '${migration.source_path}'`);
    const manifest: MigrationManifest = { schema: "opf-migration-manifest/1", migrations: { [id]: migration } };
    const payload = { schema: "opf-bundle/2" as const, id, definition: item, files, migration_manifest: manifest };
    return { ...payload, digest: digest(payload) };
  }
  const payload = { schema: "opf-bundle/1" as const, id, definition: item, files };
  return { ...payload, digest: digest(payload) };
}

function validateMigrationManifest(value: unknown): MigrationManifest {
  if (!isObject(value) || value.schema !== "opf-migration-manifest/1" || !isObject(value.migrations) || Object.keys(value).sort().join(",") !== "migrations,schema") throw new OPFError("invalid migration manifest");
  const migrations: Record<string, MigrationRecord> = Object.create(null);
  for (const [id, raw] of Object.entries(value.migrations)) {
    if (!ID_RE.test(id) || !isObject(raw)) throw new OPFError("migration manifest contains an invalid prompt entry");
    const required = ["converter", "converter_version", "findings", "migrated_at", "source_kind", "source_path"];
    const allowed = [...required, "source_digest", "source_format_version"];
    if (required.some((key) => !(key in raw)) || Object.keys(raw).some((key) => !allowed.includes(key))) throw new OPFError(`migration record for '${id}' has missing or unknown fields`);
    const record = raw as unknown as MigrationRecord;
    record.source_path = pathName(record.source_path);
    for (const field of ["source_kind", "converter", "converter_version"] as const) {
      if (typeof record[field] !== "string" || !record[field] || /[\u0000-\u001f]/.test(record[field])) throw new OPFError(`invalid migration field '${field}' for '${id}'`);
    }
    if (record.source_format_version !== undefined && (typeof record.source_format_version !== "string" || !record.source_format_version)) throw new OPFError(`invalid source_format_version for '${id}'`);
    if (record.source_digest !== undefined && (typeof record.source_digest !== "string" || !DIGEST_RE.test(record.source_digest))) throw new OPFError(`invalid source_digest for '${id}'`);
    if (typeof record.migrated_at !== "string" || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(record.migrated_at) || Number.isNaN(Date.parse(record.migrated_at))) throw new OPFError(`invalid migrated_at for '${id}'`);
    if (!Array.isArray(record.findings)) throw new OPFError(`findings for '${id}' must be a list`);
    for (const finding of record.findings) {
      if (!isObject(finding) || Object.keys(finding).some((key) => !["code", "severity", "disposition", "message", "path"].includes(key)) || ["code", "severity", "disposition", "message"].some((key) => !(key in finding))) throw new OPFError(`invalid migration finding for '${id}'`);
      if (typeof finding.code !== "string" || !ID_RE.test(finding.code) || !["info", "warning", "error"].includes(String(finding.severity)) || !["preserved", "approximated", "dropped", "manual"].includes(String(finding.disposition)) || typeof finding.message !== "string") throw new OPFError(`invalid migration finding values for '${id}'`);
      if (finding.path !== undefined) pathName(finding.path);
    }
    migrations[id] = record;
  }
  return { schema: "opf-migration-manifest/1", migrations };
}

function validateBundle(value: unknown): Bundle {
  if (!isObject(value) || (value.schema !== "opf-bundle/1" && value.schema !== "opf-bundle/2") || typeof value.id !== "string" || !isObject(value.files) || typeof value.digest !== "string") throw new OPFError("invalid OPF bundle");
  if (Object.keys(value).some((key) => !["schema", "id", "definition", "files", "digest", "version", "commit", "migration_manifest"].includes(key))) throw new OPFError("unknown OPF bundle field");
  if ((value.schema === "opf-bundle/1") !== (value.migration_manifest === undefined)) throw new OPFError("bundle schema and migration manifest do not match");
  if (value.version !== undefined && (typeof value.version !== "string" || !VERSION_RE.test(value.version))) throw new OPFError("invalid bundle release version");
  if (value.commit !== undefined && typeof value.commit !== "string") throw new OPFError("invalid bundle commit");
  const item = definition(value.id, value.definition);
  if (canonicalJson(item) !== canonicalJson(value.definition)) throw new OPFError("invalid bundle definition");
  const files = value.files as Record<string, unknown>;
  if (Object.entries(files).some(([name, source]) => typeof source !== "string" || pathName(name) !== name)) throw new OPFError("invalid bundle file map");
  if (item.renderer === "opf") {
    const source = files[item.source];
    if (Object.keys(files).length !== 1 || typeof source !== "string" || parse(source).metadata.id !== value.id) throw new OPFError("invalid OPF source in bundle");
  } else {
    for (const message of item.messages) if (typeof files[message.file] !== "string") throw new OPFError(`missing bundle file ${message.file}`);
  }
  let migration: MigrationRecord | undefined;
  if (value.schema === "opf-bundle/2") {
    const manifest = validateMigrationManifest(value.migration_manifest);
    if (Object.keys(manifest.migrations).join(",") !== value.id) throw new OPFError("bundle migration manifest must contain only its prompt id");
    migration = manifest.migrations[value.id];
  }
  if (makeBundle(value.id, item, files as Record<string, string>, migration).digest !== value.digest) throw new OPFError("bundle digest does not match contents");
  return value as Bundle;
}

async function git(root: string, ...args: string[]): Promise<string> {
  try {
    const { stdout } = await execFileAsync("git", ["-C", root, ...args], { maxBuffer: 32 * 1024 * 1024 });
    return stdout;
  } catch (error) {
    throw new OPFError(`git ${args.join(" ")}: ${(error as Error).message}`);
  }
}

type GitReader = (root: string, ...args: string[]) => Promise<string>;

export class PreparedPrompt {
  constructor(readonly messages: RenderedMessage[], readonly receipt: Record<string, unknown>) {}

  callReceipt(options: { provider: string; model: string; modelVersion?: string; parameters?: Record<string, unknown> }): Record<string, unknown> {
    if (!options.provider || !options.model) throw new OPFError("provider and resolved model are required for a call receipt");
    return { ...this.receipt, provider: options.provider, model: options.model, ...(options.modelVersion ? { model_version: options.modelVersion } : {}), parameters: options.parameters ?? {} };
  }
}

export class RegisteredPrompt {
  constructor(readonly bundle: Bundle, readonly version?: string, readonly channel?: string) {}

  render(inputs: Record<string, string> = {}): PreparedPrompt {
    if (this.bundle.definition.renderer !== "opf") throw new OPFError("Jinja2 rendering is available in the Python SDK; TypeScript cannot execute this bundle");
    const messages = parse(this.bundle.files[this.bundle.definition.source]).render(inputs);
    const receipt: Record<string, unknown> = { id: this.bundle.id, version: this.version ?? null, channel: this.channel ?? null, bundle_digest: this.bundle.digest, render_digest: digest(messages) };
    if (this.bundle.commit) receipt.commit = this.bundle.commit;
    const migration = this.bundle.migration_manifest?.migrations[this.bundle.id];
    if (migration) receipt.migration = { source_path: migration.source_path, source_kind: migration.source_kind, source_digest: migration.source_digest ?? null, converter: migration.converter, converter_version: migration.converter_version };
    return new PreparedPrompt(messages, receipt);
  }
}

export class Registry {
  private constructor(readonly path: string, readonly config: Config, private readonly gitReader: GitReader) {}

  static async local(configPath = "opf.yaml", options: { gitReader?: GitReader } = {}): Promise<Registry> {
    const path = resolve(configPath);
    return new Registry(path, config(await readFile(path, "utf8")), options.gitReader ?? git);
  }

  static async fromBundle(path: string): Promise<RegisteredPrompt> {
    const bundle = validateBundle(JSON.parse(await readFile(path, "utf8")));
    return new RegisteredPrompt(bundle, bundle.version);
  }

  static langfuse(options: { baseUrl?: string; publicKey?: string; secretKey?: string } = {}): LangfuseRegistry {
    return new LangfuseRegistry(options);
  }

  private async repository(): Promise<{ root: string; configPath: string }> {
    const root = (await this.gitReader(dirname(this.path), "rev-parse", "--show-toplevel")).trim();
    const configPath = relative(root, this.path).split(sep).join("/");
    if (configPath.startsWith("../") || isAbsolute(configPath)) throw new OPFError("opf.yaml must be inside the Git repository");
    return { root, configPath };
  }

  private async readLocal(path: string): Promise<string> {
    const target = resolve(dirname(this.path), pathName(path));
    const info = await lstat(target);
    const actual = await realpath(target);
    const base = await realpath(dirname(this.path));
    if (info.isSymbolicLink() || !actual.startsWith(base + sep)) throw new OPFError(`registry path escapes its root: ${path}`);
    return readFile(target, "utf8");
  }

  private async migrationFor(promptId: string, manifestPath = this.config.migration_manifest): Promise<MigrationRecord | undefined> {
    if (!manifestPath) return undefined;
    const manifest = validateMigrationManifest(yamlMapping(await this.readLocal(manifestPath)));
    return manifest.migrations[promptId];
  }

  private async release(id: string, version: string): Promise<Bundle> {
    if (!VERSION_RE.test(version)) throw new OPFError("version must be SemVer MAJOR.MINOR.PATCH");
    const { root, configPath } = await this.repository();
    const ref = `refs/tags/opf/${id}/v${version}`;
    const annotation = JSON.parse((await this.gitReader(root, "for-each-ref", "--format=%(contents)", ref)).trim());
    if (annotation.schema !== "opf-release/1" || annotation.id !== id || annotation.version !== version || !DIGEST_RE.test(annotation.digest)) throw new OPFError(`invalid release tag ${ref}`);
    const taggedConfig = config(await this.gitReader(root, "show", `${ref}:${configPath}`));
    const entry = taggedConfig.prompts[id];
    if (!entry) throw new OPFError(`prompt '${id}' is missing from release commit`);
    const item = definition(id, entry);
    if (item.renderer !== "opf") throw new OPFError("Jinja2 Git releases are available in the Python SDK; TypeScript can load exported bundles but cannot render them");
    const prefix = dirname(configPath) === "." ? "" : `${dirname(configPath)}/`;
    const readTagged = async (path: string) => this.gitReader(root, "show", `${ref}:${prefix}${path}`);
    const source = (await readTagged(item.source)).replace(/\r\n?/g, "\n");
    const taggedManifest = taggedConfig.migration_manifest
      ? validateMigrationManifest(yamlMapping(await readTagged(taggedConfig.migration_manifest)))
      : undefined;
    const migration = taggedManifest?.migrations[id];
    const files: Record<string, string> = { [item.source]: source };
    if (migration) files[migration.source_path] = (await readTagged(migration.source_path)).replace(/\r\n?/g, "\n");
    const bundle = makeBundle(id, item, files, migration);
    const prompt = parse(source);
    if (prompt.metadata.id !== id || (prompt.metadata.version && prompt.metadata.version !== version)) throw new OPFError("release prompt id or frontmatter version mismatch");
    if (bundle.digest !== annotation.digest) throw new OPFError(`release tag digest mismatch: ${ref}`);
    bundle.version = version;
    bundle.commit = (await this.gitReader(root, "rev-parse", `${ref}^{}`)).trim();
    return bundle;
  }

  async get(id: string, options: { channel?: string; version?: string } = {}): Promise<RegisteredPrompt> {
    const entry = this.config.prompts[id];
    if (!entry) throw new OPFError(`unknown registry prompt id '${id}'`);
    if (options.channel && options.version) throw new OPFError("choose either channel or version");
    const pointer = options.channel ? entry.channels?.[options.channel] : undefined;
    if (options.channel && !pointer) throw new OPFError(`unknown channel '${options.channel}' for '${id}'`);
    const version = options.version ?? pointer?.version;
    if (version) {
      const bundle = await this.release(id, version);
      if (pointer && bundle.digest !== pointer.digest) throw new OPFError(`channel digest mismatch for '${options.channel}'`);
      return new RegisteredPrompt(bundle, version, options.channel);
    }
    const item = definition(id, entry);
    if (item.renderer !== "opf") throw new OPFError("Jinja2 rendering is available in the Python SDK");
    const path = resolve(dirname(this.path), item.source);
    const info = await lstat(path);
    const actual = await realpath(path);
    const base = await realpath(dirname(this.path));
    if (info.isSymbolicLink() || !actual.startsWith(base + sep)) throw new OPFError(`prompt path escapes registry: ${item.source}`);
    const source = (await readFile(path, "utf8")).replace(/\r\n?/g, "\n");
    const prompt = parse(source);
    if (prompt.metadata.id !== id) throw new OPFError(`registry id '${id}' differs from prompt id '${prompt.metadata.id}'`);
    const migration = await this.migrationFor(id);
    const files: Record<string, string> = { [item.source]: source };
    if (migration) files[migration.source_path] = (await this.readLocal(migration.source_path)).replace(/\r\n?/g, "\n");
    return new RegisteredPrompt(makeBundle(id, item, files, migration));
  }
}

export class LangfuseRegistry {
  readonly baseUrl: string;
  private readonly authorization: string;

  constructor(options: { baseUrl?: string; publicKey?: string; secretKey?: string } = {}) {
    this.baseUrl = (options.baseUrl ?? process.env.LANGFUSE_BASE_URL ?? "https://cloud.langfuse.com").replace(/\/$/, "");
    const publicKey = options.publicKey ?? process.env.LANGFUSE_PUBLIC_KEY;
    const secretKey = options.secretKey ?? process.env.LANGFUSE_SECRET_KEY;
    if (!publicKey || !secretKey) throw new OPFError("set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY before loading a remote prompt");
    if (!this.baseUrl.startsWith("https://") && !/^http:\/\/(localhost|127\.0\.0\.1):/.test(this.baseUrl)) throw new OPFError("Langfuse base URL must use HTTPS, except for local development");
    this.authorization = `Basic ${Buffer.from(`${publicKey}:${secretKey}`, "utf8").toString("base64")}`;
  }

  async get(id: string, options: { channel?: string; version?: string; expectedDigest?: string } = {}): Promise<RegisteredPrompt> {
    if (options.channel && options.version) throw new OPFError("choose either channel or version");
    const label = options.channel ?? (options.version ? `opf-v${options.version}` : "production");
    const url = `${this.baseUrl}/api/public/v2/prompts/${encodeURIComponent(id)}?label=${encodeURIComponent(label)}`;
    let response: Response;
    try {
      response = await fetch(url, { headers: { Authorization: this.authorization, Accept: "application/json" }, signal: AbortSignal.timeout(20_000) });
    } catch (error) {
      throw new OPFError(`Langfuse GET failed: ${(error as Error).message}`);
    }
    if (response.status === 404) throw new OPFError(`Langfuse prompt '${id}' with label '${label}' was not found`);
    if (!response.ok) throw new OPFError(`Langfuse GET failed with HTTP ${response.status}`);
    const remote: unknown = await response.json();
    if (!isObject(remote) || !isObject(remote.config) || !isObject(remote.config.opf)) throw new OPFError("Langfuse prompt does not contain OPF metadata");
    const opf = remote.config.opf;
    const bundle = validateBundle(opf.bundle);
    if (bundle.id !== id || bundle.digest !== opf.bundle_digest || (options.version && bundle.version !== options.version)) throw new OPFError("Langfuse release identity differs from requested release");
    if (options.expectedDigest && bundle.digest !== options.expectedDigest) throw new OPFError("Langfuse bundle digest differs from the pinned local release");
    if (bundle.definition.renderer !== "opf") throw new OPFError("Jinja2 remote rendering is available in the Python SDK");
    const prompt = parse(bundle.files[bundle.definition.source]);
    const expected = prompt.messages.map(([role, source]) => ({ role, content: source.replace(/(?<!\\)\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g, "{{$1}}") }));
    if (!Array.isArray(remote.prompt) || remote.prompt.length !== expected.length || remote.prompt.some((item: unknown, index: number) => !isObject(item) || item.role !== expected[index].role || item.content !== expected[index].content)) {
      throw new OPFError("Langfuse chat prompt differs from its OPF bundle");
    }
    return new RegisteredPrompt(bundle, bundle.version, options.channel);
  }
}
