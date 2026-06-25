# Adobe Premiere UXP Plugin Development Guide

> Agent reference for building Premiere Pro plugins using the Unified Extensibility Platform (UXP).  
> Source of truth: https://developer.adobe.com/premiere-pro/uxp/  
> Last updated: June 2026

---

## TL;DR

- **UXP** is a JavaScript-based (ES6) extensibility platform for Adobe CC apps (Premiere v25.6+).
- Plugins are built with **HTML + CSS + JS**, packaged as `.ccx` files, loaded via the **UXP Developer Tool (UDT v2.2+)**.
- Two plugin types: **Commands** (menu items) and **Panels** (dockable UI).
- Manifest version is **5**. All network/filesystem/shell access requires explicit **permission declarations** in `manifest.json`.
- The UXP runtime is **not a browser** — many web APIs are unavailable or limited.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Plugin Architecture](#plugin-architecture)
- [Manifest Reference](#manifest-reference)
- [Development Workflow](#development-workflow)
- [Core Concepts](#core-concepts)
- [Premiere DOM API](#premiere-dom-api)
- [UI Building](#ui-building)
- [File System Operations](#file-system-operations)
- [Network Operations](#network-operations)
- [Launching External Processes](#launching-external-processes)
- [Inter-Plugin Communication](#inter-plugin-communication)
- [Packaging & Distribution](#packaging--distribution)
- [Best Practices](#best-practices)
- [Common Pitfalls](#common-pitfalls)

---

## Prerequisites

| Software | Minimum Version |
|---|---|
| Adobe Premiere Pro | v25.6 |
| UXP Developer Tool (UDT) | v2.2 |
| Code Editor | VS Code or Cursor recommended |

**Enable Developer Mode** in Premiere: Settings → Plugins → "Enable developer mode" checkbox → Restart Premiere.

**Enable Developer Mode** in UDT: Launch UDT, it auto-enables on first launch.

---

## Plugin Architecture

### Commands vs Panels

| Feature | Command | Panel |
|---|---|---|
| UI | Optional (modal dialog) | Persistent, dockable |
| Trigger | Menu item (Window > UXP Plugins) | Window > UXP Plugins or workspace dock |
| Lifecycle hooks | None | create, show, hide, destroy |
| Use case | One-shot actions, automation | Persistent tools, search interfaces |

A plugin can define **multiple commands and/or panels**.

### Standard File Structure

```
my-plugin/
├── manifest.json     ← Plugin configuration (REQUIRED)
├── index.html        ← UI markup (panel entry point)
├── index.js          ← Application logic
├── style.css         ← Styling
├── icons/            ← Plugin/panel icons
│   ├── plugin-icon.png
│   ├── dark.png
│   └── light.png
└── fragments/        ← Optional: external HTML/CSS for dialogs
    ├── dialog.html
    └── styles.css
```

The `main` property in the manifest defaults to `index.html` if not specified.

---

## Manifest Reference

The `manifest.json` is located at the root of the plugin bundle and is the **only required file**.

### Minimal Example

```json
{
  "manifestVersion": 5,
  "id": "com.example.myplugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "main": "index.html",
  "host": { "app": "premierepro", "minVersion": "25.6.0" },
  "entrypoints": [
    {
      "type": "panel",
      "id": "mainPanel",
      "label": { "default": "My Panel" },
      "minimumSize": { "width": 400, "height": 400 },
      "maximumSize": { "width": 800, "height": 800 },
      "preferredDockedSize": { "width": 400, "height": 400 },
      "preferredFloatingSize": { "width": 600, "height": 600 }
    }
  ]
}
```

### Required Properties

| Property | Type | Description |
|---|---|---|
| `manifestVersion` | `5` | Must be `"5"` for Premiere |
| `id` | `string` | Unique plugin identifier. Must match Developer Distribution portal ID for marketplace submission |
| `name` | `string` or `LocalizedString` | Display name in UI |
| `version` | `string` | Semver format: `major.minor.patch` |
| `host` | `HostDefinition` | Target host app and version |
| `entrypoints` | `EntrypointDefinition[]` | At least one command or panel |

### Optional Properties

| Property | Type | Description |
|---|---|---|
| `main` | `string` | Entry file (default: `"index.js"`). Can be `.html` or `.js` |
| `icons` | `IconDefinition[]` | Plugin/panel icons |
| `strings` | `StringsDefinition` | Localization strings |
| `requiredPermissions` | `PermissionsDefinition` | Permissions for network, filesystem, etc. |
| `featureFlags` | `FeatureFlags` | Enable experimental features |
| `addon` | `object` | Hybrid plugin C++ addon config |

### Host Definition

```json
"host": { "app": "premierepro", "minVersion": "25.6.0" }
```

- `app` must be `"premierepro"` for Premiere plugins
- During development only, you can use an array of hosts for cross-app testing:
  ```json
  "host": [
    { "app": "premierepro", "minVersion": "25.6.0" },
    { "app": "PS", "minVersion": "25.0.0" }
  ]
  ```
  UDT auto-converts to the first host for packaging.

### Entrypoint Definitions

```json
{
  "type": "panel",         // or "command"
  "id": "uniqueId",        // unique within plugin
  "label": { "default": "Display Name" },
  "minimumSize": { "width": 400, "height": 400 },
  "maximumSize": { "width": 800, "height": 800 },
  "preferredDockedSize": { "width": 400, "height": 400 },
  "preferredFloatingSize": { "width": 600, "height": 600 },
  "description": "Optional tooltip text",
  "icon": { /* IconDefinition */ }
}
```

- **Panel sizing**: Lock size by setting `minimumSize` equal to `maximumSize`
- **Keyboard shortcuts**: Not yet available in Premiere (defined via `shortcut` property but ignored)
- **hideFromMenu**: Set `"hideFromMenu": true` in `hostUIContext` to create a plugin that runs at launch but doesn't appear in menus

### Permissions

Permissions not declared are **denied by default**. Users are asked for consent at runtime for `openExternal()`, `openPath()`, and `<sp-link>` anchors.

```json
"requiredPermissions": {
  "network": {
    "domains": ["https://api.example.com", "https://*.adobe.io"]
  },
  "localFileSystem": "request",
  "clipboard": "readAndWrite",
  "launchProcess": {
    "schemes": ["https", "mailto"],
    "extensions": [".pdf", ".mp4", ""]
  },
  "ipc": { "enablePluginCommunication": true },
  "enableAddon": false
}
```

#### Permission Levels

| Permission | Values | Description |
|---|---|---|
| `localFileSystem` | `"plugin"` (default), `"request"`, `"fullAccess"` | Filesystem access scope |
| `network` | `{ "domains": [...] }` or `{ "domains": "all" }` | Network domain allowlist |
| `clipboard` | `"read"`, `"readAndWrite"` | Clipboard access |
| `launchProcess` | `{ "schemes": [...], "extensions": [...] }` | External process launching |
| `ipc` | `{ "enablePluginCommunication": true }` | Inter-plugin communication |
| `allowCodeGenerationFromStrings` | `boolean` | Required for inline event handlers (`onclick`) |
| `enableUserInfo` | `boolean` | Access to anonymized user GUID |
| `enableAddon` | `boolean` | Load C++ native addons |

#### Network Permission Examples

```json
// Specific domains
"network": {
  "domains": [
    "https://api.example.com",
    "https://*.adobe.io",
    "wss://ws.example.com"
  ]
}

// All domains (use sparingly)
"network": { "domains": "all" }
```

- Wildcards supported: `"https://api.*.example.com"`
- Any request to an unlisted domain fails with a permission error
- macOS restricts `http://` — always use `https://`

### Feature Flags

```json
"featureFlags": {
  "enableFillAsCustomAttribute": true,
  "enableSWCSupport": true,
  "enableAlerts": true
}
```

| Flag | Description |
|---|---|
| `enableSWCSupport` | Enable Spectrum Web Components (requires npm install + bundler) |
| `enableAlerts` | Enable `alert()`, `confirm()`, `prompt()` methods |
| `enableFillAsCustomAttribute` | CSS variable support in SVG fill attributes |

### Localization

```json
{
  "strings": {
    "my-plugin": {
      "default": "My Plugin",
      "fr": "Mon Plugin",
      "it": "Il mio Plugin"
    }
  }
}
```

Use `LocalizedString` keys anywhere a label is expected:

```json
"label": { "default": "Settings" }
```

### Icons

```json
{
  "icons": [
    {
      "width": 48,
      "height": 48,
      "path": "icons/plugin-icon.png",
      "scale": [1, 2],
      "theme": ["darkest", "dark", "medium", "lightest", "light", "all"],
      "species": ["pluginList"]
    }
  ]
}
```

- **species**: `"generic"`, `"toolbar"` (23x23px), `"pluginList"` (24x24px)
- **theme**: `"all"`, `"lightest"`, `"light"`, `"medium"`, `"dark"`, `"darkest"`
- **scale**: Supports `[1, 2, 2.5]` — UDT auto-selects `@1x.png`, `@2x.png`, `@2.5x.png`

---

## Development Workflow

### 1. Scaffold a Plugin

Open UDT → Click **Create Plugin**:

| Field | Value |
|---|---|
| Name | My Plugin |
| Host Application | Adobe Premiere |
| Host Application Version | 25.6 |
| Template | `premierepro-quick-starter` |

Select a folder → UDT creates the plugin directory with `manifest.json`, `index.html`, `index.js`, `README.md`.

### 2. Load into Premiere

In UDT, click **Load & Watch** on your plugin row:

- Plugin loads in Premiere
- UDT watches for source code changes and auto-reloads

> **Manifest changes** require manual unload + reload (not auto-detected).

### 3. Edit & Iterate

- Edit `index.html` / `index.js` / `style.css` in your editor
- UDT's Watch & Reload applies changes instantly
- View plugin from Premiere: **Window > UXP Plugins > Your Plugin Name**

### 4. Debug

- **UDT Console**: Open Logs panel in UDT for `console.log/warn/error` output
- **UDT Debugger**: Full Chrome DevTools integration with breakpoints
- **Quick debugging**: Use `console.log()` statements
- **Dialog debugging**: Use `alert()` / `confirm()` / `prompt()` (requires `enableAlerts` feature flag)

```js
console.log("Plugin initialized");
console.warn("Deprecated feature used");
console.error("Failed to load data:", error);
```

### 5. Package

In UDT → Click **•••** → **Package** → Select destination folder → Creates `PluginName.ccx`.

---

## Core Concepts

### entrypoints.setup()

The central method for wiring lifecycle hooks, commands, and panels. **Can only be called once.**

```js
const { entrypoints } = require("uxp");

entrypoints.setup({
  plugin: {
    create()  { console.log("Plugin created"); },
    destroy() { console.log("Plugin destroyed"); }
  },
  panels: {
    mainPanel: {
      create(rootNode)  { /* Panel created */ },
      show(rootNode)    { /* Panel shown */ },
      hide(rootNode)    { /* Panel hidden (not reliable yet in Premiere) */ },
      destroy(rootNode) { /* Panel destroyed */ }
    }
  },
  commands: {
    myCommand: (evt) => { console.log("Command invoked!", evt.type); }
  }
});
```

### Lifecycle Hooks

#### Plugin-Level

| Hook | When | Receives |
|---|---|---|
| `create()` | Plugin container created | Nothing |
| `destroy()` | Plugin container destroyed | Nothing |

#### Panel-Level

| Hook | When | Receives |
|---|---|---|
| `create(rootNode)` | Panel created | HTML document root node |
| `show(rootNode)` | Panel shown/activated | HTML document root node |
| `hide(rootNode)` | Panel hidden | HTML document root node |
| `destroy(rootNode)` | Panel destroyed | HTML document root node |

- Most hooks can return a **Promise** (async supported, 300ms timeout)
- `hide()` and `destroy()` are **not reliable yet in Premiere** — use `show()` for setup

#### Example with Promises

```js
entrypoints.setup({
  panels: {
    mainPanel: {
      create(rootNode) {
        return new Promise((resolve) => {
          console.log("Panel created", rootNode);
          resolve();
        });
      },
      show(rootNode) {
        return new Promise((resolve) => {
          console.log("Panel shown");
          resolve();
        });
      }
    }
  }
});
```

### Command Handlers

Commands execute when the user clicks **Window > UXP Plugins > Your Plugin > Command Name**.

```js
entrypoints.setup({
  commands: {
    myCommand: (evt) => {
      console.log("Command invoked!", evt.type); // "uxpcommand"
    }
  }
});
```

Or listen at body level:

```js
document.body.addEventListener("uxpcommand", (event) => { /* ... */ });
```

### Alternative: module.exports (commands-only plugins)

For plugins with only commands and no UI, set `main` to `index.js`:

```json
{
  "main": "index.js",
  "entrypoints": [{ "type": "command", "id": "myCommand", "label": { "default": "Run" } }]
}
```

```js
module.exports = {
  commands: {
    myCommand: () => { console.log("Running!"); }
  }
};
```

### Modal Dialogs

Modal dialogs are `<dialog>` elements launched with `uxpShowModal()`. They block interaction with Premiere until dismissed.

#### Basic Modal

```html
<!-- index.html -->
<sp-button id="openBtn">Open Dialog</sp-button>

<dialog id="myDialog">
  <sp-heading>Hello Modal!</sp-heading>
  <sp-divider size="L"></sp-divider>
  <sp-body>Dialog content</sp-body>
  <sp-button-group>
    <sp-button id="cancelBtn">Cancel</sp-button>
    <sp-button id="okBtn">OK</sp-button>
  </sp-button-group>
</dialog>
```

```js
// index.js
const dialog = document.getElementById("myDialog");

document.getElementById("openBtn").addEventListener("click", async () => {
  const result = await dialog.uxpShowModal({
    title: "My Dialog",
    resize: "none",
    size: { width: 300, height: 300 }
  });
  console.log("Dialog result:", result); // "ok", "cancel", or "reasonCanceled"
});

document.getElementById("okBtn").addEventListener("click", () => {
  dialog.close("ok");
});

document.getElementById("cancelBtn").addEventListener("click", () => {
  dialog.close("cancel");
});
```

#### uxpShowModal() Options

| Option | Type | Description |
|---|---|---|
| `title` | `string` | Dialog title |
| `titleVisibility` | `"show"` or `"none"` | Show/hide title |
| `resize` | `"none"`, `"both"`, `"horizontal"`, `"vertical"` | Resize behavior |
| `size` | `{ width, height }` | Initial size |
| `minSize` | `{ width, height }` | Minimum size |
| `maxSize` | `{ width, height }` | Maximum size |

#### Dialog Return Values

- `"ok"` — User clicked OK
- `"cancel"` — User clicked Cancel
- `"reasonCanceled"` — User closed via title bar X or Esc key

> Always handle `"reasonCanceled"` for consistent UX.

#### Multiple Modals

You can have multiple `<dialog>` elements — only one can be open at a time.

#### Singleton Pattern for Complex Dialogs

Recommended for production dialogs. Prevents duplicate DOM elements and event listeners:

```js
class ModalDialog {
  static #instance;
  #dialog;

  constructor() {
    if (ModalDialog.#instance) return ModalDialog.#instance;
    ModalDialog.#instance = this;
  }

  static getInstance() {
    if (!ModalDialog.#instance) ModalDialog.#instance = new ModalDialog();
    return ModalDialog.#instance;
  }

  async createDialog() {
    if (!document.querySelector("#my-dialog")) {
      this.#dialog = document.createElement("dialog");
      this.#dialog.id = "my-dialog";
      this.#dialog.innerHTML = (
        await fetch("./fragments/dialog.html").then(r => r.text())
      ).trim();
      document.body.appendChild(this.#dialog);
    } else {
      this.#dialog = document.querySelector("#my-dialog");
    }
  }

  initDialog() {
    // Set default values, attach event listeners (only once)
    this.#dialog.querySelector("#okBtn").addEventListener("click", () => {
      this.#dialog.close("ok");
    });
  }

  async runDialog() {
    const rv = await this.#dialog.uxpShowModal({
      title: "Settings", resize: "none", size: { width: 300, height: 200 }
    });
    if (rv === "ok") { /* run routine */ }
    if (rv === "cancel" || rv === "reasonCanceled") throw "cancel";
  }
}

// Usage
const dialog = ModalDialog.getInstance();
await dialog.createDialog();
dialog.initDialog();
await dialog.runDialog();
```

---

## Premiere DOM API

Access the Premiere DOM via:

```js
const app = require("premierepro");
```

### Key Characteristics

- All property access is **synchronous** (despite being async under the hood)
- Method calls are **asynchronous** — use `await`
- No blocking of the UI thread (unlike ExtendScript)

### Getting Project & Sequence

```js
const app = require("premierepro");

async function getActiveInfo() {
  const project = await app.Project.getActiveProject();
  const sequence = await project.getActiveSequence();

  console.log("Project:", project.name);
  console.log("Sequence:", sequence.name);
  console.log("Duration:", sequence.duration);
}
```

### Working with Sequences & Tracks

```js
async function inspectSequence() {
  const project = await app.Project.getActiveProject();
  const sequence = await project.getActiveSequence();

  // Get video tracks
  const videoTracks = sequence.getVideoTracks();
  for (const track of videoTracks) {
    console.log(`Track: ${track.name}`);
    const clips = track.clips;
    for (const clip of clips) {
      console.log(`  Clip: ${clip.name}, In: ${clip.inPoint}, Out: ${clip.outPoint}`);
    }
  }

  // Get audio tracks
  const audioTracks = sequence.getAudioTracks();
  for (const track of audioTracks) {
    console.log(`Audio Track: ${track.name}`);
  }
}
```

### Markers

```js
async function getMarkers() {
  const project = await app.Project.getActiveProject();
  const sequence = await project.getActiveSequence();
  const markers = sequence.markers;

  for (let i = 0; i < markers.numMarkers; i++) {
    const marker = markers[i];
    console.log(`Marker: ${marker.name}, Time: ${marker.time}, Comments: ${marker.comments}`);
  }
}
```

### Project Items

```js
async function getProjectItems() {
  const project = await app.Project.getActiveProject();
  const rootBin = project.rootBin;

  function listItems(bin, depth = 0) {
    for (let i = 0; i < bin.numItems; i++) {
      const item = bin[i];
      const indent = "  ".repeat(depth);
      if (item.type === " bins ") {
        console.log(`${indent}📁 ${item.name}`);
        listItems(item, depth + 1);
      } else {
        console.log(`${indent}🎞️ ${item.name}`);
      }
    }
  }

  listItems(rootBin);
}
```

### Running Menu Items

```js
const app = require("premierepro");

async function runMenuCommand() {
  await app.System.runMenuCommand("File > Save");
}
```

---

## UI Building

### Three UI Approaches

#### 1. Plain HTML Elements

Standard HTML with custom CSS. Full control but requires manual styling.

```html
<div class="container">
  <h4>My Plugin</h4>
  <input type="text" id="searchInput" placeholder="Search..." />
  <button id="searchBtn">Search</button>
  <div id="results"></div>
</div>
```

#### 2. Spectrum UXP Widgets (Built-in)

Adobe's design system components, built into UXP. No installation needed.

```html
<sp-button variant="primary">Click me</sp-button>
<sp-textfield>
  <sp-label slot="label">Search</sp-label>
</sp-textfield>
<sp-divider size="L"></sp-divider>
<sp-heading>Results</sp-heading>
<sp-body>Content here</sp-body>
```

Available widgets: buttons, textfields, sliders, dropdowns, checkboxes, radio buttons, switches, tabs, dividers, headings, body text, badges, cards, etc.

#### 3. Spectrum Web Components (SWC)

Full Adobe Spectrum Web Components library. Requires npm install + bundler (Webpack/Esbuild).

```bash
npm i @swc-uxp-wrappers/button
```

```js
import '@swc-uxp-wrappers/button/sp-button.js';
```

```html
<sp-button variant="primary">SWC Button</sp-button>
```

> Requires `enableSWCSupport: true` in `featureFlags`.

#### You Can Mix All Three

```html
<form>
  <sp-banner>
    <div slot="header">Header text</div>
    <div slot="content">Content</div>
  </sp-banner>
  <sp-button variant="primary">SWC Button</sp-button>
  <button>Plain HTML Button</button>
</form>
```

### Theme Awareness

Premiere supports Light, Dark, and Darkest themes. Detect and adapt:

```js
function updateTheme(theme) {
  document.body.classList.remove("theme-light", "theme-dark");
  document.body.classList.add(theme.includes("dark") ? "theme-dark" : "theme-light");
}

document.theme.onUpdated.addListener(updateTheme);
updateTheme(document.theme.getCurrent());
```

```css
body.theme-light {
  --text-color: #2c2c2c;
  --bg-color: #ffffff;
}
body.theme-dark {
  --text-color: #f5f5f5;
  --bg-color: #2c2c2c;
}
body { color: var(--text-color); background: var(--bg-color); }
```

> UXP CSS variables like `--uxp-host-text-color` are **not yet supported** in Premiere.

### CSS Limitations

- **Not a browser** — many CSS properties are unsupported
- **No CSS Grid** — use Flexbox instead
- CSS preprocessors (Sass/SCSS) must be transpiled before bundling
- Check the [CSS Reference](https://developer.adobe.com/premiere-pro/uxp/uxp-api/reference-css/) for supported properties

### Creating Elements Dynamically

```js
// Spectrum widgets
const button = document.createElement("sp-button");
button.textContent = "Click me";
button.setAttribute("variant", "cta");
document.body.appendChild(button);

// Standard HTML
const div = document.createElement("div");
div.textContent = "Dynamic content";
document.body.appendChild(div);
```

> SWC components must be defined in HTML markup, not created with `createElement()`.

---

## File System Operations

### Sandbox Model

By default, plugins can only access their own sandbox:

| Folder | Path | Access |
|---|---|---|
| Plugin folder | `plugin:/` | Read-only |
| Data folder | `plugin-data:/` | Read-write (persistent, cleared on uninstall) |
| Temp folder | `plugin-temp:/` | Read-write (may be cleared automatically) |

### Two APIs

#### LocalFileSystem (Object-oriented)

```js
const { localFileSystem, types } = require("uxp").storage;

// Read a file from sandbox
const file = await localFileSystem.getEntryWithUrl("plugin:/config.json");
const content = await file.read();

// Write to data folder
const dataFile = await localFileSystem.getEntryWithUrl("plugin-data:/state.json");
await dataFile.write(JSON.stringify({ key: "value" }));

// Create folder
const folder = await localFileSystem.createEntryWithUrl(
  "plugin-temp:/myFolder",
  { type: types.folder }
);
```

#### fs Module (Path-based)

```js
const fs = require("fs");

// Read
const content = await fs.readFile("plugin:/config.json", "utf8");

// Write
await fs.writeFile("plugin-data:/state.json", JSON.stringify(data), "utf-8");
```

### User-Selected Files (permission: `"request"`)

```js
const { localFileSystem, domains, fileTypes } = require("uxp").storage;

// Open file picker
const file = await localFileSystem.getFileForOpening({
  initialDomain: domains.userDesktop,
  types: fileTypes.text
});
if (file) {
  const content = await file.read();
}

// Save file picker
const saveFile = await localFileSystem.getFileForSaving("export.txt", {
  types: ["txt"]
});
if (saveFile) {
  await saveFile.write("Exported content");
}

// Folder picker
const folder = await localFileSystem.getFolder({
  initialDomain: domains.userDocuments
});
```

### Persistent Tokens

Remember user-selected files across sessions:

```js
// Create token after user selects file
const token = await localFileSystem.createPersistentToken(file);
localStorage.setItem("fileToken", token);

// Re-access later
const savedToken = localStorage.getItem("fileToken");
const file = await localFileSystem.getEntryForPersistentToken(savedToken);
```

### Full Access (permission: `"fullAccess"`)

```js
// macOS
const file = await localFileSystem.getEntryWithUrl("file:/Users/user/Documents/config.json");

// Windows
const file = await localFileSystem.getEntryWithUrl("file:/C:/Users/user/Documents/config.json");
```

> Users may be hesitant to grant `"fullAccess"`. Prefer `"request"` when possible.

---

## Network Operations

### fetch() (Recommended)

```js
async function fetchData() {
  try {
    const response = await fetch("https://api.example.com/data", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "hello" })
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    console.log("Response:", data);
  } catch (err) {
    console.error("Fetch failed:", err);
  }
}
```

### XMLHttpRequest

```js
function fetchDataXHR() {
  const xhr = new XMLHttpRequest();
  xhr.open("GET", "https://api.example.com/data");
  xhr.responseType = "json";

  xhr.onload = () => {
    if (xhr.status === 200) {
      console.log("Data:", xhr.response);
    }
  };

  xhr.onerror = () => console.error("Network error");
  xhr.send();
}
```

### WebSocket

```js
let socket;

function connectWS() {
  socket = new WebSocket("wss://example.com/ws");

  socket.onopen = () => {
    console.log("Connected");
    socket.send("Hello from plugin!");
  };

  socket.onmessage = (event) => {
    console.log("Received:", event.data);
  };

  socket.onclose = () => { socket = null; };
}
```

> Plugins can only be WebSocket **clients**, not servers.

### Timeout Pattern

```js
async function safeFetch(url, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("Request failed:", err);
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}
```

### Limitations

- No `TextDecoder` for streaming responses
- CORS restrictions apply — server must allow UXP origins
- All domains must be in `requiredPermissions.network.domains`
- macOS requires HTTPS

---

## Launching External Processes

Requires `launchProcess` permission and user consent via dialog.

### Open File

```js
const { shell } = require("uxp");

// Open file in default application
const result = await shell.openPath(
  "/Users/user/Desktop/report.pdf",
  "Opening project report for review"
);
if (result === "") console.log("Opened successfully");

// Open folder in Finder/Explorer (use empty string "" in extensions)
const folderResult = await shell.openPath(
  "/Users/user/Documents/Projects",
  "Opening project folder"
);
```

### Open URL

```js
const { shell } = require("uxp");

// Open website
await shell.openExternal("https://example.com", "Opening documentation");

// Open email compose
await shell.openExternal(
  "mailto:user@example.com?subject=Feedback&body=Hello",
  "Opening mail client"
);

// macOS Maps
await shell.openExternal("maps://?address=345+Park+Ave+San+Jose", "Opening Maps");
```

### Platform-Specific URL Schemes

| Scheme | Platform | Purpose |
|---|---|---|
| `https://` | Both | Web browser |
| `mailto:` | Both | Email |
| `maps://` | macOS | Apple Maps |
| `bingmaps:` | Windows | Bing Maps |
| `facetime:` | macOS | FaceTime |

```js
const isMac = require("os").platform() === "darwin";
const scheme = isMac ? "maps://" : "bingmaps:";
```

### Run CLI Commands

```js
// Run shell command (limited — no args, no output capture)
const result = await shell.openPath("/bin/ls", "Listing directory");
```

> Cannot pass arguments or capture output. Consider spawning via other means for complex needs.

---

## Inter-Plugin Communication

Plugins within Premiere can communicate with each other via the `pluginManager` API.

### Requester Plugin (Initiator)

```js
const { pluginManager } = require("uxp");

// Find the other plugin by ID
const allPlugins = pluginManager.plugins;
const responder = Array.from(allPlugins).find(p => p.id === "responder-plugin-id");

if (responder && responder.enabled) {
  // Show its panel
  responder.showPanel("panelId");

  // Invoke its command
  responder.invokeCommand("commandId");

  // Send data payload
  responder.invokeCommand("commandId", { message: "Hello!" });
}
```

Requires `"ipc": { "enablePluginCommunication": true }` permission.

### Responder Plugin (Receiver)

No special permissions needed. Just expose commands in the manifest and handle them:

```js
entrypoints.setup({
  commands: {
    myCommand: (evt) => {
      console.log("Received:", evt.data);
    }
  }
});
```

### Notes

- Payloads cannot contain functions
- Check `plugin.enabled` before invoking
- Use `plugin.manifest.commands` / `plugin.manifest.panels` to discover available entrypoints
- Cross-application communication (e.g., Premiere to Photoshop) is **not supported**
- Panels can only be shown, not hidden, via API

---

## Packaging & Distribution

### CCX Format

Plugins are packaged as `.ccx` files (ZIP under the hood). UDT handles packaging automatically.

> No need for digital signatures or timestamps (unlike CEP `.zzp` files).

### Package with UDT

1. Plugin must be in UDT workspace (doesn't need to be loaded)
2. Click **•••** → **Package**
3. Select destination folder
4. Output: `PluginName.ccx`

### Distribution Channels

| Channel | Review Required | Discoverability |
|---|---|---|
| **Creative Cloud Marketplace** | Yes (Adobe review) | CC Desktop app |
| **Direct Distribution** | No | GitHub, website, third-party stores |
| **Enterprise** | No | Internal deployment |

### Multi-Channel Distribution

If distributing through both Marketplace and third-party channels, use **different plugin IDs** for each channel to avoid installation conflicts with CC Desktop.

### Hybrid Plugin Packaging

For C++ addons, ensure correct directory structure:

```
my-plugin/
├── manifest.json
├── index.html
├── index.js
└── addons/
    ├── mac/
    │   ├── arm64/
    │   │   └── sample.uxpaddon
    │   └── x64/
    │       └── sample.uxpaddon
    └── win/
        └── x64/
            └── sample.uxpaddon
```

Marketplace requires **all three architectures** (macOS arm64, macOS x64, Windows x64).

### Testing Installation

Always test the `.ccx` installation before distributing:
1. Double-click the `.ccx` file
2. Creative Cloud Desktop handles installation
3. Plugin appears in Premiere under Window > UXP Plugins

---

## Best Practices

### Permissions
- Start with the **least restrictive** permission needed
- Prefer `"request"` over `"fullAccess"` for filesystem access
- Declare only the domains your plugin actually uses
- Users may refuse to install plugins with broad permissions

### Architecture
- Use the **Singleton pattern** for modal dialogs to prevent DOM/listener duplication
- Use `entrypoints.setup()` only once — add all entrypoints in a single call
- Use `show()` lifecycle hook for setup (not `hide()` — it's unreliable)
- Use `rootNode` parameter in panel hooks to manage DOM in multi-panel plugins

### Performance
- Clean up heavy objects in lifecycle hooks
- Use `fetch()` for network requests (Promise-based)
- Use `console.log()` for debugging — UDT captures all output
- Bundle SWC components with Webpack/Esbuild if using them

### UI/UX
- Use Spectrum widgets for consistent Adobe look and feel
- Implement theme awareness to adapt to Light/Dark/Darkest modes
- Provide clear `developerText` in shell operations for user consent dialogs
- Handle `"reasonCanceled"` in modal dialogs for consistent UX
- Test with both docked and floating panel configurations

### Security
- Never expose API keys in source code — use environment variables or server-side auth
- Validate all user input before processing
- Use HTTPS for all network requests
- Don't request permissions you don't need

### Code Organization
- Keep dialog UI in `fragments/` directory
- Use `fetch()` to load external HTML files into dialogs
- Scope CSS for modal dialogs to prevent style conflicts
- Use `require()` for local `.js` and `.json` files
- Use `fetch()` or `fs` for other file formats

---

## Common Pitfalls

| Pitfall | Solution |
|---|---|
| `entrypoints.setup()` called multiple times | Call only once — add all entrypoints in a single call |
| `hide()` / `destroy()` hooks not firing | Known Premiere limitation — use `show()` for setup instead |
| `alert()` / `confirm()` not working | Enable `enableAlerts` feature flag in manifest |
| CSS Grid not working | Use Flexbox — CSS Grid is not supported in UXP |
| `TextDecoder` undefined | Not available in UXP — use alternative approaches for stream reading |
| Network request fails silently | Domain not in `requiredPermissions.network.domains` |
| `file://` not working with `shell.openExternal()` | Use `shell.openPath()` for local files instead |
| Plugin not appearing in Premiere | Check Developer Mode is enabled, restart Premiere |
| UDT can't connect to Premiere | Ensure Premiere is running and Developer Mode is enabled |
| Inline event handlers (`onclick`) not working | Enable `allowCodeGenerationFromStrings` permission |
| SWC components not rendering | Enable `enableSWCSupport` feature flag + install + bundle + import |
| `host` as array in production | Must be a single `HostDefinition` object — arrays are dev-only |
| Manifest changes not reflected | Unload and reload plugin manually in UDT |
| `require()` doesn't work for HTML/CSS | Use `fetch()` for non-JS/JSON files |
| Dialog event listeners duplicated | Use Singleton pattern with listener attachment guards |
| Panel DOM shared across panels | Use `show()` hook to dynamically append content per panel |

---

## Key Module Imports

```js
// Premiere DOM
const app = require("premierepro");

// UXP Core
const { entrypoints } = require("uxp");
const { pluginManager } = require("uxp");
const { localFileSystem, types, domains, fileTypes } = require("uxp").storage;
const { shell } = require("uxp");
const { host, versions } = require("uxp");

// Node-compatible modules
const fs = require("fs");
const os = require("os");
const path = require("path");
```

---

## Quick Reference: Minimum Versions

| Feature | Minimum Premiere Version |
|---|---|
| UXP Plugins | 25.6 |
| Manifest v5 | 25.6 |
| Hybrid Plugins | 26.2 |
| SWC Support | UXP v7.0 (via feature flag) |

---

## Useful Links

- [Premiere UXP Documentation](https://developer.adobe.com/premiere-pro/uxp/)
- [Premiere DOM API Reference](https://developer.adobe.com/premiere-pro/uxp/ppro-reference/)
- [UXP JS API Reference](https://developer.adobe.com/premiere-pro/uxp/uxp-api/)
- [Spectrum UXP Reference](https://developer.adobe.com/premiere-pro/uxp/uxp-api/reference-spectrum/)
- [TypeScript Declarations NPM](https://github.com/adobe/premierepro-types)
- [Developer Forums](https://forums.creativeclouddeveloper.com/)
- [UXP Developer Tool Download](https://creativecloud.adobe.com/apps/download/uxp-developer-tools)
