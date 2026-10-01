const path = require("node:path");
const { pathToFileURL } = require("node:url");

module.exports = async function renderOpfPrompt({ vars }) {
  const promptFile = process.env.OPF_PROMPT_FILE;
  if (!promptFile) {
    throw new Error("Set OPF_PROMPT_FILE to the repo-relative path of an OPF prompt file.");
  }
  const loaderPath = path.resolve(__dirname, "../packages/typescript/dist/index.js");
  const { load } = await import(pathToFileURL(loaderPath).href);
  const prompt = await load(path.resolve(process.cwd(), promptFile));
  return prompt.render(vars ?? {});
};
