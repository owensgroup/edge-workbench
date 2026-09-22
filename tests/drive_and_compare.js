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
 * Free choices are replayed. `pick-admissible-edge` is genuinely unspecified
 * -- the Einsum says ANY admissible edge, and cascade.json's default is
 * seeded-random for that reason -- so a driven run is free to choose
 * differently and still be correct, which would make a step-for-step diff
 * meaningless. Replaying the recorded choices removes that degree of freedom,
 * leaving only differences that are real.
 *
 * The later sections then let the driver choose for itself, and check the
 * freedom rather than assuming it: 27 different ways of choosing, one answer,
 * varying work.
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

// ============================================ 3. the choice is free ====
// `1(pick-admissible-edge)` says ANY admissible edge, and cascade.json's
// default is seeded-random rather than a rule for exactly that reason. But
// "the choice is free" should be a measurement, not a claim: run it many ways
// and require the ANSWER to be invariant while the WORK varies.
//
// If the answer ever moved, the choice would not be free and the spec would
// be understating itself. If the work never moved, the selector would not be
// reaching the cascade at all and every check here would be vacuous.
const CAP = Object.fromEntries(
  Object.entries(instance.tensors.C).map(([k, v]) => [k, v]));

/** Value of the flow, and whether it is a flow at all. */
function appraise(r) {
  const F = r.steps[r.steps.length - 1].state.F || {};
  let value = 0;
  const net = {};
  const problems = [];
  Object.entries(F).forEach(([c, f]) => {
    const [u, v] = c.split(",").map(Number);
    net[u] = (net[u] || 0) + f;
    if (f > 0 && f > (CAP[c] || 0)) problems.push(`${c} carries ${f} > cap`);
    const back = F[`${v},${u}`] || 0;
    if (back !== -f) problems.push(`${c} not antisymmetric`);
  });
  Object.entries(net).forEach(([u, n]) => {
    if (Number(u) !== 0 && Number(u) !== 5 && n !== 0)
      problems.push(`vertex ${u} leaks ${n}`);
  });
  value = net[0] || 0;
  let pushes = 0;
  r.steps.forEach((s) => {
    if (s.einsum === "E11") pushes += Object.keys(s.state.delta || {}).length;
  });
  return { value, pushes, problems,
           shape: JSON.stringify(Object.entries(F).sort()) };
}

const runs = [];
for (let seed = 0; seed < 25; seed++) {
  runs.push(appraise(runCascade(program, instance, cascade, {
    selector: makeSelector({
      "pick-admissible-edge": { rule: "seeded", seed } }),
  })));
}
["select-min-coord", "select-max-coord"].forEach((rule) => {
  runs.push(appraise(runCascade(program, instance, cascade,
    { selector: makeSelector({ "pick-admissible-edge": rule }) })));
});

const values = new Set(runs.map((r) => r.value));
const work = new Set(runs.map((r) => r.pushes));
const shapes = new Set(runs.map((r) => r.shape));
const broken = runs.filter((r) => r.problems.length);

check("27 ways of choosing, and every one reaches the published answer",
  values.size === 1 && values.has(23), [...values].join(","));
check("every one of them is a feasible flow, not just the right number",
  broken.length === 0, broken.slice(0, 2).map((r) => r.problems[0]).join("; "));
// Work, not generations. A parallel round advances every active vertex, so on
// this graph the round count is insensitive to which edge each one picks --
// but the number of pushes is not, and neither is where the flow ends up.
check("but the work varies, so the choice is really reaching the cascade",
  work.size > 1, `pushes seen: ${[...work].sort((a, b) => a - b).join(", ")}`);
check("and different choices reach different, equally maximum, flows",
  shapes.size > 1, "every choice produced the identical flow assignment");
check("the same seed gives the same run, so a build is reproducible",
  JSON.stringify(appraise(runCascade(program, instance, cascade, {
    selector: makeSelector({ "pick-admissible-edge": { rule: "seeded", seed: 7 } }),
  }))) === JSON.stringify(appraise(runCascade(program, instance, cascade, {
    selector: makeSelector({ "pick-admissible-edge": { rule: "seeded", seed: 7 } }),
  }))));

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
