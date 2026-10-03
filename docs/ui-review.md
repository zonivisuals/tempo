# UI review gate (AGENTS.md §6, ADR-0011, `docs/design/panel-ui.md`)

Before release, screenshot the panel docked next to a native AE panel
(Project or Timeline) at 100% scaling and walk this list. Any reviewer can
flag and reject an element reading as "AI-generated slop".

## Must hold

- [ ] The design's radii, ported as ratios: 8px on the search field, the CTA and
      the indexing pill; 3px on cards and skeleton blocks; 4px on buttons. The
      7px status dot is the one documented exception. Compare against
      `docs/design/panel-ui.md` §1, not against a flat 2px rule.
- [ ] The search field carries the design's 1.5px white→surface gradient edge at
      0.28 alpha and its shadow. No shadow anywhere else.
- [ ] 12px base / 11px metadata, system font stack, 4px spacing rhythm.
- [ ] Monochrome + at most one accent, used only for selection/active.
- [ ] Progress is the running row's own readout — a percentage, or the real unit
      (MB, audio seconds) — not a bar. `total == 0` renders no readout at all:
      check the `reused`-job screen (`preview.html#cached`) for a stray "0%".
- [ ] Loading = skeletons that may pulse or sweep.
- [ ] **No more than two animated surfaces on screen at once.** In practice:
      one running step, or one spinner, or one skeleton field — never two.
- [ ] Every animation answers "what state is this?". A sweep that decorates
      rather than informs is rejected here exactly as a spinner over a skeleton
      would be.
- [ ] Indexing section: a status pill reading "Processing your videos" with the
      two-arc indicator, and the step list. **No summary line and no file name**
      anywhere on this screen outside the footage rows. **There is no hide/show
      toggle** — the list is shown whenever a job is live and gone when none is,
      and a failed job keeps its message and Retry.
- [ ] Step list: the running stage at the top with its readout, finished stages
      dimmed below it with a check. **A stage that has not started draws no row** —
      check `preview.html#indexing` early in the run: the list must not be a
      column of dim placeholders, and `preview.html#queued` must show the single
      synthetic queued row. No step renders a number when `total` is 0.
- [ ] Short factual labels ("Indexing · OCR 37/157"); result cards show
      thumbnail, file name when more than one footage is loaded, timecode range +
      duration, and **one** description line (caption, or transcript when the
      engine produced no caption — never both). No score bars, no percentages, no
      result-count line above the grid, no separate Insert button.
- [ ] Errors are compact inline rows under the search field with the service
      error code — no modals, no toasts.
- [ ] Offline service renders a usable degraded state, never a blank panel.
- [ ] The no-footage heading is a status pill (`role="status"`), not a button — a
      disabled control that cannot be pressed is a dead affordance.

## Review it without After Effects

`docs/design/preview.html` opens by double-click and renders every screen with
the real `panel.css` and `panel.js`. Deep-link a screen with
`preview.html#indexing`, `#cached`, `#failed`, `#results`, `#list`, `#quota` and
the rest — the full list is in `docs/design/panel-ui.md` §7. Any uncaught error
prints into the red box on the left.

## Instant reject

Glows, glassmorphism, shadows on any surface other than the two pill surfaces,
floating chips, purple/blue AI palettes, emoji UI, "Ask anything…"/"Powered by"
copy, exclamation marks, animated backgrounds.

A gradient is acceptable **only** as the mechanism of a loading sweep (skeleton
blocks, the accent band travelling across the query text) or as the search
field's and pill's 1.5px edge — never as a decorative surface treatment.
