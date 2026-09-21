/* host.jsx — ALL After Effects project access lives here (AGENTS.md §4.2).
 *
 * ExtendScript ES3 only: `var`, no let/const/arrows/template literals,
 * no Array map/forEach, no JSON (json2.js is loaded first via manifest
 * ScriptPath order). Every function returns a JSON string; errors are
 * encoded as {ok:false,error:"…"} — never thrown across the bridge.
 *
 * Verified APIs (docsforadobe After Effects scripting guide):
 *   app.project.items[i], instanceof FootageItem / CompItem,
 *   FootageItem.mainSource (FileSource).file.fsName,
 *   app.beginUndoGroup / app.endUndoGroup,
 *   Layer startTime / inPoint / outPoint, CompItem.time,
 *   Project.items.addComp, Layers.add, File.exists / ImportOptions.
 */

function tempoListFootage() {
    var out = [];
    try {
        if (!app.project) { return JSON.stringify(out); }
        var n = app.project.items.length;
        for (var i = 1; i <= n; i++) {
            var item = app.project.items[i];
            if (!(item instanceof FootageItem)) { continue; }
            var src = null;
            try { src = item.mainSource; } catch (e1) { continue; }
            if (!(src instanceof FileSource)) { continue; }
            var file = null;
            try { file = src.file; } catch (e2) { continue; }
            if (!file) { continue; }
            var mtimeNs = 0;
            try { mtimeNs = Math.round(file.modified.getTime() * 1000000); } catch (e3) {}
            var size = 0;
            try { size = file.length; } catch (e4) {}
            var fps = 25.0;
            try { fps = item.frameRate; } catch (e5) {}
            out.push({
                path: file.fsName,
                size: size,
                mtime_ns: mtimeNs,
                item_id: item.id,
                frame_rate: fps
            });
        }
    } catch (e) {
        return JSON.stringify(out);
    }
    return JSON.stringify(out);
}

function tempoGetActiveCompInfo() {
    try {
        var active = app.project ? app.project.activeItem : null;
        if (active instanceof CompItem) {
            return JSON.stringify({ comp_id: active.id, name: active.name, fps: active.frameRate });
        }
    } catch (e) {}
    return JSON.stringify({ ok: false });
}

/* payload: {source_path, start_s, end_s} — full insert in ONE evalScript call. */
function tempoInsertOrFocus(payloadJson) {
    var payload = null;
    try {
        payload = JSON.parse(payloadJson);
    } catch (e) {
        return JSON.stringify({ ok: false, error: "bad payload" });
    }
    if (!payload || !payload.source_path ||
            typeof payload.start_s !== "number" || typeof payload.end_s !== "number" ||
            !(payload.end_s > payload.start_s)) {
        return JSON.stringify({ ok: false, error: "bad payload" });
    }

    app.beginUndoGroup("Tempo: Insert Shot");
    var result;
    try {
        result = tempoInsertOrFocusInner(payload);
    } catch (e) {
        result = JSON.stringify({ ok: false, error: String(e && e.message || e).slice(0, 200) });
    }
    try { app.endUndoGroup(); } catch (e2) {}
    return result;
}

function tempoFindFootage(path) {
    var n = app.project.items.length;
    for (var i = 1; i <= n; i++) {
        var item = app.project.items[i];
        if (!(item instanceof FootageItem)) { continue; }
        var src = null;
        try { src = item.mainSource; } catch (e1) { continue; }
        if (!(src instanceof FileSource)) { continue; }
        var file = null;
        try { file = src.file; } catch (e2) { continue; }
        if (file && file.fsName === path) { return item; }
    }
    return null;
}

function tempoInsertOrFocusInner(payload) {
    var footage = tempoFindFootage(payload.source_path);
    if (!footage) {
        var file = new File(payload.source_path);
        if (!file.exists) {
            return JSON.stringify({ ok: false, error: "source missing from disk" });
        }
        var opts = new ImportOptions(file);
        footage = app.project.importFile(opts);
    }

    var comp = null;
    if (app.project.activeItem instanceof CompItem) {
        comp = app.project.activeItem;
    } else {
        var base = payload.source_path.replace(/^.*[\\/]/, "");
        var w = 1920, h = 1080, fps = 25.0;
        try { w = footage.width; h = footage.height; fps = footage.frameRate; } catch (e) {}
        comp = app.project.items.addComp("Tempo — " + base, w, h, 1.0, 60.0, fps);
    }

    var T = comp.time;
    var dur = payload.end_s - payload.start_s;
    var layer = comp.layers.add(footage);
    layer.startTime = T - payload.start_s;
    layer.inPoint = T;
    layer.outPoint = T + dur;

    var nl = comp.layers.length;
    for (var i = 1; i <= nl; i++) {
        try { comp.layer(i).selected = false; } catch (e2) {}
    }
    try { layer.selected = true; } catch (e3) {}
    comp.time = layer.inPoint;
    try {
        if (comp.openInViewer instanceof Function) { comp.openInViewer(); }
    } catch (e4) {}

    return JSON.stringify({ ok: true, comp_id: comp.id, layer_id: layer.id });
}
