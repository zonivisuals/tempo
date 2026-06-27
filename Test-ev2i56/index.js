const { entrypoints } = require("uxp");
const fs = require("fs");
const api = require("./js/api");
const search = require("./js/search");
const premiere = require("./js/premiere");
const storage = require("./js/storage");
const ui = require("./js/ui");

const API_URL = "https://4474-34-7-62-50.ngrok-free.app";

let panelInitialized = false;

async function loadStyles() {
  try {
    const css = await fs.readFile("plugin:/style.css", "utf8");
    const style = document.createElement("style");
    style.id = "tempo-styles";
    style.textContent = css;
    document.head.appendChild(style);
  } catch (e) {
    console.warn("Failed to load style.css:", e);
  }
}

function show(rootNode) {
  if (panelInitialized) {
    if (!rootNode.contains(ui.getPanelRoot())) {
      rootNode.appendChild(ui.getPanelRoot());
    }
    return;
  }
  panelInitialized = true;

  ui.createPanel(rootNode);
  ui.updateTheme(document.theme.getCurrent());

  ui.getSearchButton().addEventListener("click", handleSearch);
  ui.getSearchField().addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleSearch();
  });

  ui.getConnectButton().addEventListener("click", async () => {
    await checkConnection();
  });

  api.setBaseUrl(API_URL);
  checkConnection();
  restoreConnection();
}

async function checkConnection() {
  ui.setStatus("Connecting...");
  try {
    await api.checkHealth();
    ui.setStatus("Connected");
    return true;
  } catch (e) {
    console.error("Health check failed:", e);
    ui.setStatus("Disconnected: " + (e.message || "error"));
    return false;
  }
}

async function restoreConnection() {
  const indexData = await storage.loadIndexData();
  if (indexData) {
    search.loadIndex(indexData);
  }
}

async function handleSearch() {
  const query = ui.getSearchField().value.trim();
  if (!query) return;

  ui.clearResults();
  ui.setStatus("Searching...");

  let results;
  let usedFallback = false;

  try {
    const response = await api.searchQuery(query);
    results = response.results || [];
  } catch {
    usedFallback = true;
    if (!search.isLoaded()) {
      const indexData = await storage.loadIndexData();
      if (indexData) search.loadIndex(indexData);
    }
    results = search.isLoaded() ? search.search(query) : [];
  }

  if (results.length === 0) {
    ui.setStatus("No results found" + (usedFallback ? " (offline)" : ""));
    return;
  }

  results.forEach((r, i) => ui.addResult(r, i));
  ui.setStatus(results.length + " results" + (usedFallback ? " (offline)" : ""));
}

document.theme.onUpdated.addListener((theme) => {
  ui.updateTheme(theme);
});

loadStyles();

entrypoints.setup({
  panels: {
    samplePlugin: { show },
  },
  commands: {
    show_alert: {
      run: async () => {
        alert("Tempo plugin loaded");
        return "OK";
      },
      cancel: async () => {},
    },
  },
});
