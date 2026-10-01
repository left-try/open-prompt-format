import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { mkdtemp, cp, rm } from "node:fs/promises";
import os from "node:os";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { OPFError, load, loadById, loadCollection, parse } from "../src/index.ts";

const packageDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(packageDir, "../../..");
const fixture = JSON.parse(await readFile(path.join(root, "fixtures/conformance.json"), "utf8"));

test("shared valid prompt renders expected provider-neutral messages", async () => {
  for (const item of fixture.valid) {
    const prompt = await load(path.join(root, "fixtures", item.file));
    assert.deepEqual(prompt.render(item.inputs), item.expected);
    assert.deepEqual(prompt.metadata.tags, ["conformance", "on", "2026-10-02"]);
    assert.match(prompt.sourceDigest, /^sha256:[0-9a-f]{64}$/);
  }
});

test("shared invalid prompts fail parsing", async () => {
  for (const file of fixture.invalid) {
    await assert.rejects(load(path.join(root, "fixtures", file)), OPFError);
  }
});

test("collection lookup works and duplicate IDs are rejected", async () => {
  const exampleDir = path.join(root, "examples");
  assert.equal((await loadById("support.reply", exampleDir)).metadata.id, "support.reply");
  assert.equal((await loadCollection(exampleDir)).length, 1);
  const temporary = await mkdtemp(path.join(os.tmpdir(), "opf-duplicates-"));
  try {
    await cp(path.join(exampleDir, "support.reply.md"), path.join(temporary, "first.md"));
    await cp(path.join(exampleDir, "support.reply.md"), path.join(temporary, "second.md"));
    await assert.rejects(loadCollection(temporary), /duplicate prompt id/);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});

test("LF, CRLF, and CR normalize to the same digest", async () => {
  const source = await readFile(path.join(root, "examples/support.reply.md"), "utf8");
  const lf = parse(source);
  const crlf = parse(source.replace(/\n/g, "\r\n"));
  const cr = parse(source.replace(/\n/g, "\r"));
  assert.equal(lf.sourceDigest, crlf.sourceDigest);
  assert.equal(lf.sourceDigest, cr.sourceDigest);
});

test("missing and undeclared inputs fail at render time", async () => {
  const prompt = await load(path.join(root, "examples/support.reply.md"));
  assert.throws(() => prompt.render(), /missing required input/);
  assert.throws(() => prompt.render({ customer_message: "hello", extra: "no" }), /undeclared input/);
});
