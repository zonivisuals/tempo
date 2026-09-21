/* api.js — the single service-communication module (AGENTS.md §7.2).
 * Payload shapes mirror docs/api.md. Every fetch has a timeout; callers get
 * {ok, status, body} and render offline states themselves — no modals here. */
"use strict";

const TempoAPI = (() => {
  const BASE = "http://127.0.0.1:8765";
  const TIMEOUT_MS = 10000;

  async function req(path, opts) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const res = await fetch(BASE + path, { ...(opts || {}), signal: ctrl.signal });
      let body = null;
      try { body = await res.json(); } catch (e) { /* non-JSON (thumbs never go here) */ }
      return { ok: res.ok, status: res.status, body };
    } catch (e) {
      return { ok: false, status: 0, body: null, offline: true };
    } finally {
      clearTimeout(timer);
    }
  }

  const qs = (o) => Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v))
    .join("&");

  return {
    health: () => req("/health"),
    footage: () => req("/footage"),
    sync: (footages) => req("/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ footages }),
    }),
    job: (id) => req("/jobs/" + encodeURIComponent(id)),
    search: (q, top_k, footage_keys) =>
      req("/search?" + qs({ q, top_k, footage_keys })),
    thumbUrl: (key, shot_id) =>
      `${BASE}/thumb/${encodeURIComponent(key)}/${shot_id}.jpg`,
  };
})();
