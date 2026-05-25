import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const frontendRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const projectRoot = resolve(frontendRoot, "..");
const generator = resolve(projectRoot, "scripts", "generate_frontend_api.py");

const candidates = [
  process.env.PYTHON ? { command: process.env.PYTHON, args: [] } : null,
  { command: resolve(projectRoot, ".venv", "bin", "python"), args: [] },
  { command: resolve(projectRoot, ".venv", "Scripts", "python.exe"), args: [] },
  { command: "python3", args: [] },
  { command: "python", args: [] },
  { command: "py", args: ["-3"] }
].filter(Boolean);

let lastError = "";

for (const candidate of candidates) {
  if (candidate.command.includes(".venv") && !existsSync(candidate.command)) {
    continue;
  }

  const result = spawnSync(candidate.command, [...candidate.args, generator], {
    cwd: frontendRoot,
    encoding: "utf8",
    stdio: "inherit"
  });

  if (result.status === 0) {
    process.exit(0);
  }
  if (result.error) {
    lastError = result.error.message;
  }
}

console.error("Unable to generate API client. Install backend dependencies or set PYTHON to the target interpreter.");
if (lastError) {
  console.error(lastError);
}
process.exit(1);
