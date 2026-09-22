# tempo-auth — identity service (Better Auth 1.7.5 + Postgres)

Email+password and Google/GitHub login for Tempo. The Python sidecar never
touches passwords after login: it validates the opaque session token against
`GET /api/auth/get-session` (Bearer) and caches by `expiresAt`.

## Run

```sh
cd auth
cp .env.example .env   # fill secrets; .env is gitignored
npm install
npm run migrate        # Better Auth CLI creates auth tables (never hand-made)
npm start              # 127.0.0.1:18099
```

Dev database: any Postgres (Supabase free tier works, no card). Tables for
auth itself are CLI-managed; app tables live in `supabase/`.

## Verified wire shapes (better-auth 1.7.5, observed live — do not guess)

- `POST /api/auth/sign-up/email {name,email,password}` → `{token, user{id,…}}`
- `POST /api/auth/sign-in/email {email,password}` → `{redirect, token, user{…}}`
  + `Set-Cookie: better-auth.session_token=…`
- `GET /api/auth/get-session` + `Authorization: Bearer <token>` →
  `{session{expiresAt,userId,…}, user{…}}`; invalid/absent → `null`
- `GET /api/auth/token` (jwt plugin) → `{token: <EdDSA JWT>}` (reserved for
  service-to-service; the sidecar uses opaque sessions, not JWTs)

## OAuth setup (optional)

Google: console.cloud.google.com → Credentials → OAuth client → Authorized
redirect URI `<BETTER_AUTH_URL>/api/auth/callback/google`. Same pattern for
GitHub (Settings → Developer settings). Put ids/secrets in `.env`.
