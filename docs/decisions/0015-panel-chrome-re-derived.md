# ADR-0015 - The search field, the view pair and the insert badge, re-derived

- Status: accepted
- Date: 2026-10-05
- Affects: `AGENTS.md` §6, §12; `docs/design/panel-ui.md` §1, §4.2; `panel/www/*`
- Spec of record: `docs/design/panel-ui.md`
- Design source: Figma `YJntqqRI69HtwO7aw8bbwz`, `search_input` (`815:294`) and the view pair (`777:473`)
- Reverses: ADR-0013 §2 and §4; the D18 addendum's 8px pair gap

## Context

Five changes to the panel's chrome, made together in one working session, none of
which the specs described. Three of them reverse something ADR-0013 or the D18
addendum had just decided, and two of those reversals left `panel.css` and
`index.html` describing numbers that were no longer in either file.

That second half is the reason this is a decision and not a patch. The port's
method is that every number is derived from the design, recorded in
`panel-ui.md`, pinned by a test, and explained in the comment next to it. A
change that moves the number without moving the three things that hold it
produces a comment that lies, a spec that lies, and a test that fails for a
reason nobody can reconstruct. `AGENTS.md` §0 rule zero and §9's regression rule
both require the record to move with the value.

## Decision

### 1. The search field is 82px, not 107px

ADR-0013 measured `815:294` off a 1x render — a 1836×196 field whose top
padding, ink-to-ink label-to-value gap and bottom padding are 47 / 46 / 53, with
42 / 40 of side padding — and landed them on 20 / 20 / 20 and 16 at the 4px
rhythm. The label-to-value gap was the substance of that ADR: at the 2px it
replaced, the label and the query read as one sentence in a box.

The product owner's call is 16 / 16 / 8. The method does not change: the numbers
still come off the design's ratios and land on the rhythm, and the height is
still a consequence of the parts rather than a target. What changed is the reading
— 107px is over a third of a 300px viewport before a single result exists, and
the design's own 196px field is 10% of a 2004px frame while the panel's is 18%.

```
2 border + 16 padding + 15.95 label row + 8 gap + 24 value row + 16 padding = 82px
```

The label row is the 11px label text at the inherited 1.45, **not** the icon.
ADR-0013's 21px there was the icon — the design's export, deliberately exempt
from the scale — and §1 below removes that exemption, so the row's owner changes
hands. `test_search_field_carries_the_designs_spacing` asserts the icon is
shorter than the line it sits on, because a test that still counted 21 would
claim 87px and be wrong without failing.

### 2. The magnifier is 10px, and §6's floor gains its one exception

The design exports the field's magnifier as a 21×21 path with a 2.2751 stroke.
ADR-0013 shipped it at 21, on the grounds that 0.406 of 21 is 8.5px and "at the
magnifier's 2.2751 stroke a smudge", and turned §1's "16px" into a floor rather
than a size.

It now ships at 10px. That is **0.476** of the export, not the type's 0.406: the
type ratio would say 8.5px, and 10 is the next step up the 4px rhythm from there —
chosen because the icon sits beside 11px label text and 8.5px is a smudge at both
sizes. 10 / 21 × 2.2751 is a **1.08px** stroke, which is the honest cost and the
reason the exception is bounded rather than open: `AGENTS.md` §6 now names this
icon as the one export below its 16px floor, and the test recomputes 1.08 from the
shipped `width` and the design's `stroke-width`, so a future resize that changed
either number would fail rather than drift.

The number is a product-owner call and is recorded as one. An earlier draft of
this ADR described 10px as "the same 0.406 the type uses, rounded to the rhythm",
which is arithmetically false — 0.406 of 21 is 8.5, and 10 is 0.476. The three
files that repeated the claim were corrected with it.

A 10px magnifier is under the floor and is the honest reading of the floor's own
wording — "identifiable at 16px" was a statement about legibility, and this is
the one icon in the panel whose silhouette survives the loss. Every other icon is
still at or above it, and the badge added in §4 is floored at 16 for exactly this
reason.

### 3. The two view chips touch

The design spaces the pair 16 into a 64px chip, which the D18 addendum ported as
8px between two 32px chips. The gap is now 0. The pair is one 64px control, the
pressed fill is the only thing marking the active view, and that is the trade: the
state is still carried (the fill and the accent glyph), but the two chips no
longer read as two things.

The chip's 32px, its 8-of-64 radius, the 19px icon slot and the 16.0px glyph all
survive untouched. The gap is the single ratio given up, and it is asserted as 0
with the reason attached, because a later edit restoring 8px would look like a
repair rather than a regression.

### 4. The insert badge is the accent, at a share of the thumbnail

The `+` on a result thumbnail was a 12px `+` glyph: `color: #fff`, a 1.5px white
border, on `rgba(235, 81, 23, 0.9)`. It is now the circle-plus path at
`fill="currentColor"` with `.plus { color: var(--accent) }` — the same
currentColor-plus-token pattern every other inline icon in this panel uses.

Two properties, both of which the old one lacked:

- **One owner for the accent.** A literal `#EB5017` on the path is right on the
  dark theme and wrong on the light one, where `--accent` is `#c23c0c`.
  `AGENTS.md` §8 prohibits a constant that has to stay in sync without a pin; the
  token is the pin, and it already existed.
- **The size follows the card.** The thumbnail is not one size: it is the grid
  cell's width, which moves with the dock, and a fixed 72px in the list view. The
  badge is `max(16px, 18%)` of it. 18% is **not** a number off the design — see
  below — it is the share that lands on **23.8px** at a 300px dock
  (24 / 132), which is where it was sized. The floor is load-bearing: 18% of the
  list view's 72px thumb is 12.96px, under §6's 16px. `max()` is Chromium 79
  against the panel's real floor of 84.

Height is the asset's own square `viewBox` at `height: auto`, not `aspect-ratio`
(Chromium 88) and not a percentage height, which for an absolutely positioned
element resolves against the containing block's *height* and would squash the
ring into an ellipse.

**This is the one asset in the panel whose provenance is not the design.** The
size was chosen against the preview's max-width variant, not read off a Figma
node, and Figma's read endpoints were rate-limited for the whole session. It is
recorded here as an icon-set path so that no later reader assumes it was ported.
The geometry is a Material `add_circle`; if the design's own badge is ever
measured, this is the ADR to amend — and with it the 18% share, which is derived
from the 300px dock rather than from the file.

### 5. The field's and the pill's edge is a vertical ramp

`--edge` was a flat `0.28` white→surface gradient at every angle, which is a
paint the design specifies only in the vertical direction (`#FFF 0% → #171717
100%`). It is now `linear-gradient(180deg, #FFF 0.16, #171717 0.28)`: still the
design's two colours, still the design's bottom alpha, with the top lifted
lighter and the direction made explicit so the edge catches light from above the
way the field does.

The light theme's own `--edge` was already a `180deg` ramp, so this puts both
themes on the same shape. They are not the same ramp — the light one is a flat
`0.18` either side, and the dark one is 0.16 → 0.28 — and an earlier draft of this
ADR claimed the change made them match, which is not true and which `AGENTS.md` §6
and `docs/ui-review.md` now state correctly instead.

### 6. Two small changes with no reversal in them

- **The thumbnail takes `--r-md`.** `panel-ui.md` §1 has always listed `--r-md`
  as covering "cards, thumbnails, skeleton blocks" and the rule never declared
  it, so a keyframe sat square inside a rounded card. The design's 12 of 560 is
  the ratio `--r-md` is, and this closes a spec/code divergence rather than
  opening a question.
- **`#searchmeta` takes a 16px top margin and the filter 4/8 of padding.** The
  design's 76px and 48px of vertical space are 11 and 7 at frame scale, and
  neither lands on `#app`'s uniform 8px; the row now states its own. The filter's
  padding is ours — the design has no filter — and puts its 11px label on the
  optical height of the 32px chips it shares the row with.

## Consequences

- Four comment blocks in `panel.css` and two in `index.html` (copied byte-identical
  into `preview.html`) described numbers that had moved. All six now describe the
  shipped values and name the ADR that moved them.
- `test_view_toggle_is_the_design_geometry_on_the_left` loses its `gap == box / 4`
  assertion and gains `gap == 0`. Everything else it pins — placement, the
  flush-left grid alignment, the radius ratio, the icon slot, the glyph floor,
  the two stroke weights, the list icon's three rules and three bullets, the
  active chip's fill — is unchanged.
- `panel.css` goes to `v=0.9.0` and `panel.js` to `v=0.7.1`, per ADR-0012's
  convention of bumping what changed. `index.html` is the document, not a cached
  asset, so it needs none.
- `AGENTS.md` §6's icon line and §12's D20 gain the reversal; `panel-ui.md` §1's
  spacing table, height arithmetic, icon paragraph and view-pair section, and §4.2
  the badge.

## Alternatives rejected

**Keep the 21px magnifier.** The alternative to §2, and the status quo. A 21px
icon beside 11px label text is 1.9× the type it labels, which is the imbalance
this reversal removes. If the 1.08px stroke proves too faint in AE, 16px is the
next step up and it is still under the design's own export.

**Restore the 8px pair gap.** Keeps the two chips as two chips, at the cost of the
tightness the change was made for. This is the one reversal in the set that is
purely aesthetic, and it is the one most likely to be re-litigated — which is why
the test carries the reasoning rather than just the number.

**Pin the badge's size in px, sized to the 300px dock.** 24px is right at 300 and
wrong at 360 and worse in the list view. A fixed number is also the failure mode
that produced the old badge's fixed 18px, which was sized for a dock nobody ships.

**`aspect-ratio: 1` on the badge.** Chromium 88, over the panel's real floor of
84 (flexbox `gap`, `docs/agents/known-issues.md`). The SVG's own viewBox is
already the square.

**Take the badge's colour from the design's export as a literal hex.** Works on
one theme, gives one constant two owners, and §8 exists to prevent it.

## Not decided here

`777:698`'s pill radius (`--r-lg`, still 8px) is still unmeasured, for the same
reason: Figma's read endpoints were rate-limited throughout. That asymmetry
surfaced again here — the field's radius is measured, the pills' is inherited —
and it remains the one open measurement in `panel-ui.md` §1.
