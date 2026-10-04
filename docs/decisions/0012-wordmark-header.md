# ADR-0012 — The wordmark replaces the navbar text; the header keeps only what §4.4 requires

- Status: accepted
- Date: 2026-10-04
- Affects: `AGENTS.md` §4.4, §6, §12; `docs/design/panel-ui.md` §1, §2; `panel/www/*`
- Spec of record: `docs/design/panel-ui.md`
- Design source: Figma `YJntqqRI69HtwO7aw8bbwz`, `tempo_logo` (node `777:761`)

## Context

The panel's top row was a navbar: `#statusbar` carried a `Tempo` text mark, a
status dot, the words `service ok` / `service offline`, the words
`engine gpu` / `engine cpu` / `tunnel down` / `engine unknown` /
`tunnel starting` / `engine offline`, and a **Sync now** button.

Two of those are load-bearing and were not up for deletion. `AGENTS.md` §4.4:

> Engine address, token, and Brev instance are server config (never panel input).
> `/health` reports engine reachability and tunnel state; unreachable/asleep/
> tunnel-down renders as an honest status row, never a spinner.

and

> Explicit **Sync now** button as the manual fallback.

Meanwhile `docs/design/panel-ui.md` §8 listed the logo as out of scope:

> The logo. The design has a `tempo_logo` wordmark with accent strokes; it is a
> Figma asset with no export in the file, so the panel ships the `Tempo` text
> mark rather than an invented one.

That reason expired: the wordmark is now exported from the file.

The bar's own text was, separately, weak. `panel-ui.md` §2 already conceded the
row "has no home in the Figma frames" — it was ours, not the design's.

## Decision

### 1. The text mark becomes the real wordmark

`panel/www/logo.png`, exported from `777:761`, at `height: 14px`, `width: auto`.
The asset is 280×49 — the mark's own 40:7 proportion — so 14 px of height is
exactly 80 px of width, and the width follows the height without distorting. That
exactness is load-bearing rather than incidental: 12 px would have been 68.57 px,
and the `<img>` attributes have to state an integer.

`test_panel_header_is_the_wordmark_not_a_navbar` reads the PNG's own header and
asserts that arithmetic against both the CSS and the `<img>`, which is how
AGENTS.md §8 asks for a derived constant that lives in two places to be pinned.
A swapped or re-proportioned asset fails the test instead of skewing in AE.

### 2. The state labels go; the dot stays and becomes the legend

The dot already encoded the same three states as the text — `ok` = service +
reachable engine, `warn` = transitional, `bad` = offline or down. Rendering the
state twice, once as a colour and once as words, meant one of the two was always
redundant and the pair could disagree after any edit to one of them.

So the classification moved into one function, `backendState()`, returning
`[class, label]` from a single cascade, and the dot takes both from it. Keeping
the two cascades side by side and calling the change a simplification would have
contradicted this ADR's own stated reason for making it.

The labels become the dot's `title`, so nothing is lost at the pointer. They also
become its `aria-label`, and the dot loses `aria-hidden`: with the text nodes
gone it is the only carrier of §4.4's status, so hiding it from assistive tech
would have quietly withdrawn the honest reporting along with the navbar.

### 3. `#statusbar` is renamed `#topbar`

It is no longer a status bar. The id would otherwise point a reader at a bar that
does not exist.

### 4. The raster is not traced

`tempo_logo` is a raster image fill in the Figma file, not a vector — there is no
path data to port, and no `fill: currentColor` to theme it with. It ships as
exported.

It is deliberately **not** redrawn as inline SVG, even though every other graphic
in `panel/www/` is. Bold geometric letterforms traced by eye would be an invented
mark wearing the real one's proportions — the exact failure the §8 line above
exists to prevent. `panel/www/` now holds one raster, and this is why.

### 5. The light theme filters rather than duplicating

A near-white raster is invisible on `--bg: #d6d6d6`. `html.light #logo` applies
`filter: invert(1) hue-rotate(180deg)`: the letters invert to black, and the 180°
rotation carries the accents' hue back to where it was. A plain `invert` would
leave them cyan. Measured on the asset: letters `#FCFCFC` → `#000000`, accent
`#F6480A` → `#F54709`.

The mark is white plus **two** accents of that one orange — the E's middle arm
and a small wedge at the O's shoulder — so one filter covers both. This is one
CSS line against a second 11 KB binary that would need its own cache buster and
its own drift risk. If the mark ever gains a third *colour*, or a gradient, the
filter stops being reversible and the second asset wins.

## Consequences

- `#topbar` is the wordmark, the dot, and Sync now. The honest status of §4.4 is
  a hover away rather than always on screen, which is the real cost of this ADR:
  it is the one place the panel now says less at rest. The error row still
  surfaces the actual codes (`BACKEND_UNREACHABLE`, `BACKEND_ASLEEP`,
  `BACKEND_TIMEOUT`) inline, so a bad backend is never silent — only a
  transient one is quieter.
- `preview.html` cannot repoint the `src` itself, because
  `test_preview_markup_matches_panel` holds the `#app` blocks byte-identical.
  `preview-harness.js` sets `logo.src` at load instead, the same way it already
  loads the real `panel.css` and `panel.js` rather than copying either.
- The asset needs a cache buster like any other `www/` file; it is on the same
  `v=0.7.0` as the CSS and JS that changed with it. `api.js` stayed on its own
  `v=0.6.1` because it did not change.
- `docs/design/preview-harness.css` needed `background: var(--bg)` on `#app`.
  Unrelated to the wordmark: the harness's own `html, body { background: #0e0e0e }`
  loads after `panel.css` at equal specificity and won, pinning the panel body
  dark in both themes. That was already wrong, but the wordmark is the first
  element here whose correctness depends on the surface colour, so leaving it
  would have shipped a light theme nobody could review. Shipped as its own commit.

## Alternatives rejected

**Delete the row outright — logo alone, floating.** This is what "remove the
navbar" reads as taken literally, and it is the version that would have needed this
ADR to *weaken* §4.4: no honest engine status, and no manual sync fallback, on a
panel whose engine lives behind a supervised `brev port-forward` that is down
whenever the instance is stopped (K4). A dead tunnel with nothing on screen saying
so is the failure §4.4's sentence was written to prevent.

**Two logo assets, one per theme.** Exact control, and the honest answer once the
mark stops being two flat colours. Today it is white plus two accents of one
orange, and the filter reproduces all three. Cost of the duplication: a second
binary in git, two cache busters, and a reviewer has to diff them by eye.

**Trace the wordmark to SVG paths for themeability and crispness.** Rejected on
§8, above: the result would not be their logo.

**Keep the state labels, drop only the `Tempo` text mark.** Rejected: it leaves
the navbar — the actual complaint — in place, and keeps the dot/label pair that
can disagree.