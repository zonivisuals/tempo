# ADR-0021 - The service names the failure, and the panel says which one

- Status: accepted
- Date: 2026-10-06
- Affects: `AGENTS.md` §3.4, §5 F4, §12; `docs/api.md`; `service/tempo_service/{proxy,jobs,schemas}.py`; `panel/www/panel.js`
- Spec of record: `docs/api.md` (`GET /jobs/{id}`), `docs/design/panel-ui.md` §3.2

## Context

ADR-0020's sentence is honest and nearly useless: "Tempo stopped on this step." The
step list says *where*; it cannot say *what*. The editor's next move differs entirely
by cause — start the instance, reconnect the tunnel, put the file back on the disk,
wait — and the panel had no way to know which.

The panel cannot work it out. The only thing it is given is the job's `error` string,
whose first 2000 characters come from `engine/tempo_engine/jobs.py` as
`f"{exc}\n{traceback tail}"`. Anything, and it changes with every library bump.

## Decision

### 1. `HandoffError` carries a reason from a closed vocabulary

The sidecar already knows why each of its own failures happened — it is the code that
chose to raise them. So each raise site names itself, from a set declared once as
`REASONS` in `proxy.py`: `NOT_CONFIGURED`, `UNKNOWN_FOOTAGE`, `SOURCE_MISSING`,
`ENGINE_REJECTED`, `ENGINE_FAILED`, plus the seam's three transport codes reused
verbatim. `HandoffError.__init__` rejects any reason outside the set with a `ValueError`, so a
new call site cannot invent a fourth vocabulary by accident. A `raise`, not an `assert`:
`python -O` strips asserts, and this is a programming error rather than a runtime
condition — a check that vanishes under a flag is not one.

`ENGINE_FAILED` is the one the sidecar does not choose: the engine's pipeline raised
and the sidecar only sees its text. It is a real and common case, and the sentence it
gets is the honest one.

### 2. No string is sniffed

A raise site with no reason of its own says `ENGINE_FAILED` rather than pattern
matching an exception message. Matching would make the panel's accuracy a function of
the engine's dependency versions, and it would put text from a container path into the
logic that decides what a user is told. Not worth a better sentence for six of nine
cases.

### 3. One list, three copies, pinned

`REASONS` (raised), `FAIL_COPY` (written) and the `docs/api.md` table (contract of
record) are three representations of one vocabulary, and
`test_the_panel_names_every_failure_the_service_can_report` checks all three — the
panel holds a sentence for every reason, the two shared codes describe one failure the
same way in both tables, and every reason appears in the doc. The panel cannot
classify anything, so a gap here would be a permanently vague screen rather than a bug
anywhere else.

The two tables are read together on purpose: `FAIL_COPY` takes its `pill` for
`BACKEND_UNREACHABLE` and `BACKEND_ASLEEP` from `ERROR_COPY` at load, so the search
failure and the indexing failure cannot describe one code two ways. The hints differ,
because the actions do ("search again" against "try the step again").

### 4. An unrecognised reason prints nothing

`reason` goes on the block's detail line when the panel has a sentence for it, which is
the F2 requirement that the service's code be on screen. A reason it has none for is
not printed: the vocabulary is closed and CI-pinned, so an unknown value is drift
between a running panel and a running sidecar, not a state an editor will meet, and a
code nothing can explain is not something they can report.

### 5. `jobs._run` reads it off the exception

`Job.reason` defaults to `None` and `_run` sets it with `getattr(exc, "reason", None)`.
Not an import: `proxy` imports `jobs`, so the dependency cannot point the other way.
An exception raised outside `proxy.handle` leaves it `None`, and the panel prints its
fallback sentence — which is the honest answer to a failure nobody named.

## Consequences

- Eight of nine failure kinds now say something the editor can act on. The ninth, a
  failure the sidecar did not raise, says the fallback.
- `error` is still returned, still truncated to 500 characters in the registry entry
  and still 2000 in the engine's envelope. `known-issues.md` S5 stays open on the
  service side; this is the panel half, already recorded by ADR-0020.
- `JobStatus` gained a field. Additive and nullable, so a panel older than this
  sidecar keeps working: it does not read the field at all.
- Nothing in the pipeline changed: a retry still resumes from the stage cache, and the
  failing stage is still identified by the step list rather than by the reason.

## Alternatives rejected

- **Classify the engine's exception text.** Better sentences for the most common
  failure, at the price of a pattern-matching table that breaks on a dependency bump
  and reads a container path into user-facing logic.
- **Send the reason from the engine.** It knows the exception type, which is more
  precise than a single `ENGINE_FAILED`. That is an engine contract change and a
  deploy; the sidecar is the panel's only boundary, and one hop is enough for MVP. If
  the generic sentence proves too vague in use, the engine's `reason` is the next step,
  not this test.
- **Let the panel hold the vocabulary and have the service send prose.** Then the panel
  decides what a user is told about a failure it cannot see, and §7.3's "no plan limit
  or instance name written into the panel" is one edit away from being wrong.
- **Print the raw code when unrecognised.** Consistency with ADR-0018's unnamed-code
  rule for search failures, and wrong here: those codes come from a documented envelope
  and a fallback sentence can still act on them.
