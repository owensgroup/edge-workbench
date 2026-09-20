"use strict";
/**
 * Choice functions for populate actions.
 *
 * A populate (`X_{i,u,v*} = Y_{i,u,v} <<<_{v*} 1(some-name)`) names a choice
 * function that the IR does not define -- `CoordinateOp` in the schema is a
 * bare name, deliberately, because for many algorithms the choice is genuinely
 * free and pinning it would make the specification claim something the
 * algorithm does not.
 *
 * "Free" is not the same as "absent", though, and conflating the two is how a
 * viewer ends up animating a different algorithm than the one it is showing.
 * Max-flow's `pick-admissible-edge` really is free: any admissible edge works,
 * and the seed changes the work but never the answer. Algorithm X's
 * `select-max-val` is not free at all -- it IS the stack discipline, and
 * choosing differently turns depth-first backtracking into something else.
 *
 * So: every name must be mapped to a rule before the cascade will run, and an
 * unmapped name is an error rather than a guess. Where the choice is free, the
 * mapping records which arbitrary rule this run used; where it is not, the
 * mapping is part of the algorithm and belongs under review.
 *
 *     const sel = makeSelector({ "pick-admissible-edge": "lowest" });
 *     const sel = replaySelector(goldenTrace, einsumLabelOf);
 */

// ---------------------------------------------------------------- rules ---
// Each rule sees the candidate points of ONE group -- the points sharing the
// same coordinates on the ranks that are not being populated -- and returns
// the one it chooses. `cands` is never empty.

const RULES = {
  /** Lowest populated coordinate. Deterministic, claims nothing else. */
  lowest: (cands) => cands.reduce((a, b) => (cmpCoord(a, b) <= 0 ? a : b)),

  /** Highest populated coordinate. */
  highest: (cands) => cands.reduce((a, b) => (cmpCoord(a, b) >= 0 ? a : b)),

  /** Largest value; ties broken by lowest coordinate so it stays a function. */
  "max-value": (cands) =>
    cands.reduce((a, b) =>
      b.value > a.value || (b.value === a.value && cmpCoord(b, a) < 0) ? b : a
    ),

  /** Smallest value; ties broken by lowest coordinate. */
  "min-value": (cands) =>
    cands.reduce((a, b) =>
      b.value < a.value || (b.value === a.value && cmpCoord(b, a) < 0) ? b : a
    ),
};

/** Compare two candidates by their populated coordinates, numerically. */
function cmpCoord(a, b) {
  const x = a.populatedCoord;
  const y = b.populatedCoord;
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? -1) - (y[i] ?? -1);
    if (d !== 0) return d;
  }
  return 0;
}

/**
 * A seeded rule. Kept separate from RULES because it needs per-selector state:
 * the whole point of a seed is that successive choices differ.
 *
 * Deliberately a poor man's LCG rather than Math.random: a run has to be
 * reproducible from its seed alone, or "the seed changes the work but never
 * the answer" stops being a checkable claim.
 */
function seededRule(seed) {
  let s = (seed >>> 0) || 1;
  const next = () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
  return (cands) => {
    const sorted = cands.slice().sort(cmpCoord);
    return sorted[Math.floor(next() * sorted.length)];
  };
}

// ------------------------------------------------------------- selectors --

class UnknownSelector extends Error {}

/**
 * Build a selector from a name -> rule mapping.
 *
 * @param mapping  {"pick-admissible-edge": "lowest", ...}. A rule may also be
 *                 {rule: "seeded", seed: 0}.
 */
function makeSelector(mapping) {
  const fns = {};
  Object.entries(mapping || {}).forEach(([name, spec]) => {
    if (typeof spec === "object" && spec && spec.rule === "seeded") {
      fns[name] = seededRule(spec.seed | 0);
      return;
    }
    const rule = RULES[spec];
    if (!rule) {
      throw new UnknownSelector(
        `no rule "${spec}" for selector "${name}". Known rules: ` +
          Object.keys(RULES).join(", ") + ", seeded"
      );
    }
    fns[name] = rule;
  });

  return function select(req) {
    const fn = fns[req.name];
    if (!fn) {
      throw new UnknownSelector(
        `the spec uses a choice function "${req.name}" that this run has no ` +
          `rule for, so the cascade cannot be executed.\n` +
          `  Map it in the algorithm's selectors block, e.g.\n` +
          `      "${req.name}": "lowest"\n` +
          `  Known rules: ${Object.keys(RULES).join(", ")}, seeded.\n` +
          `  Currently mapped: ${Object.keys(fns).join(", ") || "(none)"}\n` +
          `  Guessing is not an option here: for some algorithms the choice ` +
          `is free, for others it is the algorithm.`
      );
    }
    const out = {};
    Object.values(groupBy(req.candidates)).forEach((cands) => {
      const chosen = fn(cands, req);
      out[chosen.coord] = chosen.value;
    });
    return out;
  };
}

/**
 * Replay the choices a recorded trace made.
 *
 * This is what makes "the driver reproduces the hand-written trace" a
 * meaningful claim rather than a coincidence. A free choice is, by definition,
 * not recomputable -- so to compare a generated trace against a recorded one
 * step for step, the generated run has to make the recorded choices. Any
 * divergence that remains is then a real difference in the evaluator or the
 * driver loop, which is the thing under test.
 *
 * It is NOT a way to run a spec. A cascade driven by replay can only reproduce
 * a run someone else already did.
 */
function replaySelector(trace, labelOf) {
  const byKey = {};
  trace.steps.forEach((s) => {
    byKey[`${s.einsum}@${s.iteration}`] = s.state[s.output] || {};
  });
  return function select(req) {
    const key = `${req.label}@${req.generation}`;
    const rec = byKey[key];
    if (!rec) {
      throw new Error(
        `replay: the recorded trace has no step ${key}, so there is no ` +
          `choice to replay. Is the driver producing steps the recording ` +
          `does not have?`
      );
    }
    return Object.assign({}, rec);
  };
}

/** Group candidate points by the coordinates that are NOT being populated. */
function groupBy(candidates) {
  const g = {};
  candidates.forEach((c) => {
    (g[c.groupCoord] = g[c.groupCoord] || []).push(c);
  });
  return g;
}

module.exports = { makeSelector, replaySelector, RULES, UnknownSelector };
