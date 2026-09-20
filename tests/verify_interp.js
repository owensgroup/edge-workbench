// Oracle test for the einsum interpreter.
//
// The drill-down recomputes one einsum from its operands. The trace already
// records what that einsum produced. So: replay every step, recompute it from
// the IR, and diff against the recorded result. Any disagreement is an
// interpreter bug -- a wrong merge truth table, a transposed operand, a
// mishandled empty value.
//
//   node verify_interp.js            # summary
//   node verify_interp.js -v         # print every mismatching cell
//
// build_viz.py runs this and refuses to emit index.html if it fails.

const fs = require("fs");
const path = require("path");
const EdgeInterp = require("../edge_workbench/render/edge_interp.js");

const ALG = process.env.EDGE_WORKBENCH_ALG || "max-flow";
const HERE = path.join(__dirname, "..", "algorithms", ALG, "fixtures");
const SPEC = path.join(__dirname, "..", "algorithms", ALG, "spec");
const program = JSON.parse(
  fs.readFileSync(path.join(SPEC, "max_flow_program.json"), "utf8")
);
const trace = JSON.parse(
  fs.readFileSync(path.join(HERE, "maxflow_edge_trace.json"), "utf8")
);

const VERBOSE = process.argv.includes("-v");
const N = trace.graph.nodes.length;

// Spec einsum ID -> position in the IR cascade. E04's three-arm `cases` has
// no IR node and is lowered to three sequential writes to R, which is why the
// two numberings diverge after it. Mirrors EINSUM_INDEX in
// edge-ir-interpreter/tests/test_max_flow_artifact.py.
const EINSUM_INDEX = {
  E01: 0, E02: 1, E03: 2,
  E04: [3, 4, 5],
  E05: 6, E06: 7, E07: 8, E08: 9, E09: 10, E10: 11, E11: 12, E12: 13,
  E13: 14, E14: 15, E15: 16, E16: 17, E17: 18, E18: 19, E19: 20, E20: 21,
  E21: 22, E22: 23, E23: 24, E24: 25,
};

// Steps the interpreter is not expected to reproduce, with the reason.
const SKIP = {
  init: "initialization block, not a cascade einsum",
  stop: "stopping condition, computes no tensor",
  E10: "nondeterministic selector; the IR names the choice function but " +
       "carries no body, so the outcome is displayed, not recomputed",
};

function canon(t) {
  // Compare on presence + value, ignoring key order.
  const out = {};
  Object.keys(t || {}).sort().forEach((k) => (out[k] = t[k]));
  return out;
}

function diff(want, got) {
  const keys = new Set([...Object.keys(want), ...Object.keys(got)]);
  const bad = [];
  for (const k of keys) {
    const a = want[k], b = got[k];
    const aHas = Object.prototype.hasOwnProperty.call(want, k);
    const bHas = Object.prototype.hasOwnProperty.call(got, k);
    if (aHas !== bHas || a !== b) {
      bad.push({
        coord: k,
        trace: aHas ? a : "(absent)",
        interp: bHas ? b : "(absent)",
      });
    }
  }
  return bad;
}

let checked = 0, failed = 0, skipped = 0;
const perEinsum = {};
const failures = [];

for (let s = 1; s < trace.steps.length; s++) {
  const step = trace.steps[s];
  const id = step.einsum;

  if (SKIP[id]) { skipped++; continue; }
  const idx = EINSUM_INDEX[id];
  if (idx === undefined) { skipped++; continue; }

  const before = trace.steps[s - 1].state;
  const after = step.state;
  const outName = step.output;

  let got;
  if (Array.isArray(idx)) {
    // Lowered case arms: run them in order, each over the state the previous
    // one produced. Later writes overwrite earlier ones -- the convention the
    // lowering depends on and that the IR does not record.
    let acc = Object.assign({}, before[outName]);
    for (const i of idx) {
      const st = Object.assign({}, before);
      st[outName] = acc;
      const r = EdgeInterp.evalEinsum(program, i, st, { N });
      // Apply what the arm WROTE, not just what it left present: writing the
      // empty value clears the cell. The source-row arm writes 0 to R[s,*],
      // and 0 is R's empty value -- if that did not clear, the default arm's
      // capacity would survive and the source would still have residual.
      for (const [coord, v] of Object.entries(r.assigned)) {
        if (v === null) delete acc[coord];
        else acc[coord] = v;
      }
    }
    got = acc;
  } else {
    const r = EdgeInterp.evalEinsum(program, idx, before, { N });
    got = r.result;
  }

  const want = canon(after[outName]);
  const bad = diff(want, canon(got));
  checked++;
  perEinsum[id] = perEinsum[id] || { n: 0, bad: 0 };
  perEinsum[id].n++;
  if (bad.length) {
    perEinsum[id].bad++;
    failed++;
    failures.push({ step: s, id, output: outName, iteration: step.iteration, bad });
  }
}

console.log(`steps checked : ${checked}`);
console.log(`steps skipped : ${skipped} (${Object.keys(SKIP).join(", ")})`);
console.log(`mismatches    : ${failed}`);

if (failed) {
  const shown = VERBOSE ? failures : failures.slice(0, 8);
  for (const f of shown) {
    console.log(
      `\n  step ${f.step}  ${f.id}  i=${f.iteration}  output ${f.output}`
    );
    (VERBOSE ? f.bad : f.bad.slice(0, 6)).forEach((b) =>
      console.log(
        `    [${b.coord}]  trace=${b.trace}  interp=${b.interp}`
      )
    );
    if (!VERBOSE && f.bad.length > 6)
      console.log(`    ... ${f.bad.length - 6} more cells`);
  }
  if (!VERBOSE && failures.length > 8)
    console.log(`\n  ... ${failures.length - 8} more steps (-v for all)`);
  console.log("\nFAIL");
  process.exit(1);
}

const ids = Object.keys(perEinsum).sort();
console.log(`einsums covered: ${ids.length}  (${ids.join(" ")})`);
console.log("OK");
