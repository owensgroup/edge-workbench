// Every built page, walked step by step with no network and no MathJax.
//
// What is checked here is what a reader sees, on any algorithm: nothing is
// named for one example. Each check was once a bug found by eye.
//
//   node tests/check_pages.js

const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const EXAMPLES = path.join(__dirname, "..", "examples");
let passed = 0;
const failed = [];

function check(where, ok, what) {
  if (ok) passed++;
  else if (failed.length < 40) failed.push(`${where}: ${what}`);
  else failed.push(null);
}

function load(file) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => {
    if (!/Could not parse CSS/.test(e.message)) errors.push(e.message);
  });
  const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
    runScripts: "dangerously", url: "file://" + file, virtualConsole: vc,
  });
  return { dom, errors };
}

function walk(name) {
  const { dom, errors } = load(path.join(EXAMPLES, name, "index.html"));
  const w = dom.window, d = w.document;
  const T = w.eval("T"), get = (id) => d.getElementById(id);

  T.steps.forEach((s, k) => {
    const at = `${name} step ${k + 1} (${s.einsum})`;
    w.eval(`go(${k})`);
    check(at, get("stepno").textContent.includes(`step ${k + 1} of`), "did not render");

    const shown = get("expr").textContent;
    check(at, !shown.includes("\\"), `raw LaTeX in the formula: ${shown.slice(0, 60)}`);
    check(at, !/undefined|NaN|\[object/.test(get("now")?.textContent ?? ""), "junk text");

    // A value is shown as its tensor is declared.
    (w.eval("IR").declarations || []).filter((t) => t.data_type?.name === "bool").forEach((t) => {
      const held = s.state[t.name] || {};
      check(at, Object.values(held).every((v) => v === true),
        `${t.name} is Boolean but holds ${JSON.stringify(Object.values(held))}`);
    });
    const cells = [...d.querySelectorAll("#tstrip td.pick")];
    check(at, !s.exec || cells.length > 0 || Object.keys(s.exec.result).length === 0
      || w.eval("EXEC") !== null, "an executed step has no grids");

    cells.forEach((cell) => {
      const key = cell.dataset.coord;
      w.eval(`EXEC.sel=${JSON.stringify(key)};writeSpaceNote();renderPoint();`);
      if (!s.exec.reduceSpec) return;
      const here = `${at} [${key}]`;
      const folded = (p) => p.afterMap || p;
      const present = s.exec.points.filter((p) => p.coord === key && folded(p).present);
      const rows = d.querySelectorAll("table.fold tr").length;
      check(here, present.length ? rows - 2 === present.length : rows === 0,
        "the table does not list exactly the contributions");

      // Only what contributed is highlighted, and min/max marks its choice.
      const kept = [...d.querySelectorAll("table.fold tr.kept")];
      const op = s.exec.reduceSpec.compute_op.symbol || s.exec.reduceSpec.compute_op.name;
      if (present.length && (op === "min" || op === "max")) {
        const want = present.filter((p) => p.value === s.exec.result[key]).length;
        check(here, kept.length === want, `${op} kept ${kept.length} rows, expected ${want}`);
      } else {
        check(here, kept.length === 0, "only min and max keep one contribution");
      }
      // The Reduce's input is on the page, and it is what was recorded.
      const card = d.querySelector("#tstrip .tcard.aftermap");
      check(here, !!card === w.eval("hasAfterMap(EXEC.R)"),
        "After Map shown where there is no Map to show, or missing");
      if (card) {
        const line = s.exec.points.filter((p) => p.coord === key).length;
        const lit = card.querySelectorAll("td.fiber").length;
        check(here, lit === line, `After Map outlines ${lit} cells of a ${line}-cell line`);
        const held = s.exec.points.filter((p) => (p.afterMap || p).present);
        const shownCells = [...card.querySelectorAll("td")]
          .filter((c) => !c.classList.contains("abs")).length;
        check(here, shownCells === held.filter((p) => (p.afterMap || p).value !== false).length,
          `After Map shows ${shownCells} values, recorded ${held.length}`);
      }
      // A Map after the Reduce: what the Reduce made is on the page, in order.
      const reduced = s.exec.points.find((p) => p.coord === key)?.afterReduce;
      const after = d.querySelector("#tstrip .tcard.afterreduce");
      check(here, !!after === !!reduced, "After Reduce shown wrongly");
      if (reduced) {
        const held = new Set(s.exec.points.filter((p) => p.afterReduce.present).map((p) => p.coord));
        const drawn = [...after.querySelectorAll("td")].filter((c) => !c.classList.contains("abs"));
        check(here, drawn.length === held.size, "After Reduce cells differ from the record");
        const order = [...d.querySelectorAll("#tstrip .tcard")].map((c) => c.className);
        check(here, order.findIndex((c) => c.includes("aftermap")) <
          order.findIndex((c) => c.includes("afterreduce")), "After Reduce precedes After Map");
        check(here, !/No point/.test(get("pbody").textContent) || !present.length,
          "says nothing was present although the Map produced a value");
      }
      const reads = new Set();
      present.forEach((p) => (p.prov.reads || []).forEach((r) => {
        if (r.tensor && !r.scalar) reads.add(r.tensor + "|" + r.coord);
      }));
      // Operands of the Reduce, plus one read for each operand of a later Map.
      const cards = [...d.querySelectorAll("#tstrip .tcard")];
      const stop = cards.findIndex((c) => c.classList.contains("aftermap"));
      const early = stop < 0 ? cards : cards.slice(0, stop);
      const marked = early.reduce((n, c) => n + c.querySelectorAll("td.rd").length, 0);
      check(here, marked <= reads.size, `${marked} cells lit for ${reads.size} reads`);
    });
  });

  (T.coordSets || []).forEach((c) => {
    w.eval("go(0)");
    check(name, get("static1").textContent.includes(c.name), `${c.name} is not shown`);
  });
  check(name, errors.length === 0, `script errors: ${errors[0]}`);
  w.close();
}

const { meaningHTML } = require("../edge_workbench/render/display.js");
const mark = (tex) => `[${tex}]`;
check("meaningHTML", meaningHTML("to $v$ & \\(u_i\\) < 1", mark) === "to [v] &amp; [u_i] &lt; 1",
      "math in a caption was not picked out");
check("meaningHTML", meaningHTML("plain text", mark) === "plain text", "plain caption changed");

const names = fs.readdirSync(EXAMPLES).filter((n) =>
  fs.existsSync(path.join(EXAMPLES, n, "index.html")));
names.forEach(walk);

failed.filter(Boolean).forEach((f) => console.log("FAIL " + f));
console.log(`${names.length} pages: ${passed} passed, ${failed.length} failed`);
process.exit(failed.length ? 1 : 0);
