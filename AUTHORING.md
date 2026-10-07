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

You need Python 3.10+, `node`, and two checkouts side by side:

```
git clone https://github.com/edge-einsums/edge-core-ir
git clone <edge-workbench>
pip install -e edge-core-ir          # the IR classes and validators (needs pydantic)
```

The workbench finds edge-core-ir through `EDGE_IR_REPO`, an installed
`edge_ir`, or `~/Projects/edge-core-ir`, in that order.

## 2. Make a directory with three files

```
my-algorithm/
  my-algorithm.md     the tutorial, exactly as it will appear on the website
  einsum.edge         the cascade in EDGE's ASCII form
  verifier.py         an independent way to get the same answers
```

### The tutorial

Your usual tutorial `.md`. The workbench reads its `edge_expression` (the
cascade, in LaTeX) and its prose. Nothing new needs adding: per-Einsum
meanings and the worked example as data are produced in step 4 and quoted from
your text.

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
- It must say **what the tutorial says**. The workbench compares the two line
  by line — declarations, initialization, each Einsum's output, operands and
  operators, and the stopping condition — and stops if they differ.

Complete, passing examples are in [`examples/`](examples/); more `einsum.edge` files are in `edge-core-ir/examples/algorithms/`.

### verifier.py

Tells the workbench what the right answer is, by a route that is not your
cascade. Prefer a *different* algorithm for the same problem (Edmonds-Karp for
push-relabel, brute force for exact cover): a second implementation of the
same method shares your misunderstandings of it.

```python
ANSWER_LABEL = "max flow"          # what the page calls the answer

def solve(instance):
    """The answer, computed independently."""

def answer(final, instance):
    """The answer, read off the cascade's final tensors."""

def random_instance(rng):          # optional, strongly recommended
    """A fresh problem in the same shape as the instance."""
```

- `instance` is `{"extent": {...}, "scalars": {...}, "tensors": {...}}`,
  tensors keyed by coordinate strings: `{"C": {"0,1": 3, "0,2": 2}}`.
- `final` is `{tensor: {coordinate: value}}` after the last step.
- If the answer is built up along the way rather than left in the final state
  (exact cover finds one solution per success), give `answer` a third
  parameter, `steps`: every step of the run, each with `output` and `state`.
- Answers are compared after turning sets and tuples into sorted lists.

The full contract is at the top of
[`edge_workbench/verifier.py`](edge_workbench/verifier.py).

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

  ✓ inputs         set_cover.md, einsum.edge, verifier.py
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
| inputs | a file is missing, `einsum.edge` has no labels, or `verifier.py` lacks `solve`/`answer` |
| tutorial | your tutorial and `einsum.edge` disagree; each difference is listed. Decide which is wrong. |
| builder / program | the model's builder does not match `einsum.edge`; paste the rewritten prompt |
| tutorial data | a meaning or the example does not quote your tutorial, or the example's inputs are wrong |
| instance | the worked example does not supply what the program reads |
| page — coverage | an Einsum never executed |
| page — answer check | **your cascade gives a different answer from your verifier** — on your worked example, on the answer your tutorial publishes, or on a random instance. The failing instance is printed. |

The answer check is the one that finds mistakes in a specification. Exact
cover's tutorial wrote `TPath = Path · d* :: /\ <(∩)`, which turns depths into
`True`; every structural check passed and the verifier rejected it on 10 of 14
instances.

The picture is chosen from your tensors: a **graph** when every rank-1 tensor
is over the same rank, **bipartite** when they sit on two ranks (rows and
columns), a **sequence** when there is no rank-2 tensor.

## 6. What you get

`my-algorithm/index.html` — one self-contained file. Open it in a browser;
nothing else is needed.

## Not supported yet

- initializations over a named coordinate set (`D_{0, s : s in root_id}`)
- stopping conditions comparing two generations (`D_{i+1} == D_i`)
- user-defined compute operators in the page: an operator your builder
  registers in `*_functions.py` satisfies the IR's validators, but the page
  evaluates in JavaScript and needs its own implementation; `check` names any
  such operator
- tensors with more than two non-generational ranks in the picture
