const app = require("premierepro");

async function getProject() {
  return await app.Project.getActiveProject();
}

async function getSequence() {
  const project = await getProject();
  if (!project) throw new Error("No active project");
  return await project.getActiveSequence();
}

async function addMarker(time, name, comments) {
  const sequence = await getSequence();
  if (!sequence) throw new Error("No active sequence");
  const marker = sequence.markers.createMarker(time);
  marker.name = name || "Tempo";
  marker.comments = comments || "";
  return marker;
}

async function getProjectItems() {
  const project = await getProject();
  if (!project) return [];
  const items = [];
  function walk(bin) {
    for (let i = 0; i < bin.numItems; i++) {
      const item = bin[i];
      if (item.type === "bin") {
        walk(item);
      } else {
        items.push(item);
      }
    }
  }
  walk(project.rootBin);
  return items;
}

module.exports = { getProject, getSequence, addMarker, getProjectItems };
