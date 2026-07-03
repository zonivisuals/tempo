# ADR-006: Modal for GPU ML Workers (MVP)

**Status:** Accepted

**Context:** ML workers (Whisper, CLIP) require GPU for acceptable performance. Managing GPU infrastructure is complex and expensive.

**Decision:** Use Modal for Python ML worker deployment in the MVP phase. Modal functions are triggered via webhooks from BullMQ workers.

**Consequences:**
- Positive: No GPU cluster management, pay per second of GPU time
- Negative: Vendor dependency for GPU compute; variable cost per job
- Neutral: Can migrate to self-hosted GPU later when load justifies it

**Alternatives:**
- Self-hosted GPU on AWS (EC2 G4/G5) — more control, but higher fixed cost
- SageMaker — powerful but heavy for MVP
