import { randomBytes } from "node:crypto";
import { defineConfig } from "@playwright/test";

const secret = randomBytes(32).toString("hex");
const nonce = randomBytes(8).toString("hex");
const origin = "http://localhost:3100";
const endpoint = "http://127.0.0.1:8100";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    baseURL: origin,
    actionTimeout: 12_000,
    channel: process.env.RAIZ_E2E_BROWSER || undefined,
  },
  webServer: [
    {
      command: "node e2e/backend.mjs",
      url: `${endpoint}/api/health`,
      env: {
        APP_ENV: "test",
        DATABASE_URL: `sqlite:///./.data/e2e/${nonce}.db`,
        FRONTEND_URL: origin,
        JWT_SECRET_KEY: secret,
        ENCRYPTION_KEY: randomBytes(32).toString("base64url") + "=",
        SMTP_MODE: "mock",
      },
    },
    {
      command: "npm run dev -- --port 3100",
      url: origin,
      env: { RAIZ_BACKEND_URL: endpoint },
      timeout: 45_000,
    },
  ],
});
