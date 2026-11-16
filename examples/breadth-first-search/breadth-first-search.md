---
title: Breadth-First Search (Depth-Tracking)
authors: [Toluwanimi Odemuyiwa]
summary: Level-synchronous BFS that records the hop-distance of every vertex from a source set, expressed as an iterated extended Einsum over a graph tensor.
tags: [bfs, traversal, frontier, graphs]
ranks:
  I: generational
  S: vertex
  D: vertex
status_intro: |
  This page gives the depth-tracking form of breadth-first search: starting from
  a set of source vertices, it labels every reachable vertex with the number of
  hops to the nearest source. The computation is a single extended Einsum applied
  once per level, threaded through a generational rank $I$ until the frontier is
  empty.
problem_statement: |
  Given a directed graph $G$ on $\lvert V\rvert$ vertices and a set of source vertices
  $id$, compute for each vertex $d$ the length of the shortest unweighted path
  from any source to $d$ (its BFS depth). Unreached vertices have no value.

  The state is carried by four tensors:

  - $G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert}$, the graph, with `empty` $= 0$. $G$ is static,
    so it carries no generational rank.
  - $F^{I,\, S \equiv \lvert V\rvert}$, the frontier at generation $i$ (the depth of each
    vertex discovered at that level), `empty` $= \infty$.
  - $T^{I,\, D \equiv \lvert V\rvert}$, the candidate depths produced by advancing the
    frontier across edges, `empty` $= \infty$.
  - $P^{I,\, D \equiv \lvert V\rvert}$, the Boolean "visited" mask, `empty` $=$ False.
working_example_part1: |
  Take the five-vertex graph with unit edges
  $0\to1,\ 0\to2,\ 1\to3,\ 2\to3,\ 3\to4$ and source set
  $id = \lbrace 0\rbrace$. Every present entry of $G$ is the hop cost $1$.

  Initialization places the source at depth $0$ and marks it visited:

  $$F_0 = \lbrace 0:0\rbrace, \qquad P_0 = \lbrace 0:\text{True}\rbrace.$$
working_example_part2: |
  Each generation advances the frontier one hop, filters out already-visited
  vertices, and folds the survivors into the visited mask:

  | $i$ | $T_i$ (candidates) | $F_{i+1}$ (new frontier) | depths fixed |
  |----|----|----|----|
  | 0 | $\lbrace 1:1,\ 2:1\rbrace$ | $\lbrace 1:1,\ 2:1\rbrace$ | $1,2 \mapsto 1$ |
  | 1 | $\lbrace 3:2\rbrace$ | $\lbrace 3:2\rbrace$ | $3 \mapsto 2$ |
  | 2 | $\lbrace 4:3\rbrace$ | $\lbrace 4:3\rbrace$ | $4 \mapsto 3$ |
  | 3 | $\lbrace \rbrace$ | $\lbrace \rbrace$ | — (stop) |

  The frontier empties at $i = 3$, so $\lVert F_{4} \rVert \equiv 0$ fires and the
  iteration halts. The union of the frontiers over all generations gives the final
  depths $\lbrace 0:0,\ 1:1,\ 2:1,\ 3:2,\ 4:3\rbrace$.
edge_expression_walkthrough: |
  **Advance.** $T_{i,d} = G_{s,d} \cdot F_{i,s} :: \bigwedge_s +(\cap)\ \bigvee_s \text{ANY}(\cup)$.
  The intersection merge $+(\cap)$ touches a coordinate only where both the edge
  $G_{s,d}$ and the source depth $F_{i,s}$ are present, and adds them, so a
  neighbour $d$ receives depth $F_{i,s} + 1$. The reduction $\bigvee_s$ collapses
  the source rank $s$. Because every vertex in a given frontier shares the same
  depth, all contributions to a destination are equal, so $\text{ANY}$ may stand
  in for $\min$ here.

  **Graph meaning:** Every vertex on the frontier offers each out-neighbour a depth one more than its own.

  **Einsum meaning:** For each destination $d$, add $G_{s,d}$ to $F_{i,s}$ wherever both are present, then reduce over $s$, keeping any one of the equal sums.

  **Filter.** $F_{i+1,d} = T_{i,d} \cdot \neg P_{i,d} :: \bigwedge_d \leftarrow(\cap)$.
  The complement $\neg P$ is taken over the full destination coordinate space, so
  it is present exactly at the *un*visited vertices. The take-left intersection
  $\leftarrow(\cap)$ then keeps the candidate depth $T_{i,d}$ only where the vertex
  is still unvisited — this is what stops BFS from revisiting a vertex at a later,
  larger depth.

  **Graph meaning:** Keep a candidate depth only for vertices not yet visited; they form the next frontier.

  **Einsum meaning:** Take $T_{i,d}$ exactly where $\neg P_{i,d}$ is present, that is, where $P_{i,d}$ is empty.

  **Mark.** $P_{i+1,d} = P_{i,d} \cdot F_{i+1,d} :: \bigwedge_d \text{OR}(\cup)$.
  A vertex is visited at generation $i+1$ if it was already visited or just
  entered the frontier.

  **Graph meaning:** Mark the vertices of the new frontier as visited, keeping the earlier marks.

  **Einsum meaning:** OR $P_{i,d}$ with $F_{i+1,d}$ over $d$, wherever either is present.

  **Stop.** $\diamond : \lVert F_{i+1} \rVert \equiv 0$. Here $\lVert \cdot \rVert$
  is the occupancy — the count of non-empty entries — so the condition reads "the
  new frontier has no active vertices." Note that with `empty` $= \infty$ for $F$,
  occupancy counts entries that are *present*, not entries whose value is zero (the
  source legitimately has depth value $0$).

  **Graph meaning:** Stop when no vertex was newly discovered.

  **Einsum meaning:** Halt when the occupancy of $F_{i+1}$, its count of non-empty entries, is zero.
edge_expression: |
  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &F^{I,\, S \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=\infty\\
  &T^{I,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=\infty\\
  &P^{I,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\[4pt]
  &\triangleright \textbf{Initialization}\\
  &F_{0,\ s\,:\,s \in id} = 0\\
  &P_{0,\ d\,:\,d \in id} = \text{True}\\[4pt]
  &\triangleright \textbf{Extended Einsum}\\
  &T_{i,d} = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge_s +(\cap)\ \bigvee_s \text{ANY}(\cup)\\
  &F_{i+1,d} = T_{i,d} \cdot \neg P_{i,d} :: \textstyle\bigwedge_d \leftarrow(\cap)\\
  &P_{i+1,d} = P_{i,d} \cdot F_{i+1,d} :: \textstyle\bigwedge_d \text{OR}(\cup)\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$
other_notes: |
  The $\text{ANY}$ reduction is sound only because the frontier at any generation
  is depth-uniform; for weighted edges the contributions to a destination differ
  and a $\min$ reduction is required (see Bellman-Ford). Termination is guaranteed
  by the monotonically growing visited mask $P$, bounded by $\lvert V\rvert$, rather than by
  any property of the notation itself.
variants: |
  Replacing the unit advance with a weighted relaxation and a $\min$ reduction, and
  dropping the visited filter so vertices can re-relax, yields single-source
  shortest paths (Bellman-Ford). A graph that changes per iteration would carry the
  generational rank $I$ on the graph tensor as well.
implementation_notes: |
  The advance is a sparse matrix-by-frontier product; the filter and mark steps are
  elementwise merges over the destination rank. Keeping $F$, $T$, and $P$ as sparse
  (present-only) tensors means each generation touches work proportional to the
  active frontier and its out-edges, not to $\lvert V\rvert$.
complexity_costs: |
  Each vertex enters the frontier at most once and each edge is relaxed at most
  once across the whole run, giving $O(\lvert V\rvert + \lvert E\rvert)$ total work. The number of
  generations is the eccentricity of the source set (at most the graph diameter).
related_notes: |
  Bellman-Ford generalizes the advance to weighted, re-relaxing shortest paths.
---
