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
  backend: { reachable: false, gpu: false },
  footages: [],
  jobs: {},       // job_id -> last job payload
  activeJobs: [], // job_ids still running
  results: [],
  searching: false,
  inserting: -1,  // result index currently inserting, -1 when idle
  compFps: 25.0,
  filter: "",
};

const cs = (typeof CSInterface !== "undefined") ? new CSInterface() : null;
const $ = (id) => document.getElementById(id);

const bootLines = [];
function dbg(line, pin) {
  // Single copy-paste surface: DevTools console + #debug box.
  try { console.log("[Tempo] " + line); } catch (e) { /* headless */ }
  try {
    const el = $("debug");
    if (!el) return;
    if (pin) bootLines.push(line);
    const tail = (el.dataset.tail || "").split("\n").filter(Boolean);
    if (!pin) {
      tail.push(line);
      el.dataset.tail = tail.slice(-60).join("\n");
    }
    el.textContent = bootLines.concat(["---"], (el.dataset.tail || "").split("\n")).join("\n");
  } catch (e) { /* ignore */ }
}

function evalScript(expr) {
  return new Promise((resolve) => {
    if (!cs) { dbg("evalScript: NO CSInterface (panel opened outside AE?) expr=" + expr); resolve(null); return; }
    try { cs.evalScript(expr, (r) => resolve(r)); }
    catch (e) { dbg("evalScript: throw " + e); resolve(null); }
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
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* ---------- render ---------- */

function renderStatus() {
  $("svc").textContent = store.online ? "service ok" : "service offline";
  const c = $("backend");
  if (c) {
    c.textContent = !store.online ? "backend unknown"
      : store.backend.reachable ? (store.backend.gpu ? "backend gpu" : "backend ok")
      : "local only";
  }
}

function renderJobs() {
  const box = $("jobs");
  const ids = Object.keys(store.jobs);
  if (!ids.length) { box.innerHTML = ""; renderFootageActions(); return; }
  box.innerHTML = ids.map((id) => {
    const j = store.jobs[id];
    const rows = (j.stages || []).map((s) => {
      const pct = s.total ? Math.round((s.done / s.total) * 100) : (s.state === "done" ? 100 : 0);
      return `<div>${esc(s.name)} ${s.state}${s.total ? ` ${s.done}/${s.total}` : ""}` +
        `<div class="bar"><div style="width:${pct}%"></div></div></div>`;
    }).join("");
    const err = j.state === "error"
      ? `<div class="job err">${esc(j.error || "error")}<div><button type="button" data-retry="${esc(id)}">Retry</button></div></div>`
      : "";
    return `<div class="job"><div>Indexing ${esc(id)} · ${esc(j.state)}</div>${rows}${err}</div>`;
  }).join("");
  box.querySelectorAll("[data-retry]").forEach((btn) => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); retryJob(btn.dataset.retry); });
  });
  renderFootageActions();
}

async function footageRetry(key) {
  dbg(`footage-retry: key=${key}`);
  const res = await TempoAPI.retryFootage(key);
  dbg(`footage-retry: ok=${res.ok} status=${res.status} body=${JSON.stringify(res.body).slice(0, 200)}`);
  if (!res.ok) { showError("RETRY_FAILED", "status " + res.status); return; }
  showError(null);
  const nid = res.body.job_id;
  store.jobs[nid] = { job_id: nid, footage_key: key, state: "queued", stages: [] };
  store.activeJobs = [...new Set([...store.activeJobs, nid])];
  renderJobs();
}

function renderFootageActions() {
  // Retry/Resume per footage state (explicit clicks only — auto-sync never
  // re-enqueues). Covers error entries and orphaned indexing entries whose
  // job id was lost (service restart / panel reload).
  const box = $("footage-actions");
  if (!box) return;
  const covered = new Set(
    store.activeJobs.map((id) => store.jobs[id] && store.jobs[id].footage_key).filter(Boolean)
  );
  // Jobs created locally have no footage_key until their first poll — can't
  // prove orphan, so suppress Resume until coverage is known (500ms poll).
  const unknown = store.activeJobs.some((id) => !(store.jobs[id] && store.jobs[id].footage_key));
  // Every footage gets one factual state row — this is how you tell what
  // indexing is doing without opening DevTools. Buttons only where an
  // explicit click can do work (error → Retry, orphaned → Resume).
  const rows = [];
  for (const f of store.footages) {
    const base = esc(String(f.path).split(/[\\/]/).pop());
    const detail = f.state === "ready" && f.shot_count
      ? ` · ${f.shot_count} shots` : "";
    if (f.state === "error") {
      rows.push(`<div class="job"><div>${base} · error — read the job message, then Retry</div>` +
        `<div><button type="button" data-fretry="${esc(f.footage_key)}">Retry</button></div></div>`);
    } else if (!unknown && (f.state === "indexing" || f.state === "uploading") && !covered.has(f.footage_key)) {
      rows.push(`<div class="job"><div>${base} · ${esc(f.state)} (no active job)</div>` +
        `<div><button type="button" data-fretry="${esc(f.footage_key)}">Resume</button></div></div>`);
    } else {
      const live = (f.state === "indexing" || f.state === "uploading") ? " · working (see stages below)" : "";
      rows.push(`<div class="job"><div>${base} · ${esc(f.state)}${detail}${live}</div></div>`);
    }
  }
  box.innerHTML = rows.join("");
  box.querySelectorAll("[data-fretry]").forEach((btn) => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); footageRetry(btn.dataset.fretry); });
  });
}

async function retryJob(id) {
  dbg(`retry: job=${id}`);
  const res = await TempoAPI.retry(id);
  dbg(`retry: ok=${res.ok} status=${res.status} body=${JSON.stringify(res.body).slice(0, 200)}`);
  if (!res.ok) { showError("RETRY_FAILED", "status " + res.status); return; }
  showError(null);
  const nid = res.body.job_id;
  store.jobs[nid] = { job_id: nid, state: "queued", stages: [] };
  store.activeJobs = [...new Set([...store.activeJobs, nid])];
  renderJobs();
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
  renderFootageActions();
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
    store.backend = res.body.backend || { reachable: false, gpu: false };
    dbg(`health: ok online=true backend=${JSON.stringify(store.backend)} base=${TempoAPI.base()}`);
  } else {
    store.online = false;
    store.backend = { reachable: false, gpu: false };
    dbg(`health: FAIL ok=${res.ok} status=${res.status} offline=${!!res.offline} base=${TempoAPI.base()}`);
  }
  renderStatus();
}

async function syncNow() {
  const raw = await evalScript("tempoListFootage()");
  dbg(`sync: evalScript raw type=${typeof raw} len=${(raw || "").length} raw=${String(raw).slice(0, 300)}`);
  if (raw === null) dbg("sync: host returned null (CSInterface missing or panel outside AE?)");
  else if (raw === "") dbg("sync: host returned EMPTY string (host.jsx not loaded — reinstall panel + restart AE)");
  let footages = [];
  try { footages = JSON.parse(raw) || []; } catch (e) { dbg(`sync: JSON.parse failed: ${e}`); footages = []; }
  dbg(`sync: parsed footages=${footages.length} ${footages.slice(0, 3).map((f) => f.path).join(" | ")}`);
  const res = await TempoAPI.sync(footages);
  dbg(`sync: POST /sync ok=${res.ok} status=${res.status} offline=${!!res.offline} body=${JSON.stringify(res.body).slice(0, 300)}`);
  store.online = res.ok;
  if (res.ok) await refreshHealth();
  else renderStatus();
  if (!res.ok) {
    showError(res.offline ? "SERVICE_OFFLINE" : "SYNC_FAILED", res.offline ? "service offline" : "status " + res.status);
    return;
  }
  showError(null);
  const b = res.body;
  $("sync-summary").textContent =
    `+${b.added.length} ~${b.changed.length} -${b.removed.length} =${b.unchanged.length}`;
  dbg(`sync: diff +${b.added.length} ~${b.changed.length} -${b.removed.length} =${b.unchanged.length} jobs=${JSON.stringify(b.jobs)} uploads=${JSON.stringify(b.uploads)}`);
  if (!footages.length) dbg("sync: 0 footages from host — check AE project has FileSource footage (not solid/sequence/missing) + host.jsx loaded");
  for (const id of b.jobs) {
    store.jobs[id] = { job_id: id, state: "queued", stages: [] };
  }
  store.activeJobs = [...new Set([...store.activeJobs, ...b.jobs])];
  renderJobs();
  const fl = await TempoAPI.footage();
  dbg(`sync: GET /footage ok=${fl.ok} count=${fl.ok ? (fl.body || []).length : "?"}`);
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
      dbg(`jobs: id=${id} poll FAIL status=${res.status} offline=${!!res.offline}`);
      still.push(id); continue;
    }
    store.jobs[id] = res.body;
    dbg(`jobs: id=${id} state=${res.body.state} stages=${(res.body.stages || []).map((s) => `${s.name}:${s.state}`).join(",")}`);
    if (["running", "queued", "uploading", "queued-for-backend"].includes(res.body.state)) still.push(id);
  }
  store.activeJobs = still;
  renderJobs();
  if (!still.length) {
    const fl = await TempoAPI.footage();
    if (fl.ok) { store.footages = fl.body || []; renderFilter(); }
  }
}

async function doSearch() {
  const q = $("q").value.trim();
  if (!q) return;
  store.searching = true;
  showError(null);
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
    dbg(`search: q=${JSON.stringify(q)} FAIL code=${code} status=${res.status} offline=${!!res.offline}`);
    showError(code, res.offline ? "service offline" : "status " + res.status);
    store.results = [];
  } else {
    store.results = res.body.results || [];
    dbg(`search: q=${JSON.stringify(q)} ok results=${store.results.length} took_ms=${res.body.took_ms}`);
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
    dbg(`insert: payload=${payload.slice(0, 200)} raw=${String(raw).slice(0, 200)}`);
    try {
      const out = JSON.parse(raw);
      if (!out || !out.ok) { dbg(`insert: FAIL ${JSON.stringify(out).slice(0, 200)}`); showError("INSERT_FAILED", out && out.error); }
      else { dbg(`insert: ok comp=${out.comp_id} layer=${out.layer_id}`); showError(null); }
    } catch (e) {
      dbg(`insert: bad host response raw=${String(raw).slice(0, 200)}`);
      showError("INSERT_FAILED", "bad host response");
    }
  } finally {
    store.inserting = -1;
    renderResults();
  }
}

/* ---------- boot ---------- */

const PANEL_VERSION = "0.2.1";

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
  if (!cs) { dbg("loader: no CSInterface, skipping", true); return; }
  const kind = await probe("typeof tempoListFootage");
  if (kind === "function") { dbg("loader: host present via ScriptPath, no action", true); return; }
  dbg(`loader: host missing (typeof=${kind}), fetching sources from service`, true);
  const needJson2 = (await probe("typeof JSON")) !== "object";
  for (const name of needJson2 ? ["json2", "host"] : ["host"]) {
    const res = await TempoAPI.hostJs(name);
    dbg(`loader: GET /host/${name}.jsx ok=${res.ok} status=${res.status} bytes=${(res.text || "").length}`);
    if (!res.ok || !res.text) { dbg(`loader: fetch ${name} failed, host stays missing`, true); return; }
    const applied = await new Promise((resolve) => {
      try { cs.evalScript(res.text, () => resolve(true)); }
      catch (e) { resolve(false); }
    });
    dbg(`loader: evalScript ${name} sent=${applied}`);
  }
  const after = await probe("typeof tempoListFootage");
  dbg(`loader: typeof tempoListFootage=${after} (want function)`, true);
}

async function boot() {
  dbg(`boot: panel=${PANEL_VERSION} cs=${cs ? "yes" : "NO"} base=${TempoAPI.base()}`, true);
  try {
    cs.evalScript("1+1", (r) => dbg(`boot: bridge 1+1=${r} (want 2)`, true));
  } catch (e) { dbg(`boot: bridge probe throw ${e}`, true); }
  try {
    cs.evalScript("typeof tempoListFootage", (r) => dbg(`boot: typeof tempoListFootage=${r} (want function)`, true));
  } catch (e) { dbg(`boot: host probe throw ${e}`, true); }
  try {
    cs.evalScript("typeof JSON", (r) => dbg(`boot: host typeof JSON=${r} (want object; undefined=json2.js failed)`, true));
  } catch (e) { dbg(`boot: JSON probe throw ${e}`, true); }
  await ensureHost();
  applyTheme();
  $("sync-now").addEventListener("click", () => { dbg("ui: Sync now clicked"); syncNow(); });
  $("q").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  $("footage-filter").addEventListener("change", (e) => { store.filter = e.target.value; });
  renderStatus();
  renderResults();
  refreshHealth().then(() => syncNow());
  setInterval(syncNow, SYNC_POLL_MS);   // project sync poll (AGENTS.md D2)
  setInterval(pollJobs, JOB_POLL_MS);   // job progress poll while jobs run
}

window.addEventListener("error", (e) => {
  try { console.log("[Tempo] window.onerror: " + (e && e.message)); } catch (_e) { /* ignore */ }
});
document.addEventListener("DOMContentLoaded", boot);
