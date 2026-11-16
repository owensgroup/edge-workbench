// Display helpers for the walkthrough page: operator glyphs, the merge truth
// tables shown in the legend, and number formatting. Nothing here evaluates
// an Einsum -- every value on the page comes from edge-core-ir's evaluator,
// recorded at build time (edge_workbench/driver/run.py).

const EdgeDisplay = (function () {
  "use strict";

  // The 16 merge operators' presence truth tables, for display. The source of
  // truth is edge_ir/runtime/op_properties.py. Order: (F,F) (F,T) (T,F) (T,T).
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

  const UNARY_GLYPH = { not: "¬", floor: "⌊ ⌋" };

  const COMPUTE_GLYPH = {
    "*": "×", eq: "≡", ne: "≠", gt: ">", ge: "≥", lt: "<", le: "≤",
    take_left: "←", take_right: "→", update: "<<",
    min: "min", max: "max", AND: "AND", OR: "OR", ANY: "ANY", any_of: "ANY",
  };

  function glyph(name, kind) {
    const t = kind === "merge" ? MERGE_GLYPH : COMPUTE_GLYPH;
    return t[name] || name;
  }
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
  const TEX_SYMBOLS = {
    bigwedge: "⋀", bigvee: "⋁", lll: "⋘", cap: "∩", cup: "∪", cdot: "·",
    leftarrow: "←", rightarrow: "→", neg: "¬", wedge: "∧", vee: "∨",
    equiv: "≡", ne: "≠", neq: "≠", ge: "≥", geq: "≥", le: "≤", leq: "≤",
    in: "∈", infty: "∞", diamond: "⋄", ast: "*", times: "×",
    lfloor: "⌊", rfloor: "⌋", lvert: "|", rvert: "|", vert: "|",
    lVert: "‖", rVert: "‖", lbrace: "{", rbrace: "}",
    sigma: "σ", delta: "δ", alpha: "α", beta: "β", gamma: "γ", lambda: "λ",
    mu: "μ", tau: "τ", pi: "π",
  };

  /* LaTeX as plain HTML, for when MathJax is not there. Never leaves a
     backslash behind: an unknown command reads as its own name. */
  function plainFormula(tex) {
    const UNDERSCORE = "\u0001";
    let s = String(tex)
      .replace(/\s*\n\s*/g, " ")
      .replace(/\\_/g, UNDERSCORE)
      .replace(/\\(lvert|lVert)\s+/g, "\\$1{}")
      .replace(/\\begin\{(?:cases|array|aligned)\}(?:\{[^}]*\})?/g, " ")
      .replace(/\\end\{(?:cases|array|aligned)\}/g, " ")
      .replace(/\\\\(\[[^\]]*\])?/g, "\n")
      .replace(/\\(?:left|right|textstyle|nolimits|displaystyle)\b/g, "")
      .replace(/\\[,;:! ]/g, " ")
      .replace(/\\quad\b/g, "  ");
    // \mathrm{x} and friends, innermost first: they nest.
    const wrapped = /\\(?:text|texttt|textbf|mathrm|mathit|mathbf|mathbin|operatorname)\{([^{}]*)\}/g;
    while (wrapped.test(s)) s = s.replace(wrapped, "$1");
    s = s.replace(/\\([A-Za-z]+)/g, (_, w) => TEX_SYMBOLS[w] ?? w)
      .replace(/\^\s*\*/g, "*")
      .replace(/&(?!lt;|gt;|amp;)/g, " ")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/_\{([^{}]*)\}/g, "<sub>$1</sub>")
      .replace(/_([A-Za-z0-9*])/g, "<sub>$1</sub>")
      .replace(/\^\{([^{}]*)\}/g, "<sup>$1</sup>")
      .replace(/\^([A-Za-z0-9])/g, "<sup>$1</sup>")
      .replace(/[{}]/g, "")
      .replace(/\n/g, "<br>")
      .replace(/[ \t]+/g, " ");
    return s.split(UNDERSCORE).join("_").replace(/(\s|<br>)+$/, "").trim();
  }

  function esc(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /* A caption as HTML: its prose escaped, its `$...$` or `\\(...\\)` handed to
     `math`, which draws them with MathJax or plainFormula. */
  function meaningHTML(text, math) {
    return String(text)
      .split(/(\$\$[^$]+\$\$|\$[^$]+\$|\\\([\s\S]+?\\\))/)
      .map((part, i) => i % 2 === 0 ? esc(part)
        : math(part.replace(/^(\$\$?|\\\()|(\$\$?|\\\))$/g, "")))
      .join("");
  }

  return { MERGE_TT, MERGE_GLYPH, UNARY_GLYPH, COMPUTE_GLYPH, glyph, num, isEmpty,
           plainFormula, esc, meaningHTML };
})();

if (typeof module !== "undefined") module.exports = EdgeDisplay;
