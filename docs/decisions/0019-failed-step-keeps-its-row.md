# ADR-0019 - The failed step keeps its row, and the row is marked

- Status: accepted
- Date: 2026-10-06
- Affects: `AGENTS.md` §5 F4, §12; `PRODUCT.md` F4; `docs/design/panel-ui.md` §3.2, §7; `panel/www/panel.css`, `panel/www/panel.js`, `docs/design/preview-harness.js`
- Spec of record: `docs/design/panel-ui.md` §3.2

## Context

The indexing screen is the only place that can say *where* indexing stopped, and it
was blank at the exact moment it was needed.

`pollJobs` drops a job from `store.activeJobs` on any terminal state but keeps the
payload, because a failed job still has something to report. `renderSteps` read
`activeJob()` and nothing else. So the poll that delivered the failure was also the
render that cleared the step list: after `store.activeJobs` emptied,
`stepOrder(null)` returned no rows and `#steps` was set to the empty string.

What the editor was left with is the `.job-err` box — up to 300 characters of engine
traceback, printed from `engine/tempo_engine/jobs.py` where the error is
`f"{exc}\n{traceback tail}"`. No rows, no stage, no indication of which of the eight
steps gave up, wrapped in a 1px `--error` border.

The panel preview showed something entirely different. `preview-harness.js` seeds
`activeJobs` for every job screen so the panel polls it, and it did so for the failed
fixture too. With the failed id still in the list, `renderSteps` found it and rendered
three rows. So `#failed` was the one screen in the preview that could not be
reproduced in the panel, and the divergence was invisible precisely because the
preview looked correct.

This is only the first of three defects on that screen. The traceback itself, the
second Retry button in the footage row, and the duplicate "Indexing Failed" block in
the results area are separate tickets, all rooted in the same question — who reports a
failure, and how much of it — being answered in four places.

## Decision

### 1. The step list renders from the job that failed

`currentJob()` is the live job, or failing that the newest job whose state is `error`.
`stepOrder`, `renderSteps` and everything downstream read it. One question — which
job's stages are on screen — asked once.

The fallback is not a second code path. `currentJob()` returns one payload, the
`activeJob()` shape, and the rest of the step list cannot tell the difference. The
active list is checked first, so a running job is never shadowed by an earlier
failure that is still in the store.

Object key order is insertion order (job ids are `job_<hex>`, never integer-like), so
walking `Object.keys(store.jobs)` backwards is newest first. The panel holds failed
payloads until reload — nothing deletes them, deliberately, because the failure screen
needs them after the job stops being live.

### 2. The errored row is marked three ways

A finished row is `--text` at 0.5 opacity with an empty readout, so an unmarked errored
row is a finished one with a red label. Three marks, each load-bearing:

- **`--error` on the label and the icon**, which is what the row already carried.
- **`--error-wash` behind the row** at 10% of that theme's `--error`. A token, not a
  literal: `--error` is a hex in both themes and `color-mix()` is Chromium 111
  against this panel's floor of 84, so the wash is a per-theme `rgba()` literal — the
  same precedent `--edge` and `--sweep` set in ADR-0015 and ADR-0016. Each theme's
  wash is its own `--error`, or the marked row is the other theme's red.
- **`failed` in the readout slot.** The slot is already there and already carries the
  running stage's percentage or unit; it carries nothing for a finished row, because
  `total == 0` means unknown rather than 0%. "failed" is a state, not a number, so it
  does not reopen that rule.

No opacity on the errored row, deliberately: the class is exclusive with `done`, and
an `opacity` here would dim the failing row exactly as hard as a finished one.

### 3. The preview stops faking a live job

The `failed` fixture declares `active: false` and the harness honours it. The fixture
was the bug's only witness, so it is pinned by a test: the panel and the preview now
show the same list, and a fixture that re-adds a live job to a failed screen fails
`test_the_preview_does_not_fake_a_live_job_on_the_failed_screen`.

## Consequences

- The failure screen can say where it stopped, and the marked row sits directly above
  the message that explains it (`stepOrder` has always rendered finished stages
  newest-first and then whatever is not ordinary progress, so the errored row lands
  last; that order is unchanged and still pinned by its own test).
- Two animated surfaces are still impossible to confuse here: the errored row's icon
  is the same hollow ring as before, and nothing on this screen animates. ADR-0011's
  budget is untouched.
- `currentJob()` is the only new function. `activeJob()` is unchanged and still
  answers the narrower question the pill and the height reserve need — both are
  live-only by §4.4, and neither may fire on a failure.
- The traceback is still on screen. That is ADR-0020.

## Alternatives rejected

- **Keep the failed job in `activeJobs`.** One line, and it makes `live` true for a
  failure — which would show the "Processing your videos" pill and its spinner over a
  job that has stopped, and reserve nine rows of height for a list of three. `live`
  means running, and §4.4 binds the pill to it.
- **Render the failure from the registry instead.** The registry entry carries
  `state: error` and a message, and no stages: the whole point is the step, and the
  only copy of it is the job payload the panel already holds.
- **Mark the row with a heavier weight or a second icon.** The panel has three step
  icons and §6 wants them identifiable at 16px and consistent; a fourth glyph for one
  state spends that consistency on a state the wash and one word already carry.

## Not decided here

- What the failure *says*. The `.job-err` box still prints the traceback verbatim
  (ADR-0020), and the footage row still offers a second Retry for the same fault.
- `docs/agents/known-issues.md` S5 (job errors return absolute paths and tracebacks)
  is untouched by this: the service still sends them, this only stopped the step list
  from vanishing.