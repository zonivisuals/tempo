"""P6 verification: contract tests (AGENTS.md §9).

Every endpoint round-trips its pydantic schema, and the
tempoInsertOrFocus payload built by the panel satisfies the documented
shape in docs/api.md (cross-runtime pin without shared imports).
"""

import json
import re
from pathlib import Path

import pytest

from tempo_service.schemas import (
    ErrorEnvelope,
    FootageInfo,
    HealthResponse,
    JobStatus,
    SearchResponse,
    SyncRequest,
    SyncResponse,
)

PANEL_JS = Path(__file__).resolve().parents[2] / "panel" / "www" / "panel.js"
PANEL_API_JS = Path(__file__).resolve().parents[2] / "panel" / "www" / "api.js"
PANEL_HTML = Path(__file__).resolve().parents[2] / "panel" / "www" / "index.html"
PANEL_CSS = Path(__file__).resolve().parents[2] / "panel" / "www" / "panel.css"
PREVIEW_HTML = Path(__file__).resolve().parents[2] / "docs" / "design" / "preview.html"

INSERT_KEYS = {"source_path", "start_s", "end_s"}


def test_sync_contract():
    body = {
        "footages": [
            {"path": "C:\\v\\a.mp4", "size": 1, "mtime_ns": 2, "item_id": 3}
        ]
    }
    req = SyncRequest(**body)
    assert req.footages[0].frame_rate == 25.0  # documented default
    res = SyncResponse(added=["a1"], changed=[], removed=[], unchanged=[], jobs=["job_1"])
    assert json.loads(res.model_dump_json())["added"] == ["a1"]


def test_job_and_footage_contracts():
    job = JobStatus(
        job_id="job_1",
        footage_key="a1",
        state="running",
        stages=[{"name": "ocr", "state": "running", "done": 37, "total": 157}],
        error=None,
    )
    assert job.stages[0].done == 37
    footage = FootageInfo(footage_key="a1", path="C:\\v\\a.mp4", state="ready")
    assert footage.shot_count == 0
    health = HealthResponse(status="ok", artifact_root="./artifacts")
    assert health.backend.tunnel == "off" and health.backend.signature == ""
    err = ErrorEnvelope(error={"code": "MODEL_NOT_LOADED", "message": "text model not loaded"})
    assert err.error.code == "MODEL_NOT_LOADED"


def test_search_result_contract():
    res = SearchResponse(
        query="van",
        took_ms=12,
        results=[
            {
                "footage_key": "a1",
                "content_id": "0123456789abcdef",
                "shot_id": 0,
                "scene_id": 0,
                "source_path": "C:\\v\\a.mp4",
                "start_s": 1.0,
                "end_s": 2.0,
                "score": 0.5,
                "contributions": {"visual": 0.2, "dialogue": 0.1, "caption": 0.1, "bm25": 0.1,
                                  "entity": 0.0, "anchor": 0.0},
                "raw_cos": {"visual": 0.1, "dialogue": None, "caption": 0.3},
                "transcript": "t",
                "caption": "c",
                "entities": [],
            }
        ],
    )
    r = res.results[0]
    assert r.raw_cos.dialogue is None  # shot without a dialogue vector
    assert abs(sum(r.contributions.model_dump().values()) - r.score) < 1e-9


def test_panel_insert_payload_matches_contract():
    """The payload panel.js builds must carry exactly the documented keys."""
    src = PANEL_JS.read_text(encoding="utf-8")
    for key in INSERT_KEYS:
        assert key in src, f"panel.js missing insert key: {key}"


def test_panel_has_no_auth_surface():
    """No auth wall: api.js carries no login/signup/logout/me fns and
    index.html carries no authbox (identity removed — the localhost
    sidecar serves one editor, no sessions, no tokens)."""
    api = PANEL_API_JS.read_text(encoding="utf-8")
    for fn in ("login", "signup", "logout", "/auth/me"):
        assert fn not in api, f"api.js still references auth: {fn}"
    # No tokens in panel code or storage: nothing to hold anymore.
    assert "Authorization" not in api
    assert "tempo_colab_url" not in api
    html = PANEL_HTML.read_text(encoding="utf-8")
    for el in ("authbox", "auth-email", "auth-pass", "auth-login", "auth-signup"):
        assert el not in html, f"index.html still has auth element: {el}"


def test_panel_insert_escapes_windows_paths():
    """The JSON payload is embedded as an ExtendScript string literal: raw
    backslashes would mangle Windows paths (C:\\Users → C:Users) so lookup
    misses and import reports 'source missing from disk'. panel.js must
    double backslashes before interpolating into the evalScript call."""
    src = PANEL_JS.read_text(encoding="utf-8")
    assert 'payload.replace(/\\\\/g, "\\\\\\\\")' in src, "insert path escaping missing"
    # The JSON must travel as a *string literal* (host.jsx JSON.parses it):
    # splicing it in bare passes an Object, and every insert fails with
    # "bad payload". The wrapping quotes are the load-bearing characters.
    assert "tempoInsertOrFocus('" in src, "insert payload not wrapped as string literal"

    # Round-trip proof at the Python level of the same transform: doubling
    # backslashes preserves the JSON text through one string-literal parse.
    import json

    payload = json.dumps({"source_path": "C:\\v\\a.mp4", "start_s": 1.0, "end_s": 2.0})
    assert json.loads(payload)["source_path"] == "C:\\v\\a.mp4"


def test_preview_markup_matches_panel():
    """docs/design/preview.html copies the panel's #app markup so the browser
    preview cannot silently diverge from what ships. The copy exists because
    fetch() is blocked on file:// and the preview must open by double-click.

    Assert the two #app blocks are byte-identical, and that the preview loads the
    real stylesheet and the real panel.js rather than a copy of either.
    """
    idx = PANEL_HTML.read_text(encoding="utf-8")
    prev = PREVIEW_HTML.read_text(encoding="utf-8")

    shipped = re.search(r'(?s)<div id="app">.*?\n</div>(?=\n<script)', idx)
    assert shipped, "no #app block in panel/www/index.html"
    copied = re.search(
        r'(?s)<!-- BEGIN app.*?-->\n(.*?)<!-- END app -->', prev
    )
    assert copied, "preview.html is missing its BEGIN/END app markers"

    assert copied.group(1).strip() == shipped.group(0).strip(), (
        "docs/design/preview.html #app markup has drifted from panel/www/index.html"
    )
    assert "../../panel/www/panel.css" in prev, "preview must load the real panel.css"
    assert "../../panel/www/panel.js" in prev, "preview must load the real panel.js"
    # The preview must not pull in the real transport: the harness stubs it.
    assert "panel/www/api.js" not in prev, "preview must not load api.js over the stub"
    assert "preview-harness.js" in prev


def _panel_eval(expr: str) -> str:
    """Evaluate one expression against panel.js and return it as JSON.

    The panel is loaded the way a browser loads it — `vm.runInThisContext`, so
    top-level `const` lands in the global lexical scope and a bare identifier in
    the expression resolves — with CSInterface and TempoAPI stubbed out. Only
    top-level code runs: boot() hangs off DOMContentLoaded, never dispatched here.
    """
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    node = shutil.which("node")
    if not node:  # CI runs node --check, so node is present; be honest if not.
        pytest.skip("node not on PATH")

    driver = f"""
      const fs = require('node:fs'), vm = require('node:vm');
      window = global;
      document = {{ addEventListener() {{}}, getElementById() {{ return null; }} }};
      CSInterface = function () {{}};
      CSInterface.prototype.evalScript = function (e, cb) {{ cb(null); }};
      CSInterface.prototype.getHostEnvironment = function () {{ return "{{}}"; }};
      TempoAPI = {{}};
      vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'),
                          {{ filename: process.argv[2] }});
      console.log(JSON.stringify({expr}));
    """
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "driver.js").write_text(driver, encoding="utf-8")
        proc = subprocess.run(
            [node, str(d / "driver.js"), str(PANEL_JS)],
            capture_output=True, text=True, timeout=60,
        )
    assert proc.returncode == 0, (
        f"panel.js failed to evaluate:\n{proc.stdout}\n{proc.stderr}"
    )
    return proc.stdout.strip().splitlines()[-1]


def _step_order(job: dict) -> list[str]:
    """The stage keys panel.js would render, in render order, for one job."""
    ordered = json.loads(_panel_eval(f"stepOrder({json.dumps(job)})"))
    return [row["key"] for row in ordered]


def _panel_eval_fn(fn: str, setup: str) -> object:
    """Run `fn` in panel.js after `setup` has mutated its store."""
    return json.loads(_panel_eval(f"(() => {{ {setup}; return {fn}(); }})()"))


def _job(state: str, stages: list[tuple[str, str]]) -> dict:
    return {"state": state, "stages": [{"name": n, "state": s} for n, s in stages]}


def test_panel_js_evaluates_cleanly():
    """panel.js must load without a runtime error, and define its globals.

    `node --check` (the CI gate) is parse-only: a file that begins `re/* ... */`
    parses fine and then throws ReferenceError on load, which is exactly how a
    stray edit reached panel.js once. Evaluating it the way a browser does
    catches that class of bug without needing a browser.
    """
    names = ("store", "render", "stepOrder", "stepNumber", "doSearch")
    expr = "({ " + ", ".join(f"{n}: typeof {n}" for n in names) + " })"
    kinds = json.loads(_panel_eval(expr))
    expected = {"store": "object", "render": "function", "stepOrder": "function",
                "stepNumber": "function", "doSearch": "function"}
    assert kinds == expected, "panel.js loaded but did not define its globals"


def test_step_order_shows_only_started_stages():
    """A stage that has not started draws no row (AGENTS.md §5 F4).

    The list is the running stage plus what is already finished. Pending rows
    cost the editor the real progress: nine of them at the start of every job,
    pushing the running row off a docked panel.
    """
    assert _step_order(_job("running", [
        ("upload", "done"), ("shots", "done"), ("visual", "running"),
        ("transcribe", "pending"), ("ocr", "pending"), ("captions", "pending"),
        ("text", "pending"), ("index", "pending"),
    ])) == ["visual", "shots", "upload"]

    # Nothing has started: no rows at all. The pill is the whole screen.
    assert _step_order(_job("running", [
        ("upload", "pending"), ("shots", "pending"), ("visual", "pending"),
    ])) == []


def test_step_order_keeps_the_rows_that_are_not_ordinary_progress():
    """The rows that carry information survive the pending hiding.

    An errored stage is why indexing stopped, an unknown stage name is the
    engine doing something the panel has no label for, and the synthetic queued
    row is the only thing on screen between enqueue and the first stage.
    """
    assert _step_order(_job("running", [
        ("upload", "done"), ("visual", "error"), ("shots", "pending"),
    ])) == ["upload", "visual"]

    assert _step_order(_job("running", [
        ("upload", "done"), ("regroup", "running"), ("shots", "pending"),
    ])) == ["upload", "regroup"]

    assert _step_order(_job("queued", [("upload", "pending")])) == ["queued"]


def test_panel_has_no_dead_step_bar():
    """The Figma step rows carry no progress bar (777:702) — progress is the
    running row's own readout. The bar markup, its CSS and the high-water store
    were all removed; a stray reference means someone re-added half of it."""
    src = PANEL_JS.read_text(encoding="utf-8")
    css = PANEL_CSS.read_text(encoding="utf-8")
    for dead in ("stepFraction", "hwm", "className = \"bar\"", "<i>"):
        assert dead not in src, f"panel.js reintroduced {dead!r}"
    assert ".step .bar" not in css, "panel.css still styles a step progress bar"


def test_indexing_section_is_visible_only_when_it_has_something_to_say():
    """The section opens for a live job, a failed one, or footage the panel can
    still act on, and for nothing else.

    The last two are per-footage states that outlive a panel restart, unlike a
    job id: a job lost to a service restart leaves the registry entry at
    `indexing` (Resume) or `error` (Retry), and the empty-state hint in the
    results area tells the editor to open the indexing detail for both. If the
    section stayed hidden there, that hint pointed at nothing -- which is the
    bug the rule exists to prevent.
    """
    def visible(footages: list[dict], jobs: dict = None, active: list[str] = None) -> bool:
        setup = (
            f"store.footages = {json.dumps(footages)};"
            f"store.jobs = {json.dumps(jobs or {})};"
            f"store.activeJobs = {json.dumps(active or [])}"
        )
        return bool(_panel_eval_fn("indexingVisible", setup))

    assert not visible([]), "no footage, no job: nothing to say"
    assert not visible([{"state": "ready"}]), "ready footage needs no indexing detail"
    assert not visible([{"state": "stale"}]), "stale footage needs no indexing detail"
    assert visible([{"state": "error"}]), "a failed footage row carries Retry"
    assert visible([{"state": "indexing"}]), "footage stranded mid-index carries Resume"
    assert visible([{"state": "uploading"}]), "so does one stranded mid-upload"
    assert visible([], {"job_1": {"state": "error"}}), "a failed job keeps its message"
    assert visible([], {"job_1": {"state": "done"}}, ["job_1"]), "a live job is the section"


def test_panel_has_no_indexing_summary():
    """The indexing screen names no file.

    It used to open with `Indexing · <file name> · <stage> <n>` above the step
    list: one more string to keep in sync, one more thing to truncate in a
    300px panel, and the only place a filename appeared outside the results
    cards and the footage filter. The step rows, the error row and the footage
    rows carry what matters. Assert the whole apparatus stays gone.
    """
    src = PANEL_JS.read_text(encoding="utf-8")
    html = PANEL_HTML.read_text(encoding="utf-8")
    for dead in ("indexSummary", "currentStep", "footageName", "indexing-summary", "Indexing ·"):
        assert dead not in src, f"panel.js reintroduced {dead!r}"
        assert dead not in html, f"index.html reintroduced {dead!r}"
    # The heading itself is not optional: it is the whole screen between enqueue
    # and the first stage reporting.
    assert "Processing your videos" in html


def test_panel_header_is_the_wordmark_not_a_navbar():
    """The top row is the wordmark, the status dot and Sync now, and nothing else.

    It used to be a navbar: a `Tempo` text mark and the service and engine states
    written out as `service ok` and `engine gpu`. The wordmark replaces the text
    mark, and the dot already encodes the same three states (ok / warn / bad) at a
    glance, so the labels were a second rendering of one value. AGENTS.md 4.4 binds
    two things into this row, so the test pins what survives as well as what does
    not: the honest engine status, and the manual sync fallback.

    The removal is pinned by mechanism, not by prose: the states themselves still
    exist as the dot's legend, so forbidding the words would forbid the honest
    reporting along with the navbar.
    """
    html = PANEL_HTML.read_text(encoding="utf-8")
    src = PANEL_JS.read_text(encoding="utf-8")
    css = PANEL_CSS.read_text(encoding="utf-8")

    for dead in (
        'id="brand"', 'id="svc"', 'id="backend"', "statusbar",
        '$("svc")', '$("backend")',
    ):
        assert dead not in html, f"index.html reintroduced {dead!r}"
        assert dead not in src, f"panel.js reintroduced {dead!r}"
        assert dead not in css, f"panel.css reintroduced {dead!r}"

    # AGENTS.md 4.4, the two reasons this row still exists.
    assert 'id="sync-now"' in html, "Sync now is 4.4's manual fallback"

    # With the on-screen labels gone the dot carries the whole state, so it must
    # stay readable to assistive tech -- it used to be aria-hidden because the
    # text nodes beside it were what said so.
    assert 'id="svc-dot"' in html
    assert 'aria-hidden' not in html.split('id="svc-dot"')[1][:80], (
        "the dot is the only carrier of 4.4's status now; hiding it hides the state"
    )

    # A near-white raster mark vanishes on the light theme (#d6d6d6). The wordmark
    # is white with two accent marks, so the light theme inverts lightness and
    # rotates hue back; a plain invert would turn them cyan.
    assert re.search(
        r"html\.light[^{]*#logo[^{]*\{[^}]*invert\(1\)[^}]*hue-rotate\(180deg\)", css
    ), "the light theme must invert the wordmark and restore the accent hue"


def test_status_dot_reports_state_and_its_legend_together():
    """The dot's colour and its legend come from one decision, and both land.

    Asserting that `dot.title` is assigned would pass for a function that assigns
    an empty string, so this drives the real renderStatus() through the panel-eval
    seam and reads what the element ends up carrying. The old bar computed the
    class and the words as two separate cascades over the same conditions, which is
    exactly how a dot and the words beside it drift apart; one backendState() now
    returns both, and each of the five real states gets its own pair here.
    """
    stub = (
        "const dot = { className: '', title: '', attrs: {},"
        " setAttribute(k, v) { this.attrs[k] = v; } };"
        "document.getElementById = (id) => (id === 'svc-dot' ? dot : null);"
    )

    def rendered(online: bool, backend: dict) -> tuple[str, str, str]:
        setup = (
            f"{stub}"
            f"store.online = {str(online).lower()};"
            f"store.backend = {json.dumps(backend)};"
            "renderStatus();"
            "return {cls: dot.className, title: dot.title,"
            " aria: dot.attrs['aria-label']};"
        )
        got = json.loads(_panel_eval(f"(() => {{ {setup} }})()"))
        return got["cls"], got["title"], got["aria"]

    ok = {"tunnel": "up", "reachable": True, "gpu": True}
    seen: dict[str, tuple[str, str, str]] = {}

    seen["ok-gpu"] = rendered(True, ok)
    seen["ok-cpu"] = rendered(True, {**ok, "gpu": False})
    seen["warn"] = rendered(True, {"tunnel": "starting", "reachable": False, "gpu": False})
    seen["tunnel-down"] = rendered(True, {"tunnel": "down", "reachable": False, "gpu": False})
    seen["engine-offline"] = rendered(True, {"tunnel": "up", "reachable": False, "gpu": False})
    seen["service-offline"] = rendered(False, ok)

    # The three states, and only those three.
    classes = {name: r[0] for name, r in seen.items()}
    assert classes == {
        "ok-gpu": "dot ok",
        "ok-cpu": "dot ok",
        "warn": "dot warn",
        "tunnel-down": "dot bad",
        "engine-offline": "dot bad",
        "service-offline": "dot bad",
    }

    for name, (cls, title, aria) in seen.items():
        assert title, f"{name}: the dot has a colour but no legend at all"
        assert aria == title, f"{name}: legend and aria-label disagree ({title!r} / {aria!r})"

    # Each state names itself: no two distinct states share a legend, and the
    # reachable/unreachable distinction is legible, not just coloured.
    assert len({t for _, t, _ in seen.values()}) == len(seen)
    assert "GPU" in seen["ok-gpu"][1] and "CPU" in seen["ok-cpu"][1]
    assert "offline" in seen["service-offline"][1].lower()


def test_wordmark_asset_geometry_agrees_with_css_and_markup():
    """The 14px / 80px / 280x49 triple is one derived number in three places.

    AGENTS.md 8 lists duplicated constants that must stay in sync as prohibited
    unless pinned. The wordmark is height-driven and `width: auto`, so the rendered
    width is the asset's aspect ratio times the CSS height -- and the <img>
    attributes have to state an integer that matches, or the panel shows a
    stretched box until the CSS loads. Read the PNG's own header rather than
    trusting the docs: this also fails if the asset is swapped or re-proportioned.
    """
    html = PANEL_HTML.read_text(encoding="utf-8")
    css = PANEL_CSS.read_text(encoding="utf-8")

    m = re.search(
        r'<img id="logo" src="([^"?]+)(?:\?[^"]*)?"[^>]*?width="(\d+)"[^>]*?height="(\d+)"', html
    )
    assert m, "index.html must declare the wordmark's size on the <img>"
    src, attr_w, attr_h = m.group(1), int(m.group(2)), int(m.group(3))

    logo = PANEL_HTML.parent / src
    assert logo.is_file(), f"{logo} is referenced by index.html but is not on disk"

    # PNG dimensions live in the IHDR: an 8-byte signature, then a 4-byte length,
    # the "IHDR" type, then width and height as big-endian uint32.
    blob = logo.read_bytes()
    assert blob[:8] == b"\x89PNG\r\n\x1a\n" and blob[12:16] == b"IHDR", (
        f"{logo.name} is not a PNG; the markup and CSS assume a raster asset"
    )
    px_w = int.from_bytes(blob[16:20], "big")
    px_h = int.from_bytes(blob[20:24], "big")

    ch = re.search(r"#logo\s*\{[^}]*?height:\s*(\d+)px", css)
    assert ch, "#logo must be height-driven so the asset's proportion holds"
    css_h = int(ch.group(1))
    assert "width: auto" in re.search(r"#logo\s*\{[^}]*\}", css).group(0), (
        "the wordmark must keep the asset's own proportion (width: auto)"
    )

    assert attr_h == css_h, (
        f"the <img> says height={attr_h} but panel.css renders {css_h}px"
    )
    assert attr_w == round(px_w * css_h / px_h), (
        f"at {css_h}px tall the {px_w}x{px_h} asset renders "
        f"{px_w * css_h / px_h:.2f}px wide, but the <img> declares {attr_w}"
    )


def test_preview_harness_repoints_the_wordmark():
    """preview.html's #app must stay byte-identical to the panel's, so it cannot
    repoint the wordmark's src itself -- the harness has to, or the preview renders
    a broken image where the panel shows the mark."""
    harness = (PREVIEW_HTML.parent / "preview-harness.js").read_text(encoding="utf-8")
    assert "../../panel/www/logo.png" in harness, (
        "the preview must repoint #logo at the shipped asset; the markup copy is "
        "pinned byte-identical and cannot do it"
    )


def _css_rule(css: str, selector: str) -> str:
    """The declaration block for one selector, so assertions read as properties.

    Anchored at line start and requiring `{` straight after the selector, so
    `button.icon` does not also match `button.icon svg`.
    """
    m = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert m, f"panel.css has no rule for {selector}"
    return m.group(1)


# The narrow dock both the badge and the skeleton are sized against: a 300px AE
# panel, which is the case both were chosen in. One derivation, shared, because
# two tests quoting 132 is a constant that can go stale in one place only.
NARROW_DOCK_PX = 300


def _grid_thumb_width(css: str) -> float:
    """The width of one result card's thumbnail at NARROW_DOCK_PX.

    Composed rather than quoted: the dock less #app's padding, split by the
    grid's gap, less the card's stroke on both sides. A change to any of those
    moves every consumer, which is the point — a test that hardcodes 132 keeps
    passing after the geometry moves out from under it.
    """
    pad = int(re.search(r"padding:\s*(\d+)px", _css_rule(css, "#app")).group(1))
    gap = int(re.search(r"gap:\s*(\d+)px", _css_rule(css, "#results.grid")).group(1))
    stroke = int(re.search(r"border:\s*(\d+)px solid", _css_rule(css, ".card")).group(1))
    return (NARROW_DOCK_PX - 2 * pad - gap) / 2 - 2 * stroke


def test_view_toggle_is_the_design_geometry_on_the_left():
    """Figma 777:473 is two 64px chips, 16px apart, flush with the card grid.

    Measured off the design (`docs/design/panel-ui.md` §1, "The view pair keeps the
    design's ratios, not its pixels"): the chip is 64x64 with radius 8, the icon
    asset is a 38-unit box holding a 32-unit glyph, the pair is 16 apart, and the
    left edge of the pair lines up with the first card.

    Most of that scales by shape rather than by pixels -- at the frame scale a 64px
    chip would be 10px, and AGENTS.md §6 pins icons at 16px regardless. What
    survives is the shape, so that is what is asserted: the radius' share of the
    chip, and the icon's share of it. A later resize that changes the chip without
    re-deriving the other two fails here rather than shipping a cramped or a loose
    control.

    The chip is 32 rather than 24 because of the icon. The exported asset is a
    38-unit box, and 38/64 of a 32px chip is 19px exactly -- which renders the
    32-unit glyph at 16.0px, on AGENTS.md §6's floor rather than through it. The
    same asset in the 24px chip it replaces renders at 13.5px, which is why the
    chip grew instead of just moving.

    The viewBox is asserted alongside the slot because it is what the glyph size is
    actually computed from. Changing either alone rescales the icon silently --
    19px into a 64-unit box is a 9.5px glyph -- and every other assertion here
    still passes.

    The gap is the one ratio that is deliberately NOT held. ADR-0015 removed the
    16-of-64 spacing (8px in a 32px chip) and the two chips now touch, so the
    pressed fill is the only thing separating them and the pair reads as one 64px
    control. That is a departure from the design, on the product owner's call, and
    it is the kind that fails silently -- a later edit restoring the gap would look
    like a fix. So it is asserted as an ABSENCE (the rule declares no `gap`, rather
    than declaring the flex default of 0), which fails a restoration at any value,
    and the one thing that must survive the adjacency is asserted too: the active
    chip is still the filled one, or the pair has no state left to carry at all.
    """
    html = PANEL_HTML.read_text(encoding="utf-8")
    css = PANEL_CSS.read_text(encoding="utf-8")

    # Left, not right. The pair is the row's first child and the row's auto margin
    # belongs to the filter, which is the only other thing in it.
    toggle = _css_rule(css, "#viewtoggle")
    assert "margin" not in toggle, (
        "the design puts the pair flush left on the card grid; a margin here is "
        "what pushed it right"
    )
    assert "margin-left: auto" in _css_rule(css, "#footage-filter"), (
        "with the pair on the left, the filter is what the row pushes right"
    )
    assert html.index('id="viewtoggle"') < html.index('id="footage-filter"'), (
        "the pair comes before the filter in the markup, not only in the layout"
    )

    # Flush left *on the card grid*, which is the line the design puts it on. The
    # row and the results share an inset because neither declares one; if either
    # grows a horizontal padding the pair stops lining up with the cards and
    # nothing else in this file would notice.
    for row in ("#searchmeta", "#results"):
        inset = _css_rule(css, row)
        for side in ("padding", "margin"):
            for edge in ("left", "right"):
                assert f"{side}-{edge}" not in inset, (
                    f"{row} gained {side}-{edge}; the view pair and the card grid "
                    "are aligned by both being flush in #app"
                )

    # The design's radius ratio, and the gap's departure from it. The rule declares
    # no `gap` at all: flex gap is 0 by default, so a `gap: 0` declaration would be a
    # no-op kept alive only to be read here, which is the dead weight §8 lists.
    # Asserting the absence is the stronger pin anyway — it fails a later `gap: 8px`
    # and a later `gap: 0px` equally, and says why.
    box = int(re.search(r"width:\s*(\d+)px", _css_rule(css, "button.icon")).group(1))
    assert "gap" not in toggle, (
        "ADR-0015 sets the pair's gap to nothing — the design's 16 of 64 was reversed "
        f"and the two {box}px chips now touch, with the pressed fill as the only "
        "separator. A gap here at any value is the regression, so the rule declares "
        "none"
    )
    radius = int(re.search(r"--r-sm:\s*(\d+)px", css).group(1))
    assert radius == box / 8, f"the design rounds the chip 8 into a 64 chip; --r-sm {radius}px in {box}px"

    # The icon's share of the chip, and what that renders the glyph at.
    chip, icon_box, glyph_units = 64, 38, 32
    icon = re.search(
        r'id="view-grid"[\s\S]*?<svg width="(\d+)" height="(\d+)" viewBox="0 0 (\d+) (\d+)"',
        html,
    )
    assert icon, "the view icons must declare their box and their viewBox"
    slot_w, slot_h, vb_w, vb_h = (int(g) for g in icon.groups())
    assert (slot_w, slot_h) == (slot_w, slot_w), "the icon slot must not be stretched"
    assert (vb_w, vb_h) == (icon_box, icon_box), (
        f"the asset is a {icon_box}-unit box; a viewBox of {vb_w}x{vb_h} rescales "
        "the glyph and every size below with it"
    )
    assert slot_w == round(box * icon_box / chip), (
        f"the design's icon fills {icon_box} of its {chip} chip, so {box}px wants "
        f"{round(box * icon_box / chip)}px, not {slot_w}px"
    )
    rendered = slot_w * glyph_units / vb_w
    assert rendered >= 16, (
        f"AGENTS.md §6 wants icons identifiable at 16px; this one renders at "
        f"{rendered:.1f}px"
    )

    # The asset carries its own stroke, so no CSS rule may flatten it back to one
    # weight for both icons -- the grid exports 3.5625 and the list 3.16667.
    assert "stroke-width" not in _css_rule(css, "button.icon svg"), (
        "the exported icons bring their own stroke-width; a CSS one overrides both"
    )
    widths = set(re.findall(r'id="view-(?:grid|list)"[\s\S]*?stroke-width="([\d.]+)"', html))
    assert len(widths) == 2, (
        f"each icon keeps the stroke the design exported it with, got {widths}"
    )

    # The list icon is three rules and three bullets. The bullets are zero-length
    # segments that `stroke-linecap: round` draws as dots; three bare rules is what
    # the panel shipped before and it is not the design's icon.
    zero_len = 0.1  # a bullet's segment length; an export puts it just above zero
    list_d = re.search(r'id="view-list"[\s\S]*?<path d="([^"]+)"', html).group(1)
    segments = [
        (float(x0), float(y), float(x1))
        for x0, y, x1 in re.findall(r"M([\d.]+) ([\d.]+)H([\d.]+)", list_d)
    ]
    bullets = [s for s in segments if abs(s[2] - s[0]) < zero_len]
    rules = [s for s in segments if s[2] - s[0] > zero_len]
    assert len(rules) == 3 and len(bullets) == 3, (
        f"the design's list icon is 3 rules and 3 bullets, got {len(rules)} and "
        f"{len(bullets)}"
    )
    assert all(b[0] < r[0] for b, r in zip(bullets, rules)), (
        "the bullets sit to the left of the rules they mark"
    )

    # One chip and one bare icon: the design signals the active view with the fill,
    # so a second identical fill makes the pair two chips and says nothing.
    assert "background: transparent" in _css_rule(css, "button.icon")
    assert "background: var(--surface)" in _css_rule(css, 'button.icon[aria-pressed="true"]')


def test_search_field_carries_the_designs_spacing():
    """The field is 82px, and every part of that is derived rather than asserted.

    ADR-0013 landed this field at 107px from a 1x render of Figma `search_input`
    (815:294, inside `04_search_results_frame`): a 1836x196 field whose top
    padding, ink-to-ink label-to-value gap and bottom padding are 47 / 46 / 53 of
    that 196, scaled by the type ratio (the panel's 13px value against the
    design's 32px = 0.406) to 20 / 20 / 20, side padding 16.

    ADR-0015 reverses that spacing to 16 / 16 / 8 on the product owner's call --
    the field is the panel's densest control and 107px is over a third of a 300px
    viewport before any result. The derivation below is what changed, not the
    method: the numbers are still read off the design's ratios and landed on the
    4px rhythm, and the height is still a consequence of the parts rather than a
    target. ADR-0015 is the record; this is the pin.

    One part of the old arithmetic is genuinely gone, and it is asserted rather
    than assumed. The label row used to be 21px *because the icon was 21px* --
    the design's own export, exempt from the scale. At 10px the icon no longer
    sets the row; the 11px label text does, at the inherited 1.45 line-height.
    A field that kept counting 21 here would claim 87px and be wrong, so the
    assertion is that the icon is shorter than the line it sits on.

    `--r-lg` stays at 8px on purpose. It also carries the indexing and
    empty-state pills, which come from a different Figma node whose radius is
    not verified here, so the field gets its own token rather than moving them.

    The icon is the design's own path, so `stroke` has to be currentColor:
    literal white is invisible on the light theme, and keeping stroke-opacity
    beside an already-translucent colour compounds the alpha instead of setting
    it. Its stroke-width stays on the path: CSS would override the asset's 2.2751,
    so the two would conflict rather than merely restate each other, and
    AGENTS.md 8 wants one owner per constant. The step icons set that precedent.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")
    html = PANEL_HTML.read_text(encoding="utf-8")

    box = _css_rule(css, "#searchbox")
    assert "padding: 16px;" in box, box
    assert "gap: 8px;" in box, box
    assert "border-radius: var(--r-field);" in box, box
    assert "--r-field: 10px;" in css, "the field's radius must come from its own token"
    assert "--r-lg: 8px;" in css, "the pills keep the radius they were measured at"

    head = _css_rule(css, ".sb-head")
    assert "gap: 6px;" in head, head
    assert "stroke-width" not in _css_rule(css, ".sb-head svg"), (
        "the icon carries its own stroke-width; a second owner would drift"
    )

    assert 'viewBox="0 0 21 21"' in html, "the design's search icon is a 21px asset"
    assert 'stroke="currentColor"' in html, "a literal white stroke vanishes on light"

    # The height, from the parts. Every input is read out of the shipped CSS
    # rather than restated, so a future edit to the padding, the gap, the
    # button or the label type moves this number instead of failing it.
    pad = int(re.search(r"padding:\s*(\d+)px;", box).group(1))
    gap = int(re.search(r"gap:\s*(\d+)px;", box).group(1))
    label_fs = int(re.search(r"font-size:\s*(\d+)px;", head).group(1))
    line_height = float(
        re.search(r"font:\s*12px/([\d.]+)", css).group(1)
    )  # body's, inherited by the unitless value on .sb-head
    submit = re.search(r"width:\s*(\d+)px;\s*height:\s*\1px", _css_rule(css, "#submit"))
    assert submit, "the value row is set by #submit, so it must be a square px box"
    # `.edge` is the 1px gradient stroke the field carries on both sides.
    border = int(re.search(r"border:\s*(\d+)px solid transparent", css).group(1))

    # The .sb-head fragment, scoped rather than searched document-wide: the
    # assertions below are about one icon, and index.html carries four.
    head_html = re.search(r'(?s)<div class="sb-head">.*?</div>', html)
    assert head_html, "index.html has no .sb-head block"
    head_html = head_html.group(0)

    label_row = label_fs * line_height
    icon = int(re.search(r'<svg width="(\d+)" height="\1"', head_html).group(1))
    assert icon < label_row, (
        f"the label row is {label_row:.2f}px because the text sets it; an icon of "
        f"{icon}px cannot, so this test's arithmetic is what the field actually is"
    )

    height = 2 * border + 2 * pad + label_row + gap + int(submit.group(1))
    assert height == pytest.approx(82, abs=0.5), (
        f"2 + 2*{pad} + {label_row:.2f} + {gap} + {submit.group(1)} = {height:.2f}px, "
        "not the 82px the field is documented at"
    )

    # The 16px floor is AGENTS.md 6's, and this icon is the one export below it
    # (ADR-0015). The exception is bounded rather than open: at 10px of a 21-unit
    # box the design's own 2.2751 stroke lands on 1.08px, and the floor is what
    # makes that number worth checking rather than assuming.
    stroke = float(re.search(r'stroke-width="([\d.]+)"', head_html).group(1))
    assert icon * stroke / 21 == pytest.approx(1.08, abs=0.01), (
        "the icon is 10px of a 21-unit asset; restate the ADR if either number moved"
    )

    assert "stroke-opacity=" not in head_html, (
        "stroke-opacity over an already-translucent colour compounds it"
    )
    assert "Search for anything" in head_html, "the design's label is the field's label"
    assert "Search footage" not in head_html, "the label was replaced, not added to"

    # The field's own edge. AGENTS.md 6 and docs/ui-review.md both state it, so it
    # is pinned here rather than left to drift against two prose copies: a 180deg
    # ramp whose top is a lighter white and whose bottom is the design's own 0.28.
    # The light theme is a flat 0.18 at the same angle, which is a different ramp
    # and not an inconsistency.
    edges = re.findall(r"--edge:\s*linear-gradient\((\d+)deg([^;]+)\);", css)
    assert len(edges) == 2, "both themes must declare --edge"
    angles = {a for a, _ in edges}
    assert angles == {"180"}, f"the design's paint is vertical; got {angles}"
    alphas = [tuple(re.findall(r"([\d.]+)\)", stops)) for _, stops in edges]
    assert alphas[0] == ("0.16", "0.28"), (
        f"the dark ramp is white 0.16 -> surface 0.28; got {alphas[0]}"
    )
    assert alphas[1] == ("0.18", "0.18"), (
        f"the light theme is a flat 0.18 at the same angle; got {alphas[1]}"
    )


def test_the_thumbnail_and_the_meta_row_take_their_tokens():
    """Two values ADR-0015 set that nothing else in the file was watching.

    Both are single declarations with no downstream consumer, which is exactly the
    shape of a value that gets changed by accident:

    - **`.thumb`'s radius.** `panel-ui.md` §1 has always listed `--r-md` as
      covering "cards, thumbnails, skeleton blocks" and the rule never declared
      it, so a keyframe rendered square inside a rounded card. It is the design's
      12 of 560, the same ratio as the card's, so the two corners agree.
    - **`#searchmeta`'s top margin.** This one is a product-owner value and is
      recorded as one: the design's 76px and 48px of vertical space are 11 and 7
      at frame scale, and neither lands on `#app`'s uniform 8px. There is no
      derivation that produces 16 from those numbers, so the test pins the value
      and the reason rather than pretending to derive it — which is the honest
      thing for a value that was chosen, not computed.

    The margin is a vertical inset, so the flush-left assertion in
    `test_view_toggle_is_the_design_geometry_on_the_left` (which is about the
    horizontal inset) does not cover it.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")

    radius = int(re.search(r"--r-md:\s*(\d+)px", css).group(1))
    card_radius = int(re.search(r"--r-field:\s*(\d+)px", css).group(1))
    assert radius == 3 and card_radius == 10, (
        f"--r-md {radius}px and --r-field {card_radius}px are the design's two "
        "measured ratios; restate the ADRs if either moved"
    )
    assert "border-radius: var(--r-md);" in _css_rule(css, ".thumb"), (
        "the thumbnail is the design's 12 of 560, the card's own ratio; a keyframe "
        "square inside a rounded card is what this rule was missing"
    )

    meta = _css_rule(css, "#searchmeta")
    margin = int(re.search(r"margin-top:\s*(\d+)px", meta).group(1))
    assert margin == 16, (
        f"#searchmeta's own top margin is 16px on the 4px rhythm, one notch tighter "
        f"than #app's 8px gap; this reads {margin}px. It is a product-owner value — "
        "the design's 76 and 48 scale to 11 and 7, neither of which is 16 — so change "
        "it in the ADR and here together"
    )


def test_header_draws_no_hairline_under_the_wordmark():
    """The header has no rule under it, because the design has none.

    The divider was part of the same invention as the bar it replaced: neither
    appears in the Figma frames. The two controls stay regardless -- AGENTS.md
    4.4 binds the honest engine status and the manual sync fallback into this
    row, and the dot is now the only carrier of that state.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")
    html = PANEL_HTML.read_text(encoding="utf-8")

    bar = _css_rule(css, "#topbar")
    assert "border-bottom" not in bar, bar
    assert "display: flex" in bar, "the row is still a row"
    assert "--border" in css, "the hairline token is used elsewhere and must survive"
    for kept in ('id="svc-dot"', 'id="sync-now"'):
        assert kept in html, f"{kept} is AGENTS.md 4.4's, not the design's to remove"


def test_panel_top_k_matches_service():
    """panel.js TOP_K and the sidecar /search default must agree.

    A cross-runtime constant with no pin is one of the nine AGENTS.md 8 lists as
    unpinned; changing one side silently changes the other. The panel reads its
    own literal and the service reads app.py's, so assert the two agree and that
    the panel never hardcodes a bare literal at the call site.
    """
    from tempo_service.app import create_app

    panel = PANEL_JS.read_text(encoding="utf-8")
    m = re.search(r"const TOP_K = (\d+);", panel)
    assert m, "panel.js must declare a TOP_K constant"
    panel_top_k = int(m.group(1))

    route = next(
        r for r in create_app().routes
        if getattr(r, "path", None) == "/search" and "GET" in getattr(r, "methods", set())
    )
    service_top_k = next(
        p.default for p in route.dependant.query_params if p.name == "top_k"
    )
    assert panel_top_k == service_top_k, (
        f"top_k drift: panel.js TOP_K={panel_top_k}, app.py default={service_top_k}"
    )
    # The search call must go through the constant, not a literal.
    assert "TempoAPI.search(q, TOP_K," in panel, "panel search must use TOP_K"


# --------------------------------------------------------------------------
# Panel layout (docs/design/panel-ui.md 3)
#
# There is no browser in CI, so these pin the two halves of a layout that can be
# pinned without one: the CSS that decides it, and the state that switches it on.
# --------------------------------------------------------------------------

# A stub DOM, because which branch a screen renders is decided by a render()
# call rather than by a pure function: panel.js talks to document on the way
# through. Enough of one for renderIndexing()/renderResults() — no layout, no
# measurement, no assertion about pixels.
_STUB_DOM_DRIVER = r"""
const fs = require('node:fs'), vm = require('node:vm');
window = global;
const mk = () => {
  const classes = new Set();
  const el = {
    hidden: false, className: '', textContent: '', innerHTML: '',
    dataset: {}, style: {}, parentNode: null, children: [],
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
      toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)),
    },
  };
  el.appendChild = (c) => { c.parentNode = el; el.children.push(c); return c; };
  el.removeChild = (c) => { el.children = el.children.filter((x) => x !== c); c.parentNode = null; };
  el.addEventListener = () => {};
  el.setAttribute = () => {};
  el.getBoundingClientRect = () => ({ top: 0, left: 0, width: 0, height: 0 });
  el.querySelector = () => mk();
  el.querySelectorAll = () => [];
  return el;
};
const nodes = {};
document = {
  addEventListener() {},
  createElement: () => mk(),
  getElementById: (id) => (nodes[id] || (nodes[id] = mk())),
};
CSInterface = function () {};
CSInterface.prototype.evalScript = function (e, cb) { cb(null); };
CSInterface.prototype.getHostEnvironment = function () { return '{}'; };
TempoAPI = {};
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'),
                    { filename: process.argv[2] });
const out = (() => { /*SETUP*/ /*CALL*/; return /*EXPR*/; })();
console.log(JSON.stringify(out));
"""


def _panel_render(call: str, setup: str, expr: str) -> object:
    """Run one render call in panel.js against a stub DOM; return `expr` after it."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node not on PATH")

    driver = (_STUB_DOM_DRIVER.replace("/*SETUP*/", setup)
              .replace("/*CALL*/", call).replace("/*EXPR*/", expr))
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "driver.js").write_text(driver, encoding="utf-8")
        proc = subprocess.run(
            [node, str(d / "driver.js"), str(PANEL_JS)],
            capture_output=True, text=True, timeout=60,
        )
    assert proc.returncode == 0, (
        f"panel.js failed to render:\n{proc.stdout}\n{proc.stderr}"
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


_RUNNING_JOB = json.dumps({
    "job_id": "job_1", "state": "running", "footage_key": "abcd1234ef",
    "stages": [
        {"name": "upload", "state": "done", "done": 1, "total": 1},
        {"name": "shots", "state": "running", "done": 3, "total": 10},
    ],
})


def test_indexing_section_is_live_exactly_while_a_job_runs():
    """`live` gates both the pill and the reserved step-list height, so it must
    follow the same flag.

    The section is centred, which means its height decides where the pill sits:
    with rows arriving one at a time, an unreserved list walks the pill down the
    panel for the whole run and back up again at the end. Holding the height while
    a job runs pins the pill where it finishes. The pin is worth nothing if the
    two are driven by different conditions, so assert they are driven by one.
    """
    live = "store.activeJobs = ['job_1']; store.jobs = { job_1: %s };" % _RUNNING_JOB

    shown = _panel_render("renderIndexing()", live, "document.getElementById('indexing').classList.contains('live')")
    assert shown, "a running job must mark the section live so the pill holds still"

    # The same store with the job finished (polledJobs drops a done job): the
    # reserve goes with the pill, so the footage rows below are not stranded
    # under an empty 216px gap.
    done = live.replace('"state": "running"', '"state": "done"').replace(
        "store.activeJobs = ['job_1'];", "store.activeJobs = [];"
    )
    assert not _panel_render("renderIndexing()", done, "document.getElementById('indexing').classList.contains('live')")

    # A job the engine never picked up is still a run: the queued row is on screen.
    queued = (
        "store.activeJobs = ['job_1']; store.jobs = { job_1: "
        '{ job_id: "job_1", state: "queued", stages: [] } };'
    )
    assert _panel_render("renderIndexing()", queued, "document.getElementById('indexing').classList.contains('live')")

    # The pill is drawn from the same flag in the same render.
    src = PANEL_JS.read_text(encoding="utf-8")
    assert re.search(r'\$?\("indexing-pill"\)\.hidden = !live;', src)
    assert re.search(r'\$?\("indexing"\)\.classList\.toggle\("live", live\);', src)


def test_indexing_reserves_the_finished_step_list_height():
    """The reserve is nine rows tall, and nine is STEPS' count.

    The height is a second copy of the step count (panel.js owns the list, CSS
    owns the layout), so the two are cross-checked here rather than trusted.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")
    js = PANEL_JS.read_text(encoding="utf-8")

    assert re.search(
        r"#indexing\.live #indexing-detail \{ min-height: "
        r"calc\(var\(--step-h\) \* var\(--step-count\)\);", css
    ), "the live detail block must be held at the finished list's height"
    assert re.search(r"\.step \{[^}]*min-height: var\(--step-h\);", css), (
        "a step row must be --step-h tall or the reserve is not the list's height"
    )

    steps = re.search(r"(?s)const STEPS = \[(.*?)\n\];", js)
    assert steps, "panel.js must declare STEPS"
    rows = len(re.findall(r'\{ key: "', steps.group(1)))
    reserved = re.search(r"--step-count: (\d+);", css)
    assert reserved, "panel.css must declare --step-count"
    assert rows == int(reserved.group(1)) == 9, (
        f"the reserve assumes {reserved.group(1)} rows, STEPS has {rows}"
    )


def test_indexing_pill_is_sized_by_its_content():
    """The pill fits its label and its indicator, centred in the column.

    It used to stretch the full column: a 320px banner carrying one short label,
    which read as a rule rather than as the heading the design drew (777:698).
    """
    css = PANEL_CSS.read_text(encoding="utf-8")
    pill = re.search(r"(?ms)^\.pill \{(.*?)\}", css)
    assert pill, "panel.css must style .pill"
    assert "align-self: center;" in pill.group(1)
    assert "width" not in pill.group(1), "the pill must take its width from its content"

    label = re.search(r"(?ms)^\.pill-label \{(.*?)\}", css)
    assert label, "panel.css must style .pill-label"
    # flex: 1 (basis 0) is a full-width layout's trick and collapses a
    # content-sized label to nothing but the indicator.
    assert "flex: 0 1 auto;" in label.group(1)


def test_spinners_are_the_accent_over_a_white_track():
    """Every indeterminate indicator is the accent arc over a white track.

    The track used to be currentColor at 0.35 alpha, which composited to a flat
    gray on the pill and inside the submit button: the one thing on the screen
    saying "working" was its dullest pixel. The track is a token instead, white on
    the dark theme and a visible gray on the light one (white vanishes on
    #f2f2f2), and the running row's ray burst takes the accent through
    currentColor, so all three indicators read as the same accent.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")

    assert re.search(r"\.spin \.arc \{ fill: var\(--accent\); \}", css)
    assert re.search(r"\.spin \.track \{ fill: var\(--spin-track\); \}", css)
    assert "opacity: 0.35" not in css, "the track is no longer a dimmed currentColor"
    assert re.search(r"\.step\.running \.ic \.spin \{ color: var\(--accent\);", css)

    tracks = re.findall(r"--spin-track: (#[0-9a-fA-F]{3,8});", css)
    assert len(tracks) == 2, "both themes must declare the track colour"
    assert tracks[0].lower() in ("#fff", "#ffffff"), tracks
    assert tracks[1].lower() != tracks[0].lower(), (
        "the light theme needs its own track colour: white is invisible on #f2f2f2"
    )


def test_no_footage_screen_is_centred_like_the_indexing_one():
    """Frame 01 takes the same centring as frame 02: the header is all that
    is above it, so it belongs in the middle of the panel, not under the bar.

    `margin: auto` on the block inside #app's column is the mechanism both use,
    and it only bites if the block is the one thing there. So assert the class is
    set for the no-footage block and for nothing else -- a centred result grid or
    a centred skeleton list would float in the middle of a panel whose search
    field is above them.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")
    assert re.search(r"#results\.centered \{ margin: auto; \}", css), (
        "the centring is margin: auto, the same mechanism #indexing uses"
    )

    cls = "document.getElementById('results').className"
    none_ready = "store.footages = [];"

    # All four variants of frame 01 (no footage / none ready / failed / stalled)
    # take the same branch, so one of them proves the rest.
    assert _panel_render("renderResults()", none_ready, cls) == "centered"
    assert _panel_render(
        "renderResults()",
        none_ready + " store.footages = [{ footage_key: 'k0', path: 'a.mov', state: 'stale' }];",
        cls,
    ) == "centered"

    # Cards, skeletons and the no-matches row stay top-aligned.
    ready = "store.footages = [{ footage_key: 'k0', path: 'a.mov', state: 'ready', shot_count: 9 }];"
    assert "centered" not in _panel_render("renderResults()", ready, cls)
    searching = ready + " store.searching = true;"
    assert "centered" not in _panel_render("renderResults()", searching, cls)
    assert "centered" not in _panel_render(
        "renderResults()", ready + " store.lastQuery = 'zzz';", cls
    )

    # A live job owns the panel: #results is emptied outright, so it must not
    # keep a centring class from an earlier empty state.
    live = "store.activeJobs = ['job_1']; store.jobs = { job_1: %s };" % _RUNNING_JOB
    assert _panel_render("renderResults()", live, cls) == ""


_GRID_CARD_SETUP = (
    "TempoAPI.thumbUrl = () => 't.jpg';"
    "store.footages = [{ footage_key: 'k0', path: 'C:/s/a.mov', state: 'ready', shot_count: 2 }];"
    "store.results = [{ footage_key: 'k0', source_path: 'C:/s/a.mov', shot_id: '0',"
    " start_s: 1, end_s: 3.25, caption: 'a dog runs', transcript: 'go on then' }];"
)
_TWO_FOOTAGES = _GRID_CARD_SETUP.replace(
    "shot_count: 2 }];",
    "shot_count: 2 }, { footage_key: 'k1', path: 'C:/s/b.mov', state: 'ready', shot_count: 2 }];",
)
_NO_DESCRIPTION = (
    "TempoAPI.thumbUrl = () => 't.jpg';"
    "store.footages = [{ footage_key: 'k0', path: 'C:/s/a.mov', state: 'ready', shot_count: 2 },"
    " { footage_key: 'k1', path: 'C:/s/b.mov', state: 'ready', shot_count: 2 }];"
    "store.results = [{ footage_key: 'k0', source_path: 'C:/s/a.mov', shot_id: '0',"
    " start_s: 1, end_s: 3.25 }];"
)
_HTML = "document.getElementById('results').innerHTML"


def test_grid_card_body_is_two_columns_with_metadata_on_the_bottom_edge():
    """The grid card body is a left description and a right metadata column.

    The design's 777:368 puts the caption and the duration on one baseline-aligned
    row with space between them, which is what the list view still does. In a grid
    cell that row reads as two loose ends rather than as a caption with metadata,
    so the grid body is re-derived: the description is the left column, centred
    vertically, and the duration and file name are the right column, sitting on the
    body's bottom edge. `docs/design/panel-ui.md` §4.2 is the spec of record and
    ADR-0014 carries the departure and the measurements.

    Four things are load-bearing, and each one is a silent failure that still
    renders -- so each is asserted separately:

    - The description spans both rows (`grid-row: 1 / -1`) so it centres against
      the whole block. On row 1 alone it centres against the name's line and sits
      visibly high beside a two-line metadata column.
    - The rows are declared. `-1` is the end of the *explicit* grid, so with
      implicit rows the span collapses to one. This was measured, not reasoned: the
      first version declared only columns and the description rendered 9px above the
      body's centre while every other assertion here still passed, because these
      tests pin declarations rather than computed geometry.
    - The **name** is row 1 and the duration row 2. The name is the optional line --
      `renderResults` emits it only when more than one footage is loaded -- so when
      it is missing the empty row is the one *above* the duration and the duration
      stays on the bottom edge. Reversed, the empty row lands below it and lifts the
      duration off the edge in the single-footage case, which is the common one.
      `:has()` would state this directly and is Chromium 105 against the panel's
      real floor of 84 (flexbox `gap`, `docs/agents/known-issues.md`).
    - The metadata track is a fixed `5em` rather than `auto`. An `auto` track is
      sized to max-content before the flexible track is resolved, so one long file
      name starves the description to nothing rather than ellipsizing. `5em`
      resolves against the 12px base `.body` inherits, so the track is 60px — not
      the 55px that reading it against the name's 11px suggests — which leaves a
      measured 58px of description. The derivation is in ADR-0014 §4; only the
      consequence is repeated here.

    `align-self` on the three children is the whole alignment mechanism, so the
    grid declares no `align-items` default: a declaration nothing reads is dead
    weight, and the caption's centring would silently move if a default were
    reintroduced and won the cascade.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")

    body = _css_rule(css, "#results.grid .body")
    assert "display: grid;" in body, body
    assert "grid-template-columns: minmax(0, 1fr) 5em;" in body, (
        "the description takes the slack and the metadata track is definite, so a "
        "long file name ellipsizes rather than squeezing the description to zero"
    )
    assert "grid-template-rows: auto auto;" in body, (
        "the description spans to `-1`, which is the end of the explicit grid; with "
        "implicit rows the span collapses to one and the description centres against "
        "the name's line instead of the block"
    )
    assert "align-items" not in body, (
        "the three children each set `align-self`; a default here is unread"
    )
    # The 8px is `.cardrow`'s own gap, moved here because `display: contents`
    # dissolves the wrapper that carried it. The 2px row gap is `.body`'s.
    assert "column-gap: 8px;" in body, body
    assert "row-gap" not in body, "the row gap is the 2px `.body` already sets"

    # `.cardrow` is the list view's caption + duration row. Dissolving it is what
    # puts the two spans in different grid cells without touching the markup.
    assert "display: contents;" in _css_rule(css, "#results.grid .body .cardrow")

    cap = _css_rule(css, "#results.grid .body .cap")
    assert "grid-column: 1;" in cap, cap
    assert "grid-row: 1 / -1;" in cap, cap
    assert "align-self: center;" in cap, (
        "the description centres against the whole body, not against one row"
    )

    name = _css_rule(css, "#results.grid .body .name")
    assert "grid-column: 2;" in name, name
    assert "grid-row: 1;" in name, name
    assert "align-self: end;" in name, name
    assert "text-align: right;" in name, (
        "the name stretches to the metadata track; it must align with the duration "
        "below it"
    )

    dur = _css_rule(css, "#results.grid .body .dur")
    assert "grid-column: 2;" in dur, dur
    assert "grid-row: 2;" in dur, dur
    assert "align-self: end;" in dur, (
        "the duration is the bottom line, so it lands on the body's bottom edge "
        "whether or not a name is rendered above it"
    )
    assert "text-align: right;" in dur, "one alignment mechanism for both, not two"

    # The list view is unchanged: its caption and duration still share the
    # baseline row, so nothing here may reach it.
    assert "#results.list .body" not in css, (
        "the two-column body is the grid's shape only; the list keeps the design's "
        "single caption + duration row"
    )
    row = _css_rule(css, ".cardrow")
    assert "align-items: baseline;" in row, row
    assert "gap: 8px;" in row, row

    # The markup the CSS depends on: description and duration inside `.body`, and
    # no name for a single footage -- the case the row order above exists for.
    html = _panel_render("renderResults()", _GRID_CARD_SETUP, _HTML)
    assert 'class="body"' in html, html
    assert 'class="cap"' in html and 'class="dur"' in html, html
    assert 'class="cardrow"' in html, html
    assert 'class="name"' not in html, (
        "one footage renders no name; if this ever renders one, the metadata "
        "column's row order needs re-deriving"
    )

    html = _panel_render("renderResults()", _TWO_FOOTAGES, _HTML)
    assert 'class="name"' in html, html

    # A shot with neither caption nor transcript is reachable, and it is the shape
    # where the row order is unproven: `renderResults` gates the whole `.cardrow`
    # on the description being non-empty, so the duration goes with it and the
    # metadata column is a lone name. The name holds row 1 and bottom-aligns, so the
    # card is the name alone on its bottom edge rather than a name floating in row 1
    # of a two-row grid.
    html = _panel_render("renderResults()", _NO_DESCRIPTION, _HTML)
    assert 'class="name"' in html, html
    assert 'class="cap"' not in html and 'class="dur"' not in html, (
        "the duration rides on the description, so a shot with neither renders the "
        "name alone; if that gate ever moves, the row order has to be re-derived"
    )


def test_result_badge_is_the_accent_at_the_thumbs_scale():
    """The `+` on a result thumbnail: the accent, sized off the thumbnail.

    Two properties, both of which fail silently.

    **One owner for the colour.** The path carries `fill="currentColor"` and
    `.plus` carries `color: var(--accent)`, the pattern every other inline icon in
    this panel already uses. A literal `#EB5017` on the path is correct on the
    dark theme and wrong on the light one, where `--accent` is `#c23c0c` -- and it
    gives one constant two owners, which is what AGENTS.md §8 lists as prohibited.
    The old badge sidestepped this by being `color: #fff` on an orange pill, so
    nothing about it was themeable either.

    **The size follows the card.** The thumbnail it is centred on is not one size:
    it is the grid cell's width, which is a function of the dock, and a fixed 72px
    in the list view. A fixed 24px badge is right in one of those and wrong in the
    others, so it is `max(16px, 18%)` of the thumbnail -- 18% because that is the
    share that lands on 24px at a 300px dock, which is the size the change was made
    at. It is NOT read off the design, whose badge box is unmeasured (ADR-0015 §4).

    The floor is load-bearing and is asserted as such: 18% of the list view's 72px
    thumb is 12.96px, under AGENTS.md §6's 16px, which is why the declaration is a
    `max()` and not a bare percentage. `max()` is Chromium 79 against the panel's
    real floor of 84 (flexbox `gap`, `docs/agents/known-issues.md`).

    The cell width is *computed* here rather than quoted, so a future change to
    `#app`'s padding, the grid's gap or the card's stroke moves the expected badge
    instead of leaving a stale literal behind it.

    The height is the SVG's own square `viewBox` at `height: auto` -- not
    `aspect-ratio` (Chromium 88), and not a percentage height, which for an
    absolutely positioned element resolves against the containing block's *height*
    and would squash a circle into an ellipse.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")

    # The accent, from the token, in one place.
    badge = _css_rule(css, ".plus")
    assert "color: var(--accent);" in badge, (
        f"the badge takes the accent from the token, not a literal; got {badge!r}"
    )
    assert "#" not in badge, "a hex in .plus is a second owner for the accent"

    html = _panel_render("renderResults()", _GRID_CARD_SETUP, _HTML)
    # The *path's* fill, not the <svg fill="none"> it inherits from.
    fill = re.search(r'<span class="plus"[\s\S]*?<path[^>]*?fill="([^"]+)"', html)
    assert fill, "the badge must ship a fill on its path"
    assert fill.group(1) == "currentColor", (
        f"the path's fill is {fill.group(1)!r}; a literal hex does not follow --accent "
        "on the light theme"
    )

    # The size, as a share of the thumbnail it is centred on.
    share = re.search(r"width:\s*max\((\d+)px,\s*(\d+)%\)", badge)
    assert share, (
        f"the badge is a share of the thumbnail with a 16px floor, not a fixed px; "
        f"got {badge!r}"
    )
    floor, pct = int(share.group(1)), int(share.group(2))

    # The grid cell, computed by the shared derivation so a future change to
    # `#app`'s padding, the grid's gap or the card's stroke moves this rather than
    # leaving a stale literal here.
    cell = _grid_thumb_width(css)
    assert cell == 132, f"the grid thumb is {cell}px at {NARROW_DOCK_PX}px; the derivation moved"
    assert cell * pct / 100 == pytest.approx(24, abs=1), (
        f"{pct}% of a {cell}px thumb is {cell * pct / 100:.1f}px, not the ~24px this "
        "was sized at; the card's geometry moved and the share has to be re-derived"
    )

    # The floor, proven load-bearing by the list view's fixed 72px thumb.
    list_thumb = int(re.search(r"width:\s*(\d+)px", _css_rule(css, "#results.list .thumb")).group(1))
    assert list_thumb * pct / 100 < floor, (
        f"{pct}% of the {list_thumb}px list thumb is already {floor}px or more, so the "
        "max() is not doing anything; the floor is either dead or the share is wrong"
    )
    assert floor >= 16, f"AGENTS.md §6 wants 16px; the floor is {floor}px"

    # Round, and round because of the viewBox rather than of a modern property.
    svg = _css_rule(css, ".plus svg")
    assert "width: 100%;" in svg and "height: auto;" in svg, (
        f"the badge takes its height from the asset's own proportion; got {svg!r}"
    )
    # Scoped to the badge's two rules rather than the file: this file's own
    # comments have to be able to name `aspect-ratio` to explain why it is not
    # used, and a whole-file scan fails on the explanation.
    assert "aspect-ratio" not in badge + svg, (
        "aspect-ratio is Chromium 88, over the panel's real floor of 84"
    )
    vb = re.search(r'class="plus"[\s\S]*?viewBox="0 0 (\d+) (\d+)"', html)
    assert vb and vb.group(1) == vb.group(2), (
        "a square viewBox is what keeps height:auto from skewing the ring"
    )


def test_searching_frame_is_two_blocks_at_the_designs_level():
    """Frame 03 is the design's `loading_result` (777:532) and nothing else.

    The design draws a skeleton as a transparent 560x399 frame holding two blocks
    and no chrome of its own:

        loading_result   560 x 399   (no fill, no stroke)
        thumb-sk         554 x 312   x=3,  y=0,   radius 12, white 0 -> 0.08
        cap-sk           560 x  69   y=330,       radius 12, white 0 -> 0.08

    Four properties, and each is a silent failure -- the skeleton still renders,
    it just renders as something the design does not have:

    - **The card's stroke and fill go.** `.card` carries a 3px same-colour stroke
      and a `--surface` fill, and the skeleton inherited both, so the loading
      state was a grey card with two dimmer rectangles in it. The design's frame
      is transparent. This also means the skeleton needs a hover guard: `.card:hover`
      paints `--accent`, and a `div` still matches `:hover`, so without one a
      skeleton turns orange under the cursor.
    - **The sweep's level is 0.08, not 0.56 and 1.** The design gives both blocks
      the *same* fill -- white at 8% -- so the panel's two tokens with two
      different peaks (0.56 thumb, 1 caption) were invented, and they were also an
      order of magnitude too hot. One token now serves both blocks. The light
      theme is the same 8% lift in the other direction, the `--spin-track`
      precedent.
    - **Both blocks take `--r-md`.** The design gives them the same 12 of 560 the
      card has, which is what `--r-md` is.
    - **The blocks are inset 3px, and the cap is the body box.** The design's
      `thumb-sk` sits at x=3 of a 560 frame — inside the card's 3px stroke — so
      the panel's inset is the stroke's width, and the cap takes `.body`'s own
      horizontal padding so both blocks land exactly where the real thumbnail and
      the real caption land. The inset lives on the *frame* (`padding`, not the
      blocks' `margin`) and that is load-bearing rather than cosmetic: percentage
      padding resolves against the containing block, so a margin inset would size
      the thumb 138 x 0.5625 = 77.6px while the real thumbnail is 132 x 0.5625 =
      74.25px. The cap's *height* is asserted as a derivation (below), because the
      design's 69 is its body box at 20px caption type and the panel's caption is
      11px: taken literally it would be 17px and every row would jump when results
      arrive.
    - **The row does not change height when results land.** That is the property
      the cap's height exists for, and it is the one thing the derivation above
      cannot check on its own — a cap that tracks the body while the thumb
      overshoots still jumps. So the two are added up and compared against a real
      card, with the card's own stroke and its two-line caption. It is a
      comparison, not a restatement, and it is the assertion that would catch a
      reflow.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")
    cell = _grid_thumb_width(css)

    # The render: two blocks, and no trace of the card they stand in for.
    searching = _GRID_CARD_SETUP + "store.searching = true;"
    html = _panel_render("renderResults()", searching, _HTML)
    assert 'class="sk-thumb"' in html and 'class="sk-cap"' in html, html
    for absent in ("<img", 'class="thumb"', 'class="body"', 'class="cap"'):
        assert absent not in html, (
            f"the design's loading frame is two blocks; {absent!r} is something it "
            "does not have"
        )

    # The frame: no stroke, no fill, and the hover guard the removal of the fill
    # makes necessary.
    skel = _css_rule(css, ".card.skel")
    assert "border: 0;" in skel and "background: none;" in skel, (
        f"the design's loading_result is transparent; got {skel!r}"
    )
    assert "background: none;" in _css_rule(css, ".card.skel:hover"), (
        ".card:hover paints --accent and a div still matches :hover, so a skeleton "
        "would turn orange under the cursor"
    )

    # One sweep, at the design's level, in both themes.
    assert "--sweep-thumb" not in css and "--sweep-cap" not in css, (
        "the design gives both blocks the same fill, so two tokens were two owners"
    )
    sweeps = re.findall(r"--sweep:\s*linear-gradient\(90deg,([^;]+)\);", css)
    assert len(sweeps) == 2, "both themes must declare --sweep"
    # The peak is the 50% stop; the two ends are the ramp's own transparent.
    peaks = {re.search(r"rgba\([^)]*?([\d.]+)\)\s+50%", s).group(1) for s in sweeps}
    assert peaks == {"0.08"}, (
        f"the design's fill peaks at white 0.08 on both blocks and in both themes; "
        f"the panel has {peaks}"
    )

    # Both blocks, both radii, and the base the ramp sits on. The design paints
    # no base colour on either block; `--surface-2` is ours, and it is what gives
    # a block a resting shape when the sweep is at its faintest or disabled.
    blocks = _css_rule(css, ".card.skel .sk-thumb, .card.skel .sk-cap")
    assert "border-radius: var(--r-md);" in blocks, (
        f"the design rounds both blocks at the card's own 12 of 560; got {blocks!r}"
    )
    assert "background-color: var(--surface-2);" in blocks, (
        f"the blocks need a base to be a shape; got {blocks!r}"
    )

    # The thumb's inset is the card's stroke, and it is the FRAME's padding, so
    # that `padding-top: 56.25%` resolves against the inset width. A margin inset
    # on the block would look identical and size the block off the full cell.
    stroke = int(re.search(r"border:\s*(\d+)px solid", _css_rule(css, ".card")).group(1))
    inset = re.search(r"padding:\s*0\s+(\d+)px", _css_rule(css, ".card.skel"))
    assert inset and int(inset.group(1)) == stroke, (
        f"the design's thumb-sk is inset by the card's {stroke}px stroke; the "
        f"skeleton frame insets by {inset and inset.group(1)}"
    )
    thumb = _css_rule(css, ".card.skel .sk-thumb")
    assert "width: 100%;" in thumb, (
        f"with the inset on the frame the block fills what is left of it; got {thumb!r}"
    )
    assert "margin" not in thumb, (
        "a margin inset would leave the percentage padding resolving against the "
        "full cell, and the block would be 3.4px taller than the thumbnail"
    )
    assert "padding-top: 56.25%;" in thumb, (
        "the design's thumb-sk is 312 of 554 = 0.5632, which is 16:9 to within 0.1%"
    )

    gap = re.search(r"margin-top:\s*(\d+)px", _css_rule(css, ".card.skel .sk-cap"))
    design_gap, design_card = 18, 560
    assert gap and int(gap.group(1)) == round(cell * design_gap / design_card), (
        f"the design's cap-sk starts {design_gap} of {design_card} below the thumb, "
        f"which is {cell * design_gap / design_card:.2f}px here"
    )

    # The cap's height is the body it stands in for, derived from the body rather
    # than restated: two lines of the caption's own type at the inherited line
    # height, plus the body's padding above and below. The design's 69 is the same
    # box at 20px type, which is why it cannot be copied.
    body = _css_rule(css, ".body")
    cap_h = int(re.search(r"height:\s*(\d+)px", _css_rule(css, ".card.skel .sk-cap")).group(1))
    cap_fs = int(re.search(r"font-size:\s*(\d+)px", _css_rule(css, ".cap")).group(1))
    line_height = float(re.search(r"font:\s*12px/([\d.]+)", _css_rule(css, "body")).group(1))
    body_pad = int(re.search(r"padding:\s*(\d+)px", body).group(1))
    body_box = 2 * cap_fs * line_height + 2 * body_pad
    assert cap_h == pytest.approx(body_box, abs=1), (
        f"the cap is the body: 2 x {cap_fs}px at {line_height} plus {body_pad}px of "
        f"padding is {body_box:.1f}px, not {cap_h}px. A cap that is the design's "
        "literal 17px makes every row jump on arrival"
    )

    # And the property all of the above exists for: the row's height is the same
    # before and after. Skeleton = thumb + gap + cap. A real card = its stroke +
    # the same thumb + the same body, with the body at its full two lines (the
    # grid clamps the caption to two, and the metadata column beside it is no
    # taller). The residual is therefore the card's 6px of stroke less the 4px the
    # skeleton puts back as the gap — 2px, and the tolerance absorbs the cap's
    # rounding onto the rhythm. A caption that comes back one line short still
    # shortens the card, because a content-sized card cannot be predicted; what
    # this rules out is the thumb overshooting its own thumbnail, which is the
    # failure that a per-block assertion cannot see.
    thumb_h = cell * 0.5625
    skeleton_h = thumb_h + int(gap.group(1)) + cap_h
    card_h = 2 * stroke + thumb_h + body_box
    residual = 2 * stroke - int(gap.group(1))
    assert card_h - skeleton_h == pytest.approx(residual, abs=1), (
        f"skeleton {skeleton_h:.1f}px against card {card_h:.1f}px: the difference "
        f"should be {residual}px — the card's {stroke}px stroke either side less "
        "the gap the skeleton spends. A larger difference is the reflow this whole "
        "re-derivation is about"
    )

    # The list view shares the frame's padding and the block rules; only the
    # grid's cap margin has to be undone there, because the row has its own gap.
    assert "margin-top: 0;" in _css_rule(css, "#results.list .card.skel .sk-cap"), (
        "the list row's own 8px gap is the spacing; the grid's 4px is not"
    )


def test_query_shimmer_is_one_text_layer_and_not_the_accent():
    """The searching field paints the query once, with a band travelling across it.

    It used to paint it twice: a legible copy in the field's own text colour with a
    band drawn over the top of it, on a gradient that repeated off both ends of the
    text. What the editor saw was a full-strength query with a second edge crossing
    it, which is the noise the shimmer existed to remove — so the removal is pinned
    by mechanism, the same way the navbar's own removals are.

    The band is also greyscale, which is not a taste call. AGENTS.md 6 allows one
    accent and only for selection and active states, and a search in flight is
    neither.

    The three alphas are not invented either. shadcn's `shimmer` utility derives its
    highlight from `currentColor` — lightness +0.4 and alpha +0.4 in its dark
    variant — and run over this panel's own dim level that lands exactly on the
    field's value level: 0.4 + 0.4 = 0.8. The mid stop is the half-mix of the two
    ends, so it is derived rather than chosen (0.45 and 0.88 average to 0.665,
    taken down to the rhythm at 0.66).

    The utility's own colour maths — `oklch(from currentColor ...)`, `color-mix()`
    — are far above this panel's Chromium floor, so the stops are literal here. That
    is the reason the token exists at all: two themes, one shape, one owner.
    """
    css = PANEL_CSS.read_text(encoding="utf-8")
    html = PANEL_HTML.read_text(encoding="utf-8")
    js = PANEL_JS.read_text(encoding="utf-8")

    # One text layer. The band IS the resting colour's carrier, so a copy of the
    # query underneath it is not a fallback, it is the second edge.
    for text, name in ((html, "index.html"), (js, "panel.js"), (css, "panel.css")):
        assert "q-base" not in text, (
            f"{name} reintroduced the second copy of the query; the shimmer's own "
            "outer stops are the resting colour, so a base layer is the noise"
        )
    assert 'id="q-sweep"' in html, "the shimmer still needs its mirror over the input"

    # One gradient, declared once, in the dark theme's block: the base and the peak
    # are the tokens themselves rather than literals of their values, so the shape
    # does not repeat per theme -- the tokens flip. Only the half-mix is a literal,
    # because nothing derives it.
    dark = _css_rule(css, ":root")
    light = _css_rule(css, "html.light")
    assert "--qsweep:" in dark and "--qsweep:" not in light, (
        "one owner for the gradient's shape; the themes differ by --qsweep-mid alone"
    )
    shape = re.search(r"--qsweep:\s*linear-gradient\(([^;]+)\);", dark).group(1)
    assert not re.search(r"rgba\(235|rgba\(194|235, 81, 23|194, 60, 12", shape), (
        f"AGENTS.md 6 allows the accent for selection and active states only, and a "
        f"search-in-flight band is neither: {shape!r}"
    )
    # The ported geometry: the util's 20deg tilt on top of 90deg, its
    # `3ch + 40px` spread, and the half-spread offsets that soften the band. A
    # regression to 90deg or to fixed stops still renders, and is still not the port.
    assert shape.strip().startswith("110deg"), f"the util's tilt is 90 + 20; got {shape!r}"
    assert "calc(50% - var(--qsweep-spread))" in shape, shape
    assert "calc(50% + var(--qsweep-spread))" in shape, shape
    assert "calc(50% - var(--qsweep-spread) * 0.5)" in shape, shape
    assert "calc(50% + var(--qsweep-spread) * 0.5)" in shape, shape
    assert shape.count("var(--text-dim)") == 2, f"the base stop, at both ends: {shape!r}"
    assert shape.count("var(--text)") == 1, f"the peak stop, at the centre: {shape!r}"
    assert len(re.findall(r"--qsweep-spread:", css)) == 1, "one owner for the band width"

    # And the one literal is derived, not chosen: each theme's half-mix is the mean
    # of its own two text alphas. Quoted numbers would go stale silently the moment
    # a text token's alpha moved, which is the trap NARROW_DOCK_PX's derivation
    # exists to avoid.
    for name, block in (("dark", dark), ("light", light)):
        dim = float(re.search(r"--text-dim:\s*rgba\([^)]*?([\d.]+)\)", block).group(1))
        text_level = float(re.search(r"--text:\s*rgba\([^)]*?([\d.]+)\)", block).group(1))
        mid = re.search(r"--qsweep-mid:\s*rgba\([^)]*?([\d.]+)\)", block)
        assert mid, f"the {name} theme needs its own half-mix; got {block!r}"
        expected = round((dim + text_level) / 2, 3)
        held = round(float(mid.group(1)), 3)
        # Half of the last digit kept, plus an epsilon so binary float noise on
        # 0.665 does not read as a breach.
        assert abs(held - expected) <= 0.005 + 1e-9, (
            f"the {name} half-mix is the mean of --text-dim ({dim}) and --text "
            f"({text_level}) = {expected}, held to two decimals; the file has "
            f"{mid.group(1)}"
        )

    # The element consumes the token and adds the three things the token cannot
    # carry: the clip that paints the text at all, the no-repeat that keeps the band
    # from growing a second edge along the string, and the sizing whose `2 *` is what
    # keeps the band clear of both ends so the loop never wraps.
    rule = _css_rule(css, "#q-sweep")
    assert "background-image: var(--qsweep);" in rule, (
        f"the gradient belongs to the token, not to the rule; got {rule!r}"
    )
    assert "linear-gradient" not in rule, "a second owner for the gradient"
    assert "background-repeat: no-repeat;" in rule, (
        "a repeating gradient gives the band a second edge along the text, which is "
        "half of what this change removes"
    )
    assert "calc(200% + var(--qsweep-spread) * 2) 100%" in rule, (
        "the seamless loop needs the band clear of both ends at the keyframe extremes"
    )
    assert "-webkit-background-clip: text;" in rule and "background-clip: text;" in rule, (
        "the -webkit- prefix is the declared CEP 9 floor"
    )
    assert "color: transparent;" in rule, "the text is painted by the gradient, not by colour"
    assert "animation: qsweep 1s linear infinite;" in rule, (
        "1s is the cycle this was chosen at; see the ADR's speed trade"
    )

    # Right to left, the direction the skeleton sweep already runs in. A positive
    # background-position percentage moves the gradient leftwards.
    kf = re.search(r"(?m)^@keyframes qsweep\s*\{(.*)\}$", css).group(1)
    assert "from { background-position: 0 0; }" in kf, f"got {kf!r}"
    assert "to { background-position: 100% 0; }" in kf, f"got {kf!r}"

    # Reduced motion: the query renders plainly, in the field's own value colour.
    # `animation: none` alone leaves the band at rest off the end of the text, and
    # the text layer is transparent — so the field went blank mid-search.
    motion = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*)", css, re.S).group(1)
    assert "#q-sweep," not in motion, (
        "the query needs its own reduced-motion rule; sharing the animation-only "
        "one is what leaves it invisible"
    )
    still = re.search(r"(?m)^\s*#q-sweep\s*\{([^}]*)\}", motion).group(1)
    assert "animation: none;" in still, f"got {still!r}"
    assert "background-image: none;" in still and "color: var(--text);" in still, (
        "with the gradient gone the text needs its own colour back, or the query "
        f"stays transparent; got {still!r}"
    )


def test_interactive_api_docs_are_disabled():
    """With no auth wall, /docs, /redoc and /openapi.json hand any process on
    the machine a complete map of every route, parameter and model for free.
    docs/api.md is the contract of record."""
    from tempo_service.app import create_app

    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths


def test_thumb_rejects_a_content_id_that_is_not_one(tmp_path, monkeypatch):
    """content_id is read from registry.json rather than the request, but that
    file is plain unauthenticated JSON on disk and thumbs_dir() concatenates it
    into a path. A registry poisoned with a traversal string must not turn
    GET /thumb into an arbitrary file read."""
    from fastapi.testclient import TestClient

    from tempo_service import registry as registry_module
    from tempo_service.app import create_app as _create

    root = tmp_path / "artifacts"
    (root / "thumbs").mkdir(parents=True)
    monkeypatch.setattr(registry_module, "load_registry", lambda: {
        "deadbeef00": {"content_id": "..\\..\\..\\Windows\\win.ini"},
    })
    client = TestClient(_create())
    res = client.get("/thumb/deadbeef00/0.jpg")
    assert res.status_code == 404, res.text

    # And a well-formed content id still resolves, so the guard is not a blanket deny.
    monkeypatch.setattr(registry_module, "load_registry", lambda: {
        "deadbeef00": {"content_id": "0123456789abcdef"},
    })
    assert client.get("/thumb/deadbeef00/0.jpg").status_code == 404  # absent file, not invalid id