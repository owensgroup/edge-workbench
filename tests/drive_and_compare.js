"use strict";
/**
 * Does the driver reproduce the hand-written trace?
 *
 * This is the acceptance test for promoting the interpreter from "evaluate one
 * Einsum against a recorded state" to "run a whole spec". The recorded trace
 * is 236 steps produced by an independent hand-written implementation of
 * push-relabel, so agreeing with it step for step is a strong claim -- much
 * stronger than reaching the right answer, which a wrong cascade can do.
 *
 * The comparison is on SEMANTIC content only: which Einsum, which generation,
 * which tensor it wrote, and the full state afterwards. Captions and graph
 * highlights are prose about push-relabel and come from display metadata, not
 * from the spec, so the driver does not produce them and they are not
 * compared.
 *
 * Free choices are replayed. `pick-admissible-edge` is genuinely unspecified,
 * so a driven run is free to choose differently and still be correct -- which
 * would make a step-for-step diff meaningless. Replaying the recorded choices
 * removes that degree of freedom, leaving only differences that are real.
 * The second mode below then runs with an actual rule, to check the driver
 * works when it is deciding for itself.
 *
 *     node tests/drive_and_compare.js
 *     node tests/drive_and_compare.js -v
 *     node tests/drive_and_compare.js --self-test   # prove it can fail
 */

const fs = require("fs");
const path = require("path");
const { runCascade, makeSelector, replaySelector } =
  require("../edge_workbench/driver/cascade.js");

const ALG = process.env.EDGE_WORKBENCH_ALG || "max-flow";
const ROOT = path.join(__dirname, "..");
const SPEC = path.join(ROOT, "algorithms", ALG, "spec");
const FIX = path.join(ROOT, "algorithms", ALG, "fixtures");
const VERBOSE = process.argv.includes("-v");

const read = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const program = read(path.join(SPEC, "max_flow_program.json"));
const instance = read(path.join(SPEC, "instance.json"));
const cascade = read(path.join(SPEC, "cascade.json"));
const golden = read(path.join(FIX, "maxflow_edge_trace.json"));

let pass = 0;
const fails = [];
function check(name, cond, detail) {
  if (cond) { pass++; if (VERBOSE) console.log("  ok   " + name); }
  else { fails.push(name); console.log("  FAIL " + name + (detail ? "\n       " + detail : "")); }
}

/** Compare two flat tensor states, reporting the first cell that differs. */
function diffState(a, b) {
  const names = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const n of [...names].sort()) {
    const x = a[n] || {}, y = b[n] || {};
    const coords = new Set([...Object.keys(x), ...Object.keys(y)]);
    for (const c of [...coords].sort()) {
      const xv = x[c], yv = y[c];
      if (xv === yv) continue;
      // The recorded traces store booleans; a driven false is an absent cell.
      if ((xv === undefined && yv === false) || (xv === false && yv === undefined)) continue;
      return `${n}[${c}]: driven ${JSON.stringify(xv)} vs recorded ${JSON.stringify(yv)}`;
    }
  }
  return null;
}

// ======================================================= 1. replayed run ===
console.log(`driving ${ALG} against its recorded trace\n`);

const replayed = runCascade(program, instance, cascade, {
  selector: replaySelector(golden),
});

check("the driven run has the same number of steps",
  replayed.steps.length === golden.steps.length,
  `driven ${replayed.steps.length}, recorded ${golden.steps.length}`);

const n = Math.min(replayed.steps.length, golden.steps.length);
let firstBad = null;
for (let i = 0; i < n; i++) {
  const d = replayed.steps[i], g = golden.steps[i];
  if (d.einsum !== g.einsum || d.iteration !== g.iteration) {
    firstBad = `step ${i}: driven ${d.einsum}@${d.iteration}, ` +
               `recorded ${g.einsum}@${g.iteration}`;
    break;
  }
  const sd = diffState(d.state, g.state);
  if (sd) { firstBad = `step ${i} (${g.einsum}@${g.iteration}) ${sd}`; break; }
}
check("every step agrees: same Einsum, same generation, same state",
  firstBad === null, firstBad);

check("the driver wrote the same output tensor at every step",
  replayed.steps.every((d, i) => !golden.steps[i] || d.output === golden.steps[i].output ||
    golden.steps[i].einsum === "stop"),
  "output tensor mismatch");

check("it took the same number of generations",
  replayed.generations === golden.iterations,
  `driven ${replayed.generations}, recorded ${golden.iterations}`);

// ==================================================== 2. it can decide ====
// Replay proves the loop and the evaluator; it does not prove the driver can
// run without a recording to lean on. This one makes its own choices.
const ruled = runCascade(program, instance, cascade, {});
const finalF = ruled.steps[ruled.steps.length - 1].state.F || {};
let outOfSource = 0;
Object.entries(finalF).forEach(([c, v]) => {
  if (Number(c.split(",")[0]) === 0) outOfSource += v;
});
check("a run that makes its own choices still reaches the published answer",
  outOfSource === 23, `net flow out of the source: ${outOfSource}`);
check("and it terminates in a comparable number of generations",
  ruled.generations > 0 && ruled.generations < 40, String(ruled.generations));

// ================================================= 3. the rules matter ====
// If every rule produced the same run, the selector machinery would be
// decoration. And if a rule changed the ANSWER, the choice would not be free
// after all and the spec would be understating itself.
const answers = new Set(), work = new Set(), shapes = new Set();
["lowest", "highest"].forEach((rule) => {
  const r = runCascade(program, instance, cascade,
    { selector: makeSelector({ "pick-admissible-edge": rule }) });
  const F = r.steps[r.steps.length - 1].state.F || {};
  let v = 0, pushes = 0;
  Object.entries(F).forEach(([c, x]) => { if (Number(c.split(",")[0]) === 0) v += x; });
  r.steps.forEach((s) => {
    if (s.einsum === "E11") pushes += Object.keys(s.state.delta || {}).length;
  });
  answers.add(v);
  work.add(pushes);
  shapes.add(JSON.stringify(Object.entries(F).sort()));
});
check("different rules never change the answer", answers.size === 1 && answers.has(23),
  [...answers].join(","));
// Work, not generations. On this graph both rules finish in 13 generations --
// a parallel round advances every active vertex, so the round count is
// insensitive to which edge each one picks -- but they push a different
// number of times and arrive at a different (equally maximum) flow.
check("but they do change the work, so the rule is really being used",
  work.size > 1, `pushes seen: ${[...work].sort((a, b) => a - b).join(", ")}`);
check("and they reach a different, equally maximum, flow",
  shapes.size > 1, "both rules produced the identical flow assignment");

// ================================================= 4. refuses to guess ====
let refused = false, msg = "";
try {
  runCascade(program, instance, Object.assign({}, cascade, { selectors: {} }), {});
} catch (e) { refused = true; msg = String(e.message); }
check("an unmapped choice function stops the run rather than being guessed",
  refused && /pick-admissible-edge/.test(msg), msg.slice(0, 120));

// ============================================== 5. the comparison bites ====
// A step-for-step comparison that cannot fail is worth nothing, and this one
// has an obvious way to be vacuous: if the diff quietly ignored something, or
// the loop compared zero steps, everything above would still pass. So break
// the run on purpose and require the comparison to notice.
if (process.argv.includes("--self-test")) {
  console.log("\nself-test: each fault must be caught");
  const clone = (x) => JSON.parse(JSON.stringify(x));

  const faults = [
    ["a capacity changed in the instance", () => {
      const i2 = clone(instance);
      i2.tensors.C["0,1"] = 15;          // was 16
      return [program, i2, cascade];
    }],
    ["two body Einsums run in the wrong order", () => {
      const c2 = clone(cascade);
      const b = c2.body;
      const t = b.E12; b.E12 = b.E13; b.E13 = t;
      return [program, instance, c2];
    }],
    ["one arm of E04's lowered `cases` dropped", () => {
      const c2 = clone(cascade);
      c2.setup.E04 = c2.setup.E04.slice(0, 2);
      return [program, instance, c2];
    }],
  ];

  let caught = 0;
  faults.forEach(([name, build]) => {
    const [P, I, C] = build();
    let differs = false;
    try {
      const r = runCascade(P, I, C, { selector: replaySelector(golden) });
      differs = r.steps.length !== golden.steps.length ||
        r.steps.some((d, i) => {
          const g = golden.steps[i];
          return !g || d.einsum !== g.einsum || d.iteration !== g.iteration ||
                 diffState(d.state, g.state) !== null;
        });
    } catch (e) {
      differs = true;                    // a fault that stops the run counts
    }
    console.log(`  ${differs ? "ok  " : "MISS"} ${name}`);
    if (differs) caught++;
  });
  console.log(`\n${caught}/${faults.length} faults caught`);
  if (caught !== faults.length) process.exit(1);
}

console.log(`\n${pass} passed, ${fails.length} failed`);
process.exit(fails.length ? 1 : 0);
