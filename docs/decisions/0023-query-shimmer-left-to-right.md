# ADR-0023 - The query shimmer runs left to right

- Status: accepted
- Date: 2026-10-06
- Amends: `0017-query-shimmer-one-layer.md` (its §2 direction line)
- Affects: `AGENTS.md` §6, §12; `docs/design/panel-ui.md` §4.1; `panel/www/panel.css`
- Spec of record: `docs/design/panel-ui.md` §4.1

## Context

ADR-0017 shipped the query shimmer running **right to left**, chosen so it would agree
with the skeleton sweep on the same frame. That agreement was an aesthetic argument,
not a constraint: the two surfaces were never meant to read as one animation — ADR-0017
itself records that their speeds differ (~150–320 px/s for the band against the
skeletons' fixed ~220 px/s) precisely so they do not.

The product owner reversed the direction: the band should run left to right.

Nothing about the geometry changes. The `110deg` tilt, the `calc(3ch + 40px)` spread
and the `calc(200% + spread × 2)` sizing are all untouched, and the two keyframe
extremes are the same two positions as before — only the order they are visited in.

## Decision

The endpoints are swapped:

```css
@keyframes qsweep { from { background-position: 100% 0; } to { background-position: 0 0; } }
```

### The direction reads backwards

A positive `background-position` percentage slides a background image **leftwards**
when the image is larger than its container, and this one is: the field's gradient is
`200% + 2 × spread` wide against a shrink-to-fit text box. So `100%` is the band
sitting off the **left** edge and `0` is the band sitting off the **right** edge, and
running `100% → 0` moves the band **left to right**.

The arithmetic and the intuition disagree here, which is why the reversal was verified
against a headless Chrome render of the real rules at both positions rather than
reasoned about: the same arithmetic read backwards says the shipped version already ran
left to right, which the render contradicted. The skeleton's `150% → -50%` was checked
the same way, and does run right to left as ADR-0017 claimed.

### The loop is unchanged

The sizing comment's guarantee is symmetric and so still holds: at each extreme the
band's near edge sits a fraction past the opposite edge of the field (the tilt accounts
for the fraction), so nothing wraps and the base stop covers the whole string in
between. Reversing the order cannot break a loop whose two ends are the same two ends.

### The resting position is now the end state

`#q-sweep` declares no `background-position`, so it defaults to `0 0` — which was the
`from` state and is now the `to` state. That is the same relationship ADR-0016 gave the
skeleton blocks ("the resting position is the keyframe's end state"), arrived at rather
than designed. At that position the band is clear of the query, so the first painted
frame shows the resting colour, and reduced motion drops the gradient entirely anyway.

## Consequences

- The band crosses the query from the left edge to the right edge at 1 s.
- **The two shimmer surfaces on the searching frame now travel opposite ways.** The
  skeleton sweep still runs right to left. That is recorded here and in §4.1 rather than
  reconciled, because the agreement ADR-0017 argued for was never load-bearing and its
  own ADR concedes the two already read as separate animations. A later reader who sees
  the mismatch should read this line, not "fix" it. The skeleton's keyframes
  (`--sweep`, `sweep`) are deliberately not part of this change.
- ADR-0017's direction line is annotated, not rewritten, so the original reasoning and
  the reversal stay readable side by side.
- Nothing else moved: the band is still greyscale (ADR-0011's `--accent` stays fenced
  off), still one layer with no second copy of the query beneath it, still 1 s, and the
  searching frame still spends its three animated surfaces under §6's recorded
  deviation.

## Alternatives rejected

- **Reverse both sweeps.** The skeleton's blocks are at the design's own 8% fill — a
  barely-there shape, not a band travelling over text — and they are the loading state
  for the results grid, a different surface with a different job. Only one shimmer was
  asked about.
- **Keep the direction and change the geometry** (a wider spread, a slower cycle, a
  different tilt) to make the right-to-left travel read better. A direction the editor
  reads wrong is fixed by direction.
- **Flip the gradient instead of the keyframes** (`270deg` instead of `110deg`). It
  mirrors the band's shading as well as its travel, which is not the same thing: the
  tilt exists so the band's near edge lands outside the field at both extremes, and
  mirroring the angle breaks that.

## Not decided here

- Whether the skeleton sweep should follow. If it ever does, ADR-0016's resting-position
  and reduced-motion rules are unaffected (they are direction-agnostic) but its
  keyframe endpoints and the `docs/design/panel-ui.md` §4.1 paragraph move with it.