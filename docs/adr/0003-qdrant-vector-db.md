# ADR-003: Qdrant for Vector Storage

**Status:** Accepted

**Context:** Need high-dimensional vector search (512d CLIP visual, 384d MiniLM text, 512d ArcFace face) with payload filtering. Must be self-hostable for cost control.

**Decision:** Qdrant as the vector database. Self-hosted via Docker for MVP. Key features leveraged: payload filtering, multiple named vectors per point, HNSW index.

**Consequences:**
- Positive: Open source, no per-vector cost, excellent filtering, good performance
- Negative: Self-hosting adds operational overhead
- Neutral: Can migrate to Pinecone later if needed

**Alternatives:**
- Pinecone — managed, expensive at scale, vendor lock-in
- pgvector — simpler, but mixed vector+metadata queries are slower
- Milvus — more complex to operate
