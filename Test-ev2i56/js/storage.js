const { localFileSystem } = require("uxp").storage;

function settingsPath() {
  return "plugin-data:/settings.json";
}

function indexPath() {
  return "plugin-data:/index.json";
}

async function saveSettings(settings) {
  const file = await localFileSystem.getEntryWithUrl(settingsPath());
  await file.write(JSON.stringify(settings, null, 2));
}

async function loadSettings() {
  try {
    const file = await localFileSystem.getEntryWithUrl(settingsPath());
    const content = await file.read();
    return JSON.parse(content);
  } catch {
    return {};
  }
}

async function saveIndexData(data) {
  const file = await localFileSystem.getEntryWithUrl(indexPath());
  await file.write(JSON.stringify(data));
}

async function loadIndexData() {
  try {
    const file = await localFileSystem.getEntryWithUrl(indexPath());
    const content = await file.read();
    return JSON.parse(content);
  } catch {
    return null;
  }
}

async function clearIndexData() {
  try {
    const file = await localFileSystem.getEntryWithUrl(indexPath());
    await file.delete();
  } catch {
    // File may not exist
  }
}

module.exports = { saveSettings, loadSettings, saveIndexData, loadIndexData, clearIndexData };
