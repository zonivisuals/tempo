/* preview-harness.js — stubs the two things panel.js talks to, so the real
 * panel.js and the real panel.css can run in a browser with no AE and no
 * sidecar. Nothing here ships.
 *
 * CSInterface is stubbed to answer nothing: evalScript returns null, which is
 * exactly what panel.js sees when the host bridge is missing, so tempoListFootage
 * yields [] and the fixtures below decide everything else.
 *
 * TempoAPI serves per-scenario fixtures. The indexing fixture ADVANCES on every
 * poll, so the step slide, the FLIP reorder and the spinner are all live rather
 * than frozen. */

(function () {
  "use strict";

  /* Any uncaught error — from the harness, from panel.js, or from a click
   * handler — is written onto the page. A silently broken preview is worse than
   * a loud one. */
  function trap(what) {
    const box = document.getElementById("err");
    if (!box) { console.error(what); return; }
    box.hidden = false;
    box.textContent = (box.textContent ? box.textContent + "\n" : "") + what;
  }
  window.addEventListener("error", function (e) {
    trap((e.message || "error") + (e.filename ? "\n  at " + e.filename + ":" + e.lineno : ""));
  });
  window.addEventListener("unhandledrejection", function (e) {
    trap("unhandled rejection: " + ((e.reason && e.reason.message) || e.reason));
  });

  const STAGES = ["upload", "shots", "visual", "transcribe", "ocr", "captions", "text", "index"];
  const TOTALS = {
    upload: 412_000_000, shots: 1_152_000, visual: 2_949, transcribe: 3842,
    ocr: 983, captions: 120, text: 4, index: 983,
  };
  const DUR = {
    upload: 0.1, shots: 0.25, visual: 0.4, transcribe: 0.5, ocr: 0.15,
    captions: 0.35, text: 0.05, index: 0.05,
  };

  /* ---- CSInterface stub ---- */
  window.CSInterface = function () {};
  window.CSInterface.prototype.evalScript = function (_expr, cb) { cb(null); };
  window.CSInterface.prototype.getHostEnvironment = function () {
    return JSON.stringify({ appSkinInfo: { color: { red: 35, green: 35, blue: 35 } } });
  };

  /* ---- fixtures ---- */
  const IMG = "data:image/svg+xml," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180">' +
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
    '<stop offset="0" stop-color="#5b6b8c"/><stop offset="1" stop-color="#c98a5b"/>' +
    "</linearGradient></defs>" +
    '<rect width="320" height="180" fill="url(#g)"/>' +
    '<circle cx="230" cy="70" r="34" fill="#f2d9b5" opacity="0.85"/>' +
    '<rect y="132" width="320" height="48" fill="#2b3348" opacity="0.8"/></svg>');

  const CAPTIONS = [
    "angry girl with black hair throwing her katana on the air",
    "close up of a hand gripping a katana handle, shallow focus",
    "wide shot of a ruined street at dusk, smoke drifting across the frame",
    "a character running through tall grass, backlit by low sun",
    "two figures standing on a rooftop, city lights behind them",
    "over the shoulder shot, a blade drawn and held low",
    "a crowd scattering as debris falls from a collapsing wall",
    "still water reflecting a burning building at night",
    "a lantern-lit alley with rain falling through the frame",
  ];
  const TRANSCRIPTS = [
    "You can't just walk in there, not after what happened.",
    "I said we go now. We don't have until morning.",
    "Then let them stop us.",
    "There's no one left down there.",
    "You sound like your father.",
    "Maybe I am.",
  ];

  function makeFootage(states) {
    return states.map((s, i) => ({
      footage_key: "k" + i, path: "C:/rushes/2026-10-03/" + CAPTIONS[i % 9].slice(0, 14)
        .replace(/\s/g, "-") + "-take" + (i + 1) + ".mov",
      content_id: "c" + i, shot_count: s === "ready" ? 983 : null,
      duration_s: s === "ready" ? 642.5 : null, indexed_at: s === "ready" ? "2026-10-03T12:00:00Z" : null,
      state: s, reused: i === 2 && s === "ready",
    }));
  }

  function makeResults(n, withCaptions) {
    const out = [];
    for (let i = 0; i < n; i++) {
      const start = 12.4 + i * 9.13;
      out.push({
        footage_key: "k" + (i % 3), content_id: "c" + (i % 3), shot_id: i,
        scene_id: i, source_path: "C:/rushes/2026-10-03/take-" + (1 + (i % 3)) + ".mov",
        start_s: start, end_s: start + (i % 4 === 0 ? 4.1 : 9.2),
        score: 0.81 - i * 0.03,
        contributions: {}, raw_cos: {},
        transcript: TRANSCRIPTS[i % TRANSCRIPTS.length],
        caption: withCaptions ? CAPTIONS[i % CAPTIONS.length] : "",
        entities: [], emotions: [],
      });
    }
    return out;
  }

  /* ---- scenario state ---- */
  let scenario = "empty";
  let tick = 0;          // advances the indexing fixture
  let results = [];
  let withCaptions = true;

  function advanceStages() {
    // Walk the pipeline: ~2 ticks per stage, so a full run takes ~4s.
    const per = 2;
    const at = Math.min(STAGES.length * per, Math.floor(tick / 2));
    const done = at;
    const running = at < STAGES.length ? STAGES[at] : null;
    const stages = STAGES.map((name, i) => {
      let state = "pending", d = 0;
      if (i < done) { state = "done"; d = TOTALS[name]; }
      else if (name === running) {
        state = "running";
        const f = Math.min(1, ((tick % per) + 0.5) / per);
        d = Math.round(TOTALS[name] * f);
      }
      return { name: name, state: state, done: d, total: TOTALS[name] };
    });
    return stages;
  }

  function jobPayload() {
    const stages = advanceStages();
    const live = stages.some((s) => s.state === "running");
    const at = STAGES.findIndex((s, i) => stages[i].state === "running");
    return {
      job_id: "job-fixture",
      footage_key: "k0",
      state: at < 0 ? "done" : (at === 0 && tick < 2 ? "queued" : "running"),
      reused: false,
      stages: stages,
      error: null,
      progress: { stage: at, total: STAGES.length },
      // Reused-job variant: every stage done with total 0, which is what the
      // panel must render as a tick and no number.
      cache_variant: scenario === "reused",
    };
  }

  const FIX = {
    empty: { footages: [], job: null, err: null, results: 0, captions: true },
    indexing: { footages: ["indexing"], job: "live", err: null, results: 0, captions: true },
    queued: { footages: ["uploading"], job: "queued", err: null, results: 0, captions: true },
    cached: { footages: ["indexing"], job: "cached", err: null, results: 0, captions: true },
    failed: { footages: ["error"], job: "failed", err: null, results: 0, captions: true },
    searching: { footages: ["ready"], job: null, err: null, results: 9, captions: true, search: true },
    results: { footages: ["ready", "ready", "ready"], job: null, err: null, results: 9, captions: true },
    list: { footages: ["ready", "ready", "ready"], job: null, err: null, results: 9, captions: true },
    nocaption: { footages: ["ready", "ready", "ready"], job: null, err: null, results: 9, captions: false },
    offline: { footages: ["ready"], job: null, err: "SERVICE_OFFLINE", results: 0, captions: true },
    asleep: { footages: ["ready"], job: null, err: "BACKEND_ASLEEP", results: 0, captions: true },
    quota: { footages: ["ready", "ready", "ready", "ready"], job: null,
      err: "QUOTA_EXCEEDED", results: 0, captions: true },
    emptyresults: { footages: ["ready"], job: null, err: null, results: 0, captions: true, searched: true },
  };

  const ok = (body) => ({ ok: true, status: 200, body: body });
  const fail = (status, code, message) => ({
    ok: false, status: status, body: { error: { code: code, message: message } },
  });

  window.TempoAPI = {
    base: function () { return "preview"; },
    health: function () {
      return ok({
        status: "ok", artifact_root: "preview",
        backend: { reachable: true, gpu: true, tunnel: "up", signature: "preview" },
      });
    },
    footage: function () { return ok(makeFootage(FIX[scenario].footages)); },
    sync: function () {
      const f = FIX[scenario];
      return ok({
        added: [], changed: [], removed: [], unchanged: [], pending: [],
        jobs: f.job ? ["job-fixture"] : [], uploads: f.job ? ["job-fixture"] : [],
      });
    },
    job: function () {
      const kind = FIX[scenario].job;
      if (kind === "live") return ok(jobPayload());
      if (kind === "queued") {
        return ok({ job_id: "job-fixture", footage_key: "k0", state: "queued", reused: false,
          stages: [], error: null });
      }
      if (kind === "cached") {
        // A cache-served job: every stage done, every total 0. The panel must
        // show a tick per stage and no number anywhere.
        return ok({
          job_id: "job-fixture", footage_key: "k0", state: "done", reused: true,
          stages: STAGES.map((n) => ({ name: n, state: "done", done: 0, total: 0 })),
          error: null,
        });
      }
      if (kind === "failed") {
        return ok({
          job_id: "job-fixture", footage_key: "k0", state: "error", reused: false,
          stages: STAGES.slice(0, 4).map((n, i) => ({
            name: n, state: i < 3 ? "done" : "error", done: TOTALS[n], total: TOTALS[n],
          })),
          error: "engine job 7f3c: BACKEND_UNREACHABLE <urlopen error [Errno 111] "
            + "Connection refused> after 5 attempts\n"
            + '  File "/app/engine/tempo_engine/pipeline.py", line 85, in build\n'
            + "    raise RuntimeError(\"shots stage needs the source video; upload it again\")",
        });
      }
      return ok({ job_id: "job-fixture", footage_key: "k0", state: "done", reused: false,
        stages: STAGES.map((n) => ({ name: n, state: "done", done: TOTALS[n], total: TOTALS[n] })),
        error: null });
    },
    retry: function () { return ok({ job_id: "job-fixture2" }); },
    retryFootage: function () { return ok({ job_id: "job-fixture3" }); },
    search: function () {
      const f = FIX[scenario];
      if (scenario === "offline") return { ok: false, status: 0, body: null, offline: true };
      if (scenario === "asleep") return fail(502, "BACKEND_ASLEEP", "engine search failed");
      // Delay so the skeleton state is visible while you look at it.
      return new Promise(function (res) {
        setTimeout(function () { res(ok({ results: makeResults(f.results, f.captions) })); }, 2600);
      });
    },
    hostJs: function () { return { ok: false, status: 404, text: "" }; },
    thumbUrl: function (key, id) { return IMG + "#" + key + "-" + id; },
  };

  /* ---- driving the panel from the outside ----
   * panel.js is a classic script, so its top-level bindings are reachable from
   * another classic script. That is how this harness sets up a state without
   * duplicating panel.js logic — the preview exercises the shipped code. */
  const SCENARIOS = [
    { id: "empty", label: "01 · no footage" },
    { id: "indexing", label: "02 · indexing (live)" },
    { id: "queued", label: "02b · queued, tunnel warming" },
    { id: "cached", label: "02c · reused job (all total=0)" },
    { id: "failed", label: "02d · indexing failed + Retry" },
    { id: "searching", label: "03 · searching (skeletons)" },
    { id: "results", label: "04 · results (grid)" },
    { id: "nocaption", label: "04b · transcript instead of caption" },
    { id: "list", label: "04c · results (list view)" },
    { id: "emptyresults", label: "04d · no matches" },
    { id: "offline", label: "error · service offline" },
    { id: "asleep", label: "error · engine asleep" },
    { id: "quota", label: "error · quota exceeded" },
  ];

  /* Screens are deep-linkable: preview.html#indexing opens that scenario
   * directly. Used by the review checklist and by the headless dump in
   * service/tests/test_contracts.py. */
  function fromHash() {
    const id = String(location.hash || "").replace(/^#/, "");
    return FIX[id] && SCENARIOS.some((s) => s.id === id) ? id : "empty";
  }

  function ready() {
    const rail = document.getElementById("rail");
    const widthInput = document.getElementById("w");
    const themeInput = document.getElementById("theme");
    const captionInput = document.getElementById("captions");
    const panel = document.getElementById("app");

    /* Re-seed the store from the fixtures and hand rendering to panel.js. The
     * job payload is fetched through the stub so the step rows are built by the
     * shipped stepOrder()/stepNumber(), not by anything here. */
    function paint() {
      const errBox = document.getElementById("err");
      const f = FIX[scenario];
      if (!f) {
        // A missing fixture used to throw inside the click handler and look like
        // "the button does nothing". Say so on the page instead.
        errBox.hidden = false;
        errBox.textContent = 'No fixture for scenario "' + scenario + '". '
          + "Add it to FIX in preview-harness.js.";
        return;
      }
      errBox.hidden = true;
      store.footages = makeFootage(f.footages);
      store.jobs = f.job ? { "job-fixture": TempoAPI.job().body } : {};
      store.activeJobs = f.job ? ["job-fixture"] : [];
      store.results = makeResults(f.results, captionInput.checked && f.captions !== false);
      store.searching = !!f.search;
      store.inserting = -1;
      store.error = f.err ? { code: f.err, message: errorMessage(f.err) } : null;
      store.index = { open: !!f.job, manual: false };
      store.lastQuery = (f.searched || f.search) ? "mikasa fighting with katana" : "";
      const q = document.getElementById("q");
      // Do not fight the reviewer: whatever is typed in the box wins.
      if (store.lastQuery && document.activeElement !== q) q.value = store.lastQuery;
      // The list screen is the only one that forces the view; everything else
      // shows the grid, which is the shipped default.
      store.view = scenario === "list" ? "list" : "grid";
      document.querySelector("#panelwrap .caption").textContent = captionFor(scenario);
      render();
      panel.scrollTop = 0;
      window.scrollTo(0, 0);
      rail.querySelectorAll("button[data-s]").forEach(function (b) {
        b.setAttribute("aria-pressed", b.dataset.s === scenario ? "true" : "false");
      });
    }

    function errorMessage(code) {
      if (code === "SERVICE_OFFLINE") return "service offline";
      if (code === "BACKEND_ASLEEP") return "engine search failed";
      if (code === "QUOTA_EXCEEDED") return "plan 'free' allows 3 footage; project holds 4";
      return "status 500";
    }
    function captionFor(id) {
      const s = SCENARIOS.find(function (x) { return x.id === id; });
      return s ? s.label : id;
    }

    for (const s of SCENARIOS) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.s = s.id;
      b.textContent = s.label;
      b.addEventListener("click", function () {
        scenario = s.id;
        tick = 0;
        try { paint(); } catch (e) { trap(s.id + ": " + e.message + "\n" + e.stack); }
      });
      rail.querySelector("#scenarios").appendChild(b);
    }

    widthInput.addEventListener("input", function () { panel.style.width = widthInput.value + "px"; });
    themeInput.addEventListener("change", function () { panel.classList.toggle("light", themeInput.checked); });
    captionInput.addEventListener("change", paint);
    rail.querySelector("#replay").addEventListener("click", function () { tick = 0; paint(); });

panel.style.width = widthInput.value + "px";
    scenario = fromHash();
    window.addEventListener("hashchange", function () {
      const next = fromHash();
      if (next !== scenario) { scenario = next; tick = 0; paint(); }
    });
    /* panel.js keeps its own 2s sync poll and 500ms job poll running (it is the
     * shipped code, and its syncNow() clears the error row). Re-assert the
     * scenario on a 500ms beat so the preview is deterministic instead of
     * racing boot()'s first sync. For the indexing screens this tick is also
     * what advances the pipeline, so the slide and the spinner are real. */
    setInterval(function () {
      if (FIX[scenario] && FIX[scenario].job) {
        tick += 1;
        store.jobs["job-fixture"] = TempoAPI.job().body;
      }
      paint();
    }, 500);
    paint();
  }

  window.addEventListener("load", function () {
    try { ready(); } catch (e) {
      const box = document.getElementById("err");
      box.hidden = false;
      box.textContent = "Harness failed to start: " + e.message;
      console.error(e);
    }
  });
})();