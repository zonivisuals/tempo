# Tempo — Video Semantic Search API Architecture

## Overview

Tempo is a commercial API for video semantic search. It ingests videos, indexes their content across multiple modalities (visual scenes, speech/transcript, faces), and returns precise timestamped results from natural language queries.

The system serves startups and SaaS products that need to add video search capabilities — find "the moment John mentions Q3 revenue" or "the foggy mountain drone shot" — without building their own ML pipeline.

---

## Requirements

### Functional

- Submit videos (by URL or upload) for asynchronous indexing
- Search indexed videos using natural language queries
- Support multi-modal search: visual scenes, spoken content, named entities, faces
- Return ranked results with precise timestamps, thumbnails, and transcript snippets
- Provide API key-based authentication for multi-tenant usage
- Offer a web playground for interactive testing
- Provide developer documentation with interactive examples

### Non-Functional

| Category | Target |
|----------|--------|
| API p95 latency | < 500ms for search (excluding network) |
| Index throughput | 10x realtime (a 10min video indexes in < 1min) |
| Availability | 99.9% (8.76h downtime/yr) |
| Search accuracy | MRR > 0.75 on golden test set |
| Max video size | 2GB / 60 minutes per submission |
| Concurrent users (MVP) | 100 |
| RPO | 1 hour |
| RTO | 4 hours |

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐ │
│  │  API Client     │  │  Web Playground  │  │  Docs Portal           │ │
│  │  (cURL / SDK)   │  │  (Next.js)       │  │  (Next.js + MDX)       │ │
│  └────────┬────────┘  └────────┬─────────┘  └───────────┬─────────────┘ │
└───────────┼────────────────────┼────────────────────────┼───────────────┘
            │                    │                        │
┌───────────▼────────────────────▼────────────────────────▼───────────────┐
│                         API GATEWAY (Hono)                              │
│  ┌──────────────┐ ┌───────────┐ ┌───────────┐ ┌────────────────────┐   │
│  │ Rate Limiter │ │ Auth      │ │ API Key   │ │ Request Validation │   │
│  │              │ │ (JWT/Bear)│ │ Mgmt      │ │ (Zod)              │   │
│  └──────────────┘ └───────────┘ └───────────┘ └────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                      APPLICATION SERVICES (TypeScript)                  │
│                                                                         │
│  ┌─────────────────┐  ┌────────────────┐  ┌────────────────────────┐   │
│  │   Video Service  │  │  Index Service │  │    Search Service      │   │
│  │  ─ upload/validate│  │  ─ orchestrate │  │  ─ cascade pipeline   │   │
│  │  ─ manage metadata│  │    indexing     │  │  ─ fused scoring     │   │
│  │  ─ S3 presigned   │  │  ─ track progress│ │  ─ cluster expansion  │   │
│  └────────┬─────────┘  └───────┬────────┘  └───────────┬────────────┘   │
│           │                    │                        │               │
│  ┌────────▼────────────────────▼────────────────────────▼────────────┐  │
│  │                    BullMQ (Redis)                                  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │  │
│  │  │ Scene Detect │ │ Transcription│ │ Embedding    │              │  │
│  │  │ Queue        │ │ Queue        │ │ Queue        │              │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘              │  │
│  └──────┬─────────────────┬──────────────────┬──────────────────────┘  │
│         │                 │                  │                         │
│  ┌──────▼──────┐ ┌───────▼────────┐ ┌───────▼──────────┐              │
│  │  PostgreSQL  │ │    Qdrant      │ │  S3 / MinIO     │              │
│  │  ─ metadata  │ │  ─ Visual vec  │ │  ─ raw videos   │              │
│  │  ─ api keys  │ │  ─ Text vec    │ │  ─ keyframes    │              │
│  │  ─ transcripts│ │  ─ Face vec    │ │  ─ thumbnails   │              │
│  │  ─ user data  │ │  ─ with payload│ │  ─ transcripts  │              │
│  └──────────────┘ └────────────────┘ └─────────────────┘              │
└────────────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                      ML WORKERS (Python)                                │
│                                                                         │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │
│  │  Scene Detect  │ │  Transcription │ │  Visual Embed  │              │
│  │  Worker        │ │  Worker        │ │  Worker        │              │
│  │  (PySceneDetec │ │  (Whisper)     │ │  (CLIP ViT)    │              │
│  │  + OpenCV)     │ │                │ │                │              │
│  └────────────────┘ └────────────────┘ └────────────────┘              │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │
│  │  Text Embed    │ │  Face Detect   │ │  NER Worker    │              │
│  │  Worker        │ │  Worker        │ │  (spaCy)       │              │
│  │  (MiniLM)      │ │  (InsightFace) │ │                │              │
│  └────────────────┘ └────────────────┘ └────────────────┘              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## System Design Decisions (ADRs)

### ADR-001: Hybrid TypeScript/Python Runtime

**Status:** Accepted

**Context:** The ML ecosystem (Whisper, CLIP, InsightFace, spaCy) is Python-native. The API/web ecosystem benefits from TypeScript's type safety, concurrency model, and ecosystem (Hono, Next.js, Zod). Running everything in one language would compromise either the ML quality or the API developer experience.

**Decision:** TypeScript serves the API gateway, application services, orchestration, web playground, and docs. Python runs ML workers as separate processes. Communication happens via BullMQ (Redis) for job dispatch and Qdrant/S3 for data exchange.

**Consequences:**
- Positive: Best tool for each job; clear separation of concerns; Python workers can be swapped for cloud APIs without touching the API layer
- Negative: Two runtimes to deploy and monitor; serialization boundary between TypeScript and Python
- Neutral: ML model updates only require redeploying Python workers

**Alternatives:**
- All Python (FastAPI + Celery + Streamlit) — simpler runtime, but weaker API/type ecosystem and harder to build the commercial product surface
- All TypeScript (Transformers.js + ONNX runtime) — single runtime, but ML model availability and quality is significantly worse than Python equivalents

---

### ADR-002: Modular Monolith (Evolutionary)

**Status:** Accepted

**Context:** Small team, unknown scale requirements, need to ship fast. Premature microservices add operational complexity without proven benefit.

**Decision:** Start as a modular monolith with strict bounded contexts. Each service (Video, Index, Search, Account) is a separate module within the same deployment with well-defined interfaces. Extract to microservices when a module's scaling requirements diverge.

**Project structure mirrors bounded contexts:**
```
apps/api/src/
  modules/
    video/     — upload, metadata CRUD
    index/     — indexing orchestration, job tracking
    search/    — cascade pipeline, fused scoring
    account/   — API keys, billing, teams
```

**Consequences:**
- Positive: Single deploy, simple debugging, shared type packages
- Negative: Cannot scale individual modules independently yet
- Neutral: Module boundaries make future extraction straightforward

---

### ADR-003: Qdrant for Vector Storage

**Status:** Accepted

**Context:** Need high-dimensional vector search (512d CLIP visual, 384d MiniLM text, 512d ArcFace face) with payload filtering (filter by video_id, face presence). Must be self-hostable for cost control.

**Decision:** Qdrant as the vector database. Self-hosted via Docker for MVP. Key features leveraged: payload filtering, multiple named vectors per point, HNSW index.

**Vector collection design:**
```
Collection: "shots"
┌──────────────┬──────────────┬──────────────┐
│ visual       │ text         │ face         │
│ (512d, IP)   │ (384d, IP)   │ (512d, IP)   │
│ CLIP emb     │ MiniLM emb   │ ArcFace emb  │
└──────────────┴──────────────┴──────────────┘
Payload: { video_id, shot_id, start_time, end_time,
           transcript, entities[], has_face }
```

**Consequences:**
- Positive: Open source, no per-vector cost, excellent filtering, good performance
- Negative: Self-hosting adds operational overhead; not as fast as Pinecone at extreme scale
- Neutral: Can migrate to Pinecone later if needed (same ANN interface pattern)

**Alternatives:**
- Pinecone — managed, expensive at scale ($0.10/GB/hr), vendor lock-in
- pgvector — simpler setup, but mixed vector+metadata queries are slower; Qdrant's filtering is more efficient
- Milvus — more complex to operate; Qdrant is lighter weight

---

### ADR-004: BullMQ for Async Job Processing

**Status:** Accepted

**Context:** Video indexing involves multiple sequential/parallel ML steps (scene detection → transcribe + embed frames + detect faces). These are CPU/GPU intensive and must not block API responses. Need reliable job queuing with retries, progress tracking, and scheduling.

**Decision:** BullMQ with Redis for job orchestration. Each pipeline stage is a separate job queue. A parent job (the video index request) fans out to child jobs across queues with dependency tracking.

**Queue topology:**
```
index-video (parent job)
  ├── detect-scenes
  │   ├── extract-keyframes ─── embed-visual (CLIP)
  │   └── transcribe-audio (Whisper)
  │       └── extract-entities (spaCy) ─── embed-text (MiniLM)
  └── detect-faces (InsightFace)
```
All parallel branches must complete before the parent job resolves.

**Consequences:**
- Positive: Native Node.js, rich features (delays, rate limiting, repeatable jobs), well-typed job definitions
- Negative: Adds Redis as a runtime dependency; jobs are in-memory (must be persisted to PG for audit)
- Neutral: Worker processes can be scaled independently

**Alternatives:**
- Celery — Python-native, but adds another runtime dependency (RabbitMQ/Redis) and doesn't integrate with TypeScript
- SQS — managed, but more complex job chaining; BullMQ's parent/child pattern is cleaner
- In-process background threads — loses durability; workers would block the API process

---

### ADR-005: Hono as API Framework

**Status:** Accepted

**Context:** Need a TypeScript API framework that is fast, lightweight, has excellent TypeScript support, and works well with Zod for request validation.

**Decision:** Hono for the API server, with Zod for schema validation and OpenAPI generation via `@hono/zod-openapi`.

**Consequences:**
- Positive: Ultrafast (~14k req/s), <10KB bundle, edge-ready, first-class Zod integration generates OpenAPI spec automatically
- Negative: Smaller ecosystem than Express; fewer middleware options (but adequate for our needs)
- Neutral: If we outgrow Hono, switching to Fastify or NestJS is manageable since business logic is in separate service modules

---

### ADR-006: Modal for GPU ML Workers (MVP)

**Status:** Accepted

**Context:** ML workers (Whisper, CLIP) require GPU for acceptable performance. Managing GPU infrastructure is complex and expensive. Need a serverless GPU solution for rapid development.

**Decision:** Use Modal for Python ML worker deployment in the MVP phase. Modal functions are triggered via webhooks from BullMQ workers. A TypeScript worker picks up a BullMQ job, calls the Modal function, and waits for the result.

**Flow:**
```
BullMQ job ──► TypeScript worker ──HTTP POST──► Modal function (GPU)
                                                      │
                  Modal function writes results ◄─────┘
                  to S3 / Qdrant directly
                                                      │
                  Worker marks job complete ──────────┘
```

**Consequences:**
- Positive: No GPU cluster management, pay per second of GPU time, cold starts ~2s for model loading
- Negative: Vendor dependency for GPU compute; variable cost per job
- Neutral: Can migrate to self-hosted GPU later when load justifies it

**Alternatives:**
- Self-hosted GPU on AWS (EC2 G4/G5) — more control, but requires GPU instance management, auto-scaling, and higher fixed cost
- Replicate — managed but limited model customization; not suitable for custom Whisper/CLIP pipelines
- AWS SageMaker — powerful but heavy for MVP

---

## Data Flow

### Indexing Pipeline

```
1. POST /v1/videos { url: "https://..." }
2. API validates URL, creates DB record (status: "pending")
3. Enqueues BullMQ job "index-video"
4. Worker picks up job:
   a. Download video to S3/MinIO
   b. Queue "detect-scenes" subtask
      - PySceneDetect splits video into shots
      - For each shot: extract keyframe → S3
      - Queue "embed-visual" per keyframe (CLIP → Qdrant)
      - Queue "transcribe-audio" (Whisper → text chunks)
        - Queue "extract-entities" (spaCy NER → PG)
        - Queue "embed-text" (MiniLM → Qdrant)
   c. Queue "detect-faces" per keyframe (InsightFace → Qdrant + PG)
   d. Wait for all subtasks to complete
5. Update DB record (status: "ready")
6. Trigger webhook if configured
```

### Search Pipeline

```
1. POST /v1/search { query: "Lewis on a foggy mountain", video_ids: [...] }
2. Parse query with spaCy:
   - Extract PERSON entities → ["Lewis"]
   - Extract concepts → "foggy mountain"
3. Stage 1 — Visual Gatekeeper:
   - Embed query text with CLIP text encoder
   - Qdrant search: visual index, top K=50 candidates
   - Filter by video_ids if specified
4. Stage 2 — Face Filter (if person detected):
   - For each candidate, check face collection for "Lewis match"
   - Boost or filter candidates by face presence
5. Stage 3 — Text Re-ranking:
   - Embed concepts with MiniLM
   - Compute cosine similarity against top 50 candidates
6. Fused Scoring:
   - score = 0.7 * visual_score + 0.3 * text_score
   - face_match → +0.5 boost
   - Sort by score descending
7. Cluster Expansion:
   - For top result, expand with visually similar shots (same cluster)
8. Return top K results with timestamps, thumbnails, transcript
```

---

## Project Structure

```
tempo/
├── apps/
│   ├── api/                          # Hono API server
│   │   ├── src/
│   │   │   ├── index.ts              # Entry point
│   │   │   ├── app.ts                # Hono app setup + middleware
│   │   │   ├── modules/
│   │   │   │   ├── video/            # Video CRUD + upload handlers
│   │   │   │   ├── index/            # Indexing orchestration handlers
│   │   │   │   ├── search/           # Search endpoint handlers
│   │   │   │   └── account/          # API key, billing, teams
│   │   │   ├── middleware/           # Auth, rate limit, error handling
│   │   │   └── lib/                  # DB clients, S3 client, queue client
│   │   ├── Dockerfile
│   │   └── package.json
│   │
│   ├── web/                          # Next.js playground + docs
│   │   ├── app/
│   │   │   ├── playground/           # Interactive API sandbox
│   │   │   ├── docs/                 # Developer documentation (MDX)
│   │   │   └── landing/              # Public marketing page
│   │   ├── components/
│   │   ├── content/                  # MDX docs
│   │   └── package.json
│   │
│   └── worker/                       # BullMQ worker (orchestration)
│       ├── src/
│       │   ├── index.ts              # Worker entry
│       │   ├── jobs/
│       │   │   ├── index-video.ts    # Parent job orchestrator
│       │   │   ├── detect-scenes.ts
│       │   │   ├── transcribe.ts
│       │   │   ├── embed-visual.ts
│       │   │   ├── embed-text.ts
│       │   │   └── detect-faces.ts
│       │   └── clients/              # S3, Qdrant, Modal clients
│       └── package.json
│
├── packages/
│   ├── core/                         # Shared types, enums, constants
│   │   ├── src/
│   │   │   ├── types.ts              # Video, Shot, SearchResult, etc.
│   │   │   ├── enums.ts              # VideoStatus, JobStatus, etc.
│   │   │   └── constants.ts          # Embedding dims, thresholds
│   │   └── package.json
│   │
│   ├── db/                           # Database schema + migrations
│   │   ├── src/
│   │   │   ├── schema/               # Drizzle ORM schema
│   │   │   ├── migrations/
│   │   │   └── seed.ts
│   │   ├── drizzle.config.ts
│   │   └── package.json
│   │
│   └── search/                       # Search logic (framework-agnostic)
│       ├── src/
│       │   ├── cascade.ts            # Cascade search pipeline
│       │   ├── scorer.ts             # Fused scoring
│       │   ├── expander.ts           # Cluster expansion
│       │   └── parser.ts             # Query parsing (NER, concept extraction)
│       └── package.json
│
├── ml/                               # Python ML workers (Modal)
│   ├── core/                         # Shared ML utilities
│   ├── workers/
│   │   ├── detect_scenes.py
│   │   ├── transcribe.py
│   │   ├── embed_visual.py
│   │   ├── embed_text.py
│   │   └── detect_faces.py
│   ├── requirements.txt
│   ├── modal_config.py              # Modal app configuration
│   └── pyproject.toml
│
├── docs/
│   ├── adr/                          # Architecture Decision Records
│   │   ├── 0001-hybrid-runtime.md
│   │   ├── 0002-modular-monolith.md
│   │   ├── 0003-qdrant-vector-db.md
│   │   ├── 0004-bullmq-job-queue.md
│   │   ├── 0005-hono-api-framework.md
│   │   └── 0006-modal-gpu-workers.md
│   └── runbooks/                     # Operational runbooks
│
├── infra/                            # Infrastructure
│   ├── docker-compose.yml            # Local dev setup
│   ├── terraform/                    # Production infrastructure
│   └── scripts/                      # Utility scripts
│
├── turbo.json                        # Turborepo config
├── package.json                      # Workspace root
└── pnpm-workspace.yaml              # pnpm workspace config
```

---

## API Surface (v1)

```
POST   /v1/videos                    # Submit video for indexing
GET    /v1/videos                    # List videos
GET    /v1/videos/:id                # Get video details + status
DELETE /v1/videos/:id                # Delete video + all indexed data

POST   /v1/search                    # Search indexed videos
GET    /v1/search/:id                # Poll async search results

GET    /v1/indexes/:id/stats         # Index statistics (shot count, duration)

POST   /v1/account/keys              # Create API key
GET    /v1/account/keys              # List API keys
DELETE /v1/account/keys/:id          # Revoke API key

POST   /v1/webhooks                  # Configure webhook URL
GET    /v1/webhooks                  # List webhooks
DELETE /v1/webhooks/:id              # Remove webhook
```

### Search Request/Response Example

```jsonc
// POST /v1/search
{
  "query": "Lewis standing near a foggy mountain",
  "video_ids": ["vid_abc123"],        // optional, filter to specific videos
  "top_k": 5,
  "include_faces": true,
  "include_expansion": true
}

// Response 200
{
  "query_id": "qry_xyz789",
  "results": [
    {
      "shot_id": 42,
      "video_id": "vid_abc123",
      "score": 0.89,
      "start_time": 143.2,
      "end_time": 148.7,
      "transcript": "This is Lewis by the way. If you don't know who Lewis is...",
      "entities": ["Lewis"],
      "thumbnail_url": "https://storage.tempo.ai/...",
      "has_face": true
    }
  ],
  "expanded_cluster": [
    { "shot_id": 43, "start_time": 148.7, "end_time": 152.1, "thumbnail_url": "..." },
    { "shot_id": 44, "start_time": 152.1, "end_time": 156.3, "thumbnail_url": "..." }
  ],
  "timing": {
    "stage1_visual": 12,
    "stage2_face": 3,
    "stage3_text": 45,
    "total": 60
  }
}
```

---

## Deployment Architecture (MVP)

```
                    ┌──────────────────────┐
                    │   Cloudflare DNS      │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Load Balancer       │
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
┌─────────▼────────┐ ┌────────▼───────┐ ┌─────────▼────────┐
│  API (Hono)      │ │  Web (Next.js) │ │  Worker (BullMQ) │
│  x2 container    │ │  x1 container  │ │  x1 container    │
│  (Fly.io/Railway)│ │  (Vercel)      │ │  (Fly.io/Railway)│
└─────────┬────────┘ └────────────────┘ └─────────┬────────┘
          │                                       │
          │                                       │
┌─────────▼───────────────────────────────────────▼──────────────────┐
│                     Redis (Upstash / self-hosted)                   │
│                     BullMQ queue + caching                          │
└────────────────────────────────────────────────────────────────────┘
          │                                       │
          │                                       │
┌─────────▼───────────────────────────────────────▼──────────────────┐
│                     PostgreSQL (Neon / Supabase)                    │
│                     Metadata, API keys, transcripts                 │
└────────────────────────────────────────────────────────────────────┘
          │                                       │
          │                                       │
┌─────────▼───────────────────────────────────────▼──────────────────┐
│                     Qdrant (self-hosted Docker)                     │
│                     Vector search index                             │
└────────────────────────────────────────────────────────────────────┘
          │                                       │
          │                                       │
┌─────────▼───────────────────────────────────────▼──────────────────┐
│                     S3 / MinIO                                      │
│                     Raw videos, keyframes, thumbnails               │
└────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────┐
                    │  Modal (Serverless GPU)           │
                    │  Python ML workers                │
                    │  ┌─────┐┌──────┐┌──────┐┌─────┐ │
                    │  │Scene││Whispe││CLIP ││Face │ │
                    │  │Det  ││r     ││     ││Det  │ │
                    │  └─────┘└──────┘└──────┘└─────┘ │
                    └──────────────────────────────────┘
```

---

## Security Considerations

- **API Authentication:** Bearer token via `Api-Key` header. Keys are hashed with bcrypt in the database. Only the full key is shown once at creation.
- **Rate Limiting:** 100 req/min per API key (search). 10 req/min per key (indexing). Implemented at the Hono middleware layer.
- **Video Validation:** Validate file type, size, and duration before accepting. Scan with ClamAV for uploaded files.
- **Data Isolation:** Each tenant's vectors in Qdrant are isolated via payload filtering (video_id scoped to API key's team). PostgreSQL queries filter by team_id.
- **Encryption:** All traffic over TLS 1.3. At-rest encryption on S3 and database.
- **Webhook Signing:** Webhook payloads signed with HMAC-SHA256 using the team's webhook secret.

---

## Monitoring & Observability

| Signal | Tool | What |
|--------|------|------|
| Logs | Structured JSON to stdout | Request/response, job lifecycle, ML worker output |
| Metrics | Prometheus + Grafana | Request rate, latency p50/p95/p99, job queue depth, ML worker duration |
| Tracing | OpenTelemetry | End-to-end trace from API request → BullMQ → Modal → Qdrant |
| Alerts | Sentry + Slack | Error rate > 1%, queue depth > 100, search latency > 1s p95 |
| Dashboards | Grafana | System health, per-tenant usage, cost breakdown |

---

## Scaling Strategy

### Phase 1 — MVP (Months 1-3)
- Modular monolith on single VPS (Docker Compose)
- Modal for GPU workers
- Qdrant single node
- Up to 100 concurrent users, 10GB indexed video

### Phase 2 — Growth (Months 3-6)
- Extract search service into separate process (first microservice)
- Qdrant cluster (3 nodes)
- Auto-scaling API containers (2-6 instances via Fly.io)
- PostgreSQL read replicas for search metadata
- Up to 1K concurrent users, 100GB indexed video

### Phase 3 — Scale (Months 6+)
- Full microservice extraction as needed
- GPU workers on self-hosted instances (Modal cost-optimization)
- Qdrant sharded cluster
- Multi-region deployment
- CDN for keyframe/thumbnail delivery
- Up to 10K concurrent users, 1TB+ indexed video

---

## Key Metrics & Success Criteria

| Metric | Target | Why |
|--------|--------|-----|
| Index latency | <1min for 10min video | Users won't wait long for indexing |
| Search p95 | <500ms | Must feel instant |
| MRR (Mean Reciprocal Rank) | >0.75 | Top result should be relevant |
| API uptime | 99.9% | Commercial SLA requirement |
| Time to first search | <5min from signup | Quick time-to-value |
