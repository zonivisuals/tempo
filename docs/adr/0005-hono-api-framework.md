# ADR-005: Hono as API Framework

**Status:** Accepted

**Context:** Need a TypeScript API framework that is fast, lightweight, has excellent TypeScript support, and works well with Zod for request validation.

**Decision:** Hono for the API server, with Zod for schema validation and OpenAPI generation via `@hono/zod-openapi`.

**Consequences:**
- Positive: Ultrafast (~14k req/s), <10KB bundle, edge-ready, first-class Zod integration
- Negative: Smaller ecosystem than Express
