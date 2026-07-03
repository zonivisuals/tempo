# ADR-001: Hybrid TypeScript/Python Runtime

**Status:** Accepted

**Context:** The ML ecosystem (Whisper, CLIP, InsightFace, spaCy) is Python-native. The API/web ecosystem benefits from TypeScript's type safety, concurrency model, and ecosystem (Hono, Next.js, Zod). Running everything in one language would compromise either ML quality or API developer experience.

**Decision:** TypeScript serves the API gateway, application services, orchestration, web playground, and docs. Python runs ML workers as separate processes. Communication happens via BullMQ (Redis) for job dispatch and Qdrant/S3 for data exchange.

**Consequences:**
- Positive: Best tool for each job; clear separation of concerns; Python workers can be swapped for cloud APIs without touching the API layer
- Negative: Two runtimes to deploy and monitor; serialization boundary between TypeScript and Python
- Neutral: ML model updates only require redeploying Python workers

**Alternatives:**
- All Python (FastAPI + Celery + Streamlit) — simpler runtime, but weaker API/type ecosystem
- All TypeScript (Transformers.js + ONNX runtime) — single runtime, but significantly worse ML model availability and quality
