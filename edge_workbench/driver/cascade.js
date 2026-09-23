"use strict";
/**
 * Run a whole EDGE specification and produce a trace.
 *
 * Until now the interpreter could evaluate ONE Einsum against a state that a
 * hand-written reference implementation had already computed. That is enough
 * to check a trace and not enough to make one, which is why every algorithm
 * needed its own reference implementation and why none of this generalised.
 *
 * This is the other half: seed the inputs, run the initialization, run the
 * cascade body once per generation, test the stopping condition, repeat. The
 * trace stops being something a person wrote and becomes something the spec
 * produces.
 *
 * WHAT THIS DELIBERATELY DOES NOT PRODUCE
 * ---------------------------------------
 * The recorded traces carry `caption`, `expr` and `graphHighlight` as well as
 * state. Those are prose and presentation -- "push 12 on 1,3" is a sentence
 * about push-relabel, not a consequence of the spec -- so they come from the
 * algorithm's display metadata and its domain view, not from here. A driven
 * trace therefore matches a hand-written one on *semantic* content (which
 * Einsum, which generation, which output, and the full state after it) and
 * nowhere else. That is the right seam: it is exactly the content a second
 * implementation could disagree about.
 */

const path = require("path");
const EdgeInterp = require(path.join(__dirname, "..", "render", "edge_interp.js"));
const { makeSelector, replaySelector } = require("./selectors.js");

/**
 * @param program   parsed IR program
 * @param instance  {extent, scalars, tensors}  the problem input
 * @param cascade   parsed cascade.json: step labels -> IR indices, selectors
 * @param opts      {selector}  overrides cascade.selectors; used by replay
 */
function runCascade(program, instance, cascade, opts) {
  opts = opts || {};
  const extents = instance.extent || {};
  const N = Math.max(...Object.values(extents));
  // Shape symbols a rank expression may read as a VALUE -- `|R|` in a depth
  // stamp. Taken from the declared rank shapes and the instance's extents, so
  // an algorithm does not have to state the same number twice.
  const shapes = shapeEnv(program, extents, instance.scalars || {});
  const prog = withScalars(program, instance.scalars || {});
  const select = opts.selector || makeSelector(cascade.selectors || {});
  // Some tensors are written in the spec under one name and shown under
  // another -- the IR's `Delta` is the reader's `delta`. The interpreter
  // already aliases on READ; a driver has to alias on WRITE too, or the
  // cascade quietly splits into two tensors that never see each other.
  const alias = cascade.displayNames || {};
  const shown = (t) => (alias[t] !== undefined ? alias[t] : t);
  const maxGen = cascade.maxGenerations || 1000;

  // Flat state: {tensorName: {"u,v": value}}. Generations are not carried --
  // a tensor holds its current generation and an Einsum writing X_{i+1} just
  // overwrites X. That works because within one round each tensor is written
  // at most once, and it is the same convention the recorded traces use.
  const state = {};
  Object.entries(instance.tensors || {}).forEach(([k, v]) => {
    state[k] = Object.assign({}, v);
  });

  const steps = [];
  const emit = (label, generation, output) => {
    const step = {
      id: steps.length,
      einsum: label,
      iteration: generation,
      output: output,
      state: snapshot(state),
    };
    steps.push(step);
    // A run that throws has still produced everything up to the throw, and
    // that prefix is usually where the answer is. Without this the only way
    // to see it is to make the failure not happen.
    if (opts.onStep) opts.onStep(step);
  };

  /**
   * Run a group of IR nodes that together are ONE step, and record it.
   *
   * Two rules, and the difference between them is the whole of `cases`:
   *
   *   Across steps, an Einsum REPLACES its output. `Adm_{i+1}` is defined
   *   entirely by the Einsum that writes it, so a coordinate that Einsum does
   *   not produce is empty -- not "whatever generation i had there". Merging
   *   instead would leave last generation's values standing wherever the new
   *   one happens to be absent, which is a stale-state bug that looks like a
   *   correct answer for a long time.
   *
   *   Within a step, the nodes ACCUMULATE. A lowered `cases` is several IR
   *   nodes writing one tensor, later arms overwriting earlier ones -- that
   *   sequencing is what makes the u=s arm of E04 win. The same applies to
   *   initialization, where D is written twice: once to zero everywhere, then
   *   again to |V| at the source.
   *
   * So the first write to a tensor within a step clears it and the rest merge
   * into it. Clearing happens AFTER evaluating, because an Einsum may read the
   * tensor it writes (E12 reads F_i to produce F_{i+1}).
   */
  const runNodes = (nodes, label, generation, record) => {
    const freshened = new Set();
    let out = null;
    nodes.forEach((e) => {
      const R = EdgeInterp.evalEinsumNode(prog, e, state, {
        N, extents, shapes,
        selector: select, label, generation, tensorAlias: alias,
      });
      const name = shown(R.output);
      if (!freshened.has(name)) { state[name] = {}; freshened.add(name); }
      const target = state[name];
      Object.entries(R.assigned).forEach(([coord, v]) => {
        // `assigned` records what was WRITTEN, including cells written the
        // empty value (as null). Those clear rather than persist -- which is
        // how a later case arm blanks what an earlier one put down.
        if (v === null || v === undefined) delete target[coord];
        else target[coord] = v;
      });
      out = name;
    });
    if (record !== false) emit(label, generation, out);
    return out;
  };

  const runLabel = (label, idx, generation) =>
    runNodes((Array.isArray(idx) ? idx : [idx])
      .map((i) => prog.main_edge.cascade.einsums[i]), label, generation);

  // ---- initialization ---------------------------------------------------
  // Several Einsums, one step: the reader wrote "here is the starting state",
  // not four separate moves.
  runNodes(prog.initialization.einsums || [], cascade.initLabel || "init", null);

  // ---- which Einsums are the loop, and which run once -------------------
  const { setup, body } = splitCascade(prog, cascade);

  setup.forEach(([label, idx]) => runLabel(label, idx, null));

  // ---- the body, once per generation, tested AFTER ----------------------
  // A do-while: the condition is checked once a generation has completed,
  // with the iterative rank bound to the generation just finished, so a
  // predicate written over `i+1` reads what that generation produced. The
  // loop belongs to the generational rank -- every Einsum carrying it runs
  // every generation -- rather than having a beginning and an end.
  const stop = prog.main_edge.cascade.stopping_conditions || [];
  let gen = 1;
  let stopped = false;
  for (; gen <= maxGen && !stopped; gen++) {
    for (const [label, idx] of body) runLabel(label, idx, gen);
    if (stopHolds(prog, stop, state, N, alias)) {
      emit(cascade.stopLabel || "stop", gen, null);
      stopped = true;
    }
  }
  if (!stopped) {
    throw new Error(
      `the cascade ran ${maxGen} generations without its stopping condition ` +
        `holding. Either the instance is larger than maxGenerations allows, ` +
        `or the cascade does not terminate on it.`
    );
  }

  return { generations: gen - 1, steps };
}

// --------------------------------------------------------------- pieces ---

/**
 * Which labelled Einsums run once, and which run every generation.
 *
 * DERIVED, not declared. An Einsum whose output generation is a rank
 * VARIABLE (`Act_{i,u}`, `F_{i+1,u,v}`) carries the generational rank and so
 * belongs to the loop. One whose output generation is a LITERAL
 * (`FS_{1,u,v}`), or which has no generational rank at all (`NST_u`), does
 * not: it computes one fixed generation and running it again would compute
 * the same thing.
 *
 * "The same thing" is the part worth checking rather than assuming. Running a
 * literal-generation Einsum once is equivalent to running it every generation
 * only if nothing it reads changes between generations -- and a flat state,
 * which keeps one current value per tensor rather than one per generation,
 * would be CORRUPTED by re-running it: `F_{1,u,v} = FS . FS` re-executed in
 * generation 5 would overwrite the live F. So a setup Einsum that reads a
 * varying generation is refused, loudly, instead of quietly producing a
 * wrong page.
 */
function splitCascade(prog, cascade) {
  const decls = {};
  (prog.declarations || []).forEach((d) => (decls[d.name] = d));
  const labels = Object.entries(cascade.labels || {});
  if (!labels.length) {
    throw new Error("cascade.json declares no `labels`: nothing to run");
  }
  const nodesOf = (idx) => (Array.isArray(idx) ? idx : [idx])
    .map((i) => prog.main_edge.cascade.einsums[i]);

  const isVarGen = (r) =>
    !!r && (r.kind === "var" ||
            (r.kind === "arith" && (isVarGen(r.lhs) || isVarGen(r.rhs))));

  const setup = [], body = [];
  labels.forEach(([label, idx]) => {
    const nodes = nodesOf(idx);
    // The output's generation is position 0 only when the tensor HAS a
    // generational rank; NST_u has none, so its `u` is not a generation.
    const iterative = nodes.some((e) => {
      const d = decls[e.output_tensor];
      const generational = d && d.ranks[0] && d.ranks[0].name === "I";
      return generational && isVarGen(e.output_ranks[0]);
    });
    (iterative ? body : setup).push([label, idx]);
    if (!iterative) {
      const reads = varGenerationReads(nodes, decls);
      if (reads.length) {
        throw new Error(
          `${label} writes a fixed generation but reads ${reads.join(", ")} ` +
          `at a varying one, so it is neither setup nor loop body. This ` +
          `driver keeps one current value per tensor, so it cannot re-run ` +
          `${label} each generation without overwriting live state.`);
      }
    }
  });
  return { setup, body };
}

/**
 * Tensors a group of Einsums reads at a VARYING generation.
 *
 * Two things have to hold, and checking only the second is a trap: the tensor
 * must be declared with a generational rank, AND the index in that position
 * must be a rank variable. `S_u`'s first index is the variable `u`, but S has
 * no generational rank, so u is not a generation and S does not vary.
 */
function varGenerationReads(nodes, decls) {
  const out = new Set();
  const isVar = (r) =>
    !!r && (r.kind === "var" ||
            (r.kind === "arith" && (isVar(r.lhs) || isVar(r.rhs))));
  const walk = (n) => {
    if (!n || typeof n !== "object") return;
    const p = n.proj;
    if (p && p.ranks && p.ranks.length) {
      const d = decls[p.tensor];
      const generational = d && d.ranks[0] && d.ranks[0].name === "I";
      if (generational && isVar(p.ranks[0])) out.add(p.tensor);
    }
    Object.values(n).forEach(walk);
  };
  nodes.forEach((e) => walk(e.expression));
  return [...out];
}

/** Deep-enough copy: one level of tensors, each a flat coord->value map. */
function snapshot(state) {
  const out = {};
  Object.entries(state).forEach(([k, v]) => (out[k] = Object.assign({}, v)));
  return out;
}

/**
 * The value of each shape symbol a rank expression might read.
 *
 * A declaration says rank R has shape "|R|"; the instance says R has extent
 * 4. So "|R|" is 4, and a depth stamp can write `depth * |R| + r` without the
 * instance repeating the number under a second name. Explicit scalars win,
 * for the case where a symbol is not any rank's shape.
 */
function shapeEnv(program, extents, scalars) {
  const env = {};
  (program.declarations || []).forEach((d) => {
    (d.ranks || []).forEach((r) => {
      if (r.shape && extents[r.name] !== undefined) {
        env[r.shape] = extents[r.name];
      }
    });
  });
  Object.entries(scalars).forEach(([k, v]) => (env[k] = v));
  return env;
}

/**
 * Fill in zero-rank tensors the IR declares but cannot value.
 *
 * `VertexCount` is the case: |V| is graph data, so the spec names it and the
 * host supplies it. Returns a copy -- mutating the caller's program would
 * make the value leak between instances.
 */
function withScalars(program, scalars) {
  const p = Object.assign({}, program);
  p.declarations = program.declarations.map((d) =>
    Object.prototype.hasOwnProperty.call(scalars, d.name)
      ? Object.assign({}, d, { value: scalars[d.name] })
      : d
  );
  return p;
}

/**
 * Does any stopping condition hold?
 *
 * Only the shape the zoo actually uses so far: `occupancy(X) == literal`.
 * Anything else throws rather than being silently read as false -- a
 * stopping condition quietly evaluating to false is an infinite loop, and an
 * infinite loop that ends at maxGenerations looks like a slow algorithm
 * rather than an unsupported predicate.
 */
function stopHolds(prog, conditions, state, N, alias) {
  return conditions.some((c) => {
    const p = c.predicate;
    if (p.kind !== "comparison") {
      throw new Error(`unsupported stopping predicate kind: ${p.kind}`);
    }
    const lhs = evalPredSide(prog, p.lhs, state, alias);
    const rhs = evalPredSide(prog, p.rhs, state, alias);
    switch (p.op) {
      case "==": return lhs === rhs;
      case "!=": return lhs !== rhs;
      case "<": return lhs < rhs;
      case "<=": return lhs <= rhs;
      case ">": return lhs > rhs;
      case ">=": return lhs >= rhs;
      default: throw new Error(`unsupported comparison op: ${p.op}`);
    }
  });
}

function evalPredSide(prog, node, state, alias) {
  if (node.kind === "property_app") {
    if (node.name !== "occupancy") {
      throw new Error(`unsupported property in a stopping condition: ${node.name}`);
    }
    // Occupancy: how many points the tensor actually holds. Reading the flat
    // state means this is the CURRENT generation of the tensor, which is what
    // `||Act_{i+1}|| == 0` means once the body has run.
    const t = node.operands[0].tensor;
    const decls = {};
    prog.declarations.forEach((d) => (decls[d.name] = d));
    const empty = decls[t] ? decls[t].empty_value : undefined;
    const cells = state[(alias && alias[t] !== undefined) ? alias[t] : t] || {};
    return Object.values(cells).filter((v) => !EdgeInterp.isEmpty(v, empty)).length;
  }
  if (node.kind === "tensor_value") {
    const t = node.proj.tensor;
    const d = prog.declarations.find((x) => x.name === t);
    return EdgeInterp.num(d && d.value !== null ? d.value : (d && d.empty_value));
  }
  if (node.kind === "literal") return Number(node.value);
  throw new Error(`unsupported stopping-condition operand: ${node.kind}`);
}

module.exports = { runCascade, makeSelector, replaySelector };
