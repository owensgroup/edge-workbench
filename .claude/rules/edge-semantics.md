# EDGE semantics and tutorial parsing

## Stack

- EDGE extended Einsums: Map `⋀`, Reduce `⋁`, Populate `⋘ 𝟙(op)`, merges `∩ ∪ ← →`, labels `·¹ ·²`
- edge-core-ir: IR classes, validators and the Python evaluator (the semantics)
- `einsum.edge`: the ASCII form of the tutorial's `edge_expression`

## Patterns

- A Reduce attaches to a binary expression in the IR, so a bare reduce is
  lowered as a transparent `take_left` Map against a literal.
- `I` is the generational rank and stays hard-coded.
- Captions: the author's `**Graph meaning:**` / `**Einsum meaning:**` lines
  under each formula in `edge_expression_walkthrough` win; then the model's
  text; then a sentence generated from the IR (`render/action_prose.py`).
  No word limit.

## Decisions

- Ranking operators (`select-min-val`, `select-max-val`, ...) are part of the
  algorithm. Any other populate name is a free choice and runs as seeded
  `select-any`; an unknown name stops the run.
- The picture (graph, bipartite, sequence) is decided by the tutorial's
  `ranks:` block (`rank_kinds.py`, closed vocabulary, checked against
  einsum.edge) when present, otherwise inferred from the tensors' ranks in
  `domain_shape.py`; never by the model.
- The verifier should use a different algorithm from the cascade, and compare
  something every valid run shares (BFS depths, not parents).

## Gotchas

- **A stored value equal to a tensor's empty value is absent.** With
  `empty = 0`, a weight-0 edge is no edge. Pick empty values deliberately
  (Bellman-Ford `G` is `empty = inf` for this reason).
- **A unary (`¬`) applies to its input tensor before any reduce.**
  `NV = ¬Tree :: ⋁_p OR(∪)` makes every vertex Not Visited; write the reduce
  and the negation as two Einsums (`Visited`, then `NV`).
- The IR's unary takes only a named tensor, not a parenthesized expression
  (issue 3).
- Init lines that assign the declared empty value (`F_{i,s} = False`) write
  nothing; the overlap check skips them.
- The tutorial parser must accept `\mathit{...}`, Einsums whose `::` part is on
  the next line, and `<user-specified>` init lines. If an Einsum is missing
  from the parsed cascade, suspect formatting first.
- A cascade gets 500 generations to reach its stopping condition.
- Coordinates start at 0; a tutorial numbering vertices from 1 shows an
  unused vertex 0 on the page.
