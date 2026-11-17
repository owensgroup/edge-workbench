# Visualizing your own cascade

This guide is for an author who has written an EDGE tutorial and wants the
step-through page for it: every Einsum executed on your worked example, with
your explanation beside each step.

You write three files. The workbench checks them against each other, runs your
cascade, checks its answers, and writes `index.html`. Two steps need a language
model; the workbench never calls one itself — it gives you a prompt to paste
into a chat and tells you where to save the reply.

---

## 1. Set up once

You need Python 3.10+ and two checkouts side by side:

```
git clone https://github.com/edge-einsums/edge-core-ir
git clone <edge-workbench>
pip install -e edge-core-ir          # the IR classes and validators (needs pydantic)
```

The workbench runs your cascade with edge-core-ir's evaluator, which it finds
through `EDGE_IR_REPO`, an edge-core-ir checkout beside edge-workbench,
`~/Projects/edge-core-ir`, or an installed `edge_ir`, in that order.

## 2. Make a directory with three files

```
my-algorithm/
  my-algorithm.md     the tutorial, exactly as it will appear on the website
  einsum.edge         the cascade in EDGE's ASCII form
  verifier.py         an independent way to get the same answers
```

### The tutorial

Your usual tutorial `.md`. The workbench reads its `edge_expression` (the
cascade, in LaTeX) and its prose. The worked example as data is produced in
step 4 and quoted from your text.

Say what each Einsum means right under it in `edge_expression_walkthrough`:

```
$$D_{i+1,v} = N_{i,v} \cdot D_{i,v} :: \bigwedge_v \min(\cup)$$

**Graph meaning:** If the new relaxed value improves the distance to $v$,
update it; otherwise keep the old distance.

**Einsum meaning:** Take an elementwise min between two tensors over $v$.
```

The page shows these as you wrote them, and `$...$` renders as math. Each pair
goes after the formula it explains, which may be an Einsum, an initialization
or the `\diamond` stop line. Any Einsum without a `Graph meaning:` is filled by
the model in step 4, quoting your text, and any without an `Einsum meaning:`
gets a sentence generated from the program. Nothing checks that your sentence
matches the Einsum, so that part is yours to keep true.

Say what each rank is in a `ranks:` block in the front matter. This decides the
picture:

```yaml
ranks:
  I: generational  # the generational (iterative) rank
  S: vertex
  D: vertex
  XY: spatial     # A*: L_{S, XY} is each vertex's location, not an edge
```

| kind | means | picture |
|---|---|---|
| `generational` | the generational (iterative) rank; at most one | one generation at a time |
| `vertex` | a vertex of a graph; all vertex ranks are one vertex set | graph |
| `set`, `element` | the two sides of an incidence matrix (exact cover's rows and columns) | bipartite |
| `position` | a position in a sequence | sequence |
| `spatial` | an axis of physical space (A*'s `XY`) | gives each vertex's location |

Every rank in einsum.edge needs a kind, and a word not in the table stops the
run. Without a `ranks:` block the picture is inferred from the tensors, which
works for graphs and bipartite graphs but cannot tell a DP table or a
location tensor from an edge tensor. When your declaration and the inference
disagree, the instance stage says so in its summary; that is a note, not a
failure. Every tensor is also shown as a grid, whatever the picture.

### einsum.edge

The same cascade as your tutorial's `edge_expression`, in ASCII, with every
Einsum labelled. Three sections:

```
- Tensors
A^{R, C}       -> Boolean, empty = False
S^{I, R}       -> integer, empty = -1
Keep^{I, R}    -> Boolean, empty = False

- Initializations
S_{0, r} = InitS_r

- Extended Einsums
# E01: the top of the stack
F_{i, r*} = S_{i, r} :: <<<_{r*} 1(select-max-val)
# E02: its depth
d*_i = floor( F_{i, r} / |R| ) :: \/ max(∪)
...
<> : ||S_{i+1}|| == 0
```

Rules the checks rely on:

- **Declare every tensor you use**, intermediates included, with ranks, type
  and empty value. The empty value decides which entries exist, so it is
  checked against the IR for every tensor.
- **Label every Einsum** `# E01:`, `# E02:`, ... in cascade order. The labels
  tie together your file, the IR, the meanings and the page.
- **Operators** are written `/\ compute(merge)` for a Map and
  `\/ compute(merge)` for a Reduce, with `^1`, `^2` labels when an Einsum has
  more than one: `/\^1 min(∩) /\^2 <-(∩)`. Merges are `∩ ∪ <- ->`; computes
  include `+ - * / min max < <= > >= == AND OR ANY <- -> <<`.
- **Populate** is `:: <<<_{v*} 1(name)`. A ranking name
  (`select-min-val`, `select-max-val`, ...) is part of the algorithm; any other
  name is a free choice and is run with random seeds.
- **More than two operands** need parentheses and labels:
  `(A_r .^1 B_r)_r .^2 C_r :: /\^1 ... /\^2 ...`.
- **A case statement** is one Einsum: `= cases:`, then one indented arm per
  line, an expression followed by `if <condition>` or `otherwise`. An arm may
  have its own `:: ...`; `empty` means its region gets no value. Arms are
  tried in the order written, and the first whose condition holds is used.

  ```
  # E01: pass 0, step j
  Z_{0, j, n} = cases:
      Z_{0, j-1, n}                  if n < j
      min(Z_{0, j-1, j}, A_{j+1})    if n = j
      max(Z_{0, j-1, j}, A_{j+1})    if n = j+1
      empty                          otherwise
  ```

  An arm written as a function call (`min(x, y)`) states no merge operator;
  it is run with intersect, so a missing operand means no value. Write
  `x . y :: /\ min(∪)` if you mean something else. A case statement may also
  be an initialization.
- **An inner cascade** is the Einsums between a `- Begin inner cascade` line
  and the stopping condition that ends it, written with two diamonds:
  `<><> : j == J`. The outer cascade's `<> : ...` comes last. A generational
  rank you give a shape (`I = N-1`) also ends its cascade when it runs out.
- **A macro** is a section of its own, after the cascade that calls it:
  `- Macro NAME(inputs) -> outputs`, then its Einsums, labelled like any
  others and written in the macro's formal names, exactly as the tutorial
  writes them. The cascade calls macros from a **multi-output case
  statement**, which is labelled too: the outputs in parentheses, `= cases:`,
  then one macro call per arm with `if <condition>` or `otherwise`. Each
  generation runs the first arm whose condition holds.

  ```
  # E03: one direction per generation
  (Tree_{i+1, s, d}, F_{i+1, d}, TopDown_{i+1}) = cases:
      TOP-DOWN(G_{s, d}, F_{i, s}, Tree_{i, s, d}, NV_{i, c}, MF_i, MU_i)   if TopDown_i == True
      BOTTOM-UP(G_{s, d}, F_{i, s}, Tree_{i, s, d}, NV_{i, c}, NF_i)        if TopDown_i == False
  <> : ||F_{i+1}|| == 0

  - Macro TOP-DOWN(TG_{s, d}, TF_{i, s}, TTree_{i, s, d}, TNV_{i, c}, TMF_i, TMU_i) -> TTree_{i+1, s, d}, TF_{i+1, d}, TTopDown_{i+1}
  # E04: gather neighbors of the frontier
  Nei_{i, d} = TG_{s, d} . TF_{i, s} :: /\ AND(∩) \/ OR(∪)
  ...
  ```

  A call binds each formal tensor to the actual one in the same position,
  inputs then outputs, and the page shows each Einsum of the body both as
  written and as that call expands it. Declare the actual tensors only
  (`Tree`, never `TTree`), including any the macro writes that the tutorial
  does not declare. The tutorial's `MACRO` blocks are compared with these
  sections line by line, header included.
- **A constant** the cascade reads by name and the tutorial gives no
  declaration for (a threshold) goes under `- Constants`, one `name = value`
  per line (`alpha = 15`). It is part of the program, not an input, so no
  instance supplies it; the tutorial has to state the value somewhere
  (`$\alpha = 15$`), or `check` says so.
- **An operation with no action**, as in `TB_i = MF_i . (MU_i / alpha) ::
  /\ >(∩)`, states a compute and no merge. It runs with the paper's default
  merge, pass-through: the compute is applied whether or not the operands
  are empty. Write the action if you mean another merge.
- **A tutorial with several cascades** gets one directory per cascade, each
  with its own `einsum.edge` and page. `einsum.edge` transcribes
  `edge_expression` unless it says otherwise with a line such as
  `- Cascade: Bottom-Up`, the name after `Extended Einsum —` in that
  cascade's heading in the tutorial. That cascade must declare its own
  tensors, and its meanings come from the tutorial-data step.
- It must say **what the tutorial says**. The workbench compares the two line
  by line — declarations, initialization, each Einsum's output, operands and
  operators, each arm of a case statement, and the stopping conditions — and
  stops if they differ.

Complete, passing examples are in [`examples/`](examples/); more `einsum.edge` files are in `edge-core-ir/examples/algorithms/`.

### verifier.py

Tells the workbench what the right answer is, by a route that is not your
cascade. It is one file; it may not import a module beside it.

```python
ANSWER_LABEL = "max flow"          # what the page calls the answer
KIND   = "different-algorithm"     # which kind of verifier this is (below)
METHOD = "Edmonds-Karp"            # what `solve` is, by name

def solve(instance):
    """The answer, computed independently."""

def answer(final, instance):
    """The answer, read off the cascade's final tensors."""

def random_instance(rng):
    """A fresh problem in the same shape as the instance."""

def certify(final, instance):      # required only when KIND = "certificate"
    """Everything wrong with the cascade's result; [] when it is valid."""
```

**Choose a kind.** `KIND` says how `solve` gets its answer:

| KIND | `solve` is | example |
|---|---|---|
| `definition` | the problem's definition, checked by enumeration | every subset of rows, for exact cover |
| `library` | a trusted library's implementation | `networkx.maximum_flow`, `scipy.sparse.csgraph.shortest_path` |
| `certificate` | anything, plus `certify`, which checks the cascade's own result is valid | a flow that conserves and saturates a cut |
| `different-algorithm` | a different algorithm for the same problem, written in the file | Edmonds-Karp for push-relabel |
| `user-reference` | a reference implementation you supply; `METHOD` names where it came from | `"dfs.py from the course repo"` |

Do not use a second implementation of the cascade's own method: it shares
your misunderstandings of it. If an AI agent is helping you, it offers you
this choice; if none fits, it builds the verifier from source code you give it
(`user-reference`). The agent never writes the verifier on its own say-so, and
never edits one you have approved.

**What is compared is whatever your tutorial states as its answer.** If the
tutorial publishes the set of vertices a DFS reaches, `solve` and `answer`
return that set; if it publishes the visit order, they return the order (and
the order must then be one every valid run produces). Where a free choice
gives different valid results, compare something they share (BFS depths, not
parents).

- `instance` is `{"extent": {...}, "scalars": {...}, "tensors": {...}}`,
  tensors keyed by coordinate strings: `{"C": {"0,1": 3, "0,2": 2}}`, plus
  `coordSets` if an Einsum is restricted to a named set.
- `final` is `{tensor: {coordinate: value}}` after the last step.
- If the answer is built up along the way rather than left in the final state
  (exact cover finds one solution per success), give `answer` (or `certify`) a
  third parameter, `steps`: every step of the run, each with `output` and `state`.
- Answers are compared after turning sets and tuples into sorted lists.

**Rules `check` enforces**, at the inputs stage, before your cascade runs:

- **Imports:** `networkx`, `scipy`, `numpy`, and the computational standard
  modules (`math`, `itertools`, `collections`, `heapq`, `functools`,
  `fractions`, `bisect`, `operator`, `statistics`, `decimal`, ...). Not
  `random` or `time` (use the `rng` you are given), not `edge_ir` or
  `edge_workbench`, no files, network or subprocesses, no `open`, `eval`,
  `exec`, `__import__`. A library need not be installed everywhere; where it
  is missing, `check` says what to install.
- **Separate routes:** `solve` must not call `answer` or `certify`, directly
  or through a helper, nor they `solve`.
- **`random_instance(rng)`** takes exactly the `rng` and is deterministic:
  the same seed gives the same instance. `check` makes 12, instance *k* from
  its own seed, so one can be rerun alone:
  `python3 -m edge_workbench verify-instance my-algorithm 7`.
- **Small and varied:** extents from 1 to 12; at least 10 of the 12 instances
  differ, with at least 2 different sizes and 3 different answers.
- **`answer` reads the cascade:** given an empty final state it must not
  already agree with `solve` on every instance. Instances with no solution are
  fine; the report counts how many have that trivial answer.

The full contract is at the top of
[`edge_workbench/verifier.py`](edge_workbench/verifier.py).

### Approving the verifier

The verifier is what your cascade is judged against, so it is pinned once you
have read it. In a terminal, yourself:

```
python3 -m edge_workbench approve-verifier path/to/my-algorithm
```

It shows the file (or what changed since you last approved it), its KIND and
METHOD, the answer your tutorial publishes, and the contract checks, and asks
you to type the METHOD to confirm. It writes `verifier.lock` beside
`verifier.py`; commit the two together.

`check` then refuses to go on, and says which of these happened, when:

- `verifier.py` was never approved (there is no `verifier.lock`);
- `verifier.py` has changed since it was approved;
- `verifier.lock` was not written by `approve-verifier` (written or edited by hand);
- the answer your tutorial publishes for its worked example has changed.

Each is fixed the same way: a person reads the change and runs
`approve-verifier` again. The command only runs at a terminal, so an AI agent
cannot run it; an agent that meets one of these stops and tells you. You will
be asked twice for a new tutorial: once for the verifier, and once more when
the tutorial-data step first records the published answer.

An approval counts if `verifier.lock` is the committed one, or was made on
this machine (recorded in `~/.config/edge-workbench/approved.json`).
`check --committed-only` counts only the committed one; the test suite uses it.

## 3. Run the check

From the edge-workbench directory:

```
python3 -m edge_workbench check path/to/my-algorithm
```

Run it as often as you like. Each run does everything it can, lists every
problem it found at once, and ends with **NEXT:** — exactly what to do. It
never writes `index.html` while anything is failing, and removes a stale one.

Everything it generates goes in `my-algorithm/workbench/`. You do not edit
anything there.

## 4. The two model steps

When `check` needs a model it stops with:

```
NEXT:
  1. Open workbench/prompts/builder.txt and paste ALL of it into a Claude chat.
  2. Copy the whole reply and save it as workbench/replies/builder.md.
  3. Run again: python3 -m edge_workbench check my-algorithm
```

Do exactly that. The reply is then checked like anything you wrote yourself;
if it fails, the problems are listed and the prompt is rewritten to include
them, so you paste it again.

| step | the model writes | it is checked by |
|---|---|---|
| **builder** | a Python script that builds the IR from `einsum.edge` (the `.edge` parser is still being built; once it lands, it replaces this step and the checks stay the same) | the IR's own validators; **one IR Einsum per Einsum you wrote, with no tensor you did not write**; every output tensor, generation, `compute(merge)`, named operator and declaration against `einsum.edge`; single-assignment findings exactly those your `einsum.edge` implies (nothing to list by hand); that every Einsum executes; your verifier |
| **tutorial data** | one meaning per Einsum, the worked example as data, how to colour the picture | every meaning quotes your tutorial **verbatim**, in cascade order; the example quotes your tutorial and supplies exactly the inputs the program reads; the published answer is checked against the run |

Pasting costs roughly 10–20 cents of model usage per algorithm, once.

## 5. What a passing run looks like

```
edge-workbench check: set-cover

  ✓ inputs         set_cover.md, einsum.edge, verifier.py (definition: subset enumeration; approved)
  ✓ tutorial       the tutorial's cascade matches einsum.edge
  ✓ builder        build_set_cover_program.py
  ✓ program        20 Einsums -> 25 IR nodes; valid IR; operators and declarations match einsum.edge
  ✓ tutorial data  20 meanings, example, styling (...)
  ✓ instance       bipartite view; supplies ['A', 'Col', 'InitS', 'Row', 'RowCount']
  ✓ page           coverage: 20 written Einsums ...; answer check: 14 checks passed; ...

index.html written: index.html
```

| stage | what it means when it fails |
|---|---|
| inputs | a file is missing, `einsum.edge` has no labels, `verifier.py` breaks one of its rules (each is listed), or the verifier is not approved as it stands |
| tutorial | your tutorial and `einsum.edge` disagree; each difference is listed. Decide which is wrong. |
| builder / program | the model's builder does not match `einsum.edge`; paste the rewritten prompt |
| tutorial data | a meaning or the example does not quote your tutorial, or the example's inputs are wrong |
| instance | the worked example, or a random instance, does not supply what the program reads; or the published answer is not the approved one |
| page — coverage | an Einsum never executed; or an arm of a case statement (or a macro of a multi-output case statement) is reached by neither the worked example nor any random instance. An arm only the random instances reach is named on the line and noted on the page. |
| page — answer check | **your cascade gives a different answer from your verifier** — on your worked example, on the answer your tutorial publishes, or on a random instance. The line reads `random instances: k/12 agree`; rerun a failing one alone with `verify-instance`. |

The answer check is the one that finds mistakes in a specification. Exact
cover's tutorial wrote `TPath = Path · d* :: /\ <(∩)`, which turns depths into
`True`; every structural check passed and the verifier rejected it on 10 of 14
instances.

The picture comes from your `ranks:` block when the tutorial has one (see "The
tutorial"). Without one it is inferred from your tensors: a **graph** when
every rank-1 tensor is over the same rank, **bipartite** when they sit on two
ranks (rows and columns), a **sequence** when there is no rank-2 tensor.

## 6. What you get

`my-algorithm/index.html` — one file. Open it in a browser. Formulas are set
by MathJax, loaded from the web; offline, or in a viewer that blocks it, they
appear in plain text and everything else works the same. Every value it shows was computed by edge-core-ir's
evaluator during `check`; the page only displays that run.

## Things that catch people out

- A stored value equal to a tensor's declared empty value is absent. With
  `G ... empty = 0`, a weight-0 edge is the same as no edge. `check` reports
  this for the worked example and for any instance `random_instance` makes.
- A cascade has 500 generations to reach its stopping condition. Past that,
  `check` stops and says so: either the condition is wrong, or the instance
  never converges (Bellman-Ford on a negative cycle), in which case keep such
  instances out of `random_instance`.

## Not supported yet

- tensors with more than two non-generational ranks in the picture
- a macro used inline, as an anonymous tensor inside an Einsum, or called
  outside a multi-output case statement
- for an inner cascade the page shows every Einsum at every generation of
  both cascades, exactly as written: a range given only in a remark
  (`▷ Pass 0, step j (j ≥ 1)`) is not a restriction
