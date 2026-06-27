let indexData = null;

function loadIndex(data) {
  indexData = data;
}

function isLoaded() {
  return indexData !== null && Array.isArray(indexData.scenes);
}

function clearIndex() {
  indexData = null;
}

function tokenize(text) {
  if (!text) return [];
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, "").split(/\s+/).filter(Boolean);
}

function buildTfidf(scenes) {
  const docCount = scenes.length;
  const df = {};
  const tfIdfVectors = [];

  for (const scene of scenes) {
    const tokens = tokenize(scene.transcript);
    const tf = {};
    for (const t of tokens) tf[t] = (tf[t] || 0) + 1;
    const maxFreq = Math.max(...Object.values(tf), 1);
    for (const t of Object.keys(tf)) tf[t] /= maxFreq;
    tfIdfVectors.push(tf);
    for (const t of Object.keys(tf)) df[t] = (df[t] || 0) + 1;
  }

  const idf = {};
  for (const t of Object.keys(df)) {
    idf[t] = Math.log((docCount + 1) / (df[t] + 1)) + 1;
  }

  return { tfIdfVectors, idf };
}

function search(query, maxResults = 20) {
  if (!isLoaded()) return [];

  const queryTokens = tokenize(query);
  if (queryTokens.length === 0) return [];

  const { tfIdfVectors, idf } = buildTfidf(indexData.scenes);

  const queryVec = {};
  for (const t of queryTokens) queryVec[t] = (queryVec[t] || 0) + 1;
  const qMax = Math.max(...Object.values(queryVec), 1);
  for (const t of Object.keys(queryVec)) {
    queryVec[t] = (queryVec[t] / qMax) * (idf[t] || 0);
  }

  const scored = indexData.scenes.map((scene, i) => {
    let dot = 0;
    let qNorm = 0;
    let dNorm = 0;
    for (const t of Object.keys(queryVec)) {
      const qv = queryVec[t];
      qNorm += qv * qv;
      const dv = tfIdfVectors[i][t] || 0;
      dot += qv * dv * (idf[t] || 0);
    }
    for (const t of Object.keys(tfIdfVectors[i])) {
      const dv = tfIdfVectors[i][t] * (idf[t] || 0);
      dNorm += dv * dv;
    }
    const mag = Math.sqrt(qNorm) * Math.sqrt(dNorm);
    const score = mag === 0 ? 0 : dot / mag;
    return { ...scene, score };
  });

  return scored
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, maxResults);
}

module.exports = { loadIndex, isLoaded, clearIndex, search };
