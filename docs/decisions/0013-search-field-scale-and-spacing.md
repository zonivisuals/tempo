# ADR-0013 - The search field is scaled by type, not by frame geometry

- Status: accepted
- Date: 2026-10-04
- Affects: `AGENTS.md` §6, §12; `docs/design/panel-ui.md` §1, §3.1, §4; `panel/www/*`
- Spec of record: `docs/design/panel-ui.md`
- Design source: Figma `YJntqqRI69HtwO7aw8bbwz`, `search_input` (node `815:294`, inside `04_search_results_frame`)

## Context

The search field read as cramped: a 2px seam between the label and the query,
57px tall, in a panel where it is the primary control. The obvious response -
scale the design's field down to panel width - is the wrong instrument, and
following it is how the field got small in the first place.

`panel-ui.md` §1 recorded the field's radius as 32px on a 196px frame, "0.163 of
the height; 0.163 of a 48 px panel field is 8 px". Both halves of that sentence
were wrong. The 32 was superseded in the design (`815:294` measures 25), and the
48px panel field was an assumption: the shipped field was 57px, so the radius had
been derived against a height that never existed.

Worse, the frame-relative method cannot work in either direction. The design's
field is 196px of a 2004px frame - 10.7% of the content width. The panel's is 18%.
Every ratio taken against the frame says the panel's field is already too tall,
which is the reading that produced the 2px gap.

Meanwhile the port had been quietly using a *different* basis all along, and
getting it right: the submit button is 60px in the design and 24px in the panel, a
ratio of 0.4. The panel's search value is 13px against the design's 32px - 0.406.
The button's radius agrees (10.67 → 4px, 0.375). So the port scales **by type**,
and had only ever claimed otherwise in prose.

## Decision

### 1. The scale basis is the type ratio, 0.406

Recorded as the section's premise, with the frame-relative method named as the
wrong one and the reason it fails. The submit button is promoted from a
coincidence to the evidence for the rule.

### 2. The field's spacing is re-derived on the 4px rhythm

Measured off a 1× render of `815:294` - a 1836×196 field whose top padding,
ink-to-ink label-to-value gap and bottom padding are 47 / 46 / 53, with 42 / 40
of side padding and 15 before the label. Scaled by 0.406: 19.1 / 18.7 / 21.5,
17 / 16, 6.1. Landed on **20 / 20 / 20**, **16**, **6**.

Height is a consequence, not a target:

```
2 border + 20 padding + 21 label row + 20 gap + 24 value row + 20 padding = 107px
```

The two rows are set by the wrong elements on purpose and the arithmetic depends
on it: the **icon** sets the label row at 21px, not the 11px text, and the
**submit button** sets the value row at 24px, not the 20px input box. Both were
previously miscounted at 16 and 20.

The gap is the substance. At 2px the label and the query read as one sentence in
a box; the design separates them by nearly a quarter of the field's height.

Nothing else moved. The submit button was already 24px, already `--r-sm`, and
already placed correctly - the design's button centre is 28px *below* the field's
own centre, sitting on the value row, which is what `.sb-row` already did.

### 3. `--r-field` splits from `--r-lg`

The corrected 25/196 × 0.406 is 10.2px, so the field wants 10. But `--r-lg` also
carries the indexing and empty-state pills, which come from a different node
(`777:698`) whose radius was **not** re-measured - Figma's read endpoints were
rate-limited throughout the session that produced this change. Giving the field
its own token is what stops one measurement from silently moving two surfaces
whose own numbers nobody has checked.

`--r-lg` stays 8px for the pills until someone measures `777:698`.

### 4. The icon is the design's path, themed and not restated

The exported 21×21 path, at its exported size. Two of its properties are
load-bearing:

- `stroke` is `currentColor`, not the asset's literal `stroke="white"`. White is
  invisible on `--bg: #d6d6d6`, and the panel ships a light theme. This is the
  same substitution `panel.js` already documents for the step icons.
- `stroke-opacity` is **absent**, so `.sb-head`'s `color: var(--text-dim)` is the
  only source of the alpha. Carried as well, it compounds on top of a colour that
  is already translucent: 0.4 over 0.4 lands the icon at 0.16 in the dark theme
  and 0.45 over 0.45 at 0.20 in the light one.
- `stroke-width` stays on the path and `.sb-head svg` no longer declares one.
  The rule previously hardcoded `2.3` against the design's `2.2751`. This is the
  one that mattered: CSS would have **overridden** the asset silently, so two
  owners were not merely redundant but in conflict. The other paint properties
  the rule and the markup share (`fill`, `stroke-linecap`, `stroke-linejoin`) are
  restatements of the same value, which is the pattern the step icons already
  use. §8 wants one owner per constant; the stroke-width was the breach.

`panel-ui.md` §1's flat "**Icons**: 16px" becomes a floor rather than a size, so
the 21px field icon has somewhere to stand. §6's "identifiable at 16px" was never
a ceiling.

### 5. `Search for anything` is kept

Reverses `panel-ui.md` §3.1, which dropped the design's label because §6 bans
placeholder copy "of that species".

The original reading conflated two different things. §6 bans *placeholder copy* -
`placeholder="Ask anything…"`, the text that vanishes when you type. The design
draws `Search for anything` as a permanent label line above the value, which is a
field label, and §6 does not name field labels. This was the product owner's call
and it is recorded as a reversal rather than smuggled in.

The label is still not the input's accessible name. The input has no `aria-label`
today and that gap is unchanged; the label is not associated with it, which is a
real (small) accessibility gap and a separate ticket.

### 6. The header hairline goes

`#topbar` drew a `border-bottom` the design has never had. It was part of the same
invention as the bar it replaced. The space below the wordmark is unchanged, and
both §4.4 controls stay: the status dot and the Sync now fallback.

## Consequences

- The field is 107px tall, against 57px. In a 300px dock that is over a third of
  the viewport before any results, which is the honest cost of being faithful to
  the basis. If it proves too tall in AE it is two values (`padding` and `gap` in
  `#searchbox`) and the derivation in §1 stands either way.
- `--r-field` has exactly one consumer. That is the point: it is a placeholder
  waiting for `777:698` to be measured, at which point the two tokens either
  converge or the split earns its keep.
- `test_search_field_carries_the_designs_spacing` and
  `test_header_draws_no_hairline_under_the_wordmark` pin the numbers, with the
  measurements in their docstrings so they can be re-derived rather than trusted.
- Only `panel.css` gets a cache buster (`v=0.8.0`), per ADR-0012's convention of
  bumping what changed. The markup edit needs none: `index.html` is the document,
  not a cached asset.
- The pill's radius is now the one unverified surface in §1. It was before too -
  it was inherited, not measured - but the field's correction makes the asymmetry
  visible.

## Alternatives rejected

**Scale the field by frame width** (196 × 314/1828 ≈ 34px). This is what the old
prose prescribed, and it shrinks the control the ticket was about. It would also
drag the label to ~4px, which is why type has never scaled with geometry in this
port.

**Hold the height at 57px and redistribute.** Keeps the panel compact, but the
redistribution has to come out of the 40px the two rows already occupy, and the
gap is the one thing that was wrong. It would land near 8/4/8 - a taller field by
6px, which is not a visible change at all.

**Reuse `--r-lg` at 10px.** One token instead of two. It moves two surfaces whose
own measurement nobody has taken, to save a declaration. That is the trade §8's
"if a literal appears twice, it's a constant" is meant to prevent, in reverse.

**Trace the 21px icon down to the 4px rhythm.** The design exports a 21×21 box,
and 0.406 makes that 8.5px — below §6's 16px floor and, at the magnifier's 2.2751
stroke, a grey dot. The icon is the one thing here that has to be exempt from the
scale, and 21px is what the export says.

## Not decided here

The submit button's own dimensions were re-measured off the same render (it reads
60 × 58 rather than 60 square, with a ~10px radius and a 27px glyph) and are
**deliberately not** folded in. The control is unchanged by this ADR — it was
already 24px with `--r-sm`, which is what any reading of the design's 60px gives
at this scale — and a 27px glyph read off a 1× raster with a hard brightness
threshold is not a measurement worth restating in the spec of record. Whoever
re-reads `777:314` properly should settle it; `panel-ui.md` §1 keeps the older
figures until then.
