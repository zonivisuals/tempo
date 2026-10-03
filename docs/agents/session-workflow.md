# Session workflow

One ticket per session. This file is the resume protocol, the gate list, and the
ticket loop. `AGENTS.md` is the spec; this is how you work through it.

## Start of session: five commands

Run these before reading any source. They take under a minute and catch the
failure modes that waste a session.

```bash
git status --short              # what did the last session leave behind
git log --oneline -5             # where the work stopped
python -m ruff check service engine
python -m pytest service/tests -q
python -m pytest engine/tests -q
```

Two things to know before you trust the last two:

- **The engine suite needs the package on the path.** Fresh clone or new machine:
  `pip install "./engine[dev]"`. Without it every test errors with
  `ModuleNotFoundError: No module named 'tempo_engine'` and zero tests run. The
  sidecar suite has no such requirement.
- **`test_warm_rank_under_300ms_at_10k_shots` is order-sensitive.** It passes alone
  and fails after the rest of the engine suite, because the preceding tests leave
  the process memory-bound. Measured ~157 ms against a 300 ms budget. If it is the
  only failure, re-run it alone before believing it:

  ```bash
  python -m pytest engine/tests/test_search.py::test_warm_rank_under_300ms_at_10k_shots -q
  ```

If any gate is red when you start, that is the first ticket, whatever you were
asked to do. Say so and fix it before opening new work.

## The gates

`python -m ruff check <path>` and `python -m pytest <path>/tests -q` work from a
repo root. CI runs exactly these, plus two more.

| Gate | Command | Scope |
|---|---|---|
| ruff | `python -m ruff check service` | sidecar |
| ruff | `python -m ruff check engine` | engine |
| sidecar tests | `python -m pytest service/tests -q` | 48 tests |
| engine tests | `python -m pytest engine/tests -q` | 47 tests |
| ES3 gate | `pnpm lint` | `host.jsx`, `ae_smoke.jsx` |
| panel syntax | `node --check panel/www/panel.js && node --check panel/www/api.js` | panel JS |
| deploy script | `bash -n engine/deploy/brev-deploy.sh` | shell syntax |

`.github/workflows/test.yml` is the source of truth for what CI runs. If you add a
gate, add it there in the same change.

**What the ES3 gate actually enforces**, so you do not assume more than it does:
`ecmaVersion: 3` parse rejection plus two `no-restricted-syntax` selectors (Array
extras, and `Promise`/`fetch`/`console`). It does **not** enable `no-undef`, so
the `globals` list in `eslint.config.mjs` is currently inert. It does not ban
regex literals.

## The ticket loop

Tickets live in GitHub Issues on `zonivisuals/tempo` (`docs/agents/issue-tracker.md`).
The skills below are installed globally and trigger on their descriptions. Naming
one removes all guesswork.

### 1. Plan a feature

```
"grill me on this before we build it"
```

`grilling` walks a design tree in rounds. Each question arrives with a recommended
answer, so you are confirming rather than composing. It dispatches subagents for
facts and reserves questions for your decisions.

Then:

```
"turn this into a spec"
```

`to-spec` synthesizes the spec from the conversation with no new interview. Its
step 2 picks the **test seams** before anything is written: existing seams
preferred, highest possible, fewest possible. Confirm those seams explicitly.

Output: one GitHub issue with Problem Statement, Solution, User Stories,
Implementation Decisions, Testing Decisions, Out of Scope.

### 2. Break it into tickets

```
"break this spec into tickets"
```

`to-tickets` produces tracer-bullet slices with four rules:

- each slice cuts a complete path through every layer, never one layer
- **each slice is sized to fit in a single fresh context window**
- each slice is demoable or verifiable on its own
- each ticket declares its blockers

It quizzes you on granularity before publishing. Answer it, then it publishes one
issue per ticket in dependency order.

### 3. Implement one ticket

```
"implement ticket 3"
```

`implement` is the whole step. It runs `tdd` at the pre-agreed seams, typechecks
and single-test files regularly, the full suite once at the end, then
`code-review`. Commits to the current branch.

Two rules from `tdd` that decide whether the ticket fits one session:

- **No test is written at an unconfirmed seam.** Seams were agreed in step 1. If
  you find yourself wanting a test somewhere else, stop and re-agree.
- **One slice at a time.** One seam, one test, one minimal implementation.

### 4. Review before committing

```
"review since main"
```

`code-review` runs two parallel sub-agents so neither pollutes the other:

- **Standards**: does the diff follow `AGENTS.md` §7, plus a Fowler smell baseline
- **Spec**: does the diff do what the ticket asked, nothing more, nothing less

Reported separately on purpose. Code can pass one axis and fail the other, and
merging them hides that.

### When the work is too big to plan

```
"wayfind this"
```

`wayfinder` names the destination, maps the frontier, and writes **decision**
tickets rather than build tickets. One ticket per session. It plans; it does not
build.

`wayfinder` assumes multiple branches and git worktrees. Tempo's convention
(`AGENTS.md` §0.8) is one phase per commit on the working branch. Use it only when
you actually want the fan-out.

## Commit discipline

One phase per commit, never mixed (`AGENTS.md` §0.8). A commit is reviewable on
its own, and the sequence reads as an argument.

- Behavior change ships with a test change in the same commit.
- Anything touching §3.5 fusion, the engine `signature`, or the sidecar
  `format_version` updates `AGENTS.md` and the decisions log in the same commit.
  `docs/decisions/README.md` carries the index; add the numbered ADR file next to
  it.
- Commit messages follow the existing pattern: `feat:`, `fix:`, `chore:`,
  `docs:`, lowercase imperative subject.

## When you are stuck

| Symptom | Reach for |
|---|---|
| A bug you cannot localize | `"diagnose this bug"`. `diagnosing-bugs` Phase 1 forbids hypothesizing before a red command exists. |
| You do not know why code is shaped a way | `"why does X work this way"` → `why`, anchored on git history and the ADRs |
| You do not know how something works | `"how does X work"` → `how` |
| You are about to break something you cannot see | `"what could this break"` → `blast-radius` |
| You want a decision stress-tested | `"grill me on this"` |
| Work larger than one session | `"wayfind this"` |
| You need an external API fact | `"research X against primary sources"` → `research`, writes a cited file |

## Where state lives

Nothing is stored in a session that the next one cannot reconstruct.

| What | Where |
|---|---|
| Which ticket is in flight | GitHub Issue, per `docs/agents/issue-tracker.md` |
| Feature spec | The spec issue; referenced by tickets, never copied into them |
| Index state, uploads, jobs | `artifact_root` on disk, engine `data_root` on Brev |
| Footage fingerprints | `<artifact_root>/registry.json` |
| Decisions | `docs/decisions/NNNN-slug.md` plus the index in `docs/decisions/README.md` |
| What the last session did | `git log`, plus uncommitted changes in the working tree |

If a session ends with work in progress, commit it. An uncommitted tree is the one
thing the next session cannot reason about.