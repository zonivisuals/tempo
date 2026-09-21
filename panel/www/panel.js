/* panel.js — plain store + explicit render() calls (AGENTS.md §7.2).
 * No framework, no event bus. All project access via evalScript into
 * host.jsx; all service access via api.js. Polling only (AGENTS.md D2):
 * 2s project sync, 500ms job progress while jobs run. */
"use strict";

const store = {
  online: false,
  footages: [],
  jobs: {},       // job_id -> last job payload
  activeJobs: [], // job_ids still running
  results: [],
  searching: false,
  compFps: 25.0,
  filter: "",
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
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* ---------- render ---------- */

function renderStatus() {
  $("svc").textContent = store.online ? "service ok" : "service offline";
}

function renderJobs() {
  const box = $("jobs");
  const ids = Object.keys(store.jobs);
  if (!ids.length) { box.innerHTML = ""; return; }
  box.innerHTML = ids.map((id) => {
    const j = store.jobs[id];
    const rows = (j.stages || []).map((s) => {
      const pct = s.total ? Math.round((s.done / s.total) * 100) : (s.state === "done" ? 100 : 0);
      return `<div>${esc(s.name)} ${s.state}${s.total ? ` ${s.done}/${s.total}` : ""}` +
        `<div class="bar"><div style="width:${pct}%"></div></div></div>`;
    }).join("");
    const err = j.state === "error" ? `<div class="job err">${esc(j.error || "error")}</div>` : "";
    return `<div class="job"><div>Indexing ${esc(id)} · ${esc(j.state)}</div>${rows}${err}</div>`;
  }).join("");
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
  box.innerHTML = store.results.map((r, i) => {
    const bars = [
      ["dense/" + r.winning_key, r.contributions.dense],
      ["bm25", r.contributions.bm25],
      ["anchor", r.contributions.anchor],
      ["entity boost", r.contributions.entity_boost],
    ].sort((a, b) => b[1] - a[1]);
    const barHTML = bars.map(([label, val], bi) => {
      const share = r.score > 0 ? val / r.score : 0;
      return `<div class="barrow${bi === 0 ? " top" : ""}"><span>${esc(label)}</span>` +
        `<span class="track"><span class="fill" style="display:block;width:${Math.round(share * 100)}%"></span></span>` +
        `<span class="pct">${Math.round(share * 100)}%</span></div>`;
    }).join("");
    const dur = Math.max(0, r.end_s - r.start_s).toFixed(1);
    return `<div class="card" data-i="${i}">` +
      `<img src="${TempoAPI.thumbUrl(r.footage_key, r.shot_id)}" alt="">` +
      `<div><div>${esc(baseName(r.source_path))}</div>` +
      `<div class="meta tc">${fmtTC(r.start_s, store.compFps)} – ${fmtTC(r.end_s, store.compFps)} · ${dur}s</div>` +
      `<div class="snippet">${esc(r.transcript.slice(0, 120))}</div>` +
      `<div class="snippet">${esc(r.caption.slice(0, 120))}</div>` +
      `<div class="bars">${barHTML}</div></div></div>`;
  }).join("");
  box.querySelectorAll(".card").forEach((el) => {
    el.addEventListener("click", () => insertResult(store.results[Number(el.dataset.i)]));
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
}

/* ---------- actions ---------- */

async function refreshCompFps() {
  const raw = await evalScript("tempoGetActiveCompInfo()");
  try {
    const info = JSON.parse(raw);
    if (info && info.fps) store.compFps = info.fps;
  } catch (e) { /* project fps stays default */ }
}

async function syncNow() {
  const raw = await evalScript("tempoListFootage()");
  let footages = [];
  try { footages = JSON.parse(raw) || []; } catch (e) { footages = []; }
  const res = await TempoAPI.sync(footages);
  store.online = res.ok;
  renderStatus();
  if (!res.ok) {
    showError("SYNC_FAILED", res.offline ? "service offline" : "status " + res.status);
    return;
  }
  showError(null);
  const b = res.body;
  $("sync-summary").textContent =
    `+${b.added.length} ~${b.changed.length} -${b.removed.length} =${b.unchanged.length}`;
  for (const id of b.jobs) {
    store.jobs[id] = { job_id: id, state: "queued", stages: [] };
  }
  store.activeJobs = [...new Set([...store.activeJobs, ...b.jobs])];
  renderJobs();
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
    if (!res.ok) { still.push(id); continue; }
    store.jobs[id] = res.body;
    if (res.body.state === "running" || res.body.state === "queued") still.push(id);
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
    showError(code, res.offline ? "service offline" : "status " + res.status);
    store.results = [];
  } else {
    store.results = res.body.results || [];
  }
  renderResults();
}

async function insertResult(r) {
  if (!r) return;
  const payload = JSON.stringify({
    source_path: r.source_path, start_s: r.start_s, end_s: r.end_s,
  });
  // One evalScript call does the whole job (locate/import, comp, trim, playhead).
  const raw = await evalScript(`tempoInsertOrFocus(${payload})`);
  try {
    const out = JSON.parse(raw);
    if (!out || !out.ok) showError("INSERT_FAILED", out && out.error);
  } catch (e) {
    showError("INSERT_FAILED", "bad host response");
  }
}

/* ---------- boot ---------- */

function boot() {
  applyTheme();
  $("sync-now").addEventListener("click", syncNow);
  $("q").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  $("footage-filter").addEventListener("change", (e) => { store.filter = e.target.value; });
  renderStatus();
  renderResults();
  syncNow();
  setInterval(syncNow, 2000);   // project sync poll (AGENTS.md D2)
  setInterval(pollJobs, 500);   // job progress poll while jobs run
}

document.addEventListener("DOMContentLoaded", boot);
