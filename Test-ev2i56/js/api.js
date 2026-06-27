let baseUrl = "";

function getBaseUrl() {
  return baseUrl;
}

function setBaseUrl(url) {
  baseUrl = url ? url.replace(/\/+$/, "") : "";
}

async function request(endpoint, options = {}) {
  if (!baseUrl) throw new Error("Colab URL not configured");
  const res = await fetch(`${baseUrl}${endpoint}`, { ...options });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return await res.json();
}

async function checkHealth() {
  return request("/health", { method: "GET" });
}

async function searchQuery(query) {
  return request("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

async function fetchIndex() {
  return request("/index/export", { method: "GET" });
}

module.exports = { setBaseUrl, getBaseUrl, checkHealth, searchQuery, fetchIndex };
