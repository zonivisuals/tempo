let panelRoot = null;
let searchField = null;
let searchButton = null;
let resultsContainer = null;
let statusBar = null;
let versionLabel = null;
let connectButton = null;

function getPanelRoot() { return panelRoot; }
function getSearchField() { return searchField; }
function getSearchButton() { return searchButton; }
function getResultsContainer() { return resultsContainer; }
function getStatusBar() { return statusBar; }
function getVersionLabel() { return versionLabel; }
function getConnectButton() { return connectButton; }

function updateTheme(theme) {
  const isDark = theme.includes("dark");
  if (panelRoot) {
    panelRoot.classList.toggle("theme-dark", isDark);
    panelRoot.classList.toggle("theme-light", !isDark);
  }
  document.body.classList.toggle("theme-dark", isDark);
  document.body.classList.toggle("theme-light", !isDark);
}

function createPanel(rootNode) {
  if (panelRoot) return;

  panelRoot = document.createElement("div");
  panelRoot.id = "tempo-panel";

  versionLabel = document.createElement("div");
  versionLabel.id = "version-label";
  versionLabel.textContent = "Tempo v3 • 2026-06-25";

  searchField = document.createElement("sp-textfield");
  searchField.setAttribute("placeholder", "Search footage...");
  searchField.setAttribute("id", "search-field");

  searchButton = document.createElement("sp-button");
  searchButton.setAttribute("variant", "cta");
  searchButton.textContent = "Search";

  const searchRow = document.createElement("div");
  searchRow.id = "search-row";
  searchRow.appendChild(searchField);
  searchRow.appendChild(searchButton);

  const divider = document.createElement("sp-divider");
  divider.setAttribute("size", "M");

  const connectRow = document.createElement("div");
  connectRow.id = "connect-row";

  connectButton = document.createElement("sp-button");
  connectButton.setAttribute("variant", "secondary");
  connectButton.textContent = "Connect";

  connectRow.appendChild(connectButton);

  resultsContainer = document.createElement("div");
  resultsContainer.id = "results-container";

  const bottomRow = document.createElement("div");
  bottomRow.id = "bottom-row";

  statusBar = document.createElement("div");
  statusBar.id = "status-bar";
  statusBar.textContent = "Disconnected";

  bottomRow.appendChild(statusBar);

  panelRoot.appendChild(versionLabel);
  panelRoot.appendChild(searchRow);
  panelRoot.appendChild(divider);
  panelRoot.appendChild(connectRow);
  panelRoot.appendChild(resultsContainer);
  panelRoot.appendChild(bottomRow);

  rootNode.appendChild(panelRoot);
}

function setStatus(text, isError) {
  if (!statusBar) return;
  statusBar.textContent = text;
  statusBar.classList.toggle("status-error", !!isError);
  statusBar.classList.toggle("status-ok", !isError);
}

function clearResults() {
  if (resultsContainer) {
    resultsContainer.innerHTML = "";
  }
}

function addResult(result, index) {
  if (!resultsContainer) return;
  const item = document.createElement("div");
  item.className = "result-item";
  item.innerHTML =
    '<div class="result-header">' +
      '<span class="result-index">' + (index + 1) + '</span>' +
      '<span class="result-score">' + (result.score * 100).toFixed(0) + '%</span>' +
    '</div>' +
    '<div class="result-transcript">' + (result.transcript || "No transcript") + '</div>' +
    '<div class="result-meta">' +
      (result.clip_name ? '<span>' + result.clip_name + '</span>' : '') +
      (result.timecode ? '<span>' + result.timecode + '</span>' : '') +
    '</div>';
  resultsContainer.appendChild(item);
}

module.exports = {
  getPanelRoot,
  getSearchField,
  getSearchButton,
  getResultsContainer,
  getStatusBar,
  getVersionLabel,
  getConnectButton,
  updateTheme,
  createPanel,
  setStatus,
  clearResults,
  addResult,
};
