// Tempo identity config (Better Auth 1.7.5).
// Verified live against the installed package: endpoint paths
// (/sign-up/email, /sign-in/email, /get-session), bearer header auth,
// {token, user{id,name,email}} and {session{expiresAt,userId}, user} shapes.
// Docs: https://better-auth.com/docs (installation, Postgres adapter,
// bearer + jwt plugins). Auth tables are created by `npm run migrate`
// (Better Auth CLI) — never hand-written (see README + supabase/).
import { betterAuth } from "better-auth";
import { Pool } from "pg";
import { bearer } from "better-auth/plugins/bearer";
import { jwt } from "better-auth/plugins/jwt";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: Number(process.env.PG_POOL_MAX || 10),
});

const socialProviders = {};
if (process.env.GOOGLE_CLIENT_ID) {
  socialProviders.google = {
    clientId: process.env.GOOGLE_CLIENT_ID,
    clientSecret: process.env.GOOGLE_CLIENT_SECRET,
  };
}
if (process.env.GITHUB_CLIENT_ID) {
  socialProviders.github = {
    clientId: process.env.GITHUB_CLIENT_ID,
    clientSecret: process.env.GITHUB_CLIENT_SECRET,
  };
}

export const auth = betterAuth({
  baseURL: process.env.BETTER_AUTH_URL,
  secret: process.env.BETTER_AUTH_API_KEY,
  database: pool,
  emailAndPassword: { enabled: true },
  socialProviders,
  plugins: [bearer(), jwt()],
});
