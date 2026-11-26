import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const cwd = fileURLToPath(new URL("../../backend/", import.meta.url));
const binary = process.env.RAIZ_E2E_PYTHON ||
  (process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const options = { cwd, stdio: "inherit" };
const migration = spawnSync(binary, ["-m", "alembic", "upgrade", "head"], options);
if (migration.status !== 0) process.exit(migration.status ?? 1);
const prepare = spawnSync(binary, ["-m", "tests.e2e_seed"], options);
if (prepare.status !== 0) process.exit(prepare.status ?? 1);
const server = spawn(binary, ["-m", "uvicorn", "app.main:create_app", "--factory", "--port", "8100"], options);
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.kill(signal));
}
server.on("error", (error) => { console.error(error.message); process.exitCode = 1; });
server.on("exit", (code) => { process.exitCode = code ?? 0; });
