"use strict";
/**
 * The one part of the viewer that knows what the numbers MEAN.
 *
 * Everything else -- tensor grids, transport, drill-down -- works off the
 * trace alone. A trace names its renderer in `domainView`, and adding a
 * picture is adding an entry here.
 *
 * This used to live inside the page template, which meant it could only be
 * exercised by building a whole page for a whole algorithm. So the graph view
 * was tested and the others could not be written safely at all. It is a module
 * now, and the page inlines it the way it already inlines the interpreter.
 *
 * THREE VIEWS, TWO RENDERERS
 * --------------------------
 * A rank-2 tensor is a graph on its two rank sets -- that is what an adjacency
 * matrix is. When both ranks index the SAME set you get the directed graph
 * max-flow draws; when they index DIFFERENT sets you get a bipartite graph,
 * which is what exact cover is: rows are sets, columns are elements, and a
 * cover picks rows so every column has degree one. Same renderer, different
 * layout and node naming.
 *
 * `sequence` is the genuinely different one: an algorithm with no rank-2
 * tensor has no edges to draw, so there is no graph reading at all. Bubble
 * sort is a row of cells.
 *
 * SIDE-QUALIFIED NODE IDS
 * -----------------------
 * In a bipartite picture row 0 and column 0 are DIFFERENT nodes that share an
 * index, so ids are `R:0` and `C:0`. A flat id list cannot express that, and a
 * renderer keying `POS[0]` would put a column's marking on a row. Tensors are
 * still keyed by the bare index, so a lookup has to strip the side -- and
 * check that the tensor belongs to that side before using it at all.
 */

/** `R:0` -> `R`, and a plain `3` -> null. */
function sideOf(id) {
  const s = String(id);
  const i = s.indexOf(":");
  return i < 0 ? null : s.slice(0, i);
}

/** `R:0` -> `0`, and a plain `3` -> `3`. */
function indexOf(id) {
  const s = String(id);
  const i = s.indexOf(":");
  return i < 0 ? s : s.slice(i + 1);
}

/**
 * Read a rank-1 tensor at a node, honouring which side the tensor lives on.
 *
 * `tensorSide` maps tensor name -> rank name, derived from the declarations.
 * When a picture has sides and a tensor belongs to the other one, the answer
 * is "absent" rather than a value read from the wrong index space -- which is
 * the bug that makes a flat id list unusable.
 */
function readAt(state, tensor, nodeId, tensorSide) {
  const side = sideOf(nodeId);
  if (side && tensorSide && tensorSide[tensor] && tensorSide[tensor] !== side) {
    return undefined;
  }
  const t = state[tensor];
  return t ? t[indexOf(nodeId)] : undefined;
}

function makeViews(ctx) {
  const { el } = ctx;
  const VIEWS = {};

  /** A label, with a highlight pill behind it when its text just changed. */
  const labeller = (g) => (x, y, txt, was, col) => {
    const chg = was !== null && was !== undefined && was !== txt;
    if (chg) {
      g.appendChild(el("rect", {
        x: x - (txt.length * 2.9 + 4), y: y - 9,
        width: txt.length * 5.8 + 8, height: 12, rx: 3,
        fill: "#ffe8cc", stroke: "#e8590c", "stroke-width": 0.8,
      }));
    }
    const t = el("text", {
      x, y, "text-anchor": "middle", "font-size": 10,
      fill: chg ? "#e8590c" : col, "font-weight": chg ? 700 : 400,
    });
    t.textContent = txt;
    g.appendChild(t);
  };

  const arrowheads = (g) => {
    const defs = el("defs");
    for (const [id, c] of [["a", "#999"], ["ah", "#e8590c"]]) {
      const m = el("marker", {
        id, viewBox: "0 0 10 10", refX: 9, refY: 5,
        markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse",
      });
      m.appendChild(el("path", { d: "M0,0 L10,5 L0,10 z", fill: c }));
      defs.appendChild(m);
    }
    g.appendChild(defs);
  };

  /**
   * Nodes at positions, edges between them, fills and labels from tensors.
   *
   * Serves `graph` and `bipartite` both: the only differences are where the
   * positions put things and whether ids carry a side, and neither is the
   * renderer's business.
   */
  function drawNodeLink(g, st, hl, pv, opts) {
    const { DOM, POS, EDGES, tensorSide } = ctx;
    const radius = (opts && opts.radius) || 22;
    // A graph's edges point somewhere; a bipartite incidence does not. "Row 2
    // covers column 0" is a membership, and an arrowhead on it asserts a
    // direction the relation has not got -- it reads as though the row were
    // sending something to the column. The two views share this function
    // because the drawing is the same; the arrowheads are the one thing that
    // is not.
    const directed = !(opts && opts.directed === false);
    g.innerHTML = "";
    arrowheads(g);
    const lab = labeller(g);

    const hle = new Set((hl.edges || []).map((e) => e.join(",")));
    const hln = new Set(hl.nodes || []);

    // A push can travel along a RESIDUAL edge that has no line of its own --
    // (4,2) when only (2,4) is drawn. That push changes the number on (2,4),
    // so that is the pipe to light. Only when the reverse is not itself
    // drawn: an antiparallel pair must stay distinguishable.
    const drawn = new Set(EDGES.map((e) => e.u + "," + e.v));
    const isLit = (e) =>
      hle.has(e.u + "," + e.v) ||
      (hle.has(e.v + "," + e.u) && !drawn.has(e.v + "," + e.u));

    EDGES.forEach((e) => {
      const a = POS[e.u], b = POS[e.v];
      if (!a || !b) return;                     // an edge to a node we cannot place
      const [x1, y1] = a, [x2, y2] = b;
      const anti = EDGES.some((o) => o.u === e.v && o.v === e.u);
      const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1;
      const ux = dx / L, uy = dy / L, px = -uy, py = ux;
      const off = anti ? 11 : 0;
      const sx = x1 + ux * radius + px * off, sy = y1 + uy * radius + py * off;
      const tx = x2 - ux * radius + px * off, ty = y2 - uy * radius + py * off;
      const on = isLit(e);
      g.appendChild(el("line", {
        x1: sx, y1: sy, x2: tx, y2: ty,
        stroke: on ? "#e8590c" : "#999", "stroke-width": on ? 3 : 1.4,
        ...(directed ? { "marker-end": `url(#${on ? "ah" : "a"})` } : {}),
      }));
      const EL = DOM.edgeLabel;
      if (EL) {
        // Edge tensors are keyed by the BARE indices, so a bipartite edge
        // `R:1 -> C:2` reads the cell `1,2`.
        const key = indexOf(e.u) + "," + indexOf(e.v);
        const fv = (q) => {
          let f = q ? ((q[EL.tensor] || {})[key] ?? EL.empty ?? 0)
                    : (EL.empty ?? 0);
          if (EL.clampNegative && f < 0) f = 0;
          return EL.over ? `${f}/${e[EL.over]}` : String(f);
        };
        lab((sx + tx) / 2 + px * 13, (sy + ty) / 2 + py * 13 + 4,
            fv(st), pv ? fv(pv) : null, on ? "#e8590c" : "#555");
      }
    });

    (DOM.graph.nodes || []).forEach((v) => {
      const [x, y] = POS[v] || [0, 0];
      const on = hln.has(v);
      // First matching rule wins, so the instance orders them by priority --
      // source and sink before "currently active", which is what a reader
      // expects when a vertex is both.
      let fill = "#fff";
      for (const r of (DOM.nodeFill || [])) {
        const val = readAt(st, r.tensor, v, tensorSide);
        if (val !== undefined && val !== false) { fill = r.color; break; }
      }
      g.appendChild(el("circle", {
        cx: x, cy: y, r: radius, fill,
        stroke: on ? "#e8590c" : "#555", "stroke-width": on ? 3 : 1.5,
      }));
      const a = el("text", {
        x, y: y + 4, "text-anchor": "middle", "font-size": 14,
        "font-weight": 600,
      });
      a.textContent = indexOf(v);
      g.appendChild(a);

      (DOM.nodeLabels || []).forEach((L) => {
        const txt = (q) => {
          if (!q) return (L.prefix || "") + (L.empty ?? "");
          const val = readAt(q, L.tensor, v, tensorSide);
          return (L.prefix || "") + (val ?? L.empty ?? "");
        };
        const dy = L.place === "below" ? radius + 14 : -(radius + 7);
        lab(x, y + dy, txt(st), pv ? txt(pv) : null, L.color || "#555");
      });
    });
  }

  VIEWS.graph = (g, st, hl, pv) => drawNodeLink(g, st, hl, pv, {});

  /**
   * Two node sets in two columns, with a side label over each.
   *
   * Same renderer as `graph`; what differs is that ids carry a side and the
   * positions put the two ranks in two columns. Exact cover reads left to
   * right: rows choose, columns get covered.
   */
  VIEWS.bipartite = (g, st, hl, pv) => {
    drawNodeLink(g, st, hl, pv, { radius: 18, directed: false });
    const sides = (ctx.DOM.graph || {}).sides;
    if (!sides) return;
    const { POS } = ctx;
    [["left", sides.left], ["right", sides.right]].forEach(([, rank]) => {
      const xs = Object.keys(POS).filter((k) => sideOf(k) === rank)
        .map((k) => POS[k][0]);
      if (!xs.length) return;
      const t = el("text", {
        x: xs[0], y: 18, "text-anchor": "middle", "font-size": 11,
        fill: "#888", "font-weight": 600,
      });
      t.textContent = rank;
      g.appendChild(t);
    });
  };

  /**
   * A row of cells: one rank of positions, no edges.
   *
   * An algorithm with no rank-2 tensor has nothing to connect, so a graph
   * reading would be N isolated circles. Bubble sort compares neighbours, and
   * a strip shows that; `DOM.cellValue` names the tensor whose value fills a
   * cell, and nodeFill/nodeLabels decorate as they do elsewhere.
   */
  VIEWS.sequence = (g, st, hl, pv) => {
    const { DOM, POS, tensorSide } = ctx;
    g.innerHTML = "";
    const lab = labeller(g);
    const hln = new Set(hl.nodes || []);
    const ids = DOM.graph.nodes || [];
    const w = 44, gap = 6, y = 90;

    ids.forEach((v, k) => {
      const x = (POS[v] || [45 + k * (w + gap)])[0];
      let fill = "#fff";
      for (const r of (DOM.nodeFill || [])) {
        const val = readAt(st, r.tensor, v, tensorSide);
        if (val !== undefined && val !== false) { fill = r.color; break; }
      }
      const on = hln.has(v);
      g.appendChild(el("rect", {
        x: x - w / 2, y: y - 22, width: w, height: 44, rx: 4, fill,
        stroke: on ? "#e8590c" : "#555", "stroke-width": on ? 3 : 1.4,
      }));
      const cv = DOM.cellValue;
      const shown = cv ? readAt(st, cv.tensor, v, tensorSide) : undefined;
      const t = el("text", {
        x, y: y + 5, "text-anchor": "middle", "font-size": 15,
        "font-weight": 600,
      });
      t.textContent = shown === undefined ? "·" : String(shown);
      g.appendChild(t);

      const pos = el("text", {
        x, y: y + 36, "text-anchor": "middle", "font-size": 10, fill: "#aaa",
      });
      pos.textContent = indexOf(v);
      g.appendChild(pos);

      (DOM.nodeLabels || []).forEach((L) => {
        const txt = (q) => {
          if (!q) return (L.prefix || "") + (L.empty ?? "");
          const val = readAt(q, L.tensor, v, tensorSide);
          return (L.prefix || "") + (val ?? L.empty ?? "");
        };
        lab(x, y - 30, txt(st), pv ? txt(pv) : null, L.color || "#555");
      });
    });
  };

  return VIEWS;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { makeViews, sideOf, indexOf, readAt };
}
if (typeof globalThis !== "undefined") {
  globalThis.EdgeDomainViews = { makeViews, sideOf, indexOf, readAt };
}
