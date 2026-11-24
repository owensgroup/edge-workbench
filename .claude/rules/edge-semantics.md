# EDGE semantics and tutorial parsing

## Stack

- EDGE extended Einsums: Map `⋀`, Reduce `⋁`, Populate `⋘ 𝟙(op)`, merges `∩ ∪ ← →`, labels `·¹ ·²`
- edge-core-ir: IR classes, validators and the Python evaluator (the semantics)
- `einsum.edge`: the ASCII form of the tutorial's `edge_expression`

## Patterns

- A Reduce attaches to a binary expression in the IR, so a bare reduce is
  lowered as a transparent `take_left` Map against a literal.
- `I` is the generational rank and stays hard-coded. An inner cascade's rank
  (bubble sort's step rank `J`) is an ordinary rank of the tensor: the page
  shows one generation of `I` at a time, with the inner rank as an axis.
- A case statement is one IR Einsum whose expression is `Cases`; each arm
  has its own expression, specs and condition, and the first arm whose
  condition holds claims a point (issue 8). A conditional cascade runs one
  arm's Einsums per generation (issue 9). IR nodes are numbered depth first
  through arms and inner cascades (`cascade_shape.flat_nodes`).
- A macro is a lexical substitution (paper B.8). `einsum.edge` writes it as
  a `- Macro NAME(inputs) -> outputs` section in formal names; the IR holds
  each call's expansion (`edge_workbench.macro.expand`; expansion is the
  front end's job, edge-core-ir's D3). A labelled multi-output
  case statement over macro calls is one conditional cascade, has no IR node
  and no entry in `labels` (it is in cascade.json's `conditionals`), and the
  driver emits a step for it saying which macro the generation ran. The
  label map follows a call's bindings (`spec_surface.expansion_order`).
- Captions: the author's `**Graph meaning:**` / `**Einsum meaning:**` lines
  under each formula in `edge_expression_walkthrough` win; then the model's
  text; then a sentence generated from the IR (`render/action_prose.py`).
  No word limit.
- A Populate with a mutable rank runs in rounds (paper §6.6, Inset 4; the
  only sense in which "round" is used): one per Reduce Temporary element, in
  the order the schedule hands them out, each on the one fiber the element
  belongs to. The evaluator checks `W ∩ (dom(S) ∪ D) = ∅` against the
  pre-state before applying the deletes and then the writes, and raises on a
  violation. The driver records every round by watching the coordinate
  operator it hands the evaluator (`driver/run.py`, `_watching_populate`;
  edge-core-ir is not changed for it), passes it through as `step["populate"]`, and the page
  only looks rounds up (`display.js`: `fiberStateAt`, `candidateFate`).
- `select-any` (the workbench's, `edge_workbench/operators.py`) writes the first arrival into an empty fiber and returns None
  for every later one: the schedule decides, never the operator.
  `select-{min,max}-val` deletes the held coordinate and writes the incoming
  one when it ranks better, ties by coordinate (issue 4), so its result does
  not depend on the schedule.
- The page's own run uses the sequential schedule (sorted coordinates); the
  answer check runs free choices under shuffled schedules as well.

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
- A generational rank declared with a shape (`I = N-1`) bounds its cascade:
  generation `i` runs only for `i` in `[0, I)` (issue 10).
- Coverage: everything outside an arm must run on the worked example; an arm
  of a case statement or of a conditional cascade must be exercised by the
  worked example or by one of the verifier's random instances.
- A function-call arm (`min(x, y)`) states no merge; builders use intersect.
- An operation written with its own glyph and no action (`(MU_i / alpha)`)
  states no merge; builders use the paper's default, `pass_through` (§7.3.4).
- A `- Constants` value (`alpha = 15`) is a zero-rank declaration carrying
  the value, never an input: an input must come from every instance, the
  approved verifier's random ones included. The tutorial must state it.
- A tutorial may define a macro twice under one name (DO-BFS: hybrid and
  compact hybrid); the reader takes the blocks after the selected cascade.
- `j-1` in a subscript is rank arithmetic, not a hyphenated operator name.
- Coordinates start at 0; a tutorial numbering vertices from 1 shows an
  unused vertex 0 on the page.
