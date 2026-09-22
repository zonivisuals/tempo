-- Tempo app tables (Supabase Postgres). Auth's own tables (user, session,
-- account, verification, jwks) are created by `npm run migrate` in auth/
-- (Better Auth CLI) — never hand-written here.
--
-- Apply: psql "$DATABASE_URL" -f supabase/licenses.sql
-- user_id references Better Auth's user.id (text ids).

create table if not exists licenses (
  user_id    text primary key,
  plan       text not null default 'free'
             check (plan in ('free', 'pro', 'studio')),
  footage_max_quota int not null default 1,
  minutes_quota     int not null default 7,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists licenses_plan_idx on licenses (plan);
