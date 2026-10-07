# -*- coding: utf-8 -*-
# per-Einsum explanations: what it means on the graph, and what it means in the iteration space
# MEANING used to live here: two sentences per Einsum, one saying what it
# means for the problem and one restating what it does over its iteration
# space. Both are gone.
#
# The first now lives in the tutorial's `einsum_meanings` block -- the author
# writes it, and the build fails when an Einsum has none. The second is
# GENERATED from the IR by edge_workbench/render/action_prose.py, because the
# program already determines which ranks reduce, which merge decides where a
# value exists and which compute combines the operands; restating that by hand
# was 26 paragraphs that nothing checked.



# RANKNAMES, GENERATIONAL and STATEFUL used to live here: three lists saying
# which ranks each tensor is drawn over, which carry a generational rank, and
# which are loop-carried state. All three are DERIVED now, by
# edge_workbench/tensor_facts.py, from the declarations and the cascade's
# generation pattern -- and verified to reproduce these lists exactly.
#
# GENERATIONAL turned out to be read by nothing at all; the page's
# "Generational tensors" panel is driven by GROUPS below.

# DESC used to live here: one line per tensor, shown beside its grid. Gone,
# and it split in two on the way out.
#
# The author's sentence comes from the TUTORIAL -- `problem_statement` for the
# tensors the problem has, and a `tensor_notes` block for the cascade
# intermediates, which the problem statement does not declare because they are
# not part of the problem. The provenance after it is DERIVED by
# edge_workbench/render/tensor_notes.py: which Einsum writes the tensor and
# which read it. That half was never written down anywhere, and for an
# intermediate it is most of what a reader wants to know.

# LaTeX form of each Einsum, matching the notebook's typesetting
# LATEX used to live here: one hand-transcribed formula per Einsum, shown
# above each step. It is now rendered from the IR by
# edge_workbench/render/latex.py, because nothing could check a transcription
# and it turned out to be wrong in four places -- it showed `Adm` for an
# Einsum that writes `AdmPost` (the spec has since adopted that name), named
# E10's compute operator where the
# deciding coordinate operator belongs, dropped one of E08's two labelled Map
# specs, and claimed initialization assigns S and T, which it does not.
#
# MEANING and DESC below are still prose, and still unchecked. They are
# editorial -- what an Einsum is FOR -- which nothing can derive.

# Tensors that carry a value from one generation to the next, as opposed to
# scratch recomputed inside a round. The before/after toggle can step back
# through these; for anything else "before" is the empty tensor.

# Which tensors get a permanent grid, and where. Intermediates are
# deliberately absent: they exist for one Einsum, and the execution panel
# shows each at the moment it is computed and again where it is read,
# which beats a grid that is empty most of the time.
GROUPS = {"static1": ["S", "T", "NST"], "static2": ["C"],
          "state1": ["E", "D", "Act"], "state2": ["F", "R"]}

# Page chrome: what this algorithm calls itself, and where the page links
# back to on the site that hosts it.
TITLE = "EDGE Max-Flow — tensor view"
CRUMB = ('<a href="/algorithms/maximum-flow/">Maximum Flow (Push-Relabel)</a>')
