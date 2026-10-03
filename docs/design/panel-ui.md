# Panel UI spec of record

Source design: Figma file `YJntqqRI69HtwO7aw8bbwz`, group `TEMPO_project_frames`
(node `777:771`), four frames. Rationale and the reversal it forces: ADR-0011.

This file is the reviewable spec. Where it disagrees with `AGENTS.md` §6 or §5,
this file and ADR-0011 are the newer word (§0 rule zero: the official docs win;
the Figma file is not official documentation, so the reversal is recorded as a
decision rather than smuggled in).

## 0. Why this is not a 1:1 port

The four frames are **2004 × 1919 px** — a standalone desktop web app. A docked
AE panel is roughly 300–360 px wide. Every dimension is therefore **re-derived
for panel scale**; only the design's *system* (palette, surface stack, motion
language, hover inversion) is carried over. This is decision Q1 of the design
review: panel-native re-derivation, not a fixed-width wide panel and not two
layouts.

## 1. Tokens

Dark values are the Figma hexes verbatim. Light values are derived (§Q2:
Tempo ships two themes; `appSkinInfo` only *selects* one — see ADR-0011).

| Token | Dark | Light | Design source |
|---|---|---|---|
| `--bg` | `#232323` | `#d6d6d6` | frame fill `rgb(35,35,35)` |
| `--surface` | `#171717` | `#f2f2f2` | `Rectangle 5411`/`5420` fill `rgb(23,23,23)` |
| `--surface-2` | `#1f1f1f` | `#e8e8e8` | skeleton base |
| `--border` | `#2e2e2e` | `#c4c4c4` | hairline dividers |
| `--text` | `rgba(255,255,255,0.8)` | `rgba(0,0,0,0.88)` | step labels `777:702`, card text `777:345` |
| `--text-dim` | `rgba(255,255,255,0.4)` | `rgba(0,0,0,0.45)` | search label `777:516` |
| `--accent` | `#EB5017` | `#c23c0c` | `777:700` "Analyzing your footage" |
| `--thumb` | `#EB6060` | `#b3555a` | `777:368` thumbnail layer, `Rectangle 5421` |
| `--error` | `#EB6060` | `#a32b2b` | |
| `--ok` | `#7fae74` | `#3f7a35` | status dot ok |
| `--spin-track` | `#fff` | `#b4b4b4` | `777:704` indicator track; white is invisible on the light surface |

### Radii are ratios, not raw px

The design's radii are ported **proportionally**, so the shape survives the scale
change instead of being flattened. A 32 px radius on a 196 px-tall field is 0.163
of the height; 0.163 of a 48 px panel field is 8 px.

| Element | Design | Ratio | Shipped |
|---|---|---|---|
| search field, CTA, indexing pill | 32 / 196 | 0.163 | `--r-lg: 8px` |
| submit + toggle buttons | 10.67 / 60, 8 / 64 | 0.178, 0.125 | `--r-sm: 4px` |
| cards, thumbnails, skeleton blocks | 12 / 560 | 0.021 | `--r-md: 3px` |
| status dot | — | — | `50%`, the one exception that must stay round |

### Other ported properties

| Property | Design | Shipped |
|---|---|---|
| search field / pill stroke | 1.5 px, `linear-gradient(#FFF 0% → #171717 100%)` at 0.28 alpha | `--edge` via a double-background `padding-box`/`border-box` clip |
| search field / pill shadow | `DROP_SHADOW 0 8 12 rgba(0,0,0,0.2)` | `0 2px 6px rgba(0,0,0,0.2)` |
| submit button | 60 px, radius 10.67, `fill #FFF @ 0.10`, no border, no shadow, "Arrow up" rotated 90°, 23 px glyph, stroke 4 round | 24 px, `--r-sm`, `rgba(255,255,255,0.1)`, glyph 16 px, stroke 1.5 |
| card stroke | 3 px, same colour as the fill | `border: 3px solid var(--surface)`, accent on hover |
| skeleton fills | `#FFF 0→0.56` (thumb), `#FFF 0→1` (caption), radius 12 | `--sweep-thumb`, `--sweep-cap` on `--r-md` |
| indeterminate indicator | two arcs: an accent active arc over a white track, thickness 4 of 44 | the `777:704` two-path export at 16 px, filled from CSS: `.arc` → `--accent`, `.track` → `--spin-track` |
| running row's indicator | 12-ray burst, `777:709`, accent | the same export at 16 px, `stroke="currentColor"` with `color: var(--accent)` |

**Type** (design px → panel px). The frames are 2004 px wide and a docked panel
is ~300 px, so type cannot scale with the geometry — 32 px type at frame scale is
~5 px in the panel. Geometry ports proportionally; type is re-derived.

| Role | Design | Panel |
|---|---|---|
| search value | 32 | 13 |
| search label | 24 | 11 |
| step label | 32 | 12 |
| card caption / duration (Medium 500) | 20 | 11 |
| indexing pill label (Medium 500) | 46 | 13 |
| empty-state heading | 46 | 13 |

Family stays the **system stack**. The design's Geist is not shipped: it is not
installed on Windows, not bundled with AE, and `§7.2` allows no panel dependency
for this.

**Spacing**: 4 px rhythm (design `itemSpacing` 12 → 4).

**Icons**: 16px (design 32 → 14 would breach `§6`'s "identifiable at 16px",
which was not reversed).

## 2. Layout

One scrolling column. The four Figma frames are four *scenarios*, not four
routing targets — a docked panel has no screen stack, and a strict switcher
would make it impossible to search footage that is already `ready` while
another file is still indexing (§5 F2).

```
#statusbar    brand · status dot · service · engine · Sync now     (always)
#searchbox    label + value + submit                                (ready footage only)
#error        inline error row                                       (on error)
#footage-filter                                                       (>1 footage)
#indexing     status pill + step list + footage rows                (job live)
#results      skeletons | cards | empty state | no-results
```

**No hide/show toggle.** The stage list is shown whenever a job is live and
disappears when none is; a failed job keeps its message and Retry visible. The
eye control is gone from `index.html`, and `store.index` is gone from `panel.js`.
A search does not collapse it either — searching with a job running shows the
list and the results together.

The status row is always visible — `§4.4` requires engine reachability to render
honestly, and it has no home in the Figma frames.

`#searchbox` and `#footage-filter` render only when at least one footage is
`ready`. Below that the panel shows the indexing scenario (frames 01/02), which
matches the design: neither frame has a search field.

## 3. Scenarios

### 3.1 Frame 01 — no footage

No search field. No indexing block. Centred on both axes, by the same mechanism
as frame 02: the block gets `margin: auto` inside `#app`'s column (`#results`
carries `centered` while it holds nothing else), so with only the status bar
above it, it sits in the middle of the panel instead of hanging under the bar.
`panel.js` sets that class only for this block — a centred result grid or a
centred skeleton list would float below a search field that is already above it.

- **Heading** `No footage found` — a status pill: `--bg2` fill, 1px border,
  `--accent` text, 2px radius. It is `role="status"`, **not** a button. The
  design draws it as a disabled CTA; a disabled control advertises an action it
  cannot perform, which §8 bans. Pixels kept, dead affordance dropped. Sized by
  its own content, like the indexing pill.
- **Hint** `Get started by importing your videos to the project`

Two more variants of the same block, same components:

| Condition | Heading | Hint |
|---|---|---|
| footage present, none `ready`, none indexing | `No searchable footage` | `Every file in this project is stale or failed indexing.` |
| any footage `error` | `Indexing failed` | `<footage name> could not be indexed.` + Retry lives in the indexing detail |

The design's `Get started by importing your videos to the project` is kept in
substance; the exact AE menu path is named so the instruction is actionable.
"Search for anything" from the design is **dropped** — `§6` bans placeholder
copy of that species and ADR-0011 did not reverse that line.

### 3.2 Frame 02 — indexing

`progress_labels` in the design: one vertical frame, `itemSpacing: 12`, rows of
exactly 42 px, 32 px icon + 32 px label, running row at full opacity, done rows
at 0.5. Reversed order — the running step is at the **top** and completed steps
slide *down* into place.

**Nine rows**, pipeline order (the design shows 7 and drops `ocr` and `text`):

| # | Key | Label | Source |
|---|---|---|---|
| 0 | `queued` | Initializing your project | synthetic, job `state == "queued"` |
| 1 | `upload` | Uploading the footage | engine stage |
| 2 | `shots` | Detecting the scenes | engine stage |
| 3 | `visual` | Embedding the visuals | engine stage |
| 4 | `transcribe` | Transcribing the audio | engine stage |
| 5 | `ocr` | Reading on-screen text | engine stage |
| 6 | `captions` | Captioning your scenes | engine stage |
| 7 | `text` | Reading names and emotion | engine stage |
| 8 | `index` | Finalizing | engine stage |

Row 0 is synthetic and last: the design's list includes it but no engine stage
reports it. It binds to job `state === "queued"` and covers the real gap while
the tunnel comes up (K4) — an empty list there reads as a broken panel.

Labels are **presentation only**. The stage *list* comes from the service
(`GET /jobs/{id}`), which takes it from engine `/v1/health`; unknown names render
as-is (`§4.4`). The label map lives in `panel.js` beside the existing
`STAGE_LABELS`.

Display order is computed per tick: **running → done (reverse completion
order)**. A stage that has not started is **not a row**: the list is the running
stage plus what is already finished, so from enqueue until the first stage
reports the list is empty and the heading pill is the only thing on screen (the
space the list will fill is held below it — see the centring note below). Row
identity is keyed by stage key, so a completing row is *moved* in the DOM, not
recreated — that is what makes the slide possible at all (§5 below).

Row states — the design has **no progress bar**; progress is the running row's own
readout (`777:702`, "Finalizing... 80%"):

| State | Icon | Label | Readout |
|---|---|---|---|
| running | 12-ray burst (`777:709`) in `--accent` | `--text` | percentage, or the unit count |
| done | 16 px check | `--text` at 0.5 opacity | hidden |
| pending | none — the row does not exist yet | — | — |
| error | 16 px hollow ring, `--error` | `--error` | hidden |

Above the list, while a job is live, the **indexing pill** (`777:698`): the fixed
label `Processing your videos` in `--accent` plus the same two-arc indicator, on
the gradient-edged, shadowed `--surface`. The label does not change with the
stage — the step list right below names the stage. It is the only thing on screen
between enqueue and the first stage reporting, when the list has no rows yet. It
is sized by its own content (`align-self: center`, not a full-width banner): a
320 px rule carrying one 13 px label reads as a divider, and the design drew it as
a chip. The text lives in `index.html`, not in JS.

**Nothing above or beside the list names the file.** An earlier revision carried
a summary line, `Indexing · <file> · <stage> <n>`; it was the only filename on
this screen outside the footage rows, it repeated what the running row already
said, and it truncated to nothing in a 300 px panel. With it gone the section
shows only when there is work to show: a live job, a failed one, or footage that
failed or is stranded mid-index. The last two are registry states that outlive a
panel restart, unlike a job id, which is why the rule reads the footage list and
not only `store.jobs` — that is the difference between a hint that says "open the
indexing detail to retry" and a detail that is actually there. `indexingVisible()`
in `panel.js` is that rule, pure so a test can pin it.

**The screen is centred, and the pill does not move.** While a job runs this
section is the whole panel — the search field is hidden until one footage is
ready — so it sits in the middle of the panel on both axes rather than stacked
under the status bar. Three details decide how it reads:

- `#app` carries `min-height: 100vh` so there is free space to centre inside;
  auto margins collapse to zero when the content is taller than the panel, so a
  long error row starts at the top and scrolls as before.
- `max-width: 320px` on the section. Without it the steps are two short rows
  floating in the middle of a 640 px dock.
- Centring a growing block moves everything above it: rows arriving one at a
  time walked the pill down the panel for the length of the run and back up at
  the end, which made the only fixed element on the screen the one that moved.
  So while a job is live the detail block is held at the **finished list's
  height** (`--step-h * --step-count`, the same flag that shows the pill sets
  `.live` on the section). The pill therefore lands where it will still be at
  the end of the run, and rows arrive underneath it. The reserve is on the
  detail block rather than on the step list so the slack falls below the last
  row: the error and footage rows stay against the steps instead of being
  stranded under 216 px of nothing. It is released with the pill, so the failed
  and stranded-footage screens get their rows back at their natural spacing.

The nine rows and the `--step-count` the reserve assumes are one number in two
files; `test_contracts.py` cross-checks them against `STEPS`.

Each step row centres its icon, label and readout as one line (the row is a
centred flex row, not a 16px/1fr grid). The error row and the footage rows stay
left-aligned inside the column: a 300-character engine traceback reads wrong
centred, and those rows are text blocks, not a status line.

### 3.3 Progress readouts

`StageStatus` is `{name, state, done, total}` (`schemas.py:42-46`). There is no
`unit` field; the unit is a static map in `panel.js`. Three rules, each forced by
a measured fact:

1. **`total === 0` renders no readout at all.** It is not 0%. It means unknown,
   and it is the *permanent* end state for a cache-served stage
   (`cache.py:49-57` returns without calling the stage, so no tick is ever
   reported) and for every stage of a `reused` job. A tick reading "0%" is a
   contradiction. Verified in the preview as screen `02c`.
2. **`transcribe` shows a time count, not a percentage.** It reports
   `(total, total)` then re-reports `(total + x, 2*total)`
   (`stages/speech.py:48,65-66`), so on any non-English footage the percentage
   halves mid-stage. `4:32 / 9:04` cannot be misread the way `100% → 50%` is.
3. **`upload` shows MB**, matching the byte unit it actually reports.

Everything else renders `NN%`.

### 3.4 Motion

| Motion | Value | Where |
|---|---|---|
| shimmer sweep | 1.2 s linear infinite | skeleton blocks |
| step slide | 240 ms `cubic-bezier(.2,0,0,1)` | a completing row moving to its resting place |
| spinner rotation | 1 s linear infinite | running step, submit button, indexing pill |
| query text sweep | 1.6 s linear infinite | search value while searching |

`prefers-reduced-motion: reduce` disables all four (a no-op on CEF < 74 — see
`known-issues.md`).

## 4. Scenarios (search)

### 4.1 Frame 03 — searching

- Submit button swaps arrow → spinner.
- Query value renders the accent sweep (above).
- Results area renders `min(previous result count, 9)` skeleton cards — one
  gradient thumb block plus one gradient caption block, radius 2px. Count
  matches the previous result count so the list does not reflow on submit; a
  first search renders 9.
- Skeletons display for at least 200ms (`§5` F3) even on a fast engine.

### 4.2 Frame 04 — results

Grid and list, toggled, choice persisted in `localStorage` under
`tempo_view`. **Grid is the default** (decision Q12).

Card (`Rectangle 5420`): 560 × 399, radius 12, fill `#171717` with a 3 px
`#171717` stroke. Hover flips both to `--accent` and the caption to white. The
`+` badge is centred on the thumbnail per the design, and the thumbnail layer is
`--thumb` (`#EB6060`) — which doubles as the free fallback while the keyframe
loads or when it 404s.

Re-derived: 2 columns at panel width, `--r-md`, 3 px same-colour stroke.

**The `+` is a `<span>`, not a control.** The card itself is a `<button>`, so
the whole row is one keyboard-reachable target and one click — satisfying
`§5` F5's "a single click on a result card" — and there is no nested interactive
element to trap focus. Both the card and the badge insert; they are the same
target.

One description line per card: the caption when the engine produced one,
otherwise the transcript. Never both — D4 exists because Florence-2 captions tend
to echo the transcript verbatim, and two near-identical strings under a thumbnail
is worse than one. The file name appears only when more than one footage is
loaded. Grid clamps the description to two lines, which at panel width truncates
the design's 58-character caption to roughly half its length — accepted knowingly
as the cost of a grid default in a 300 px panel.

## 5. Why the step list is keyed, not re-rendered

`renderJobs()` used to replace `#jobs` wholesale every 500ms
(`panel.js:169` ← `477`→`370`→`164`). `innerHTML =` builds new elements, so any
CSS animation restarts from frame zero at 2 Hz and never completes.

The step list keeps one persistent node per stage key and mutates it in place:
text and icon only when they changed. Reordering uses FLIP — measure
`getBoundingClientRect().top` before the move, apply the inverse `translateY`,
then release to 0 over 240ms. That is what makes "slides down and the next label
takes its place" render as a slide rather than a jump. There is no bar and no
high-water state to keep: progress is the running row's text (§3.3).

## 6. Errors

One inline row directly under the search box, `#error`. `CODE` in `--error`
plus the message, 11px, 1px border, radius 2px. No modal, no toast, no spinner.

**This work is layout-only.** The panel still discards the server's error code
and message on four of five actions (`SYNC_FAILED · status 403` for a quota
denial) — fixing that is a separate ticket, and the row is sized for it. Two
related bugs are also separate tickets, not UI patches:

- `ensureHost()` fails silently (`panel.js:457`) and its downstream effect is
  that every footage entry is marked `stale` with no error at all
  (`registry.py:145-149`).
- Thumbnail URLs go straight into `<img src>`, so the panel never sees the
  response; a fully unreachable engine is mapped to `404 unknown thumbnail`
  (`app.py:462-464`) and renders as nine broken images. Deliberately unchanged
  in this work (decision Q17).

## 7. Previewing without After Effects

`docs/design/preview.html` opens by double-click (`file://` works — it makes no
`fetch` call). It loads the **real** `panel/www/panel.css` and the **real**
`panel/www/panel.js`, and stubs only the two things `panel.js` talks to:
`CSInterface` and `TempoAPI`.

Because `panel.js` is a classic script, its top-level bindings are reachable from
another classic script, so the harness seeds the panel's own `store` and calls the
panel's own `render()`. The preview exercises shipped code; it does not
reimplement it.

Screens are deep-linkable — `preview.html#indexing` opens that one directly, which
is also how the headless checks drive it:

| Hash | Screen |
|---|---|
| `#empty` | no footage (frame 01) — centred block |
| `#indexing` | indexing, advancing on the 500 ms poll (frame 02) |
| `#queued` | the synthetic `queued` row while the tunnel warms |
| `#cached` | a `reused` job: every stage `done` with `total = 0` — nothing may show a number |
| `#failed` | engine failure: error state, message, Retry |
| `#searching` | skeletons, query sweep, submit spinner (frame 03) |
| `#results` | nine cards, grid (frame 04) |
| `#nocaption` | transcript shown instead of caption |
| `#list` | list view |
| `#emptyresults` | no matches |
| `#offline` / `#asleep` / `#quota` | the three inline error rows |

Any uncaught error — from the harness, from `panel.js`, or from a click handler —
is printed into the red box on the left. A silently broken preview is worse than a
loud one.

The `#app` markup is **copied verbatim** from `panel/www/index.html` and pinned by
`test_contracts.py::test_preview_markup_matches_panel`. It is copied because
`fetch` is blocked on `file://` and the preview has to open by double-click.

Two gates back this up, both in `service/tests/test_contracts.py`:

- `test_panel_js_evaluates_cleanly` runs `panel.js` through `vm.runInThisContext`
  and asserts `store` / `render` / `stepOrder` / `stepNumber` / `doSearch` exist.
  `node --check` is parse-only and would pass a file that throws on load.
- `test_panel_has_no_dead_step_bar` fails if the removed progress-bar markup,
  CSS or high-water store reappear.

## 8. Out of scope

- No new `host.jsx` entry point. The empty state instructs; it cannot import.
- `top_k` 8 → 9 (`panel.js`, `app.py`, pinned by `test_panel_top_k_matches_service`).
- The logo. The design has a `tempo_logo` wordmark with accent strokes; it is a
  Figma asset with no export in the file, so the panel ships the `Tempo` text
  mark rather than an invented one.
- The honest-error plumbing, the `ensureHost` fix, and thumbnail *failure*
  handling, per §6.