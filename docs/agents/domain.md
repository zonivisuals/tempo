# Domain Docs

How the engineering skills should consume this repo's domain documentation when
exploring the codebase.

## Before exploring, read these

- **`AGENTS.md`** at the repo root. This is the binding spec for the whole project:
  architecture (§2), API contracts (§3), panel and host rules (§4), feature
  acceptance criteria (§5), UI rules (§6), coding standards (§7), and the decisions
  log (§12). Read it before proposing anything that touches those areas.
- **`PRODUCT.md`** for product vision and scope.
- **`docs/decisions/`**: the ADR log. Files are `NNNN-slug.md`, indexed in
  `docs/decisions/README.md`. Read the ones that touch the area you're working in.

> This repo predates the `docs/adr/` + `GLOSSARY.md` convention these skills
> assume. **The ADRs live in `docs/decisions/`, and there is no `GLOSSARY.md`.**
> Do not create `docs/adr/`. Do not look for `GLOSSARY.md` and report it missing;
> the domain vocabulary lives in `AGENTS.md` §2.1 (components and boundaries) and
> §12 (the D-numbered decisions with their rationale).

## File structure

Single-context repo. The canonical domain record is `AGENTS.md`, with the decision
log in `docs/decisions/`.

## Use the glossary's vocabulary

When your output names a domain concept (a ticket title, a test name, a refactor
proposal, a hypothesis), use the term as `AGENTS.md` defines it. Do not drift to
synonyms. Established vocabulary that matters:

| Term | Meaning |
|---|---|
| **panel** | The CEP extension under `panel/`, docked in After Effects |
| **host** | `panel/host/host.jsx`, ExtendScript (ES3), the only code allowed to touch the AE project |
| **sidecar** | The local FastAPI service under `service/`. Owns the registry, queue, thumb cache, tunnel |
| **engine** | The GPU service under `engine/`. Owns the pipeline, library, search scoring |
| **content id** | `sha1(str(size) + first 4 MiB + last 4 MiB)[:16]`. The engine library key (D16) |
| **shot** | One scene produced by stage 1. The unit search returns |
| **scene_id** | The dedup key; search keeps one result per `(content_id, scene_id)` |
| **fusion** | The six-component weighted score. Pinned by golden tests (§3.5). Never change weights without the goldens, the config, and `AGENTS.md` in one change |
| **signature** | The engine's pipeline-config hash. Decides whether a library index is `ready` or `stale` |

**Signature, format_version, and z-score values are contract.** They are not
implementation details and must not be renamed or restructured in code that a
ticket does not explicitly target.

## Flag ADR conflicts

If your output contradicts an existing decision, surface it explicitly rather than
silently overriding:

> _Contradicts D7 (stale-by-default pruning), but worth reopening because…_

The `docs/decisions/` files are the authority on which decision is currently in
force. Several are explicitly marked **SUPERSEDED**; never treat a superseded
decision as binding. `docs/decisions/README.md` carries the supersession markers
next to each entry.