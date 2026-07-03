# ADR-002: Modular Monolith (Evolutionary)

**Status:** Accepted

**Context:** Small team, unknown scale requirements, need to ship fast. Premature microservices add operational complexity without proven benefit.

**Decision:** Start as a modular monolith with strict bounded contexts. Each service (Video, Index, Search, Account) is a separate module with well-defined interfaces. Extract to microservices when a module's scaling requirements diverge.

**Consequences:**
- Positive: Single deploy, simple debugging, shared type packages
- Negative: Cannot scale individual modules independently yet
- Neutral: Module boundaries make future extraction straightforward
