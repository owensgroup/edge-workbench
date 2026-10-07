// Loading the generated page, and the helpers every page check needs.
//
// This was the top 170 lines of `algorithms/max-flow/tests/check_page.js`, so
// a second algorithm inherited none of it: Algorithm X's probe started with
// zero page checks, which is part of why the probe found so little about the
// renderer.
//
// The renderer is generic -- it knows tensors, ranks, grids and a transport --
// so the checks over it are generic too, and belong here rather than beside
// one algorithm. What stays algorithm-specific is the CHOICE OF EXAMPLE: a
// check that exercises a reduction has to name an Einsum that reduces.
//
// Everything here is derived from the page, not declared: the extent, the
// coordinate range, a generation that exists. A number written in by hand
// would pin these checks to one instance, which is exactly what they used to
// be.

// correct is a different question, answered before the page is written, by
// the coverage gate (the whole spec executed) and the algorithm's own
// verifier (the answer is right).
//
//   node check_viz.js            # summary
//   node check_viz.js -v         # list every check
//
// jsdom is a dev-only dependency; install it wherever you run this.

const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

// Generic code cannot guess the algorithm from its own location any more, so
// it has to be told -- which is the right constraint: a harness that inferred
// the algorithm from where it sat is a harness that only works in one place.
const ALG = process.env.EDGE_WORKBENCH_ALG || (() => {
  const dirs = fs.readdirSync(path.join(__dirname, "..", "algorithms"))
    .filter((d) => !d.startsWith("."));
  if (dirs.length === 1) return dirs[0];
  console.error(
    `${dirs.length} algorithms available (${dirs.join(", ")}); ` +
    "say which with EDGE_WORKBENCH_ALG"
  );
  process.exit(1);
})();
// The harness lives in tests/, so the repository root is one level up.
const ROOT = path.join(__dirname, "..");
const BUILD = process.env.EDGE_WORKBENCH_OUT || path.join(ROOT, "build", ALG);
const VERBOSE = process.argv.includes("-v");

let pass = 0;
const fails = [];
function check(name, cond, detail) {
  if (cond) {
    pass++;
    if (VERBOSE) console.log("  ok   " + name);
  } else {
    fails.push({ name, detail });
    console.log("  FAIL " + name + (detail ? "  -- " + detail : ""));
  }
}

const consoleErrors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => consoleErrors.push(String(e.message)));
vc.on("error", (...a) => consoleErrors.push(a.join(" ")));

const html = fs.readFileSync(path.join(BUILD, "index.html"), "utf8");

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  virtualConsole: vc,
  // MathJax is fetched from a CDN; the page already falls back to its own
  // typeset() when MathJax is absent, which is the path exercised here.
  resources: undefined,
  pretendToBeVisual: true,
});

const { window } = dom;
const doc = window.document;
const $ = (id) => doc.getElementById(id);

// The trace the page is rendering, read back OUT OF THE PAGE. Every expected
// value below comes from here.
//
// Evaluated in the page's own global rather than read from `window.T`: the
// page declares `const T=...` at script scope, and a top-level `const` goes
// into the global lexical environment instead of becoming a property of
// `window`. It is reachable by evaluating in that same global, which is what
// this does.
const trace = window.eval("typeof T !== 'undefined' ? T : null");
if (!trace || !Array.isArray(trace.steps) || !trace.steps.length) {
  console.error(
    "the built page does not define a usable trace `T`, so there is nothing " +
    "to check the DOM against. Did build_page.py rename the embedded trace?"
  );
  process.exit(1);
}

// How many vertices this instance has. DERIVED, because the instance now comes
// from the tutorial's worked example: every grid size below used to be written
// as 6 (or 7 rows, with the header), which was true only of the graph this repo
// used to hardcode. A number like that turns a generic page check into a check
// of one particular picture.
const N = trace.graph.nodes.length;
const RANGE = [...Array(N).keys()].map(String);

// A mid-run generation that EXISTS. The checks below used to name generation 3
// or 7 literally, which held only while the instance was a fixed 6-vertex
// graph. The instance now comes from the tutorial's worked example, so a
// literal generation is a pin to one tutorial.
const MID = Math.min(3, Math.max(1, trace.iterations || 1));

// Find a step, and SAY SO when it is missing. `trace.steps.findIndex` returns
// -1 for an absent step, and `go(-1)` neither throws nor renders, so a check
// aimed at a step that no longer exists used to pass quietly while testing
// nothing at all. Several did.
function stepIdx(einsum, iteration) {
  const i = trace.steps.findIndex(
    (s) => s.einsum === einsum &&
      (iteration === undefined || s.iteration === iteration)
  );
  if (i < 0) {
    fails.push({
      name: `no step ${einsum}` +
        (iteration === undefined ? "" : ` at i=${iteration}`),
      detail: "the check below tested nothing",
    });
    console.log(`  FAIL no step ${einsum}` +
      (iteration === undefined ? "" : ` at i=${iteration}`));
  }
  return i;
}

function textOf(el) {
  return el ? el.textContent.trim() : null;
}

// The page renders infinities as glyphs, so compare on what it would print.
function fmtNum(v) {
  if (v === null || v === undefined) return "—";
  if (v === Infinity) return "∞";
  return String(v);
}

// The title is "<name><sup>ranks</sup>"; the rank superscript is not part of
// the label under test, so strip it. Thin spaces in the generation label are
// normalised to ordinary ones.
function titleOf(t) {
  return t.innerHTML
    .split("<sup>")[0]
    .replace(/<[^>]*>/g, "")
    .replace(/[\u2009\u00a0]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Read a rendered tensor block back out of the DOM.
function readBlock(name) {
  for (const b of doc.querySelectorAll(".tblock")) {
    const t = b.querySelector(".tname");
    if (t && titleOf(t) === name) return { el: b, label: titleOf(t), title: t };
  }
  return null;
}

// Operand cards are captioned "F" + <sub>1,u,v</sub>; the name is the leading
// letters.
function capName(card) {
  const m = card.querySelector(".cap").textContent.trim().match(/^[A-Za-z]+/);
  return m ? m[0] : "";
}

// The caption without its trailing empty-value tag, which every card carries.
function capText(card) {
  const c = card.querySelector(".cap").cloneNode(true);
  [...c.querySelectorAll(".emp")].forEach((e) => e.remove());
  return c.textContent.trim();
}

// The empty-value tag itself, e.g. "0", "+inf", "false" -- or "" when the
// tensor is anonymous and has no declaration to read it from.
function emptyTag(card) {
  const e = card.querySelector(".cap .emp");
  return e ? e.textContent.replace(/^∅\s*/, "").trim() : "";
}

function blockTitles() {
  return [...doc.querySelectorAll(".tblock .tname")].map(titleOf);
}

setTimeout(() => {
  try {
    run();
  } catch (e) {
    console.log("\nEXCEPTION: " + e.stack);
    process.exit(1);
  }
}, 300);


module.exports = {
  window, doc, $, trace, dom, html,
  N, RANGE, MID,
  check, fails, consoleErrors,
  stepIdx, textOf, fmtNum, titleOf, readBlock, capName, capText, emptyTag,
  blockTitles,
  passed: () => pass,
  report() {
    console.log(`\n${pass} passed, ${fails.length} failed`);
    process.exit(fails.length ? 1 : 0);
  },
};
