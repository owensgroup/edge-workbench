// Headless UI check for the generated index.html.
//
// Loads the page in jsdom and drives it the way a person would -- step, jump
// iterations, hold the before toggle -- asserting that what the DOM shows
// agrees with the trace. Catches the class of bug that only appears once the
// data reaches the screen: wrong labels, stale grids, highlight logic that
// fires when it should not.
//
//   node check_viz.js            # summary
//   node check_viz.js -v         # list every check
//
// jsdom is a dev-only dependency; install it wherever you run this.

const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ALG = process.env.EDGE_WORKBENCH_ALG || path.basename(
  path.join(__dirname, ".."));
const ROOT = path.join(__dirname, "..", "..", "..");
const HERE = path.join(ROOT, "algorithms", ALG, "fixtures");
const BUILD = process.env.EDGE_WORKBENCH_OUT || path.join(ROOT, "build", ALG);
const VERBOSE = process.argv.includes("-v");
const trace = JSON.parse(
  fs.readFileSync(path.join(HERE, "maxflow_edge_trace.json"), "utf8")
);

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

function run() {
  console.log("checking index.html\n");

  // ------------------------------------------------------------- structure
  check("page has a graph svg", !!$("g"));
  check("page has an einsum panel", !!$("expr"));
  check("before/after button exists", !!$("btog"));
  check(
    "before button is in the top panel, not the transport bar",
    !!$("now") && $("now").contains($("btog")),
    "expected #btog inside #now"
  );
  check("transport bar has no before button", !$("bar").querySelector("#btog"));
  check("slider spans the trace", +$("slider").max === trace.steps.length - 1);

  // ------------------------------------------------------- step through it
  const go = window.go;
  check("go() is exposed", typeof go === "function");

  // A step whose output is stateful and which actually changes something:
  // E24 writes D at i=7.
  const idx = trace.steps.findIndex(
    (s) => s.einsum === "E24" && s.iteration === 7
  );
  check("found E24 at i=7", idx > 0, "idx=" + idx);

  go(idx);
  const step = trace.steps[idx];

  check(
    "iteration badge shows i = 7",
    /i\s*=\s*7/.test(textOf($("itbadge"))),
    textOf($("itbadge"))
  );
  check(
    "step counter is right",
    textOf($("stepno")) === `step ${idx + 1} of ${trace.steps.length}`,
    textOf($("stepno"))
  );
  check(
    "max flow is hidden before the end",
    textOf($("flow")) === "",
    textOf($("flow"))
  );
  check(
    "einsum id is shown",
    ($("expr").textContent || "").includes("E24"),
    $("expr").textContent.slice(0, 40)
  );
  check(
    "graph meaning is populated",
    (textOf($("mg")) || "").length > 10
  );
  check(
    "einsum meaning is populated",
    (textOf($("me")) || "").length > 10
  );

  // ------------------------------------------------ after-view is the truth
  const dAfter = step.state.D;
  const blk = readBlock("D (8)");
  check(
    "D is labelled with its output generation, D (8)",
    !!blk,
    "titles: " + blockTitles().filter((t) => t.startsWith("D")).join(" | ")
  );
  const cellsAfter = blk
    ? [...blk.el.querySelectorAll("td")].map((td) => td.textContent)
    : [];
  const wantAfter = [0, 1, 2, 3, 4, 5].map((v) =>
    dAfter[String(v)] === undefined ? "·" : String(dAfter[String(v)])
  );
  check(
    "D grid matches the trace after-state",
    JSON.stringify(cellsAfter) === JSON.stringify(wantAfter),
    "dom=" + cellsAfter.join(",") + "  trace=" + wantAfter.join(",")
  );

  check(
    "output tensor is highlighted as active",
    blk && blk.el.classList.contains("active")
  );
  check(
    "before-mode class is off",
    !doc.body.classList.contains("showing-before")
  );
  check("before banner is empty", !$("beforebar").innerHTML.trim());

  // --------------------------------------------------------- before toggle
  $("btog").onclick();

  check(
    "aria-pressed flips on",
    $("btog").getAttribute("aria-pressed") === "true"
  );
  check(
    "body gets showing-before",
    doc.body.classList.contains("showing-before")
  );
  const blkB = readBlock("D (7)");
  check(
    "D is relabelled to the prior generation, D (7)",
    !!blkB,
    "titles: " + blockTitles().filter((t) => t.startsWith("D")).join(" | ")
  );
  check(
    "output tensor styled as before, not active",
    blkB && blkB.el.classList.contains("before") && !blkB.el.classList.contains("active")
  );

  const dBefore = trace.steps[idx - 1].state.D;
  const cellsBefore = blkB
    ? [...blkB.el.querySelectorAll("td")].map((td) => td.textContent)
    : [];
  const wantBefore = [0, 1, 2, 3, 4, 5].map((v) =>
    dBefore[String(v)] === undefined ? "·" : String(dBefore[String(v)])
  );
  check(
    "D grid shows the prior generation",
    JSON.stringify(cellsBefore) === JSON.stringify(wantBefore),
    "dom=" + cellsBefore.join(",") + "  trace=" + wantBefore.join(",")
  );
  check(
    "banner names both generations",
    /D<sub>7<\/sub>/.test($("beforebar").innerHTML) &&
      /D<sub>8<\/sub>/.test($("beforebar").innerHTML),
    $("beforebar").textContent
  );

  // The bug that was reported: everything lighting up in before-mode.
  const flashed = [...doc.querySelectorAll("td.chg")].length;
  check(
    "no change-highlighting while showing the before state",
    flashed === 0,
    flashed + " cells marked .chg"
  );

  // Graph pane follows the toggle.
  const gTextB = $("g").textContent;
  check(
    "graph shows the prior height for the source",
    gTextB.includes("d=" + (dBefore["0"] ?? "")),
    gTextB.slice(0, 120)
  );
  const pillsB = $("g").querySelectorAll("rect").length;
  check(
    "no label highlight pills in before-mode",
    pillsB === 0,
    pillsB + " pills"
  );

  // ---------------------------------------------------------- release it
  $("btog").onclick();
  check(
    "toggle releases back to the after view",
    !doc.body.classList.contains("showing-before") && !!readBlock("D (8)")
  );

  // Stepping resets the toggle.
  $("btog").onclick();
  go(idx + 1);
  check(
    "stepping clears before-mode",
    !doc.body.classList.contains("showing-before")
  );

  // ------------------------------------------------------- intermediates
  const admIdx = trace.steps.findIndex(
    (s) => s.einsum === "E09" && s.iteration === 7
  );
  go(admIdx);
  $("btog").onclick();
  check(
    "intermediates keep the toggle enabled",
    !$("btog").disabled
  );
  // Intermediates are not carried on the grid any more -- the execution
  // panel shows them being built, which is the only place they exist.
  check(
    "intermediate has no grid block of its own",
    blockTitles().every((t) => !t.startsWith("Adm")),
    "titles: " + blockTitles().join(" | ")
  );
  check(
    "banner sends the reader to the execution panel",
    /intermediate/i.test($("beforebar").textContent) &&
      /executes/i.test($("beforebar").textContent),
    $("beforebar").textContent
  );
  check(
    "and the execution panel is showing that intermediate's einsum",
    $("tstrip").querySelectorAll(".tcard").length > 0 &&
      !$("execpanel").classList.contains("off")
  );

  // ----------------------------------------------------- change highlights
  go(idx); // back to E24 at i=7, after-view
  const pills = $("g").querySelectorAll("rect").length;
  check(
    "graph highlights the labels that changed",
    pills > 0,
    pills + " pills"
  );
  const chg = [...doc.querySelectorAll("td.chg")].length;
  check("tensor grid flags changed cells", chg > 0, chg + " cells");

  // ------------------------------------------------------------ stop step
  go(trace.steps.length - 1);
  check(
    "max flow appears on the last step",
    /max flow = 23/.test(textOf($("flow"))),
    textOf($("flow"))
  );
  check(
    "toggle is disabled on the stop step",
    $("btog").disabled === true
  );

  // ------------------------------------------------------------- first step
  go(0);
  check("toggle is disabled on the first step", $("btog").disabled === true);
  check(
    "setup badge on the first step",
    /setup/.test(textOf($("itbadge"))),
    textOf($("itbadge"))
  );

  // -------------------------------------------------- 1-D tensor orientation
  // A rank-1 U tensor is drawn as a COLUMN so its cell for vertex u lines up
  // with row u of every U x V tensor next to it.
  go(idx);
  const dBlk = readBlock("D (8)");
  check(
    "rank-1 U tensor is drawn vertically",
    dBlk.el.querySelectorAll("tr").length === 7 &&
      dBlk.el.querySelectorAll("tr")[1].querySelectorAll("td").length === 1,
    dBlk.el.querySelectorAll("tr").length + " rows"
  );
  check(
    "and its header names the rank rather than a row/col pair",
    dBlk.el.querySelector("th.rk").textContent === "U",
    dBlk.el.querySelector("th.rk").textContent
  );
  check(
    "cells stay in coordinate order 0..5 when read out",
    JSON.stringify(
      [...dBlk.el.querySelectorAll("td")].map((td) => td.dataset.coord)
    ) === JSON.stringify(["0", "1", "2", "3", "4", "5"])
  );
  const fBlk = readBlock("F");
  check(
    "rank-2 tensors are unchanged",
    fBlk && fBlk.el.querySelectorAll("tr").length === 7 &&
      fBlk.el.querySelectorAll("tr")[1].querySelectorAll("td").length === 6
  );
  // In the modal strip a 1-D operand must line up with the 2-D one beside it.
  go(
    trace.steps.findIndex((s) => s.einsum === "E11" && s.iteration === 3)
  );
  const eCardG = [...$("tstrip").querySelectorAll(".tcard")].find(
    (c) => capName(c) === "E"
  );
  const rCardG = [...$("tstrip").querySelectorAll(".tcard")].find(
    (c) => capName(c) === "R"
  );
  check(
    "an untransposed operand keeps its stored axis order",
    [...$("tstrip").querySelectorAll(".tcard")]
      .filter((c) => capName(c) === "R")
      .every((c) => c.querySelector("th.rk").textContent === "U:u\\V:v"),
    [...$("tstrip").querySelectorAll(".tcard")]
      .map((c) => c.querySelector("th.rk").textContent).join(" | ")
  );
  check(
    "1-D operand in the strip is a column too",
    eCardG.querySelectorAll("tr").length === 7 &&
      eCardG.querySelectorAll("tr")[1].querySelectorAll("td").length === 1
  );
  check(
    "so it has the same number of rows as the 2-D operand beside it",
    eCardG.querySelectorAll("tr").length ===
      rCardG.querySelectorAll("tr").length
  );
  doc.onkeydown({ key: "Escape" });

  // ------------------------------------------- recomputed-but-unchanged
  // E06 recomputes Act at the top of every round from an E that E19 already
  // read, so from iteration 2 on it produces an identical tensor. The banner
  // should say so rather than looking broken.
  const actIdx = trace.steps.findIndex(
    (s) => s.einsum === "E06" && s.iteration === 5
  );
  go(actIdx);
  $("btog").onclick();
  check(
    "unchanged recomputation is labelled",
    /unchanged/i.test($("beforebar").textContent),
    $("beforebar").textContent
  );
  check(
    "and still shows both generations",
    !!readBlock("Act (4)"),
    "titles: " + blockTitles().filter((t) => t.startsWith("Act")).join(" | ")
  );
  go(actIdx);

  // ------------------------------------------------------------ hold-B
  const kd = new window.KeyboardEvent("keydown", { key: "b", bubbles: true });
  doc.dispatchEvent(kd);
  if (doc.onkeydown) doc.onkeydown({ key: "b", repeat: false });
  check(
    "holding B enters before-mode",
    doc.body.classList.contains("showing-before")
  );
  doc.dispatchEvent(new window.KeyboardEvent("keyup", { key: "b", bubbles: true }));
  check(
    "releasing B leaves before-mode",
    !doc.body.classList.contains("showing-before")
  );

  // ------------------------------------------------------- speed slider
  // Reported bug: the slider ran backwards. Right should mean faster, i.e. a
  // SMALLER interval.
  const sp = $("speed");
  sp.value = sp.min;
  const slow = window.delay();
  sp.value = sp.max;
  const fast = window.delay();
  check(
    "sliding right speeds up",
    fast < slow,
    `min->${slow}ms  max->${fast}ms`
  );
  check("fastest delay is still positive", fast > 0, fast + "ms");

  // ============================================================ drill-down
  const EdgeInterp = window.EdgeInterp;
  check("interpreter is inlined into the page", !!EdgeInterp);
  // `const IR = ...` is a top-level lexical binding, so it is reachable by
  // name but is not a property of window.
  check(
    "IR program is inlined",
    window.eval("typeof IR === 'object' && IR.declarations.length > 0")
  );

  // ------------------------------------------------- empty values
  // Every grid draws absence as hatching, but absence MEANS something
  // different per tensor: 0 for a flow, +inf for a height, false for a
  // predicate. The label has to come from the IR, not from a hand-kept list,
  // or it can quietly disagree with what the interpreter treats as empty.
  const declEmpty = JSON.parse(
    window.eval(
      "JSON.stringify(Object.fromEntries(" +
        "IR.declarations.map(d => [d.name, d.empty_value])))"
    )
  );
  const blockEmpty = () => {
    const out = {};
    [...doc.querySelectorAll(".tblock")].forEach((b) => {
      // The output block is labelled "D (8)" -- the generation is display
      // only; the empty value belongs to the tensor, not the generation.
      const nm = (titleOf(b.querySelector(".tname")).match(/^[A-Za-z]+/) ||
        [""])[0];
      const e = b.querySelector(".tname .emp");
      out[nm] = e ? e.textContent.replace(/^∅\s*/, "").trim() : null;
    });
    return out;
  };
  const glyph = (v) =>
    v === "inf" ? "+∞" : v === "-inf" ? "−∞" : String(v);

  go(idx);
  const be = blockEmpty();
  check(
    "every tensor on the grid states its empty value",
    Object.values(be).every((v) => v !== null && v !== ""),
    JSON.stringify(be)
  );
  check(
    "and it is the value the IR declares, for every one of them",
    Object.keys(be).every((n) => be[n] === glyph(declEmpty[n])),
    Object.keys(be)
      .filter((n) => be[n] !== glyph(declEmpty[n]))
      .map((n) => n + ": shows " + be[n] + ", IR says " + declEmpty[n])
      .join(" | ") || "all agree"
  );
  // The three distinct values must actually appear -- a label that always
  // said "0" would pass the agreement check on most tensors while hiding the
  // very thing it exists to show.
  check(
    "a height tensor reads +inf, not 0",
    be["D"] === "+∞",
    "D: " + be["D"]
  );
  check(
    "a flow tensor reads 0",
    be["F"] === "0" && be["R"] === "0" && be["E"] === "0",
    "F/R/E: " + be["F"] + " " + be["R"] + " " + be["E"]
  );
  check(
    "a predicate tensor reads false",
    be["Act"] === "false" && be["S"] === "false",
    "Act/S: " + be["Act"] + " " + be["S"]
  );
  check(
    "at least three different empty values are on screen at once",
    new Set(Object.values(be)).size >= 3,
    [...new Set(Object.values(be))].join(" ")
  );

  // --- E03: a reduction. E_{1,v} = F_{1,u,v} :: OR +(union), reducing u.
  const e03 = trace.steps.findIndex((s) => s.einsum === "E03");
  go(e03);
  check("execution panel is live on E03", !$("execpanel").classList.contains("off"));
  check(
    "subtitle states the points are independent",
    /independently/.test($("execsub").textContent),
    $("execsub").textContent
  );

  check(
    "there is no separate iteration-space grid",
    !$("sgrid"),
    "#sgrid should be gone; the operand grid is the space"
  );
  check(
    "the note says which rank collapses",
    /rank/i.test($("snote").textContent) &&
      $("snote").innerHTML.includes("collapse"),
    $("snote").textContent.slice(-110)
  );
  // The note is now ONLY the per-Einsum fact. The standing explanations --
  // points are independent, how the axes work -- were repeated on all 222
  // steps and are gone; the first still appears once, in the subtitle.
  check(
    "the note carries nothing but the collapse",
    $("snote").children.length === 1 &&
      $("snote").children[0].classList.contains("collapse"),
    $("snote").innerHTML.slice(0, 160)
  );
  check(
    "no standing explanation is repeated in the note",
    !/independently|without reference|runs down|not transposing/.test(
      $("snote").textContent
    ),
    $("snote").textContent.slice(0, 160)
  );
  check(
    "reduce fold table is shown",
    !!$("pbody").querySelector("table.fold")
  );
  check(
    "fold has a running-total column",
    /running/.test($("pbody").textContent)
  );

  // The fold must land on the value the trace recorded.
  const outCard0 = [...$("tstrip").querySelectorAll(".tcard")].slice(-1)[0];
  const selCoord = outCard0.querySelector("td.wr").dataset.coord;
  const wantVal = trace.steps[e03].state.E[selCoord];
  const totalRow = $("pbody").querySelector("tr.total");
  check(
    "fold total matches the trace",
    totalRow && totalRow.textContent.includes(String(wantVal)),
    "coord " + selCoord + " want " + wantVal + " got " + (totalRow && totalRow.textContent)
  );

  // Selecting a different output coordinate moves the highlighted line.
  const other = [...outCard0.querySelectorAll("td.pick")].find(
    (td) => td.dataset.coord !== selCoord
  );
  const otherCoord = other.dataset.coord;
  other.onclick();
  const opCard = [...$("tstrip").querySelectorAll(".tcard")][0];
  const litCols = {};
  [...opCard.querySelectorAll("tr")].slice(1).forEach((r) =>
    [...r.querySelectorAll("td")].forEach((td, i) => {
      if (td.classList.contains("rd")) litCols[i] = (litCols[i] || 0) + 1;
    })
  );
  check(
    "selecting another output coord moves the line",
    Object.keys(litCols).length === 1 &&
      litCols[Number(otherCoord)] === 6,
    "coord " + otherCoord + " lit per column: " + JSON.stringify(litCols)
  );

  // --- operand strip: where the values came from.
  const cards = () => [...$("tstrip").querySelectorAll(".tcard")];
  check(
    "operand strip shows the input tensor and the output",
    cards().length === 2,
    cards().map((c) => c.querySelector(".cap").textContent).join(" | ")
  );
  check(
    "the last card is the output",
    cards().slice(-1)[0].classList.contains("out")
  );
  check(
    "output card caption shows the access with the generation resolved",
    capText(cards().slice(-1)[0]) === "E1,v",
    cards().slice(-1)[0].querySelector(".cap").textContent
  );
  check(
    "operand caption shows the access as written",
    capText(cards()[0]) === "F1,u,v",
    cards()[0].querySelector(".cap").textContent
  );
  // The tensor is not redrawn to suit the access: F keeps rank U down and V
  // across, and the LABEL records which variable walks each rank.
  check(
    "operand keeps its own layout, with rank:variable labels",
    cards()[0].querySelector("th.rk").textContent === "U:u\\V:v",
    cards()[0].querySelector("th.rk").textContent
  );
  check(
    "the 1-D output names its rank and variable too",
    cards().slice(-1)[0].querySelector("th.rk").textContent === "U:v",
    cards().slice(-1)[0].querySelector("th.rk").textContent
  );
  // E03 reads F_{1,u,v}: with v pinned to the output coordinate and u ranging,
  // the cells read are one COLUMN of F -- because u walks F's U rank, which
  // runs down the page.
  check(
    "the reduced line is a column of F, since u walks F's U rank",
    (() => {
      const rows = [...cards()[0].querySelectorAll("tr")].slice(1);
      const cols = {};
      rows.forEach((r) =>
        [...r.querySelectorAll("td")].forEach((td, i) => {
          if (td.classList.contains("rd")) cols[i] = (cols[i] || 0) + 1;
        })
      );
      const k = Object.keys(cols);
      return k.length === 1 && cols[k[0]] === 6;
    })(),
    "expected all six lit cells in one column"
  );
  // A reduction reads a whole line out of its operand, and that line should
  // be lit -- the same line that collapses in the iteration space.
  const reads = $("tstrip").querySelectorAll(".mini td.rd").length;
  check(
    "reduction lights the whole line it reads from the operand",
    reads === 6,
    reads + " cells lit (expected 6)"
  );
  check(
    "exactly one cell is marked as written",
    $("tstrip").querySelectorAll(".mini td.wr").length === 1,
    $("tstrip").querySelectorAll(".mini td.wr").length + " written"
  );

  // --- Out-of-declared-order access. E03 and E13 now read their operands in
  // declared (U, V) order, but E12 still reads delta both ways round:
  //     F_{i+1,u,v} = (F ·1 delta_{i,u,v}) ·2 delta_{i,v,u}
  // so it is the case that proves the caption records the ACCESS while the
  // grid keeps the tensor's own layout.
  const e12 = trace.steps.findIndex(
    (s) => s.einsum === "E12" && s.iteration === 3
  );
  go(e12);
  const e12Cards = [...$("tstrip").querySelectorAll(".tcard")].filter(
    (c) => capName(c) === "delta"
  );
  check(
    "both delta accesses appear, in the order written",
    e12Cards.map(capText).join(" | ") === "delta3,u,v | delta3,v,u",
    e12Cards.map(capText).join(" | ")
  );
  check(
    "a transposed access keeps the tensor's layout and relabels the axes",
    e12Cards.map((c) => c.querySelector("th.rk").textContent).join(" | ") ===
      "U:u\\V:v | U:v\\V:u",
    e12Cards.map((c) => c.querySelector("th.rk").textContent).join(" | ")
  );

  // Same labelling inside the execution panel, where the reader is looking
  // at one Einsum's operands rather than the whole state.
  go(trace.steps.findIndex((s) => s.einsum === "E21" && s.iteration === 3));
  const e21 = [...$("tstrip").querySelectorAll(".tcard")];
  check(
    "operand cards carry the empty value too",
    e21.every((c) => c.classList.contains("inter") || emptyTag(c) !== ""),
    e21.map((c) => capName(c) + "=" + emptyTag(c)).join(" | ")
  );
  check(
    "a height operand and a residual operand disagree, and say so",
    emptyTag(e21.find((c) => capName(c) === "D")) === "+∞" &&
      emptyTag(e21.find((c) => capName(c) === "R")) === "0",
    e21.map((c) => capName(c) + "=" + emptyTag(c)).join(" | ")
  );
  // Anonymous intermediates have no declaration, so there is no declared
  // empty value to show -- and inventing one would be a claim the IR does
  // not make.
  go(trace.steps.findIndex((s) => s.einsum === "E06" && s.iteration === 3));
  check(
    "an anonymous intermediate claims no empty value",
    [...$("tstrip").querySelectorAll(".tcard.inter")].every(
      (c) => emptyTag(c) === ""
    ),
    [...$("tstrip").querySelectorAll(".tcard.inter")]
      .map((c) => c.querySelector(".cap").textContent).join(" | ")
  );

  // ------------------------------------------------ 1-D orientation
  // A 1-D tensor is laid out by the variable walking it HERE, so that the
  // line a reduction collapses points at the cell it collapses into. E03 is
  // the case that forces it: F is read in declared order, the reduced cells
  // are a COLUMN of F at horizontal position v, so E must be drawn across.
  const shapeOf = (card) => {
    const trs = card.querySelectorAll("tr");
    const rows = trs.length - 1;
    const cols = trs[1] ? trs[1].querySelectorAll("td").length : 0;
    return rows > 1 && cols > 1 ? "2D" : cols > 1 ? "ACROSS" : "DOWN";
  };
  const cardNamed = (nm) =>
    [...$("tstrip").querySelectorAll(".tcard")].find((c) => capName(c) === nm);

  go(trace.steps.findIndex((s) => s.einsum === "E03"));
  check(
    "E03: the reduced operand F stays 2-D on its declared axes",
    shapeOf(cardNamed("F")) === "2D",
    shapeOf(cardNamed("F"))
  );
  check(
    "E03: the output E is drawn ACROSS, because its variable is v",
    shapeOf(cardNamed("E")) === "ACROSS",
    shapeOf(cardNamed("E")) + " (header " +
      cardNamed("E").querySelector("th.rk").textContent + ")"
  );
  check(
    "E03: and its cell sits under the column of F that feeds it",
    (() => {
      // the lit column index in F, and the written cell index in E
      const f = cardNamed("F"), e = cardNamed("E");
      let col = -1;
      [...f.querySelectorAll("tr")].slice(1).forEach((r) =>
        [...r.querySelectorAll("td")].forEach((td, i) => {
          if (td.classList.contains("rd")) col = i;
        })
      );
      const cells = [...e.querySelectorAll("td")];
      const wr = cells.findIndex((td) => td.classList.contains("wr"));
      return col >= 0 && col === wr;
    })(),
    "lit column of F and written cell of E should share a position"
  );

  go(trace.steps.findIndex((s) => s.einsum === "E13" && s.iteration === 3));
  check(
    "E13: InPush is ACROSS -- same shape of reduction as E03",
    shapeOf(cardNamed("InPush")) === "ACROSS",
    shapeOf(cardNamed("InPush"))
  );
  go(trace.steps.findIndex((s) => s.einsum === "E14" && s.iteration === 3));
  check(
    "E14: OutPush is DOWN -- it reduces the other end, so its variable is u",
    shapeOf(cardNamed("OutPush")) === "DOWN",
    shapeOf(cardNamed("OutPush"))
  );
  // The same tensor, drawn differently in two Einsums, is the point rather
  // than a bug: E13 writes InPush_{i,v}, E15 reads InPush_{i,u}.
  go(trace.steps.findIndex((s) => s.einsum === "E15" && s.iteration === 3));
  check(
    "E15: InPush is DOWN here, because this Einsum walks it with u",
    shapeOf(cardNamed("InPush")) === "DOWN",
    shapeOf(cardNamed("InPush"))
  );
  check(
    "E15: every operand shares the u axis, so the strip lines up",
    [...$("tstrip").querySelectorAll(".tcard")].every(
      (c) => shapeOf(c) === "DOWN"
    ),
    [...$("tstrip").querySelectorAll(".tcard")]
      .map((c) => capName(c) + ":" + shapeOf(c)).join(" ")
  );
  check(
    "a map einsum leaves the note empty -- nothing collapses",
    $("snote").innerHTML === "",
    $("snote").innerHTML.slice(0, 120)
  );

  // --- intermediates: parenthesised sub-expressions get their own grid.
  const e06 = trace.steps.findIndex(
    (s) => s.einsum === "E06" && s.iteration === 3
  );
  go(e06);
  const allCards = () => [...$("tstrip").querySelectorAll(".tcard")];
  const inters = () => allCards().filter((c) => c.classList.contains("inter"));
  check(
    "E06's (E > 0) is shown as its own step",
    inters().length === 1,
    allCards().map((c) => c.querySelector(".cap").textContent).join(" | ")
  );
  check(
    "the step is captioned with the sub-expression and its rank binding",
    /^\(E > 0\)3,u$/.test(inters()[0].querySelector(".cap").textContent.trim()),
    inters()[0].querySelector(".cap").textContent
  );
  check(
    "it sits between the operands and the output",
    allCards().indexOf(inters()[0]) === allCards().length - 2,
    "position " + allCards().indexOf(inters()[0]) + " of " + allCards().length
  );
  // The intermediate must agree with the derivation: E06 is NST AND (E > 0),
  // so every vertex the step marks true and NST marks true must end up active.
  check(
    "the step's values are consistent with the output",
    (() => {
      const stepCells = [...inters()[0].querySelectorAll("tr")]
        .slice(1)
        .map((r) => r.querySelector("td").textContent);
      const act = trace.steps[e06].state.Act;
      const nst = trace.steps[e06].state.NST;
      return [0, 1, 2, 3, 4, 5].every((u) => {
        const stepTrue = stepCells[u] === "T";
        const want = stepTrue && !!nst[String(u)];
        return want === !!act[String(u)];
      });
    })(),
    "step AND NST should equal Act"
  );
  check(
    "false renders as absent, matching the main grids",
    !inters()[0].textContent.includes("false"),
    inters()[0].textContent
  );
  doc.onkeydown({ key: "Escape" });

  // --- one tensor, two projections: E08 reads D_{i,u} AND D_{i,v}.
  // Merged into one card they would light two cells at once and the caption
  // could only name one of them, which reads like a highlight that never
  // cleared. They get a card each.
  go(trace.steps.findIndex((s) => s.einsum === "E08" && s.iteration === 1));
  const dCards = () =>
    allCards().filter((c) => capName(c) === "D");
  check(
    "a tensor read through two projections gets two cards",
    dCards().length === 2,
    allCards().map((c) => c.querySelector(".cap").textContent).join(" | ")
  );
  check(
    "captioned by their own projections",
    dCards().map(capText).join(" ") === "D1,u D1,v",
    dCards().map((c) => c.querySelector(".cap").textContent).join(" ")
  );
  const litIn = (card) =>
    [...card.querySelectorAll("td")]
      .map((td, i) => (td.classList.contains("rd") ? i : -1))
      .filter((i) => i >= 0);
  const pick = (k) =>
    [...$("tstrip").querySelectorAll(".tcard.out td.pick")]
      .find((td) => td.dataset.coord === k)
      .onclick();
  pick("2,5");
  check(
    "each card lights only its own coordinate",
    JSON.stringify(litIn(dCards()[0])) === JSON.stringify([2]) &&
      JSON.stringify(litIn(dCards()[1])) === JSON.stringify([5]),
    "u-card " + litIn(dCards()[0]) + "  v-card " + litIn(dCards()[1])
  );
  pick("0,3");
  check(
    "and both follow the selection",
    JSON.stringify(litIn(dCards()[0])) === JSON.stringify([0]) &&
      JSON.stringify(litIn(dCards()[1])) === JSON.stringify([3]),
    "u-card " + litIn(dCards()[0]) + "  v-card " + litIn(dCards()[1])
  );
  doc.onkeydown({ key: "Escape" });

  // A two-operator map has one intermediate; a plain one-operator map has none.
  go(trace.steps.findIndex((s) => s.einsum === "E09" && s.iteration === 3));
  check(
    "a single-operator einsum shows no intermediate step",
    inters().length === 0,
    allCards().map((c) => c.querySelector(".cap").textContent).join(" | ")
  );
  doc.onkeydown({ key: "Escape" });

  // --- E08: a two-label map with a truth table. Lbl = D ==(int) (D+1).
  const e08 = trace.steps.findIndex(
    (s) => s.einsum === "E08" && s.iteration === 3
  );
  go(e08);
  const derivCards = $("pbody").querySelectorAll(".step").length;
  check(
    "both labelled ops get a card, plus the result",
    derivCards >= 3,
    derivCards + " cards"
  );
  check(
    "merge truth table is rendered",
    !!$("pbody").querySelector("table.tt")
  );
  const hits = $("pbody").querySelectorAll("table.tt tr.hit").length;
  check(
    "exactly one truth-table row is marked as the one taken, per table",
    hits === $("pbody").querySelectorAll("table.tt").length,
    hits + " hits for " + $("pbody").querySelectorAll("table.tt").length + " tables"
  );
  check(
    "no reduce fold on a map-only einsum",
    !$("pbody").querySelector("table.fold")
  );
  doc.onkeydown({ key: "Escape" });

  // --- E11: three operands, so the strip should show all three plus output.
  const e11 = trace.steps.findIndex(
    (s) => s.einsum === "E11" && s.iteration === 3
  );
  go(e11);
  // Operand cards only: intermediates are steps, not inputs.
  const opCards = () =>
    [...$("tstrip").querySelectorAll(".tcard")].filter(
      (c) => !c.classList.contains("inter") && !c.classList.contains("out")
    );
  const caps = opCards().map(capName);
  check(
    "all three operands are shown, in order",
    JSON.stringify(caps) === JSON.stringify(["E", "R", "PushCand"]),
    caps.join(" -> ")
  );
  check(
    "the output is last",
    capName([...$("tstrip").querySelectorAll(".tcard")].slice(-1)[0]) === "delta"
  );
  check(
    "a map lights exactly one cell per operand",
    opCards().reduce(
      (n, c) => n + c.querySelectorAll("td.rd").length, 0) === 3,
    opCards().reduce((n, c) => n + c.querySelectorAll("td.rd").length, 0) + " lit"
  );

  // The lit operand cells must be the values the derivation actually used.
  const litVals = [...$("tstrip").querySelectorAll(".mini td.rd")].map(
    (td) => td.textContent
  );
  const pt = $("pbody").textContent;
  check(
    "lit operand values appear in the derivation",
    // Grids abbreviate booleans to T to stay narrow; the prose spells them out.
    litVals.map((v) => (v === "T" ? "true" : v)).every((v) => pt.includes(v)),
    "lit " + litVals.join(",")
  );
  check(
    "operand grids are drawn from the state BEFORE the einsum ran",
    (() => {
      const eCard = cards().find((c) => capName(c) === "E");
      const lit = eCard.querySelector("td.rd");
      const coord = [...eCard.querySelectorAll("tr")][1];
      const before = trace.steps[e11 - 1].state.E;
      return lit && String(before[Object.keys(before).find((k) => String(before[k]) === lit.textContent)]) === lit.textContent;
    })(),
    "E operand cell should come from the previous step's state"
  );

  // A map's iteration space and its output are the same shape, so the output
  // grid above already IS the space -- no second grid saying the same thing.
  check(
    "a map has no reduce fold and no collapse note",
    !$("pbody").querySelector("table.fold") &&
      !$("snote").querySelector(".collapse")
  );

  // The output card doubles as the picker.
  const outCard = cards().slice(-1)[0];
  const pickable = [...outCard.querySelectorAll("td.pick")];
  check("output cells are pickable", pickable.length === 36, pickable.length + "");
  const target = pickable.find(
    (td) => td.dataset.coord !== outCard.querySelector("td.wr").dataset.coord
  );
  const newCoord = target.dataset.coord;
  target.onclick();
  check(
    "clicking an output cell follows that value",
    $("tstrip").querySelector(".tcard.out td.wr").dataset.coord === newCoord,
    "marked " + $("tstrip").querySelector(".tcard.out td.wr").dataset.coord
  );
  check(
    "and the derivation follows it too",
    ($("pbody").textContent || "").includes("[" + newCoord + "]"),
    $("pbody").textContent.slice(0, 80)
  );
  doc.onkeydown({ key: "Escape" });

  // --- Cell click as the second entry point, on E24 (writes D).
  go(idx);
  const dblk = readBlock("D (8)");
  const dcell = dblk.el.querySelector("td[data-coord]");
  check("output cells carry a coordinate", !!dcell && !!dcell.dataset.coord);
  check("output cells are clickable", typeof dcell.onclick === "function");
  dcell.onclick();
  check(
    "and focuses the coordinate that was clicked",
    ($("pbody").textContent || "").includes("D[" + dcell.dataset.coord + "]"),
    $("pbody").textContent.slice(0, 90)
  );

  // The interpreter's answer must equal what the trace recorded.
  const dTrace = trace.steps[idx].state.D[dcell.dataset.coord];
  check(
    "recomputed value matches the trace",
    $("pbody").textContent.includes(fmtNum(dTrace)),
    "want " + dTrace
  );

  // --- Where the drill-down cannot run, it says why rather than misleading.
  go(0);
  const off = () => $("execpanel").classList.contains("off");
  check("execution panel is off on the setup step", off());
  const e04 = trace.steps.findIndex((s) => s.einsum === "E04");
  go(e04);
  check("execution panel is off on E04", off());
  check(
    "and the subtitle explains that E04 is a lowered cases statement",
    /cases/i.test($("execsub").textContent),
    $("execsub").textContent
  );
  check(
    "an unexpandable step leaves no stale tensors on screen",
    $("tstrip").innerHTML === "" && $("pbody").innerHTML === ""
  );
  go(trace.steps.length - 1);
  check("execution panel is off on the stop step", off());

  // --- E10: the selector. Expandable, but must be honest about the choice.
  const e10 = trace.steps.findIndex(
    (s) => s.einsum === "E10" && s.iteration === 3
  );
  go(e10);
  check("execution panel is live on the selector", !$("execpanel").classList.contains("off"));
  check(
    "selector panel says the choice is read, not recomputed",
    /selector/i.test($("pbody").textContent),
    $("pbody").textContent.slice(-160)
  );

  // --- The panel follows the trace: stepping rebuilds it for the new step.
  go(idx);
  const panelAt = () => $("execsub").textContent;
  const p0 = panelAt();
  doc.onkeydown({ key: "ArrowRight" });
  check("arrow keys still step the trace", +$("slider").value === idx + 1);
  check(
    "and the execution panel follows to the new step",
    panelAt() !== p0 || $("tstrip").querySelectorAll(".tcard").length > 0
  );
  go(idx);

  // ============================================================== compare
  const seq = JSON.parse(
    fs.readFileSync(path.join(HERE, "maxflow_seq_trace.json"), "utf8")
  );
  const scaling = JSON.parse(
    fs.readFileSync(path.join(HERE, "scaling.json"), "utf8")
  );

  // The whole comparison is worthless if the two runs disagree on the answer.
  check(
    "both runs reach the same maximum flow",
    seq.maxFlow === 23 && trace.maxFlow === 23,
    "seq " + seq.maxFlow + " edge " + trace.maxFlow
  );
  check(
    "the sequential trace is the pseudocode: one operation per round",
    seq.rounds === seq.operations,
    seq.rounds + " rounds for " + seq.operations + " operations"
  );
  // Kept as an offline artifact: the generator asserts both runs agree on
  // the answer, so a measured row can never compare a wrong result.
  check(
    "the offline scaling measurement asserts equal flow at every size",
    /same maximum flow/.test(scaling.note),
    scaling.note
  );

  // The EDGE trace gets its header at build time, so read the embedded copy
  // rather than the file on disk.
  const eStart = html.indexOf("const T=") + 8;
  const edge = JSON.parse(html.slice(eStart, html.indexOf(",DOM=", eStart)));
  check(
    "the EDGE trace carries the shared header",
    edge.variant === "edge" && typeof edge.domainView === "string" &&
      typeof edge.rounds === "number" && typeof edge.operations === "number",
    JSON.stringify({v: edge.variant, d: edge.domainView,
                    r: edge.rounds, o: edge.operations})
  );
  check(
    "both traces name the same domain view",
    edge.domainView === seq.domainView,
    edge.domainView + " vs " + seq.domainView
  );

  // The mode switcher lives in the header, where it can say what the two
  // modes are, rather than as an unexplained button in the transport bar.
  check("mode switcher is in the header", !!$("modes") &&
    !!doc.querySelector("header #modes"));
  check("both modes are offered", !!$("mode-step") && !!$("mode-cmp"));
  check(
    "the switcher describes each mode",
    ($("mode-step").textContent || "").length > 20 &&
      ($("mode-cmp").textContent || "").length > 20,
    $("mode-cmp").textContent
  );
  check(
    "step mode is selected first, and explained",
    $("mode-step").getAttribute("aria-pressed") === "true" &&
      /before \/ after/.test($("modeinfo").textContent),
    $("modeinfo").textContent.slice(0, 60)
  );
  check("no stray compare button in the transport bar", !$("cmpbtn"));

  $("mode-cmp").onclick();
  check("compare mode opens", doc.body.classList.contains("compare"));
  check(
    "and hides the single-run view",
    !!$("cmp") && !!$("gA") && !!$("gB")
  );
  check(
    "the modes swap their pressed state",
    $("mode-cmp").getAttribute("aria-pressed") === "true" &&
      $("mode-step").getAttribute("aria-pressed") === "false"
  );
  check(
    "compare mode explains what is being compared",
    /same algorithm/.test($("modeinfo").textContent) &&
      /rounds, not seconds/.test($("modeinfo").textContent),
    $("modeinfo").textContent.slice(0, 80)
  );
  // The bottom transport drives the single-run timeline and does nothing
  // here, so it must be out of the way rather than sitting there inert.
  check(
    "the single-run transport bar is hidden while comparing",
    /body\.compare #bar\{display:none\}/.test(html),
    "expected a rule hiding #bar in compare mode"
  );
  check(
    "both sides are labelled",
    ($("labA").textContent || "").length > 3 &&
      ($("labB").textContent || "").length > 3,
    $("labA").textContent + " / " + $("labB").textContent
  );

  const cmpGo = window.cmpGo;
  const txt = (id) => ($(id).textContent || "").replace(/\s+/g, " ");

  // Rounds are the clock. At the tick where EDGE finishes, the sequential
  // side must still be mid-run -- that IS the comparison.
  cmpGo(edge.rounds);
  check(
    "EDGE finishes first",
    /Finished in/.test(txt("capB")) && !/Finished in/.test(txt("capA")),
    "edge: " + txt("capB").slice(0, 40) + " | seq: " + txt("capA").slice(0, 40)
  );
  check(
    "the finished side is marked",
    $("sideB").classList.contains("done") &&
      !$("sideA").classList.contains("done")
  );

  cmpGo(seq.rounds);
  check(
    "both finish by the last tick",
    /Finished in/.test(txt("capA")) && /Finished in/.test(txt("capB"))
  );
  check(
    "final tallies show equal flow to the sink",
    txt("tallyA").includes("23") && txt("tallyB").includes("23"),
    txt("tallyA") + " || " + txt("tallyB")
  );

  // The honest claim: near-identical work, fewer rounds. If the operation
  // counts ever diverge badly, the note would be making a false claim.
  check(
    "operation counts are within 15% of each other",
    Math.abs(seq.operations - edge.operations) / edge.operations < 0.15,
    "seq " + seq.operations + " vs edge " + edge.operations
  );
  // The framing lives in the header, once, rather than being repeated as a
  // paragraph under the race -- and there is no hand-written narrative in
  // compare mode for another algorithm to have to rewrite.
  check(
    "a tick is stated to be a round, in the header",
    /rounds, not seconds/.test($("modeinfo").textContent),
    txt("modeinfo").slice(-60)
  );
  check("no narrative paragraph under the race", !$("cmpnote"));

  // A round happened all at once, so the graph must show everything it
  // touched. Showing only the last step's highlight meant pushes never
  // appeared at all -- the last step of a round marks relabelled vertices.
  const litEdges = (g) =>
    [...$(g).querySelectorAll("line")].filter(
      (l) => l.getAttribute("stroke") === "#e8590c"
    ).length;
  const litNodes = (g) =>
    [...$(g).querySelectorAll("circle")].filter(
      (c) => c.getAttribute("stroke") === "#e8590c"
    ).length;

  check(
    "the EDGE trace carries a per-round highlight",
    !!edge.roundHighlights && Object.keys(edge.roundHighlights).length > 0
  );

  // Every round: highlighted edges must equal that round's pushes, and
  // highlighted nodes its relabels -- the same numbers the caption states.
  let hlOk = true, hlDetail = "";
  for (let r = 1; r <= edge.rounds; r++) {
    cmpGo(r);
    let pushes = 0, relabels = 0;
    edge.steps.forEach((st) => {
      if (st.round !== r) return;
      if (st.opKind === "push") pushes = st.concurrency || 0;
      if (st.opKind === "relabel") relabels = st.concurrency || 0;
    });
    if (litEdges("gB") !== pushes || litNodes("gB") !== relabels) {
      hlOk = false;
      hlDetail = `round ${r}: lit ${litEdges("gB")}e/${litNodes("gB")}n, ` +
        `expected ${pushes}e/${relabels}n`;
      break;
    }
  }
  check("every round highlights exactly what it did", hlOk, hlDetail);

  // And the contrast is the whole point: a parallel round lights more than
  // the single edge a sequential step can.
  cmpGo(3);
  check(
    "a parallel round lights more edges than a sequential step",
    litEdges("gB") > litEdges("gA"),
    "edge " + litEdges("gB") + " vs seq " + litEdges("gA")
  );

  // Concurrency strip: one bar per EDGE round, and it must vary.
  check(
    "concurrency strip has one bar per EDGE round",
    $("strip").children.length === edge.rounds,
    $("strip").children.length + " bars for " + edge.rounds + " rounds"
  );
  check(
    "bars vary in height, so parallelism is visibly uneven",
    new Set([...$("strip").children].map((b) => b.style.height)).size > 1
  );

  // The scaling numbers are one-time measurement, not interactive state, so
  // they live in gen_scaling.py / scaling.json and the README rather than on
  // the page. Nothing here should be rendering them.
  check("no scaling chart on the page", !$("chart"));
  check(
    "and the scaling data is not inlined",
    !/ratioHi/.test(html),
    "scaling.json should not be embedded"
  );

  // Keyboard ownership while comparing.
  const tickBefore = +$("tick").value;
  doc.onkeydown({ key: "ArrowLeft" });
  check(
    "arrow keys drive the race, not the single-run timeline",
    +$("tick").value === tickBefore - 1,
    "tick " + $("tick").value
  );
  $("mode-step").onclick();
  check("compare mode closes", !doc.body.classList.contains("compare"));
  check(
    "and the transport bar is available again",
    $("mode-step").getAttribute("aria-pressed") === "true"
  );

  // ------------------------------------------------------------- console
  const realErrors = consoleErrors.filter(
    (e) => !/mathjax|cdn|Not implemented|css/i.test(e)
  );
  check(
    "no page errors",
    realErrors.length === 0,
    realErrors.slice(0, 3).join(" | ")
  );

  console.log(`\n${pass} passed, ${fails.length} failed`);
  process.exit(fails.length ? 1 : 0);
}
