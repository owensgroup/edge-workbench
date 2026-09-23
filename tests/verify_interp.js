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

/** The algorithm to work on: named, or the only one there is. */
function defaultAlg(root) {
  const dir = path.join(root, "algorithms");
  const names = fs.readdirSync(dir).filter(
    (n) => !n.startsWith(".") && fs.statSync(path.join(dir, n)).isDirectory());
  if (names.length === 1) return names[0];
  throw new Error(
    `${names.length} algorithms available (${names.join(", ")}); say which ` +
    `with EDGE_WORKBENCH_ALG`);
}

const EdgeInterp = require("../edge_workbench/render/edge_interp.js");

const ALG = process.env.EDGE_WORKBENCH_ALG || defaultAlg(path.join(__dirname, ".."));
const HERE = path.join(__dirname, "..", "algorithms", ALG, "fixtures");
const SPEC = path.join(__dirname, "..", "algorithms", ALG, "spec");

/** The IR program in a spec directory: found, not named. */
function programFile(dir) {
  const own = new Set(["cascade.json", "instance.json"]);
  const found = fs.readdirSync(dir)
    .filter((f) => f.endsWith(".json") && !own.has(f));
  if (found.length !== 1) {
    throw new Error(`expected one IR program in ${dir}, found ${found}`);
  }
  return path.join(dir, found[0]);
}

// Tensors the write-up names differently from the IR. The interpreter takes
// this from its caller rather than baking one algorithm's names in.
const ALIAS = JSON.parse(
  fs.readFileSync(path.join(SPEC, "cascade.json"), "utf8")
).displayNames || {};
const program = JSON.parse(
  fs.readFileSync(programFile(SPEC), "utf8")
);
const trace = JSON.parse(
  fs.readFileSync(path.join(HERE, "maxflow_edge_trace.json"), "utf8")
);

const VERBOSE = process.argv.includes("-v");
const CASCADE = JSON.parse(
  fs.readFileSync(path.join(SPEC, "cascade.json"), "utf8")
);
const N = Math.max(...Object.values(
  JSON.parse(fs.readFileSync(path.join(SPEC, "instance.json"), "utf8")).extent
));

// Spec einsum label -> position in the IR cascade, read from the algorithm's
// cascade.json rather than repeated here. A label mapping to a LIST is one
// written Einsum lowered to several IR nodes, which is why a written
// numbering and the IR's diverge.
const EINSUM_INDEX = CASCADE.labels || {};

// Steps the interpreter is not expected to reproduce, and why. The first two
// are structural; the rest are DERIVED from the program -- an Einsum whose
// outcome depends on a choice function cannot be recomputed from the spec,
// because the spec names the function and does not define it.
const SKIP = {
  [CASCADE.initLabel || "init"]: "initialization block, not a cascade einsum",
  [CASCADE.stopLabel || "stop"]: "stopping condition, computes no tensor",
};
Object.entries(EINSUM_INDEX).forEach(([label, idx]) => {
  const nodes = (Array.isArray(idx) ? idx : [idx])
    .map((i) => program.main_edge.cascade.einsums[i]);
  if (nodes.some((e) => (e.specs || []).some((sp) => sp.kind === "populate"))) {
    SKIP[label] =
      "nondeterministic selector; the IR names the choice function but " +
      "carries no body, so the outcome is displayed, not recomputed";
  }
});

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
      const r = EdgeInterp.evalEinsum(program, i, st, { N, tensorAlias: ALIAS });
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
    const r = EdgeInterp.evalEinsum(program, idx, before, { N, tensorAlias: ALIAS });
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
if (!ids.length) {
  // A replay that checked no einsums would report zero mismatches and call
  // itself OK. That has happened: the cascade's label map moved and this
  // file kept reading the old key, so every step fell through as "not in the
  // index". Coverage is part of the result, not a statistic beside it.
  console.log(
    "\nFAIL: covered nothing. Every step fell through as unindexed, so the " +
    "zero mismatches above mean nothing. Check that cascade.json's label " +
    "map is where this file looks for it.");
  process.exit(1);
}
console.log("OK");
