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
  const job = activeJob();
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
      const text = w.state === "running" ? stepNumber(w.stage) : "";
      if (num.textContent !== text) num.textContent = text;
      const icon = w.state === "running" ? ICON.spin : (w.state === "done" ? ICON.done : ICON.idle);
      if (ic.dataset.icon !== icon) { ic.dataset.icon = icon; ic.innerHTML = icon; }
      // Single authoritative appendChild per key: existing nodes move, they are
      // never recreated.
      box.appendChild(row);
    }
  });
}

/* ---------- indexing error ---------- */

function renderJobError() {
  const box = $("job-err");
  const failed = store.activeJobs.concat(Object.keys(store.jobs))
    .map((id) => store.jobs[id]).find((j) => j && j.state === "error");
  if (!failed) { box.hidden = true; box.textContent = ""; return; }
  box.hidden = false;
  // Job error strings can be 2000 chars of engine traceback (engine/jobs.py:179).
  // Never routed into a one-row area — truncated here, Retry stays.
  const msg = String(failed.error || "indexing failed");
  box.innerHTML = `<div>${esc(msg.length > 300 ? msg.slice(0, 300) + "…" : msg)}</div>` +
    `<button type="button" data-retry="${esc(failed.job_id)}">Retry</button>`;
  box.querySelector("[data-retry]").addEventListener("click", (e) => {
    e.stopPropagation(); retryJob(failed.job_id);
  });
}

function renderFootageActions() {
  // Retry/Resume per footage state (explicit clicks only — auto-sync never
  // re-enqueues). Covers error entries and orphaned indexing entries whose
  // job id was lost (service restart / panel reload).
  const box = $("footage-actions");
  const covered = new Set(
    store.activeJobs.map((id) => store.jobs[id] && store.jobs[id].footage_key).filter(Boolean)
  );
  // Jobs created locally have no footage_key until their first poll — can't
  // prove orphan, so suppress Resume until coverage is known (500ms poll).
  const unknown = store.activeJobs.some((id) => !(store.jobs[id] && store.jobs[id].footage_key));
  const rows = [];
  for (const f of store.footages) {
    const detail = f.state === "ready"
      ? `${f.shot_count ? ` · ${f.shot_count} shots` : ""}${f.reused ? " · reused index" : ""}` : "";
    if (f.state === "error") {
      rows.push(`<div class="frow"><span class="fname">${esc(baseName(f.path))}</span>` +
        `<span class="fstate">error</span>` +
        `<button type="button" data-fretry="${esc(f.footage_key)}">Retry</button></div>`);
    } else if (!unknown && (f.state === "indexing" || f.state === "uploading") && !covered.has(f.footage_key)) {
      rows.push(`<div class="frow live"><span class="fname">${esc(baseName(f.path))}</span>` +
        `<span class="fstate">${esc(f.state)}</span>` +
        `<button type="button" data-fretry="${esc(f.footage_key)}">Resume</button></div>`);
    } else if (!covered.has(f.footage_key)) {
      rows.push(`<div class="frow"><span class="fname">${esc(baseName(f.path))}</span>` +
        `<span class="fstate">${esc(f.state)}${esc(detail)}</span></div>`);
    }
  }
  box.innerHTML = rows.join("");
  box.querySelectorAll("[data-fretry]").forEach((btn) => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); footageRetry(btn.dataset.fretry); });
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
  el.hidden = false;
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
  $("q-base").textContent = q.value;
  $("q-sweep").textContent = q.value;
  // Mirrors are absolutely positioned over the input's text; keep them in step
  // with its scroll offset so a long query lines up.
  const off = q.scrollLeft;
  $("q-base").style.left = -off + "px";
  $("q-sweep").style.left = -off + "px";
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
 * still act on — stranded mid-index (Resume) or failed (Retry). Both of the
 * last two are per-footage states that survive a panel restart, unlike a job
 * id, which is why they are read from the registry and not from store.jobs. */
function indexingVisible() {
  return !!activeJob()
    || Object.keys(store.jobs).some((id) => store.jobs[id].state === "error")
    || store.footages.some((f) => f.state === "error" || f.state === "indexing" || f.state === "uploading");
}

function renderIndexing() {
  const show = indexingVisible();
  const live = !!activeJob();
  $("indexing").hidden = !show;

  // Figma 777:698: the heading pill carries a fixed label and the two-arc
  // indicator, and it is the whole screen until the first stage reports. The
  // live stage is named in the step list right below it. No toggle: the list is
  // simply there while a job runs and disappears with it. A failed job keeps its
  // message and Retry visible.
  $("indexing-pill").hidden = !live;
  $("indexing-detail").hidden = !show;
  // The section is centred, so its height decides where the pill sits. While a
  // job runs the detail block is held at the finished step list's height (the
  // `live` rule in panel.css), which leaves the pill on the spot it will still
  // occupy at the end of the run and lets rows arrive underneath it. The same
  // flag that shows the pill drives it, so the two cannot disagree.
  $("indexing").classList.toggle("live", live);
  renderSteps();
  if (show) { renderJobError(); renderFootageActions(); }
}

function skeletonHTML() {
  return `<div class="card skel"><span class="sk-thumb"></span><span class="sk-cap"></span></div>`;
}

function emptyStateHTML() {
  // Figma 777:639: an accent heading above one line of instruction, centred.
  // The heading is a status pill, not the design's disabled CTA — same pixels,
  // no control that cannot be pressed.
  const pill = (text) =>
    `<div class="pill edge warn warn-muted" role="status"><span class="pill-label">${esc(text)}</span></div>`;
  const fs = store.footages;
  if (!fs.length) {
    return `<div class="empty-state">${pill("No Footage Found")}` +
      `<p class="hint">Get started by importing your videos to the project</p></div>`;
  }
  const bad = fs.find((f) => f.state === "error");
  if (bad) {
    return `<div class="empty-state">${pill("Indexing Failed")}` +
      `<p class="hint">${esc(baseName(bad.path))} could not be indexed. Open the indexing detail to retry.</p></div>`;
  }
  // Footage stuck in indexing/uploading with no live job: the job id was lost
  // (service restart) or the engine never picked it up. Resume lives in the
  // indexing detail, so point there rather than claiming the files are stale.
  const stuck = fs.find((f) => f.state === "indexing" || f.state === "uploading");
  if (stuck) {
    return `<div class="empty-state">${pill("Indexing Stalled")}` +
      `<p class="hint">${esc(baseName(stuck.path))} has not started. Open the indexing detail to resume it.</p></div>`;
  }
  return `<div class="empty-state">${pill("No Searchable Footage")}` +
    `<p class="hint">Every file in this project is stale. Re-import it, or delete it from the project.</p></div>`;
}

function renderResults() {
  const box = $("results");
  const ready = readyFootage().length > 0;
  // While a job is live the indexing screen owns the panel: an empty-state pill
  // under a running step list reads as two contradictory states at once.
  if (!ready && activeJob()) { box.className = ""; box.innerHTML = ""; return; }
  // The grid class is only applied when there are cells to grid. Applying it to
  // a single empty-state or "no results" row would split it across two columns.
  const gridding = ready && (store.searching || store.results.length > 0);
  box.className = store.view === "grid" && gridding ? "grid" : "list";
  if (store.searching) {
    // Count matches the previous result count so the list does not reflow on
    // submit; a first search renders TOP_K.
    const n = Math.max(3, Math.min(TOP_K, store.results.length || TOP_K));
    box.innerHTML = skeletonHTML().repeat(n);
    return;
  }
  // Frame 01, and its three variants: the header is all that is above it, so
  // it is centred on both axes like the indexing screen (the `centered` rule in
  // panel.css is `margin: auto`, the same thing #indexing does).
  if (!ready) { box.className = "centered"; box.innerHTML = emptyStateHTML(); return; }
  if (!store.results.length) {
    const q = store.lastQuery;
    box.innerHTML = `<div class="empty">${q ? `No shots matched “${esc(q)}”.` : "Search your footage."}</div>`;
    return;
  }
  const many = store.footages.length > 1;
  box.innerHTML = store.results.map((r, i) => {
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
  box.querySelectorAll(".card").forEach((el) => {
    el.addEventListener("click", () => insertResult(store.results[Number(el.dataset.i)], Number(el.dataset.i)));
  });
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

function showError(code, message) {
  store.error = code ? { code, message } : null;
  renderError();
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
    showError(res.offline ? "SERVICE_OFFLINE" : "SYNC_FAILED", res.offline ? "service offline" : "status " + res.status);
    renderResults();
    return;
  }
  showError(null);
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
  if (!res.ok) { showError(res.offline ? "SERVICE_OFFLINE" : "RETRY_FAILED", res.offline ? "service offline" : "status " + res.status); return; }
  showError(null);
  delete store.jobs[id];
  trackJob(res.body.job_id, undefined);
  render();
}

async function footageRetry(key) {
  const res = await TempoAPI.retryFootage(key);
  if (!res.ok) { showError(res.offline ? "SERVICE_OFFLINE" : "RETRY_FAILED", res.offline ? "service offline" : "status " + res.status); return; }
  showError(null);
  trackJob(res.body.job_id, key);
  render();
}

async function doSearch() {
  const q = $("q").value.trim();
  if (!q) return;
  store.searching = true;
  store.lastQuery = q;
  showError(null);
  render();
  const t0 = Date.now();
  await refreshCompFps();
  const res = await TempoAPI.search(q, TOP_K, store.filter || undefined);
  const elapsed = Date.now() - t0;
  // Skeletons never flash: minimum ~200ms display (AGENTS.md 5 F3).
  if (elapsed < 200) await new Promise((r) => setTimeout(r, 200 - elapsed));
  store.searching = false;
  if (!res.ok) {
    const code = (res.body && res.body.error && res.body.error.code) ||
      (res.offline ? "SERVICE_OFFLINE" : "SEARCH_FAILED");
    showError(code, res.offline ? "service offline" : "status " + res.status);
    store.results = [];
  } else {
    showError(null);
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
      if (!out || !out.ok) { showError("INSERT_FAILED", out && out.error); }
      else { showError(null); }
    } catch (e) {
      showError("INSERT_FAILED", "bad host response");
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
