---
title: Direction-Optimizing BFS (DO-BFS)
authors: [Sanjana Mali, Toluwanimi Odemuyiwa]
summary: Breadth-first search that dynamically switches between top-down (push from frontier) and bottom-up (pull from unvisited) traversal to cut wasted edge examinations on low-diameter graphs, expressed as EDGE cascades with macros.
tags: [bfs, traversal, direction-optimizing, frontier, graphs]
status_intro: |
  Direction-Optimizing Breadth-First Search, introduced by Beamer et al. (2012), combines
  multiple traversal strategies to improve performance on low-diameter graphs. This page
  gives it in EDGE notation by walking through three formulations in order: **top-down**
  (push from the frontier), **bottom-up** (pull from unvisited vertices), and **hybrid**
  (switch dynamically between the two, using Beamer's original switching heuristic). Each
  cascade comes with a walkthrough that explains every line in both graph-algorithm terms
  and Einsum terms.

  Traditionally, bottom-up BFS requires maintaining additional data structures (e.g., parent
  pointers) to enable efficient backward exploration, which can introduce overhead. The EDGE
  formulation shows that algorithmically, this information is readily available within the
  Einsum, and the key difference boils down to an algebraic manipulation of top-down BFS
  combined with a mapping change (traversal order). Switching between the two strategies is
  not free: it involves an additional algorithmic step to decide when to switch, and
  potentially requires changes to data formats or traversal order.

  Switching is part of the specification. The work estimates and the threshold comparison
  are Einsums over the same tensors the traversal already uses, and the choice of direction
  is made with a macro and a conditional cascade. The other switching heuristics (Gunrock,
  Ligra, XBFS) are written the same way, which makes it easy to compare them side by side.

  This is a worked example, not an algorithm tutorial: we assume the reader already knows BFS.

problem_statement: |
  Given an unweighted graph $G = (V, E)$ and a source vertex $s \in V$, discover all vertices
  reachable from $s$ and construct a BFS tree. The BFS tree records, for each reachable
  vertex, a parent vertex that discovered it during traversal.

  Direction-Optimizing BFS improves performance on large graphs by dynamically switching
  between two traversal strategies:

  - **Top-Down:** expand outward from the current frontier (the set of vertices discovered at
    the current level, i.e., the active set) to discover new vertices.
  - **Bottom-Up:** for each unvisited vertex, check whether any of its neighbors (parents)
    are in the current frontier.

  The algorithm selects the traversal direction based on the size of the frontier relative
  to the remaining unvisited vertices.

  **Inputs.** An unweighted graph $G = (V, E)$ with $\lvert V\rvert$ vertices and
  $\lvert E\rvert$ edges, which may be directed or undirected, and a source vertex $s \in V$.

  **Outputs.** The set of vertices reachable from $s$, and a BFS tree recording, for each
  reachable vertex $v \neq s$, a parent that discovered $v$.

  **Algorithmic steps.**

  1. Initialize the frontier with the source vertex $s$.
  2. Mark $s$ as visited and record it as its own parent.
  3. While the frontier is not empty:
     - If the frontier is small relative to the number of unvisited vertices, perform a
       Top-Down step: for each vertex in the frontier, explore its outgoing edges; for each
       unvisited neighbor, mark it visited, record its parent, and add it to the next frontier.
     - Otherwise, perform a Bottom-Up step: for each unvisited vertex, check whether any of its
       parents (incoming edges) are in the frontier; if so, mark it visited, record one such
       neighbor as its parent, and add it to the next frontier.
     - Replace the current frontier with the newly discovered vertices.
  4. Terminate when the frontier becomes empty.

  The state is carried by three tensors, each indexed by the generational rank $I$ that
  counts BFS levels:

  - $G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean}$, `empty` $=$ False.
    $G_{s,d} = $ True iff edge $s \to d$ exists. Static; carries no $I$ rank.
  - $F^{I,\, S \equiv \lvert V\rvert} \to \text{Boolean}$, `empty` $=$ False.
    $F_{i,s} = $ True iff vertex $s$ is in the frontier at level $i$.
  - $\mathit{Tree}^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean}$,
    `empty` $=$ False. $\mathit{Tree}_{i,s,d} = $ True means vertex $s$ is recorded as the
    parent of vertex $d$ by level $i$.

  The $\mathit{Tree}$ tensor is the tensor representation of the parent array: a $(s,d)$ entry
  means "$s$ is the parent of $d$." At the format/implementation level it would typically be
  stored as a compact parent array rather than a dense matrix. In the cascades below, $n$ is
  the source vertex, since $s$ is a rank variable there.

working_example_part1: |
  Consider the five-vertex graph with directed edges
  $1 \to 2,\ 1 \to 3,\ 2 \to 4,\ 3 \to 4,\ 4 \to 5$ and source $s = 1$.

  **Top-down traversal.** Starting from vertex 1, every frontier vertex explores all of its
  outgoing edges:

  | Level $i$ | Frontier $F_i$ | New discoveries | Parent edges added |
  |---|---|---|---|
  | 0 | $\{1\}$ | $2, 3$ | $(1,2),\ (1,3)$ |
  | 1 | $\{2, 3\}$ | $4$ | $(2,4)$ |
  | 2 | $\{4\}$ | $5$ | $(4,5)$ |
  | 3 | $\{5\}$ | — (stop) | — |

  Vertex 1 is its own parent. Vertex 3 also reaches 4, but 4 is already discovered, so only one
  parent is kept (vertex 2, the first discoverer). Vertex 5 has no new neighbors, so the
  frontier becomes empty and the algorithm terminates.

  **When would bottom-up be used?** In large graphs, when the frontier becomes very large (for
  example, when it contains a significant fraction of the vertices), it may be more efficient
  to reverse the search direction. The key advantage of the bottom-up approach is that, for each
  unvisited vertex, the search can terminate as soon as a single parent is found (i.e., early
  exit). In contrast, the top-down approach explores all outgoing edges from the frontier,
  requiring every such edge to be examined.

  **Bottom-up traversal** on the same graph, starting from vertex 1. At the first step, instead
  of expanding from vertex 1, we scan vertices 2–5 and ask "does any parent lie in $\{1\}$?".
  Vertex 2 checks: yes (edge $1 \to 2$). Vertex 3 checks: yes ($1 \to 3$). Vertices 4 and 5: no
  (their parents are 2, 3 and 4 respectively, none in the frontier yet). The next frontier is
  $\{2, 3\}$. Then vertex 4 finds that 2 is in the frontier; although 3 also connects to 4, the
  first detected parent is chosen. Then vertex 5 finds 4. Finally no unvisited vertex finds a
  parent in the frontier, so the next frontier is empty and the algorithm terminates. The result
  is the same tree, with the traversal order reversed.

working_example_part2: |
  The same example as tensors. The adjacency matrix $G$ has True entries at
  $(1,2),\ (1,3),\ (2,4),\ (3,4),\ (4,5)$; all other entries are False.

  **Top-down: one iteration.** We will use the intermediate tensors that appear in the full
  EDGE expression: $NV$ (Not Visited vertices), $\mathit{Nei}$ (neighbors of the frontier),
  $\mathit{NeiNV}$ (neighbors of the frontier that are Not Visited), and
  $\mathit{CandTree}$ / $\mathit{Temp}$ (temporary tree updates).

  *Initialize.* The frontier contains only the source, and the source is its own parent:

  $$F_{0,1} = \text{True}, \qquad \mathit{Tree}_{0,1,1} = \text{True}.$$

  *Step A: Not Visited vertices.* A vertex is Not Visited if it has no parent recorded in
  $\mathit{Tree}$. At iteration 0:

  $$NV_{0,1} = \text{False}, \quad NV_{0,2} = NV_{0,3} = NV_{0,4} = NV_{0,5} = \text{True}.$$

  *Step B: neighbors of the frontier.* The frontier contains only vertex 1, so
  $\mathit{Nei}_{0,d}$ is True exactly for the outbound neighbors of 1:

  $$\mathit{Nei}_{0,2} = \text{True}, \quad \mathit{Nei}_{0,3} = \text{True}, \quad
    \mathit{Nei}_{0,4} = \text{False}, \quad \mathit{Nei}_{0,5} = \text{False}.$$

  *Step C: new discoveries.* Vertices 2 and 3 are Not Visited and are neighbors of the
  frontier, so $\mathit{NeiNV}_{0,2} = \mathit{NeiNV}_{0,3} = \text{True}$, and all other
  entries are False.

  *Step D: record parent links.* Only $s = 1$ is in the frontier and the new children are
  $d \in \{2, 3\}$, so $\mathit{CandTree}_{0,1,2}$ and $\mathit{CandTree}_{0,1,3}$ become True.
  If multiple parents discover the same child in the same iteration, the populate action
  selects exactly one. After iteration 0, the tree has True at $(s,d)$ locations
  $(1,1),\ (1,2),\ (1,3)$.

  *Step E: update the frontier.* The newly discovered vertices become the next frontier:
  $F_{1,2} = \text{True},\ F_{1,3} = \text{True}$. Termination is detected when the newly
  computed frontier becomes empty.

  **Bottom-up: the same iteration.** Intuitively, the bottom-up traversal asks: "For each Not
  Visited vertex, does it have a parent in the current frontier?" The initial frontier and tree
  are the same, and so is $NV$: vertices $\{2, 3, 4, 5\}$ are Not Visited.

  *Step B: examine unvisited vertices.* $\mathit{CandParents}_{i,s,d}$ holds all candidate
  parent-child edges $(s,d)$ where $d$ is currently Not Visited. Next we check which of those
  candidate parents lie in the current frontier: since only vertex 1 is in the frontier at
  iteration 0, $\mathit{InF}_{0,1,2}$ and $\mathit{InF}_{0,1,3}$ become True, and no other
  $\mathit{InF}$ entries are True.

  *Step C: select a parent and update the tree.* Only one valid parent exists for each of 2 and
  3, so $\mathit{Temp}_{0,1,2}$ and $\mathit{Temp}_{0,1,3}$ are True. The tree now contains
  $(1,1),\ (1,2),\ (1,3)$.

  *Step D: update the frontier.* Reducing $\mathit{InF}$ over the parent index gives
  $F_{1,2} = \text{True},\ F_{1,3} = \text{True}$.

  This matches the top-down result, but the computation order was reversed: instead of expanding
  from vertex 1, we scanned Not Visited vertices and checked whether they have a parent in the
  frontier. While these expressions are written over all $(s,d)$ pairs, the actual bottom-up
  algorithm is vertex-centric, where each Not Visited vertex examines its parents and may
  terminate early once one parent in the frontier is found.

edge_expression_walkthrough: |
  This walkthrough covers the **top-down** direction, line by line. For each expression, we
  explain what it means in graph-algorithm terms and what it means as an Einsum-style tensor
  computation. The tensors are those in the Problem Statement.

  **Step 1 — Gather neighbors of the current frontier (Nei).**
  In the top-down direction, we expand outward from active frontier vertices. A vertex $d$ is
  considered a neighbor if there exists at least one frontier vertex $s$ such that an edge
  $s \to d$ exists.

  $$\mathit{Nei}_{i,d} = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge_s \text{AND}(\cap)\ \bigvee_s \text{OR}(\cup).$$

  **Graph meaning:** From all vertices in the frontier, collect all outgoing neighbors.

  **Einsum meaning:** Elementwise AND between $G_{s,d}$ and $F_{i,s}$ produces a tensor that
  identifies all candidate edges $(s,d)$ from the current frontier. Reducing over $s$ using OR
  then determines whether each vertex $d$ has at least one such incoming edge, thereby gathering
  all neighbors of the frontier.

  **Step 2 — Find the visited vertices (Visited).**
  A vertex has been visited when it has a parent recorded in the BFS tree. We detect this by
  reducing $\mathit{Tree}_{i,p,c}$ over the parent index $p$.

  $$\mathit{Visited}_{i,c} = \mathit{Tree}_{i,p,c} :: \textstyle\bigvee_p \text{OR}(\cup).$$

  **Graph meaning:** Find every vertex that already has a parent in the BFS tree.

  **Einsum meaning:** Reduce the Boolean tensor $\mathit{Tree}$ over index $p$ using OR.

  **Step 3 — Compute the set of Not Visited vertices (NV).**
  A vertex is considered Not Visited when it does not yet have any parent recorded in the BFS
  tree, so we negate the result of the reduction. The negation comes after the reduction: a
  unary operator applies to its input tensor first, so $\neg \mathit{Tree}_{i,p,c}$ under the
  same reduction would ask whether *some* $p$ is not a parent of $c$, which is true of every
  vertex.

  $$NV_{i,c} = \neg \mathit{Visited}_{i,c}.$$

  **Graph meaning:** Find every vertex that does not yet have a parent in the BFS tree.

  **Einsum meaning:** Negate the resulting mask.

  **Step 4 — Filter out previously visited neighbors (NeiNV).**
  We only want to visit new vertices in the current iteration. Intersecting $\mathit{Nei}$ with
  the Not Visited mask $NV$ keeps only those neighbors that are not yet visited.

  $$\mathit{NeiNV}_{i,d} = \mathit{Nei}_{i,d} \cdot NV_{i,d} :: \textstyle\bigwedge_d \text{AND}(\cap).$$

  **Graph meaning:** Keep only neighbors that have not been discovered before.

  **Einsum meaning:** Elementwise AND between $\mathit{Nei}_{i,d}$ and $NV_{i,d}$.

  **Step 5 — Record parent-child relationships (CandTree).**
  For each newly discovered child $d$, we want to record which frontier vertex or vertices $s$
  discovered it. A parent-child entry should be set when $s$ is in the frontier at iteration $i$,
  an edge $s \to d$ exists in the graph, and $d$ is newly discovered in this iteration.

  $$\mathit{CandTree}_{i,s,d} = (G_{s,d} \cdot F_{i,s})_{i,s,d} \cdot \mathit{NeiNV}_{i,d}
    :: \textstyle\bigwedge \text{AND}(\cap)\ \bigwedge \text{AND}(\cap).$$

  **Graph meaning:** Record all parents for newly discovered vertices from the frontier.

  **Einsum meaning:** Compute $(G_{s,d} \cdot F_{i,s})$ and broadcast it into the $(i,s,d)$
  space, then AND with $\mathit{NeiNV}_{i,d}$.

  **Step 6 — Select exactly one parent when there are multiple candidates (Temp).**
  A newly discovered vertex may be a child of multiple frontier vertices. BFS stores only one
  parent per vertex. The populate action enforces this by selecting a single parent index $s^*$
  for each child $d$. Here, the first parent found is kept. See
  Other Notes for details on the implementation of populate with the coordinate operator
  `pick-parent`.

  $$\mathit{Temp}_{i,s^*,d} = \mathit{CandTree}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent}).$$

  **Graph meaning:** If multiple frontier vertices discover the same child, keep the first one
  found as the parent.

  **Einsum meaning:** Populate a new tensor by applying a coordinate operator `pick-parent` to
  choose one $s$ per $d$.

  **Step 7 — Update the BFS tree (Tree).**
  We merge the newly selected parent assignments with the existing tree so that parents recorded
  in previous iterations are preserved.

  $$\mathit{Tree}_{i+1,s,d} = \mathit{Tree}_{i,s,d} \cdot \mathit{Temp}_{i,s,d}
    :: \textstyle\bigwedge_d \text{OR}(\cup).$$

  **Graph meaning:** Add the newly discovered parent-child edges into the BFS tree.

  **Einsum meaning:** Elementwise OR between the previous tree and the new assignments.

  **Step 8 — Update the frontier for the next iteration.**
  The next frontier is exactly the set of newly discovered vertices.

  $$F_{i+1,d} = \mathit{NeiNV}_{i,d}.$$

  **Graph meaning:** Set the next frontier to all newly discovered vertices.

  **Einsum meaning:** Copy the Boolean mask $\mathit{NeiNV}_{i,d}$ into $F_{i+1,d}$.

  **Step 9 — Terminate when no new vertices are discovered.**
  The BFS traversal stops when the new frontier is empty.

  $$\diamond : \lVert F_{i+1} \rVert \equiv 0.$$

  **Graph meaning:** Stop when there are no newly discovered vertices.

  **Einsum meaning:** Check whether any entry in $F_{i+1}$ is True.

  Here $\lVert \cdot \rVert$ counts present (non-empty) entries, not zero-valued ones, so
  the source at depth 0 does not accidentally trigger early termination.

edge_expression: |
  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &F^{I,\, S \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{Tree}^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\[4pt]
  &\triangleright \textbf{Initializations}\\
  &F_{i,s} = \text{False}\\
  &\mathit{Tree}_{i,s,d} = \text{False}\\
  &G_{s,d} \to \langle\text{user-specified}\rangle\\
  &F_{0,n} = \text{True}\\
  &\mathit{Tree}_{0,n,n} = \text{True}\\[4pt]
  &\triangleright \textbf{Extended Einsum — Top-Down}\\
  &\mathit{Nei}_{i,d} = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge_s \text{AND}(\cap)\ \bigvee_s \text{OR}(\cup)\\
  &\mathit{Visited}_{i,c} = \mathit{Tree}_{i,p,c} :: \textstyle\bigvee_p \text{OR}(\cup)\\
  &NV_{i,c} = \neg \mathit{Visited}_{i,c}\\
  &\mathit{NeiNV}_{i,d} = \mathit{Nei}_{i,d} \cdot NV_{i,d} :: \textstyle\bigwedge_d \text{AND}(\cap)\\
  &\mathit{CandTree}_{i,s,d} = (G_{s,d} \cdot F_{i,s})_{i,s,d} \cdot \mathit{NeiNV}_{i,d}
    :: \textstyle\bigwedge \text{AND}(\cap)\ \bigwedge \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{CandTree}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{Tree}_{i+1,s,d} = \mathit{Tree}_{i,s,d} \cdot \mathit{Temp}_{i,s,d}
    :: \textstyle\bigwedge_d \text{OR}(\cup)\\
  &F_{i+1,d} = \mathit{NeiNV}_{i,d}\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

other_notes: |
  **From a visited mask to parent tracking.**
  The baseline formulations (see Variants) use an explicit visited mask $P$. In the
  Direction-Optimizing BFS of Beamer et al., this information is not stored explicitly. Instead,
  the algorithm maintains a parent array, where each vertex records the vertex that first
  discovered it. The visited set is implicit in the parent array: if a vertex has a parent, it
  has been visited; if not, it is unvisited. This representation is used consistently in both
  the top-down and bottom-up phases. It tracks reachability as a visited mask does, and also
  captures the structure of the BFS tree.

  **Why a Tree tensor instead of a visited bit?**
  The $\mathit{Tree}^{I,S,D}$ tensor encodes parent-child relationships using two vertex
  ranks ($S$ for parent, $D$ for child). This follows the EDGE convention that each set of
  vertices playing a distinct role gets its own named rank. As a result, "is vertex $d$
  visited?" is derived by reducing $\mathit{Tree}_{i,p,d}$ over the parent rank $p$ — it is
  not stored separately. At the format/implementation level, $\mathit{Tree}$ would typically
  be materialized as a compact parent array, not a dense $\lvert V\rvert \times \lvert V\rvert$
  Boolean matrix.

  **Populate with the coordinate operator `pick-parent`.**
  A child vertex may be discovered by multiple candidate parents in the same iteration, but the
  BFS tree must store exactly one parent for each child. In EDGE, we enforce this using the
  populate action together with a coordinate operator called `pick-parent`. Populate processes
  one child coordinate at a time. For a fixed child $d$, it may receive multiple candidate
  parents $s$; the role of `pick-parent` is to choose exactly one of those candidates and discard
  the others. We enforce early exit in the coordinate operator, by selecting the first candidate
  parent encountered for each child vertex:

  ```
  for each child vertex d do
      for each candidate parent s do
          if no parent is currently recorded for d then
              record s as the parent of d
              break
  ```

  After populate completes, each vertex has at most one recorded parent, ensuring that the
  $\mathit{Tree}$ tensor represents a valid BFS tree rather than a general directed acyclic graph
  in which a vertex could have several parents.

  In $\mathit{Temp}_{i,s^*,d} = \mathit{CandTree}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})$,
  the operator is applied along the parent dimension $s$ for a fixed child vertex $d$. Its inputs
  are `z_fiber`, the set of currently selected parent coordinates for child $d$ (an $S$-fiber of
  $\mathit{Temp}$); `rhs_coord`, the candidate parent coordinate $s$; and `rhs_val`, the value of
  candidate parent $s$ coming from $\mathit{CandTree}_{i,s,d}$. Its outputs are `valid_coords`,
  the parent coordinate that should remain True, and `dead_coords`, parent coordinates that must
  be removed. The rule implemented here selects the first-seen parent. Other tie-breaking rules
  may select the parent with the smallest vertex id, but doing so prevents early exit.

  ```python
  def pick_parent(z_fiber, rhs_coord, rhs_val):
      # Candidate parent coming from CandTree_{i,s,d}
      cand_s = rhs_coord

      # Check if any parent is already recorded for this child d
      has_parent = len(z_fiber) > 0

      if has_parent:
          # Already have a parent: reject the candidate
          valid_coords = []
          dead_coords = []
      else:
          # No parent yet: accept the first candidate seen
          valid_coords = [cand_s]
          dead_coords = []

      return valid_coords, dead_coords
  ```

  **BFS tree and path reconstruction.** For each vertex $d$, exactly one parent $s$ is selected
  (except for the source, which is its own parent). The collection of these parent assignments
  forms a BFS tree rooted at the source vertex. To generate the path from the source $s$ to any
  reachable vertex $v$, repeatedly follow the recorded parent pointers: start at $v$, look up its
  parent in the $\mathit{Tree}$ tensor, and continue until the source is reached. Reversing this
  sequence yields the shortest path from $s$ to $v$ in an unweighted graph. Because BFS explores
  vertices level by level, the depth of a vertex in the tree corresponds to its shortest-path
  distance (in number of edges) from the source.

  **Populate and parent choice.** The populate step enforces the BFS-tree constraint "one parent
  per vertex." The coordinate operator `pick-parent` can implement different deterministic
  tie-breaking rules (e.g., minimum parent id, first-seen in a traversal order, or any random
  selection). Different rules may produce different valid BFS trees but the reachable set is
  unchanged.

  **Switch thresholds ($\alpha$ and $\beta$).** The hybrid algorithm uses two thresholds: $\alpha$
  to decide when to switch from top-down to bottom-up, and $\beta$ to decide when to switch back.
  These parameters are typically chosen empirically and may depend on graph structure (diameter,
  degree distribution) and hardware (memory bandwidth, cache behavior).

  **Work estimates ($\mathit{MF}$, $\mathit{MU}$).** $\mathit{MF}_i$ approximates work for top-down
  by measuring total frontier degree. $\mathit{MU}_i$ approximates work for bottom-up by measuring
  total degree of Not Visited vertices. These are proxy cost models; exact runtime depends on
  memory access patterns and representation.

  **Termination check.** The condition $\lVert F_{i+1} \rVert \equiv 0$ is written abstractly.
  Implementations typically check whether the next frontier has any elements (or whether a
  frontier count is zero).

  **Memory optimization.** The cascade as written materializes all generations of $F$ and
  $\mathit{Tree}$. In practice only two generations are needed (ping-pong), since each level
  depends only on the previous one:

  $$F_{(i+1)\bmod 2,\,d} = G_{s,d} \cdot F_{i\bmod 2,\,s} \cdot NV_{i\bmod 2,\,d}
    :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee \text{OR}(\cup).$$

  A similar optimization is possible for the $\mathit{Tree}$ tensor. This is a
  format/implementation choice, invisible to the EDGE specification.

variants: |
  **Baseline: BFS with a visited mask.**
  Before adding parent tracking and switching, plain BFS gives a simple baseline. It uses the
  graph $G$, the frontier $F$, and a visited mask $P$ that keeps track of which vertices have
  already been discovered.

  In the top-down form, we take all neighbors of the current frontier and add those that have not
  been visited before to the next frontier:

  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &G^{S,D} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &F^{I,S} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &P^{I,S} \to \text{Boolean},\ \text{empty}=\text{False}\\[4pt]
  &\triangleright \textbf{Initializations}\\
  &F_{i,s} = \text{False},\quad P_{i,s} = \text{False},\quad G_{s,d} \to \langle\text{user-specified}\rangle\\
  &F_{0,n} = \text{True},\quad P_{0,n} = \text{True}\\[4pt]
  &\triangleright \textbf{Extended Einsum — Top-Down}\\
  &T_{i,d} = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee \text{OR}(\cup)\\
  &F_{i+1,d} = T_{i,d} \cdot \neg P_{i,d} :: \textstyle\bigwedge \text{AND}(\cap)\\
  &P_{i+1,d} = P_{i,d} \cdot F_{i+1,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

  In the bottom-up form, for every unvisited vertex $d$ we ask: "Is there some vertex $s$ in the
  frontier such that $(s,d)$ exists?" The tensors and initializations are the same:

  $$
  \begin{aligned}
  &\triangleright \textbf{Extended Einsum — Bottom-Up}\\
  &T_{i,s,d} = G_{s,d} \cdot \neg P_{i,d} :: \textstyle\bigwedge \text{AND}(\cap)\\
  &F_{i+1,d} = T_{i,s,d} \cdot F_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee \text{OR}(\cup)\\
  &P_{i+1,d} = P_{i,d} \cdot F_{i+1,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

  The first expression restricts the graph to edges whose destination $d$ has not yet been
  visited, which can be viewed as creating a subgraph over the unvisited vertices. The second
  checks, for each such vertex, whether any of its parents lie in the current frontier. Although
  this uses the same tensors as the top-down case, the key difference is that we first restrict to
  unvisited vertices (before reduction), which changes the direction of the computation.

  ---

  **Bottom-Up.**
  In the bottom-up traversal, instead of expanding outward from the frontier, we iterate over Not
  Visited vertices and check whether any of their parents are in the current frontier. This
  reverses the direction of exploration and can significantly reduce edge examinations when the
  frontier becomes large.

  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &F^{I,\, S \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{Tree}^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{CandParents}^{I,S,D} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{InF}^{I,S,D} \to \text{Boolean},\ \text{empty}=\text{False}\\[4pt]
  &\triangleright \textbf{Initializations}\\
  &F_{i,s} = \text{False},\quad \mathit{Tree}_{i,s,d} = \text{False},\quad G_{s,d} \to \langle\text{user-specified}\rangle\\
  &\mathit{CandParents}_{i,s,d} = \text{False},\quad \mathit{InF}_{i,s,d} = \text{False}\\
  &F_{0,n} = \text{True},\quad \mathit{Tree}_{0,n,n} = \text{True}\\[4pt]
  &\triangleright \textbf{Extended Einsum — Bottom-Up}\\
  &\mathit{Visited}_{i,c} = \mathit{Tree}_{i,p,c} :: \textstyle\bigvee_p \text{OR}(\cup)\\
  &NV_{i,c} = \neg \mathit{Visited}_{i,c}\\
  &\mathit{CandParents}_{i,s,d} = G_{s,d} \cdot NV_{i,d} :: \textstyle\bigwedge_d \text{AND}(\cap)\\
  &\mathit{InF}_{i,s,d} = \mathit{CandParents}_{i,s,d} \cdot F_{i,s} :: \textstyle\bigwedge_s \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{InF}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{Tree}_{i+1,s,d} = \mathit{Temp}_{i,s,d} \cdot \mathit{Tree}_{i,s,d}
    :: \textstyle\bigwedge_d \text{OR}(\cup)\\
  &F_{i+1,d} = \mathit{InF}_{i,s,d} :: \textstyle\bigvee_s \text{OR}(\cup)\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

  *Step 1 — Compute Not Visited vertices (NV).* As in the top-down case, we derive the Not Visited
  set directly from the BFS tree.

  - Graph meaning: Find vertices that have not yet been discovered.
  - Einsum meaning: Reduce the $\mathit{Tree}$ tensor over the parent index using OR, then negate
    the result.

  *Step 2 — Find candidate parents of Not Visited vertices (CandParents).* Instead of expanding
  from the frontier, we now examine each Not Visited vertex $d$ and find the vertices $s$ that are
  parents to it.

  - Graph meaning: For each Not Visited vertex, identify all of its potential parents. In the
    top-down case, edges are explored with frontier vertices acting as sources, discovering their
    outgoing neighbors. Here the perspective is reversed: for each Not Visited vertex $d$, we
    examine its incoming edges $(s,d)$ to determine whether any adjacent vertex $s$ could serve as
    its parent.
  - Einsum meaning: Elementwise AND between the graph tensor and the Not Visited mask;
    $\mathit{CandParents}_{i,s,d}$ is True exactly when the edge $(s,d)$ exists and $d$ is
    currently Not Visited.

  *Step 3 — Check whether any of those parents are in the frontier (InF).* For each Not Visited
  vertex $d$, we now check whether any of its parent vertices $s$ are currently active in the
  frontier.

  - Graph meaning: A Not Visited vertex becomes discovered if at least one of its parents is in
    the frontier.
  - Einsum meaning: Intersect $\mathit{CandParents}$ with the frontier tensor $F$ on rank variable
    $s$, keeping only edges where the source is in the frontier.

  *Step 4 — Select one parent per newly discovered vertex (Temp).* If multiple frontier vertices
  are adjacent to the same Not Visited vertex, we must choose exactly one as its parent. A common
  optimization is early exit, where a vertex can stop examining its parents as soon as it finds
  one in the frontier. Thus, the only constraint on `pick-parent` is that it must select at least
  one parent from the frontier if any exist, but it can be implemented in a way that allows for
  early exit. Here, the first parent found in the frontier is kept, which allows early exit;
  any valid parent would produce a correct BFS tree.

  - Graph meaning: Choose a single parent for each newly discovered vertex.
  - Einsum meaning: Use the populate action with the coordinate operator `pick-parent` to enforce
    one parent per child.

  *Step 5 — Update the BFS tree.* Merge the newly selected parent-child edges into the existing
  tree.

  - Graph meaning: Record newly discovered vertices in the BFS tree.
  - Einsum meaning: Elementwise OR between previous $\mathit{Tree}$ and $\mathit{Temp}$.

  *Step 6 — Update the frontier.* The next frontier consists of vertices that were newly discovered
  in this iteration. These are exactly the $d$ vertices for which at least one entry in
  $\mathit{InF}_{i,s,d}$ was True.

  - Graph meaning: The new frontier contains vertices that were just discovered.
  - Einsum meaning: Reduce $\mathit{InF}$ over the parent dimension using OR. Note that we can
    early-exit here as well: OR is a bear-trap function, meaning that it can return True as soon as
    it encounters the first True entry. Thus, we can stop checking parents for a child as soon as
    we find one in the frontier.

  *Step 7 — Termination condition.* The algorithm stops when no new vertices are added to the
  frontier, i.e., when the frontier tensor contains no True entries (equivalently, the frontier is
  empty).

  **Comparing top-down and bottom-up.**
  Both traversals operate on the same underlying tensors, including the frontier and the
  $\mathit{Tree}$ tensor. In both cases, the goal is to identify edges $(s,d)$ such that $s$ lies in
  the current frontier and $d$ does not yet have a parent. Conceptually:

  $$\text{Top-down:}\quad \mathit{CandTree}_{i,s,d} = G_{s,d} \cdot F_{i,s} \cdot NV_{i,d},$$

  $$\text{Bottom-up:}\quad \mathit{CandTree}_{i,s,d} = G_{s,d} \cdot NV_{i,d} \cdot F_{i,s}.$$

  Although these expressions look similar, the difference lies in how they are evaluated:

  - **Traversal order:** top-down evaluates edges as $s \to d$, while bottom-up evaluates them as
    $d \to s$.
  - **Masking:** top-down applies the frontier mask on $s$ first, while bottom-up applies the Not
    Visited mask on $d$ first.
  - **Reduction:** both formulations reduce over $s$ to determine whether a valid parent exists, but
    this reduction occurs after different masking steps.

  From the EDGE perspective, the two traversal strategies are not fundamentally different. They
  correspond to different evaluation orders of the same underlying computation. This is why
  bottom-up BFS can be derived from top-down BFS through algebraic reorganization and changes in
  traversal order.

  ---

  **Hybrid (Direction-Optimizing).**
  The hybrid algorithm maintains an explicit traversal-mode tensor, $\mathit{TopDown}_i$, that
  records whether iteration $i$ executes the Top-Down or Bottom-Up macro. The switching conditions
  are computed from frontier work estimates and are used inside the selected macro to determine the
  traversal mode for the next iteration.

  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &F^{I,\, S \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{Tree}^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{CandParents}^{I,S,D} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{InF}^{I,S,D} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &\mathit{TopDown}^I \to \text{Boolean},\ \text{empty}=\text{False}\\[4pt]
  &\triangleright \textbf{Initializations}\\
  &F_{i,s} = \text{False},\quad \mathit{Tree}_{i,s,d} = \text{False},\quad G_{s,d} \to \langle\text{user-specified}\rangle\\
  &\mathit{CandParents}_{i,s,d} = \text{False},\quad \mathit{InF}_{i,s,d} = \text{False}\\
  &F_{0,n} = \text{True},\quad \mathit{Tree}_{0,n,n} = \text{True},\quad \mathit{TopDown}_0 = \text{True}\\[4pt]
  &\triangleright \textbf{Extended Einsum — Hybrid}\\
  &\mathit{Visited}_{i,c} = \mathit{Tree}_{i,p,c} :: \textstyle\bigvee \text{OR}(\cup)\\
  &NV_{i,c} = \neg \mathit{Visited}_{i,c}\\
  &\begin{pmatrix}\mathit{Tree}_{i+1,s,d},\, F_{i+1,d},\, \mathit{TopDown}_{i+1}\end{pmatrix}
    = \begin{cases}
        \text{TOP-DOWN}(G_{s,d}, F_{i,s}, \mathit{Tree}_{i,s,d}, NV_{i,c}, \mathit{MF}_i, \mathit{MU}_i) & \text{if } \mathit{TopDown}_i \equiv \text{True}\\
        \text{BOTTOM-UP}(G_{s,d}, F_{i,s}, \mathit{Tree}_{i,s,d}, NV_{i,c}, \mathit{NF}_i) & \text{if } \mathit{TopDown}_i \equiv \text{False}
      \end{cases}\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

  A macro in EDGE is a named, parameterized Einsum template. Invoking a macro expands it into one or
  more Einsums via lexical substitution of its tensor and rank-variable expression parameters.
  Inside a macro template, the formal input and output tensors are written with a `T` prefix to
  distinguish them from the actual tensors at the call site.

  $$
  \begin{aligned}
  &\triangleright \textbf{MACRO}\ \text{TOP-DOWN}(\mathit{TG}_{s,d}, \mathit{TF}_{i,s}, \mathit{TTree}_{i,s,d}, \mathit{TNV}_{i,c}, \mathit{TMF}_i, \mathit{TMU}_i)\\
  &\qquad \mapsto \mathit{TTree}_{i+1,s,d}, \mathit{TF}_{i+1,d}, \mathit{TTopDown}_{i+1}\\
  &\mathit{Nei}_{i,d} = \mathit{TG}_{s,d} \cdot \mathit{TF}_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee \text{OR}(\cup)\\
  &\mathit{NeiNV}_{i,d} = \mathit{Nei}_{i,d} \cdot \mathit{TNV}_{i,d} :: \textstyle\bigwedge \text{AND}(\cap)\\
  &\mathit{CandTree}_{i,s,d} = (\mathit{TG}_{s,d} \cdot \mathit{TF}_{i,s})_{i,s,d} \cdot \mathit{NeiNV}_{i,d}
    :: \textstyle\bigwedge \text{AND}(\cap)\ \bigwedge \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{CandTree}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{TTree}_{i+1,s,d} = \mathit{TTree}_{i,s,d} \cdot \mathit{Temp}_{i,s,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &\mathit{TF}_{i+1,d} = \mathit{NeiNV}_{i,d}\\
  &\mathit{TMF}_i = \mathit{TG}_{s,d} \cdot \mathit{TF}_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee +(\cup)\\
  &\mathit{TMU}_i = \mathit{TG}_{s,d} \cdot \mathit{TNV}_{i,d} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee +(\cup)\\
  &\mathit{TB}_i = \mathit{TMF}_i \cdot (\mathit{TMU}_i / \alpha) :: \textstyle\bigwedge >(\cap)\\
  &\mathit{TTopDown}_{i+1} = \neg \mathit{TB}_i
  \end{aligned}
  $$

  $$
  \begin{aligned}
  &\triangleright \textbf{MACRO}\ \text{BOTTOM-UP}(\mathit{TG}_{s,d}, \mathit{TF}_{i,s}, \mathit{TTree}_{i,s,d}, \mathit{TNV}_{i,c}, \mathit{TNF}_i)\\
  &\qquad \mapsto \mathit{TTree}_{i+1,s,d}, \mathit{TF}_{i+1,d}, \mathit{TTopDown}_{i+1}\\
  &\mathit{CandParents}_{i,s,d} = \mathit{TG}_{s,d} \cdot \mathit{TNV}_{i,d} :: \textstyle\bigwedge \text{AND}(\cap)\\
  &\mathit{InF}_{i,s,d} = \mathit{CandParents}_{i,s,d} \cdot \mathit{TF}_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{InF}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{TTree}_{i+1,s,d} = \mathit{Temp}_{i,s,d} \cdot \mathit{TTree}_{i,s,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &\mathit{TF}_{i+1,d} = \mathit{InF}_{i,s,d} :: \textstyle\bigvee \text{OR}(\cup)\\
  &\mathit{TNF}_i = \mathit{TF}_{i,s} :: \textstyle\bigvee +(\cup)\\
  &\mathit{BT}_i = \mathit{TNF}_i \cdot (\lvert V\rvert / \beta) :: \textstyle\bigwedge <(\cap)\\
  &\mathit{TTopDown}_{i+1} = \mathit{BT}_i
  \end{aligned}
  $$

  *Step 1 — Identify Not Visited vertices.* As in both traversal strategies, we first determine which
  vertices do not yet have parents recorded in the BFS tree.

  *Step 2 — Record the current traversal mode.* If $\mathit{TopDown}_i$ is True, the algorithm executes
  the Top-Down macro; if False, the Bottom-Up macro. Initially, the traversal begins in Top-Down mode.

  *Step 3 — Select the macro for this iteration.* The selected macro computes three outputs
  simultaneously: the updated BFS tree, the next frontier, and the traversal mode for the next
  iteration.

  *Step 4 — Top-Down macro.* The first part is unchanged from the top-down formulation: gather
  neighbors, filter them by the Not Visited mask, record candidate parent-child edges, select one
  parent, and update the tree and frontier.

  *Step 5 — Top-Down switching condition.* At the end of the macro, we estimate whether the next
  iteration should remain top-down or switch to bottom-up, using two work estimates, $\mathit{TMF}_i$
  (the sum of degrees of vertices in the frontier) and $\mathit{TMU}_i$ (the sum of degrees of Not
  Visited vertices). If $\mathit{TB}_i$ is True, the macro sets the next traversal mode to Bottom-Up.
  Otherwise, the next iteration stays Top-Down.

  *Step 6 — Bottom-Up macro.* As before, it finds candidate parents for Not Visited vertices, checks
  whether any such parent is in the frontier, selects one parent, updates the tree, and reduces to form
  the next frontier.

  *Step 7 — Bottom-Up switching condition.* At the end of the macro, the algorithm checks whether the
  frontier has become small enough to switch back to top-down, using the frontier-size estimate
  $\mathit{TNF}_i$. If $\mathit{BT}_i$ is True, the macro sets the next traversal mode to Top-Down.
  Otherwise, the next iteration stays Bottom-Up.

  *Step 8 — Termination.* As in both individual strategies, the hybrid algorithm terminates when the
  newly computed frontier is empty.

  The traversal mode for iteration $i+1$ depends both on the current mode and on which switching
  condition is computed inside the active macro:

  | $\mathit{TopDown}_i$ | Cond. | Val. | $\mathit{TopDown}_{i+1}$ | Meaning |
  |---|---|---|---|---|
  | True | $\mathit{TB}_i$ | False | True | stay Top-Down |
  | True | $\mathit{TB}_i$ | True | False | switch to Bottom-Up |
  | False | $\mathit{BT}_i$ | False | False | stay Bottom-Up |
  | False | $\mathit{BT}_i$ | True | True | switch to Top-Down |

  ---

  **Other Switching Heuristics.**

  All switching heuristics address the same question: given the current frontier, which traversal
  direction will be more efficient in the next iteration? Top-down traversal is efficient when the
  frontier is small, since only a small number of outgoing edges are explored. Bottom-up traversal
  becomes advantageous when the frontier is large and the number of visited vertices is high, as it
  checks incoming edges from a smaller set of unvisited vertices. Each framework designs its heuristic
  to approximate the relative cost of these two strategies while minimizing the overhead of computing
  the decision itself.

  *Gunrock* (Wang et al., 2017) modifies the switching heuristic to better suit parallel execution on
  GPUs. Instead of computing exact edge-based quantities, it uses simple approximations based on global
  graph statistics, where $n_f$ is the number of vertices in the current frontier, $n_u$ is the number
  of unvisited vertices, $m = \lvert E\rvert$ and $n = \lvert V\rvert$:

  $$m_f = \frac{n_f \cdot m}{n}, \qquad m_u = \frac{n_u \cdot n}{n - n_u}.$$

  It switches to bottom-up when $m_f > m_u \cdot do_a$ and back to top-down when $m_f < m_u \cdot do_b$:

  $$
  \begin{aligned}
  &\triangleright \textbf{Initializations}\\
  &N = \lvert V\rvert,\quad M = \lvert E\rvert\\
  &do_a \to \langle\text{user-specified threshold}\rangle,\quad do_b \to \langle\text{user-specified threshold}\rangle\\
  &\mathit{TopDown}_0 = \text{True}\\[4pt]
  &\triangleright \textbf{Extended Einsums}\\
  &\mathit{NF}_i = F_{i,s} :: \textstyle\bigvee +(\cup)\\
  &\mathit{NU}_i = NV_{i,s} :: \textstyle\bigvee +(\cup)\\
  &\mathit{MF}_i = \mathit{NF}_i \cdot (M / N) :: \textstyle\bigwedge \times(\cap)\\
  &\mathit{MU}_i = \mathit{NU}_i \cdot \tfrac{N}{N - \mathit{NU}_i} :: \textstyle\bigwedge \times(\cap)\\
  &\mathit{TB}_i = \mathit{MF}_i \cdot (\mathit{MU}_i \cdot do_a) :: \textstyle\bigwedge >(\cap)\\
  &\mathit{BT}_i = \mathit{MF}_i \cdot (\mathit{MU}_i \cdot do_b) :: \textstyle\bigwedge <(\cap)\\
  &\begin{pmatrix}\mathit{Tree}_{i+1,s,d},\, F_{i+1,d},\, \mathit{TopDown}_{i+1}\end{pmatrix}
    = \begin{cases}
        \text{TOP-DOWN}(\cdots) & \text{if } \mathit{TopDown}_i \equiv \text{True}\\
        \text{BOTTOM-UP}(\cdots) & \text{if } \mathit{TopDown}_i \equiv \text{False}
      \end{cases}\\
  &\mathit{TopDown}_{i+1} = \begin{cases}
        \neg \mathit{TB}_i & \text{if } \mathit{TopDown}_i \equiv \text{True}\\
        \mathit{BT}_i & \text{if } \mathit{TopDown}_i \equiv \text{False}
      \end{cases}
  \end{aligned}
  $$

  Compared to Beamer's formulation, Gunrock replaces exact edge-based counts with simple approximations,
  avoiding additional graph traversals, trading accuracy for efficiency while still capturing the
  relative cost of push and pull phases.

  *Ligra* (Shun & Blelloch, 2013) provides a generalized abstraction for switching through its EDGEMAP
  procedure, used across multiple graph algorithms. It uses the dense (bottom-up) traversal when
  $\lvert U\rvert + \sum_{u \in U} \deg(u) > \text{threshold}$, where $U$ is the set of active vertices
  (e.g., the frontier) and $\deg(u)$ is the out-degree of $u$; otherwise, it uses the sparse (top-down)
  traversal:

  $$
  \begin{aligned}
  &\triangleright \textbf{Initializations}\\
  &\text{threshold} \to \langle\text{user-specified threshold}\rangle\\[4pt]
  &\triangleright \textbf{Extended Einsums}\\
  &\mathit{NF}_i = F_{i,s} :: \textstyle\bigvee +(\cup)\\
  &\mathit{MF}_i = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee +(\cup)\\
  &\mathit{TB}_i = (\mathit{NF}_i + \mathit{MF}_i) \cdot \text{threshold} :: \textstyle\bigwedge >(\cap)\\
  &\begin{pmatrix}\mathit{Tree}_{i+1,s,d},\, F_{i+1,d}\end{pmatrix}
    = \begin{cases}
        \text{BOTTOM-UP}(\cdots) & \text{if } \mathit{TB}_i \equiv \text{True}\\
        \text{TOP-DOWN}(\cdots) & \text{otherwise}
      \end{cases}
  \end{aligned}
  $$

  The cost of a top-down step depends not only on the number of active vertices but also on the number
  of edges they induce. By combining both quantities, Ligra captures the total work of a sparse traversal,
  and a single threshold keeps the decision simple and general across different graph algorithms.

  *XBFS* (Yang et al., 2024) extends the approach with multiple traversal strategies: in addition to
  bottom-up traversal, it distinguishes between different top-down execution modes. Bottom-up is selected
  when $\lvert E_f\rvert / \lvert E\rvert > \alpha$, where $\lvert E_f\rvert$ is the number of outgoing
  edges from the frontier and $\alpha$ is a tunable parameter. Otherwise XBFS remains in top-down mode and
  selects among different push-based execution strategies:

  $$
  \begin{aligned}
  &\triangleright \textbf{Initializations}\\
  &M = \lvert E\rvert,\quad \alpha \to \langle\text{user-specified threshold}\rangle\\[4pt]
  &\triangleright \textbf{Extended Einsums}\\
  &\mathit{MF}_i = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee +(\cup)\\
  &\mathit{BU}_i = \mathit{MF}_i \cdot (M \cdot \alpha) :: \textstyle\bigwedge >(\cap)\\
  &\begin{pmatrix}\mathit{Tree}_{i+1,s,d},\, F_{i+1,d}\end{pmatrix}
    = \begin{cases}
        \text{BOTTOM-UP}(\cdots) & \text{if } \mathit{BU}_i \equiv \text{True}\\
        \text{TOP-DOWN-VARIANT}(\cdots) & \text{otherwise}
      \end{cases}
  \end{aligned}
  $$

  Instead of using absolute counts, XBFS compares the edges coming from the frontier to the total number
  of edges in the graph, which makes the decision more robust across graphs of different sizes.

  Across Ligra, Gunrock, and XBFS, a common quantity is the total number of outgoing edges from the
  frontier vertices:

  $$\mathit{MF}_i = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee +(\cup).$$

  Each framework uses this quantity differently: Ligra compares it against a fixed threshold, Gunrock
  uses approximations based on global graph statistics, and XBFS incorporates it into a multi-stage
  decision process. The differences between these methods are not from new computations, but from how
  the computed quantities are used. More precise estimates can lead to better switching decisions, but
  may introduce additional computational cost, so the effectiveness of a heuristic depends both on how
  well it models the underlying work and on how efficiently that model can be evaluated in each iteration.

  ---

  **Compact Formulation.**
  The expressions above follow the step-by-step construction of BFS and introduce intermediate tensors to
  make each stage explicit. While this improves intuition, it also results in redundant computations and
  additional tensors that are not strictly necessary. We can avoid repeatedly computing neighbor sets and
  directly express the conditions required for discovering new vertices and assigning parents. Both
  traversals then compute the same set of candidate parent-child edges, with different evaluation orders
  and masking strategies. Each compact cascade uses the tensors $G$, $F$, $\mathit{Tree}$ and
  $\mathit{InF}^{I,S,D} \to \text{Boolean},\ \text{empty}=\text{False}$, with the usual initializations
  and $\mathit{InF}_{i,s,d} = \text{False}$.

  $$
  \begin{aligned}
  &\triangleright \textbf{Extended Einsum — Compact Top-Down}\\
  &\mathit{Visited}_{i,c} = \mathit{Tree}_{i,p,c} :: \textstyle\bigvee \text{OR}(\cup)\\
  &NV_{i,c} = \neg \mathit{Visited}_{i,c}\\
  &\mathit{InF}_{i,s,d} = (G_{s,d} \cdot^1 F_{i,s})_{i,s,d} \cdot^2 NV_{i,d}
    :: \textstyle\bigwedge^1 \text{AND}(\cap)\ \bigwedge^2 \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{InF}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{Tree}_{i+1,s,d} = \mathit{Tree}_{i,s,d} \cdot \mathit{Temp}_{i,s,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &F_{i+1,d} = \mathit{InF}_{i,s,d} :: \textstyle\bigvee \text{OR}(\cup)\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

  $$
  \begin{aligned}
  &\triangleright \textbf{Extended Einsum — Compact Bottom-Up}\\
  &\mathit{Visited}_{i,c} = \mathit{Tree}_{i,p,c} :: \textstyle\bigvee \text{OR}(\cup)\\
  &NV_{i,c} = \neg \mathit{Visited}_{i,c}\\
  &\mathit{InF}_{i,s,d} = (G_{s,d} \cdot^1 NV_{i,d})_{i,s,d} \cdot^2 F_{i,s}
    :: \textstyle\bigwedge^1 \text{AND}(\cap)\ \bigwedge^2 \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{InF}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{Tree}_{i+1,s,d} = \mathit{Temp}_{i,s,d} \cdot \mathit{Tree}_{i,s,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &F_{i+1,d} = \mathit{InF}_{i,s,d} :: \textstyle\bigvee \text{OR}(\cup)\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

  The compact hybrid adds $\mathit{TopDown}^I \to \text{Boolean},\ \text{empty}=\text{False}$ with
  $\mathit{TopDown}_0 = \text{True}$:

  $$
  \begin{aligned}
  &\triangleright \textbf{Extended Einsum — Compact Hybrid}\\
  &\mathit{Visited}_{i,c} = \mathit{Tree}_{i,p,c} :: \textstyle\bigvee \text{OR}(\cup)\\
  &NV_{i,c} = \neg \mathit{Visited}_{i,c}\\
  &\begin{pmatrix}\mathit{Tree}_{i+1,s,d},\, F_{i+1,d},\, \mathit{TopDown}_{i+1}\end{pmatrix}
    = \begin{cases}
        \text{TOP-DOWN}(G_{s,d}, F_{i,s}, \mathit{Tree}_{i,s,d}, NV_{i,c}, \mathit{MF}_i, \mathit{MU}_i) & \text{if } \mathit{TopDown}_i \equiv \text{True}\\
        \text{BOTTOM-UP}(G_{s,d}, F_{i,s}, \mathit{Tree}_{i,s,d}, NV_{i,c}, \mathit{NF}_i) & \text{if } \mathit{TopDown}_i \equiv \text{False}
      \end{cases}\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$

  $$
  \begin{aligned}
  &\triangleright \textbf{MACRO}\ \text{TOP-DOWN}(\mathit{TG}_{s,d}, \mathit{TF}_{i,s}, \mathit{TTree}_{i,s,d}, \mathit{TNV}_{i,c}, \mathit{TMF}_i, \mathit{TMU}_i)\\
  &\qquad \mapsto \mathit{TTree}_{i+1,s,d}, \mathit{TF}_{i+1,d}, \mathit{TTopDown}_{i+1}\\
  &\mathit{InF}_{i,s,d} = (\mathit{TG}_{s,d} \cdot^1 \mathit{TF}_{i,s})_{i,s,d} \cdot^2 \mathit{TNV}_{i,d}
    :: \textstyle\bigwedge^1 \text{AND}(\cap)\ \bigwedge^2 \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{InF}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{TTree}_{i+1,s,d} = \mathit{TTree}_{i,s,d} \cdot \mathit{Temp}_{i,s,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &\mathit{TF}_{i+1,d} = \mathit{InF}_{i,s,d} :: \textstyle\bigvee \text{OR}(\cup)\\
  &\mathit{TMF}_i = \mathit{TG}_{s,d} \cdot \mathit{TF}_{i,s} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee +(\cup)\\
  &\mathit{TMU}_i = \mathit{TG}_{s,d} \cdot \mathit{TNV}_{i,d} :: \textstyle\bigwedge \text{AND}(\cap)\ \bigvee +(\cup)\\
  &\mathit{TB}_i = \mathit{TMF}_i \cdot (\mathit{TMU}_i / \alpha) :: \textstyle\bigwedge >(\cap)\\
  &\mathit{TTopDown}_{i+1} = \neg \mathit{TB}_i
  \end{aligned}
  $$

  $$
  \begin{aligned}
  &\triangleright \textbf{MACRO}\ \text{BOTTOM-UP}(\mathit{TG}_{s,d}, \mathit{TF}_{i,s}, \mathit{TTree}_{i,s,d}, \mathit{TNV}_{i,c}, \mathit{TNF}_i)\\
  &\qquad \mapsto \mathit{TTree}_{i+1,s,d}, \mathit{TF}_{i+1,d}, \mathit{TTopDown}_{i+1}\\
  &\mathit{InF}_{i,s,d} = (\mathit{TG}_{s,d} \cdot^1 \mathit{TNV}_{i,d})_{i,s,d} \cdot^2 \mathit{TF}_{i,s}
    :: \textstyle\bigwedge^1 \text{AND}(\cap)\ \bigwedge^2 \text{AND}(\cap)\\
  &\mathit{Temp}_{i,s^*,d} = \mathit{InF}_{i,s,d} \lll_{s^*} \mathbf{1}(\text{pick-parent})\\
  &\mathit{TTree}_{i+1,s,d} = \mathit{Temp}_{i,s,d} \cdot \mathit{TTree}_{i,s,d} :: \textstyle\bigwedge \text{OR}(\cup)\\
  &\mathit{TF}_{i+1,d} = \mathit{InF}_{i,s,d} :: \textstyle\bigvee \text{OR}(\cup)\\
  &\mathit{TNF}_i = \mathit{TF}_{i,s} :: \textstyle\bigvee +(\cup)\\
  &\mathit{BT}_i = \mathit{TNF}_i \cdot (\lvert V\rvert / \beta) :: \textstyle\bigwedge <(\cap)\\
  &\mathit{TTopDown}_{i+1} = \mathit{BT}_i
  \end{aligned}
  $$

  Both macros compute the same tensor $\mathit{InF}_{i,s,d}$: the edges that can extend the BFS tree at
  iteration $i$, meaning the edge $(s,d)$ exists, $s$ is in the frontier, and $d$ is not yet visited. The
  two differ only in where the parentheses fall — top-down applies $F_{i,s}$ first, bottom-up applies
  $NV_{i,d}$ first. This makes it clear that even when recording parents, the difference between top-down
  and bottom-up boils down to an algebraic manipulation when collecting neighbors.

implementation_notes: |
  The advance step (gathering neighbors, `Nei`) is a sparse Boolean matrix-vector product
  over the graph tensor. The filter (`NeiNV`) and tree-update (`Tree`) steps are elementwise
  merges over the destination rank.

  In top-down mode, work per level is proportional to the number of edges leaving the
  frontier. In bottom-up mode, work per level is proportional to edges entering unvisited
  vertices — more efficient when the frontier is large relative to the unvisited set, because
  each unvisited vertex can exit early once it finds one frontier parent.

  Keeping $F$ and $\mathit{Tree}$ as sparse tensors (present-only) means each level touches
  work proportional to active vertices and their edges, not to $\lvert V\rvert$.

  The EDGE formulation captures the full computation for clarity, while practical implementations
  can apply standard optimizations such as double-buffering, sparsity-aware storage, and in-place
  updates. Using the TeAAL pyramid of abstractions, EDGE specifies the algorithmic space; mapping
  choices (traversal order, parallelism, data layout), the format space, and the implementation
  space are separate concerns.

complexity_costs: |
  In top-down mode each vertex enters the frontier exactly once and each edge is examined
  at most once, giving $O(\lvert V\rvert + \lvert E\rvert)$ total work. The same bound holds for
  bottom-up, but with potentially far fewer edge examinations in practice (early-exit in the
  bottom-up phase). The number of levels is the BFS diameter of the source.

related_notes: |
  The basic (top-down-only) form of this cascade is the depth-tracking BFS on this site.
  Replacing the Boolean edge weights with integer weights and the AND/OR operators with +/min
  recovers Bellman-Ford (all vertices re-relax each level rather than being filtered by a
  visited mask).

  **References.**

  - Scott Beamer, Krste Asanović, and David Patterson. 2012. Direction-Optimizing Breadth-First
    Search. In *SC '12*. IEEE, 12:1–12:10. [doi:10.1109/SC.2012.50](https://doi.org/10.1109/SC.2012.50)
  - Nandeeka Nayak, Toluwanimi O. Odemuyiwa, Shubham Ugare, Christopher Fletcher, Michael Pellauer,
    and Joel Emer. 2023. TeAAL: A Declarative Framework for Modeling Sparse Tensor Accelerators. In
    *MICRO-56*. ACM, 1255–1270. [doi:10.1145/3613424.3623791](https://doi.org/10.1145/3613424.3623791)
  - Toluwanimi O. Odemuyiwa, Serban D. Porumbescu, Joel S. Emer, and John D. Owens. 2026. The EDGE
    Language: Extended General Einsums for Graph Algorithms.
    [arXiv:2404.11591v2](https://arxiv.org/abs/2404.11591v2)
  - Toluwanimi O. Odemuyiwa, Serban D. Porumbescu, Muhammad Osama, Joel S. Emer, and John D. Owens.
    2026. The Einsum-Enabled Design Space for Graph Algorithms: A BFS Case Study.
    [arXiv:2607.17106](https://arxiv.org/abs/2607.17106)
  - Julian Shun and Guy E. Blelloch. 2013. Ligra: A Lightweight Graph Processing Framework for Shared
    Memory. In *PPoPP*. 135–146. [doi:10.1145/2442516.2442530](https://doi.org/10.1145/2442516.2442530)
  - Yangzihao Wang, Yuechao Pan, Andrew Davidson, Yuduo Wu, Carl Yang, Leyuan Wang, Muhammad Osama,
    Chenshan Yuan, Weitang Liu, Andy T. Riffel, and John D. Owens. 2017. Gunrock: GPU Graph Analytics.
    *ACM Transactions on Parallel Computing* 4, 1, 3:1–3:49.
    [doi:10.1145/3108140](https://doi.org/10.1145/3108140)
  - Hao Yang, Haicheng Lu, Nadeem S. Sattar, Hang Liu, and Feifei Wang. 2024. Establish the Basis for
    Breadth-First Search on Frontier System: XBFS on AMD GPUs. In *SC-W*. 650–658.
    [doi:10.1109/SCW63240.2024.00090](https://doi.org/10.1109/SCW63240.2024.00090)
---
