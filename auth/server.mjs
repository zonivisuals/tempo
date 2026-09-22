// Tempo auth service entrypoint.
// Mounts Better Auth on Express; all auth UI lives in the CEP panel, which
// calls these routes over HTTPS. Env documented in .env.example.
// Docs: https://better-auth.com/docs/installation (mount handler),
// Express 5 wildcard routes (/{*any}). dotenv loads first so `.env` values
// are visible to the checks below and to auth.mjs (plain node has no
// dotenv otherwise — missing vars would fail even with a filled `.env`).
import "dotenv/config";
import express from "express";
import { toNodeHandler } from "better-auth/node";
import { auth } from "./auth.mjs";

for (const name of ["BETTER_AUTH_API_KEY", "BETTER_AUTH_URL", "DATABASE_URL"]) {
  if (!process.env[name]) {
    console.error(`missing env: ${name} (see .env.example)`);
    process.exit(1);
  }
}

const app = express();
app.all("/api/auth/{*any}", toNodeHandler(auth));
app.get("/health", (_req, res) => res.json({ status: "ok", service: "tempo-auth" }));

const port = Number(process.env.PORT || 18099);
app.listen(port, "127.0.0.1", () => console.log(`tempo-auth on 127.0.0.1:${port}`));
