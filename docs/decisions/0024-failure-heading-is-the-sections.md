# D31 - The failure heading is the section's

**Date:** 2026-10-05
**Touches:** `panel/www/index.html`, `panel/www/panel.js`, `panel/www/panel.css`,
`docs/design/panel-ui.md` §3.2

## What

On the indexing-failure screen (02d), the status pill moves from the failure block to
the top of the section, and the Retry step button gains a rotate-ccw icon and 8/16
padding.

Before:

```
[Indexing Failed]        <- the block's own first line, under the steps
```

After:

```
[Indexing Failed]        <- #index-fail-pill, the slot the live pill occupies
  the step list
  the sentence
  [icon] Retry step
```

## Why the heading moves

ADR-0020 put one sentence and one button under the step list, and ADR-0022 removed the
duplicate report from `#results`. Both left the heading where it was: at the top of the
block, which is below the list it introduces. That is the same misplacement ADR-0022
identified in `#results`, where a failure block sat below the detail it pointed at, and
it is the one the two ADRs did not fix.

The pill is a heading, and the section already has a slot for one. The live pill fills
it while a job runs; the failure pill fills it once indexing has stopped. Reading order
becomes what happened, then the steps that say where, then what to do.

`stateBlock()` gained an empty-pill case so the block can hand its heading up rather
than draw one itself. Without it the two elements would each render a pill and the
screen would carry the heading twice.

## Why the button changed

An icon that names the action beats the word alone, and the padding is what gives a
16px glyph room. 3/10 left the label crowded against it.

The icon is the product owner's SVG, a 24-unit rotate-ccw, drawn into a 16px slot so
its stroke-width 2 lands on 1.33px. That is the slot the other icons occupy, and it
clears §6's 16px floor without needing the exemption the search magnifier takes. The
markup carries no `xmlns`: the one supplied was malformed (`http://w3.org`, not
`http://www.w3.org/2000/svg`), inline SVG in HTML does not want one, and no other icon
in the panel carries it. `stroke: currentColor` follows `--text` onto the light theme,
which is what every other icon in the panel does.

## What it does not change

Nothing engine-internal is still rendered, the failure is still reported once (ADR-0022
holds), the button still addresses the same job or footage key, and the live pill still
drives `.live` on the section so rows arrive underneath it rather than pushing it down.