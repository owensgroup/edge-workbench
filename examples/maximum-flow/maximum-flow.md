---
title: Maximum Flow (Push-Relabel)
authors: [Sanjana Mali, Toluwanimi Odemuyiwa]
summary: Maximum s-t flow by the bulk-synchronous push-relabel method, which seeds a saturating preflow from the source and then repeatedly pushes excess down admissible residual edges and relabels stuck vertices, expressed as one long extended Einsum iterated until no internal vertex holds excess.
tags: [max-flow, push-relabel, residual-graph, graphs]
viz: /assets/viz/maximum-flow/
viz_label: Open the interactive walkthrough
viz_note: step one Einsum at a time and watch it execute — every point of its iteration space, and how each value is computed — or race the cascade against the textbook pseudocode
viz_alt: /assets/viz/maximum-flow-sequential/
viz_alt_label: Walk the sequential cascade (derived)
viz_alt_note: the parallel cascade with one Einsum added — a correct sequentialisation, but one that still evaluates both arms each round
viz_alt2: /assets/viz/maximum-flow-branching/
viz_alt2_label: Walk the sequential cascade (from the pseudocode)
viz_alt2_note: written from the while loop instead — one vertex, one test, one operation per round, reproducing the textbook's 29 operations in order
viz_alt3: /assets/viz/maximum-flow-cascade-diff/
viz_alt3_label: Parallel and sequential side by side
viz_alt3_note: every Einsum in two columns — a selector added, four changed, two dropped — with the differences computed by diffing the specs rather than typed
status_intro: |
  This page gives the bulk-synchronous, full-edge form of the push-relabel
  maximum-flow algorithm. It first saturates every edge out of the source to build
  an antisymmetric preflow, then runs a single extended Einsum once per generation
  $$i$$: each active internal vertex (one holding excess) pushes flow down one
  admissible residual edge, and any active vertex left with excess and no admissible
  edge is relabeled to a higher distance. Distances only ever rise, excess only ever
  moves "downhill," and the cascade halts when no internal vertex holds excess — at
  which point the flow is maximum.

problem_statement: |
  Given a directed graph $$G$$ on $$\lvert V\rvert$$ vertices with a non-negative capacity
  $$C$$ on each edge, a source $$s$$, and a sink $$t$$, compute a flow $$F$$ of maximum value
  from $$s$$ to $$t$$.

  The state is carried by a flow tensor, a residual tensor, a per-vertex excess, and a
  per-vertex distance (label), alongside the source and sink masks and per-round scratch
  tensors:

  - $$G^{U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer}$$, `empty` $$= 0$$, the graph structure.
  - $$C^{U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer}$$, `empty` $$= 0$$, the edge capacities.
  - $$F^{I,\, U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer}$$, `empty` $$= 0$$, the flow on each
    edge at generation $$i$$ (the answer). $$F$$ is antisymmetric: $$F_{v,u} = -F_{u,v}$$, so a
    negative entry means the flow runs the other way.
  - $$R^{I,\, U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer}$$, `empty` $$= 0$$, the residual
    capacity at generation $$i$$. A saturated edge reaches $$0$$, which equals the empty
    value, so it simply leaves the tensor.
  - $$E^{I,\, U \equiv \lvert V\rvert} \to \text{integer}$$, `empty` $$= 0$$, the excess at each vertex.
  - $$D^{I,\, U \equiv \lvert V\rvert} \to \text{integer}$$, `empty` $$= +\infty$$, the distance (label)
    of each vertex. The empty value is not $$0$$ because $$0$$ is a legal distance.
  - $$Act^{I,\, U \equiv \lvert V\rvert} \to \text{Boolean}$$, `empty` $$=$$ False, the active
    internal vertices (those holding excess).
  - $$S^{U \equiv \lvert V\rvert} \to \text{Boolean}$$, `empty` $$=$$ False, the one-hot source mask.
  - $$T^{U \equiv \lvert V\rvert} \to \text{Boolean}$$, `empty` $$=$$ False, the one-hot sink mask.
working_example_part1: |
  Take a four-vertex network with source $$s = 0$$, sink $$t = 3$$, two internal
  vertices $$1$$ and $$2$$, and capacities

  $$0\to1\,(3),\ 0\to2\,(2),\ 1\to2\,(1),\ 1\to3\,(2),\ 2\to3\,(3).$$

  The two source edges carry total capacity $$3 + 2 = 5$$ and the two sink edges
  carry total capacity $$2 + 3 = 5$$, so the maximum flow is $$5$$.

  Initialization sets every distance to $$0$$ except the source, which is lifted to
  $$\lvert V\rvert = 4$$ so it can never receive excess back, and zeros the flow and excess:

  $$D_{i \equiv 1} = \lbrace 0:4,\ 1:0,\ 2:0,\ 3:0\rbrace,\qquad E_{i \equiv 0} = \lbrace \rbrace,\qquad F_{i \equiv 0} = \lbrace \rbrace.$$

  The preflow step (generation $$i = 1$$) then saturates both source edges:
  $$F_{1,0,1} = 3,\ F_{1,0,2} = 2$$, which floods the two internal vertices with
  excess (and, since $$F$$ is antisymmetric, records $$F_{1,1,0} = -3$$ and $$F_{1,2,0} = -2$$ on the
  reverse cells) and opens the reverse residual edges back toward the source:

  $$E_1 = \lbrace 1:3,\ 2:2\rbrace,\qquad Act_1 = \lbrace 1,\ 2\rbrace.$$
working_example_part2: |
  Each generation lets every active vertex push along one admissible residual edge
  ($$R$$ present and distance $$D(u) = D(v) + 1$$), then relabels any active vertex left with no
  admissible edge. The trace below shows distances $$D$$, excess $$E$$, and the actions
  taken; the residual graph $$R$$ updates in lockstep:

  | $$i$$ | active | push $$(u\to v: \text{amt})$$ | relabel $$(u: D')$$ | $$D_{i+1}$$ | $$E_{i+1}$$ |
  |----|----|----|----|----|----|
  | 1 | $$\lbrace 1,2\rbrace$$ | none (no admissible edge) | $$1\!:\!1,\ 2\!:\!1$$ | $$\lbrace 0:4,\ 1:1,\ 2:1\rbrace$$ | $$\lbrace 1:3,\ 2:2\rbrace$$ |
  | 2 | $$\lbrace 1,2\rbrace$$ | $$1\!\to\!3\!:\!2,\ \ 2\!\to\!3\!:\!2$$ | $$1\!:\!2$$ | $$\lbrace 0:4,\ 1:2,\ 2:1\rbrace$$ | $$\lbrace 1:1\rbrace$$ |
  | 3 | $$\lbrace 1\rbrace$$ | $$1\!\to\!2\!:\!1$$ | none | $$\lbrace 0:4,\ 1:2,\ 2:1\rbrace$$ | $$\lbrace 2:1\rbrace$$ |
  | 4 | $$\lbrace 2\rbrace$$ | $$2\!\to\!3\!:\!1$$ | none | unchanged | $$\lbrace \rbrace$$ — stop |

  In generation $$1$$ both internal vertices sit at distance $$0$$ alongside all of their
  neighbours, so no edge is admissible and both are relabeled to distance $$1$$. In
  generation $$2$$ each can now push its excess one step down to the sink: vertex $$1$$
  sends $$2$$ units on $$1\to3$$ and vertex $$2$$ sends $$2$$ units on $$2\to3$$, leaving vertex
  $$1$$ with $$1$$ leftover unit and no admissible edge, so it relabels to distance $$2$$. That
  lets vertex $$1$$ push its last unit across $$1\to2$$ in generation $$3$$, which gives
  vertex $$2$$ one unit of excess; vertex $$2$$ pushes it to the sink in generation $$4$$.
  No internal vertex now holds excess, so $$\lVert Act_5\rVert \equiv 0$$ fires and the
  cascade halts. Summing the flow leaving the source gives the maximum flow value
  $$F_{0,1} + F_{0,2} = 3 + 2 = 5$$.
edge_expression_walkthrough: |
  **Preflow.** $$FS_{i \equiv 1,u,v} = S_u \cdot C_{u,v} :: \bigwedge *(\cap)$$ saturates every
  edge out of the source: intersecting on $$u$$ with the one-hot $$S$$ keeps only the
  $$u = s$$ row of $$C$$. That row is then mirrored into an antisymmetric flow,
  $$F_{i \equiv 1,u,v} = FS_{i \equiv 1,u,v} \cdot FS_{i \equiv 1,v,u} :: \bigwedge -(\cup)$$ —
  reading $$FS$$ at a point and at its transpose, so $$f(s,v) = c(s,v)$$ and
  $$f(v,s) = -c(s,v)$$. Because outflow is already stored as negative entries, excess is
  just net inflow: $$E_{i \equiv 1,v} = F_{i \equiv 1,u,v} :: \bigvee +(\cup)$$, a reduction
  over rank $$u$$. The initial residual $$R_1$$ is the capacity graph with the source row
  zeroed (its edges are now saturated) and the corresponding reverse edges back toward
  the source opened. The three cases are disjoint — the $$v = s$$ arm carries an explicit
  $$u \neq s$$ guard — so the result does not depend on evaluation order at a source
  self-loop.

  **Active vertices.** $$NST_u = \neg S_u \cdot \neg T_u :: \bigwedge \text{AND}(\cap)$$
  marks the internal vertices (neither source nor sink). A vertex is active when it is
  internal and holds positive excess:
  $$Act_{1,u} = NST_u \cdot^1 (E_{1,u} \cdot^2 0)_{1,u} :: \bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 >(\cap)$$,
  where the inner sub-merge tests $$E_{1,u} > 0$$ and the outer take-left keeps $$NST$$'s
  Boolean at the surviving coordinates. This is pinned to generation 1 because it only
  needs to **seed** the loop: the relabel step below recomputes $$Act_{i+1}$$ from the
  excess each push produces, so every round after the first reads that instead.

  **Admissibility.** $$ActR_{i,u,v} = Act_{i,u} \cdot R_{i,u,v} :: \bigwedge \leftarrow(\cap)$$
  keeps the residual edges leaving an active vertex. No explicit $$>0$$ test is needed:
  a saturated edge has already dropped out of $$R$$, so the intersection skips it. The
  distance rule
  $$Lbl_{i,u,v} = D_{i,u} \cdot (D_{i,v} + 1)_{i,v} :: \bigwedge \equiv(\cap)$$
  is True exactly where $$D(u) = D(v) + 1$$ — flow may only move strictly downhill by one
  level. Their AND
  $$Adm_{i,u,v} = ActR_{i,u,v} \cdot Lbl_{i,u,v} :: \bigwedge \text{AND}(\cap)$$
  is the set of admissible residual edges out of active vertices.

  **Push.** The populate
  $$PushCand_{i,u,v^*} = Adm_{i,u,v} \lll_{v^*} \mathbf{1}(\text{pick-admissible-edge})$$
  selects one admissible neighbour $$v$$ for each pushing vertex $$u$$; any admissible
  neighbour is a valid choice. One edge per vertex is required, not merely convenient:
  every admissible edge of $$u$$ would otherwise compute its own $$\min$$ against the *same*
  $$E_{i,u}$$, and $$u$$ would send out more than it holds. The amount pushed is the smaller
  of the vertex's excess and the edge's residual, restricted to the chosen edge:
  $$\delta_{i,u,v} = (E_{i,u} \cdot^1 R_{i,u,v})_{i,u,v} \cdot^2 PushCand_{i,u,v} :: \bigwedge^1 \min(\cap)\ \bigwedge^2 \leftarrow(\cap)$$.
  Flow is then adjusted on the chosen edges and their reverses
  $$F_{i+1,u,v} = (F_{i,u,v} \cdot^1 \delta_{i,u,v})_{i,u,v} \cdot^2 \delta_{i,v,u} :: \bigwedge^1 +(\cup)\ \bigwedge^2 -(\cup)$$.
  The distance rule makes $$u \to v$$ and $$v \to u$$ mutually exclusive in one round, so at
  most one of $$\delta_{i,u,v}$$ and $$\delta_{i,v,u}$$ is ever present: the $$+$$ and the $$-$$ land on
  a cell and its mirror in a single write. Excess is updated by what each vertex
  received versus sent
  ($$InPush_{i,v} = \delta_{i,u,v} :: \bigvee +(\cup)$$,
  $$OutPush_{i,u} = \delta_{i,u,v} :: \bigvee +(\cup)$$,
  then
  $$E_{i+1,u} = (E_{i,u} \cdot^1 InPush_{i,u})_{i,u} \cdot^2 OutPush_{i,u} :: \bigwedge^1 +(\cup)\ \bigwedge^2 -(\cup)$$),
  and the residual is updated symmetrically: used capacity subtracted forward, reverse
  capacity added back
  $$R_{i+1,u,v} = (R_{i,u,v} \cdot^1 \delta_{i,u,v})_{i,u,v} \cdot^2 \delta_{i,v,u} :: \bigwedge^1 -(\cup)\ \bigwedge^2 +(\cup)$$.

  **Relabel.** Using the updated residual, recompute the admissible mask
  $$AdmPost_{i+1,u,v} = R_{i+1,u,v} \cdot Lbl_{i,u,v} :: \bigwedge \rightarrow(\cap)$$ — distances
  have not moved yet, so $$Lbl$$ is still generation $$i$$ — and whether each vertex still
  has any admissible edge
  $$HasAdm_{i+1,u} = AdmPost_{i+1,u,v} :: \bigvee \text{OR}(\cup)$$. The active set is recomputed
  on the updated excess
  $$Act_{i+1,u} = NST_u \cdot^1 (E_{i+1,u} \cdot^2 0)_{i+1,u} :: \bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 >(\cap)$$;
  this re-derivation is necessary because bulk-synchronous evaluation gives no
  read-after-write within a generation. A vertex relabels when it is still active but
  stuck:
  $$Rel_{i+1,u} = Act_{i+1,u} \cdot \neg HasAdm_{i+1,u} :: \bigwedge \text{AND}(\cap)$$ — the
  `else` branch of the textbook algorithm, expressed as a mask rather than control flow.
  For those vertices, gather residual-neighbour distances
  $$NeiLbl_{i,u,v} = (R_{i+1,u,v} \cdot^1 Rel_{i+1,u})_{i,u,v} \cdot^2 D_{i,v} :: \bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 \rightarrow(\cap)$$,
  take the minimum over rank $$v$$
  $$MinNeiLbl_{i,u} = NeiLbl_{i,u,v} :: \bigvee \min(\cup)$$, add one
  $$NewD_{i,u} = (MinNeiLbl_{i,u} \cdot 1)_{i,u} :: \bigwedge +(\cap)$$, and write the new
  distance back
  $$D_{i+1,u} = D_{i,u} \cdot NewD_{i,u} :: \bigwedge \mathbin{<\!\!<}(\cup)$$. The update
  operator $$<\!\!<$$ takes the right operand where it is present and falls back to the
  left, so relabeled vertices take $$NewD$$ and every other vertex keeps $$D_i$$.

  **Stop.** $$\diamond : \lVert Act_{i+1}\rVert \equiv 0$$. The cascade halts when no internal
  vertex holds excess — every unit of preflow has either reached the sink or been
  returned to the source, and the flow is maximum.
edge_expression: |
  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &G^{U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &C^{U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &F^{I,\, U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &R^{I,\, U \equiv \lvert V\rvert,\, V \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &E^{I,\, U \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &D^{I,\, U \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=+\infty\\
  &Act^{I,\, U \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &S^{U \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &T^{U \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\[4pt]
  &\triangleright \textbf{Initialization (}s = \text{source}, t = \text{sink)}\\
  &F_{i \equiv 0,u,v} = 0\\
  &E_{i \equiv 0,u} = 0\\
  &D_{i \equiv 1,u} = 0\\
  &D_{i \equiv 1,\ u\,:\,u = s} = \lvert V\rvert\\
  &S_{u\,:\,u = s} = \text{True}\\
  &T_{u\,:\,u = t} = \text{True}\\[4pt]
  &\triangleright \textbf{Preflow from source (}i \equiv 1\text{)}\\
  &FS_{i \equiv 1,u,v} = S_u \cdot C_{u,v} :: \textstyle\bigwedge *(\cap)\\
  &F_{i \equiv 1,u,v} = FS_{i \equiv 1,u,v} \cdot FS_{i \equiv 1,v,u} :: \textstyle\bigwedge -(\cup)\\
  &E_{i \equiv 1,v} = F_{i \equiv 1,u,v} :: \textstyle\bigvee +(\cup)\\
  &R_{i \equiv 1,u,v} =
  \begin{cases}
  0 & u = s\\
  C_{v,u} & v = s \,\wedge\, u \neq s\\
  C_{u,v} & \text{otherwise}
  \end{cases}\\[4pt]
  &\triangleright \textbf{Extended Einsum (one push/relabel round per iteration } i)\\
  &NST_u = \neg S_u \cdot \neg T_u :: \textstyle\bigwedge \text{AND}(\cap)\\
  &Act_{1,u} = NST_u \cdot^1 (E_{1,u} \cdot^2 0)_{1,u} :: \textstyle\bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 >(\cap)\\
  &ActR_{i,u,v} = Act_{i,u} \cdot R_{i,u,v} :: \textstyle\bigwedge \leftarrow(\cap)\\
  &Lbl_{i,u,v} = D_{i,u} \cdot (D_{i,v} + 1)_{i,v} :: \textstyle\bigwedge \equiv(\cap)\\
  &Adm_{i,u,v} = ActR_{i,u,v} \cdot Lbl_{i,u,v} :: \textstyle\bigwedge \text{AND}(\cap)\\[4pt]
  &\triangleright \textbf{Push Step}\\
  &PushCand_{i,u,v^*} = Adm_{i,u,v} \lll_{v^*} \mathbf{1}(\text{pick-admissible-edge})\\
  &\delta_{i,u,v} = (E_{i,u} \cdot^1 R_{i,u,v})_{i,u,v} \cdot^2 PushCand_{i,u,v} :: \textstyle\bigwedge^1 \min(\cap)\ \bigwedge^2 \leftarrow(\cap)\\
  &F_{i+1,u,v} = (F_{i,u,v} \cdot^1 \delta_{i,u,v})_{i,u,v} \cdot^2 \delta_{i,v,u} :: \textstyle\bigwedge^1 +(\cup)\ \bigwedge^2 -(\cup)\\
  &InPush_{i,v} = \delta_{i,u,v} :: \textstyle\bigvee +(\cup)\\
  &OutPush_{i,u} = \delta_{i,u,v} :: \textstyle\bigvee +(\cup)\\
  &E_{i+1,u} = (E_{i,u} \cdot^1 InPush_{i,u})_{i,u} \cdot^2 OutPush_{i,u} :: \textstyle\bigwedge^1 +(\cup)\ \bigwedge^2 -(\cup)\\
  &R_{i+1,u,v} = (R_{i,u,v} \cdot^1 \delta_{i,u,v})_{i,u,v} \cdot^2 \delta_{i,v,u} :: \textstyle\bigwedge^1 -(\cup)\ \bigwedge^2 +(\cup)\\[4pt]
  &\triangleright \textbf{Relabel Step}\\
  &AdmPost_{i+1,u,v} = R_{i+1,u,v} \cdot Lbl_{i,u,v} :: \textstyle\bigwedge \rightarrow(\cap)\\
  &HasAdm_{i+1,u} = AdmPost_{i+1,u,v} :: \textstyle\bigvee \text{OR}(\cup)\\
  &Act_{i+1,u} = NST_u \cdot^1 (E_{i+1,u} \cdot^2 0)_{i+1,u} :: \textstyle\bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 >(\cap)\\
  &Rel_{i+1,u} = Act_{i+1,u} \cdot \neg HasAdm_{i+1,u} :: \textstyle\bigwedge \text{AND}(\cap)\\
  &NeiLbl_{i,u,v} = (R_{i+1,u,v} \cdot^1 Rel_{i+1,u})_{i,u,v} \cdot^2 D_{i,v} :: \textstyle\bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 \rightarrow(\cap)\\
  &MinNeiLbl_{i,u} = NeiLbl_{i,u,v} :: \textstyle\bigvee \min(\cup)\\
  &NewD_{i,u} = (MinNeiLbl_{i,u} \cdot 1)_{i,u} :: \textstyle\bigwedge +(\cap)\\
  &D_{i+1,u} = D_{i,u} \cdot NewD_{i,u} :: \textstyle\bigwedge \mathbin{<\!\!<}(\cup)\\
  &\diamond : \lVert Act_{i+1}\rVert \equiv 0
  \end{aligned}
  $$
other_notes: |
  The source distance is lifted to $$\lvert V\rvert$$ at initialization, which is the standard
  push-relabel device: no admissible edge can ever point back into the source (its
  neighbours never reach distance $$\lvert V\rvert - 1$$ in a flow problem), so preflow excess
  that cannot reach the sink is routed back along reverse residual edges instead.
  Distances are monotonically non-decreasing across generations, which is what
  guarantees termination; the stop test $$\lVert Act_{i+1}\rVert \equiv 0$$ fires once all
  excess has drained to the sink or returned to the source. Note that the spec does not
  encode the $$2\lvert V\rvert - 1$$ distance bound — it halts on an empty active set, not on a
  counter.

  **Empty values carry real meaning here, and the two integer tensors resolve
  differently.** Capacity, flow, residual and excess all take `empty` $$= 0$$: a missing
  entry genuinely means zero. For the residual that is more than a convenience — a
  saturated edge reaches exactly $$0$$, which equals the empty value, so the edge simply
  leaves $$R$$ and every downstream intersection skips it with no explicit $$>0$$ test.
  The distance tensor $$D$$ cannot do the same. A distance of $$0$$ is a legal, common
  value, and $$D$$ is read through an intersection in the neighbour-distance gather
  ($$\cdots \rightarrow(\cap)\ D_{i,v}$$); with `empty` $$= 0$$ every distance-$$0$$ vertex would
  be treated as absent and dropped before reaching the $$\min$$ reduction, letting the
  relabel skip those neighbours and lift a vertex too high. $$D$$ therefore uses
  `empty` $$= +\infty$$, which also happens to be the identity of the $$\min(\cup)$$ that
  consumes it. The same question, asked of two tensors, gets opposite answers — and the
  deciding factor is what the value *means*, not the arithmetic.

variants: |
  Replacing the populate $$\lll_v$$ that picks one admissible edge per vertex with a
  push along *every* admissible edge gives the fully parallel (all-edges) push-relabel
  variant, at the cost of needing to split excess across edges. Replacing the
  height-rule pick and relabel machinery with an augmenting-path search on the residual
  graph recovers the Ford-Fulkerson / Edmonds-Karp family, which grows the flow path by
  path rather than by local push and relabel.

  **A correct sequential form is this cascade plus one Einsum.** Put a selector in
  front of it:

  $$Sel_{i,u^*} = Act_{i,u} \lll_{u^*} \mathbf{1}(\text{select-any-vertex})$$

  Feed $$Sel$$ into $$ActR$$ in place of $$Act$$, gate $$Rel$$ with it, and the other
  twenty-two Einsums are unchanged. They need no change because $$Sel$$ is one-hot:
  only one row survives into $$ActR$$, so $$Adm$$ has one row, so the populate selects
  one edge, so $$\delta$$ has at most one entry. The reductions still reduce — over a
  single element. The result computes the same maximum flow, with the same number of
  pushes and relabels.

  **That is not the same as transcribing the pseudocode.** The cascade above
  recomputes $$Act$$ and admissibility after the push, because bulk-synchronous execution
  has no read-after-write. Keep those recomputations and the relabel test is asked
  against *post-push* state — so a vertex that makes a saturating push, still holds
  excess, and now has nothing admissible will relabel **in the same round**. On CLRS
  Figure 26.1 that happens three times: 29 operations packed into 26 rounds. Every
  round is a legal push-relabel step, but a round is no longer an iteration of
  *while there exists an active vertex*.

  Writing the pseudocode out directly instead — pick one vertex, test it **once**,
  then push *or* relabel — moves the admissibility test before the push, decides the
  branch from it, and drops the three post-push recomputations. That cascade is
  **shorter than the parallel one**, 23 Einsums against 24, and reproduces the
  textbook operation for operation: 29 rounds, 29 operations, the same 29 in the same
  order, on every seed tested. Both sequential forms are linked above; the side-by-side
  page puts the parallel cascade next to the pseudocode one, with the
  differences computed from the specs.

  So the transformation has two prices, and they are worth stating separately.
  **One Einsum** buys a correct sequentialisation. **Matching the pseudocode
  operation for operation** costs that Einsum plus three edits and three deletions.

  Read the other way round, **the parallel version is the sequential one with a
  selector removed**, and that is the general shape of the transformation: every
  populate marks a place where the sequential algorithm said "pick one and do it."
  A selector can be dropped when the items it chooses between do not share mutable
  state. Dropping $$Sel$$ is safe — each vertex spends only its own excess, and two
  vertices' pushes land on disjoint cells of $$F$$ and $$R$$; the one collision that
  would matter, $$u \to v$$ and $$v \to u$$ in the same generation, needs
  $$D(u) = D(v)+1$$ *and* $$D(v) = D(u)+1$$, which the height rule forbids. Dropping
  the per-vertex $$\lll_v$$ is *not* safe: one vertex cannot spend the same excess
  twice. That populate is a resource constraint, not a serialization point.

  Removing a selector is not free. Bulk-synchronous execution has no read-after-write,
  so anything derived from mutated state must be recomputed as a new generation — which
  is exactly why admissibility is computed twice per generation above. $$Act$$ is
  written twice too, but only one of those is in the loop: $$Act_{1}$$ seeds it and
  $$Act_{i+1}$$ advances it. That duplication is the visible residue of the selector
  that is no longer there.

  The two admissibility results are **different tensors**, and deliberately so.
  $$Adm_{i,u,v}$$ reduces $$ActR$$, so it carries the active-vertex factor, and it is
  what the push selects from. $$AdmPost_{i+1,u,v}$$ reads $$R_{i+1}$$ directly, has no
  active-vertex factor, and reads $$Lbl_i$$ — the heights *before* this round's
  relabel. It is not a later generation of $$Adm$$: asking the question at the new
  heights would need $$D_{i+1}$$, which is computed from this very answer. $$Act$$ is
  the opposite case — its two computations agree, so one of them is redundant.

  Which vertex $$\text{select-any-vertex}$$ picks is deliberately left open, as in the
  generic algorithm. Lowest-index, FIFO and highest-label are all valid refinements
  with their own bounds; across random graphs the rule changes the operation count by
  up to $$3\times$$ but never the answer. It is a scheduling choice, not part of the
  specification.
implementation_notes: |
  The preflow is one saturating product over the source row plus the residual case
  setup. Each generation is dominated by the two edge-ranked tensors $$F$$ and $$R$$:
  forming the admissible mask, the per-vertex push selection, and the symmetric
  flow / residual / excess updates are all sparse products and merges over the
  $$(u, v)$$ edge rank, while the active and relabel steps reduce to per-vertex work.
  Keeping $$F$$, $$R$$, $$E$$, and $$Act$$ sparse means each generation touches work
  proportional to the active edges, not to $$\lvert V\rvert^2$$. The pick-admissible-edge
  populate is the one nondeterministic step — any admissible neighbour is a valid
  choice — and is naturally a per-vertex selection over its admissible residual edges.
  Running the cascade under many different choices produces different schedules and
  different generation counts, but the same maximum flow.
complexity_costs: |
  Generic push-relabel runs in $$O(\lvert V\rvert^2\,\lvert E\rvert)$$ time; the highest-label
  selection rule improves this to $$O(\lvert V\rvert^2 \sqrt{\lvert E\rvert})$$. Each relabel
  raises a vertex's distance by at least one and distances are bounded by $$2\lvert V\rvert - 1$$,
  bounding the number of relabels at $$O(\lvert V\rvert^2)$$; saturating and non-saturating
  pushes are bounded separately, with the non-saturating pushes dominating. The
  bulk-synchronous form here trades a larger generation count for fully parallel
  per-generation work.
related_notes: |
  The augmenting-path methods (Ford-Fulkerson, Edmonds-Karp) solve the same maximum-flow
  problem by repeatedly pushing flow along whole source-to-sink paths in the residual
  graph, rather than by local push and relabel. Breadth-first search is the residual-graph
  traversal those augmenting-path methods build on.
---
