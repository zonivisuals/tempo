# ADR-0020 - The indexing failure is one sentence and one button

- Status: accepted
- Date: 2026-10-06
- Affects: `AGENTS.md` §4.4, §5 F4, §12; `PRODUCT.md` F4; `docs/design/panel-ui.md` §3.2, §6; `panel/www/panel.css`, `panel/www/panel.js`, `panel/www/index.html`, `docs/design/preview.html`
- Spec of record: `docs/design/panel-ui.md` §3.2

## Context

ADR-0019 fixed the step list. Three things were left on that screen, all of them the
same question asked in four places.

**The error was a stack trace.** `engine/tempo_engine/jobs.py` stores
`f"{exc}\n{traceback tail}"` — up to 2000 characters — and `panel.js` printed the
first 300 into a 1px `--error` border. What reached the editor was
`engine job 7f3c: BACKEND_UNREACHABLE <urlopen error [Errno 111] Connection refused>
after 5 attempts`, a `File "/app/engine/tempo_engine/pipeline.py", line 85, in build`,
and the `raise` itself. A container path, a line number and a socket errno are three
things the editor cannot act on. The stage that failed is one row above it, in
editorial words, and was the whole point of the screen.

**One fault had two Retry buttons.** One in the error box, one in the footage row.
Both call the same operation, because a retry re-runs the pipeline through the
engine's stage cache and the finished steps are cache hits — so which one the editor
pressed made no difference. The footage row also named the file and printed the
registry's state word beside it.

**The footage rows had one job left.** They existed to retry an entry the panel has
no job for: a service restart or a panel reload leaves the registry at
`indexing`/`uploading`/`error` with no payload and no job id. That is the one thing
they still did that nothing else did.

## Decision

### 1. One block, one sentence, one button

`renderIndexFailure()` replaces the error row and the footage rows. It builds
`stateBlock(pill, hint, "", action)` — the same builder ADR-0018 gave every other
failure, which gains an optional action slot so this screen does not fork a second
shape. The failing step is named by its own row; the sentence does not repeat it.

The raw `error` string is not rendered anywhere in the panel. It stays in the payload
and in the service log, where it belongs.

### 2. The button's route is the only thing that differs

A failed job is retried by job id; an entry the panel has no job for is retried by
footage key. `POST /footage/{key}/retry` is documented as the same operation
addressed by key, so the stranded case keeps its recovery path and the panel holds
one function per route rather than one renderer with a branch. Both routes resume
from the stage cache, which is what "Retry step" promises.

**The stranded case is suppressed until coverage is known.** A job enqueued locally
carries no `footage_key` until its first poll, 500 ms after the 2 s sync that created
it, and new registry entries are already `indexing` — so for that window the panel
cannot know which entry the live job is about to claim. Reporting those entries would
print "Indexing Stopped / Tempo lost track of this step" and a Retry button over
footage that is uploading fine, on every single import. The footage rows carried this
guard and it came out with them; `strandedFootage()` has it back, and
`test_a_job_the_panel_has_not_polled_yet_is_not_a_stalled_footage` pins it in both
directions.

### 3. The other failures are counted, not listed

Queues are single-worker but a failure does not stop them, so a dead engine fails
every queued footage in turn and the panel accumulates failed jobs. One block can
report one; a block each is the dense list this screen just lost. So the sentence
ends with a count when there are others — read off the footage list the panel already
holds, which is data and not a number written here (§7.3's rule is about plan limits
and instance names, not about a count of the project's own files).

### 4. No file name on this screen

The rows, their CSS, the renderer that built them and the `data-fretry` hooks go. What
remains on the indexing screen is a step list, a status pill and one failure block —
which is what §4.4 already said the section contains, before the rows contradicted it.

## Consequences

- The screen answers one question — where did it stop, what now — in two rows and one
  sentence. The traceback is one `git log` away for anyone who needs it.
- The step list's own height reserve (`--step-count`) is unchanged: the reserve is
  live-only, and a failure is never live.
- The block adds no animation, so ADR-0011's budget is untouched. The pill inside it
  is `--accent` like every other block (ADR-0018 §5); `--error` stays on the step row,
  the header dot and the retained inline row.
- **A limitation, accepted:** the block reports whenever a failed job exists, including
  while a different job runs. In that window the step list belongs to the running job,
  so the sentence stands without its marked row above it. The alternative — no report
  at all until the queue drains — loses the retry for a footage the editor can see is
  stuck, which is the thing they need.
- The stranded case has no rows at all: there is no payload, so there is no step list
  to draw. Its sentence says so rather than implying a step it cannot name.

## Alternatives rejected

- **Show the traceback behind a disclosure.** A second control for a detail no editor
  asked for, and §6 bans what moves that does not inform. The string is in the payload
  and in the log; a diagnostic panel can read it from there.
- **Keep the footage rows, drop only their Retry buttons.** Then the stranded entry
  loses its only recovery path, and the rows still name files on a screen the user
  asked not to be named.
- **One block per failed footage.** Honest, and the density complaint again.
- **Retire the button and let the editor re-import.** Indexing is expensive and the
  stage cache means a retry costs the failed step only. A button that cannot be
  pressed is a dead affordance (§8).

## Not decided here

- **What the sentence names.** It says the most the panel can say without help:
  "Tempo stopped on this step." The service does not yet classify its failures, so
  "the engine was unreachable" is not something the panel can know honestly — that is
  ADR-0021, and this wording is its fallback.
- `docs/agents/known-issues.md` S5 — job errors return absolute paths and tracebacks
  across the service boundary — is narrowed, not closed: the panel no longer renders
  them, and the service still sends them.
- The duplicate failure report in the results area is ADR-0022.