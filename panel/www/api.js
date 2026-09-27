/* api.js — the single service-communication module (AGENTS.md §7.2).
 * Payload shapes mirror docs/api.md. Every fetch has a timeout; callers get
 * {ok, status, body} and render offline states themselves — no modals here. */
"use strict";

const TempoAPI = (() => {
  const DEFAULT_BASE = "http://127.0.0.1:8765";
  const TIMEOUT_MS = 10000;

  function base() {
    try {
      const saved = localStorage.getItem("tempo_service_base");
      if (saved && saved.startsWith("http")) return saved.replace(/\/$/, "");
    } catch (e) { /* localStorage unavailable — fall back */ }
    return DEFAULT_BASE;
  }

  async function req(path, opts, timeoutMs) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs || TIMEOUT_MS);
    try {
      const res = await fetch(base() + path, { ...(opts || {}), signal: ctrl.signal });
      let body = null;
      try { body = await res.json(); } catch (e) { /* non-JSON (thumbs never go here) */ }
      return { ok: res.ok, status: res.status, body };
    } catch (e) {
      return { ok: false, status: 0, body: null, offline: true };
    } finally {
      clearTimeout(timer);
    }
  }

  async function reqText(path, timeoutMs) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs || TIMEOUT_MS);
    try {
      const res = await fetch(base() + path, { signal: ctrl.signal });
      const text = await res.text();
      return { ok: res.ok, status: res.status, text };
    } catch (e) {
      return { ok: false, status: 0, text: "", offline: true };
    } finally {
      clearTimeout(timer);
    }
  }

  const qs = (o) => Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v))
    .join("&");

  return {
    base,
    health: () => req("/health"),
    footage: () => req("/footage"),
    sync: (footages) => req("/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ footages }),
    }),
    job: (id) => req("/jobs/" + encodeURIComponent(id)),
    retry: (id) => req("/jobs/" + encodeURIComponent(id) + "/retry", { method: "POST" }),
    retryFootage: (key) => req("/footage/" + encodeURIComponent(key) + "/retry", { method: "POST" }),
    search: (q, top_k, footage_keys) =>
      req("/search?" + qs({ q, top_k, footage_keys }), undefined, 25000),
    hostJs: (name) => reqText("/host/" + encodeURIComponent(name) + ".jsx"),
    thumbUrl: (key, shot_id) =>
      `${base()}/thumb/${encodeURIComponent(key)}/${shot_id}.jpg`,
  };
})();
