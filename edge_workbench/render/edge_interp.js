// EDGE einsum interpreter -- evaluates ONE einsum from the IR over a trace
// state, recording provenance for every point of the iteration space.
//
// This is deliberately not a general EDGE evaluator: it does not drive the
// fixed point, sequence generations, or resolve which generation an operand
// refers to. It re-runs a single einsum whose operands are already sitting in
// the trace. That is all the drill-down needs, and it is a much smaller
// contract than a full interpreter.
//
// Loadable three ways: `require` from node, a plain <script> tag, or inlined
// verbatim into a generated page. No imports.

const EdgeInterp = (function () {
  "use strict";

  // ---------------------------------------------------------------- merges
  // The 16 merge operators, as presence truth tables keyed [left][right].
  // Transcribed from edge_ir/runtime/op_properties.py; the paper's Appendix A
  // is the source. Order of the four bits: (F,F) (F,T) (T,F) (T,T).
  const MERGE_TT = {
    pass_through: [true, true, true, true],
    no_pass: [false, false, false, false],
    intersect: [false, false, false, true],
    take_left_only: [false, false, true, false],
    take_left: [false, false, true, true],
    take_right_only: [false, true, false, false],
    take_right: [false, true, false, true],
    xor: [false, true, true, false],
    union: [false, true, true, true],
    nor: [true, false, false, false],
    xnor: [true, false, false, true],
    not_right: [true, false, true, false],
    not_left: [true, true, false, false],
    implies_left: [true, false, true, true],
    implies_right: [true, true, false, true],
    nand: [true, true, true, false],
  };

  const MERGE_GLYPH = {
    pass_through: "T", no_pass: "F", intersect: "∩",
    take_left_only: "⊖l", take_left: "←",
    take_right_only: "⊖r", take_right: "→", xor: "⊕",
    union: "∪", nor: "∪̄", xnor: "≡",
    not_right: "↛", not_left: "↚", implies_left: "⇐",
    implies_right: "⇒", nand: "∩̄",
  };

  function merges(name, l, r) {
    const tt = MERGE_TT[name];
    if (!tt) throw new Error("unknown merge operator: " + name);
    return tt[(l ? 2 : 0) + (r ? 1 : 0)];
  }

  // -------------------------------------------------------------- computes
  // Compute operators. `+ - * /` are IR builtins; the rest arrive as
  // user-defined names, which is why their bodies have to live somewhere --
  // the IR records only the name. These match eval_edge.py.
  const COMPUTE = {
    "+": (a, b) => a + b,
    "-": (a, b) => a - b,
    "*": (a, b) => a * b,
    "/": (a, b) => a / b,
    min: (a, b) => Math.min(a, b),
    max: (a, b) => Math.max(a, b),
    eq: (a, b) => a === b,
    gt: (a, b) => a > b,
    lt: (a, b) => a < b,
    AND: (a, b) => Boolean(a) && Boolean(b),
    OR: (a, b) => Boolean(a) || Boolean(b),
    take_left: (a) => a,
    take_right: (a, b) => b,
    // The partial-update operator `<<`: take the right value where it
    // exists, otherwise keep the left. Written as a user-defined op because
    // IR compute builtins are limited to + - * / and the operator-name
    // pattern rejects "<<".
    update: (a, b, lp, rp) => (rp ? b : a),
  };

  const COMPUTE_GLYPH = {
    "*": "×", eq: "≡", gt: ">", lt: "<",
    take_left: "←", take_right: "→", update: "<<",
    min: "min", max: "max", AND: "AND", OR: "OR",
  };

  function glyph(name, kind) {
    const t = kind === "merge" ? MERGE_GLYPH : COMPUTE_GLYPH;
    return t[name] || name;
  }

  // ---------------------------------------------------------------- values
  // A value equal to a tensor's declared empty value is ABSENT. This rule is
  // load-bearing -- it is why a saturated residual edge (R = 0) drops out of
  // E07's intersect with no positivity guard -- and it is NOT recorded
  // anywhere in the IR. Hardcoded here, same as in eval_edge.py.
  function num(v) {
    if (v === "inf") return Infinity;
    if (v === "-inf") return -Infinity;
    return v;
  }

  function isEmpty(value, emptyValue) {
    const e = num(emptyValue);
    if (e === null || e === undefined) return false;
    return value === e;
  }

  // ------------------------------------------------------------ IR helpers
  function rankName(r) {
    if (!r) return "?";
    if (r.kind === "var") return r.name;
    if (r.kind === "literal") return String(r.value);
    if (r.kind === "arith") return rankName(r.lhs) + r.op + rankName(r.rhs);
    return "?";
  }

  // Rank variables to enumerate: every variable mentioned anywhere, minus
  // the generation variable. The generation is not enumerated -- the trace's
  // state is flat, one entry per tensor, already holding the right
  // generation for this point in the cascade.
  function collectRankVars(node, out) {
    if (!node || typeof node !== "object") return out;
    if (node.kind === "input" && node.proj) {
      node.proj.ranks.forEach((r) => {
        if (r.kind === "var") out.add(r.name);
      });
    }
    for (const k of Object.keys(node)) {
      const v = node[k];
      if (Array.isArray(v)) v.forEach((x) => collectRankVars(x, out));
      else if (v && typeof v === "object") collectRankVars(v, out);
    }
    return out;
  }

  // ------------------------------------------------------------ evaluation
  // Every node returns {present, value, prov} where prov is a display record.

  // IR tensor name -> name used in the state, supplied by the caller. The IR
  // requires tensor names to start uppercase (`^[A-Z][A-Za-z0-9_]*$`), so a
  // write-up's lowercase name cannot be carried over verbatim and something
  // has to map between them -- but which names those are is a fact about one
  // algorithm, so it arrives in `opts.tensorAlias` (from its cascade.json)
  // rather than being compiled in here.
  function makeCtx(program, state, opts) {
    const decls = {};
    program.declarations.forEach((d) => (decls[d.name] = d));
    const alias = Object.assign({}, opts.tensorAlias || {});
    return {
      decls,
      alias,
      stateName: (t) => (alias[t] !== undefined ? alias[t] : t),
      state: state,
      N: opts.N,
      genVar: opts.genVar || "i",
      // rank names declared as the generational rank, per tensor
      isGenRank: (tensor, idx) => {
        const d = decls[tensor];
        return !!(d && d.ranks[idx] && d.ranks[idx].name === "I");
      },
    };
  }

  function lookupInput(node, bind, ctx) {
    const tensor = node.proj.tensor;
    const decl = ctx.decls[tensor];
    const ranks = node.proj.ranks;

    // Zero-rank tensor: a literal stand-in. Its value is on the declaration.
    if (ranks.length === 0) {
      const v = decl && decl.value !== null && decl.value !== undefined
        ? num(decl.value)
        : num(decl ? decl.empty_value : undefined);
      return {
        present: true,
        value: v,
        prov: { tensor, coord: null, present: true, value: v, scalar: true },
      };
    }

    // Drop the generational rank; the trace state is flat.
    const coords = [];
    ranks.forEach((r, idx) => {
      if (ctx.isGenRank(tensor, idx)) return;
      coords.push(r.kind === "var" ? bind[r.name] : Number(r.value));
    });
    const key = coords.join(",");
    const t = ctx.state[ctx.stateName(tensor)] || {};
    const has = Object.prototype.hasOwnProperty.call(t, key);
    const raw = has ? t[key] : undefined;
    const present = has && !isEmpty(raw, decl ? decl.empty_value : undefined);
    const value = present ? raw : num(decl ? decl.empty_value : 0);
    return {
      present,
      value,
      prov: {
        tensor,
        coord: key,
        ranks: ranks.map(rankName),
        present,
        value: present ? raw : null,
        emptyValue: decl ? decl.empty_value : null,
      },
    };
  }

  function evalNode(node, bind, ctx, specs) {
    if (node.kind === "input") return lookupInput(node, bind, ctx);

    if (node.kind === "anonymous") {
      const inner = evalNode(node.expression, bind, ctx, specs);
      return {
        present: inner.present,
        value: inner.value,
        prov: {
          anonymous: true,
          boundTo: node.ranks.map(rankName),
          inner: inner.prov,
          present: inner.present,
          value: inner.present ? inner.value : null,
        },
      };
    }

    if (node.kind === "unary") {
      const inner = evalNode(node.operand, bind, ctx, specs);
      // `not` over presence-carrying Booleans: an absent Boolean is false,
      // so its negation is true and present.
      const v = !(inner.present && inner.value);
      return {
        present: true,
        value: v,
        prov: {
          op: "not",
          inner: inner.prov,
          present: true,
          value: v,
        },
      };
    }

    if (node.kind === "binary") {
      const spec = specs[node.label];
      const lhs = evalNode(node.lhs, bind, ctx, specs);
      const rhs = evalNode(node.rhs, bind, ctx, specs);

      // A ReduceSpec on this label means the node is the unary-reduce
      // workaround: `tensor OP identityScalar`. The right operand is a
      // placeholder to give the spec a label to hang on, not a real operand.
      if (spec && spec.kind === "reduce") {
        return {
          present: lhs.present,
          value: lhs.value,
          reduceHere: { spec, lhsProv: lhs.prov, rhsProv: rhs.prov },
          prov: lhs.prov,
        };
      }

      // A PopulateSpec is a selector whose choice function has no body in
      // the IR. The caller supplies the recorded outcome instead.
      if (spec && spec.kind === "populate") {
        return {
          present: lhs.present,
          value: lhs.value,
          populateHere: { spec, lhsProv: lhs.prov },
          prov: lhs.prov,
        };
      }

      const mergeName = spec.merge_op.symbol;
      const computeName = spec.compute_op.symbol || spec.compute_op.name;
      const present = merges(mergeName, lhs.present, rhs.present);
      const fn = COMPUTE[computeName];
      if (!fn) throw new Error("unknown compute operator: " + computeName);
      const value = present
        ? fn(lhs.value, rhs.value, lhs.present, rhs.present)
        : null;
      return {
        present,
        value,
        prov: {
          label: node.label,
          merge: mergeName,
          mergeGlyph: glyph(mergeName, "merge"),
          compute: computeName,
          computeGlyph: glyph(computeName, "compute"),
          lhs: lhs.prov,
          rhs: rhs.prov,
          lhsPresent: lhs.present,
          rhsPresent: rhs.present,
          present,
          value,
        },
      };
    }

    throw new Error("unhandled expression node: " + node.kind);
  }

  // ----------------------------------------------------------------- entry
  /**
   * Evaluate one einsum.
   *
   * @param program  the IR program (parsed max_flow_program.json)
   * @param index    position of the einsum in program.main_edge.cascade
   * @param state    flat tensor state BEFORE this einsum runs
   *                 ({tensorName: {"u,v": value}})
   * @param opts     {N, recordedOutput, selector, label, generation}
   *                 A populate's choice function is a bare name in the IR, so
   *                 its outcome cannot be recomputed from the spec alone.
   *                 Supply EITHER `selector` (a function that decides) or
   *                 `recordedOutput` (the outcome a run already made). The
   *                 viewer passes recordedOutput because it is showing a trace
   *                 that already exists; the driver passes a selector because
   *                 it is producing one.
   * @returns {output, outputRanks, points, result, reduced, note}
   */
  function evalEinsum(program, index, state, opts) {
    return evalEinsumNode(
      program, program.main_edge.cascade.einsums[index], state, opts);
  }

  /**
   * As evalEinsum, but for an einsum node given directly.
   *
   * The cascade's initialization einsums live in `program.initialization`,
   * not in the indexed body, so driving a whole program needs a way in that
   * is not "position in the main cascade".
   */
  function evalEinsumNode(program, einsum, state, opts) {
    opts = opts || {};
    const ctx = makeCtx(program, state, opts);
    const specs = {};
    einsum.specs.forEach((s) => (specs[s.label] = s));

    // The iteration space is the union of the ranks the operands are read
    // over AND the output's own ranks. The output ranks matter on their own:
    // E04's source-row arm reads only S_u, but writes R_{1,u,v} for every v,
    // so v has to be enumerated even though no operand mentions it.
    const varSet = collectRankVars(einsum, new Set());
    einsum.output_ranks.forEach((r) => {
      if (r.kind === "var") varSet.add(r.name);
    });
    const vars = Array.from(varSet);
    const outRanks = einsum.output_ranks
      .filter((r) => r.kind === "var" && r.name !== ctx.genVar)
      .map((r) => r.name);
    const iterVars = vars.filter((v) => v !== ctx.genVar).sort();

    const outDecl = ctx.decls[einsum.output_tensor];
    const outEmpty = outDecl ? outDecl.empty_value : null;

    // Enumerate the iteration space.
    const points = [];
    const N = ctx.N;
    const walk = (i, bind) => {
      if (i === iterVars.length) {
        let r;
        try {
          r = evalNode(einsum.expression, bind, ctx, specs);
        } catch (err) {
          r = { present: false, value: null, prov: { error: String(err) } };
        }
        points.push({
          bind: Object.assign({}, bind),
          coord: outRanks.map((n) => bind[n]).join(","),
          present: r.present,
          value: r.value,
          prov: r.prov,
          reduceHere: r.reduceHere || null,
          populateHere: r.populateHere || null,
        });
        return;
      }
      for (let c = 0; c < N; c++) {
        bind[iterVars[i]] = c;
        walk(i + 1, bind);
      }
    };
    walk(0, {});

    // Reduction, if any: fold the points sharing an output coordinate.
    const reduceSpec = einsum.specs.find((s) => s.kind === "reduce");
    const populateSpec = einsum.specs.find((s) => s.kind === "populate");

    const result = {};
    // `assigned` records what the einsum WROTE, including cells it wrote the
    // empty value to (as null). `result` records only what is present.
    // They differ where a computed value equals the output's empty value:
    // that cell is absent, but it was still written -- so when one einsum
    // overwrites another (E04's lowered case arms) it must CLEAR the earlier
    // value rather than leave it standing.
    const assigned = {};
    const groups = {};
    let note = null;

    if (populateSpec) {
      const choiceName =
        populateSpec.compute_op.name || populateSpec.compute_op.symbol;
      // The populated ranks are the `*`-marked ones; the rest of the output
      // coordinate identifies the group a choice is made within. For
      // `PushCand_{i,u,v*}` that is: choose one v per u.
      const popRanks = populateSpec.rank_list || [];
      const groupRanks = outRanks.filter((r) => !popRanks.includes(r));
      const candidates = points
        .filter((p) => p.present)
        .map((p) => ({
          coord: p.coord,
          value: p.value,
          bind: p.bind,
          groupCoord: groupRanks.map((n) => p.bind[n]).join(","),
          populatedCoord: popRanks.map((n) => p.bind[n]),
        }));

      if (opts.selector) {
        // Driving: the choice is made now, by a named rule.
        Object.assign(result, opts.selector({
          name: choiceName,
          label: opts.label,
          generation: opts.generation,
          candidates, popRanks, groupRanks, outRanks,
          state, N: ctx.N,
        }));
        Object.keys(result).forEach((c) => (assigned[c] = result[c]));
        note =
          "selector: the IR names the choice function (" + choiceName +
          ") but carries no body, so the rule that decided it comes from the " +
          "run's selector mapping, not from the spec.";
      } else {
        // Showing: the choice was already made, by whoever produced the trace.
        note =
          "selector: the IR names the choice function (" + choiceName +
          ") but carries no body, so the chosen coordinate is read from the " +
          "trace rather than recomputed. Any admissible coordinate is valid.";
        if (opts.recordedOutput) Object.assign(result, opts.recordedOutput);
      }
    } else if (reduceSpec) {
      const fnName = reduceSpec.compute_op.symbol || reduceSpec.compute_op.name;
      const fn = COMPUTE[fnName];
      points.forEach((p) => {
        if (!p.present) return;
        (groups[p.coord] = groups[p.coord] || []).push(p);
      });
      Object.keys(groups).forEach((coord) => {
        const vals = groups[coord].map((p) => p.value);
        // Fold over the PRESENT values only. The identity operand in the IR
        // exists to give the ReduceSpec a label to attach to; folding from
        // the first present value avoids depending on it.
        const folded = vals.reduce((a, b) => fn(a, b));
        if (isEmpty(folded, outEmpty)) assigned[coord] = null;
        else assigned[coord] = result[coord] = folded;
      });
    } else {
      points.forEach((p) => {
        if (!p.present) return;
        if (isEmpty(p.value, outEmpty)) {
          assigned[p.coord] = null;
          return;
        }
        assigned[p.coord] = result[p.coord] = p.value;
      });
    }

    return {
      einsum,
      output: einsum.output_tensor,
      outputRanks: outRanks,
      outputGeneration: rankName(einsum.output_ranks[0]),
      iterVars,
      points,
      groups,
      result,
      assigned,
      reduceSpec: reduceSpec || null,
      populateSpec: populateSpec || null,
      outEmpty,
      note,
    };
  }

  return {
    evalEinsum,
    evalEinsumNode,
    merges,
    glyph,
    MERGE_TT,
    MERGE_GLYPH,
    COMPUTE,
    isEmpty,
    num,
  };
})();

if (typeof module !== "undefined" && module.exports) module.exports = EdgeInterp;
if (typeof globalThis !== "undefined") globalThis.EdgeInterp = EdgeInterp;
