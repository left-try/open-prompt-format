import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const require = createRequire(import.meta.url);
const renderOpfPrompt = require("../../../adapters/promptfoo.cjs");

test("Promptfoo adapter ignores its internal variables and renders declared inputs", async () => {
  const originalPromptFile = process.env.OPF_PROMPT_FILE;
  process.env.OPF_PROMPT_FILE = path.join(repoRoot, "examples/support.reply.md");

  try {
    const messages = await renderOpfPrompt({
      vars: {
        customer_message: "My order is late.",
        __evalId: "eval-123",
        __evalStepId: "step-456",
        __repeatIndex: "0",
      },
    });

    assert.deepEqual(messages, [
      {
        role: "system",
        content: "You help customers with order questions. Be concise, kind, and factual.\nDo not invent order details. If key information is missing, ask one clear question.",
      },
      { role: "user", content: "My order is late." },
    ]);
  } finally {
    if (originalPromptFile === undefined) delete process.env.OPF_PROMPT_FILE;
    else process.env.OPF_PROMPT_FILE = originalPromptFile;
  }
});
