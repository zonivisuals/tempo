# ADR-004: BullMQ for Async Job Processing

**Status:** Accepted

**Context:** Video indexing involves multiple sequential/parallel ML steps. These are CPU/GPU intensive and must not block API responses. Need reliable job queuing with retries, progress tracking, and scheduling.

**Decision:** BullMQ with Redis for job orchestration. Each pipeline stage is a separate job queue. Parent jobs fan out to child jobs across queues with dependency tracking.

**Consequences:**
- Positive: Native Node.js, rich features, well-typed job definitions
- Negative: Adds Redis as a runtime dependency
- Neutral: Worker processes can be scaled independently

**Alternatives:**
- Celery — Python-native, but doesn't integrate with TypeScript
- SQS — managed, but more complex job chaining
