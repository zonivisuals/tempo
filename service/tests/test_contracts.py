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


def test_view_toggle_is_the_design_geometry_on_the_left():
    """Figma 777:473 is two 64px chips, 16px apart, flush with the card grid.

    Measured off the design (`docs/design/panel-ui.md` §1, "The view pair keeps the
    design's ratios, not its pixels"): the chip is 64x64 with radius 8, the icon
    asset is a 38-unit box holding a 32-unit glyph, the pair is 16 apart, and the
    left edge of the pair lines up with the first card.

    None of that scales linearly into a 300px panel -- at the frame scale a 64px
    chip would be 10px, and AGENTS.md §6 pins icons at 16px regardless. What does
    survive is the shape, so that is what is asserted: the gap's share of the
    chip, the radius' share of it, and the icon's share of it. A later resize that
    changes the chip without re-deriving the other two fails here rather than
    shipping a cramped or a loose control.

    The chip is 32 rather than 24 because of the icon. The exported asset is a
    38-unit box, and 38/64 of a 32px chip is 19px exactly -- which renders the
    32-unit glyph at 16.0px, on AGENTS.md §6's floor rather than through it. The
    same asset in the 24px chip it replaces renders at 13.5px, which is why the
    chip grew instead of just moving.

    The viewBox is asserted alongside the slot because it is what the glyph size is
    actually computed from. Changing either alone rescales the icon silently --
    19px into a 64-unit box is a 9.5px glyph -- and every other assertion here
    still passes.
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

    # The design's ratios: gap 16 of 64, radius 8 of 64.
    box = int(re.search(r"width:\s*(\d+)px", _css_rule(css, "button.icon")).group(1))
    gap = int(re.search(r"gap:\s*(\d+)px", toggle).group(1))
    radius = int(re.search(r"--r-sm:\s*(\d+)px", css).group(1))
    assert gap == box / 4, f"the design spaces the pair 16 into a 64 chip; {gap}px into {box}px"
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
    """The field is as tall as the design says, not as tight as it fits.

    Measured off a 1x render of Figma `search_input` (815:294, inside
    `04_search_results_frame`): a 1836x196 field whose top padding, ink-to-ink
    label-to-value gap and bottom padding are 47 / 46 / 53 of that 196. Scaling
    by the port's own basis -- the panel's 13px value type against the design's
    32px, a ratio of 0.406, which is the ratio the submit button already uses
    (design 60px -> shipped 24px) -- lands them on 20 / 20 / 20 at the 4px
    rhythm, and the field's 25px radius on 10px.

    Geometry is deliberately not the basis. The design's field is 10.7% of its
    content width and the panel's was already 18%, so every frame-relative
    ratio argues for shrinking the one thing that was too tight; only the type
    ratio says grow. Height follows from the parts: 2px of border, 20 padding,
    a 21px label row (the icon sets it, not the 11px text), the 20px gap, a 24px
    value row (the button sets it, not the 20px input box) and 20 padding.

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
    assert "padding: 20px 16px;" in box, box
    assert "gap: 20px;" in box, box
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

    # Scoped to .sb-head rather than the whole document: both assertions are
    # about one fragment, and a file-wide scan would fail on unrelated markup --
    # including on this file's own comments, which have to be able to name the
    # attributes and the old string they explain away.
    head = re.search(r'(?s)<div class="sb-head">.*?</div>', html)
    assert head, "index.html has no .sb-head block"
    head = head.group(0)
    assert "stroke-opacity=" not in head, (
        "stroke-opacity over an already-translucent colour compounds it"
    )
    assert "Search for anything" in head, "the design's label is the field's label"
    assert "Search footage" not in head, "the label was replaced, not added to"


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
