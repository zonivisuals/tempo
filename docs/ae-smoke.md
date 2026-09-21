# AE smoke checklist (AGENTS.md §9)

AE cannot be UI-automated in CI cheaply — run this manually before every
release, on the **oldest and newest AE versions claimed** by the manifest range.

## Setup

1. Open AE, create a test project, import one footage file (any mp4).
2. Open the ExtendScript Toolkit console to see `$.writeln` output.
3. Run `panel/host/ae_smoke.jsx` (File > Scripts > Run Script File).

## Script asserts (must all PASS)

- [ ] `list returns JSON array` — `tempoListFootage()` parses to an array.
- [ ] `footage has path/size/mtime` — first entry carries all three.
- [ ] `insert ok` — `tempoInsertOrFocus()` returns `{ok:true, comp_id, layer_id}`.

## Eye verification (one inserted layer, first 2 s of first footage)

- [ ] Layer exists, trimmed to exactly `[T, T+2]` where `T` was the playhead.
- [ ] Playhead sits on the shot start (first frame on screen).
- [ ] Only the new layer is selected.
- [ ] One Ctrl/Cmd+Z removes the whole action (single undo group).
- [ ] Re-running the script with the same file imports **no duplicate** footage.
- [ ] With no comp open, a `Tempo — <basename>` comp is created instead.
- [ ] Missing source path returns `{ok:false}` with a clean message (rename a file to try).

## Sign-off

Version(s) tested: _______________  Date: __________  By: __________
