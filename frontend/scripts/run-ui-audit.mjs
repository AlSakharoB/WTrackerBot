import { once } from "node:events";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));
const suppliedUrl = process.env.UI_AUDIT_URL;
const port = Number(process.env.UI_AUDIT_PORT ?? "5173");

if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error("UI_AUDIT_PORT must be an integer between 1024 and 65535");
}

let server;
let serverOutput = "";
let serverError;

async function waitForServer(url) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (serverError) {
      throw new Error(`Could not start Vite: ${serverError.message}`);
    }
    if (server && server.exitCode !== null) {
      await new Promise((resolveWait) => setTimeout(resolveWait, 50));
      throw new Error(`Vite exited before UI audit startup:\n${serverOutput}`);
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {
      // Vite is still starting.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(`Timed out waiting for local Vite server:\n${serverOutput}`);
}

async function stopServer() {
  if (!server || server.exitCode !== null) return;
  server.kill("SIGTERM");
  await Promise.race([
    once(server, "exit"),
    new Promise((resolveWait) => setTimeout(resolveWait, 3_000)),
  ]);
  if (server.exitCode === null) {
    server.kill("SIGKILL");
    await once(server, "exit");
  }
}

try {
  if (!suppliedUrl) {
    const auditUrl = `http://127.0.0.1:${port}`;
    process.env.UI_AUDIT_URL = auditUrl;
    server = spawn(
      process.execPath,
      [
        resolve(frontendRoot, "node_modules/vite/bin/vite.js"),
        "--host",
        "127.0.0.1",
        "--port",
        String(port),
        "--strictPort",
      ],
      {
        cwd: frontendRoot,
        env: process.env,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const recordOutput = (chunk) => {
      serverOutput = `${serverOutput}${chunk}`.slice(-8_192);
    };
    server.stdout.on("data", recordOutput);
    server.stderr.on("data", recordOutput);
    server.on("error", (error) => {
      serverError = error;
    });
    await waitForServer(auditUrl);
  }
  await import("./capture-ui-baseline.mjs");
} finally {
  await stopServer();
}
