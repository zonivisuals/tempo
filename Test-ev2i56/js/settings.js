const storage = require("./storage");

async function showSettingsDialog() {
  const existing = document.getElementById("settings-dialog");
  if (existing) existing.remove();

  const dialog = document.createElement("dialog");
  dialog.id = "settings-dialog";

  const currentSettings = await storage.loadSettings();

  const label = document.createElement("sp-body");
  label.textContent = "Colab API URL";

  const urlField = document.createElement("sp-textfield");
  urlField.setAttribute("id", "settings-url");
  urlField.setAttribute("placeholder", "https://xxxx.ngrok-free.app");
  urlField.setAttribute("value", currentSettings.colabUrl || "");

  const divider = document.createElement("sp-divider");
  divider.setAttribute("size", "M");

  const buttonGroup = document.createElement("sp-button-group");

  const cancelBtn = document.createElement("sp-button");
  cancelBtn.setAttribute("id", "settings-cancel");
  cancelBtn.textContent = "Cancel";

  const saveBtn = document.createElement("sp-button");
  saveBtn.setAttribute("id", "settings-save");
  saveBtn.setAttribute("variant", "cta");
  saveBtn.textContent = "Save";

  buttonGroup.appendChild(cancelBtn);
  buttonGroup.appendChild(saveBtn);

  dialog.appendChild(label);
  dialog.appendChild(urlField);
  dialog.appendChild(divider);
  dialog.appendChild(buttonGroup);

  document.body.appendChild(dialog);

  cancelBtn.addEventListener("click", () => dialog.close("cancel"));
  saveBtn.addEventListener("click", () => {
    const url = urlField.value.trim();
    dialog.close(url);
  });

  const result = await dialog.uxpShowModal({
    title: "Settings",
    resize: "none",
    size: { width: 400, height: 220 },
  });

  if (result && result !== "cancel" && result !== "reasonCanceled") {
    await storage.saveSettings({ colabUrl: result });
    return result;
  }
  return null;
}

module.exports = { showSettingsDialog };
