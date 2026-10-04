# ADR-0014 - The grid card body is two columns; the list body stays the design's row

- Status: accepted
- Date: 2026-10-04
- Affects: `AGENTS.md` §12; `docs/design/panel-ui.md` §4.2; `panel/www/panel.css`
- Spec of record: `docs/design/panel-ui.md`
- Design source: Figma `YJntqqRI69HtwO7aw8bbwz`, `777:368` (card caption + duration)

## Context

`777:368` draws the card's caption and duration as one baseline-aligned row with
space between them. That is a good shape when the row is 500px wide, which is
what it is in the design. In the panel it is drawn twice: the grid splits the
results area into two columns, so the row is about 122px, and the caption it
carries is a two-line clamp.

At that width the row stops reading as a caption with metadata. Two 11px strings
with an 8px gap between them read as two unrelated labels, and the file name —
which only renders when more than one footage is loaded — is left stranded on its
own line above them. The user's read was that the caption wants the left of the
body and the duration and name want the right, with the caption centred and the
metadata sitting on the bottom edge.

## Decision

### 1. Two columns in the grid, the design's row in the list

`#results.grid .body` is a two-column grid: `minmax(0, 1fr) 5em`. The description
is column 1, spanning both rows and centred; the name is row 1 and the duration
row 2 of column 2, both `align-self: end`.

The list view keeps `777:368` verbatim — caption and duration on one baseline row,
the name above, the timecode below. List cells are full panel width, so the
design's shape is right there and nothing about it needed re-deriving. One shape
per view is also why this is CSS only: `.cardrow`, the caption-plus-duration
wrapper the list needs, is dissolved with `display: contents` under
`#results.grid`, which hoists its two spans into the grid without touching the
markup or the DOM order. Nothing in the card body carries a `role` or an ARIA
attribute, so the wrapper has no semantics for `display: contents` to lose — the
claim is about the markup, not about what any given Chromium does with a
`display: contents` subtree.

The alignment is carried entirely by `align-self` on the three children, so the
grid declares no `align-items` default. A declaration nothing reads is dead
weight, and it is one specificity change away from silently winning the cascade
against the caption's centring.

### 2. The description spans both rows, and the rows are declared

`grid-row: 1 / -1` plus `align-self: center` is what centres the description
against the whole block rather than against one line.

`-1` is the end line of the **explicit** grid. With only implicit rows it resolves
to line 1, the span collapses to a single row, and the description centres inside
the name's line. This was measured, not reasoned: the first version declared only
columns and the description rendered **9px above** the body's centre while every
CSS-text assertion in `test_grid_card_body_is_two_columns_with_metadata_on_the_bottom_edge`
still passed. `grid-template-rows: auto auto` is now declared and pinned, because
the failure mode is invisible in review and invisible to the tests that check the
declarations.

### 3. The name is row 1 and the duration row 2

The name renders only when `store.footages.length > 1`, so with one footage
loaded — the common case — there is no name at all, and row 1 holds nothing.

That makes the **name** the optional line, and the row order has to put the
optional one first: when the name is absent, the empty row is the one *above* the
duration, so the duration still sits on the body's bottom edge. Reversed, the
empty row lands below the duration and lifts it off the edge in exactly the case
the panel spends most of its life in. The empty row also does useful work: it
absorbs the description's slack, which is what lets the description centre.

The duration is not, in general, "the line that always exists" — `renderResults`
gates the whole `.cardrow` on a non-empty description, so a shot with neither
caption nor transcript loses the duration too. That case is reachable, and it
renders the name alone: the name keeps row 1, bottom-aligned within it, so the
card is a name in the right column over an empty description column rather than a
name floating at the top. The test pins that shape, because it is where the
row-order reasoning would otherwise be unfalsified.

`:has()` could state the row order directly (`… .body:not(:has(.name)) .dur { grid-row: 1 }`)
and is not available. The panel's real floor is Chromium 84 — flexbox `gap`, per
`docs/agents/known-issues.md` — and `:has()` is 105. A fixed order that is correct
in both states beats a conditional the shipped CEF may not parse.

### 4. The metadata track is a definite 5em

`auto` would size the metadata track to its max-content **before** the flexible
track is resolved, so one long file name takes the width and the description
collapses to nothing. A definite track removes that question; the name's existing
`overflow: hidden` + `text-overflow: ellipsis` then does the truncating inside
it.

Measured in a 300px dock: the body is 132px wide, 126 of it content after the
card's 3px stroke and the body's 3px side padding. The metadata track is `5em`
**at the panel's 12px base — 60px**, not the 55px that reading it against the
name's 11px metadata type suggests, because `em` on the grid resolves against the
inherited font size, and `.body` inherits the 12px base. 126 − 8 (column gap) −
60 leaves a **58px** description column, about 11 characters per line under the
two-line clamp. The name ellipsizes at about nine (`interview…`); its rendered
width is 60px against 158px of text in the fixture that measured this.

## Consequences

- The grid caption gets materially shorter. `panel-ui.md` §4.2 already accepted
  truncating the design's 58-character caption to about half its length for the
  grid default; this spends part of what was left. Two-line captions now read at
  roughly a dozen characters per line. If that proves too tight in AE, `5em` is
  the one number to move and the derivation in §4 still holds.
- The name is legible in the grid only as a prefix. It is metadata and the panel
  shows the full timecode in list view; the trade was made deliberately rather
  than by omission, since the name only renders at all when more than one footage
  is loaded.
- `panel.css` gets a cache buster bump (`v=0.8.1`) per ADR-0012's convention.
- The list view is asserted unchanged by the same test
  (`#results.list .body` must not exist in the CSS, and `.cardrow` keeps its
  baseline row and its 8px gap).
- The layout is **not** verified in CI — the panel's tests pin the declarations,
  not computed geometry, which is how the 9px miss got through in the first
  place. The verification was a headless measurement of four card shapes: a
  one-line description with a name, one without, a two-line description with a
  name, and a shot with neither caption nor transcript. The first three report
  the description centred at 0.0px, the duration on the content-box bottom edge
  (6.0px above the body's border box, which is the body's own bottom padding) and
  the name 2.0px above the duration. This is the same bargain §9 already strikes
  for AE itself: no browser, no honest automation, so the check is manual and
  written down.
- The `5em` arithmetic is recorded **here** and referenced from `panel-ui.md`
  §4.2, the CSS comment and the test docstring. It was written in all four in the
  first draft and two of the four copies were already wrong (59px against a
  measured 58px), which is §8's "one owner per constant" arriving at prose.

## Alternatives rejected

**Name above, duration below, in both views.** One shape for the whole panel
reads as more consistent, and the list has room for it. It costs a `.meta`
wrapper and reorders the list card's three lines, for a view that was already
right. Two views already have two shapes — thumbnails are 16:9 in the grid and
72×41 in the list — so this adds no new concept.

**Let the name be the bottom line and accept a floating duration.** Matches the
wording of the request more literally, and puts the file name (the less
identifying of the two, and the one absent by default) in the position the
duration should hold.

**Show the name in the grid only, the duration in the list only.** Each card then
carries one piece of metadata and the grid body is just the caption. It loses the
grid's at-a-glance duration, which is the cheaper of the two facts to lose.

**Cap the caption and let the metadata take what it needs.** `grid-template-columns:
auto auto` with a `max-width` on the description. Same collapse risk as `auto`,
one token more.

## Not decided here

The timecode range. It is still list-only, because the grid has no width for a
`00:00:01:12 – 00:00:04:18` pair beside a caption. It would fit as a third
metadata line, and that is a separate call about what a grid cell should carry.