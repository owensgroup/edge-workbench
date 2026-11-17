// Every built page, walked step by step with no network and no MathJax.
//
// What is checked here is what a reader sees, on any algorithm: nothing is
// named for one example. Each check was once a bug found by eye.
//
//   node tests/check_pages.js

const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

// The page inlines this file; the lookups are the same code the page runs.
const EdgeDisplay = require("../edge_workbench/render/display.js");
// EDGE_WORKBENCH_PAGES: another directory of author directories to walk
// instead (pages built outside examples/).
const EXAMPLES = process.env.EDGE_WORKBENCH_PAGES || path.join(__dirname, "..", "examples");
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

// A Populate with a mutable rank is shown round by round (paper, Inset 4),
// and every round on the page is the round the evaluator recorded.
function checkPopulate(w, d, s, at) {
  const box = d.getElementById("popbox"), P = s.populate;
  const spec = ((s.exec && s.exec.einsum.specs) || []).find((x) =>
    x.kind === "populate" && (x.rank_list || []).length);
  check(at, !spec || !!P || Object.keys(s.exec.result).length === 0,
    "a Populate with a mutable rank wrote values but recorded no rounds");
  check(at, (box.style.display !== "none") === !!P, "the Populate rounds are shown wrongly");
  if (!P) return;
  const same = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());
  const held = (cells) => Object.keys(cells).filter((c) => cells[c] !== false);
  const drawn = (card, cls) => [...d.querySelectorAll(`#popstrip .tcard.${card} td${cls}`)]
    .map((c) => c.dataset.coord);
  const lastOn = {};
  P.rounds.forEach((R, k) => {
    const here = `${at} round ${k + 1}`;
    w.eval(`goRound(${k})`);
    const F = P.fibers[R.fiber], sets = EdgeDisplay.roundSets(R);
    check(here, d.getElementById("popno").textContent === `round ${k + 1} of ${P.rounds.length}`,
      "the round shown is not the round asked for");
    // Inset 4, on the recorded sets: W ∩ (dom(S) ∪ D) = ∅, and a location
    // deleted was occupied in the pre-state.
    check(here, sets.overlap.length === 0, `W meets dom(S) ∪ D at ${sets.overlap}`);
    check(here, R.D.every((c) => c in R.pre), "a location not in the pre-state was deleted");
    check(here, sets.W.concat(sets.D).every((c) => F.loc.includes(c)), "W or D leaves the fiber");
    check(here, R.checked && d.getElementById("popcheck").classList.contains("yes")
      && d.getElementById("popcheck").textContent.includes("✓"), "the constraint is not marked checked");
    // Each round starts from what the round before it left in that fiber,
    // and ends with the pre-state less D plus W.
    if (R.fiber in lastOn) check(here, same(Object.entries(P.rounds[lastOn[R.fiber]].post).map(String),
      Object.entries(R.pre).map(String)), "the pre-state is not the previous round's result");
    lastOn[R.fiber] = k;
    check(here, same(Object.keys(R.post),
      Object.keys(R.pre).filter((c) => !R.D.includes(c)).concat(sets.W)),
      "the state after the round is not the pre-state less D plus W");
    // The cards draw exactly the recorded pre-state, W and D.
    check(here, same(drawn("prestate", ".fiber:not(.abs)"), held(R.pre)),
      `pre-state drawn as ${drawn("prestate", ".fiber:not(.abs)")}, recorded ${held(R.pre)}`);
    check(here, same(drawn("prestate", ".fiber"), F.loc), "the fiber outlined is not Loc");
    check(here, same(drawn("poststate", ".wr"), sets.W), "W drawn differs from the record");
    check(here, same(drawn("poststate", ".del"), sets.D), "D drawn differs from the record");
    check(here, same(drawn("poststate", ".fiber:not(.abs):not(.del)"), held(R.post)),
      "the state after the round differs from the record");
    check(here, same(drawn("redtmp", ".rd"), [R.coord]), "the incoming element is not the one lit");
    // The candidates of this fiber, in the order the schedule offered them.
    const rows = [...d.querySelectorAll("#popcands tr[data-round]")];
    check(here, JSON.stringify(rows.map((r) => +r.dataset.round)) === JSON.stringify(F.rounds),
      "the candidates listed are not the fiber's rounds in order");
    check(here, rows.filter((r) => r.classList.contains("cur")).length === 1
      && rows.find((r) => r.classList.contains("cur")).dataset.round === String(k),
      "the current round is not marked among the candidates");
    const body = d.getElementById("popbody").textContent;
    check(here, !/undefined|NaN|\[object/.test(body), "junk text in the round");
    // A free choice is shown as free; a ranking operator shows what it ranked.
    check(here, !!d.getElementById("popfree") === !!P.free
      && !!d.getElementById("popranked") === !P.free, "free choice and ranking operator confused");
    if (P.free && F.rounds.length > 1) check(here,
      body.includes(`All ${F.rounds.length} candidates above were eligible`)
      && body.includes(P.schedule.kind), "a free choice among several is not shown as free");
    if (!P.free && /[-_]val/.test(P.operator)) check(here,
      body.includes("ranked by value: incoming [" + R.coord + "]"), "the ranked value is not shown");
  });
  // The rounds end at the state the step recorded for its output.
  const end = EdgeDisplay.outputAt(P, s.state[s.output], P.rounds.length - 1, "post");
  check(at, same(Object.entries(end).map(String),
    Object.entries(s.state[s.output] || {}).map(String)),
    "the last round does not leave the output the step recorded");
  w.eval("goRound(0)");
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

    // A value is shown as its tensor is declared. A literal (a zero-rank
    // declaration carrying its value, like the False a condition compares
    // against) is that value, not an entry that may be absent.
    (w.eval("IR").declarations || []).filter((t) => t.data_type?.name === "bool"
      && (t.value === undefined || t.value === null)).forEach((t) => {
      const held = s.state[t.name] || {};
      check(at, Object.values(held).every((v) => v === true),
        `${t.name} is Boolean but holds ${JSON.stringify(Object.values(held))}`);
    });
    checkPopulate(w, d, s, at);
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

function populateRounds(name) {
  const html = fs.readFileSync(path.join(EXAMPLES, name, "index.html"), "utf8");
  return (html.match(/"writeDelSize":/g) || []).length;
}

const { meaningHTML } = EdgeDisplay;
const mark = (tex) => `[${tex}]`;
check("meaningHTML", meaningHTML("to $v$ & \\(u_i\\) < 1", mark) === "to [v] &amp; [u_i] &lt; 1",
      "math in a caption was not picked out");
check("meaningHTML", meaningHTML("plain text", mark) === "plain text", "plain caption changed");

const names = fs.readdirSync(EXAMPLES).filter((n) =>
  fs.existsSync(path.join(EXAMPLES, n, "index.html")));
names.forEach(walk);

const rounds = names.reduce((n, name) => n + populateRounds(name), 0);
// The examples include cascades with a Populate; another directory need not.
check("populate", rounds > 0 || !!process.env.EDGE_WORKBENCH_PAGES,
  "no page shows a Populate round");
failed.filter(Boolean).forEach((f) => console.log("FAIL " + f));
console.log(`${names.length} pages: ${passed} passed, ${failed.length} failed`
  + ` (${rounds} Populate rounds)`);
process.exit(failed.length ? 1 : 0);
