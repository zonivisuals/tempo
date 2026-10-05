# ADR-0018 - The failure state block, and one cascade that says which of the two speaks

- Status: accepted
- Date: 2026-10-05
- Affects: `AGENTS.md` §5 F2, F3, §12; `docs/design/panel-ui.md` §3.1a, §6; `panel/www/panel.css`, `panel/www/panel.js`, `panel/www/index.html`
- Spec of record: `docs/design/panel-ui.md`

## Context

Two screens had two shapes for the same fact.

**The no-matches screen** was one `--dim` sentence in a bare `.empty` div at the top
of the results area: `No shots matched “x”.` Frame 01 — the *no footage* screen, one
state further down the same ladder — had been a centred block since ADR-0011: an
accent status pill, one line of instruction, `margin: auto` on both axes. So the
panel rendered "there is nothing here for you" twice, in two unrelated shapes, and
the second one was the one an editor sees after every fruitless search.

**The failure screens** were an inline row under the search field: `CODE · message`,
11px, `--error`, 1px border. That row is right for a failure that arrives *over*
content — a failed insert belongs next to the field the editor just used, and it
costs nothing to read. It is wrong for the three states where there is nothing else
on screen at all. With the service down, the panel had no footage, no results and no
search field, and its entire report of the outage was one red line pinned to the top
edge under a header: not centred, not named, and carrying a code
(`SERVICE_OFFLINE`) where a sentence belonged.

The two were also derived from two different questions. `renderResults` asked
whether footage was ready; `renderError` asked only whether an error existed. Nothing
joined them, so "where does this failure go" was answered in two places and could be
answered differently.

## Decision

### 1. One block, every state with nothing to show

`stateBlock(heading, instruction, detail)` is the single shape for frame 01, its
variants, a search that matched nothing, the screen before any search has run, and a
failure with nothing else on screen. Frame 01's four variants keep their wording
verbatim — the wording is the behaviour there, and it is pinned by test.

Two new variants joined it, because the ladder had two rungs with no block:

| Condition | Heading | Instruction |
|---|---|---|
| a search returned nothing | `No shots found` | `Nothing in this project matches “<query>”. Try a word from the dialogue or captions.` |
| ready footage, no search yet | `Ready to search` | `Type a few words to find shots across your footage.` |

The query is quoted back: the editor needs to see what was actually searched. That
made `overflow-wrap: anywhere` load-bearing on the hint — `max-width: 36ch` does not
stop one long unbroken query from widening the block past the panel.

### 2. `resultsScreen()` is the only question

One cascade names what `#results` holds, and both `renderResults` and `renderError`
read it. `job`, `searching`, `error`, `empty`, `nomatch`, `results`. The two
renderers cannot disagree about whether a failure is the block's or the row's,
because neither of them decides.

`error` requires an **empty result set**. An error arriving over cards is the row's
business: the block would wipe results the editor is still reading, and a failed
insert is not a reason nine results disappear.

`error` also sits **above** `empty`. With the service down and no footage known,
`No footage found` is a claim about the project that the panel cannot make — it does
not know whether the project has footage, it knows it could not ask. The precedence
is not cosmetic: it is the difference between an honest panel and a confident lie.

### 3. Each failure names itself, and the code stays on screen

| Code | Heading | Instruction |
|---|---|---|
| `SERVICE_OFFLINE` | `Service offline` | `The local Tempo service is not responding. Start it, then press Sync now.` |
| `BACKEND_ASLEEP` | `Engine asleep` | `The GPU engine is not running. Start the instance, then search again.` |
| `BACKEND_UNREACHABLE` | `Engine unreachable` | `Tempo cannot reach the GPU engine. Check the tunnel, then search again.` |
| `BACKEND_TIMEOUT` | `Search timed out` | `The engine took too long to answer. Search again.` |
| `QUOTA_EXCEEDED` | `Limit reached` | `This project is over your plan's footage limit. Footage already indexed stays searchable.` |

A code in the heading is a label, not a name: `BACKEND_ASLEEP` says nothing about what
stopped, and nothing about what to do about it. So the heading is a state in words and
the instruction is the action — the one part the editor can take. The service's own
message is *not* quoted on the first four, because it restates the heading
(`service offline`, `engine search failed`) and would say less.

`QUOTA_EXCEEDED` is the exception, and it is `withMessage` in the table: the numbers
are the useful part. The panel's wording says a limit was reached, and the service's
sentence carries which plan, what it allows and what the project holds. That is §7.3
made concrete — a plan limit written into the panel would be wrong the moment the limit
moves, so raising the limit on the server changes this line with no panel change. Its
wording says "your plan's limit" and not "the footage limit", because the service raises
this one code for footage-minutes too (`entitlements.check_new_work`). Its instruction
also says what is still true, because a denial on `/sync` gates new work only and an
editor who read "limit reached" as "nothing works" would be wrong.

The code goes on the new third line, `.detail`, in a new `--text-faint` token: F2
requires the code on screen, and a failure the editor cannot name is one they cannot
report. `--dim` was the obvious candidate and is wrong — over `#232323` the hint lands at
`rgb(123)` and `--dim` (`#8a8a8a`) at `rgb(138)`, so the quotation would be *louder* than
the instruction it is supposed to sit under, and on the light theme the relationship
inverts (`#5c5c5c` at 92 against the hint's 118). Quieter than 0.4 white is 0.28 white;
quieter than 0.45 black on a light surface is 0.62 black. Both are declared.

A code the table has no copy for falls back to a generic heading with the service's
message as the instruction and the code on the detail line, so a new backend error cannot
leave the panel blank.

Both routes into the block are clamped. A job error is 2000 characters of engine
traceback, and a block that tall is not a message; the cut is marked with an ellipsis,
the way the indexing error row's already was — and `clamp` is now the one owner of that
truncation, shared with that row.

### 4. The service's envelope is kept, and an error belongs to its action

Two things had to be true for any of this to be reachable rather than merely drawn.

**The envelope wins.** A failed call reports the code and message the service sent. The
panel's own code (`SERVICE_OFFLINE`, `SYNC_FAILED`, `RETRY_FAILED`, `SEARCH_FAILED`) is
the fallback for a transport that never reached the service and so has no envelope to
keep. Before this, every failed `/sync` was reported as `SYNC_FAILED · status 403` — which
is how the quota block could only ever be seen from a preview fixture, and it is the
honest-error gap this file's own spec section had recorded as outstanding.

**Only the action that raised an error clears it.** `store.error` carries the scope that
raised it (`sync`, `search`, `action`) and only that scope's success clears it. The
project sync runs every 2s; a sync that succeeds does not repair a search that timed out.
Without this the failure block lasted at most one poll interval and then fell through to
the no-matches block, which asserts that nothing matched a search that never returned —
a false claim, and a centred one.

`showError` renders both surfaces itself. The error decides which of the block and the
row speaks, so a caller that refreshed only the row left the other stale; that is how a
failed retry went unreported until the next poll.

### 5. The pill is the accent, not the error colour

The failure block is the frame-01 block, so it is `--accent`. `--error` stays where
the state is already carried: the header dot (ADR-0012) and the retained inline row. A
red block would introduce a third carrier of the same fact and read as a different
kind of screen from the one it is.

## Consequences

- The block is centred on both axes wherever it appears, including under a search
  field. That is a geometry change for the no-matches screen, which used to hang under
  the field; cards and skeletons stay top-aligned.
- `.empty` is deleted. The no-matches row was its only user, and §8 bans dead code.
- The block adds no animation, so ADR-0011's two-surface budget is untouched.
- The inline row is narrower than it was: it is now only for errors over content. It
  is not dead, and it keeps its 11px `--error` border.

## Alternatives rejected

- **Delete the inline row.** One rule, but a failed insert would wipe the result grid
  and move the message away from the field the editor typed in. Two surfaces, each
  with one job, beat one surface with two.
- **Keep the row for everything and just centre it.** A centred 11px red row is not
  the frame-01 block; it is the old row in a new position, and the three failure
  screens would still be named by codes alone.
- **A toast.** §6 bans them, and a toast over a panel that is already showing nothing
  is worse than the nothing.
- **Tint the failure pill `--error`.** Rejected for the reason in §5 above.

## Not decided here

- `prefers-reduced-motion` needs nothing here: the block does not move, so it adds no
  animation to ADR-0011's budget.
- Whether the no-matches screen's *query* needs the same clamp the service's words get.
  The query is this panel's own input and `overflow-wrap` already stops it widening the
  block; a pathological paste would still make the block tall.