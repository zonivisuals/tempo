# ADR-0011 — Panel UI derived from the Figma design: motion allowed, dimensions re-derived

- Status: accepted
- Date: 2026-10-03
- Affects: `AGENTS.md` §6, §5 F3, §4.4; `PRODUCT.md` F3/F6; `docs/ui-review.md`; `docs/release.md`; `panel/www/*`
- Spec of record: `docs/design/panel-ui.md`
- Design source: Figma `YJntqqRI69HtwO7aw8bbwz`, group `TEMPO_project_frames` (node `777:771`)

## Context

`AGENTS.md` §6 was written as a prohibition list, and it was enforced: the repo
had exactly one animation (`panel.css` opacity pulse on skeleton blocks), zero
`transition` declarations, zero `@media` queries, and a CSS comment stating the
rule in its own voice — *"Loading = opacity pulse. No gradients, no shadows."*

A four-frame Figma design landed for the panel. It specifies a shimmer sweep on
the running indexing step, an accent sweep on the query text while searching, a
circular-indeterminate spinner on the submit control, a gradient shimmer on the
result skeletons, a full-card accent inversion on hover, and a step that slides
into place on completion. Every one of those is named in §6's "Don't" list or in
§5 F3.

Two facts made the naive options untenable:

**The frames are 2004 × 1919 px.** A docked AE panel is ~300–360 px wide. The
design's own search field is 1836 px of 32 px type; its result grid is three
columns of 560 px cards. Ported literally to panel scale, the type renders at
about 5 px. The design cannot be a 1:1 spec for this host.

**The animations cannot survive the existing render loop.** `renderJobs()`
replaced `#jobs` wholesale every 500 ms. `innerHTML =` constructs new elements,
so any CSS animation on them restarts from frame zero at 2 Hz. A 1.2 s sweep
would never complete; a slide would stutter. The requested motion was
impossible to ship without first changing how the step list renders.

## Decision

### 1. Motion is permitted, under a budget

Shimmer, indeterminate spinner, and state-transition animation are allowed.
They are not decoration here: each encodes a state the editor cannot otherwise
see — which step is live, that their query is in flight, that a step just
finished. That is the test §6 already had ("anything that moves that doesn't
inform"), applied honestly rather than by keyword.

What is **not** reversed by this ADR:

- radius ≤ 2px (the design's 32/12/8 px radii do not come across)
- one accent colour, monochrome surfaces
- 4px spacing rhythm, 12px/11px type, system font stack
- icons identifiable at 16px
- thin flat progress bars
- no modals, no toasts, no placeholder filler copy
- every click does one obvious thing; all mutations undoable
- no emoji UI

`§6`'s "Don't" entries on gradients, glows, glassmorphism, shadows-as-decoration,
big radii, pills and spinners-where-skeletons-belong are **deleted**. `§6`'s
"Do" list stands except that "loading = opacity-pulsing skeletons" becomes
"loading = skeletons and progress indicators may pulse, sweep or spin".

**Budget: at most two animated surfaces on screen at once.** In practice:
one running step row, or one spinner, or one skeleton field.

### 2. Dimensions are re-derived, not ported

The design is the mood board; `docs/design/panel-ui.md` is the spec. Every px
value is re-derived for panel scale, recorded in a table next to its design
value so a future Figma revision can be checked against it rather than
eyeballed.

### 3. Tempo ships two themes; `appSkinInfo` selects one

§6 previously required deriving background, border *and* text from
`appSkinInfo` — and flagged as an open gap that only `--bg` was derived
(`panel.js:52`). The design is dark-only and AE ships a light theme.

Resolution: the Figma palette becomes Tempo's **dark** theme; a light theme is
derived from it; `getHostEnvironment().appSkinInfo` is used to detect which to
apply. Tempo no longer mirrors an arbitrary custom AE panel colour. This
amends §6's theming sentence and closes the gap §6 itself recorded — the two
panels cannot both be "the source of truth" for `--text`.

### 4. Stage names stay service-owned; labels are presentation

The design lists seven steps and silently drops `ocr` and `text`, merging the
tail into "Finalizing". §4.4 requires the stage list to come from the service,
which takes it from engine `/v1/health`. Nine rows ship: the eight real stages
with editorial labels from a static map in `panel.js`, plus one synthetic row
bound to job `state === "queued"` covering the tunnel-warmup gap.

### 5. The step list is keyed, not re-rendered

One persistent DOM node per stage key, mutated in place, reordered with FLIP.
Required for the requested slide animation; also removes the 2 Hz animation
restart that made any motion impossible.

### 6. Progress numbers obey the data

`total === 0` renders no number — it means unknown, and it is the permanent
state for cache-served stages and for every stage of a `reused` job.
`transcribe` renders a time count rather than a percentage, because it reports
`2 × total` mid-stage and a percentage that halves reads as broken. Bar width
is a per-stage high-water mark and never rewinds.

This is §8's "no fake progress" applied to a case it did not anticipate: not a
fabricated number, but a real one that is meaningless.

## Consequences

- `docs/design/panel-ui.md` is the reviewable spec; this ADR is the rationale.
  Both, plus the four spec files, must land together (§11).
- The step list and the results list are now two different render strategies
  (keyed vs. rebuilt). `#results` only re-renders on discrete transitions, not
  on the 500 ms poll, so rebuilding it is still correct.
- The step list is ~9 rows. At 20px + 4px gap that is 212px, which fits a
  docked panel but is the tallest thing in it.
- Grid mode truncates the design's 58-character caption to roughly half its
  length at panel width. Accepted knowingly; grid is the default.
- **Three known gaps are explicitly not fixed here** and get their own tickets:
  the panel discards the server's error code and message on four of five
  actions; `ensureHost()` fails silently and its downstream effect marks every
  footage `stale` with no error; and thumbnail failures render as broken images
  because the URL goes into `<img src>` and an unreachable engine is mapped to
  `404 unknown thumbnail`. The error row's layout is sized for the first.
- `prefers-reduced-motion` is unavailable on the declared CEP 9 floor
  (Chromium 61; the query landed in 74). It is shipped anyway and no-ops on
  old CEF. The manifest divergence is now real and recorded: `panel.css` already
  used flexbox `gap` (Chromium 84) before this ADR.

## Alternatives rejected

**§6 wins, translate the design into the existing vocabulary.** Rejected: the
editor asked for a specific interaction language, and the running-step shimmer is
the clearest signal in the whole indexing UI. A pulse cannot say "this one, not
those five" as well.

**Ship the design at its native width.** Rejected: unusable at any sane panel
width.

**Two layouts, narrow and wide.** Rejected: doubles the CSS surface and the QA
matrix for a design that will be revised.

**Strict view switcher between the four frames.** Rejected: the Figma frames
have no indexing UI and no search field, which as routing targets would make it
impossible to search footage that is already `ready` while another file is still
indexing — a direct §5 F2 regression, and the common case on the 3-footage free
tier.