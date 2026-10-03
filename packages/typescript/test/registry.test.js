import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { Registry } from "../dist/index.js";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

const source = `---
format: opf/0.2
id: support.reply
inputs:
  question:
    type: string
---

## system
Answer briefly.

## user
{{ question }}
`;

function git(root, ...args) {
  return execFileSync("git", ["-C", root, ...args], { encoding: "utf8" }).trim();
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "opf-registry-ts-"));
  await mkdir(path.join(root, "prompts"));
  await writeFile(path.join(root, "prompts/reply.md"), source);
  await writeFile(path.join(root, "opf.yaml"), "schema: opf-registry/1\nprompts:\n  support.reply:\n    renderer: opf\n    source: prompts/reply.md\n");
  return root;
}

test("shared bundle digest matches the Python registry", async () => {
  for (const fixture of ["fixtures/registry-digest.json", "fixtures/registry-unicode/digest.json"]) {
    const expected = JSON.parse(await readFile(path.join(repoRoot, fixture), "utf8"));
    const bundle = (await (await Registry.local(path.join(repoRoot, expected.config))).get(expected.id)).bundle;
    assert.equal(bundle.digest, expected.bundle_digest);
  }
});

test("Git release, channel, bundle, and render receipts", async () => {
  const root = await fixture();
  try {
    const configPath = path.join(root, "opf.yaml");
    const registry = await Registry.local(configPath);
    const draft = await registry.get("support.reply");
    const digest = draft.bundle.digest;
    const annotation = JSON.stringify({ schema: "opf-release/1", id: "support.reply", version: "1.0.0", digest });
    const originalConfig = await readFile(configPath, "utf8");
    const gitReader = async (_root, ...args) => {
      if (args[0] === "rev-parse" && args[1] === "--show-toplevel") return root;
      if (args[0] === "for-each-ref") return annotation;
      if (args[0] === "show" && args[1].endsWith(":opf.yaml")) return originalConfig;
      if (args[0] === "show" && args[1].endsWith(":prompts/reply.md")) return source;
      if (args[0] === "rev-parse") return "deadbeef";
      throw new Error(`unexpected git command: ${args.join(" ")}`);
    };
    await writeFile(configPath, `schema: opf-registry/1
prompts:
  support.reply:
    renderer: opf
    source: prompts/reply.md
    channels:
      production:
        version: 1.0.0
        digest: ${digest}
`);
    const released = await (await Registry.local(configPath, { gitReader })).get("support.reply", { channel: "production" });
    assert.equal(released.bundle.digest, digest);
    const prepared = released.render({ question: "Hello" });
    assert.equal(prepared.messages[1].content, "Hello");
    assert.equal(prepared.callReceipt({ provider: "openai", model: "chosen-model" }).model, "chosen-model");
    assert.equal(prepared.receipt.question, undefined);

    await writeFile(path.join(root, "prompts/reply.md"), source.replace("briefly", "at length"));
    const stillReleased = await (await Registry.local(configPath, { gitReader })).get("support.reply", { channel: "production" });
    assert.equal(stillReleased.render({ question: "Hello" }).messages[0].content, "Answer briefly.");

    const bundlePath = path.join(root, "release.json");
    await writeFile(bundlePath, JSON.stringify(released.bundle));
    assert.deepEqual((await Registry.fromBundle(bundlePath)).render({ question: "Hello" }).messages, prepared.messages);
    const altered = JSON.parse(await readFile(bundlePath, "utf8"));
    altered.files["prompts/reply.md"] = altered.files["prompts/reply.md"].replace("briefly", "badly");
    await writeFile(bundlePath, JSON.stringify(altered));
    await assert.rejects(Registry.fromBundle(bundlePath), /digest/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("Langfuse remote bundle is checked against the requested digest", async () => {
  const root = await fixture();
  const originalFetch = globalThis.fetch;
  try {
    const draft = await (await Registry.local(path.join(root, "opf.yaml"))).get("support.reply");
    const bundle = { ...draft.bundle, version: "1.0.0", commit: "deadbeef" };
    const remote = {
      type: "chat",
      prompt: [{ role: "system", content: "Answer briefly." }, { role: "user", content: "{{question}}" }],
      config: { opf: { id: "support.reply", version: "1.0.0", bundle_digest: bundle.digest, bundle } },
    };
    globalThis.fetch = async () => new Response(JSON.stringify(remote), { status: 200, headers: { "Content-Type": "application/json" } });
    const registry = Registry.langfuse({ baseUrl: "https://example.invalid", publicKey: "pk", secretKey: "sk" });
    const prompt = await registry.get("support.reply", { version: "1.0.0", expectedDigest: bundle.digest });
    assert.equal(prompt.render({ question: "Hi" }).messages[1].content, "Hi");
    await assert.rejects(registry.get("support.reply", { version: "1.0.0", expectedDigest: `sha256:${"0".repeat(64)}` }), /pinned local release/);
  } finally {
    globalThis.fetch = originalFetch;
    await rm(root, { recursive: true, force: true });
  }
});

test("real Git tag resolution on CI", { skip: process.env.OPF_TEST_REAL_GIT !== "1" }, async () => {
  const root = await fixture();
  try {
    git(root, "init", "-q");
    git(root, "config", "user.name", "OPF Tests");
    git(root, "config", "user.email", "opf@example.invalid");
    git(root, "add", "opf.yaml", "prompts");
    git(root, "commit", "-qm", "initial prompt");
    const registry = await Registry.local(path.join(root, "opf.yaml"));
    const draft = await registry.get("support.reply");
    const annotation = JSON.stringify({ schema: "opf-release/1", id: "support.reply", version: "1.0.0", digest: draft.bundle.digest });
    git(root, "tag", "-a", "opf/support.reply/v1.0.0", "-m", annotation, "HEAD");
    const released = await registry.get("support.reply", { version: "1.0.0" });
    assert.equal(released.bundle.digest, draft.bundle.digest);
    assert.equal(released.bundle.commit, git(root, "rev-parse", "HEAD"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
