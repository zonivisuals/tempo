# ADR-0017 - The query value shimmers as one text layer

- Status: accepted
- Date: 2026-10-05
- Affects: `AGENTS.md` §5 F3, §6, §12; `docs/design/panel-ui.md` §3.4, §4.1; `panel/www/panel.css`, `panel/www/index.html`, `panel/www/panel.js`
- Spec of record: `docs/design/panel-ui.md`
- Design source: shadcn/ui's `shimmer` utility (`shadcn/tailwind.css`, `apps/v4/examples/aria/shimmer-demo.tsx`); the panel's own text tokens, `777:294`'s field

## Context

The searching state painted the query **twice**. `#q-base` sat under `#q-sweep` in
the search field's value row: a legible copy in `--text`, with a band drawn over the
top of it. So what the editor saw was a full-strength query with a second edge
crossing it — the "noisy" shimmer this ADR removes.

Two things compounded it, and neither was the gradient's shape:

- The band gradient had **no `background-repeat: no-repeat`**, on a `background-size`
  of 240%. A gradient that repeats along the text gives the band a second edge, and
  the ends of the string were where it showed.
- The band was **`--accent`**. AGENTS.md §6 allows one accent, "used only for
  selection/active states". A search in flight is neither. ADR-0011 listed the accent
  sweep here without ever noticing that it was borrowing a token §6 had fenced off.

And under `prefers-reduced-motion: reduce` the query **disappeared**. `#q-sweep`
paints its text with a gradient clipped to the glyphs and `color: transparent`, and
the reduced-motion rule set `animation: none` while leaving the gradient in place.
The band's resting position was `150%`, which parks it clear of the text, so nothing
was painted: a blank field mid-search, for exactly the users least able to read the
spinner next to it.

The reference is shadcn/ui's `shimmer` utility, the shimmer behind the generating
text in most assistant UIs. Its shape is right for this panel and its colour
arithmetic is not reachable from one.

## Decision

### 1. One text layer, and the gradient's own outer stops are the resting colour

`#q-base` is deleted — from the markup, from `syncQueryMirror`, and from the CSS.
Nothing sits under the band.

This is the reference's central move and it is what makes the shimmer clean. In
`shimmer` the text's resting colour is the gradient's outer stop, the highlight is a
band in the middle of it, and the whole thing is one painted layer. A separate legible
copy underneath is not a fallback for that layer, it is a second edge on top of it.

The skeleton blocks already do the same thing for the opposite reason — a
`--surface-2` base under the ramp, because a block with no base has no resting shape
(ADR-0016 §6). The query needed no base at all, because its ramp's own ends are one.

### 2. The stop geometry is the utility's, ported

```css
--qsweep-spread: calc(3ch + 40px);
--qsweep-spread: calc(3ch + 40px);
--qsweep-mid: rgba(255, 255, 255, 0.6);
--qsweep: linear-gradient(110deg,
    var(--text-dim) calc(50% - var(--qsweep-spread)),
    var(--qsweep-mid) calc(50% - var(--qsweep-spread) * 0.5),
    var(--text) 50%,
    var(--qsweep-mid) calc(50% + var(--qsweep-spread) * 0.5),
    var(--text-dim) calc(50% + var(--qsweep-spread)));
```

- **The tilt** is the utility's default `--shimmer-angle: 20deg`, which it adds to
  90deg: `110deg`. A hard vertical band edge reads as a wipe; 20° off reads as light
  travelling over a surface.
- **The spread** is the utility's default, `calc(3ch + 40px)` — a fixed 40px plus a
  `3ch` term, so the band scales with the query's own type rather than with the
  field's width. One owner: `--qsweep-spread`, declared once.
- **The sizing** is `calc(200% + var(--qsweep-spread) * 2)`, also the utility's. It
  is what makes the loop seamless: the image is twice the text's width *plus the band
  on either side*, so at `background-position: 0 0` the band's near edge sits just
  past the field's right edge and at `100% 0` its far edge just past the left one —
  "just", because the tilt projects the spread by sin 110° ≈ 0.94, which is the 6 %
  that puts it outside rather than on the boundary, and outside is the side that
  errs safe. It is also what keeps the base stop covering the whole string at every
  position between the two, so the query never blanks mid-sweep. Nothing wraps and
  nothing blinks. The `2 *` is not slack: remove it and the far extreme leaves the
  tail of a long query outside the image.
- **`no-repeat`** is explicit, because the panel had inferred it and had it wrong.
- **The direction** is right to left, which is what the skeleton sweep already runs
  (`sweep` goes `150%` → `-50%`, both leftward), so the two shimmer surfaces agree.

### 3. The colours are the utility's formula, run over this panel's tokens

`shimmer` derives its highlight from `currentColor` rather than naming a colour, and
its dark variant is `max(0.8, l + 0.4)` lightness at `alpha + 0.4`. Run that over this
panel's own dim level it lands exactly on the field's value level:

| | panel token | alpha | → utility's formula | lands on |
|---|---|---|---|---|
| resting | `--text-dim` | 0.40 | — | `--text-dim` (0.40) |
| mid | `--qsweep-mid` | 0.60 | the 50 % mix of the two ends | — |
| peak | `--text` | 0.80 | `0.4 + 0.4` | `--text` (0.80) |

So the three levels are the field's own: the query rests at the level of the
`Search for anything` label above it and peaks at the level a value normally reads
at. Nothing is invented, which is the point — the numbers are a derivation, not a
taste call. The light theme is the same shape with `--text-dim`/`--text`'s own
flipped values, and only the mid stop is ours there: (0.45 + 0.88) / 2 = 0.665, held to
the two decimals the text tokens themselves carry.

**The base and the peak are therefore written as the tokens themselves, not as
literals of their values.** That is partly why: §7.3's "if a literal appears twice,
it's a constant" and the two themes would otherwise each carry their own copy of the
field's own text levels. The utility cannot do this — it needs `currentColor`,
`oklch(from currentColor l c h / …)` and `color-mix()`, and relative colour syntax
is far above the Chromium 84 floor ADR-0014 established — but the panel has the
tokens the formula was pointing at, so the substitution is available here and the
reachability argument does not apply to it.

Only `--qsweep-mid` stays a literal, because nothing derives it: it is the mean of two
alphas, held to the precision they are written at. One shape, declared once in the
dark block, and the light theme overrides that one token and nothing else — the
`--sweep` precedent, one token per theme for the part that differs.

### 4. Reduced motion renders the query plainly

`#q-sweep` gets its own rule in the existing `prefers-reduced-motion` block —
`animation: none; background-image: none; color: var(--text)` — instead of joining the
animation-only list. This is the utility's own answer to the same question, and it is
the only one that leaves the query readable: the layer is transparent by construction,
so dropping the gradient has to put the colour back.

The skeletons keep ADR-0016's resting-position answer, because their resting state is
a *shape* (a block with no base reads as background) rather than *text*. Two rules for
one media query is not two owners of anything.

## Consequences

- **The query is legible in every state it can be in.** At rest under reduced motion
  it reads at `--text`; animating it never drops below `--text-dim`, because the
  gradient's outer stops are painted across the whole box at every position.
- **The accent is out of the searching state**, which leaves §6's one accent for
  selection and active states and nothing else. `panel.css` no longer contains the
  dark accent literal except on `#submit:hover`.
- **The light theme's `#q-sweep` override is gone**: it existed only to restate the
  accent in the other direction, and `--text-dim`/`--text` already flip. This is the
  `--sweep` precedent — one token per theme, no per-theme rule at the element.
- **The test pins the mechanism, not the look**: the second copy absent from markup,
  script and stylesheet; both themes' three levels; no accent literal inside either
  gradient; `no-repeat` and the `200% + 2 × spread` sizing present; one owner for the
  gradient; and the reduced-motion rule restoring the text colour. A band that starts
  repeating fails on `no-repeat`, and a level that drifts fails on the alphas.
- **The 1 s cycle is not reconciled with the skeleton sweep.** The band travels
  `W + 2 × spread` per cycle, not the image's own `2W + 2 × spread`: a positive
  `background-position` percentage moves the image by `p · (−W − 2S)` and the band
  sits at its centre, so it runs from `W + S` to `−S`. Because `W` is the mirror's
  shrink-to-fit **text** width, the speed depends on how long the query is — roughly
  150 px/s on a three-character query and 320 px/s at a full 200 px field, against
  the skeleton sweep's fixed ~220 px/s at 1.2 s. So 1 s is between a third and half
  again as fast as the skeletons rather than "twice", and the ratio moves with what
  was typed. 1 s was chosen on the product owner's call, for the query — which is the
  thing being watched while they wait — and the two surfaces are not meant to read as
  one animation. Recorded here so a later reader does not "fix" it as an
  inconsistency, and so nobody quotes the travel figure as a constant.
- ADR-0011's "an accent sweep on the query text while searching" is superseded by
  this ADR. ADR-0011's motion budget is otherwise untouched, and the searching frame
  is worth counting against §6's two-surface ceiling honestly: it animates **three**
  things — the submit button's arc, the query shimmer and the skeleton sweep. It
  animated all three before this change too, so nothing here pushed it across a line
  it was not already over; §6 now names the frame rather than leaving a reviewer to
  find it. The argument that three is acceptable there is that all three answer the
  same question, "what state is this?", with the same answer, and none of them is the
  kind of surface the rule targets (a glow, a decoration, a second unrelated
  spinner). It is a recorded deviation rather than a cleared one: if the budget ever
  binds, the query shimmer is the one to go, because the skeletons and the arc are the
  design's.
- Cache busters move (`panel.css` 0.9.0 → 0.9.1, `panel.js` 0.7.1 → 0.7.2), because
  CEF holds panel assets across AE restarts and neither file would otherwise reload.

## Alternatives rejected

**Keep the base copy and fix the gradient.** The smaller diff, and it treats the
symptom. The double layer is the noise; a cleaner band drawn over a second copy of
the text is still a band over a second copy of the text. The reference solves it by
deleting the layer, and the layer only existed because the ramp had transparent ends.

**Highlight in `--surface`.** It was tried first, on the reasoning that a surface
token is the quiet choice. `--surface` **is** the search field's fill — `.edge` paints
the field with it — so a band in `--surface` paints the glyphs in the background
colour and the shimmer disappears. A surface is a good thing to put a highlight
*behind*; it is not a colour a highlight can be.

**`--surface-2` as the peak.** A surface token, and only 8 of lightness above the
fill. On text it would be a band nobody sees.

**2 s, matching the skeleton sweep.** Would make the two shimmer surfaces one speed.
Rejected on the product owner's call: the query is what the editor is watching while
they wait, and 1 s reads as responsive rather than as a loop. The cost is named
above rather than absorbed.

**Animate `--sweep` and reuse it for the text.** One token for both shimmer surfaces,
which is appealing. `--sweep` is white at 0.08 with transparent ends — it is the
design's block fill (ADR-0016 §5), and as a text ramp it would leave the query's
resting state at 8% white on a 17% surface, i.e. nearly invisible, for the whole
second between passes.

**Sweep across the field rather than across the text.** Wider band, and it would
cross the label, the submit button and the field's own edge — three more moving
things, on the surface §6's motion budget is already counting.

## Not decided here

The skeleton blocks' own sweep keeps `--sweep`, its 0.08 level and its 1.2 s cycle.
The two now differ in speed and in geometry (the blocks ramp transparent → 0.08,
the query ramps 0.4 → 0.8), which is a deliberate difference rather than an
oversight: the blocks are a resting shape with a lift over it, and the query is text
that has to stay readable between passes. Unifying them into one shimmer treatment
would be a separate piece of work, and it would have to answer both questions at
once.