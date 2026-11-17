---
title: Bubble Sort
authors: [Toluwanimi Odemuyiwa]
summary: In-place comparison sort that repeatedly bubbles the largest unsorted element rightward by a sweep of adjacent compare-exchanges, expressed as a nested cascade over a pass rank and a step rank where each step keeps the min on the left and the max on the right of an adjacent pair.
tags: [sorting, compare-exchange, iteration, building-blocks]
ranks:
  I: generational  # the pass rank, iterated by the outer cascade
  J: position      # the step rank, iterated by the inner cascade
  M: position
  N: position
status_intro: |
  This page gives the classic sequential form of bubble sort as a nested EDGE
  cascade. The array state lives in a three-rank tensor $Z_{i,j,n}$: the value at
  position $n$ after step $j$ of pass $i$. An inner cascade over the step rank $j$
  sweeps left to right, and at each step compares one adjacent pair and writes the
  smaller value to the left position and the larger to the right. The outer
  cascade over the pass rank $i$ repeats the sweep, each pass settling one more
  element into place, and halts when a full pass changes nothing. The whole
  algorithm is expressed inside the tensor machinery: the adjacent pair is reached
  by ordinary rank-variable arithmetic ($j$ and $j+1$), and the exchange is a pair
  of $\min$/$\max$ computes. No value is ever promoted to a coordinate.
problem_statement: |
  Given an array $A$ of $\lvert A\rvert = N$ comparable values, produce the same
  multiset in non-decreasing order.

  A single three-rank tensor carries the running state, alongside the input array:

  - $A^{N \equiv \lvert A\rvert} \to \text{integer}$, the input array.
  - $Z^{I \equiv N{-}1,\, J \equiv N{-}1,\, M \equiv N} \to \text{integer}$, the
    working state. $Z_{i,j,n}$ is the value at position $n$ (the $M$ rank) after
    step $j$ (the $J$ rank) of pass $i$ (the $I$ rank). Each pass performs
    $J \equiv N-1$ adjacent compare-exchange steps, and the algorithm needs at
    most $I \equiv N-1$ passes.

  Position $n$ ranges over $0 \ldots N-1$. Step $j$ compares the pair at positions
  $(j,\, j{+}1)$, so steps run $j = 0 \ldots J-1$ to keep $j{+}1$ in range; the
  final row of pass $i$ is $Z_{i,\,J-1,\,\cdot}$, the state after the last step.
working_example_part1: |
  Take $A = [3,\,1,\,4,\,2]$, so $N = 4$, $J = N-1 = 3$ steps per pass, and at
  most $I = N-1 = 3$ passes. Position $n$ runs $0 \ldots 3$.

  Initialization performs pass $0$'s first compare-exchange on positions $0$ and
  $1$ ($\min(3,1) = 1$ to the left, $\max(3,1) = 3$ to the right):

  $$Z_{0,0,\cdot} = [\,1,\ 3,\ \cdot,\ \cdot\,].$$

  Positions $2$ and $3$ are not yet touched in step $0$; they are empty (no
  value) until a later step reads them in from $A$.
working_example_part2: |
  Each step $j$ carries the already-settled left region forward, compares the
  running value at position $j$ against the next array element $A_{j+1}$, and
  writes $\min$ to position $j$ and $\max$ to position $j+1$. The final row
  $Z_{i,\,J-1,\cdot}$ of each pass is the input to the next pass.

  | pass $i$ | step $j=0$ | step $j=1$ | step $j=2$ (final row) |
  |----|----|----|----|
  | $0$ | $[1,\,3,\,0,\,0]$ | $[1,\,3,\,4,\,0]$ | $[1,\,3,\,2,\,4]$ |
  | $1$ | $[1,\,3,\,2,\,4]$ | $[1,\,2,\,3,\,4]$ | $[1,\,2,\,3,\,4]$ |
  | $2$ | $[1,\,2,\,3,\,4]$ | $[1,\,2,\,3,\,4]$ | $[1,\,2,\,3,\,4]$ |

  In pass $0$ the largest value $4$ bubbles rightward into its final position,
  giving $[1,\,3,\,2,\,4]$. Pass $1$ then fixes the $3,2$ inversion at step $1$,
  producing the sorted array $[1,\,2,\,3,\,4]$. Pass $2$ sweeps once more and
  changes nothing, so its final row equals pass $1$'s final row,
  $Z_{2,\,J-1} \equiv Z_{1,\,J-1}$, and the outer cascade halts. The result is
  $Z_{i,\,J-1,\cdot} = [1,\,2,\,3,\,4]$, the sorted array.
edge_expression_walkthrough: |
  The state tensor $Z_{i,j,n}$ is read piecewise by position $n$. The selectors
  $n < j$, $n = j$, $n = j+1$, and $n > j+1$ are constraints on the iteration
  space (which point of $Z$ each compute writes), and the shifted reads $j-1$,
  $j+1$, and $i-1$ are ordinary rank-variable expressions: functions of the
  iteration-space variables $i$ and $j$ only. No tensor value is ever placed in a
  subscript, so this stays within EDGE's rank-variable rules — the adjacency
  $j / j{+}1$ comes entirely from arithmetic on the loop variables.

  **Initialize each pass (step $0$).** Pass $0$ reads the raw input:
  $\min(A_0, A_1)$ lands at position $0$ and $\max(A_0, A_1)$ at position $1$;
  every other position is `empty`. Each later pass $i$ instead reads pass $i-1$'s
  final row $Z_{i-1,\,J-1,\cdot}$: it compares positions $0$ and $1$ of that row
  (writing $\min$ to $0$, $\max$ to $1$) and copies positions $n \geq 2$ across
  unchanged.

  **Sweep within a pass (steps $j \geq 1$).** The compare-exchange at step $j$ is
  four cases on position $n$:

  - $n < j$: carry the settled left region forward, $Z_{i,j,n} = Z_{i,j-1,n}$.
  - $n = j$: write the smaller of the running value and the incoming element,
    $\min(Z_{i,\,j-1,\,j},\, R)$.
  - $n = j+1$: write the larger, $\max(Z_{i,\,j-1,\,j},\, R)$.
  - $n > j+1$: carry the not-yet-reached right region forward.

  The incoming element $R$ is $A_{j+1}$ on pass $0$ (still bubbling through the raw
  input) and $Z_{i-1,\,J-1,\,j+1}$ on later passes (the corresponding cell of the
  previous pass's final row). The exchange is exactly the pair
  $\bigl(\min(x,y),\, \max(x,y)\bigr)$ written to positions $(j,\, j{+}1)$, which
  leaves the pair sorted regardless of its original order: an in-order pair is
  unchanged, an out-of-order pair is swapped.

  **Inner stop.** $\diamond\diamond : j \equiv J$. The step cascade runs the fixed
  $J = N-1$ compare-exchanges of one pass, then ends so the outer cascade can take
  the pass's final row.

  **Outer stop.** $\diamond : Z_{i+1,\,J-1} \equiv Z_{i,\,J-1}$. The pass cascade
  halts when a whole sweep produces no change, i.e. the array is sorted. (A fixed
  $I = N-1$ passes is the worst-case alternative; the change-detecting stop ends
  early on already-mostly-sorted input.)
edge_expression: |
  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &A^{N \equiv \lvert A\rvert} \to \text{integer},\ \text{empty}=\infty\\
  &Z^{I \equiv N{-}1,\, J \equiv N{-}1,\, M \equiv N} \to \text{integer},\ \text{empty}=\infty\\[4pt]
  &\triangleright \textbf{Initialization (pass } 0\text{, step } 0\text{: first compare-exchange of } A_0, A_1)\\
  &A \to \langle\text{user-specified}\rangle\\
  &Z_{0,\,0,\,n} =
    \begin{cases}
      \min(A_0,\, A_1) & n = 0\\
      \max(A_0,\, A_1) & n = 1\\
      \text{empty} & \text{o/w}
    \end{cases}\\[4pt]
  &\triangleright \textbf{Extended Einsum}\\
  &\triangleright \textbf{Begin outer cascade (passes)}\quad i = 0\\[2pt]
  &\triangleright \textbf{Begin inner cascade (steps)}\\
  &\triangleright\ \text{Pass } 0,\ \text{step } j\ (j \geq 1)\text{: bubble the max rightward through } A\\
  &Z_{0,\,j\,:\,j \geq 1,\,n} =
    \begin{cases}
      Z_{0,\,j-1,\,n} & n < j\\
      \min(Z_{0,\,j-1,\,j},\, A_{j+1}) & n = j\\
      \max(Z_{0,\,j-1,\,j},\, A_{j+1}) & n = j+1\\
      \text{empty} & \text{o/w}
    \end{cases}\\[2pt]
  &\triangleright\ \text{Pass } i\ (i \geq 1)\text{, step } 0\text{: first compare-exchange reads the previous pass's final row}\\
  &Z_{i\,:\,i \geq 1,\,0,\,n} =
    \begin{cases}
      \min(Z_{i-1,\,J-1,\,0},\, Z_{i-1,\,J-1,\,1}) & n = 0\\
      \max(Z_{i-1,\,J-1,\,0},\, Z_{i-1,\,J-1,\,1}) & n = 1\\
      Z_{i-1,\,J-1,\,n} & n \geq 2
    \end{cases}\\[2pt]
  &\triangleright\ \text{Pass } i\ (i \geq 1)\text{, step } j\ (j \geq 1)\text{: bubble rightward through the previous pass's final row}\\
  &Z_{i\,:\,i \geq 1,\,j\,:\,j \geq 1,\,n} =
    \begin{cases}
      Z_{i,\,j-1,\,n} & n < j\\
      \min(Z_{i,\,j-1,\,j},\, Z_{i-1,\,J-1,\,j+1}) & n = j\\
      \max(Z_{i,\,j-1,\,j},\, Z_{i-1,\,J-1,\,j+1}) & n = j+1\\
      Z_{i-1,\,J-1,\,n} & n > j+1
    \end{cases}\\[4pt]
  &\diamond\diamond : j \equiv J\qquad \triangleright \textbf{end inner cascade (pass complete)}\\
  &\diamond : Z_{i+1,\,J-1} \equiv Z_{i,\,J-1}\qquad \triangleright \textbf{end outer cascade (no change this pass)}
  \end{aligned}
  $$
other_notes: |
  The two reads of an adjacent pair, $Z_{i,\,j-1,\,j}$ and either $A_{j+1}$ or
  $Z_{i-1,\,J-1,\,j+1}$, are slices of fixed tensors at coordinates given by
  arithmetic on the loop variables $i$ and $j$. Pinning a rank to $j+1$ or to
  $J-1$ is a rank-variable expression (a function of iteration-space variables),
  the same device Floyd-Warshall uses to read the pivot row and column. No value
  read out of $Z$ or $A$ is ever used as a coordinate.

  `empty` $= \infty$ is the array's no-value sentinel: positions that step $j$ has
  not yet reached are empty and are filled in by a later step or carried from the
  previous pass. It lies outside the value range, so a $0$ in the array is an
  ordinary value, exactly as the shortest-path pages use $\infty$. The ranges
  $j \geq 1$ and $i \geq 1$ are written into the Einsums as conditions, so each
  Einsum runs only at the passes and steps it describes.

  The "running value" at position $j$ on entry to step $j$ is the larger element
  carried from step $j-1$ (it was written to position $j$ as the $\max$ of the
  previous pair). Comparing it against the next element and keeping $\min$ on the
  left, $\max$ on the right is what makes the largest unsorted value migrate to
  the right end of the array within a single pass.
variants: |
  Replacing the change-detecting outer stop $\diamond : Z_{i+1,\,J-1} \equiv
  Z_{i,\,J-1}$ with a fixed trip count $\diamond : i \equiv N-1$ gives the
  textbook unconditional bubble sort: always $N-1$ passes, no early exit.
  Shrinking the inner step bound each pass — pass $i$ sweeps only
  $j = 0 \ldots J-1-i$, since the last $i$ positions are already settled — is the
  standard optimization and is purely an iteration-space restriction on $j$.

  A pipelined variant changes only *which* cell of the previous pass each step
  reads: instead of always reading the previous pass's final row
  $Z_{i-1,\,J-1,\,j+1}$, an interior step reads $Z_{i-1,\,j+1,\,j+1}$ — the
  previous pass's state one step ahead. Pass $i$ then trails pass $i-1$ by a
  single step rather than waiting for it to finish, so passes overlap. Both forms
  produce the same sorted final row. Swapping $\min$/$\max$ (max to the left)
  sorts in non-increasing order.
implementation_notes: |
  The inner cascade is a left-to-right sweep of $N-1$ scalar compare-exchanges;
  the only data carried between steps is the running value at the current
  boundary. Materializing the full $Z$ tensor (one row per step, one plane per
  pass) is the unrolled, write-once view that makes the dependences explicit:
  step $j$ depends on step $j-1$ of the same pass and on the previous pass's
  final row. In practice the rows are not stored — the sweep is done in place over
  a single length-$N$ array, with one comparison and an optional swap per step.
  The change-detecting outer stop is a single Boolean: did any swap happen this
  pass.
complexity_costs: |
  Each pass is $N-1$ compare-exchanges, and there are at most $N-1$ passes, for
  $O(N^2)$ comparisons and swaps in the worst case (a reverse-sorted array). With
  the change-detecting stop, an already-sorted array finishes in one pass at
  $O(N)$. The in-place implementation uses $O(1)$ extra space; the unrolled $Z$
  tensor is $O(N^2)$ if every row is retained.
related_notes: |
  Bubble sort is the simplest compare-exchange network: a sequence of adjacent
  $\min$/$\max$ swaps iterated to a fixed point. The same compare-exchange
  primitive, arranged in a fixed data-independent pattern rather than a
  change-detecting loop, gives the sorting networks (odd-even transposition,
  bitonic) that map well to parallel hardware. The nested-cascade structure — an
  inner fixed-trip-count sweep inside an outer fixed-point loop — mirrors the
  connected-components cascade, which nests a shortcut loop inside a
  parent-connect loop.
---
