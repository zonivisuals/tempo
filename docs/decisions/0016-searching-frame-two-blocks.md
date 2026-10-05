# ADR-0016 - The searching frame is the design's two blocks and nothing else

- Status: accepted
- Date: 2026-10-05
- Affects: `AGENTS.md` §5 F3, §6, §12; `docs/design/panel-ui.md` §1, §4.1; `panel/www/panel.css`
- Spec of record: `docs/design/panel-ui.md`
- Design source: Figma `YJntqqRI69HtwO7aw8bbwz`, `loading_result` (node `777:532`)

## Context

The searching state rendered a card: `.card.skel` inherited `.card`'s 3px
same-colour stroke and its `--surface` fill, and the two gradient blocks sat inside
that chrome. The design has no such chrome. `loading_result` is a transparent
560 × 399 frame with two blocks and no fill or stroke of its own.

The two blocks were also wrong in three ways that a review would not catch,
because a skeleton that renders is a skeleton that renders. The peaks were
invented rather than measured — 0.56 on the thumb and **1.0** on the caption,
which is pure white and therefore the brightest pixel on a dark card. The blocks
had no radius, though the design gives them the same 12 the card has. And the cap
was 26px, which is neither the design's number nor the body it stands in for.

Everything below is measured off `777:532`'s own fills, which were read out of the
design and pasted in rather than re-derived from a render.

## Decision

### 1. The frame carries no stroke and no fill

`.card.skel` drops both. The card's 3px stroke existed to make a same-colour
border invisible on the result card; the skeleton has no reason to reserve 6px of
a cell it is only standing in for.

This makes the blocks' geometry do the work the stroke was doing — see §3.

### 2. Both blocks take `--r-md`, and so does the real thumbnail

The design gives `thumb-sk`, `cap-sk` and `Rectangle 5420` the same radius: 12 of
560, which is what `--r-md` already is. ADR-0015 put the real thumbnail on that
token; this puts the two blocks on it too, so the skeleton's silhouette is the
result card's silhouette.

### 3. The blocks are inset 3px, which is the card's own stroke width

`thumb-sk` is 554 wide at `left: 3` of a 560 frame — inside the card's 3px
stroke. So the skeleton's inset is not a design number that could have been
anything: it is the stroke it no longer draws, and the cap takes `.body`'s own
horizontal padding for the same reason. Both blocks therefore land exactly where
the real thumbnail and the real caption land, which is the whole point of
scaffolding a card: nothing moves when the real thing arrives.

The test asserts the inset against the card's `border` rather than restating 3, so
a change to the stroke moves both or fails.

### 4. The gap is 18/560 on the 4px rhythm, and the cap is the body

The design's `cap-sk` starts 18px below the thumb, on a 560 frame. That is 4.2px
on the panel's 132px thumbnail, so `margin-top: 4px`.

The cap's **height** is the re-derivation, and it is the one number in this ADR
that could not be copied. The design's 69 is its body box: two lines of 20px
caption type plus padding. The panel's caption is 11px — type is re-derived, not
scaled, and that is the port's own rule — so the same box is two lines at the
inherited 1.45 plus `.body`'s 6px above and below:

```
2 x 11 x 1.45 + 2 x 6 = 43.9  ->  44px
```

Taken literally, 69 of 560 would be **17px** here, and a row would grow from
122px to 94px the moment results landed — a **~30px jump**, per row, for nine
rows. `panel-ui.md` §4.1's "count matches the previous result count so the list
does not reflow on submit" exists to prevent exactly that, and a literal copy of a
type-driven measurement would have caused it.

With 44 the skeleton is 122.2px against a real card's 124.2 — 2px, and the design
has the same slack: `loading_result` fills all 399 of its frame while
`Rectangle 5420` insets 3px inside the same 399.

The test asserts the height as `2 x cap_font_size x line_height + 2 x body_padding`
with a 1px tolerance, reading each term out of the shipped CSS. It cannot pass by
construction: change `.cap`'s font size and it moves.

### 5. One sweep token at the design's level

`thumb-sk` and `cap-sk` carry the **same** fill — white 0 → 0.08 — differing only
in where the ramp stops (`3.25%`/`61.64%` and `0%`/`55.77%`). Those stop positions
describe a static gradient, and the panel's block is a moving highlight, so the
shape stays the panel's symmetric three-stop ramp and only the **level** carries
over: 0.08, for both blocks.

That collapses `--sweep-thumb` and `--sweep-cap` into `--sweep`. The design saying
the two are equal is what makes this one token rather than two — the same reason
`--spin-track` is a token in both themes.

The light theme is the same 8% lift in the other direction (black at 0.08). White
at 0.08 on `#f2f2f2` is invisible, which is the same reason `--spin-track` is a
visible gray rather than white there.

### 6. A hover guard, and a resting position

Two small things that only exist because of the two above.

`.card:hover` paints `--accent`, and `.card.skel` is a `div` — which still matches
`:hover`. Removing the stroke and fill would otherwise have handed the skeleton an
orange background under the cursor, so `.card.skel:hover` restores `background:
none`.

The blocks' resting `background-position` is `-50% 0`, which is the keyframe's
*end* state. `prefers-reduced-motion` sets `animation: none` and leaves the rest of
the declaration standing, so without this the reduced-motion skeleton would show a
ramp pinned to its left edge rather than a centred peak. One line, and the
no-motion case stops being the worst-looking one.

## Consequences

- `--sweep-thumb` and `--sweep-cap` are gone. They had two invented peaks and were
  the only pair of tokens in the file that existed to disagree.
- The list view shares the two block rules and undoes the grid-shaped parts of
  them: its row has its own 8px gap and its thumb is a fixed 72px, so
  `#results.list .card.skel .sk-thumb` resets `margin: 0` (the shared 3px inset
  would have made it 78px) and `.sk-cap` resets `margin: 0`. Both are asserted.
- `panel.css`'s top-of-file token comment and `panel-ui.md` §1's "skeleton fills"
  row now say 0.08 and one token. §4.1's stale "radius 2px" is corrected to
  `--r-md`.
- ADR-0011's motion budget is untouched: this is still the one animated surface
  while searching, and it still answers "what state is this?".

## Alternatives rejected

**Port `cap-sk`'s 69 literally (17px).** The literal reading, and the reason §4
exists. It costs ~30px of reflow per row on arrival, against a spec line whose
whole purpose is that the list does not reflow. The cost is named here because it
is the kind of thing that looks like fidelity.

**Keep two sweep tokens.** Preserves the ability to differentiate the blocks, and
the panel had used it to make the caption a full white. The design does not
differentiate them, and a token that exists to disagree with its twin is not a
token.

**Keep the card's 3px stroke on the skeleton, coloured `--surface`.** It is
invisible, so nothing is lost visually — which is why it survived this long. It
costs 6px of a 138px cell twice over: once as the stroke, and again as the inset
the blocks now take, so the skeleton would have sat inside a frame the result card
does not have either.

**Keep `--surface-2` off the blocks and let the 8% ramp sit on `--bg`.** The design
draws no base colour on either block, so this is closer to the file. `--surface-2`
is kept because a block with no base has no resting shape: under reduced motion,
or on the one frame the sweep is at its faintest, the skeleton would read as
background rather than as a placeholder.

## Not decided here

The list view's skeleton height is untouched: `11px` for its cap, which is our own
shape and not the design's — the design has no list view, so there is nothing to
port. It is a rule where the grid's is a body box, and the list row's height is
set by its fixed 41px thumbnail rather than by the cap. Re-deriving it the same way
§4 re-derives the grid's is a separate ticket, and this ADR deliberately leaves
the list skeleton's geometry alone rather than half-adopting the grid's rules.