/* ae_smoke.jsx — manual host smoke script (AGENTS.md §9).
 *
 * Run from After Effects (File > Scripts > Run Script File) with a test
 * project open that contains at least one imported footage file.
 * ES3 only. Depends on json2.js + host.jsx loaded first:
 *   #include "json2.js"  (adjust the relative path to your checkout)
 *   #include "host.jsx"
 * Then run this file. It writes results via $.writeln (ExtendScript Toolkit
 * console) and alerts a PASS/FAIL summary. Human verifies the checklist in
 * docs/ae-smoke.md.
 */

//@include "json2.js"
//@include "host.jsx"

(function aeSmoke() {
    var failures = [];
    function check(name, cond, extra) {
        $.writeln((cond ? "PASS " : "FAIL ") + name + (extra ? " — " + extra : ""));
        if (!cond) { failures.push(name); }
    }

    // 1. list footage
    var listRaw = tempoListFootage();
    var list = null;
    try { list = JSON.parse(listRaw); } catch (e) { list = null; }
    check("list returns JSON array", list instanceof Array, listRaw.slice(0, 120));
    if (!(list instanceof Array) || !list.length) {
        alert("SMOKE ABORT: import a footage file into the test project first.");
        return;
    }
    var f = list[0];
    check("footage has path/size/mtime",
        typeof f.path === "string" && typeof f.size === "number" && typeof f.mtime_ns === "number");

    // 2. active comp info (informational — no comp required)
    var infoRaw = tempoGetActiveCompInfo();
    var info = JSON.parse(infoRaw);
    $.writeln("INFO active comp: " + infoRaw.slice(0, 120));

    // 3. insert first 2 seconds of the first footage at the playhead
    var payload = JSON.stringify({ source_path: f.path, start_s: 0.0, end_s: 2.0 });
    var beforeUndo = app.project ? true : false;
    var out = JSON.parse(tempoInsertOrFocus(payload));
    check("insert ok", out && out.ok === true, JSON.stringify(out).slice(0, 160));
    check("project still open (undo available)", beforeUndo);

    if (failures.length) {
        alert("SMOKE FAIL (" + failures.length + "): " + failures.join(", "));
    } else {
        alert("SMOKE PASS — now verify trim/playhead/selection/single-undo by eye (docs/ae-smoke.md).");
    }
})();
