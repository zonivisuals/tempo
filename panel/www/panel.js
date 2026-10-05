/* panel.js — plain store + one render() (AGENTS.md §7.2). No framework, no
 * event bus. All project access via evalScript into host.jsx; all service access
 * via api.js. Polling only (AGENTS.md D2): 2s project sync, 500ms job progress
 * while jobs run.
 *
 * Render strategies differ by list, on purpose (docs/design/panel-ui.md 5):
 *  - #results is rebuilt wholesale. It only re-renders on discrete transitions,
 *    never on the 500ms poll, so nothing in flight is destroyed.
 *  - #steps is keyed and mutated in place. It DOES re-render on the poll, and
 *    replacing its nodes would restart every CSS animation from frame zero at
 *    2Hz. One persistent node per stage key; text is written only when it
 *    changes; reordering uses FLIP so a completing step slides. */
"use strict";

// Poll cadence mirrors service config (config.py sync_poll_s/job_poll_s).
// Cross-runtime constants can't be shared by import (AGENTS.md §2.3);
// keep the two in step by hand.
const SYNC_POLL_MS = 2000;
const JOB_POLL_MS = 500;

// Must equal the sidecar default in app.py (/search top_k). Pinned by
// service/tests/test_contracts.py::test_panel_top_k_matches_service.
const TOP_K = 9;

// Nine steps: the eight engine stages with editorial labels, plus one synthetic
// row bound to job state "queued" (docs/design/panel-ui.md 3.2). Presentation
// only — the stage list itself comes from the service, which takes it from
// engine /v1/health; unknown names render as-is with no label (panel.js's
// stageLabel falls through to the raw name). A step is a row only once its
// stage has started: see stepOrder.
const STEPS = [
  { key: "queued", label: "Initializing your project" },
  { key: "upload", label: "Uploading the footage" },
  { key: "shots", label: "Detecting the scenes" },
  { key: "visual", label: "Embedding the visuals" },
  { key: "transcribe", label: "Transcribing the audio" },
  { key: "ocr", label: "Reading on-screen text" },
  { key: "captions", label: "Captioning your scenes" },
  { key: "text", label: "Reading names and emotion" },
  { key: "index", label: "Finalizing" },
];

const LIVE_JOB_STATES = ["queued", "uploading", "queued-for-backend", "running"];
const MB = 1024 * 1024;

const store = {
  online: false,
  backend: { reachable: false, gpu: false, tunnel: "off" },
  footages: [],
  jobs: {},       // job_id -> last job payload
  activeJobs: [], // job_ids still running
  results: [],
  searching: false,
  inserting: -1,  // result index currently inserting, -1 when idle
  compFps: 25.0,
  filter: "",
  error: null,    // {code, message}
  view: "grid",   // "grid" | "list"
  stepNodes: {},  // stage key -> {row, ic, lab, num}
};

const cs = (typeof CSInterface !== "undefined") ? new CSInterface() : null;
const $ = (id) => document.getElementById(id);

function evalScript(expr) {
  return new Promise((resolve) => {
    if (!cs) { resolve(null); return; }
    try { cs.evalScript(expr, (r) => resolve(r)); }
    catch (e) { resolve(null); }
  });
}

/* ---------- theme ---------- */

function applyTheme() {
  // appSkinInfo no longer supplies background/border/text (ADR-0011): it is read
  // only to pick dark or light. Neutral fallback is the dark palette.
  try {
    if (!cs) return;
    const env = JSON.parse(cs.getHostEnvironment());
    const skin = env && env.appSkinInfo;
    if (!skin) return;
    // appSkinInfo.color is the darkest of the AE UI set; treat a light value as
    // a light host. Anything unreadable leaves the dark default in place.
    const c = skin.color || skin.panelBackgroundColor.color;
    if (!c) return;
    const lum = (c.red * 0.299 + c.green * 0.587 + c.blue * 0.114) / 255;
    document.documentElement.classList.toggle("light", lum > 0.6);
  } catch (e) { /* fallbacks stand */ }
}

/* ---------- formatting ---------- */

function fmtTC(seconds, fps) {
  const f = Math.max(1, Math.round(fps || 25));
  const total = Math.max(0, Math.floor(seconds * f + 1e-6));
  const fr = total % f;
  const s = Math.floor(total / f);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}:${p(fr)}`;
}

function fmtClock(seconds) {
  const t = Math.max(0, Math.round(seconds || 0));
  const m = Math.floor(t / 60);
  return `${m}:${String(t % 60).padStart(2, "0")}`;
}

function baseName(path) {
  return String(path).split(/[\\/]/).pop();
}

function esc(s) {
  // Used in text and attribute positions alike.
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function stageLabel(name) {
  const step = STEPS.find((s) => s.key === name);
  return step ? step.label : name;
}

/* ---------- icons (Figma 777:702) ----------
 * The running row's indicator is the design's 12-ray asset (777:709): a 32px box
 * with stroke-width 3.2. It is rendered into a 16px slot rather than 32 —
 * the design's step row is 42px tall and ours is ~20px, so the geometry scales
 * with the viewport and the stroke lands at 1.6px instead of being restated.
 *
 * stroke is currentColor, not the asset's literal white: white is invisible on
 * the light theme. */
const ICON = {
  spin: '<svg class="spin" width="16" height="16" viewBox="0 0 32 32" fill="none" aria-hidden="true">'
    + '<path d="M15.9993 2.66699V8.00033M15.9993 24.0003V29.3337M6.57268 6.57366L10.346 10.347'
    + 'M21.6527 21.6537L25.426 25.427M2.66602 16.0003H7.99935M23.9993 16.0003H29.3327'
    + 'M6.57268 25.427L10.346 21.6537M21.6527 10.347L25.426 6.57366"'
    + ' stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  done: '<svg class="ok" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">'
    + '<path d="M3.5 8.5 6.5 11.5 12.5 5" fill="none" stroke="currentColor" stroke-width="1.6"'
    + ' stroke-linecap="round" stroke-linejoin="round"/></svg>',
  idle: '<svg class="idle" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">'
    + '<circle cx="8" cy="8" r="4.5" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>',
  /* The insert badge on a result thumbnail. NOT a Figma export: the design's badge
   * box was never measured (Figma's read endpoints were rate-limited), and this
   * geometry is an icon-set path sized against the preview. ADR-0015 §4.
   *
   * No width/height and no `xmlns`: the slot is a share of the thumbnail
   * (`max(16px, 18%)` in CSS) and the square viewBox is what keeps the ring round
   * at any size. `fill` is currentColor because `.plus` sets the accent, so the
   * light theme follows `--accent` rather than a literal hex. */
  badge: '<svg viewBox="0 0 55 55" fill="none" aria-hidden="true">'
    + '<path d="M24.75 41.25H30.25V30.25H41.25V24.75H30.25V13.75H24.75V24.75H13.75V30.25H24.75V41.25Z'
    + 'M27.5 55C23.6958 55 20.1208 54.2896 16.775 52.8688C13.4292 51.4021 10.5188 49.4312 8.04375 46.9562'
    + 'C5.56875 44.4812 3.59792 41.5708 2.13125 38.225C0.710417 34.8792 0 31.3042 0 27.5'
    + 'C0 23.6958 0.710417 20.1208 2.13125 16.775C3.59792 13.4292 5.56875 10.5187 8.04375 8.04375'
    + 'C10.5188 5.56875 13.4292 3.62083 16.775 2.2C20.1208 0.733333 23.6958 0 27.5 0'
    + 'C31.3042 0 34.8792 0.733333 38.225 2.2C41.5708 3.62083 44.4813 5.56875 46.9563 8.04375'
    + 'C49.4313 10.5187 51.3792 13.4292 52.8 16.775C54.2667 20.1208 55 23.6958 55 27.5'
    + 'C55 31.3042 54.2667 34.8792 52.8 38.225C51.3792 41.5708 49.4313 44.4812 46.9563 46.9562'
    + 'C44.4813 49.4313 41.5708 51.4021 38.225 52.8688C34.8792 54.2896 31.3042 55 27.5 55ZM27.5 49.5'
    + 'C33.6417 49.5 38.8438 47.3687 43.1063 43.1062C47.3688 38.8437 49.5 33.6417 49.5 27.5'
    + 'C49.5 21.3583 47.3688 16.1562 43.1063 11.8937C38.8438 7.63125 33.6417 5.5 27.5 5.5'
    + 'C21.3583 5.5 16.1562 7.63125 11.8937 11.8937C7.63125 16.1562 5.5 21.3583 5.5 27.5'
    + 'C5.5 33.6417 7.63125 38.8437 11.8937 43.1062C16.1562 47.3687 21.3583 49.5 27.5 49.5Z"'
    + ' fill="currentColor"/></svg>',
};

/* ---------- step numbers ----------
 * StageStatus is {name, state, done, total} (schemas.py:42-46); there is no unit
 * field, so the unit is this static map. The design carries progress in the
 * running row's own readout ("Finalizing... 80%") rather than a bar, so there
 * is no bar to rewind and no high-water state to keep. Three rules, each forced
 * by measured engine behaviour (docs/design/panel-ui.md 3.3):
 *   total === 0  -> no readout at all. It means unknown, not 0%. It is the
 *                   permanent state for a cache-served stage and for every
 *                   stage of a `reused` job.
 *   transcribe   -> a time count, never a percentage: it reports (total,total)
 *                   then (total+x, 2*total), so a percentage halves mid-stage.
 *   upload       -> MB, matching the byte unit it actually reports. */
function stepNumber(s) {
  if (!s.total) return "";
  if (s.name === "transcribe") return `${fmtClock(s.done)} / ${fmtClock(s.total)}`;
  if (s.name === "upload") {
    return `${(s.done / MB).toFixed(1)}/${(s.total / MB).toFixed(1)} MB`;
  }
  return Math.round((s.done / s.total) * 100) + "%";
}

/* The one row the service never reports: job state "queued" has no stage of
 * its own (docs/design/panel-ui.md 3.2). Built here, used by both stepOrder and
 * renderSteps — it must stay one object, not two literals that drift. */
const QUEUED_STAGE = { name: "queued", state: "running", done: 0, total: 0 };

/* ---------- step list ---------- */

/* Display order: running -> done (most recent first). A stage that has not
 * started is not a row: the list is the running stage plus what is finished,
 * so a docked panel shows real progress instead of nine claims about work that
 * has not happened yet (AGENTS.md 5 F4). A row appears when its stage starts
 * and keeps its place until it is done.
 *
 * Returns {key, stage, state} per row rather than bare keys: a caller that had
 * to look the stage up again would be re-deriving the state, and the one key
 * with no stage of its own ("queued") is where that re-derivation goes wrong.
 * The stage vocabulary is closed and validated service-side
 * (docs/api.md:68), so `state` is taken as reported. */
function stepOrder(job) {
  const byKey = new Map();
  for (const s of (job && job.stages) || []) byKey.set(s.name, s);
  if (job && job.state === "queued") byKey.set("queued", QUEUED_STAGE);
  const stateOf = (key) => (byKey.get(key) || {}).state;

  const row = (key) => ({ key, stage: byKey.get(key), state: stateOf(key) });
  const running = STEPS.filter((s) => stateOf(s.key) === "running").map((s) => s.key);
  const done = STEPS.filter((s) => stateOf(s.key) === "done").map((s) => s.key).reverse();
  // Anything else that has started still gets a row: an errored stage (why
  // indexing stopped) and a stage the engine added that STEPS has no label for.
  // Keys come from the Map, not Object.keys, which is empty for a Map.
  const erroredOrUnlisted = [...byKey.keys()]
    .filter((k) => stateOf(k) !== "pending" && !running.includes(k) && !done.includes(k))
    .reverse();

  return [...running, ...done, ...erroredOrUnlisted].map(row);
}

function activeJob() {
  for (const id of store.activeJobs) {
    const j = store.jobs[id];
    if (j) return j;
  }
  return null;
}

/* The job whose payload the panel still holds and whose stages are on screen. */
function newestFailedJob() {
  const ids = Object.keys(store.jobs);
  for (let i = ids.length - 1; i >= 0; i--) {
    const j = store.jobs[ids[i]];
    if (j && j.state === "error") return j;
  }
  return null;
}

/* The job whose payload the step list renders: the live one while a job runs, and
 * the one that failed once it stops being live.
 *
 * pollJobs drops a job from `activeJobs` on any terminal state but KEEPS the
 * payload, so reading `activeJob()` alone made the poll that reported a failure
 * also the render that cleared the list naming it. The failing stage is the only
 * thing on this screen that says where indexing stopped, and the preview hid the
 * bug by leaving the failed id in the active list. */
function currentJob() {
  return activeJob() || newestFailedJob();
}

function makeStepNode(key) {
  const row = document.createElement("div");
  row.className = "step";
  row.dataset.k = key;
  const ic = document.createElement("span");
  ic.className = "ic";
  ic.innerHTML = ICON.idle;
  const txt = document.createElement("span");
  txt.className = "txt";
  const lab = document.createElement("span");
  lab.className = "lab";
  lab.textContent = stageLabel(key);
  const num = document.createElement("span");
  num.className = "num";
  txt.appendChild(lab);
  txt.appendChild(num);
  row.appendChild(ic);
  row.appendChild(txt);
  return { row, ic, lab, num };
}

/* FLIP: a completing row is MOVED in the DOM, so its new position has to be
 * animated from where it was. Measure before the move, apply the inverse
 * transform, then release. */
function flip(box, mutate) {
  const before = new Map();
  for (const k of Object.keys(store.stepNodes)) {
    const r = store.stepNodes[k].row;
    if (r.parentNode === box) before.set(k, r.getBoundingClientRect().top);
  }
  mutate();
  for (const k of Object.keys(store.stepNodes)) {
    const row = store.stepNodes[k].row;
    if (!before.has(k) || row.parentNode !== box) continue;
    const d = before.get(k) - row.getBoundingClientRect().top;
    if (!d) continue;
    row.style.transition = "none";
    row.style.transform = `translateY(${d}px)`;
    row.getBoundingClientRect(); /* flush */
    row.style.transition = "";
    row.style.transform = "";
  }
}

function renderSteps() {
  const box = $("steps");
  const job = currentJob();
  const wanted = job ? stepOrder(job) : [];
  const keys = new Set(wanted.map((w) => w.key));

  // Drop nodes whose key left the order.
  for (const k of Object.keys(store.stepNodes)) {
    if (!keys.has(k)) {
      const n = store.stepNodes[k];
      if (n.row.parentNode) n.row.parentNode.removeChild(n.row);
      delete store.stepNodes[k];
    }
  }
  if (!wanted.length) { box.textContent = ""; return; }

  flip(box, () => {
    for (const w of wanted) {
      let n = store.stepNodes[w.key];
      if (!n) { n = makeStepNode(w.key); store.stepNodes[w.key] = n; }
      const { row, ic, lab, num } = n;
      if (row.className !== "step " + w.state) row.className = "step " + w.state;
      const label = stageLabel(w.key);
      if (lab.textContent !== label) lab.textContent = label;
      // The readout slot carries the stage's state where it has one to report. A
      // finished row says nothing (F4: `total == 0` is unknown, not 0%), and a
      // failed row says one word — against a done row's 0.5 opacity and an empty
      // slot, that is the whole difference between "this is where it stopped" and
      // another finished row.
      const text = w.state === "running" ? stepNumber(w.stage)
        : (w.state === "error" ? "failed" : "");
      if (num.textContent !== text) num.textContent = text;
      const icon = w.state === "running" ? ICON.spin : (w.state === "done" ? ICON.done : ICON.idle);
      if (ic.dataset.icon !== icon) { ic.dataset.icon = icon; ic.innerHTML = icon; }
      // Single authoritative appendChild per key: existing nodes move, they are
      // never recreated.
      box.appendChild(row);
    }
  });
}

/* ---------- indexing failure ---------- */

/* The footage states the panel has to offer something for: nothing is ready to search
 * and no live job is claiming it. One list, read by `strandedFootage` and by
 * `indexingVisible`, because a state in one and not the other would show a recovery
 * button for footage the section has already decided not to report. The vocabulary is
 * the service's (docs/api.md § GET /footage). */
const NEEDS_ATTENTION = ["error", "indexing", "uploading"];

/* A registry entry the panel has no job for: stranded mid-index after a service
 * restart or a panel reload, or left in `error`. An entry a live job already covers
 * is not stranded — that job is its retry. */
function strandedFootage() {
  const jobs = store.activeJobs.map((id) => store.jobs[id]).filter(Boolean);
  // A job enqueued locally has no footage_key until its first poll (500ms after the
  // 2s sync that created it), so for that window the panel cannot know which entries
  // a live job is about to claim. Reporting them as stranded then would print
  // "Indexing Stopped / Tempo lost track of this step" — and a Retry button — over a
  // job that is uploading fine, on every single import. Nothing is reported until
  // coverage is known. The footage rows this replaces carried the same guard.
  if (jobs.some((j) => !j.footage_key)) return null;
  const covered = new Set(jobs.map((j) => j.footage_key));
  return store.footages.find((f) => !covered.has(f.footage_key)
    && NEEDS_ATTENTION.includes(f.state));
}

/* One failure, one sentence, one button — under the step list, where the failing
 * row is (ADR-0019). This replaced two boxes: an error row printing 300 characters
 * of engine traceback, and a footage row carrying a second Retry for the same fault
 * plus the file name. The raw `error` string is not rendered anywhere; it stays in
 * the payload and in the service log.
 *
 * Reported whenever a failed job exists, including while a different job runs: the
 * queues are single-worker but a failure does not stop them, so the next footage is
 * usually already indexing. In that window the step list belongs to the running job,
 * so the message stands without its row — the retry is the part the editor needs. */
function renderIndexFailure() {
  const box = $("index-fail");
  const failed = newestFailedJob();
  const stranded = failed ? null : strandedFootage();
  if (!failed && !stranded) { box.hidden = true; box.textContent = ""; return; }

  // One action, two addresses: the service treats both routes as the same operation
  // (docs/api.md), and both resume from the stage cache, so the finished steps are
  // not redone. Resolved to a selector and a call here rather than at three uses.
  // `footageKey` is separate from `target.id` on purpose: the target is a job id when
  // a job is known, and the count below compares footage keys.
  const footageKey = failed ? failed.footage_key : stranded.footage_key;
  const target = failed
    ? { sel: "[data-retry-job]", id: failed.job_id, run: () => retryJob(failed.job_id) }
    : { sel: "[data-retry-footage]", id: stranded.footage_key, run: () => footageRetry(stranded.footage_key) };

  // A reason the panel has a sentence for is printed, and it goes on the detail line
  // because F2 requires the service's code on screen. A reason it has none for is
  // not: the vocabulary is closed and pinned across the sidecar, this table and
  // docs/api.md, so an unrecognised one is drift rather than a state an editor will
  // ever meet, and printing a code nothing can explain helps nobody report it.
  const known = failed && failed.reason && FAIL_COPY[failed.reason];
  const copy = failed ? (known || FAIL_COPY.failed) : FAIL_COPY.stranded;
  // The other failures are counted rather than listed: a block per failed footage is
  // the row list this screen just lost, and one failure reported silently is not
  // honest either. The count is read off the footage list, so it is data and not a
  // number written here (§7.3).
  const others = store.footages.filter((f) => f.footage_key !== footageKey && f.state === "error").length;
  const hint = others ? `${copy.hint} ${others} other file${others > 1 ? "s" : ""} also failed to index.` : copy.hint;

  box.hidden = false;
  box.innerHTML = stateBlock(copy.pill, hint, known ? failed.reason : "",
    `<button type="button" class="fail-retry" ${failed ? "data-retry-job" : "data-retry-footage"}`
    + `="${esc(target.id)}">Retry step</button>`);
  box.querySelector(target.sel).addEventListener("click", (e) => {
    e.stopPropagation();
    target.run();
  });
}

/* ---------- render ---------- */

function readyFootage() {
  return store.footages.filter((f) => f.state === "ready");
}

// One cascade, so the dot's colour and its legend cannot drift apart. The bar
// this replaced computed them as two separate if-cascades over the same
// conditions, which is how a dot and the words beside it end up disagreeing.
// ok = service + reachable engine, warn = transitional, bad = offline or down.
function backendState() {
  const b = store.backend;
  if (!store.online) return ["bad", "Service offline · engine unknown"];
  if (b.tunnel === "down") return ["bad", "Tunnel down · engine unreachable"];
  if (b.tunnel === "starting") return ["warn", "Tunnel starting"];
  if (!b.reachable) return ["bad", "Engine offline"];
  return ["ok", b.gpu ? "Engine ready · GPU" : "Engine ready · CPU"];
}

function renderStatus() {
  const dot = $("svc-dot");
  if (!dot) return;
  const [cls, label] = backendState();
  dot.className = "dot " + cls;
  // The bar spelled this out on screen. It is now the dot's legend: title for
  // the pointer, aria-label because the dot is the only thing left carrying it.
  dot.title = label;
  dot.setAttribute("aria-label", label);
}

function renderError() {
  const el = $("error");
  if (!store.error) { el.hidden = true; el.textContent = ""; return; }
  // The block under the header carries the code too, so when it owns the panel the
  // row stands down: one fault, one report. The row is the fallback for an error
  // that arrives over results, which is what `resultsScreen()` calls `results`.
  el.hidden = resultsScreen() === "error";
  el.textContent = store.error.code + (store.error.message ? " · " + store.error.message : "");
}

function renderSearch() {
  // The search field exists once at least one footage is ready (matches the
  // design: neither the no-footage nor the indexing frame has one). The query
  // is never cleared here — a poll that briefly reports no ready footage must
  // not destroy what the editor typed.
  const show = readyFootage().length > 0;
  $("searchbox").hidden = !show;
  $("searchmeta").hidden = !show;
  $("searchbox").classList.toggle("searching", store.searching);
  $("q").disabled = store.searching;
  syncQueryMirror();
}

function syncQueryMirror() {
  const q = $("q");
  $("q-sweep").textContent = q.value;
  // The mirror is absolutely positioned over the input's text; keep it in step
  // with its scroll offset so a long query lines up.
  $("q-sweep").style.left = -q.scrollLeft + "px";
}

function renderFilter() {
  const sel = $("footage-filter");
  const many = store.footages.length > 1;
  sel.hidden = !many;
  if (many) {
    sel.innerHTML = `<option value="">All footage</option>` + store.footages.map((f) =>
      `<option value="${esc(f.footage_key)}">${esc(baseName(f.path))}</option>`).join("");
    sel.value = store.filter;
  } else {
    store.filter = "";
  }
  const g = $("view-grid"), l = $("view-list");
  g.setAttribute("aria-pressed", store.view === "grid" ? "true" : "false");
  l.setAttribute("aria-pressed", store.view === "list" ? "true" : "false");
}

/* Whether the indexing section has anything to say. Pure, so the rule is
 * testable without a DOM: a live job, a failed one, or footage this panel can
 * still act on — stranded mid-index (its Retry) or failed (its Retry). The last two
 * are per-footage states that survive a panel restart, unlike a job id, which is why
 * they are read from the registry and not from store.jobs. `resultsScreen()` asks
 * this same question to decide whether the section owns the panel (ADR-0022). */
function indexingVisible() {
  return !!activeJob()
    || Object.keys(store.jobs).some((id) => store.jobs[id].state === "error")
    || store.footages.some((f) => NEEDS_ATTENTION.includes(f.state));
}

function renderIndexing() {
  const show = indexingVisible();
  const live = !!activeJob();
  $("indexing").hidden = !show;

  // Figma 777:698: the heading pill carries a fixed label and the two-arc
  // indicator, and it is the whole screen until the first stage reports. The
  // live stage is named in the step list right below it. No toggle: the list is
  // simply there while a job runs and disappears with it. The pill stays
  // live-only — a failure reports itself below, in the failure block.
  $("indexing-pill").hidden = !live;
  $("indexing-detail").hidden = !show;
  // The section is centred, so its height decides where the pill sits. While a
  // job runs the detail block is held at the finished step list's height (the
  // `live` rule in panel.css), which leaves the pill on the spot it will still
  // occupy at the end of the run and lets rows arrive underneath it. The same
  // flag that shows the pill drives it, so the two cannot disagree.
  $("indexing").classList.toggle("live", live);
  renderSteps();
  renderIndexFailure();
}

function skeletonHTML() {
  return `<div class="card skel"><span class="sk-thumb"></span><span class="sk-cap"></span></div>`;
}

/* One decision about what #results holds, read by `renderResults` and by
 * `renderError` alike. They used to ask different questions — this one whether
 * footage was ready, that one only whether an error existed — so a failure could be
 * reported by the row while the block stayed away, or by both. One cascade, one
 * answer. Ordered most-specific first: a live job outranks everything, and an error
 * outranks the no-footage claim, which is a claim about the project the panel cannot
 * make while the service is down.
 *
 * `indexingVisible()` is the whole gate rather than `activeJob()`, so a *failed* run
 * or a stranded entry also owns the panel: the indexing section is reporting it, and
 * a frame-01 block saying "Indexing Failed, open the indexing detail" under a detail
 * that is already on screen was the same fault reported twice (ADR-0022). It is
 * qualified on `!ready`, so searchable footage keeps its results. */
function resultsScreen() {
  const ready = readyFootage().length > 0;
  if (!ready && indexingVisible()) return "job";
  if (store.searching) return "searching";
  if (store.error && !store.results.length) return "error";
  if (!ready) return "empty";
  if (!store.results.length) return "nomatch";
  return "results";
}

/* One block, every state that has nothing to show. Figma 777:639 draws the heading
 * as a disabled CTA; it is a status pill instead: a control that cannot be pressed
 * advertises an action it does not have (AGENTS.md §8). Pixels kept, dead affordance
 * dropped. `detail` is the raw service line, for the states that have one; `action`
 * is the one button the block carries, and only the indexing failure has one. Both
 * slots are the caller's own text — nothing user-supplied reaches them. */
function stateBlock(pill, hint, detail, action) {
  return `<div class="empty-state">` +
    `<div class="pill edge warn warn-muted" role="status"><span class="pill-label">${esc(pill)}</span></div>` +
    `<p class="hint">${esc(hint)}</p>` +
    (detail ? `<p class="detail">${esc(detail)}</p>` : "") +
    (action ? action : "") +
    `</div>`;
}

/* A failure, named. `pill` is what stopped, in words; `hint` is the action, which is
 * the part the editor can actually take. `withMessage` is for the states whose own
 * message carries something the hint cannot — a limit, a count — and is absent for
 * the ones that only restate the heading. Codes are the service's vocabulary
 * (docs/api.md) and are pinned by tests; the words are ours.
 * §7.3: no instance name, plan limit, port or path is written here. Every number an
 * editor needs arrives from the service. */
const ERROR_COPY = {
  SERVICE_OFFLINE: {
    pill: "Service Offline",
    hint: "The local Tempo service is not responding. Start it, then press Sync now.",
  },
  BACKEND_ASLEEP: {
    pill: "Engine Asleep",
    hint: "The GPU engine is not running. Start the instance, then search again.",
  },
  BACKEND_UNREACHABLE: {
    pill: "Engine Unreachable",
    hint: "Tempo cannot reach the GPU engine. Check the tunnel, then search again.",
  },
  BACKEND_TIMEOUT: {
    pill: "Search Timed Out",
    hint: "The engine took too long to answer. Search again.",
  },
  // The one state that quotes the service's own sentence: the numbers are the useful
  // part, and §7.3 keeps them out of the panel, so they arrive as text. The wording
  // says "your plan's limit" and not "the footage limit", because the service raises
  // this same code for footage-minutes as well (entitlements.check_new_work).
  QUOTA_EXCEEDED: {
    pill: "Limit Reached",
    hint: "This project is over your plan's limit. Footage already indexed stays searchable.",
    withMessage: true,
  },
};

/* What the failure screen says, keyed by the reason the service reported
 * (docs/api.md § GET /jobs/{id}; the vocabulary is `REASONS` in the sidecar's
 * proxy.py and both sides are pinned against each other by test). The heading is a
 * status pill because that is what every other failure gets, and the instruction is
 * the part the editor can take.
 *
 * `pill` is read from ERROR_COPY for the three transport codes rather than restated,
 * so the same code cannot describe one failure two ways across search and indexing.
 * The hints are written for the action this screen offers — retry the step — and so
 * differ from ERROR_COPY's "search again" on purpose.
 *
 * §7.3: no instance name, plan limit, port or path is written here. Two states are
 * not keyed by a reason because they are not failures the service named: `failed` is
 * the fallback for a reason nobody has written a sentence for yet (including a job
 * from before the field existed), and `stranded` is an entry with no job at all. */
const FAIL_COPY = {
  BACKEND_UNREACHABLE: {
    pill: ERROR_COPY.BACKEND_UNREACHABLE.pill,
    hint: "Tempo could not reach the GPU engine. Start the instance, then try the step again.",
  },
  BACKEND_ASLEEP: {
    pill: ERROR_COPY.BACKEND_ASLEEP.pill,
    hint: "The GPU engine is not running. Start the instance, then try the step again.",
  },
  BACKEND_TIMEOUT: {
    pill: "Engine Timed Out",
    hint: "The engine stopped answering. Try the step again.",
  },
  NOT_CONFIGURED: {
    pill: "No Engine Set Up",
    hint: "Tempo has no engine to index on. Point it at one, then try the step again.",
  },
  SOURCE_MISSING: {
    pill: "Footage Unreadable",
    hint: "Tempo could not read the file from disk. Put it back where the project expects it, then try again.",
  },
  UNKNOWN_FOOTAGE: {
    pill: "Footage Missing",
    hint: "Tempo lost track of this file. Press Sync now, then try the step again.",
  },
  ENGINE_REJECTED: {
    pill: "Engine Refused",
    hint: "The engine would not take this footage. Check the file, then try the step again.",
  },
  ENGINE_FAILED: {
    pill: "Indexing Failed",
    hint: "Tempo's engine stopped on this step. Try it again — the finished steps are kept.",
  },
  failed: {
    pill: "Indexing Failed",
    hint: "Tempo stopped. Try it again, the finished steps are kept.",
  },
  stranded: {
    pill: "Indexing Stopped",
    hint: "Tempo lost track of the step this stopped on. Try again — indexing resumes from the last finished step.",
  },
};

/* The service's words, bounded. A job error is 2000 characters of engine traceback
 * (engine/jobs.py:179) and a service message can be a limit sentence, so a block
 * that tall is not a message: the ellipsis says it was cut. The indexing failure no
 * longer quotes the job's `error` at all — it names the step in its own row (see
 * renderIndexFailure) — but the block's two routes into the service's line are both
 * bounded here. */
const BLOCK_TEXT_MAX = 160;
function clamp(s, max) {
  const t = String(s == null ? "" : s);
  return t.length > max ? t.slice(0, max).trimEnd() + "…" : t;
}

/* A failure with nothing else on screen. The heading and the instruction come from
 * the copy table; the code is the detail line either way, because F2 requires it on
 * screen and a code nobody can name is a failure nobody can report. A code with no
 * copy of its own falls back to the service's message as the instruction rather than
 * to nothing. */
function errorStateHTML() {
  const e = store.error || {};
  const copy = ERROR_COPY[e.code];
  if (!copy) {
    return stateBlock("Request Failed", clamp(e.message, BLOCK_TEXT_MAX) || "The service returned an error.", e.code);
  }
  const detail = copy.withMessage && e.message ? `${e.code} · ${clamp(e.message, BLOCK_TEXT_MAX)}` : e.code;
  return stateBlock(copy.pill, copy.hint, detail);
}

/* Frame 01 and the one variant left in this area. The indexing variants — a failed
 * footage and one stranded mid-index — moved to the section that reports them, along
 * with the sentence and the button that retry (ADR-0020, ADR-0022); reaching here
 * with either means `resultsScreen()` sent this panel somewhere else. */
function emptyStateHTML() {
  const fs = store.footages;
  if (!fs.length) {
    return stateBlock("No Footage Found",
      "Get started by importing your videos to the project");
  }
  return stateBlock("No Searchable Footage",
    "Every file in this project is stale. Re-import it, or delete it from the project.");
}

/* Nothing matched, or nothing asked yet. Both take frame 01's shape: the state
 * named, then one line saying what to do. The query is quoted back, because the
 * editor needs to see what was actually searched. */
function noMatchHTML() {
  const q = store.lastQuery;
  if (!q) {
    return stateBlock("Ready to Search", "Type a few words to find shots across your footage.");
  }
  return stateBlock("No Shots Found",
    `Nothing in this project matches “${q}”. Try a word from the dialogue or captions.`);
}

function renderResults() {
  const box = $("results");
  const screen = resultsScreen();
  // A live job owns the panel: a state block under a running step list reads as two
  // contradictory states at once. The grid class is applied only when there are cells
  // to grid — on a single state block it would split it across two columns.
  if (screen === "job") { box.className = ""; box.innerHTML = ""; return; }
  if (screen === "searching") {
    box.className = store.view === "grid" ? "grid" : "list";
    // Count matches the previous result count so the list does not reflow on
    // submit; a first search renders TOP_K.
    const n = Math.max(3, Math.min(TOP_K, store.results.length || TOP_K));
    box.innerHTML = skeletonHTML().repeat(n);
    return;
  }
  if (screen === "results") {
    box.className = store.view === "grid" ? "grid" : "list";
    box.innerHTML = renderCards();
    box.querySelectorAll(".card").forEach((el) => {
      el.addEventListener("click", () => insertResult(store.results[Number(el.dataset.i)], Number(el.dataset.i)));
    });
    return;
  }
  // Frame 01, its variants, a search that matched nothing, and a failure with nothing
  // else to show: the header (and the search field, when there is one) is all that is
  // above them, so each is centred on both axes like the indexing screen (the
  // `centered` rule in panel.css is `margin: auto`, the same thing #indexing does).
  box.className = "centered";
  box.innerHTML = screen === "error" ? errorStateHTML()
    : screen === "nomatch" ? noMatchHTML()
    : emptyStateHTML();
}

function renderCards() {
  const many = store.footages.length > 1;
  return store.results.map((r, i) => {
    const dur = Math.max(0, r.end_s - r.start_s).toFixed(1);
    const busy = store.inserting === i;
    // One description line: the caption when the engine produced one, otherwise
    // the transcript. Never both — D4 (no context hint in caption prompts) exists
    // because Florence-2 captions tend to echo the transcript verbatim, and two
    // near-identical strings under a thumbnail is worse than one.
    const desc = r.caption || r.transcript || "";
    const name = many ? `<span class="name">${esc(baseName(r.source_path))}</span>` : "";
    // Figma 777:368: the caption and the duration share one baseline-aligned row
    // with space between them. The timecode range needs more width than a grid
    // cell has, so it only appears in list mode.
    const row = `<span class="cardrow"><span class="cap">${esc(desc)}</span>` +
      `<span class="dur">${dur}s</span></span>`;
    const tc = store.view === "list"
      ? `<span class="tc">${fmtTC(r.start_s, store.compFps)} – ${fmtTC(r.end_s, store.compFps)}</span>`
      : "";
    return `<button type="button" class="card${busy ? " busy" : ""}" data-i="${i}"${busy ? " disabled" : ""}>` +
      `<span class="thumb"><img src="${esc(TempoAPI.thumbUrl(r.footage_key, r.shot_id))}" alt="">` +
      `<span class="plus" aria-hidden="true">${ICON.badge}</span></span>` +
      `<span class="body">${name}${desc ? row : ""}${tc}</span></button>`;
  }).join("");
}

function render() {
  renderStatus();
  renderError();
  renderSearch();
  renderFilter();
  renderIndexing();
  renderResults();
}

/* ---------- actions ---------- */

function showError(code, message, scope) {
  // Both surfaces at once: the error decides which of the block and the row speaks
  // (resultsScreen), so a caller that only refreshed the row would leave the other
  // one stale — which is how a retry failure went unreported until the next poll.
  store.error = code ? { code, message, scope } : null;
  renderError();
  renderResults();
}

/* Only the action that raised an error clears it. The project sync runs every 2s, and
 * a sync that succeeds does not repair a search that timed out: clearing it left the
 * panel asserting that nothing matched a search that never returned. */
function clearError(scope) {
  if (store.error && store.error.scope !== scope) return;
  store.error = null;
}

/* A failed call's own answer, or the panel's fallback for a transport that never
 * reached the service. The envelope wins because it is the service speaking: the
 * quota denial's code and its limit are the whole point of that block, and throwing
 * them away for "status 403" is how the panel used to report one. */
function callError(res, fallbackCode, fallbackMessage) {
  const e = res.body && res.body.error;
  return e ? { code: e.code, message: e.message } : { code: fallbackCode, message: fallbackMessage };
}

async function refreshCompFps() {
  const raw = await evalScript("tempoGetActiveCompInfo()");
  try {
    const info = JSON.parse(raw);
    if (info && info.fps) store.compFps = info.fps;
  } catch (e) { /* project fps stays default */ }
}

async function refreshHealth() {
  const res = await TempoAPI.health();
  if (res.ok && res.body) {
    store.online = true;
    store.backend = res.body.backend || { reachable: false, gpu: false, tunnel: "off" };
  } else {
    store.online = false;
    store.backend = { reachable: false, gpu: false, tunnel: "off" };
  }
  renderStatus();
}

async function syncNow() {
  const raw = await evalScript("tempoListFootage()");
  let footages = [];
  try { footages = JSON.parse(raw) || []; } catch (e) { footages = []; }
  const res = await TempoAPI.sync(footages);
  store.online = res.ok;
  if (res.ok) await refreshHealth();
  else renderStatus();
  if (!res.ok) {
    const err = callError(res, res.offline ? "SERVICE_OFFLINE" : "SYNC_FAILED",
      res.offline ? "service offline" : "status " + res.status);
    showError(err.code, err.message, "sync");
    return;
  }
  clearError("sync");
  for (const id of res.body.jobs) trackJob(id);
  const fl = await TempoAPI.footage();
  if (fl.ok) {
    store.footages = fl.body || [];
  }
  render();
}

function trackJob(id, footageKey) {
  store.jobs[id] = store.jobs[id] || { job_id: id, footage_key: footageKey, state: "queued", stages: [] };
  store.activeJobs = [...new Set([...store.activeJobs, id])];
}

async function pollJobs() {
  if (!store.activeJobs.length) return;
  const still = [];
  for (const id of store.activeJobs) {
    const res = await TempoAPI.job(id);
    if (!res.ok) { still.push(id); continue; }
    store.jobs[id] = res.body;
    if (LIVE_JOB_STATES.includes(res.body.state)) still.push(id);
    else if (res.body.state !== "error") delete store.jobs[id];  // done/cancelled: the footage row takes over
  }
  store.activeJobs = still;
  if (still.length) {
    renderIndexing();
    renderResults();
    return;
  }
  const fl = await TempoAPI.footage();
  if (fl.ok) store.footages = fl.body || [];
  render();
}

async function retryJob(id) {
  const res = await TempoAPI.retry(id);
  if (!res.ok) {
    const err = callError(res, res.offline ? "SERVICE_OFFLINE" : "RETRY_FAILED",
      res.offline ? "service offline" : "status " + res.status);
    showError(err.code, err.message, "action");
    return;
  }
  clearError("action");
  delete store.jobs[id];
  trackJob(res.body.job_id, undefined);
  render();
}

async function footageRetry(key) {
  const res = await TempoAPI.retryFootage(key);
  if (!res.ok) {
    const err = callError(res, res.offline ? "SERVICE_OFFLINE" : "RETRY_FAILED",
      res.offline ? "service offline" : "status " + res.status);
    showError(err.code, err.message, "action");
    return;
  }
  clearError("action");
  trackJob(res.body.job_id, key);
  render();
}

async function doSearch() {
  const q = $("q").value.trim();
  if (!q) return;
  store.searching = true;
  store.lastQuery = q;
  clearError("search");
  render();
  const t0 = Date.now();
  await refreshCompFps();
  const res = await TempoAPI.search(q, TOP_K, store.filter || undefined);
  const elapsed = Date.now() - t0;
  // Skeletons never flash: minimum ~200ms display (AGENTS.md 5 F3).
  if (elapsed < 200) await new Promise((r) => setTimeout(r, 200 - elapsed));
  store.searching = false;
  if (!res.ok) {
    const err = callError(res, res.offline ? "SERVICE_OFFLINE" : "SEARCH_FAILED",
      res.offline ? "service offline" : "status " + res.status);
    showError(err.code, err.message, "search");
    store.results = [];
  } else {
    clearError("search");
    store.results = res.body.results || [];
  }
  render();
}

async function insertResult(r, idx) {
  // Click a result → the [start_s, end_s] shot lands trimmed on the
  // timeline at the playhead (host.jsx tempoInsertOrFocus, one undo step).
  if (!r || store.inserting >= 0) return;
  store.inserting = idx;
  renderResults();
  try {
    const payload = JSON.stringify({
      source_path: r.source_path, start_s: r.start_s, end_s: r.end_s,
    });
    // One evalScript call does the whole job (locate/import, comp, trim, playhead).
    // The JSON travels as an ExtendScript *string literal* (host.jsx parses
    // it with JSON.parse): it must be wrapped in quotes with every backslash
    // doubled, or Windows paths mangle ("C:\Users" parses to "C:Users").
    // Single quotes are escaped too so paths with apostrophes survive.
    const expr = "tempoInsertOrFocus('" + payload.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "')";
    const raw = await evalScript(expr);
    try {
      const out = JSON.parse(raw);
      if (!out || !out.ok) { showError("INSERT_FAILED", out && out.error, "action"); }
      else { clearError("action"); }
    } catch (e) {
      showError("INSERT_FAILED", "bad host response", "action");
    }
  } finally {
    store.inserting = -1;
    render();
  }
}

function setView(view) {
  store.view = view;
  try { localStorage.setItem("tempo_view", view); } catch (e) { /* storage unavailable */ }
  render();
}

/* ---------- boot ---------- */

async function ensureHost() {
  // Loader fallback: some environments load the panel UI but skip manifest
  // ScriptPath evaluation (host functions stay undefined). The service serves
  // the repo files verbatim (GET /host/*.jsx); evalScript them on demand.
  // Probes decide — never blindly re-evaluates over a working host.
  if (!cs) { return; }
  const kind = await evalScript("typeof tempoListFootage");
  if (kind === "function") { return; }
  const needJson2 = (await evalScript("typeof JSON")) !== "object";
  for (const name of needJson2 ? ["json2", "host"] : ["host"]) {
    const res = await TempoAPI.hostJs(name);
    if (!res.ok || !res.text) { return; }
    await new Promise((resolve) => {
      try { cs.evalScript(res.text, () => resolve(true)); }
      catch (e) { resolve(false); }
    });
  }
}

async function boot() {
  await ensureHost();
  applyTheme();
  try {
    const saved = localStorage.getItem("tempo_view");
    if (saved === "grid" || saved === "list") store.view = saved;
  } catch (e) { /* storage unavailable — grid default */ }

  $("sync-now").addEventListener("click", () => syncNow());
  $("q").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  $("q").addEventListener("input", syncQueryMirror);
  $("q").addEventListener("scroll", syncQueryMirror);
  $("submit").addEventListener("click", () => doSearch());
  $("footage-filter").addEventListener("change", (e) => { store.filter = e.target.value; });
  $("view-grid").addEventListener("click", () => setView("grid"));
  $("view-list").addEventListener("click", () => setView("list"));

  render();
  refreshHealth().then(() => syncNow());
  setInterval(syncNow, SYNC_POLL_MS);   // project sync poll (AGENTS.md D2)
  setInterval(pollJobs, JOB_POLL_MS);   // job progress poll while jobs run
}

document.addEventListener("DOMContentLoaded", boot);
