# Tempo — Agent Guide

## Stack

- **Monorepo**: pnpm workspace + Turborepo (Node >=22, pnpm >=10.8)
- **API**: Hono + Zod (apps/api)
- **Web app**: Next.js (apps/web)
- **Orchestration**: BullMQ via Redis (apps/worker)
- **DB**: PostgreSQL + Drizzle ORM (packages/db)
- **Vector DB**: Qdrant (self-hosted via docker-compose)
- **Storage**: S3-compatible via MinIO (docker-compose) or S3
- **ML workers**: Python 3.12+ via Modal (ml/)

## Key Commands

```sh
pnpm install              # install all workspace dependencies
pnpm dev                  # turbo dev (all apps in parallel)
pnpm build                # turbo build
pnpm lint                 # turbo lint (tsc --noEmit per package)
pnpm typecheck            # turbo typecheck (dependsOn build)
pnpm test                 # turbo test (vitest in packages/search)
pnpm clean                # turbo clean
pnpm format               # prettier on .ts,.tsx,.md,.json
pnpm db:generate          # drizzle-kit generate
pnpm db:migrate           # drizzle-kit migrate
pnpm db:seed              # seed script
```

## Required Services (for local dev)

```sh
docker compose up -d      # starts postgres, redis, qdrant, minio
cp .env.example .env.local # then fill in secrets
```

## Workspace Packages

| Path | Package | What |
|------|---------|------|
| `apps/api` | `@tempo/api` | Hono API server with Zod validation |
| `apps/web` | `@tempo/web` | Next.js playground + docs |
| `apps/worker` | `@tempo/worker` | BullMQ job orchestration |
| `packages/core` | `@tempo/core` | Shared types, constants, enums |
| `packages/db` | `@tempo/db` | Drizzle schema + migrations |
| `packages/search` | `@tempo/search` | Cascade search logic (vitest tests) |
| `ml/` | `tempo-ml` (Python) | Whisper, CLIP, MiniLM, InsightFace via Modal |

## Architecture Rules

- **Hybrid runtime**: TypeScript for API/orchestration, Python for ML workers. Never call Python ML libraries from TypeScript directly — always go through Modal/BullMQ.
- **Modular monolith**: Each module in `apps/api/src/modules/` has a clear bounded context (video, index, search, account). Module boundaries are respected — no cross-module imports.
- **No `any` types**: TS strict mode with `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noUnusedLocals`, `noUnusedParameters`.
- **Async indexing**: All video processing is async via BullMQ queues. API returns immediately with a job ID. Webhooks or polling for completion.
- **Search pipeline**: Cascade with 3 stages: visual (Qdrant) → face filter → text re-rank. Constants in `@tempo/core` constants.

## DB Schema

Tables: `videos`, `shots`, `api_keys` (see `packages/db/src/schema/videos.ts`).
UUID primary keys with `defaultRandom()`. Migrations via Drizzle Kit.

## Embedding Dimensions

- CLIP visual: 512d, inner product
- MiniLM text: 384d, inner product
- ArcFace face: 512d, inner product
- Qdrant collection uses named vectors per point (visual, text, face)

## ML Workers

Located in `ml/`. Python 3.12. Each worker is a Modal function with A10G GPU. Worker functions: `detect_scenes`, `transcribe`, `embed_visual`, `embed_text`, `detect_faces`. Triggered by TypeScript BullMQ workers via Modal webhooks.

## Conventions

- Use `workspace:*` for inter-package dependencies
- All packages are `"type": "module"` — use `.js` extensions in imports
- Turbo pipeline: `test` depends on `build`; `typecheck` depends on `^build`
- Single `tsconfig.json` at root, each package extends it
- ML Python deps in both `pyproject.toml` and `requirements.txt`
