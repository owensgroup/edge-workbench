---
title: Exact Cover (Knuth's Algorithm X)
authors: [Toluwanimi Odemuyiwa]
summary: Knuth's Algorithm X for solving the exact cover and generalized exact cover problems, expressed as a stamped-stack EDGE cascade that dynamically reconstructs the active matrix state from the current path.
tags: [exact-cover, algorithm-x, backtracking, np-complete, graphs]
status_intro: |
  This page presents Knuth's Algorithm X for solving the exact cover problem, expressed
  entirely within the EDGE tensor algebraic framework. Recursive backtracking is
  made explicit via a stack tensor \(S\) carrying *depth stamps*
  \(\sigma(d, r) = d\,\lvert R\rvert + r\), which encode both the search depth and
  the candidate row. At each step, the algorithm pops the deepest choice (the
  maximum stamp), truncates the active path to match the backtrack depth, updates
  the active rows and columns, and picks the next column to branch on using the
  minimum-degree heuristic. This formulation avoids storing the full reduced matrix
  at each stack level, as the active matrix state is dynamically reconstructed from
  the current path.
problem_statement: |
  Given a Boolean matrix \(A\) of \(\lvert R\rvert\) rows and \(\lvert C\rvert\) columns,
  find a subset of rows \(\mathrm{Sol} \subseteq R\) such that for each column \(c \in C\),
  exactly one row in \(\mathrm{Sol}\) covers \(c\) (contains a True value at that column).

  For generalized exact cover, the columns are partitioned into *primary columns* (must be covered exactly once) and *secondary columns* (must be covered at most once).

  The search state and current path are carried by the following tensors:

  - \(A^{R \equiv \lvert R\rvert,\, C \equiv \lvert C\rvert} \to \text{Boolean}\), `empty` \(=\) False, the static input matrix.
  - \(S^{I,\, R \equiv \lvert R\rvert} \to \text{integer}\), `empty` \(= -1\), the stack of alternative choices. An entry at row \(r\) holds its depth stamp \(\sigma\).
  - \(\mathrm{Path}^{I,\, R \equiv \lvert R\rvert} \to \text{integer}\), `empty` \(= -1\), the path of chosen rows, mapping each chosen row to its selection depth.
  - \(\mathrm{SelRow}^{I,\, R \equiv \lvert R\rvert} \to \text{Boolean}\), `empty` \(=\) False, the set of rows currently in the path.
  - \(\mathrm{CovCol}^{I,\, C \equiv \lvert C\rvert} \to \text{Boolean}\), `empty` \(=\) False, the set of columns covered by the path.
  - \(\mathrm{ActiveCol}^{I,\, C \equiv \lvert C\rvert} \to \text{Boolean}\), `empty` \(=\) False, the remaining uncovered columns.
  - \(\mathrm{ConflictRow}^{I,\, R \equiv \lvert R\rvert} \to \text{Boolean}\), `empty` \(=\) False, rows that overlap with columns already covered by the path.
  - \(\mathrm{ActiveRow}^{I,\, R \equiv \lvert R\rvert} \to \text{Boolean}\), `empty` \(=\) False, the remaining rows eligible for selection.
  - \(\mathrm{Success}^{I} \to \text{Boolean}\), `empty` \(=\) False, flag indicating whether all columns are covered.
  - \(\mathrm{Sol}^{I,\, R \equiv \lvert R\rvert} \to \text{Boolean}\), `empty` \(=\) False, the output exact cover solution.
  - \(\mathrm{RowCounts}^{I,\, C \equiv \lvert C\rvert} \to \text{integer}\), `empty` \(= 0\), the cover degree of each column.
  - \(\mathrm{PickedCol}^{I,\, C \equiv \lvert C\rvert} \to \text{Boolean}\), `empty` \(=\) False, the column chosen to cover next.
  - \(\mathrm{Candidates}^{I,\, R \equiv \lvert R\rvert} \to \text{Boolean}\), `empty` \(=\) False, the active rows covering the chosen column.
working_example_data: |
  {
    "_comment": [
      "Working Example 1, machine-readable. The prose above states the same",
      "universe; this is what a tool reads, so a visualiser runs THE EXAMPLE",
      "THIS PAGE DESCRIBES rather than an instance somebody typed separately.",
      "",
      "`kind: matrix` because the problem is stated as rows over columns, not",
      "as a capacitated graph. It is DRAWN as a bipartite graph -- rows on one",
      "side, columns on the other, an edge wherever the matrix has an entry --",
      "which for exact cover is the standard formulation rather than a",
      "reinterpretation: rows are sets, columns are elements, and a cover",
      "picks rows so that every column has degree exactly one.",
      "",
      "`expect` is the answer this page publishes, taken from the trace table",
      "above: generation 1 reaches Succ=T with Path {R3, R2}, and generation 3",
      "with Path {R3, R0, R1}. It is what makes the example an oracle rather",
      "than a picture -- a tool can run the cascade and check it against what",
      "the author stated, with nothing hardcoded on the tool's side."
    ],
    "kind": "matrix",
    "rows": 4,
    "columns": 3,
    "rowRank": "R",
    "colRank": "C",
    "tensor": "A",
    "matrix": [
      [
        1,
        0,
        0
      ],
      [
        0,
        1,
        0
      ],
      [
        1,
        1,
        0
      ],
      [
        0,
        0,
        1
      ]
    ],
    "scalars": {
      "RowCount": 4
    },
    "expect": {
      "generations": 4,
      "solutions": [
        [
          2,
          3
        ],
        [
          0,
          1,
          3
        ]
      ],
      "_note": "row sets, sorted; the depth stamp is sigma(d,r) = 4d + r"
    }
  }
working_example_part1: |
  ### Working Example 1: Three-Column Universe

  Take a universe of 3 columns, \(C = \lbrace C_0, C_1, C_2 \rbrace\), and 4 rows,
  \(R = \lbrace R_0, R_1, R_2, R_3 \rbrace\):

  $$\begin{aligned}
    R_0 &= \lbrace C_0 \rbrace \\
    R_1 &= \lbrace C_1 \rbrace \\
    R_2 &= \lbrace C_0, C_1 \rbrace \\
    R_3 &= \lbrace C_2 \rbrace
  \end{aligned}$$

  We use 0-indexed row IDs: \(R_0 \to 0\), \(R_1 \to 1\), \(R_2 \to 2\), \(R_3 \to 3\).
  The number of rows \(\lvert R\rvert = 4\), so the depth stamp is:
  \(\sigma(\mathrm{depth}, r) = 4 \cdot \mathrm{depth} + r\).

  At the start, the path is empty, and the initial stack pushes candidate choices for
  the column with the fewest covering active rows. Since \(C_2\) has only 1 row covering it
  (\(R_3\)), we branch on \(C_2\) first. We push \(R_3\) to the stack at depth 1:
  \(S_0 = \lbrace 3:7 \rbrace\) and \(\mathrm{Path}_0 = \lbrace \rbrace\).

  The table below traces the step-by-step execution.

  | \(i\) | Stack \(S_i\) | Peeked \(F_i\) | \(d^*_i\) | Path \(\mathrm{Path}_{i+1}\) | Active Cols | Active Rows | Succ | Stack \(S_{i+1}\) |
  |---|---|---|---|---|---|---|---|---|
  | 0 | \(\lbrace R_3:7 \rbrace\) | \(R_3:7\) | 1 | \(\lbrace R_3:1 \rbrace\) | \(\lbrace C_0, C_1 \rbrace\) | \(\lbrace R_0, R_1, R_2 \rbrace\) | F | \(\lbrace R_0:8, R_2:10 \rbrace\) |
  | 1 | \(\lbrace R_0:8, R_2:10 \rbrace\) | \(R_2:10\) | 2 | \(\lbrace R_3:1, R_2:2 \rbrace\) | \(\lbrace \rbrace\) | \(\lbrace \rbrace\) | T | \(\lbrace R_0:8 \rbrace\) |
  | 2 | \(\lbrace R_0:8 \rbrace\) | \(R_0:8\) | 2 | \(\lbrace R_3:1, R_0:2 \rbrace\) | \(\lbrace C_1 \rbrace\) | \(\lbrace R_1 \rbrace\) | F | \(\lbrace R_1:13 \rbrace\) |
  | 3 | \(\lbrace R_1:13 \rbrace\) | \(R_1:13\) | 3 | \(\lbrace R_3:1, R_0:2, R_1:3 \rbrace\) | \(\lbrace \rbrace\) | \(\lbrace \rbrace\) | T | \(\lbrace \rbrace\) |

  The search finds two exact cover solutions: \(\lbrace R_2, R_3 \rbrace\) and \(\lbrace R_0, R_1, R_3 \rbrace\).

  <br/>

  ### Working Example 2: Seven-Column Universe (Wikipedia Example)

  Consider the exact cover problem specified by the universe \(U = \lbrace 0, 1, 2, 3, 4, 5, 6 \rbrace\) and the collection of sets \(S = \lbrace A, B, C, D, E, F \rbrace\) where:

  $$\begin{aligned}
    A &= \lbrace 0, 3, 6 \rbrace \\
    B &= \lbrace 0, 3 \rbrace \\
    C &= \lbrace 3, 4, 6 \rbrace \\
    D &= \lbrace 2, 4, 5 \rbrace \\
    E &= \lbrace 1, 2, 5, 6 \rbrace \\
    F &= \lbrace 1, 6 \rbrace
  \end{aligned}$$

  We index rows as \(A \to 0, B \to 1, C \to 2, D \to 3, E \to 4, F \to 5\) and columns as \(0, 1, 2, 3, 4, 5, 6\).
  The number of rows \(\lvert R\rvert = 6\), so the depth stamp is:
  \(\sigma(\mathrm{depth}, r) = 6 \cdot \mathrm{depth} + r\).

  Initially, column \(0\) is picked because it has the minimum covering active row count (2: \(A, B\)). Sibling choices \(A, B\) are pushed to the stack at depth 1:
  \(S_0 = \lbrace A:6, B:7 \rbrace\), and \(\mathrm{Path}_0 = \lbrace \rbrace\).

  The table below traces the step-by-step execution.

  | \(i\) | Stack \(S_i\) | Peeked \(F_i\) | \(d^*_i\) | Path \(\mathrm{Path}_{i+1}\) | Active Cols | Active Rows | Succ | Stack \(S_{i+1}\) |
  |---|---|---|---|---|---|---|---|---|
  | 0 | \(\lbrace A:6, B:7 \rbrace\) | \(B:7\) | 1 | \(\lbrace B:1 \rbrace\) | \(\lbrace 1, 2, 4, 5, 6 \rbrace\) | \(\lbrace D, E, F \rbrace\) | F | \(\lbrace A:6, D:15 \rbrace\) |
  | 1 | \(\lbrace A:6, D:15 \rbrace\) | \(D:15\) | 2 | \(\lbrace B:1, D:2 \rbrace\) | \(\lbrace 1, 6 \rbrace\) | \(\lbrace F \rbrace\) | F | \(\lbrace A:6, F:23 \rbrace\) |
  | 2 | \(\lbrace A:6, F:23 \rbrace\) | \(F:23\) | 3 | \(\lbrace B:1, D:2, F:3 \rbrace\) | \(\lbrace \rbrace\) | \(\lbrace \rbrace\) | T | \(\lbrace A:6 \rbrace\) |
  | 3 | \(\lbrace A:6 \rbrace\) | \(A:6\) | 1 | \(\lbrace A:1 \rbrace\) | \(\lbrace 1, 2, 4, 5 \rbrace\) | \(\lbrace D \rbrace\) | F | \(\lbrace \rbrace\) |

  The search finds one exact cover solution: \(\lbrace B, D, F \rbrace\) (or row indices \(\lbrace 1, 3, 5 \rbrace\)).
working_example_part2: |
  ### Working Example 3: Four-Queens Problem (Generalized Exact Cover)

  The \(N\)-queens problem requires placing \(N\) queens on an \(N \times N\) chessboard such that no two queens attack each other. This can be modeled as a *generalized exact cover problem*, which partitions the column constraints into *primary columns* (which must be covered exactly once) and *secondary columns* (which must be covered at most once).

  For the \(4\)-queens problem:
  - **Rows**: \(16\) candidate rows, where row \(row = r \cdot 4 + c\) represents placing a queen at row \(r \in \lbrace 0 \dots 3 \rbrace\) and column \(c \in \lbrace 0 \dots 3 \rbrace\) of the board.
  - **Primary Columns**: \(8\) columns. Columns \(0 \dots 3\) represent the row placement constraints (exactly one queen in each row \(r\)). Columns \(4 \dots 7\) represent the column placement constraints (exactly one queen in each column \(c\)).
  - **Secondary Columns**: \(14\) columns. Columns \(8 \dots 14\) represent the primary diagonals (\(r+c\)). Columns \(15 \dots 21\) represent the secondary diagonals (\(r-c+3\)).

  To accommodate secondary columns in EDGE, we introduce a static primary mask vector \(\mathrm{IsPrimary} \in \lbrace 0, 1 \rbrace^{C}\) where \(\mathrm{IsPrimary}_c = 1\) if column \(c\) is primary, and \(0\) if it is secondary. The cascade evaluation is modified as:

  $$\begin{aligned}
    \mathrm{Success}_{i+1} &= \lVert \mathrm{ActiveCol}_{i+1} \cdot \mathrm{IsPrimary} \rVert \equiv 0 \\
    \mathrm{ActiveCounts}_{i+1, c} &= \mathrm{RowCounts}_{i+1, c} \cdot \mathrm{ActiveCol}_{i+1, c} \cdot \mathrm{IsPrimary}_c
  \end{aligned}$$

  This ensures the search evaluates success based solely on covering all rows and columns, and only branches on uncovered primary constraints.

  Starting with candidate placements on row 0, the EDGE stamped-stack search trace is shown in the table below.

  | \(i\) | Stack \(S_i\) | Peek \(F_i\) | \(d^*_i\) | Path \(\mathrm{Path}_{i+1}\) | Active Cols | Active Rows | Succ | Stack \(S_{i+1}\) |
  |---|---|---|---|---|---|---|---|---|
  | 0 | \(\lbrace (0,0):16, (0,1):17, (0,2):18, (0,3):19\rbrace\) | \((0,3):19\) | 1 | \(\lbrace (0,3):1\rbrace\) | \(\lbrace 1,2,3,4,5,6\rbrace\) | \(\lbrace (1,0),(1,1\ldots\rbrace\) | F | \(\lbrace (0,0):16, (0,1):17, (0,2):18, (1,0):36, (1,\ldots\rbrace\) |
  | 1 | \(\lbrace (0,0):16, (0,1):17, (0,2):18, (1,0):36, (1,\ldots\rbrace\) | \((1,1):37\) | 2 | \(\lbrace (0,3):1, (1,1):2\rbrace\) | \(\lbrace 2,3,4,6\rbrace\) | \(\lbrace (3,2)\rbrace\) | F | \(\lbrace (0,0):16, (0,1):17, (0,2):18, (1,0):36\rbrace\) |
  | 2 | \(\lbrace (0,0):16, (0,1):17, (0,2):18, (1,0):36\rbrace\) | \((1,0):36\) | 2 | \(\lbrace (0,3):1, (1,0):2\rbrace\) | \(\lbrace 2,3,5,6\rbrace\) | \(\lbrace (2,2),(3,1\ldots\rbrace\) | F | \(\lbrace (0,0):16, (0,1):17, (0,2):18, (2,2):58\rbrace\) |
  | 3 | \(\lbrace (0,0):16, (0,1):17, (0,2):18, (2,2):58\rbrace\) | \((2,2):58\) | 3 | \(\lbrace (0,3):1, (1,0):2, (2,2):3\rbrace\) | \(\lbrace 3,5\rbrace\) | \(\lbrace \rbrace\) | F | \(\lbrace (0,0):16, (0,1):17, (0,2):18\rbrace\) |
  | 4 | \(\lbrace (0,0):16, (0,1):17, (0,2):18\rbrace\) | \((0,2):18\) | 1 | \(\lbrace (0,2):1\rbrace\) | \(\lbrace 1,2,3,4,5,7\rbrace\) | \(\lbrace (1,0),(2,1\ldots\rbrace\) | F | \(\lbrace (0,0):16, (0,1):17, (1,0):36\rbrace\) |
  | 5 | \(\lbrace (0,0):16, (0,1):17, (1,0):36\rbrace\) | \((1,0):36\) | 2 | \(\lbrace (0,2):1, (1,0):2\rbrace\) | \(\lbrace 2,3,5,7\rbrace\) | \(\lbrace (2,3),(3,1\ldots\rbrace\) | F | \(\lbrace (0,0):16, (0,1):17, (2,3):59\rbrace\) |
  | 6 | \(\lbrace (0,0):16, (0,1):17, (2,3):59\rbrace\) | \((2,3):59\) | 3 | \(\lbrace (0,2):1, (1,0):2, (2,3):3\rbrace\) | \(\lbrace 3,5\rbrace\) | \(\lbrace (3,1)\rbrace\) | F | \(\lbrace (0,0):16, (0,1):17, (3,1):77\rbrace\) |
  | 7 | \(\lbrace (0,0):16, (0,1):17, (3,1):77\rbrace\) | \((3,1):77\) | 4 | \(\lbrace (0,2):1, (1,0):2, (2,3):3, (3,1):4\rbrace\) | \(\lbrace \rbrace\) | \(\lbrace \rbrace\) | T | \(\lbrace (0,0):16, (0,1):17\rbrace\) |
  | 8 | \(\lbrace (0,0):16, (0,1):17\rbrace\) | \((0,1):17\) | 1 | \(\lbrace (0,1):1\rbrace\) | \(\lbrace 1,2,3,4,6,7\rbrace\) | \(\lbrace (1,3),(2,0\ldots\rbrace\) | F | \(\lbrace (0,0):16, (1,3):39\rbrace\) |
  | 9 | \(\lbrace (0,0):16, (1,3):39\rbrace\) | \((1,3):39\) | 2 | \(\lbrace (0,1):1, (1,3):2\rbrace\) | \(\lbrace 2,3,4,6\rbrace\) | \(\lbrace (2,0),(3,0\ldots\rbrace\) | F | \(\lbrace (0,0):16, (2,0):56\rbrace\) |
  | 10 | \(\lbrace (0,0):16, (2,0):56\rbrace\) | \((2,0):56\) | 3 | \(\lbrace (0,1):1, (1,3):2, (2,0):3\rbrace\) | \(\lbrace 3,6\rbrace\) | \(\lbrace (3,2)\rbrace\) | F | \(\lbrace (0,0):16, (3,2):78\rbrace\) |
  | 11 | \(\lbrace (0,0):16, (3,2):78\rbrace\) | \((3,2):78\) | 4 | \(\lbrace (0,1):1, (1,3):2, (2,0):3, (3,2):4\rbrace\) | \(\lbrace \rbrace\) | \(\lbrace \rbrace\) | T | \(\lbrace (0,0):16\rbrace\) |
  | 12 | \(\lbrace (0,0):16\rbrace\) | \((0,0):16\) | 1 | \(\lbrace (0,0):1\rbrace\) | \(\lbrace 1,2,3,5,6,7\rbrace\) | \(\lbrace (1,2),(1,3\ldots\rbrace\) | F | \(\lbrace (1,2):38, (1,3):39\rbrace\) |
  | 13 | \(\lbrace (1,2):38, (1,3):39\rbrace\) | \((1,3):39\) | 2 | \(\lbrace (0,0):1, (1,3):2\rbrace\) | \(\lbrace 2,3,5,6\rbrace\) | \(\lbrace (2,1),(3,2\ldots\rbrace\) | F | \(\lbrace (1,2):38, (2,1):57\rbrace\) |
  | 14 | \(\lbrace (1,2):38, (2,1):57\rbrace\) | \((2,1):57\) | 3 | \(\lbrace (0,0):1, (1,3):2, (2,1):3\rbrace\) | \(\lbrace 3,6\rbrace\) | \(\lbrace \rbrace\) | F | \(\lbrace (1,2):38\rbrace\) |
  | 15 | \(\lbrace (1,2):38\rbrace\) | \((1,2):38\) | 2 | \(\lbrace (0,0):1, (1,2):2\rbrace\) | \(\lbrace 2,3,5,7\rbrace\) | \(\lbrace (3,1)\rbrace\) | F | \(\lbrace \rbrace\) |

  The search space is fully explored in 16 iterations, yielding exactly 2 solutions:

  1. **Solution 1** (Iteration 7): \(\mathrm{Sol}_1 = \lbrace (0, 2),\, (1, 0),\, (2, 3),\, (3, 1) \rbrace\)
     ```text
     .  .  Q  .
     Q  .  .  .
     .  .  .  Q
     .  Q  .  .
     ```

  2. **Solution 2** (Iteration 11): \(\mathrm{Sol}_2 = \lbrace (0, 1),\, (1, 3),\, (2, 0),\, (3, 2) \rbrace\)
     ```text
     .  Q  .  .
     .  .  .  Q
     Q  .  .  .
     .  .  Q  .
     ```
edge_expression_walkthrough: |
  - **Peek.** \(F_{i, r^\ast} = S_{i, r} :: \lll_{r^\ast} \mathbf{1}(\text{select-max-val})\) pops the deepest choice (largest stamp) to explore.
  - **Depth Extraction.** \(d^\ast_i = \lfloor F_{i,r} / \lvert R\rvert \rfloor :: \bigvee \max(\cup)\) extracts the depth.
  - **Pop.** \(T_{i,r} = S_{i,r} \cdot \neg F_{i,r} :: \bigwedge \leftarrow(\cap)\) removes the choice from stack.
  - **Truncate and Update Path.** We truncate any choices made at depths \(\ge d^*_i\) using \(\mathrm{TPath}_{i,r} = \mathrm{Path}_{i,r} \cdot d^\ast_i :: \bigwedge <(\cap)\), and then append the new choice.
  - **Active State Computation.** Using the updated path, we compute covered columns (\(\mathrm{CovCol}\)), active columns (\(\mathrm{ActiveCol}\)), conflicting rows (\(\mathrm{ConflictRow}\)), and active rows (\(\mathrm{ActiveRow}\)) using matrix-vector products.
  - **Success Evaluation.** If no active columns remain, we write the solution (\(\mathrm{Sol}\)).
  - **Branch Selection.** If we did not succeed, we count covering active rows for each active column, pick the column with the minimum count, and push its covering active rows onto the stack with the new depth \(d^*_i + 1\).
edge_expression: |
  $$
  \begin{aligned}
    &\triangleright\ \text{Tensors} \\
    A^{R,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    S^{I,\, R} &\to \text{integer},\ \text{empty}=-1 \\
    \mathrm{Path}^{I,\, R} &\to \text{integer},\ \text{empty}=-1 \\
    \mathrm{SelRow}^{I,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{CovCol}^{I,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{ActiveCol}^{I,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{ConflictRow}^{I,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{ActiveRow}^{I,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{Success}^{I} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{Sol}^{I,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{RowCounts}^{I,\, C} &\to \text{integer},\ \text{empty}=0 \\
    \mathrm{ActiveCounts}^{I,\, C} &\to \text{integer},\ \text{empty}=0 \\
    \mathrm{PickedCol}^{I,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{Candidates}^{I,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{NewChoices}^{I,\, R} &\to \text{integer},\ \text{empty}=-1 \\
    T^{I,\, R} &\to \text{integer},\ \text{empty}=-1 \\[6pt]
    &\triangleright\ \text{Stamp function} \\
    \sigma(\mathrm{depth}, r) &= \mathrm{depth} \cdot \lvert R\rvert + r \\[6pt]
    &\triangleright\ \text{Initialization} \\
    S_{0,\, r} &= \text{initial candidates at depth 1 (first column branch choices)} \\
    \mathrm{Path}_{0} &= \text{empty} \\[6pt]
    &\triangleright\ \text{Extended Einsum (one pop/backtrack step per iteration } i\text{)} \\
    &\triangleright\ \text{\textbf{peek and pop}} \\
    F_{i,r^\ast} &= S_{i,r} :: \lll_{r^\ast} \mathbf{1}(\text{select-max-val}) \\
    d^\ast_i &= \lfloor F_{i,r} / \lvert R\rvert \rfloor :: \bigvee \max(\cup) \\
    T_{i,r} &= S_{i,r} \cdot \neg F_{i,r} :: \bigwedge \leftarrow(\cap) \\
    &\triangleright\ \text{\textbf{update path}} \\
    \mathrm{TPath}_{i,r} &= \mathrm{Path}_{i,r} \cdot d^\ast_i :: \bigwedge <(\cap) \\
    \mathrm{NewPathEntry}_{i,r} &= F_{i,r} \cdot d^\ast_i :: \bigwedge \rightarrow(\cap) \\
    \mathrm{Path}_{i+1,r} &= \mathrm{TPath}_{i,r} \cdot \mathrm{NewPathEntry}_{i,r} :: \bigwedge \texttt{<<}(\cup) \\
    &\triangleright\ \text{\textbf{active subset computation}} \\
    \mathrm{SelRow}_{i+1,r} &= \mathrm{Path}_{i+1,r} \cdot 0 :: \bigwedge \ge(\cup) \\
    \mathrm{CovCol}_{i+1,c} &= A_{r,c} \cdot \mathrm{SelRow}_{i+1,r} :: \bigwedge \leftarrow(\cap)\ \bigvee \text{ANY}(\cup) \\
    \mathrm{ActiveCol}_{i+1,c} &= \mathrm{Col}_c \cdot \neg \mathrm{CovCol}_{i+1,c} :: \bigwedge \leftarrow(\cap) \\
    \mathrm{ConflictRow}_{i+1,r} &= A_{r,c} \cdot \mathrm{CovCol}_{i+1,c} :: \bigwedge \leftarrow(\cap)\ \bigvee \text{ANY}(\cup) \\
    \mathrm{ActiveRow}_{i+1,r} &= \mathrm{Row}_r \cdot \neg \mathrm{ConflictRow}_{i+1,r} \cdot \neg \mathrm{SelRow}_{i+1,r} :: \bigwedge \leftarrow(\cap) \\
    &\triangleright\ \text{\textbf{success evaluation}} \\
    \mathrm{Success}_{i+1} &= \lVert \mathrm{ActiveCol}_{i+1} \rVert \equiv 0 \\
    \mathrm{Sol}_{i+1,r} &= \mathrm{SelRow}_{i+1,r} \cdot \mathrm{Success}_{i+1} :: \bigwedge \leftarrow(\cap) \\
    &\triangleright\ \text{\textbf{branch and push (if Success is False)}} \\
    \mathrm{RowCounts}_{i+1,c} &= A_{r,c} \cdot \mathrm{ActiveRow}_{i+1,r} :: \bigwedge \leftarrow(\cap)\ \bigvee +(\cup) \\
    \mathrm{ActiveCounts}_{i+1,c} &= \mathrm{RowCounts}_{i+1,c} \cdot \mathrm{ActiveCol}_{i+1,c} :: \bigwedge \leftarrow(\cap) \\
    \mathrm{PickedCol}_{i+1,c^\ast} &= \mathrm{ActiveCounts}_{i+1,c} :: \lll_{c^\ast} \mathbf{1}(\text{select-min-val}) \\
    \mathrm{Candidates}_{i+1,r} &= (A_{r,c} \cdot \mathrm{PickedCol}_{i+1,c} :: \bigwedge \leftarrow(\cap)\ \bigvee \text{ANY}(\cup)) \cdot \mathrm{ActiveRow}_{i+1,r} :: \bigwedge \leftarrow(\cap) \\
    \mathrm{NewChoices}_{i+1,r} &= \mathrm{Candidates}_{i+1,r} \cdot \sigma(d^\ast_i + 1, r) :: \bigwedge \rightarrow(\cap) \\
    S_{i+1,r} &= T_{i,r} \cdot \mathrm{NewChoices}_{i+1,r} :: \bigwedge \texttt{<<}(\cup) \\[6pt]
    &\diamond : \lVert S_{i+1} \rVert \equiv 0
  \end{aligned}
  $$
other_notes: |
  ### Path-Driven State Reconstruction
  A classic implementation of Algorithm X (like Dancing Links) maintains the exact state of the reduced matrix by destructively covering and uncovering columns and rows during descent and backtracking. In contrast, this EDGE formulation reconstructs the active subset dynamically from the current path at the start of each step. The complexity of carrying state updates through the recursion tree is replaced by clean, parallel matrix-vector multiplication over the input matrix \(A\).

  ### Disjoint Candidate Levels
  Sibling alternatives pushed at depth \(d\) are candidates covering a chosen column \(c_d\). In any sub-branch where one candidate \(r'\) is selected, \(c_d\) becomes covered, making all other candidates for \(c_d\) conflicting. Since conflicting rows are excluded from the active set, none of the shallower alternative siblings can ever be pushed again as candidates at a deeper level. This guarantees that stack updates at depth \(d^* + 1\) never overwrite active alternative branches from shallower levels, preserving the integrity of the backtracking history.
variants: |
  The cascade can be extended to generalized exact cover (e.g., N-Queens) by adding a static primary column mask \(\mathrm{IsPrimary}\), as demonstrated in Example 3.

  ### Parallelization of Algorithm X in EDGE
  
  #### Parallelization Strategy
  Since Knuth's Algorithm X is a tree-based backtracking search, it can be parallelized by exploring alternative branches of the search tree concurrently (OR-parallelism). When the algorithm selects a column to cover, it branches on the \(K\) candidate rows that cover that column. Each of these \(K\) choices represents a mutually exclusive branch of the search space.

  Because any valid exact cover solution must contain exactly one row covering each column, choosing row \(A\) for column \(c_0\) automatically conflicts with and excludes row \(B\) from all subsequent steps in that branch. Thus, the search spaces under different candidate rows at any branching point are completely disjoint, ensuring that multiple workers can explore these subtrees concurrently without any redundant work or cross-worker overlap.

  #### EDGE Formulation with Worker Rank
  To express this parallel search algebraically in EDGE, we introduce a new non-reduced tensor rank \(W\) representing the active parallel workers (or threads). For a width of \(W\) parallel search paths, the state tensors are augmented with the rank \(W\) representing each worker's independent search state:
  - \(S^{I,\, W,\, R}\) representing the open stack of alternatives for each worker \(w \in W\).
  - \(\mathrm{Path}^{I,\, W,\, R}\) representing each worker's active path of selected rows.
  
  All other intermediate state tensors similarly gain the rank \(W\), indicating that they represent the local, independent search sub-problems of each worker.

  #### Full Parallel EDGE Cascade
  The transition to the parallel worker cascade is extremely clean, requiring only shape propagation along the new rank \(W\) with no structural changes to the logic of the update equations:

  $$
  \begin{aligned}
    &\triangleright\ \text{Tensors} \\
    A^{R,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    S^{I,\, W,\, R} &\to \text{integer},\ \text{empty}=-1 \\
    \mathrm{Path}^{I,\, W,\, R} &\to \text{integer},\ \text{empty}=-1 \\
    \mathrm{SelRow}^{I,\, W,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{CovCol}^{I,\, W,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{ActiveCol}^{I,\, W,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{ConflictRow}^{I,\, W,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{ActiveRow}^{I,\, W,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{Success}^{I,\, W} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{Sol}^{I,\, W,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{RowCounts}^{I,\, W,\, C} &\to \text{integer},\ \text{empty}=0 \\
    \mathrm{ActiveCounts}^{I,\, W,\, C} &\to \text{integer},\ \text{empty}=0 \\
    \mathrm{PickedCol}^{I,\, W,\, C} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{Candidates}^{I,\, W,\, R} &\to \text{Boolean},\ \text{empty}=\text{False} \\
    \mathrm{NewChoices}^{I,\, W,\, R} &\to \text{integer},\ \text{empty}=-1 \\
    T^{I,\, W,\, R} &\to \text{integer},\ \text{empty}=-1 \\[6pt]
    &\triangleright\ \text{Stamp function} \\
    \sigma(depth, r) &= depth \cdot \lvert R\rvert + r \\[6pt]
    &\triangleright\ \text{Initialization} \\
    S_{0,\, w,\, r} &= \text{initial candidate rows partitioned across workers } w \in W \\
    \mathrm{Path}_{0} &= \text{empty} \\[6pt]
    &\triangleright\ \text{Extended Einsum (one pop/backtrack step per iteration } i\text{)} \\
    &\triangleright\ \text{\textbf{peek and pop}} \\
    F_{i,w,r^\ast} &= S_{i,w,r} :: \lll_{r^\ast} \mathbf{1}(\text{select-max-val}) \\
    d^\ast_{i,w} &= \lfloor F_{i,w,r} / \lvert R\rvert \rfloor :: \bigvee \max(\cup) \\
    T_{i,w,r} &= S_{i,w,r} \cdot \neg F_{i,w,r} :: \bigwedge \leftarrow(\cap) \\
    &\triangleright\ \text{\textbf{update path}} \\
    \mathrm{TPath}_{i,w,r} &= \mathrm{Path}_{i,w,r} \cdot d^\ast_{i,w} :: \bigwedge <(\cap) \\
    \mathrm{NewPathEntry}_{i,w,r} &= F_{i,w,r} \cdot d^\ast_{i,w} :: \bigwedge \rightarrow(\cap) \\
    \mathrm{Path}_{i+1,w,r} &= \mathrm{TPath}_{i,w,r} \cdot \mathrm{NewPathEntry}_{i,w,r} :: \bigwedge \texttt{<<}(\cup) \\
    &\triangleright\ \text{\textbf{active subset computation}} \\
    \mathrm{SelRow}_{i+1,w,r} &= \mathrm{Path}_{i+1,w,r} \cdot 0 :: \bigwedge \ge(\cup) \\
    \mathrm{CovCol}_{i+1,w,c} &= A_{r,c} \cdot \mathrm{SelRow}_{i+1,w,r} :: \bigwedge \leftarrow(\cap)\ \bigvee \text{ANY}(\cup) \\
    \mathrm{ActiveCol}_{i+1,w,c} &= \mathrm{Col}_c \cdot \neg \mathrm{CovCol}_{i+1,w,c} :: \bigwedge \leftarrow(\cap) \\
    \mathrm{ConflictRow}_{i+1,w,r} &= A_{r,c} \cdot \mathrm{CovCol}_{i+1,w,c} :: \bigwedge \leftarrow(\cap)\ \bigvee \text{ANY}(\cup) \\
    \mathrm{ActiveRow}_{i+1,w,r} &= \mathrm{Row}_r \cdot \neg \mathrm{ConflictRow}_{i+1,w,r} \cdot \neg \mathrm{SelRow}_{i+1,w,r} :: \bigwedge \leftarrow(\cap) \\
    &\triangleright\ \text{\textbf{success evaluation}} \\
    \mathrm{Success}_{i+1,w} &= \lVert \mathrm{ActiveCol}_{i+1,w} \rVert \equiv 0 \\
    \mathrm{Sol}_{i+1,w,r} &= \mathrm{SelRow}_{i+1,w,r} \cdot \mathrm{Success}_{i+1,w} :: \bigwedge \leftarrow(\cap) \\
    &\triangleright\ \text{\textbf{branch and push (if Success is False)}} \\
    \mathrm{RowCounts}_{i+1,w,c} &= A_{r,c} \cdot \mathrm{ActiveRow}_{i+1,w,r} :: \bigwedge \leftarrow(\cap)\ \bigvee +(\cup) \\
    \mathrm{ActiveCounts}_{i+1,w,c} &= \mathrm{RowCounts}_{i+1,w,c} \cdot \mathrm{ActiveCol}_{i+1,w,c} :: \bigwedge \leftarrow(\cap) \\
    \mathrm{PickedCol}_{i+1,w,c^\ast} &= \mathrm{ActiveCounts}_{i+1,w,c} :: \lll_{c^\ast} \mathbf{1}(\text{select-min-val}) \\
    \mathrm{Candidates}_{i+1,w,r} &= (A_{r,c} \cdot \mathrm{PickedCol}_{i+1,w,c} :: \bigwedge \leftarrow(\cap)\ \bigvee \text{ANY}(\cup)) \cdot \mathrm{ActiveRow}_{i+1,w,r} :: \bigwedge \leftarrow(\cap) \\
    \mathrm{NewChoices}_{i+1,w,r} &= \mathrm{Candidates}_{i+1,w,r} \cdot \sigma(d^\ast_{i,w} + 1, r) :: \bigwedge \rightarrow(\cap) \\
    S_{i+1,w,r} &= T_{i,w,r} \cdot \mathrm{NewChoices}_{i+1,w,r} :: \bigwedge \texttt{<<}(\cup) \\[6pt]
    &\diamond : \lVert S_{i+1} \rVert \equiv 0
  \end{aligned}
  $$
implementation_notes: |
  At each iteration, the cascade performs a peek (selecting the maximum stamp coordinate), path truncation and update, matrix-vector product to compute active rows/columns, and a column minimum selection (minimum covering active rows count). In an optimized execution environment, these operations can be vectorized.
complexity_costs: |
  The search depth is bounded by \(\lvert C\rvert\), and the stack holds at most \(\lvert R\rvert\) stamps. Each row is chosen at most once along any valid path, yielding a traversal complexity bounded by the size of the search tree.
related_notes: |
  [Post-Order Depth-First Search](post-order-dfs.html) uses a similar stamped-stack backtracking mechanism.
---
