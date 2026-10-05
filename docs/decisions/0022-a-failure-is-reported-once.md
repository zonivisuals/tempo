# ADR-0022 - A failure is reported once

- Status: accepted
- Date: 2026-10-06
- Affects: `AGENTS.md` §5 F4, §12; `docs/design/panel-ui.md` §3.1a, §3.2, §6; `panel/www/panel.js`
- Spec of record: `docs/design/panel-ui.md` §3.1a

## Context

With ADR-0019 and ADR-0020 landed, the indexing failure was reported correctly — and
twice.

`resultsScreen()` sent a panel with no searchable footage to frame 01's block, which
had two indexing variants of its own:

> **Indexing Failed** — `rushes-take-3.mov could not be indexed. Open the indexing
> detail to retry.`

That is a second report of the same cause, and a bad one on both counts. It names a
file the indexing screen had just stopped naming, it appears *below* a detail that is
already on screen and above it, and it tells the editor to go somewhere they already
are. The second variant ("Indexing Stalled", for an entry with no job) was the same
sentence with a different word.

The variants were not decorative. They were the fallback for a panel that could not
see a job payload — a service restart or a panel reload leaves the registry at
`indexing`/`uploading`/`error` with nothing in `store.jobs`. ADR-0020 kept that
recovery, through the same button aimed at `/footage/{key}/retry`, so the blocks now
duplicate a recovery that already works.

## Decision

### 1. `indexingVisible()` is the gate, not `activeJob()`

`resultsScreen()` asks "is the indexing section reporting something?" rather than "is
a job live?". One function, already pure and already pinned, so there is no second
definition of what the section is showing. A failed run and a stranded entry both own
the panel; `#results` is emptied the way it already was for a live job.

Qualified on `!ready`: searchable footage keeps its results. A failed second footage
does not wipe the nine cards the editor is reading — the same rule ADR-0018 set for an
error arriving over content.

### 2. Both variants are deleted, not reworded

`emptyStateHTML()` is two branches: no footage, and every file stale. The two indexing
variants could only ever repeat a sentence and a button that live elsewhere, so there
is nothing left for them to say.

The `stale` branch stays because it is a claim about the project the panel *can* make:
every file is in the registry and none is ready to search, and no indexing section is
reporting why.

## Consequences

- One fault, one screen. `#results` is empty while the indexing section reports, and
  the failure block is centred there by the same `margin: auto` the indexing section
  uses, so it does not sit under the header.
- `baseName()` still has two callers (the footage filter and the result cards), so the
  helper stays; what went is the last place a filename appeared on this screen.
- `resultsScreen()`'s precedence is unchanged apart from the widened first branch: a
  live job still outranks a search in flight, and an error still outranks the
  no-footage claim.
- Nothing in the service changed. No new state, no new route.

## Alternatives rejected

- **Keep the block, drop only the sentence's file name.** Still two reports for one
  fault, and the second one would say nothing ("this file could not be indexed") above
  a section that says it with a button attached.
- **Point the results block at the section and keep it for the stranded case only.** Two
  states with the same shape and the same cause, differing only in whether the panel
  happens to hold a job payload — which is an accident of restart timing, not a fact
  about the project.
- **Let the section hide and the block speak.** The section carries the step list, which
  is the only thing that names the step that failed. A panel showing "indexing failed"
  with no rows is the state ADR-0019 removed.

## Not decided here

- The `searching` and `nomatch` branches are unreachable with no ready footage (there
  is no field to type in and nothing to search), but they were unreachable before this
  too and cost nothing to leave: one cascade reads as one list of states.