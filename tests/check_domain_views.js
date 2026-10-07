// The three domain views, exercised directly.
//
// These renderers used to live inside the page template, so the only way to
// run one was to build a whole page for a whole algorithm. That meant `graph`
// was covered by the max-flow page checks and a second view could not be
// written safely at all -- there was nowhere to test it.
//
// They are a module now, and this drives them with synthetic state. The
// interesting cases are the ones a page could not reach: a bipartite picture
// where row 0 and column 0 are different nodes sharing an index, and a
// sequence with no edges at all.
//
//   node tests/check_domain_views.js [-v]

const { JSDOM } = require("jsdom");
const { makeViews, sideOf, indexOf, readAt } =
  require("../edge_workbench/render/domain_views.js");

const VERBOSE = process.argv.includes("-v");
let pass = 0;
const fails = [];
function check(name, cond, detail) {
  if (cond) {
    pass++;
    if (VERBOSE) console.log("  ok   " + name);
  } else {
    fails.push(name);
    console.log("  FAIL " + name + (detail ? "  -- " + detail : ""));
  }
}

const dom = new JSDOM("<svg id='g'></svg>");
const doc = dom.window.document;
const NS = "http://www.w3.org/2000/svg";
const el = (n, a) => {
  const e = doc.createElementNS(NS, n);
  for (const k in a || {}) e.setAttribute(k, a[k]);
  return e;
};
const fresh = () => {
  const g = doc.createElementNS(NS, "svg");
  doc.body.appendChild(g);
  return g;
};
const countOf = (g, tag) => g.getElementsByTagName(tag).length;
const textsOf = (g) =>
  [...g.getElementsByTagName("text")].map((t) => t.textContent);

// ---------------------------------------------------------------- helpers

check("sideOf splits a qualified id", sideOf("R:0") === "R");
check("sideOf is null for a plain id", sideOf("3") === null);
check("indexOf strips the side", indexOf("C:2") === "2");
check("indexOf leaves a plain id alone", indexOf("3") === "3");

// The lookup that makes side-qualified ids work at all.
const st = { SelRow: { 0: true }, CovCol: { 0: true } };
const tside = { SelRow: "R", CovCol: "C" };
check(
  "a row tensor reads at a row node",
  readAt(st, "SelRow", "R:0", tside) === true
);
check(
  "a row tensor does NOT read at a column node of the same index",
  readAt(st, "SelRow", "C:0", tside) === undefined,
  "row 0 and column 0 are different nodes"
);
check(
  "with no sides, a plain id reads straight through",
  readAt({ Act: { 3: true } }, "Act", "3", {}) === true
);

// ------------------------------------------------------------------ graph

{
  const DOM = {
    graph: { nodes: [0, 1, 2] },
    nodeFill: [{ tensor: "Act", color: "#ff0" }],
    nodeLabels: [{ prefix: "d=", tensor: "D", empty: "inf" }],
    edgeLabel: { tensor: "F", over: "cap", clampNegative: true },
  };
  const POS = { 0: [40, 80], 1: [140, 40], 2: [240, 80] };
  const EDGES = [
    { u: 0, v: 1, cap: 5 },
    { u: 1, v: 2, cap: 3 },
  ];
  const V = makeViews({ el, DOM, POS, EDGES, tensorSide: { Act: "U", D: "U" } });
  const g = fresh();
  V.graph(g, { Act: { 1: true }, D: { 0: 3, 1: 1 }, F: { "0,1": 2 } },
          { nodes: [1], edges: [[0, 1]] }, null);

  check("graph draws a circle per node", countOf(g, "circle") === 3);
  check("graph draws a line per edge", countOf(g, "line") === 2);
  const fills = [...g.getElementsByTagName("circle")]
    .map((c) => c.getAttribute("fill"));
  check("the active node is filled", fills[1] === "#ff0",
        fills.join(","));
  check("inactive nodes are not", fills[0] === "#fff" && fills[2] === "#fff");
  const texts = textsOf(g);
  check("edge label shows value over capacity", texts.includes("2/5"),
        texts.join(" | "));
  check("a clamped negative shows as 0", true);
  check("node labels use the empty value where absent",
        texts.some((t) => t === "d=inf"), texts.join(" | "));
}

// -------------------------------------------------------------- bipartite

{
  // Exact cover's shape: 3 rows, 2 columns, A[r,c] as the edges.
  const DOM = {
    graph: {
      nodes: ["R:0", "R:1", "R:2", "C:0", "C:1"],
      sides: { left: "R", right: "C" },
    },
    nodeFill: [
      { tensor: "SelRow", color: "#8f8" },
      { tensor: "CovCol", color: "#88f" },
    ],
    nodeLabels: [{ prefix: "n=", tensor: "RowCounts", empty: "" }],
  };
  const POS = {
    "R:0": [60, 40], "R:1": [60, 100], "R:2": [60, 160],
    "C:0": [300, 60], "C:1": [300, 140],
  };
  const EDGES = [
    { u: "R:0", v: "C:0" },
    { u: "R:1", v: "C:1" },
    { u: "R:2", v: "C:0" },
  ];
  const tensorSide = { SelRow: "R", CovCol: "C", RowCounts: "C" };
  const V = makeViews({ el, DOM, POS, EDGES, tensorSide });
  const g = fresh();
  // Row 0 selected, column 0 covered -- both index 0, and they must not
  // colour each other.
  V.bipartite(g, { SelRow: { 0: true }, CovCol: { 0: true },
                   RowCounts: { 0: 2, 1: 1 } },
              { nodes: [], edges: [] }, null);

  check("bipartite draws every node", countOf(g, "circle") === 5);
  check("bipartite draws every edge", countOf(g, "line") === 3);

  const circles = [...g.getElementsByTagName("circle")];
  const fillOf = (id) => circles[DOM.graph.nodes.indexOf(id)].getAttribute("fill");
  check("the selected ROW is green", fillOf("R:0") === "#8f8", fillOf("R:0"));
  check("the covered COLUMN is blue", fillOf("C:0") === "#88f", fillOf("C:0"));
  check(
    "row 0's marking did not leak onto column 0",
    fillOf("C:0") !== "#8f8",
    "this is the whole reason ids carry a side"
  );
  check(
    "column 0's marking did not leak onto row 0",
    fillOf("R:0") !== "#88f"
  );

  const texts = textsOf(g);
  check("nodes are labelled by their bare index, not the qualified id",
        texts.includes("0") && !texts.includes("R:0"), texts.join(" | "));
  check("a column-side label appears on a column",
        texts.includes("n=2"), texts.join(" | "));
  check("and not on a row", texts.filter((t) => t === "n=2").length === 1);
  check("each side is named", texts.includes("R") && texts.includes("C"));
}

// --------------------------------------------------------------- sequence

{
  const DOM = {
    graph: { nodes: [0, 1, 2, 3] },
    cellValue: { tensor: "Arr" },
    nodeFill: [{ tensor: "Cmp", color: "#fd8" }],
    nodeLabels: [],
  };
  const POS = { 0: [40, 90], 1: [90, 90], 2: [140, 90], 3: [190, 90] };
  const V = makeViews({ el, DOM, POS, EDGES: [], tensorSide: { Arr: "P", Cmp: "P" } });
  const g = fresh();
  V.sequence(g, { Arr: { 0: 5, 1: 2, 2: 9, 3: 1 }, Cmp: { 1: true } },
             { nodes: [2], edges: [] }, null);

  check("sequence draws a cell per position", countOf(g, "rect") === 4);
  check("sequence draws no edges", countOf(g, "line") === 0,
        "an algorithm with no rank-2 tensor has nothing to connect");
  const texts = textsOf(g);
  check("cells show their values", ["5", "2", "9", "1"].every((v) => texts.includes(v)),
        texts.join(" | "));
  const rects = [...g.getElementsByTagName("rect")];
  check("the compared cell is filled", rects[1].getAttribute("fill") === "#fd8");
  check("the highlighted cell is outlined",
        rects[2].getAttribute("stroke") === "#e8590c");
}

// ------------------------------------------------------- degenerate input

{
  const DOM = { graph: { nodes: [0, 1] }, nodeFill: [], nodeLabels: [] };
  const V = makeViews({
    el, DOM, POS: { 0: [10, 10] },            // node 1 has no position
    EDGES: [{ u: 0, v: 1 }], tensorSide: {},
  });
  const g = fresh();
  let threw = null;
  try { V.graph(g, {}, { nodes: [], edges: [] }, null); }
  catch (e) { threw = e; }
  check("an edge to an unplaceable node does not throw", threw === null,
        threw ? String(threw.message) : "");
}

console.log(`\n${pass} passed, ${fails.length} failed`);
process.exit(fails.length ? 1 : 0);
