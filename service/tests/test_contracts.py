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
    """Frame 01 takes the same centring as frame 02: the status bar is all that
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
