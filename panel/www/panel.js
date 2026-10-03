/* panel.js — plain store + explicit render() calls (AGENTS.md §7.2).
 * No framework, no event bus. All project access via evalScript into
 * host.jsx; all service access via api.js. Polling only (AGENTS.md D2):
 * 2s project sync, 500ms job progress while jobs run. */
"use strict";

// Poll cadence mirrors service config (config.py sync_poll_s/job_poll_s).
// Cross-runtime constants can't be shared by import (AGENTS.md §2.3);
// keep the two in step by hand.
const SYNC_POLL_MS = 2000;
const JOB_POLL_MS = 500;

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
  // Indexing detail: opens when a job starts, closes when all jobs finish or a
  // search runs; a manual toggle wins until the next job starts.
  index: { open: false, manual: false },
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

function applyTheme() {
  // CSInterface#getHostEnvironment().appSkinInfo drives bg/border/text;
  // neutral fallbacks in panel.css when unavailable.
  try {
    if (!cs) return;
    const env = JSON.parse(cs.getHostEnvironment());
    const skin = env && env.appSkinInfo;
    if (!skin) return;
    const root = document.documentElement.style;
    const base = skin.panelBackgroundColor && skin.panelBackgroundColor.color;
    if (base) {
      const c = `rgb(${base.red},${base.green},${base.blue})`;
      root.setProperty("--bg", c);
    }
  } catch (e) { /* fallbacks stand */ }
}

function fmtTC(seconds, fps) {
  const f = Math.max(1, Math.round(fps || 25));
  const total = Math.max(0, Math.floor(seconds * f + 1e-6));
  const fr = total % f;
  const s = Math.floor(total / f);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}:${p(fr)}`;
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

/* ---------- render ---------- */

// Display names for the engine's stage names (presentation only: the stage
// list itself comes from the service, unknown names render as-is).
const STAGE_LABELS = {
  upload: "Upload", shots: "Shots", visual: "Visual", transcribe: "Speech",
  ocr: "OCR", captions: "Captions", text: "Text", index: "Index",
};
const JOB_STATE_LABELS = {
  queued: "queued", uploading: "uploading", "queued-for-backend": "waiting for engine",
  running: "indexing", done: "done", error: "error", cancelled: "cancelled",
};
const LIVE_JOB_STATES = ["queued", "uploading", "queued-for-backend", "running"];
const MB = 1024 * 1024;

const stageLabel = (name) => STAGE_LABELS[name] || name;

function stageCount(s) {
  if (!s.total) return "";
  if (s.name === "upload") return `${(s.done / MB).toFixed(1)}/${(s.total / MB).toFixed(1)} MB`;
  if (s.name === "transcribe") return `${s.done}/${s.total} s`;
  return `${s.done}/${s.total}`;
}

function footageName(key) {
  const f = store.footages.find((x) => x.footage_key === key);
  return f ? baseName(f.path) : "";
}

function currentStage(job) {
  const stages = job.stages || [];
  return stages.filter((s) => s.state === "running").pop() ||
    stages.find((s) => s.state === "pending") || null;
}

function renderStatus() {
  $("svc").textContent = store.online ? "service ok" : "service offline";
  const b = store.backend;
  const label = !store.online ? "engine unknown"
    : b.tunnel === "down" ? "tunnel down"
    : b.tunnel === "starting" ? "tunnel starting"
    : b.reachable ? (b.gpu ? "engine gpu" : "engine cpu")
    : "engine offline";
  $("backend").textContent = label;
  // Status dot: ok = service + reachable engine; warn = transitional
  // (starting/unknown); bad = offline or down. Presentation only.
  const dot = $("svc-dot");
  if (dot) {
    dot.className = "dot " + (!store.online || b.tunnel === "down" || (store.online && !b.reachable && b.tunnel !== "starting")
      ? "bad"
      : (b.reachable ? "ok" : "warn"));
  }
}

function indexSummary() {
  const live = store.activeJobs.map((id) => store.jobs[id]).filter(Boolean);
  if (live.length) {
    const j = live[0];
    const st = currentStage(j);
    const name = footageName(j.footage_key) || "footage";
    const step = st ? ` · ${stageLabel(st.name)}${st.total ? " " + stageCount(st) : ""}` : "";
    const waiting = j.state === "queued-for-backend" ? " · waiting for engine" : "";
    const more = live.length > 1 ? ` · +${live.length - 1} queued` : "";
    return `Indexing · ${name}${step}${waiting}${more}`;
  }
  const fs = store.footages;
  if (!fs.length) return "No footage in project";
  const count = (state) => fs.filter((f) => f.state === state).length;
  const parts = [`${fs.length} footage`, `${count("ready")} ready`];
  if (count("error")) parts.push(`${count("error")} error`);
  if (count("stale")) parts.push(`${count("stale")} stale`);
  return parts.join(" · ");
}

function setIndexOpen(open, manual) {
  store.index.open = open;
  store.index.manual = manual;
  renderIndexing();
}

function renderIndexing() {
  $("indexing-summary").textContent = indexSummary();
  const open = store.index.open;
  const toggle = $("indexing-toggle");
  toggle.setAttribute("aria-pressed", open ? "true" : "false");
  toggle.title = open ? "Hide indexing detail" : "Show indexing detail";
  $("indexing-detail").hidden = !open;
  if (open) { renderJobs(); renderFootageActions(); }
}

function renderJobs() {
  const box = $("jobs");
  box.innerHTML = Object.keys(store.jobs).map((id) => {
    const j = store.jobs[id];
    const rows = (j.stages || []).map((s) => {
      const pct = s.total ? Math.round((s.done / s.total) * 100) : (s.state === "done" ? 100 : 0);
      return `<div class="stage ${esc(s.state)}"><span>${esc(stageLabel(s.name))} · ${esc(s.state)}</span>` +
        `<span class="count">${esc(stageCount(s))}</span>` +
        `<div class="bar"><div style="width:${pct}%"></div></div></div>`;
    }).join("");
    const err = j.state === "error"
      ? `<div class="job err">${esc(j.error || "error")}<div><button type="button" data-retry="${esc(id)}">Retry</button></div></div>`
      : "";
    const name = footageName(j.footage_key) || id;
    const live = LIVE_JOB_STATES.includes(j.state) ? " live" : "";
    return `<div class="job"><div class="job-head"><span class="job-name">${esc(name)}</span>` +
      `<span class="job-state${live}">${esc(JOB_STATE_LABELS[j.state] || j.state)}</span></div>${rows}${err}</div>`;
  }).join("");
  box.querySelectorAll("[data-retry]").forEach((btn) => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); retryJob(btn.dataset.retry); });
  });
}

function trackJob(id, footageKey) {
  // A new job opens the indexing detail again (manual hide lasts until then).
  const fresh = !store.activeJobs.includes(id);
  store.jobs[id] = store.jobs[id] || { job_id: id, footage_key: footageKey, state: "queued", stages: [] };
  store.activeJobs = [...new Set([...store.activeJobs, id])];
  if (fresh) setIndexOpen(true, false);
  else renderIndexing();
}

async function footageRetry(key) {
  const res = await TempoAPI.retryFootage(key);
  if (!res.ok) { showError("RETRY_FAILED", "status " + res.status); return; }
  showError(null);
  trackJob(res.body.job_id, key);
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
  // Every footage gets one factual state row. Buttons only where an explicit
  // click can do work (error → Retry, orphaned → Resume).
  const rows = [];
  for (const f of store.footages) {
    const base = esc(baseName(f.path));
    const detail = f.state === "ready"
      ? `${f.shot_count ? ` · ${f.shot_count} shots` : ""}${f.reused ? " · reused index" : ""}` : "";
    if (f.state === "error") {
      rows.push(`<div class="job"><div class="job-head"><span class="job-name">${base}</span>` +
        `<span class="job-state">error</span></div>` +
        `<div class="row-actions"><button type="button" data-fretry="${esc(f.footage_key)}">Retry</button></div></div>`);
    } else if (!unknown && (f.state === "indexing" || f.state === "uploading") && !covered.has(f.footage_key)) {
      rows.push(`<div class="job"><div class="job-head"><span class="job-name">${base}</span>` +
        `<span class="job-state live">${esc(f.state)}</span></div>` +
        `<div class="row-actions"><button type="button" data-fretry="${esc(f.footage_key)}">Resume</button></div></div>`);
    } else if (!covered.has(f.footage_key)) {
      rows.push(`<div class="job"><div class="job-head"><span class="job-name">${base}</span>` +
        `<span class="job-state">${esc(f.state)}${detail}</span></div></div>`);
    }
  }
  box.innerHTML = rows.join("");
  box.querySelectorAll("[data-fretry]").forEach((btn) => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); footageRetry(btn.dataset.fretry); });
  });
}

async function retryJob(id) {
  const res = await TempoAPI.retry(id);
  if (!res.ok) { showError("RETRY_FAILED", "status " + res.status); return; }
  showError(null);
  const old = store.jobs[id];
  delete store.jobs[id];
  trackJob(res.body.job_id, old && old.footage_key);
}

function skeletonHTML() {
  return `<div class="card skel"><div class="thumb"></div>` +
    `<div><div class="line" style="width:70%"></div><div class="line" style="width:45%"></div></div></div>`;
}

function renderResults() {
  const box = $("results");
  if (store.searching) {
    box.innerHTML = skeletonHTML().repeat(Math.min(8, Math.max(3, store.results.length || 8)));
    return;
  }
  if (!store.results.length) {
    box.innerHTML = `<div class="empty">No results.</div>`;
    return;
  }
  box.innerHTML = `<div class="res-count">${store.results.length} result${store.results.length === 1 ? "" : "s"} · click to insert at playhead</div>` +
    store.results.map((r, i) => {
      const dur = Math.max(0, r.end_s - r.start_s).toFixed(1);
      const ts = r.transcript ? `<div class="snippet">${esc(r.transcript.slice(0, 140))}</div>` : "";
      const cap = r.caption ? `<div class="snippet dim">${esc(r.caption.slice(0, 140))}</div>` : "";
      const busy = store.inserting === i;
      return `<div class="card${busy ? " busy" : ""}" data-i="${i}">` +
        `<img src="${TempoAPI.thumbUrl(r.footage_key, r.shot_id)}" alt="">` +
        `<div class="body"><div class="title">${esc(baseName(r.source_path))}</div>` +
        `<div class="meta tc">${fmtTC(r.start_s, store.compFps)} – ${fmtTC(r.end_s, store.compFps)} · ${dur}s</div>` +
        ts + cap +
        `<div><button type="button" data-insert="${i}"${busy ? " disabled" : ""}>${busy ? "Inserting" : "Insert shot"}</button></div>` +
        `</div></div>`;
    }).join("");
  box.querySelectorAll(".card").forEach((el) => {
    el.addEventListener("click", () => insertResult(store.results[Number(el.dataset.i)], Number(el.dataset.i)));
  });
  box.querySelectorAll("[data-insert]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      insertResult(store.results[Number(btn.dataset.insert)], Number(btn.dataset.insert));
    });
  });
}

function showError(code, message) {
  const el = $("error");
  if (!code) { el.hidden = true; el.textContent = ""; return; }
  el.hidden = false;
  el.textContent = code + (message ? " · " + message : "");
}

function renderFilter() {
  const sel = $("footage-filter");
  if (store.footages.length > 1) {
    sel.hidden = false;
    sel.innerHTML = `<option value="">All footage</option>` + store.footages.map((f) =>
      `<option value="${esc(f.footage_key)}">${esc(baseName(f.path))}</option>`).join("");
    sel.value = store.filter;
  } else {
    sel.hidden = true;
    store.filter = "";
  }
  renderIndexing();
}

/* ---------- actions ---------- */

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
    return;
  }
  showError(null);
  const b = res.body;
  for (const id of b.jobs) trackJob(id);
  const fl = await TempoAPI.footage();
  if (fl.ok) {
    store.footages = fl.body || [];
    renderFilter();
  }
}

async function pollJobs() {
  if (!store.activeJobs.length) return;
  const still = [];
  for (const id of store.activeJobs) {
    const res = await TempoAPI.job(id);
    if (!res.ok) {
      still.push(id); continue;
    }
    store.jobs[id] = res.body;
    if (LIVE_JOB_STATES.includes(res.body.state)) still.push(id);
    else if (res.body.state !== "error") delete store.jobs[id];  // done/cancelled: the footage row takes over
  }
  store.activeJobs = still;
  if (still.length) { renderIndexing(); return; }
  // All jobs finished: hide the detail unless one failed (its message + Retry stay visible).
  const failed = Object.values(store.jobs).some((j) => j.state === "error");
  if (!store.index.manual && !failed) store.index.open = false;
  const fl = await TempoAPI.footage();
  if (fl.ok) store.footages = fl.body || [];
  renderFilter();
}

async function doSearch() {
  const q = $("q").value.trim();
  if (!q) return;
  store.searching = true;
  showError(null);
  if (store.index.open && !store.index.manual) setIndexOpen(false, false);
  renderResults();
  const t0 = Date.now();
  await refreshCompFps();
  const res = await TempoAPI.search(q, 8, store.filter || undefined);
  const elapsed = Date.now() - t0;
  // Skeletons never flash: minimum ~200ms display.
  if (elapsed < 200) await new Promise((r) => setTimeout(r, 200 - elapsed));
  store.searching = false;
  if (!res.ok) {
    const code = (res.body && res.body.error && res.body.error.code) ||
      (res.offline ? "SERVICE_OFFLINE" : "SEARCH_FAILED");
    showError(code, res.offline ? "service offline" : "status " + res.status);
    store.results = [];
  } else {
    store.results = res.body.results || [];
  }
  renderResults();
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
    renderResults();
  }
}

/* ---------- boot ---------- */

const PANEL_VERSION = "0.4.0";

function probe(expr) {
  return new Promise((resolve) => {
    if (!cs) { resolve(null); return; }
    try { cs.evalScript(expr, (r) => resolve(r)); }
    catch (e) { resolve(null); }
  });
}

async function ensureHost() {
  // Loader fallback: some environments load the panel UI but skip manifest
  // ScriptPath evaluation (host functions stay undefined). The service serves
  // the repo files verbatim (GET /host/*.jsx); evalScript them on demand.
  // Probes decide — never blindly re-evaluates over a working host.
  if (!cs) { return; }
  const kind = await probe("typeof tempoListFootage");
  if (kind === "function") { return; }
  const needJson2 = (await probe("typeof JSON")) !== "object";
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
  $("sync-now").addEventListener("click", () => syncNow());
  $("q").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  $("footage-filter").addEventListener("change", (e) => { store.filter = e.target.value; });
  $("indexing-toggle").addEventListener("click", () => setIndexOpen(!store.index.open, true));
  renderStatus();
  renderIndexing();
  renderResults();
  refreshHealth().then(() => syncNow());
  setInterval(syncNow, SYNC_POLL_MS);   // project sync poll (AGENTS.md D2)
  setInterval(pollJobs, JOB_POLL_MS);   // job progress poll while jobs run
}

document.addEventListener("DOMContentLoaded", boot);
