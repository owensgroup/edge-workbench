---
title: Breadth-First Search (Depths and Parents)
authors: [Sanjana Mali]
summary: CLRS breadth-first search, computing each vertex's distance d and a parent π, run one level per generation as an extended Einsum cascade in which the parent is a free choice.
tags: [bfs, traversal, frontier, bfs-tree, graphs]
ranks:
  I: generational
  S: vertex
  D: vertex
status_intro: |
  This page follows BFS as Cormen, Leiserson, Rivest and Stein give it
  (Introduction to Algorithms, §22.2): every vertex starts white with
  $d = \infty$ and no parent; the source is discovered at $d = 0$; each white
  neighbour $v$ of a discovered vertex $u$ is discovered with $v.d = u.d + 1$
  and $v.\pi = u$. CLRS processes vertices through a queue. Here a whole level
  is processed in one generation, so the queue order disappears and the
  parent becomes what CLRS says it is: any neighbour one level up, depending
  on adjacency order. The cascade states that as a free choice.
problem_statement: |
  Given a graph $G$ on $\lvert V\rvert$ vertices and a source set $source$,
  compute for each reachable vertex $v$ its distance $d(v)$ in edges from the
  source, and a parent $\pi(v)$: a neighbour with $d(\pi(v)) = d(v) - 1$.
  Unreached vertices have no value. A stored value equal to a tensor's empty
  value is absent.

  - $G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert}$, the graph, `empty` $= 0$; an edge is $1$.
  - $F^{I,\, S \equiv \lvert V\rvert}$, the frontier: the depth of each vertex discovered at generation $i$, `empty` $= \infty$.
  - $T^{I,\, D \equiv \lvert V\rvert}$, candidate depths one hop beyond the frontier, `empty` $= \infty$.
  - $P^{I,\, D \equiv \lvert V\rvert}$, the vertices no longer white (gray), Boolean, `empty` $=$ False.
  - $ParentCand^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert}$, frontier edges into newly discovered vertices, `empty` $= 0$.
  - $NewParent^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert}$, the one edge chosen per new vertex, `empty` $= 0$.
  - $Parent^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert}$, the parent edges so far: $\pi$, `empty` $= 0$.
  - $Depth^{I,\, D \equiv \lvert V\rvert}$, the distances so far: $d$, `empty` $= \infty$, so a depth of $0$ is present.
working_example_part1: |
  CLRS Figure 22.3: the undirected graph on $r, s, t, u, v, w, x, y$, numbered
  $0$ to $7$, with edges r–s, r–v, s–w, w–t, w–x, t–x, t–u, x–u, x–y, u–y
  (each stored in both directions), and source $s$ (vertex $1$).

  The expected distances are $d$: r 1, s 0, t 2, u 3, v 2, w 1, x 2, y 3,
  that is $\lbrace 0:1,\ 1:0,\ 2:2,\ 3:3,\ 4:2,\ 5:1,\ 6:2,\ 7:3\rbrace$.
working_example_part2: |
  One generation per level:

  | $i$ | $F_{i+1}$ (newly discovered, depth) | parent choices |
  |----|----|----|
  | 0 | r:1, w:1 | r ← s, w ← s |
  | 1 | v:2, t:2, x:2 | v ← r, t ← w, x ← w |
  | 2 | u:3, y:3 | u ← t or x (free), y ← x |
  | 3 | (none) | stop |

  $u$ has two neighbours at depth $2$, so either is a valid parent; CLRS's
  figure shows $t$. Every run gives the same distances.
edge_expression_walkthrough: |
  **Advance.** $T_{i,d} = G_{s,d} \cdot F_{i,s} :: \bigwedge_s +(\cap)\ \bigvee_s \min(\cup)$.

  **Graph meaning:** Every frontier vertex offers each neighbour a distance one more than its own.

  **Einsum meaning:** Add $G_{s,d}$ to $F_{i,s}$ where both are present, and take the minimum over $s$.

  **Discover.** $F_{i+1,d} = T_{i,d} \cdot \neg P_{i,d} :: \bigwedge_d \leftarrow(\cap)$.

  **Graph meaning:** Only white vertices are discovered; they form the next frontier.

  **Einsum meaning:** Keep $T_{i,d}$ where $P_{i,d}$ is empty.

  **Parent candidates.** $ParentCand_{i,s,d} = (G_{s,d} \cdot^1 F_{i,s})_{i,s,d} \cdot^2 F_{i+1,d} :: \bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 \leftarrow(\cap)$.

  **Graph meaning:** An edge from the frontier into a newly discovered vertex could be its parent edge.

  **Einsum meaning:** Keep $G_{s,d}$ where $s$ is on the frontier and $d$ was just discovered.

  **Choose a parent.** $NewParent_{i,s^*,d} = ParentCand_{i,s,d} :: \lll_{s^*} \mathbb{1}(\text{pick-parent})$.

  **Graph meaning:** Each newly discovered vertex takes one of its candidate parents; which one is free.

  **Einsum meaning:** For each $d$, keep one $s$ of $ParentCand_{i,s,d}$.

  **Record parents.** $Parent_{i+1,s,d} = Parent_{i,s,d} \cdot NewParent_{i,s,d} :: \bigwedge_d \texttt{<<}(\cup)$.

  **Graph meaning:** The new parent edges join the BFS tree.

  **Einsum meaning:** Take $NewParent$ where present, else carry $Parent_{i}$ forward.

  **Colour gray.** $P_{i+1,d} = P_{i,d} \cdot F_{i+1,d} :: \bigwedge_d \text{OR}(\cup)$.

  **Graph meaning:** Newly discovered vertices are no longer white.

  **Einsum meaning:** OR $P_{i,d}$ with $F_{i+1,d}$ wherever either is present.

  **Record depths.** $Depth_{i+1,d} = Depth_{i,d} \cdot F_{i+1,d} :: \bigwedge_d \texttt{<<}(\cup)$.

  **Graph meaning:** Newly discovered vertices keep their distance.

  **Einsum meaning:** Take $F_{i+1,d}$ where present, else carry $Depth_{i,d}$ forward.

  **Stop.** $\diamond : \lVert F_{i+1} \rVert \equiv 0$.

  **Graph meaning:** Stop when a level discovers nothing.

  **Einsum meaning:** Halt when $F_{i+1}$ has no non-empty entries.
edge_expression: |
  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &G^{S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &F^{I,\, S \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=\infty\\
  &T^{I,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=\infty\\
  &P^{I,\, D \equiv \lvert V\rvert} \to \text{Boolean},\ \text{empty}=\text{False}\\
  &ParentCand^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &NewParent^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &Parent^{I,\, S \equiv \lvert V\rvert,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &Depth^{I,\, D \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=\infty\\[4pt]
  &\triangleright \textbf{Initialization}\\
  &F_{0,\ s\,:\,s \in source} = 0\\
  &P_{0,\ d\,:\,d \in source} = \text{True}\\
  &Depth_{0,\ d\,:\,d \in source} = 0\\[4pt]
  &\triangleright \textbf{Extended Einsum}\\
  &T_{i,d} = G_{s,d} \cdot F_{i,s} :: \textstyle\bigwedge_s +(\cap)\ \bigvee_s \min(\cup)\\
  &F_{i+1,d} = T_{i,d} \cdot \neg P_{i,d} :: \textstyle\bigwedge_d \leftarrow(\cap)\\
  &ParentCand_{i,s,d} = (G_{s,d} \cdot^1 F_{i,s})_{i,s,d} \cdot^2 F_{i+1,d} :: \textstyle\bigwedge^1 \leftarrow(\cap)\ \bigwedge^2 \leftarrow(\cap)\\
  &NewParent_{i,s^*,d} = ParentCand_{i,s,d} :: \lll_{s^*} \mathbb{1}(\text{pick-parent})\\
  &Parent_{i+1,s,d} = Parent_{i,s,d} \cdot NewParent_{i,s,d} :: \textstyle\bigwedge_d \texttt{<<}(\cup)\\
  &P_{i+1,d} = P_{i,d} \cdot F_{i+1,d} :: \textstyle\bigwedge_d \text{OR}(\cup)\\
  &Depth_{i+1,d} = Depth_{i,d} \cdot F_{i+1,d} :: \textstyle\bigwedge_d \texttt{<<}(\cup)\\
  &\diamond : \lVert F_{i+1} \rVert \equiv 0
  \end{aligned}
  $$
other_notes: |
  $E03$ uses take-left rather than AND: AND would read the source's depth $0$
  as False and drop the source's edges. $Depth$ is empty $= \infty$ for the same
  reason, so a depth of $0$ is present.
complexity_costs: |
  Each vertex enters the frontier once and each edge is examined once per level
  it touches, $O(\lvert V\rvert + \lvert E\rvert)$ work over all generations.
related_notes: |
  The depth-only form is the Breadth-First Search tutorial; direction-optimizing
  BFS adds a bottom-up step and a switching rule.
---
