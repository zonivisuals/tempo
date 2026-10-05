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

The port scales **by type, not by frame geometry**: the panel's 13px search value
against the design's 32px is a ratio of **0.406**, and that is the ratio the
submit button already used (design 60px → shipped 24px, 0.4) before this section
existed. Frame-relative ratios are the wrong instrument here, because the frames
are 2004px wide and a docked panel is 300: the design's field is 10.7% of its
content width and the panel's is already 18%, so every geometry ratio argues for
shrinking a control that was too tight. Radii follow the same 0.406.

`search_input` (`815:294`, inside `04_search_results_frame`) measures 25px on a
196px field, which is 0.128 of the height and **10.2px** of the panel's 13px
type. It is the design's own value; the spec previously recorded 32, from the
superseded `Rectangle 5411`.

| Element | Design | Ratio | Shipped |
|---|---|---|---|
| search field | 25 / 196 | 0.128 | `--r-field: 10px` (× 0.406) |
| indexing + empty-state pill | 32 / (pill height) | — | `--r-lg: 8px` |
| submit button | 10.67 / 60 | 0.178 | `--r-sm: 4px` (0.167 at 24 px) |
| view-toggle chips | 8 / 64 | 0.125 | `--r-sm: 4px`, exact at 32 px |
| cards, thumbnails, skeleton blocks | 12 / 560 | 0.021 | `--r-md: 3px` |
| status dot | — | — | `50%`, the one exception that must stay round |

The field and the pills are separate tokens on purpose. They come from different
Figma nodes, and the pill's radius was not re-measured when the field's was, so
giving the field its own token is what stops one measurement from silently
moving two surfaces. `--r-field` is the only consumer of the corrected figure.

### The search field's spacing

Measured off a 1× render of `815:294`: the 196px field divides into 47 above the
label, a 46px ink-to-ink gap, and 53 below the value, with 42 and 40 of side
padding. ADR-0013 scaled those by 0.406 to 19.1 / 18.7 / 21.5 and 17 / 16, and
landed them on **20 / 20 / 20** and **16** at the 4px rhythm, taking the field
from 57px to 107px. **ADR-0015 reversed that to 16 / 16 / 8** on the product
owner's call — 107px is over a third of a 300px viewport before a single result.
The method did not change: the numbers still come off the design's ratios and
land on the rhythm, and the height is still a consequence of the parts.

| | Design | Shipped | |
|---|---|---|---|
| top padding | 47 | 16 | 19.1 was ADR-0013's 20 |
| label → value gap | 46 | 8 | 18.7 was ADR-0013's 20 |
| bottom padding | 53 | 16 | 21.5 was ADR-0013's 20 |
| side padding | 42 / 40 | 16 | unchanged |
| icon → label gap | 15 | 6 | unchanged |

Height follows from the parts rather than being a target: 2px of border, 16
padding, a **15.95px** label row, the 8px gap, a **24px** value row (the submit
button sets it, not the 20px input box) and 16 padding — **82px**.

**The label row changed owners.** ADR-0013 counted 21px there because the
magnifier was 21px, and said so explicitly: the icon set the row, not the 11px
text. ADR-0015 took the icon to 10px, so the row is the label text at the
inherited 1.45 and the icon no longer has a say in the field's height at all.
`test_search_field_carries_the_designs_spacing` asserts the icon is shorter than
the line it sits on, so a field that went back to counting 21 would fail rather
than quietly claim 87px.

The two rows are set by the wrong elements on purpose and the arithmetic depends
on it: the **submit button** sets the value row at 24px, not the 20px input box.

Two properties of the icon are load-bearing rather than cosmetic. Its `stroke` is
`currentColor`, not the asset's literal white, which is invisible on the light
theme; and its alpha comes from `.sb-head`'s `--text-dim` alone, so carrying
`stroke-opacity` as well would compound it — 0.4 over 0.4 lands the icon at 0.16
in the dark theme, and 0.45 over 0.45 at 0.20 in the light one. Its
`stroke-width` stays on the path because `.sb-head` must not restate it: CSS
would override the asset's `2.2751` silently, which is a conflict rather than
the harmless restatement the other paint properties are. The step icons set that
precedent, and AGENTS.md §8 wants one owner per constant.
### Other ported properties

| Property | Design | Shipped |
|---|---|---|
| search field / pill stroke | 1.5 px, `linear-gradient(#FFF 0% → #171717 100%)` at 0.28 alpha | `--edge` via a double-background `padding-box`/`border-box` clip; ADR-0015 turned it into a `180deg` ramp, `#FFF 0.16` → `#171717 0.28`, so the edge catches light from above |
| search field / pill shadow | `DROP_SHADOW 0 8 12 rgba(0,0,0,0.2)` | `0 2px 6px rgba(0,0,0,0.2)` |
| submit button | 60 px, radius 10.67, `fill #FFF @ 0.10`, no border, no shadow, "Arrow up" rotated 90°, 23 px glyph, stroke 4 round | 24 px, `--r-sm`, `rgba(255,255,255,0.1)`, glyph 16 px, stroke 1.5 |
| card stroke | 3 px, same colour as the fill | `border: 3px solid var(--surface)`, accent on hover |
| skeleton fills | `#FFF 0→0.08` on **both** blocks, radius 12 | one `--sweep` token, 0.08 peak, on `--r-md` |
| indeterminate indicator | two arcs: an accent active arc over a white track, thickness 4 of 44 | the `777:704` two-path export at 16 px, filled from CSS: `.arc` → `--accent`, `.track` → `--spin-track` |
| running row's indicator | 12-ray burst, `777:709`, accent | the same export at 16 px, `stroke="currentColor"` with `color: var(--accent)` |
| wordmark | `tempo_logo`, `777:761`: white caps, two accent marks (the E's middle arm, a wedge at the O's shoulder) | `panel/www/logo.png` at `height: 14px`, `width: auto` |
| view-toggle chips | `777:473`: 64 px square, radius 8, 16 px apart, active one filled `#171717` and the other bare | 32 px square, `--r-sm`, 8 px apart, active one filled `--surface` and the other bare |
| view-toggle icons | the `777:473` exports: a 38-unit box around a 32-unit glyph; the grid is 4 outlined squares at stroke 3.5625, the list is 3 rules and 3 bullets at stroke 3.16667 | the same path data, `viewBox="0 0 38 38"` at 19 px, `stroke="currentColor"`; the chip carries no `stroke-width` so each icon keeps the weight the design exported |

### The view pair keeps the design's ratios, not its pixels

`777:473` is two 64 px chips 16 px apart, and the left edge of the pair lines up
with the first card rather than with the search field above it — measured on the
rendered frame, the chip and the card both start at x=124 while the field starts at
x=88. The panel has no such second inset: `#app`'s children are all flush, so the
pair lands on the card grid, which is the line the design chose.

Nothing here scales linearly. At the 2004→300 frame scale a 64 px chip would be
10 px, and `§1`'s icon floor pins the glyph at 16 px regardless. So the shipped
control holds the *shape* and drops the pixels:

| | Design | Ratio | Shipped (32 px chip) |
|---|---|---|---|
| chip | 64 | — | 32 |
| radius | 8 | 0.125 | `--r-sm` 4 px, exact |
| gap between chips | 16 | 0.25 | **0** — ADR-0015 removed it |
| icon slot | 38 | 0.594 | 19 px |
| glyph | 32 | 0.5 of the chip | 16.0 px, on AGENTS.md §6's floor |

The chip is 32 rather than 24 because of the icon. The exported asset is a 38-unit
box, and 38/64 of a 32 px chip is 19 px exactly — which puts the 32-unit glyph on
16.0 px, AGENTS.md §6's floor rather than through it. The same asset in the 24 px chip it
replaces renders a 13.5 px glyph, which is why the chip grew at all. At the 4 px
rhythm of this section the vertical gaps do not port: the design's 76 px and 48 px
are 11 px and 7 px at frame scale, and neither lands on `#app`'s uniform 8 px —
which is why `#searchmeta` carries its own 16 px top margin instead.

**The chips touch, and that is the departure.** ADR-0015 removed the 16-of-64 gap,
so the pair is one 64 px control and the pressed fill is the only thing marking
the active view. The state survives — the fill and the accent glyph — but the two
chips no longer read as two things, which is the price of the row's tightness.
Every other ratio above is the design's.

The active view is marked by the fill, as drawn: the pressed chip is filled
`--surface` and the other one is `transparent`, because two identical fills read as
two chips and carry no state. AGENTS.md §6's accent still names the working view in
the glyph. The icons are the design's own exports, not redrawn — the list icon's
three bullets are zero-length segments that `stroke-linecap: round` draws as dots,
and flattening them into three bare rules is what the panel used to ship. At 19 px a
bullet is the icon's own stroke width, 1.6 px, and lands on one device pixel: that
is the design's proportion carried through the scale rather than a dot redrawn to
suit it, and it is legible in the preview at `#list`.

The design has no footage filter, so it says nothing about where ours goes once
the pair moves left. The pair is the row's first child and the row's `auto` margin
belongs to the filter, which is the only other thing in it: view mode left on the
card grid, scope right.

### The wordmark is an asset, not traced geometry

`tempo_logo` (`777:761`) is a **raster image fill** in the file, not a vector, so
there is no path data to port and nothing to theme with `fill: currentColor` the
way the inline icons do. It ships as exported PNG — 280×49, `#FCFCFC` letters,
both accents in the same `#F6480A` — at `height: 14px`; the asset's 40:7
proportion makes 14px of height exactly 80px of width, and `width: auto` keeps it
from distorting. `test_panel_header_is_the_wordmark_not_a_navbar` reads the PNG's
own header and asserts that arithmetic against both the CSS and the `<img>`
attributes, so a swapped or re-proportioned asset fails rather than skewing.

It is deliberately **not** re-drawn as SVG. Bold geometric letterforms traced by
eye would be an invented mark wearing the real one's proportions, which is the
thing `§8` and the earlier "text mark rather than an invented one" rule exist to
prevent.

On the light theme a near-white raster on `#d6d6d6` is invisible, so
`html.light #logo` applies `filter: invert(1) hue-rotate(180deg)`: the letters go
black and the 180° rotation carries the accents' hue back, where a plain `invert`
would leave them cyan. Verified against the asset — `#F6480A → #F54709`.

`panel/www/logo.png` is the first raster in `panel/www/`, which is otherwise
inline SVG only. `docs/design/preview.html` repoints the `src` at it from
`preview-harness.js` rather than editing the markup, because
`test_preview_markup_matches_panel` holds the `#app` blocks byte-identical.

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

**Spacing**: 4 px rhythm (design `itemSpacing` 12 → 4). The one departure is
`#searchmeta`'s 16px top margin: the design's 76 px and 48 px of vertical space
are 11 and 7 at frame scale, and neither lands on `#app`'s uniform 8.

**Icons**: 16px is the floor, not the size. The field's magnifier is the one
export below it: the design exports a 21×21 path, and ADR-0015 took it to **10px**,
which is **0.476** of that box — the type's 0.406 would say 8.5, and 10 is the
next step up the rhythm from there — where the design's own 2.2751 stroke lands on
**1.08px**. It is the silhouette in the panel that survives that loss, and §6
names it as a bounded exception rather than leaving the floor open. Everything
else is at or above 16px: the view pair's glyph is exactly 16, the step icons are
16, and the result card's insert badge floors at 16 (it is sized rather than
exported, so it scales with a `max()` instead — see §4.2).

## 2. Layout

One scrolling column. The four Figma frames are four *scenarios*, not four
routing targets — a docked panel has no screen stack, and a strict switcher
would make it impossible to search footage that is already `ready` while
another file is still indexing (§5 F2).

```
#topbar       wordmark · status dot · Sync now                      (always)
#searchbox    label + value + submit                                (ready footage only)
#error        inline error row                                       (on error)
#searchmeta   view pair (left) · footage filter (right, >1 footage)  (ready footage)
#indexing     status pill + step list + footage rows                (job live)
#results      skeletons | cards | empty state | no-results
```

**No hide/show toggle.** The stage list is shown whenever a job is live and
disappears when none is; a failed job keeps its message and Retry visible. The
eye control is gone from `index.html`, and `store.index` is gone from `panel.js`.
A search does not collapse it either — searching with a job running shows the
list and the results together.

The header is always visible — `§4.4` requires engine reachability to render
honestly, and it has no home in the Figma frames. What it renders is the
shortest honest form: the wordmark, the dot, the button. ADR-0012.

`#searchbox` and `#searchmeta` render only when at least one footage is `ready`;
`#footage-filter` is the one part of that row that needs **more** than one, so it
carries its own `hidden` and the row itself does not. Below that the panel shows
the indexing scenario (frames 01/02), which matches the design: neither frame has a
search field.

## 3. Scenarios

### 3.1 Frame 01 — no footage

No search field. No indexing block. Centred on both axes, by the same mechanism
as frame 02: the block gets `margin: auto` inside `#app`'s column (`#results`
carries `centered` while it holds nothing else), so with only the header above
it, it sits in the middle of the panel instead of hanging under the bar.
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

### 3.1a The block is the shape for every "nothing to show"

The no-matches screen used to be one `--dim` sentence in a bare div at the top of
the results area, so the panel had two shapes for the same fact. It is a block
now, and so is the screen before any search has run:

| Condition | Heading | Hint |
|---|---|---|
| a search returned nothing | `No shots found` | `Nothing in this project matches "<query>". Try a word from the dialogue or captions.` |
| ready footage, no search yet | `Ready to search` | `Type a few words to find shots across your footage.` |

The query is quoted back because the editor needs to see what was actually
searched, and `overflow-wrap: anywhere` on the hint is what keeps a long unbroken
query from widening the block past the panel — `max-width` alone does not stop
one. The no-matches block is centred like frame 01, which is a change of
geometry: it used to hang under the search field. Cards and the skeleton list
stay top-aligned, since a centred grid would float in a panel that has a search
field above it.

The block has an optional third line, `.detail`, in `--dim` one step below the
hint: the service's own line verbatim, for the states that have one (§6).

### 3.1b A failure names itself

| Code | Heading | Instruction |
|---|---|---|
| `SERVICE_OFFLINE` | `Service offline` | `The local Tempo service is not responding. Start it, then press Sync now.` |
| `BACKEND_ASLEEP` | `Engine asleep` | `The GPU engine is not running. Start the instance, then search again.` |
| `BACKEND_UNREACHABLE` | `Engine unreachable` | `Tempo cannot reach the GPU engine. Check the tunnel, then search again.` |
| `BACKEND_TIMEOUT` | `Search timed out` | `The engine took too long to answer. Search again.` |
| `QUOTA_EXCEEDED` | `Limit reached` | `This project is over your plan's footage limit. Footage already indexed stays searchable.` |

A code in the heading is a label, not a name: `BACKEND_ASLEEP` says nothing about
what stopped, and nothing about what to do. So the heading is a state in words and
the instruction is the action — the part the editor can take. The service's own
message is not quoted on these four, because it restates the heading
(`service offline`, `engine search failed`) and says less.

`QUOTA_EXCEEDED` is the exception, and the reason is in its `.detail` line: the
numbers are the useful part. The panel's wording says a limit was reached, and the
service's own sentence carries which plan, what it allows and what the project
holds — `plan 'free' allows 3 footage; project holds 4`. §7.3 keeps that number out
of the panel, so raising the limit on the server changes this line with no panel
change. Its instruction also says what is still true: a denial on `/sync` gates new
work only, and footage already indexed stays searchable.

The heading is `--accent`, like every other block. `--error` stays where the state is
already carried: the header dot (ADR-0012) and the retained inline row.

A code with no row in this table falls back to `Request failed`, with the service's
message as the instruction and the code on the `.detail` line, so a new backend error
cannot leave the panel blank. Nothing about the deployment is written here — no
instance name, no port, no path, no plan limit (§7.3); every number an editor needs
arrives from the service.

Both routes into the block are **clamped**: a job error is 2000 characters of engine
traceback, and a block that tall is not a message. The cut is marked with an ellipsis,
the way the indexing error row's is.

`Search for anything` is **kept**, reversing the earlier decision to drop it.
§6 bans placeholder *copy* — the species this was read as, and the reason it was
cut — but the design draws it as a permanent label line above the value, not as
a `placeholder` attribute that disappears on the first keystroke. That is a
field label, which §6 does not name, so the original reading conflated the two.
It is still a label rather than the input's accessible name: the input carries
no `aria-label` today, and that gap is unchanged by this.

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
under the header. Three details decide how it reads:

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
| query shimmer | 1 s linear infinite | search value while searching |
| step slide | 240 ms `cubic-bezier(.2,0,0,1)` | a completing row moving to its resting place |
| spinner rotation | 1 s linear infinite | running step, submit button, indexing pill |

The two shimmers are deliberately not the same speed. The query's band travels
`W + 2 × spread` per cycle, where `W` is the mirror's shrink-to-fit **text** width —
so its speed depends on how long the query is, roughly 150 px/s on a three-character
query and 320 px/s at a full 200 px field, against the skeleton sweep's fixed
~220 px/s (ADR-0017).

`prefers-reduced-motion: reduce` disables all four (a no-op on CEF < 74 — see
`known-issues.md`), and the query additionally **gives the gradient up and takes its
own text colour back** — see §4.1.

## 4. Scenarios (search)

### 4.1 Frame 03 — searching

- Submit button swaps arrow → spinner.
- Query value renders the shimmer (below).
- Results area renders `min(previous result count, 9)` skeleton cards. Count
  matches the previous result count so the list does not reflow on submit; a
  first search renders 9.
- Skeletons display for at least 200ms (`§5` F3) even on a fast engine.
- The view pair is present and unchanged from frame 04, on the left as drawn (§1).

**The query shimmer is one text layer.** `#q-sweep` paints the query by itself: the
band is a gradient clipped to the glyphs, and that gradient's *outer stops are the
resting colour*, so the dim query is visible and one brighter band travels across it.
The shape is shadcn/ui's `shimmer` utility — its 20° tilt (so the gradient is
`110deg`), its `calc(3ch + 40px)` spread, and its `calc(200% + spread × 2)` sizing,
which is what puts the band clear of both ends at the keyframe's extremes so the loop
never wraps. Direction is right to left, the direction the skeleton sweep already
runs in, at 1 s.

It is **not** an accent sweep. ADR-0011 shipped the band in `--accent`, which §6
fences to selection and active states; a search in flight is neither, and this is
greyscale.

| | level | token |
|---|---|---|
| resting | 0.40 dark / 0.45 light | `--text-dim` — the level of the `Search for anything` label above it |
| mid | 0.60 / 0.66 | `--qsweep-mid`, the half-mix of the two ends |
| peak | 0.80 / 0.88 | `--text` — the level a value normally reads at |

Those are not chosen numbers. The utility derives its highlight from `currentColor`
(lightness +0.4, alpha +0.4 in dark), and over `--text-dim`'s 0.4 that lands exactly
on `--text`'s 0.8. The utility reaches that through `oklch(from currentColor …)` and
`color-mix()`, far above this panel's Chromium 84 floor — but the two levels it lands
on are tokens the panel already has, so the base and the peak are written as
`var(--text-dim)` and `var(--text)` and only the half-mix is a literal. One `--qsweep`
shape for both themes; the light theme overrides `--qsweep-mid` and nothing else
(ADR-0017 §2–§3).

**Under `prefers-reduced-motion: reduce` the query renders plainly**, in
`--text`. This is not tidiness: the layer's text is transparent by construction, so
`animation: none` alone parks the band clear of the string and leaves the field
**blank** mid-search. The skeletons keep ADR-0016's resting-position answer instead,
because their resting state is a shape rather than text.

**The skeleton is `loading_result` (777:532) and nothing else.** The design draws
it as a transparent 560 × 399 frame holding two blocks, with no stroke and no
fill of its own:

| | Design | Shipped |
|---|---|---|
| frame | 560 × 399, no fill, no stroke | `.card.skel` drops the card's 3px stroke and `--surface`, and takes a 3px `padding` |
| `thumb-sk` | 554 × 312 at x=3, radius 12 | fills the frame's inset, `--r-md`, `padding-top: 56.25%` |
| gap | `cap-sk` starts 18 down | `margin-top: 4px` (18/560 is 4.2px on a 132px thumb) |
| `cap-sk` | 560 × 69, radius 12 | the body box: 44px, `--r-md` |
| fill | `#FFF 0→0.08`, **both** blocks | one `--sweep` token at 0.08, over a `--surface-2` base |

Three of those are re-derivations rather than copies, and each has a reason.

**The inset is the frame's padding, not the blocks' margin.** That is the
load-bearing detail. `thumb-sk` is 554 wide at `left: 3` of a 560 frame — inside
the card's 3px stroke — so the panel's inset is the stroke width, the same value
the stroke used to have. It has to live on the frame: percentage padding resolves
against the *containing block*, so a margin inset would leave the block sized
138 × 0.5625 = 77.6px while the real thumbnail, inside the stroke, is
132 × 0.5625 = 74.25px. On the frame, the containing block is already the inset
width and the two are identical.

**The thumb's aspect is the design's own.** 312 of 554 is 0.5632, which is 16:9
to within 0.1%, so `padding-top: 56.25%` is the design's ratio and not a
convenience.

**The cap is the body, not a number.** The design's 69 is its body box at 20px
caption type; the panel's caption is 11px, so the same box is two lines at the
inherited 1.45 plus the body's 6px above and below — 44px. Taken literally, 69 of
560 would be 17px here and **every row would jump** when results arrive, which is
the reflow the count rule exists to prevent. With 44 the skeleton is 122.2px
against a real card's 124.2 — the difference is the card's 6px of stroke less the
4px the skeleton spends as a gap — and the design has the same slack: its
skeleton fills all 399 while its result card insets 3px. That figure is the
two-line-caption case, which is what the grid clamps to; a caption that comes back
one line short still shortens its card, because a content-sized card cannot be
predicted.

**The blocks keep a base the design does not draw.** `--surface-2` sits under the
ramp. The design paints no base on either block, so this is ours, and it is what
gives a block a resting shape when the sweep is at its faintest or disabled.

**The fill is one level, not two.** The design gives both blocks the *same* white
at 0.08. The panel had two tokens with two invented peaks — 0.56 on the thumb,
1.0 on the caption — and the caption's was pure white, which on a dark card is
the brightest pixel on the screen. `--sweep-thumb` and `--sweep-cap` are now one
`--sweep`, which is what §8's "if a literal appears twice, it's a constant" asks
for when the design itself says the two are equal. The light theme is the same 8%
lift in the other direction, the `--spin-track` precedent.

The blocks' resting `background-position` is the keyframe's end state, so
`prefers-reduced-motion` — which sets `animation: none` and leaves the rest of the
declaration standing — shows a centred peak rather than a ramp pinned to the left
edge.

### 4.2 Frame 04 — results

Grid and list, toggled, choice persisted in `localStorage` under
`tempo_view`. **Grid is the default** (decision Q12).

The pair itself is `777:473` and is ported by ratio, not by pixel — see §1, "The
view pair keeps the design's ratios, not its pixels" for the measured design
geometry, the 32 px chip, the 19 px icon slot and why the pair is left.

Card (`Rectangle 5420`): 560 × 399, radius 12, fill `#171717` with a 3 px
`#171717` stroke. Hover flips both to `--accent` and the caption to white. The
`+` badge is centred on the thumbnail per the design, and the thumbnail layer is
`--thumb` (`#EB6060`) — which doubles as the free fallback while the keyframe
loads or when it 404s. The thumbnail takes `--r-md`, the same 12 of 560 the card
has: §1 has always listed `--r-md` as covering thumbnails and the rule had never
declared it, so a keyframe sat square inside a rounded card.

Re-derived: 2 columns at panel width, `--r-md`, 3 px same-colour stroke.

**The insert badge** is the circle-plus path at `fill="currentColor"` with
`.plus { color: var(--accent) }` — the same token-plus-currentColor pattern the
step icons use, and one owner for the accent instead of a literal hex that is
right on the dark theme and wrong on the light one.

Its size is `max(16px, 18%)` **of the thumbnail**, because the thumbnail is not
one size: it is the grid cell's width, which moves with the dock, and a fixed
72 px in the list view. 18% is the share that lands on 23.8 px at a 300 px dock
(24 / 132), which is where it was sized. It is **not** read off the design, whose
badge box is unmeasured — the badge is the one asset in the panel whose geometry
is not the design's, and ADR-0015 §4 records that so no later reader assumes
otherwise. The floor is load-bearing: 18% of the list view's 72 px thumb is
12.96 px, under §6's 16 px. `max()` is Chromium 79 against the panel's real floor
of 84. Height comes from the asset's own square `viewBox` at `height: auto` — not
`aspect-ratio` (Chromium 88), and not a percentage height, which for an
absolutely positioned element resolves against the thumb's *height* and would
squash the ring.

**The `+` is a `<span>`, not a control.** The card itself is a `<button>`, so
the whole row is one keyboard-reachable target and one click — satisfying
`§5` F5's "a single click on a result card" — and there is no nested interactive
element to trap focus. Both the card and the badge insert; they are the same
target.

One description line per card: the caption when the engine produced one,
otherwise the transcript. Never both — D4 exists because Florence-2 captions tend
to echo the transcript verbatim, and two near-identical strings under a thumbnail
is worse than one. The file name appears only when more than one footage is
loaded.

**The grid body is two columns; the list body is the design's row.** `777:368`
puts the caption and the duration on one baseline-aligned row with space between
them, and the list view still does exactly that. In a half-width grid cell that
row reads as two loose ends rather than as a caption with metadata, so the grid
body is re-derived (ADR-0014): the description is the **left** column, centred
vertically; duration and file name are the **right** column, on the body's bottom
edge.

| | column 1 — `1fr` | column 2 — `5em` |
|---|---|---|
| row 1 | `.cap` — spans **rows 1–2**, centred | `.name`, bottom-aligned |
| row 2 | | `.dur`, bottom-aligned |

Three details are load-bearing rather than taste:

- The description spans **both** rows (`grid-row: 1 / -1`) so it centres against
  the whole block. On the first row alone it centres against the name's line and
  sits visibly high. The rows are therefore declared explicitly — `-1` is the end
  of the *explicit* grid, and with implicit rows the span silently collapses to
  one. That was measured, not reasoned: the description rendered 9px above centre
  while every text assertion still passed.
- The **name is row 1 and the duration row 2**, because the name is the optional
  line — it renders only when more than one footage is loaded. When it is missing,
  the empty row is the one *above* the duration, so the duration stays on the
  bottom edge. Reversed, the empty row lands below it and lifts the duration off
  the edge in the single-footage case, which is the common one. `:has()` would say
  this directly and is not available — Chromium 84 is the panel's real floor
  (`docs/agents/known-issues.md`).
- The metadata track is a definite `5em`, not `auto`. An `auto` track is sized to
  max-content before the flexible track is resolved, so one long file name starves
  the description to nothing instead of ellipsizing.

A shot with **neither** caption nor transcript renders the name alone: the
duration rides inside the description's `.cardrow`, so it goes when the
description does. The name then holds row 1, bottom-aligned within it — a name in
the right column over an empty description column, not a name floating in row 1 of
a two-row grid.

Grid clamps the description to two lines, which at panel width truncates the
design's 58-character caption to roughly half its length — accepted knowingly as
the cost of a grid default in a 300 px panel. The metadata column spends more of
it again: `5em` is 60px at the panel's 12px base, and out of the body's 126px of
content minus the 8px column gap it leaves a measured 58px of description, about
11 characters per line. The name ellipsizes at about nine (`interview…`). Both
are visible in `docs/design/preview.html#results`, whose width slider is the
check.

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

A failure with **nothing else on screen** is not that row: it is the §3.1 block,
centred, and the row stands down so the same fault is never printed twice. Which
of the two speaks is one decision — `resultsScreen()` — read by both:

| `resultsScreen()` | `#results` holds | The row |
|---|---|---|
| `job` | nothing (a live job owns the panel) | speaks |
| `searching` | skeleton list | speaks |
| `error` | the failure block | **stands down** |
| `empty` | frame 01 | speaks |
| `nomatch` | the no-matches block | speaks |
| `results` | cards | speaks |

`error` sits above `empty` deliberately: with the service down and no footage
known, `No footage found` is a claim about the project the panel cannot make —
it does not know whether the project has footage, it knows it could not ask. It
also requires an empty result set, because an error arriving over cards is the
row's business: the block would wipe results the editor is still reading.

Each failure names itself in the block's heading and says what to do underneath;
the service's code goes on the third line (§3.1b). The row keeps its own
`CODE · message` format and its `--error` colour for the errors that arrive over
content.

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
| `#emptyresults` | no matches — the §3.1a block |
| `#idle` | ready to search — the same block, no query yet |
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
- The honest-error plumbing, the `ensureHost` fix, and thumbnail *failure*
  handling, per §6.