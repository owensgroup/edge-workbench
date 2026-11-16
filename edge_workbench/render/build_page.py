# -*- coding: utf-8 -*-
import json, re, os, subprocess, sys
from pathlib import Path

# The page is built by EXECUTING THE SPECIFICATION. The driver runs the IR
# over the instance and returns a trace; `annotate` adds the LaTeX, captions
# and highlights that make it readable; this file renders it.
#
# THERE IS NO RECORDED TRACE ANYWHERE IN THIS REPOSITORY. Not as an input, not
# as a fixture, not as something to check against. A recorded trace can only
# answer "does this run match a run someone did before", which stops being a
# useful question the moment the spec is the thing under review -- and it
# quietly makes the recording the authority instead of the specification.
#
# Two gates run before anything is written, and there is no flag to skip them:
#
#   coverage   every Einsum the author wrote executed, and every IR node is
#              claimed by something they wrote. Catches the silent failure --
#              an Einsum that never runs raises nothing and leaves a page that
#              looks complete.
#   answer     the algorithm's own verifier recomputes the result from the
#              driven run and checks it against what is independently known
#              to be true.
#
# Between them: the spec ran in full, and what it produced is right.
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
from edge_workbench import paths                       # noqa: E402

ALG = os.environ.get("EDGE_WORKBENCH_ALG") or "(unnamed)"
HERE = str(paths.RENDER)                 # tool files: display.js, domain_views.js
SPEC = str(paths.spec(ALG))              # IR program, display metadata
OUT = os.environ.get("EDGE_WORKBENCH_OUT", os.path.join(str(paths.ROOT), "build", ALG))
#: Set by `edge_workbench check` for an author's algorithm: their verifier.py.
AUTHOR_VERIFIER = os.environ.get("EDGE_WORKBENCH_VERIFIER")
os.makedirs(OUT, exist_ok=True)

sys.path.insert(0, SPEC)
import meta                                             # noqa: E402

from edge_workbench.driver import run as driver          # noqa: E402
from edge_workbench.render import annotate as ann        # noqa: E402
from edge_workbench.render import latex                  # noqa: E402
from edge_workbench.render import action_prose           # noqa: E402
from edge_workbench.render import tensor_notes           # noqa: E402
from edge_workbench import coverage                      # noqa: E402
from edge_workbench import tensor_facts                  # noqa: E402
from edge_workbench import domain_shape                  # noqa: E402
from edge_workbench import prepare                       # noqa: E402

# What the author wrote, read ONCE by `python3 -m edge_workbench check` into
# spec/authored.json. The build does not open the tutorial.
#
# It used to. Meanings, tensor prose and the published answer all came out of
# the .md while the page was being written, which made a build depend on which
# branch a sibling checkout happened to be on -- and that showed the moment
# work moved to a branch predating the tutorial's last edit: generic captions,
# and three oracle gates failing for no reason to do with the algorithm.
AUTHORED=prepare.load(paths.spec(ALG))


def tutorial_tensor_notes():
    return AUTHORED.get("tensorNotes", {})


def tutorial_meanings():
    """The author's per-Einsum meanings, from the prepared artifact.

    Absent -> empty, and the page falls back to the generic caption.
    `verify_meanings` decides whether that is acceptable; rendering and gating
    are kept apart on purpose.
    """
    return prepare.explained(AUTHORED)


def verify_meanings(cascade, meanings):
    """Every Einsum the author wrote must have a meaning they wrote.

    The author is expected to explain each Einsum; this is what makes that an
    expectation rather than a hope. Loud but not fatal when the tutorial has
    no block at all, so an unmigrated tutorial still builds.
    """
    labels = set(cascade.get("labels", {}))
    if not meanings:
        print("!! no per-Einsum meanings in spec/authored.json -- generic "
              "captions will be used. Run `python3 -m edge_workbench check "
              "<dir>`.", file=sys.stderr)
        return
    missing = sorted(labels - set(meanings))
    print(f"meanings      : {len(labels & set(meanings))}/{len(labels)} "
          f"Einsums explained by the author")
    if missing:
        sys.exit(
            f"\nBUILD ABORTED: the tutorial explains no meaning for "
            f"{missing}.\nAdd a `Graph meaning:` line under each in the "
            f"walkthrough. "
            f"index.html was NOT written."
        )


def _exercised_by_random_instances(cascade):
    """The driver's tally, summed over the verifier's random instances.

    The same instances the answer check runs (`verifier.sample`, seeded by
    the tutorial's name). An instance the cascade cannot run adds nothing
    here; the answer check reports it.
    """
    from edge_workbench import verifier as _v
    mod = _v.load(Path(AUTHOR_VERIFIER))
    total = {}
    for inst in _v.sample(mod, ALG, _v.N_RANDOM).instances:
        if inst is None:
            continue
        try:
            run = _v.final_state(Path(SPEC), inst, 0, cascade)
        except Exception:                                  # noqa: BLE001
            continue
        for key, n in run["executed"].items():
            total[key] = total.get(key, 0) + n
    return total


def verify_coverage(program, cascade, executed):
    """Every Einsum the author wrote must have run.

    This is the gate that replaced comparing against a recorded trace, and it
    asks a question the recording never could: not "does this match what
    happened before" but "did the specification in front of me execute".

    The failure it catches is silent. An Einsum that never runs produces no
    wrong value and raises nothing; it just leaves a page whose step list
    looks complete. Nothing else in the build would notice.

    It works off the driver's own per-IR-node tally rather than the emitted
    steps, because the two differ on purpose: initialization runs four
    Einsums and emits one step, a lowered `cases` runs three and emits one.
    """
    cov = coverage.measure(program, cascade, executed)
    if cov.needs_instances and AUTHOR_VERIFIER:
        # An arm of a case statement or of a conditional cascade that the
        # worked example never reaches: it must be exercised by one of the
        # verifier's random instances, whose answers the next gate checks.
        cov = coverage.measure(program, cascade, executed,
                               _exercised_by_random_instances(cascade))
    elif cov.needs_instances:
        cov = coverage.measure(program, cascade, executed, {})
    print("coverage      :", cov.summary())
    if not cov.ok:
        sys.exit("\nBUILD ABORTED: the specification did not fully execute.\n"
                 + cov.report() + "\nindex.html was NOT written.")
    return cov


def verify_algorithm():
    """Run the author's verifier.py against this run.

    Coverage proves the spec ran. This is the other question: is what it
    produced right? Only the algorithm can answer that, so the verifier lives
    beside the tutorial and the tool only knows how to run it.

    Required: a page whose answer nothing checked is not published.
    """
    # `verifier.py` is written to the contract in edge_workbench/verifier.py;
    # the tool runs it against this spec.
    if AUTHOR_VERIFIER:
        r=subprocess.run([sys.executable,"-m","edge_workbench.verifier",
                          "--spec",SPEC,"--verifier",AUTHOR_VERIFIER,
                          "--slug",ALG],
                         capture_output=True,text=True,cwd=str(paths.ROOT))
        tail=[l for l in r.stdout.strip().splitlines() if l.strip()]
        print("answer check  :", tail[-1].strip() if tail else "(no output)")
        if r.returncode!=0:
            sys.stdout.write(r.stdout); sys.stderr.write(r.stderr)
            sys.exit(f"\nBUILD ABORTED: {ALG} failed its verifier.\n"
                     f"index.html was NOT written.")
        return
    sys.exit(f"\nBUILD ABORTED: {ALG} has no verifier.py. Run the page "
             f"through `python3 -m edge_workbench check`, which supplies it.\n"
             f"index.html was NOT written.")



# ---- the trace, produced by running the spec -----------------------------
INSTANCE=json.load(open(os.path.join(SPEC,"instance.json")))
CASCADE=json.load(open(os.path.join(SPEC,"cascade.json")))
ALIAS=CASCADE.get("displayNames",{})
_run=driver.run(ALG)

# Both gates, on this run's own output. Coverage first: if the spec did not
# fully execute, whether the answer happens to be right is beside the point.
IR_PROGRAM=json.load(open(driver._program_file(paths.spec(ALG))))
_COVERAGE=verify_coverage(IR_PROGRAM, CASCADE, _run["executed"])
verify_meanings(CASCADE, tutorial_meanings())
verify_algorithm()

NAMED_VIEW = INSTANCE.get("domain", {}).get("view")

# WHICH PICTURE THIS PROGRAM WANTS: the tutorial's `ranks:` block when it has
# one (carried in cascade.json), otherwise derived from the program. The
# derivation's signal is where the rank-1 tensors live: max-flow's twelve are
# all over U, so the two ranks of a rank-2 tensor index the same set and the
# picture is a graph. Exact cover's split 17 on R and 6 on C, so they are
# different sets and the picture is bipartite.
# A `view` named in the instance that CONTRADICTS it fails below rather than
# silently winning.
DERIVED_VIEW = domain_shape.classify(
    IR_PROGRAM, INSTANCE, CASCADE.get("generationalRank", "I"),
    CASCADE.get("rankKinds"))

# The left pane's heading. It was the literal word "Graph" for every
# algorithm, which was true of the only algorithm there was. Exact cover has
# no graph: it is a row/column incidence picture, and calling it a graph tells
# a reader to look for something that is not there.
PANEL_TITLE = {
    domain_shape.GRAPH: "Graph",
    domain_shape.BIPARTITE: "Rows and columns",
    domain_shape.SEQUENCE: "Positions",
}.get(NAMED_VIEW or DERIVED_VIEW["view"], "Domain")



# One implementation, in domain_shape beside `classify`; author.py folds
# the same findings into its instance stage. Fatal here because a page is
# about to be written and there is no stage left to report to.
_view_problems = domain_shape.disagreement(
    NAMED_VIEW, IR_PROGRAM, INSTANCE, CASCADE.get('generationalRank', 'I'),
    where=f'{ALG}/spec', kinds=CASCADE.get('rankKinds'))
if _view_problems:
    for _p in _view_problems:
        print(f"!! {_p}", file=sys.stderr)
    sys.exit(1)
print(f"domain view   : {NAMED_VIEW or DERIVED_VIEW['view']}"
      + ("" if NAMED_VIEW else " (derived)")
      + f" -- {DERIVED_VIEW['reason']}")

LATEX=latex.render_all(IR_PROGRAM, CASCADE, ALIAS)
# The formulas as the author wrote them, written by `check` from the tutorial.
# Absent for a spec built without it, which then shows the IR's form.
_written_path=paths.spec(ALG)/"written.json"
WRITTEN=json.loads(_written_path.read_text()) if _written_path.exists() else {}
T=ann.annotate({"steps":_run["steps"]}, meta, LATEX)
T["iterations"]=_run["generations"]
# The outer cascade's iterative rank variable, for the generation badge.
from edge_workbench import cascade_shape as _shape     # noqa: E402
_placed=_shape.placement(IR_PROGRAM)
T["genVar"]=(_placed[0]["ranks"][0] if _placed and _placed[0]["ranks"] else "i")
# In a bipartite picture a node id carries its side (`R:0`, `C:2`), because
# row 0 and column 0 are different nodes. The generic highlight speaks bare
# indices, so qualify them by the ranks of the tensor each step wrote.
if (NAMED_VIEW or DERIVED_VIEW["view"]) == domain_shape.BIPARTITE:
    _ranks_of = tensor_facts.all_facts(IR_PROGRAM, CASCADE)["rankNames"]
    for _s in T["steps"]:
        _rk = _ranks_of.get(_s.get("output") or "", [])
        _hl = _s.get("graphHighlight") or {}
        if len(_rk) == 1:
            _hl["nodes"] = [domain_shape.qualify(_rk[0], n)
                            for n in _hl.get("nodes", [])]
        if len(_rk) == 2:
            _hl["edges"] = [[domain_shape.qualify(_rk[0], a),
                             domain_shape.qualify(_rk[1], b)]
                            for a, b in _hl.get("edges", [])]
T["graph"]=INSTANCE.get("domain",{}).get("graph")
T["note"]=("computed by edge-core-ir's reference evaluator over the instance; "
           "no part of this page comes from a hand-written implementation")
if _COVERAGE.not_on_example:
    # Arms this example never takes are not steps, so nothing else on the
    # page would say they exist.
    T["notReached"]=_COVERAGE.not_on_example
    T["note"]+=("; this example never reaches "
                + ", ".join(_COVERAGE.not_on_example)
                + " (checked on the verifier's random instances instead)")
if AUTHOR_VERIFIER:
    # The number in the corner is the verifier's reading of the final state:
    # the same function the answer gate just checked against `solve`.
    from edge_workbench import verifier as _verifier
    _v=_verifier.load(Path(AUTHOR_VERIFIER))
    _ans=_verifier.normalise(
        _verifier.read_answer(_v,{"steps":_run["steps"]},INSTANCE))
    # A list of lists (exact cover's solutions) reads as sets; JS would
    # otherwise flatten it into one run of numbers.
    if isinstance(_ans,list) and all(isinstance(x,list) for x in _ans):
        _ans=", ".join("{"+", ".join(map(str,x))+"}" for x in _ans) or "none"
    # A mapping (Bellman-Ford's vertex -> distance) reads as "key: value",
    # numeric keys in numeric order.
    elif isinstance(_ans,dict):
        _ans=", ".join(f"{k}: {v}" for k,v in sorted(
            _ans.items(), key=lambda kv:(not kv[0].lstrip("-").isdigit(),
                                         int(kv[0]) if kv[0].lstrip("-").isdigit() else 0,
                                         kv[0]))) or "none"
    T["headline"]={"label":getattr(_v,"ANSWER_LABEL","answer"),"value":_ans}
print(f"driven trace  : {len(T['steps'])} steps, "
      f"{T['iterations']} generations"
      + (f", {T['headline']['label']} {T['headline']['value']}"
         if "headline" in T else ""))
# The IR program and the display helpers get inlined so the page stays a
# single self-contained file. The page evaluates nothing: every value it shows
# was computed by edge-core-ir's evaluator at build time (driver/run.py).
IR=json.load(open(driver._program_file(paths.spec(ALG))))
INTERP=open(os.path.join(HERE,"display.js"),encoding="utf-8").read()
# The domain views are a module too, so they can be tested without a page.
DVIEWS=open(os.path.join(HERE,"domain_views.js"),encoding="utf-8").read()

# Spec einsum label -> position in the IR cascade, read from the algorithm's
# own cascade.json rather than repeated here. A label mapping to a LIST is one
# written Einsum lowered to several IR nodes. The drill-down needs this to
# recompute the Einsum the reader is looking at.
EINSUM_IDX=CASCADE.get("labels",{})


def trace_header(T):
    """Name the renderer this trace wants, and nothing else.

    This used to carry a whole compare-mode header -- variant, generations,
    operation counts, per-step generation and `opKind` -- so two traces could be
    raced against each other. Nothing races any more, and every one of those
    fields was dead: the page reads exactly one thing from here.

    `domainView` is that thing, and it is what keeps the viewer
    algorithm-agnostic. A trace names its renderer; a matrix view for a
    non-graph algorithm is a new entry in DOMAIN_VIEWS rather than surgery on
    the viewer.
    """
    T["algorithm"] = ALG
    T["domainView"] = NAMED_VIEW or DERIVED_VIEW["view"]
    return T



# What the page needs to know about each tensor, DERIVED from the program.
# These were three hand-written lists in the algorithm's meta.py, restating
# what the declarations and the cascade's generation pattern already say.
#
# `stateful` -- which tensors the before/after toggle can step back through --
# is the one worth watching. The obvious rule ("written at i+1 and read at a
# plain i") returns thirteen tensors here where five are carried; see
# edge_workbench/tensor_facts.py for the clause that fixes it.
# What each tensor is, beside its grid. The author's sentence comes from the
# tutorial -- problem_statement for the tensors the problem has, tensor_notes
# for the cascade intermediates -- and the provenance line after it is DERIVED:
# which Einsum writes the tensor and which read it. That half was never
# written anywhere, and for an intermediate it is most of what a reader wants.
DESCS=tensor_notes.combine(IR_PROGRAM, CASCADE, tutorial_tensor_notes(), ALIAS)
FACTS=tensor_facts.all_facts(IR_PROGRAM, CASCADE)
RANKNAMES=FACTS["rankNames"]
# Which rank each tensor is indexed by. A bipartite picture has two node sets
# and a tensor belongs to exactly one of them; without this a row marking
# would be read at a column's index.
TENSORSIDE={n:(r[0] if len(r)==1 else "") for n,r in RANKNAMES.items()}
RANKS={n:len(r) for n,r in RANKNAMES.items()}
STATEFUL=FACTS["stateful"]
# How the domain view draws this algorithm. Everything in here is data: the
# layout, which tensor labels a node, which colours a vertex. A second graph
# algorithm is a different block, not a different renderer.
DOMAIN=dict(INSTANCE.get("domain",{}))
DOMAIN.setdefault("positions",{})
# Page chrome: the algorithm's own name for itself, and where it links back to.
TITLE=getattr(meta,"TITLE",ALG+" — tensor view")
CRUMB=getattr(meta,"CRUMB",getattr(meta,"TITLE",ALG))
EXTENTS=INSTANCE.get("extent",{})
# Only the tensors that persist: the fixed inputs and the generational state.
# Intermediates are no longer given permanent blocks -- they exist for one
# Einsum, and the execution panel shows each one at the moment it is computed
# and again where it is read, which is more informative than a grid that is
# empty most of the time.
GROUPS=getattr(meta,"GROUPS",{})

# Every grid states the tensor's declared empty value, because absence means
# something different on each one: 0 on a flow, +inf on a height, false on a
# predicate. The page reads it from the inlined IR at render time, so it cannot
# drift -- but a tensor with no declaration would silently lose its label, so
# fail the build instead.
_DECL={d["name"]: d for d in IR["declarations"]}
for _g in GROUPS.values():
    for _n in _g:
        if _n not in _DECL:
            sys.exit("tensor %r is drawn but not declared in the IR" % _n)
        if _DECL[_n].get("empty_value") is None:
            sys.exit("tensor %r has no empty_value in the IR; every grid "
                     "labels one" % _n)
# The formula and the generation both come from the IR. Neither is prose,
# and neither can disagree with what runs -- which the hand-written table
# demonstrably could: it showed `Adm` for an Einsum that writes `AdmPost`,
# named the wrong operator as E10's choice function, and quietly dropped one
# of E08's two labelled Map specs.
OUTGEN=latex.generations(IR_PROGRAM, CASCADE)
# The two halves of each explanation. What an Einsum MEANS for the problem comes
# from the tutorial. What it DOES is the author's too when the walkthrough says,
# and otherwise is generated from the program. Neither is retyped here.
MEANINGS=tutorial_meanings()
TOLD={k:v["einsum"] for k,v in AUTHORED.get("tutorialMeanings",{}).items() if v.get("einsum")}
ACTIONS=action_prose.describe_all(IR_PROGRAM, CASCADE, ALIAS)
for s in T["steps"]:
    s["graphMeaning"]=MEANINGS.get(s["einsum"], s.get("caption",""))
    s["einsumMeaning"]=TOLD.get(s["einsum"]) or ACTIONS.get(s["einsum"], "")
    _ir,_tex=LATEX.get(s["einsum"],""),WRITTEN.get(s["einsum"])
    s["latex"]=_tex or _ir
    if s["einsum"]==CASCADE.get("initLabel","init"):
        s["setupSteps"]=AUTHORED.get("setupSteps",[])
    s["expr"]=s["latex"]        # what shows until MathJax loads, or if it can't
    # The labelled parts the run actually steps through, where the written
    # form does not already carry them: shorthand, or a function like sigma.
    s["latexParts"]=_ir if _tex and r"\cdot^" in _ir and r"\cdot^" not in _tex else ""
    # Definitions the written form uses, e.g. the stamp function sigma.
    s["latexDefs"]=[d for d in WRITTEN.get("definitions",[])
                    if _tex and re.match(r"\\?[A-Za-z]+",d).group(0)+"(" in _tex]
    gen=OUTGEN.get(s["einsum"])
    s["outGen"]=gen if gen in ("i","i+1") or (gen or "").isdigit() else None
    s["stateful"]=s.get("output") in STATEFUL
    s["hasPrior"]=bool(s.get("output")) and s["einsum"]!="stop"

_sets=tensor_facts.coord_sets(IR_PROGRAM)
T["coordSets"]=[{"name":n,"rank":_sets.get(n,""),"members":m}
                for n,m in (INSTANCE.get("coordSets") or {}).items()]

HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>PAGETITLE</title>
<script>window.MathJax={tex:{inlineMath:[["\\(","\\)"]],displayMath:[["\\[","\\]"],["$$","$$"]],
  packages:{"[+]":["ams"]}},chtml:{scale:1.0},startup:{typeset:false}};</script>
<script async id="mjx" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&display=swap" rel="stylesheet">
<style>
.site-header{padding:1.4rem 0 1rem;border-bottom:1px solid #ddd;background:#fff}
.wrap{width:min(1500px,95vw);margin:0 auto}
.site-title{font-family:'Libre Baskerville',serif;font-size:1.45rem;text-decoration:none;color:#222}
.crumb{margin:.3rem 0 0;color:#777;font-size:.95rem}
.crumb a{color:#4b7bec;text-decoration:none} .crumb a:hover{text-decoration:underline}
.site-footer{padding:1.2rem 0 2rem;border-top:1px solid #ddd;color:#888;font-size:.9rem}
  border-radius:7px;background:#fff;cursor:pointer;margin:0;line-height:1.3}
*{box-sizing:border-box} body{margin:0;font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;background:#fafafa;color:#222}
#top{display:flex;gap:14px;padding:14px 0;align-items:flex-start;width:min(1500px,95vw);margin:0 auto}
#left{flex:0 0 560px} #right{flex:1;min-width:0}
.panel{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px;margin-bottom:12px}
h3{margin:0 0 8px;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:#888;font-weight:600}
h3 .sub{text-transform:none;letter-spacing:0;color:#aaa;font-weight:400;font-size:11px}
h3 .sub i{font-style:italic;color:#4b7bec}
h4{margin:14px 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:#aaa;font-weight:600}
#bar{position:sticky;bottom:0;background:#fff;border-top:1px solid #ddd;padding:10px 0}
#bar .wrap{display:flex;align-items:center;flex-wrap:wrap;gap:6px}
#now{border-color:#c9d8f0;background:#fcfdff}
#itbadge{display:inline-block;background:#4b7bec;color:#fff;border-radius:12px;padding:2px 12px;
  font-weight:600;font-size:13px;margin-right:9px;font-family:Georgia,serif}
#itbadge i{font-style:italic}
#stepno{color:#888;font-size:12px} #flow{float:right;font-weight:600;color:#2b8a3e}
#expr{overflow-x:auto;background:#f4f6f8;border-left:3px solid #4b7bec;padding:6px 12px;border-radius:3px;
  min-height:50px;overflow-x:auto;font-size:15px;font-family:"Latin Modern Math","Cambria Math",Georgia,serif}
#expr mjx-container{margin:.25em 0!important;text-align:left!important}
#expr i{font-style:italic} #expr sub,#expr sup{font-size:.68em}
#expr .op{font-size:1.25em;vertical-align:-.08em;padding:0 1px}
#expr .sep{color:#4b7bec;font-weight:600;padding:0 5px}
.cset{font-family:ui-monospace,monospace;font-size:12px;padding:4px 2px}
#ss{margin:0;padding-left:1.2em} #ss li{margin:1px 0}
#expr .exsub{font-size:.82em;color:#556;margin-top:2px;overflow-x:auto}
#expr .exsub b{font-weight:600;color:#778;font-size:.86em;letter-spacing:.02em}
#expr .eid{color:#adb5bd;font-family:ui-monospace,monospace;font-size:.72em;margin-right:10px}
.mean{margin-top:9px;display:grid;grid-template-columns:104px 1fr;gap:3px 9px;font-size:12.5px}
.mean b{color:#888;font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.06em;padding-top:2px}
button{font:inherit;padding:5px 11px;margin-right:5px;border:1px solid #bbb;background:#fff;border-radius:5px;cursor:pointer}
button:hover{background:#f0f0f0} #slider{width:100%;margin:8px 0 0}
.row{display:grid;gap:9px 16px;justify-content:start}
.r2{grid-template-columns:repeat(2,max-content)}.r3{grid-template-columns:repeat(3,max-content)}
.r4{grid-template-columns:repeat(4,max-content)}
/* Rank-1 tensors are drawn as columns, so they are narrow enough to sit six
   abreast -- one row of columns, the same height as a row of U x V grids. */
.r6{grid-template-columns:repeat(6,max-content)}
.tname{font-weight:600;font-size:11px;margin:0 0 3px;font-family:ui-monospace,monospace;color:#333;cursor:help}
.tname sup{font-size:.82em;color:#888;font-weight:400}
/* The declared empty value. Every grid draws absence the same way -- hatched
   -- but what absence MEANS is per-tensor: 0 for a flow, +inf for a height,
   false for a predicate. Without this label the hatching is ambiguous. */
.emp{font-weight:400;color:#b08968;font-size:.9em;margin-left:5px;
  white-space:nowrap}
.emp b{font-weight:600;color:#9c6644}
.cap .emp{font-size:.88em;margin-left:4px}
.tblock{padding:3px;border-radius:4px} .tblock.off .tname{color:#ccc}
.tblock.active{background:#fff4e6;outline:2px solid #ffa94d}
.tblock.before{background:#eef4fb;outline:2px dashed #74a0e0}
.tblock.before .tname{color:#3b6fb8}
#beforebar{display:none;margin-top:7px;background:#eef4fb;border:1px dashed #74a0e0;
  border-radius:6px;padding:5px 9px;font-size:12px;color:#33528a}
body.showing-before #beforebar{display:block}
#nowhead{display:flex;align-items:center;gap:10px}
#btog{margin-left:auto;font-size:12px;padding:3px 10px;border:1px solid #74a0e0;
  border-radius:5px;background:#f4f8fd;color:#33528a;cursor:pointer}
#btog:hover{background:#e6eff9}
#btog[aria-pressed="true"]{background:#dbe7f8;border-color:#4a7fce;color:#1f3d6f;font-weight:600}
.tblock.active .tname{color:#e8590c}
.tblock.active .grid td{cursor:pointer}
.tblock.active .grid td:hover{outline:2px solid #9c6ade;outline-offset:-2px}

/* ------------------------------------------------- execution panel */
/* The drill-down used to be a modal behind an "expand" button. Nobody
   pressed it, and it is the part that explains the execution, so it now
   sits inline under the Einsum -- and the intermediate tensors it draws
   are the reason there is no longer an intermediates panel. */
#execpanel{margin-top:14px;padding-top:12px;border-top:1px solid #ececec}
#exech{margin:0 0 9px}
#execpanel.off{opacity:.55}
#execpanel.off #execsplit{display:none}
#execsplit{margin-top:12px;padding-top:12px;border-top:1px solid #eee}
#execsplit h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;
  color:#999;margin:0 0 7px;font-weight:700}
.h3sub{text-transform:none;letter-spacing:0;font-weight:400;color:#bbb}
table.fold tr.kept td{background:#e3f1fd;font-weight:700}
.tcard.aftermap .cap,.tcard.afterreduce .cap{color:#5f3dc4}
.tcard.aftermap .mini td.fiber:not(.rd){background:#e9e0fb;box-shadow:inset 0 0 0 1px #b9a3ec}
.tcard.aftermap .mini td.fiber{box-shadow:0 0 0 1px #7950f2}
.mini td.pick{cursor:pointer}
.mini td.pick:hover{outline:2px solid #9c6ade;outline-offset:-2px}
.tstrip{display:flex;flex-wrap:wrap;align-items:flex-start;gap:14px}
.tcard{flex:none}
.tcard .cap{font-family:ui-monospace,monospace;font-size:11px;font-weight:600;
  color:#444;margin-bottom:3px}
.tcard .cap .gen{color:#999;font-weight:400}
.finished{color:#2b8a3e;font-weight:600}
.note2{font-size:11.5px;color:#666;background:#f8f9fa;border-left:3px solid #dee2e6;
  padding:7px 11px;border-radius:0 5px 5px 0;margin-top:11px;line-height:1.55}
.tcard.out .cap{color:#5f3dc4}
/* A parenthesised sub-expression: a real tensor in EDGE, but not one the
   cascade names or keeps. Tinted so it reads as a step, not an operand. */
.tcard.inter .cap{color:#0b7285}
.tcard.inter .mini td{background:#fbfeff}
.tcard.inter .mini td.abs{background:repeating-linear-gradient(45deg,#fafdfe,#fafdfe 3px,#eef6f8 3px,#eef6f8 6px)}
.arrow{align-self:center;font-size:19px;color:#c9c2d6;padding:0 2px}
.mini{border-collapse:collapse;font-family:ui-monospace,monospace}
.mini td,.mini th{width:25px;height:20px;text-align:center;font-size:10px;padding:0;
  border:1px solid #e8e8e8;color:#555}
.mini th{color:#c4c4c4;font-weight:500;border:none;font-size:9px}
/* "V:u \ U:v" is wider than a data cell, so let the corner header size itself. */
.mini th.rk{color:#4b7bec;font-weight:700;width:auto;padding:0 5px;
  white-space:nowrap;letter-spacing:.02em}
.mini td.abs{background:repeating-linear-gradient(45deg,#fafafa,#fafafa 3px,#f0f0f0 3px,#f0f0f0 6px);
  color:transparent}
/* the cells this point actually reads, and the cell it writes */
.mini td.rd{background:#d0ebff;color:#0b4f87;font-weight:700;
  outline:2px solid #4dabf7;outline-offset:-2px}
.mini td.wr{background:#e5d9fb;color:#4c2f9e;font-weight:700;
  outline:2px solid #9c6ade;outline-offset:-2px}
#mpoint h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;
  color:#999;margin:0 0 7px;font-weight:700}
.collapse{margin-top:8px;font-size:11.5px;color:#5f3dc4;background:#faf7ff;
  border:1px solid #d9c9f5;border-radius:6px;padding:6px 10px;line-height:1.5;max-width:760px}
.fold{border-collapse:collapse;font-size:12px;margin-top:4px;font-family:ui-monospace,monospace}
.fold td{padding:3px 9px;border-top:1px solid #eee}
.fold td.acc{color:#5f3dc4;font-weight:700}
.fold tr.total td{border-top:2px solid #d9c9f5;font-weight:700}
.spacenote{margin-top:10px;font-size:11.5px;color:#666;max-width:760px;line-height:1.55}
.spacenote:empty{display:none}   /* no reduction: no gap either */
.spacenote b{color:#5f3dc4}
#mpoint{font-size:13px;min-width:0}
.deriv{border-collapse:collapse;width:100%;font-size:12.5px}
.deriv td{padding:6px 9px;border-top:1px solid #eee;vertical-align:top}
.deriv td.k{color:#888;width:118px;font-size:11px;text-transform:uppercase;
  letter-spacing:.05em;white-space:nowrap}
.mono{font-family:ui-monospace,monospace}
.op{display:inline-block;padding:1px 6px;border-radius:4px;background:#f1f3f5;
  font-family:ui-monospace,monospace;font-size:11.5px}
.op.mg{background:#e7f5ff;color:#1864ab}
.op.cp{background:#fff4e6;color:#c2410c}
.pill{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;font-weight:600}
.pill.yes{background:#d3f9d8;color:#2b8a3e}
.pill.no{background:#f1f3f5;color:#999}
.tt{border-collapse:collapse;font-size:11px;margin-top:5px;font-family:ui-monospace,monospace}
.tt td,.tt th{border:1px solid #e3e3e3;padding:2px 7px;text-align:center;color:#777}
.tt th{background:#fafafa;font-weight:600;font-size:10px}
.tt td.hit{background:#e7f5ff;color:#1864ab;font-weight:700}
.step{margin:0 0 13px;padding:9px 12px;border-left:3px solid #dee2e6;background:#fcfcfd;
  border-radius:0 6px 6px 0}
.step.out{border-left-color:#9c6ade;background:#faf7ff}
.step h4{margin:0 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#888}
.opnd{font-family:ui-monospace,monospace;font-size:12px;margin:2px 0}
.opnd .v{font-weight:700;color:#1864ab}
.opnd .abs{color:#aaa;font-style:italic}
.note{margin-top:11px;font-size:11.5px;color:#666;background:#fff9db;
  border:1px solid #ffe066;border-radius:6px;padding:7px 10px;line-height:1.5}
.grid{border-collapse:collapse}
.grid td,.grid th{width:23px;height:19px;text-align:center;font-size:10px;padding:0;
  border:1px solid #e3e3e3;font-family:ui-monospace,monospace}
.grid th{color:#bbb;font-weight:500;border:none;font-size:9px}
.grid th.rk{color:#4b7bec;font-weight:700;font-size:9px}
td.absent{background:repeating-linear-gradient(45deg,#f7f7f7,#f7f7f7 3px,#ececec 3px,#ececec 6px);color:transparent}
td.zero{background:#fff;color:#c4c4c4}
td.chg{animation:flash 1.1s ease-out}
@keyframes flash{0%{box-shadow:inset 0 0 0 3px #fd7e14}100%{box-shadow:inset 0 0 0 3px transparent}}
#legend{font-size:11px;color:#777;margin-top:8px;line-height:1.7}
#legend span{display:inline-block;margin-right:12px}
#legend .sw{display:inline-block;width:11px;height:11px;vertical-align:-1px;border:1px solid #ddd;margin-right:3px}
#legend i{font-style:italic;color:#555}
#legend code{background:#f1f3f5;padding:1px 4px;border-radius:3px;font-size:10.5px}
#tip{position:fixed;display:none;max-width:290px;background:#212529;color:#fff;font-size:12px;
  line-height:1.45;padding:7px 9px;border-radius:5px;z-index:99;pointer-events:none}
svg text{font-family:-apple-system,Segoe UI,sans-serif}
</style></head><body>
<div id="tip"></div>
<header class="site-header"><div class="wrap">
  <a class="site-title" href="/">EDGE Algorithms</a>
  <p class="crumb">CRUMBHTML
     &nbsp;›&nbsp; interactive tensor walkthrough</p>
</div></header>
<div id="top">
 <div id="left">
  <div class="panel"><h3>PANELTITLE</h3><svg id="g" width="540" height="310"></svg>
   <div id="legend">
    <div id="domlegend"></div>
    <div id="fillegend"><span><span class="sw" style="background:#e8590c"></span>touched this step</span></div>
    <div><span><span class="sw" style="background:#fff"></span>stored 0</span>
     <span><span class="sw" style="background:repeating-linear-gradient(45deg,#f7f7f7,#f7f7f7 3px,#ececec 3px,#ececec 6px)"></span>empty
      — <b>what empty means is per tensor</b>, so every grid carries its declared
      value as <span class="emp">∅ <b>0</b></span>, <span class="emp">∅ <b>+∞</b></span>
      or <span class="emp">∅ <b>false</b></span></span>
     <span><span class="sw" style="background:#a5c8f0"></span>positive</span><span><span class="sw" style="background:#f0b0b0"></span>negative</span>
     <span><span class="sw" style="background:#8ce99a"></span>true</span></div>
   </div></div>
  <div class="panel"><h3>Static tensors <span class="sub">— no rank I; never change</span></h3>
   <div id="static1" class="row r3"></div><h4>&nbsp;</h4><div id="static2" class="row r2"></div></div>
 </div>
 <div id="right">
  <div class="panel" id="now">
   <div id="nowhead"><span id="itbadge"></span><span id="stepno"></span><span id="flow"></span>
    <button id="btog" aria-pressed="false" title="Show the output tensor as it was before this Einsum ran. Hold B to peek.">⇄ before / after</button>
</div>
   <div id="expr"></div>
   <div class="mean"><b id="mglabel">Meaning</b><span id="mg"></span><b id="sslabel" style="display:none">Setup steps</b><ol id="ss" style="display:none"></ol><b>Einsum meaning</b><span id="me"></span></div>
   <div id="beforebar"></div>
   <div id="execpanel">
   <h3 id="exech">How this Einsum executes
     <span class="sub" id="execsub"></span></h3>
   <div class="tstrip" id="tstrip"></div>
   <div class="spacenote" id="snote"></div>
   <div id="execsplit">
     <div id="mpoint"><h3>How this value is computed</h3><div id="pbody"></div></div>
   </div>
   </div>
  </div>
  <div class="panel"><h3>Generational tensors <span class="sub">— have rank I; carry state across iterations</span></h3>
   <div id="state1" class="row r3"></div><h4>&nbsp;</h4><div id="state2" class="row r2"></div></div>
 </div>
</div>
<div id="bar"><div class="wrap">
 <button id="first">⏮</button><button id="prev">◀</button><button id="play">▶ play</button>
 <button id="next">▶</button><button id="last">⏭</button><button id="nextit">next iteration ⇥</button>
 <label style="margin-left:10px">speed <input id="speed" type="range" min="60" max="1200" value="840" style="vertical-align:-3px" title="slide right to go faster"></label>
 <input id="slider" type="range" min="0" value="0">
</div></div>
<footer class="site-footer"><div class="wrap"><p>EDGE is a notation for Extended General Einsums for Graph Algorithms.</p></div></footer>
<script>
/*INTERPRETER*/
</script>
<script>
const IR=IRPROGRAM, EIDX=EINSUMIDX;
</script>
<script>
const TENSORSIDE=TSIDEMAP;
const T=TRACE,DOM=DOMAINCFG,POS=DOM.positions||{},RANKS=RANKMAP,GROUPS=GROUPMAP,RN=RANKNAMES,DESC=DESCS;
/* Which rank runs down a grid and which across, from the program: the first
   two-rank tensor declared keeps its first rank down and its second across
   (max-flow's U x V, exact cover's R x C, Bellman-Ford's S x D), and every
   other grid lines up with it. */
const AXES=(()=>{
  const two=IR.declarations.map(d=>d.ranks.filter(r=>r.name!=='I').map(r=>r.name))
    .find(r=>r.length===2)||[];
  return {down:two[0]||null,across:two[1]||null};})();
// A rank variable walks the rank it names in lower case: u walks U, r walks R.
const rankOfVar=(v)=>String(v).toUpperCase();
/* The extent comes from the instance, not from the picture: an algorithm
   with no graph still has ranks to size its grids by. */
const EXTENT=EXTENTMAP;
// Each axis is as long as its own rank: exact cover has 4 rows and 3 columns.
// A rank the instance gives no extent for takes the longest one.
const sizeOf=(rank)=>EXTENT[rank]??N;
const N=Math.max(...Object.values(EXTENT)),
      EDGES=(DOM.graph&&DOM.graph.edges)||[];
let cur=0,timer=null,showBefore=false; const $=id=>document.getElementById(id);
$('slider').max=T.steps.length-1;

// The formula when MathJax cannot load: offline, or a viewer that blocks it.
function typeset(s){
  return EdgeDisplay.plainFormula(s)
    .replace(/([⋀⋁⋘])/g,'<span class="op">$1</span>')
    .replace(/::/g,'<span class="sep">::</span>');
}
/* The domain legend is written from the same block that drives the drawing,
   so a page cannot describe one picture and draw another. */
(function domainLegend(){
  const el2=(h)=>{const d=document.createElement('div');d.innerHTML=h;return d;};
  const parts=[];
  if(DOM.edgeLabel){
    const L=DOM.edgeLabel;
    const ev=(RN[L.tensor]||[]).map(r=>r.toLowerCase()).join(',');
    parts.push('<b>on each edge</b> <code>'+L.tensor+'('+ev+')'+
      (L.over?' / '+L.over:'')+'</code>');}
  if((DOM.nodeLabels||[]).length){
    parts.push('<b>on each node</b> '+(DOM.nodeLabels||[]).map(
      (L)=>'<code>'+(L.prefix||'')+'</code> '+L.tensor).join(', '));}
  if(parts.length)$('domlegend').innerHTML=parts.join(' &nbsp;·&nbsp; ');
  const fills=(DOM.nodeFill||[]).map(
    (r)=>'<span><span class="sw" style="background:'+r.color+'"></span>'+
         (r.label||r.tensor)+'</span>').join('');
  $('fillegend').insertAdjacentHTML('afterbegin',fills);
})();

const NS='http://www.w3.org/2000/svg';
function el(n,a){const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;}
/*DOMAINVIEWS*/
/* The domain views are a module so they can be tested without building a
   page; the page supplies what they used to read from globals here. */
const DOMAIN_VIEWS=EdgeDomainViews.makeViews({
  el:el, DOM:DOM, POS:POS, EDGES:EDGES, tensorSide:TENSORSIDE});

// The main pane always draws the EDGE trace into #g.
function drawGraph(st,hl,pv){
  const v=DOMAIN_VIEWS[T.domainView];
  if(!v){$('g').innerHTML='';return;}          // no view: leave the pane blank
  v($('g'),st,hl,pv);}
function cell(val,changed){const td=document.createElement('td');
  if(val===undefined){td.className='absent';td.textContent='·';}
  else if(val===true){td.style.background='#8ce99a';td.textContent='T';}
  else if(val===false){td.className='absent';td.textContent='·';}
  else if(val===0){td.className='zero';td.textContent='0';}
  else{const m=Math.min(1,Math.abs(val)/20);
    td.style.background=val>0?`rgba(80,140,220,${.15+m*.6})`:`rgba(220,90,90,${.15+m*.6})`;td.textContent=val;}
  if(changed)td.classList.add('chg');return td;}
function block(name,curT,prvT,isOut,isBefore,label){
  const rk=RN[name]||[],d=document.createElement('div');
  d.className='tblock'+(curT?'':' off')+(isOut?(isBefore?' before':' active'):'');
  const h=document.createElement('div');h.className='tname';
  h.innerHTML=(label||name)+'<sup>'+rk.join(',')+'</sup>'+emptyTag(name);
  h.dataset.desc=DESC[name]||''; d.appendChild(h);
  const tb=document.createElement('table');tb.className='grid';
  const C=curT||{},P=prvT||{};
  // A rank-1 tensor is drawn along the axis its rank indexes: one over the
  // down rank becomes a COLUMN, so its cell for u sits at the same height as
  // row u of every two-rank grid beside it. One over the across rank stays a
  // row.
  const rank1=RANKS[name]===1, vert=rank1&&rk[0]!==AXES.across;
  const hr=tb.insertRow();const c0=document.createElement('th');
  c0.className='rk';c0.textContent=rank1?(rk[0]||''):rk[0]+'\\'+rk[1];hr.appendChild(c0);
  const nDown=sizeOf(rk[0]), nAcross=sizeOf(rank1?rk[0]:rk[1]);
  for(let v=0;v<(vert?1:nAcross);v++){const th=document.createElement('th');
    th.textContent=vert?'':v;hr.appendChild(th);}
  // On the output tensor, each cell is a way into the drill-down for that
  // coordinate: "why did THIS value come out?"
  const wire=(td,k)=>{
    td.dataset.coord=k;
    if(isOut&&!isBefore){td.title='Why is '+name+'['+k+'] this value?';
      td.onclick=()=>buildExec(k);}
    return td;};
  if(vert){for(let u=0;u<nDown;u++){const r=tb.insertRow();
    const th=document.createElement('th');th.textContent=u;r.appendChild(th);
    r.appendChild(wire(cell(C[''+u],curT&&P[''+u]!==C[''+u]),''+u));}}
  else if(rank1){const r=tb.insertRow();r.appendChild(document.createElement('th'));
    for(let v=0;v<nAcross;v++)r.appendChild(wire(cell(C[''+v],curT&&P[''+v]!==C[''+v]),''+v));}
  else{for(let u=0;u<nDown;u++){const r=tb.insertRow();
    const th=document.createElement('th');th.textContent=u;r.appendChild(th);
    for(let v=0;v<nAcross;v++){const k=u+','+v;
      r.appendChild(wire(cell(C[k],curT&&P[k]!==C[k]),k));}}}
  d.appendChild(tb);return d;}
function genLabel(g,it){
  if(g===null||g===undefined)return null;
  if(g==='i')return it; if(g==='i+1')return it+1;
  const n=+g; return isNaN(n)?null:n;}
function drawTensors(st,prev,out,isBefore,lbl){
  for(const gid in GROUPS){const box=$(gid);box.innerHTML='';
    GROUPS[gid].forEach(n=>box.appendChild(
      block(n,st[n],prev?prev[n]:null,n===out,isBefore,n===out?lbl:null)));}
  // Named coordinate sets are inputs, but no tensor holds them.
  (T.coordSets||[]).forEach(c=>{const d=document.createElement('div');
    d.className='tblock';
    d.innerHTML='<div class="tname">'+c.name+'<sup>'+c.rank+'</sup></div>'+
      '<div class="cset">{ '+c.members.join(', ')+' }</div>';
    $('static1').appendChild(d);});}

const tip=$('tip');
document.addEventListener('mouseover',e=>{const t=e.target.closest('.tname');
  if(t&&t.dataset.desc){
    tip.innerHTML=t.dataset.desc.replace(/«([^»]*)»/,'<b style="color:#ffd43b">$1</b><br>');
    tip.style.display='block';
    tip.style.left=Math.min(e.clientX+14,innerWidth-305)+'px';tip.style.top=(e.clientY+16)+'px';}});
document.addEventListener('mouseout',e=>{if(e.target.closest('.tname'))tip.style.display='none';});

function render(){
  const s=T.steps[cur],prev=cur>0?T.steps[cur-1].state:null;
  const can=!!(s.hasPrior&&prev), on=showBefore&&can;
  const gAfter=genLabel(s.outGen,s.iteration), gBefore=gAfter===null?null:gAfter-1;
  let view=s.state, lbl=null;
  if(on){ view=Object.assign({},s.state);
          view[s.output]=s.stateful?prev[s.output]:{};
          lbl=s.stateful?s.output+(gBefore!==null?'\u2009('+gBefore+')':'')
                        :s.output+'\u2009(not yet computed)'; }
  else if(can&&gAfter!==null){ lbl=s.output+'\u2009('+gAfter+')'; }
  $('btog').disabled=!can;
  $('btog').setAttribute('aria-pressed',on?'true':'false');
  document.body.classList.toggle('showing-before',on);
  if(on){
    const nm=(g)=>'<b>'+s.output+(g===null?'':'<sub>'+g+'</sub>')+'</b>';
    let msg;
    if(!s.stateful){
      msg='<b>'+s.output+'</b> is an intermediate — it is not carried on the '+
          'grid at all. It is built from scratch each iteration, and you can '+
          'watch it being built under <i>How this Einsum executes</i> below. '+
          'Before-mode here shows the graph and the state as they stood '+
          'before this Einsum ran.';
    } else {
      msg='Showing '+nm(gBefore)+' — the value before this Einsum ran. '+
          'Release to see '+nm(gAfter)+'.';
      if(JSON.stringify(prev[s.output])===JSON.stringify(s.state[s.output]))
        msg+=' <span style="opacity:.75">Unchanged — this Einsum recomputed the same value.</span>';
    }
    $('beforebar').innerHTML=msg;}
  drawGraph(view,on?{nodes:[],edges:[]}:(s.graphHighlight||{}),on?null:prev);
  drawTensors(view,on?view:prev,s.output,on,lbl);
  const box=$('expr'), live=window.MathJax&&MathJax.typesetPromise;
  const math=tex=>live?'\\('+EdgeDisplay.esc(tex)+'\\)':typeset(tex);
  $('mg').innerHTML=EdgeDisplay.meaningHTML(s.graphMeaning||'',math);
  $('me').innerHTML=EdgeDisplay.meaningHTML(s.einsumMeaning||'',math);
  if(live&&s.latex){
    box.innerHTML='<span class="eid">'+s.einsum+'</span>\\['+s.latex+'\\]'+
      (s.latexDefs||[]).map(d=>'<div class="exsub"><b>where</b> \\('+d+'\\)</div>').join('')+
      (s.latexParts?'<div class="exsub"><b>step by step</b> \\['+s.latexParts+'\\]</div>':'');
    MathJax.typesetPromise([box,$('mg'),$('me')]).catch(()=>{box.innerHTML='<span class="eid">'+s.einsum+'</span>'+typeset(s.expr);});
  } else {
    box.innerHTML='<span class="eid">'+s.einsum+'</span>'+typeset(s.expr);
    if(live)MathJax.typesetPromise([$('mg'),$('me')]).catch(()=>{});
  }
  $('mglabel').style.display=$('mg').style.display=s.graphMeaning?'':'none';
  const ss=s.setupSteps||[]; $('sslabel').style.display=$('ss').style.display=ss.length?'':'none';
  $('ss').innerHTML=''; ss.forEach(t=>{const li=document.createElement('li');li.textContent=t;$('ss').appendChild(li);});
  buildExec();
  // An Einsum in an inner cascade runs in a generation of each cascade
  // around it: `i = 1, j = 2`.
  $('itbadge').innerHTML=s.iteration!=null
    ?'<i>'+(T.genVar||'i')+'</i> = '+s.iteration+Object.entries(s.inner||{})
       .map(([v,c])=>', <i>'+v+'</i> = '+c).join('')
    :'setup';
  $('stepno').textContent=`step ${cur+1} of ${T.steps.length}`;
  $('flow').textContent = (cur===T.steps.length-1 && T.headline)
    ? T.headline.label+' = '+T.headline.value : '';
  $('slider').value=cur;}
function delay(){return 1260-(+$('speed').value);}
function go(i){showBefore=false;cur=Math.max(0,Math.min(T.steps.length-1,i));render();}
$('next').onclick=()=>go(cur+1);$('prev').onclick=()=>go(cur-1);
$('first').onclick=()=>go(0);$('last').onclick=()=>go(T.steps.length-1);
// The next generation: of the innermost cascade this step ran in.
const genKey=s=>s.iteration+'|'+JSON.stringify(s.inner||null);
$('nextit').onclick=()=>{const it=genKey(T.steps[cur]);let i=cur+1;
  while(i<T.steps.length&&genKey(T.steps[i])===it)i++;go(i);};
$('slider').oninput=e=>go(+e.target.value);
$('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;$('play').textContent='▶ play';return;}
  $('play').textContent='❚❚ pause';
  timer=setInterval(()=>{if(cur>=T.steps.length-1){clearInterval(timer);timer=null;$('play').textContent='▶ play';}
    else go(cur+1);},delay());};
$('speed').oninput=()=>{if(timer){clearInterval(timer);
  timer=setInterval(()=>{if(cur>=T.steps.length-1){clearInterval(timer);timer=null;$('play').textContent='▶ play';}
    else go(cur+1);},delay());}};
$('btog').onclick=()=>{showBefore=!showBefore;render();};
document.addEventListener('keyup',e=>{if(e.key==='b'||e.key==='B'){showBefore=false;render();}});
document.onkeydown=e=>{
  if((e.key==='b'||e.key==='B')&&!e.repeat){showBefore=true;render();return;}
  if(e.key==='ArrowRight')go(cur+1);if(e.key==='ArrowLeft')go(cur-1);
  if(e.key===' '){e.preventDefault();$('play').click();}};
/* ===================================================================
   Drill-down: show how one Einsum's values were computed, from what
   edge-core-ir's evaluator recorded at build time (step.exec). Nothing is
   recomputed in the browser.
   =================================================================== */
let EXEC=null;

function irIndexFor(s){
  const x=EIDX[s.einsum];
  // E04 is a three-arm `cases` lowered to three IR einsums. The drill-down
  // shows one Einsum at a time, so it is not expandable.
  return (x===undefined||Array.isArray(x))?null:x;}

function expandable(i){
  const s=T.steps[i];
  return !!s.exec;}

function whyNotExpandable(s){
  if(Array.isArray(EIDX[s.einsum]))
    return s.einsum+' is a three-arm cases statement, lowered to three '+
           'Einsums. The drill-down works on one Einsum at a time.';
  if(s.einsum==='init')return 'Initializations are not cascade Einsums.';
  if(s.einsum==='stop')return 'Checked after each generation; it computes no tensor.';
  return 'No recorded execution for this step.';}

function fmt(v){
  if(v===null||v===undefined)return '—';
  if(v===true)return 'true'; if(v===false)return 'false';
  if(v===Infinity)return '∞'; if(v===-Infinity)return '−∞';
  return String(v);}

function emptyOf(name){
  const d=IR.declarations.find(x=>x.name===name);
  if(!d)return null;
  return EdgeDisplay.num(d.empty_value);}

/* The execution panel is not a detour any more -- it is rebuilt for
   whatever step you are on. `coord` focuses one output cell (a click on
   the grid, or on a cell of the output card); otherwise it opens on the
   first point that produced a value. */
function buildExec(coord){
  const panel=$('execpanel'), s=T.steps[cur];
  if(!expandable(cur)){
    EXEC=null; panel.classList.add('off');
    $('execsub').textContent='— '+whyNotExpandable(s);
    $('tstrip').innerHTML=''; $('snote').innerHTML='';
    $('pbody').innerHTML='';
    return;}
  // Recorded at build time from edge-core-ir's evaluator: every point of the
  // iteration space, the operand cells it read, and what it produced.
  // The first step has nothing before it, but its inputs are already there:
  // everything in its state except what it just wrote.
  const R=s.exec, before=cur>0?T.steps[cur-1].state:{...s.state,[s.output]:{}};
  panel.classList.remove('off');
  EXEC={s,R,before,sel:coord!==undefined&&coord!==null?String(coord):null};
  if(EXEC.sel===null&&R.points.length)
    EXEC.sel=(R.points.find(p=>p.present)||R.points[0]).coord;
  renderExec();}

function renderExec(){
  const {R}=EXEC;
  const nOut=Object.keys(R.result).length;
  $('execsub').textContent=
    '— '+R.points.length+(R.points.length===1?' point':' points')+
    ' in the iteration space, each computed independently of the others; '+nOut+
    (nOut===1?' produced a value':' produced values');
  writeSpaceNote(); renderPoint();}

// Grids are drawn on fixed screen axes: rank U down, rank V across, whatever
// order each tensor happens to be indexed in -- so what a reduction collapses
// on screen follows from which RANK the reduced variable walks, not from where
// that variable sits in the subscript list.
/* Only what is true of THIS Einsum.

   There used to be a paragraph here restating, on every step, that the points
   are independent and how the axes are laid out. Both are properties of the
   whole page, not of the step in front of you, so after the first read they
   are noise -- and they pushed the part that does change further down. The
   independence claim still appears once, in the panel subtitle, with the
   point count; the axis convention lives in the README and in the axis
   labels themselves. */
function writeSpaceNote(){
  const {R}=EXEC, vars=R.iterVars;
  if(!R.reduceSpec){ $('snote').innerHTML=''; return; }
  const rl=(R.reduceSpec.rank_list||[]).join(', ');
  const op=R.reduceSpec.compute_op.symbol||R.reduceSpec.compute_op.name;
  $('snote').innerHTML=
    '<div class="collapse">Rank <b>'+rl+'</b> is reduced'+
    (hasAfterMap(R)
      ?': the outlined line in After Map is what folds'
      :': each highlighted entry is part of one contribution, and they fold')+
    ' into <b>'+(hasAfterReduce(R)?'After Reduce':shownName(R.output))+
    '['+EXEC.sel+']</b> under <b>'+
    EdgeDisplay.glyph(op,'compute')+'</b>.</div>';}

// ---- one point, or one reduction group -----------------------------------
function renderPoint(clicked){
  const {R}=EXEC, box=$('pbody'); box.innerHTML='';
  const outEmpty=EdgeDisplay.num(R.outEmpty);
  const members=R.points.filter(p=>p.coord===EXEC.sel);
  const shown=clicked||members.find(p=>p.present)||members[0];
  if(!shown){box.innerHTML='<p style="color:#888">No point selected.</p>';return;}

  const h=[];
  h.push('<div style="font-family:ui-monospace,monospace;font-size:13px;'+
    'margin-bottom:11px">'+R.iterVars
      .filter(v=>!(R.reduceSpec&&(R.reduceSpec.rank_list||[]).includes(v)))
      .filter(v=>shown.bind[v]!==undefined)
      .map(v=>'<b>'+v+'</b> = '+shown.bind[v]).join('&nbsp;&nbsp;')+'</div>');
  // A case statement: say which arm claimed this point, by its condition.
  if(R.arms&&shown.arm!==undefined){
    const arm=R.arms[shown.arm];
    h.push('<div class="collapse">Case '+(shown.arm+1)+' of '+R.arms.length+
      ': <b>'+(arm.condition?EdgeDisplay.esc(arm.condition):'otherwise')+
      '</b></div>');}

  // The derivation, innermost first, so it reads as a sequence of moves.
  // A reduction lists every contribution below, so one point's operands here
  // would only be the first of several, or an arbitrary absent one.
  const cards=[];
  if(!R.reduceSpec)walkProv(shown.prov,cards);
  cards.forEach(c=>h.push(c));

  // A reduction folds the group; show the accumulation explicitly.
  if(R.reduceSpec){
    const op=R.reduceSpec.compute_op.symbol||R.reduceSpec.compute_op.name;
    // The contributions are listed; the total is the evaluator's own result.
    // Nothing here recomputes the fold.
    const present=members.filter(p=>atMap(p).present);
    const rows=[], won=keptBy(R,present);
    const folded=shown.afterReduce;
    const into=folded?'After Reduce':R.output;
    const total=folded?(folded.present?folded.value:null)
                      :(R.result[EXEC.sel]!==undefined?R.result[EXEC.sel]:null);
    const over=R.reduceSpec.rank_list||[];
    present.forEach(p=>{
      rows.push('<tr'+(won.includes(p)?' class="kept"':'')+'><td class="mono">'+
        over.map(v=>v+'='+p.bind[v]).join(' ')+'</td><td class="mono">'+
        working(R,p)+'</td><td class="mono">'+fmt(atMap(p).value)+'</td></tr>');});
    h.push('<div class="step out"><h4>Reduce over rank '+
      (R.reduceSpec.rank_list||[]).join(', ')+' &nbsp;'+
      '<span class="op cp">'+EdgeDisplay.glyph(op,'compute')+'</span>'+
      '<span class="op mg">'+
        EdgeDisplay.glyph(R.reduceSpec.merge_op.symbol,'merge')+'</span></h4>'+
      (present.length===0
        ? '<div style="color:#888;font-size:12px">No point in the group is '+
          'present, so nothing is produced for '+into+'['+EXEC.sel+'].</div>'
        : '<table class="fold"><tr><th></th><th>working</th><th>value</th></tr>'+
          rows.join('')+'<tr class="total"><td>'+into+'['+EXEC.sel+
          ']</td><td>'+EdgeDisplay.glyph(op,'compute')+' of these</td><td class="acc">'+
          fmt(total)+'</td></tr></table>')+
      '</div>');
    // The Map outside the parentheses, on what the Reduce produced.
    if(folded)h.push('<div class="step"><h4>Then the Map outside the parentheses</h4>'+
      '<div class="opnd">After Reduce['+EXEC.sel+'] = '+
      (folded.present?'<span class="v">'+fmt(folded.value)+'</span>'
                     :'<span class="abs">absent</span>')+'</div>'+
      splitReads(R,shown.prov.reads||[]).outer.map(operandLine).join('')+'</div>');
  }

  // The empty-value rule is where most surprises live, so state it whenever
  // it fired.
  const finalV=R.result[EXEC.sel];
  const produced=finalV!==undefined;
  h.push('<div class="step out"><h4>Result</h4>'+
    '<div class="opnd">'+R.output+'['+EXEC.sel+'] = '+
    (produced?'<span class="v">'+fmt(finalV)+'</span>'
             :'<span class="abs">absent</span>')+'</div>'+
    (!produced&&shown.present&&EdgeDisplay.isEmpty(shown.value,R.outEmpty)
      ? '<div class="note">The computed value '+fmt(shown.value)+
        ' equals '+R.output+'’s empty value, so the coordinate is '+
        '<b>absent</b> rather than stored. This is the rule that lets a '+
        'saturated edge drop out of an intersect without a positivity guard.'+
        '</div>' : '')+
    '</div>');

  if(R.note)h.push('<div class="note">'+R.note+'</div>');
  box.innerHTML=h.join('');
  renderTensors(members,shown);}

/* ---- operand tensors, with the read cells lit -------------------------
   The derivation on the right says WHICH values were used; this says WHERE
   they came from. For a reduction the whole group's reads are lit at once,
   so the line collapsing in the iteration space and the line being read out
   of the operand are visibly the same line. */
// Keyed by tensor AND projection, because one tensor can be read through more
// than one projection in a single Einsum: E08 reads D_{i,u} and D_{i,v}. Those
// are two different accesses and deserve two cards -- merged into one, the
// card lights both cells and the caption can only name one of them, which
// reads like a highlight that failed to clear.
function collectReads(p,acc){
  if(!p)return acc;
  if(p.tensor&&!p.scalar){
    const key=p.tensor+'|'+(p.ranks||[]).join(',');
    const e=acc[key]=acc[key]||
      {tensor:p.tensor,ranks:p.ranks||[],cells:new Set()};
    // ||T|| reads every entry it counts, not one cell.
    (p.cells||[p.coord]).forEach(c=>e.cells.add(c)); return acc;}
  if(p.reads)p.reads.forEach(r=>collectReads(r,acc));
  if(p.inner)collectReads(p.inner,acc);
  if(p.lhs)collectReads(p.lhs,acc);
  if(p.rhs)collectReads(p.rhs,acc);
  return acc;}

// IR tensor name -> the name used everywhere else on the page.
const DISPLAY=ALIASMAP;
function shownName(t){return DISPLAY[t]||t;}

// The trace names a tensor as the spec writes it (`d*`); the IR as it must
// (`DStar`). Accept either, so a renamed tensor still finds its declaration.
function declOf(name){
  const ir=Object.keys(DISPLAY).find(k=>DISPLAY[k]===name)||name;
  return IR.declarations.find(d=>d.name===ir||d.name===name);}

/* The declared empty value, formatted for display. Read from the IR, so this
   cannot drift from what the interpreter actually treats as absent. Anonymous
   intermediates ("__inter3") have no declaration and get no label: their empty
   value follows from the operator, and the IR does not record one. */
function emptyGlyph(name){
  const d=declOf(name);
  if(!d||d.empty_value===undefined||d.empty_value===null)return null;
  const e=d.empty_value;
  if(e==='inf'||e===Infinity)return '+∞';
  if(e==='-inf')return '−∞';
  if(e===true)return 'true';
  if(e===false)return 'false';
  return String(e);}

function emptyTag(name){
  const g=emptyGlyph(name);
  return g===null?'':'<span class="emp" title="Cells drawn as empty on this '+
    'tensor mean '+g+'. Writing '+g+' into a cell is the same as clearing it.">'+
    '∅ <b>'+g+'</b></span>';}
// The tensor's own rank names, minus the generational rank, in stored order;
// null when nothing declares it.
function dataRankNames(name){
  const d=declOf(name); if(!d)return null;
  return d.ranks.filter(r=>r.name!=='I').map(r=>r.name);}

// For a tensor nothing declares, how many ranks it has is read off what is
// known here -- the variables indexing it, else its coordinates -- and the
// ranks go unnamed rather than borrowing names from some other algorithm.
function undeclaredRanks(dict,vars){
  let n=vars&&vars.length?vars.length:0;
  if(!n){const k=Object.keys(dict||{})[0];
    n=(k===undefined||k==='')?0:String(k).split(',').length;}
  return Array(n).fill(null);}

// Drop the generational rank from a projection's rank list, leaving the
// variables that index the data. `ranks` comes from the interpreter and is in
// the order the tensor is actually indexed at this site.
function dataVars(name,ranks){
  const d=declOf(name); if(!d||!ranks)return ranks||[];
  return ranks.filter((r,i)=>!(d.ranks[i]&&d.ranks[i].name==='I'));}

/* Screen axes: the VARIABLE picks the axis -- the down rank's variable runs
   down, the across rank's across (u and v in max-flow, r and c in exact
   cover).
   Everything in a card strip is drawn so that a shared variable lands on a
   shared axis, which is the only reason the strip is readable: what a
   reduction collapses has to point at the cell it collapses into. */
const AXIS_OF_VAR={};
if(AXES.down)AXIS_OF_VAR[AXES.down.toLowerCase()]='down';
if(AXES.across)AXIS_OF_VAR[AXES.across.toLowerCase()]='across';

function orient(vars,rankNames){
  const lab=(i)=>((rankNames&&rankNames[i])?rankNames[i]+':':'')+(vars[i]||'?');
  const nd=rankNames?rankNames.length:vars.length;
  if(nd===0)return {rows:0,cols:0,head:'',key:()=>''};
  if(nd===1){
    /* A 1-D tensor is laid out by the variable walking it HERE, not by its
       declared rank. E03 is the case that forces this:

           E_{1,v} = F_{1,u,v}  ::  V +(U)        reducing u

       F is 2-D and keeps rank U down, rank V across, so the cells this point
       reads are a COLUMN of F -- one per u, all at horizontal position v. The
       output cell has to sit under that column, so E is drawn ACROSS, indexed
       by v. Drawn down (by its declared rank U) its cell for v would sit at
       vertical position v, nowhere near the column feeding it.

       The same tensor can therefore appear across in one Einsum and down in
       another -- InPush is written InPush_{i,v} in E13 and read InPush_{i,u}
       in E15 -- which is correct rather than inconsistent: the orientation
       shows how it is being walked here, and the rank:variable label on the
       axis says which rank that is. Grids in the static and generational
       panels have no access to show, so those stay on the declared rank. */
    const v0=vars[0];
    const across=(v0 in AXIS_OF_VAR)
      ? AXIS_OF_VAR[v0]==='across'
      : (rankNames&&rankNames[0])===AXES.across;   // unknown variable: fall back to rank
    return across
      ? {rows:0,cols:sizeOf(rankNames&&rankNames[0]),head:lab(0),key:(r,c)=>''+c}
      : {rows:sizeOf(rankNames&&rankNames[0]),cols:0,head:lab(0),key:r=>''+r};}
  /* 2-D tensors keep their declared layout -- first rank down, second across --
     even when read out of order. E12 is why: it reads delta_{i,u,v} AND
     delta_{i,v,u} in the same Einsum, so honouring the variable would draw
     one tensor two contradictory ways in one strip. The label carries the
     binding instead: "U:v" is the tensor's U rank, walked here by v. */
  return {rows:sizeOf(rankNames&&rankNames[0]),cols:sizeOf(rankNames&&rankNames[1]),
          head:lab(0)+'\\'+lab(1),key:(r,c)=>r+','+c};}

function miniGrid(name,dict,mark,cls,pick,vars,rankOverride){
  const rn=rankOverride||dataRankNames(name)||undeclaredRanks(dict,vars),
        nd=rn.length;
  // No variables given: each rank is walked by its own name in lower case,
  // or by the grid's axis variables when the rank is unnamed.
  const axisVars=[AXES.down,AXES.across].map(r=>r?r.toLowerCase():'?');
  vars=(vars&&vars.length===nd)?vars
    :rn.map((r,i)=>r?r.toLowerCase():axisVars[i]||'?');
  const o=orient(vars,rn);
  const tb=document.createElement('table'); tb.className='mini';
  const hr=tb.insertRow(); const c0=document.createElement('th');
  c0.className='rk'; c0.textContent=o.head; hr.appendChild(c0);
  const ncols=o.cols||1;
  for(let c=0;c<ncols;c++){const th=document.createElement('th');
    th.textContent=o.cols?c:''; hr.appendChild(th);}
  const put=(tr,key,val)=>{
    const td=document.createElement('td');
    // false is drawn like absent, matching the main grids: a Boolean tensor's
    // empty value IS false, so the two mean the same thing wherever it is read.
    if(val===undefined||val===false){td.className='abs';td.textContent='·';}
    else td.textContent=val===true?'T':fmt(val);
    if(mark.has(key))td.classList.add(cls);
    if(mark.fiber&&mark.fiber.has(key))td.classList.add('fiber');
    if(pick){td.classList.add('pick');td.dataset.coord=key;
      td.title='Follow '+shownName(name)+'['+key+']';
      td.onclick=()=>pick(key);}
    tr.appendChild(td);};
  if(nd===0){const tr=tb.insertRow();tr.appendChild(document.createElement('th'));
    put(tr,'',dict['']);}
  else if(!o.cols){                       // a column: one cell per row
    for(let r=0;r<o.rows;r++){const tr=tb.insertRow();
      const th=document.createElement('th');th.textContent=r;tr.appendChild(th);
      put(tr,o.key(r),dict[o.key(r)]);}}
  else if(!o.rows){                       // a row: one cell per column
    const tr=tb.insertRow(); tr.appendChild(document.createElement('th'));
    for(let c=0;c<o.cols;c++)put(tr,o.key(0,c),dict[o.key(0,c)]);}
  else{for(let r=0;r<o.rows;r++){const tr=tb.insertRow();
    const th=document.createElement('th');th.textContent=r;tr.appendChild(th);
    for(let c=0;c<o.cols;c++)put(tr,o.key(r,c),dict[o.key(r,c)]);}}
  return tb;}

function tcard(capHtml,grid,extra){
  const d=document.createElement('div');
  d.className='tcard'+(extra||'');
  const c=document.createElement('div'); c.className='cap';
  c.innerHTML=capHtml;
  d.appendChild(c); d.appendChild(grid); return d;}

// Show the access as written, with the generation resolved to a number:
// F_{i,u,v} at iteration 3 reads "F 3,u,v".
function resolveGen(r,it){
  if(r==='i')return String(it);
  if(r==='i+1')return String(it+1);
  return r;}

function capOf(name,ranks,it){
  const shown=(ranks||[]).map(r=>{
    if(r==='i')return String(it);
    if(r==='i+1')return String(it+1);
    return r;});
  return shownName(name)+
    (shown.length?'<sub class="gen">'+shown.join(',')+'</sub>':'')+
    emptyTag(name);}

/* ---- intermediates ---------------------------------------------------
   A parenthesised sub-expression with its own rank annotation -- the
   (E_{i,u} .^2 0)_{i,u} in E06, say -- is a real intermediate tensor in EDGE,
   not just grouping. Showing it as a grid of its own turns a two-operator
   Einsum into two visible steps: first E > 0, then that AND-ed with NST. */

function isGenRank(r){return r==='i'||r==='i+1'||/^\d+$/.test(r);}

function anonCap(prov){
  const inner=prov.inner;
  if(!inner||inner.merge===undefined)return '(…)';
  const nm=(q)=>{
    if(!q)return '?';
    if(q.scalar)return fmt(q.value);
    if(q.tensor)return shownName(q.tensor);
    if(q.op==='not')return '¬'+nm(q.inner);
    return '(…)';};
  return '('+nm(inner.lhs)+' '+inner.computeGlyph+' '+nm(inner.rhs)+')';}

function collectInter(R){
  const out={};
  const walk=(prov,bind)=>{
    if(!prov)return;
    if(prov.anonymous){
      const lbl=(prov.inner&&prov.inner.label)||0;
      const vars=(prov.boundTo||[]).filter(r=>!isGenRank(r));
      const e=out[lbl]=out[lbl]||
        {label:lbl,vars,cells:{},cap:anonCap(prov),
         gen:(prov.boundTo||[]).find(isGenRank)||null};
      if(prov.present&&prov.value!==null&&prov.value!==undefined)
        e.cells[vars.map(v=>bind[v]).join(',')]=prov.value;
      walk(prov.inner,bind); return;}
    if(prov.lhs)walk(prov.lhs,bind);
    if(prov.rhs)walk(prov.rhs,bind);
    if(prov.inner)walk(prov.inner,bind);};
  R.points.forEach(p=>walk(p.prov,p.bind));
  return Object.values(out).sort((a,b)=>a.label-b.label);}

// Which cell of an intermediate this point (or reduction group) used.
function interMarks(inter,pts){
  const m=new Set();
  pts.forEach(p=>m.add(inter.vars.map(v=>p.bind[v]).join(',')));
  return m;}

// What fed this output: the one point, or a group's points that hold a value.
function contributions(members,shown){
  return EXEC.R.reduceSpec?members.filter(p=>atMap(p).present):[shown];}

// What a Reduce folds at a point: the Map under it, which for a Reduce inside
// parentheses is not the whole Einsum's value.
function atMap(p){return p.afterMap||p;}

// A Reduce inside parentheses with a Map outside them.
function hasAfterReduce(R){return !!R.points.length&&!!R.points[0].afterReduce;}

// Tensors under an expression node.
function tensorsIn(n,out){
  out=out||new Set();
  if(!n||typeof n!=='object')return out;
  if(n.kind==='input')out.add(shownName(n.proj.tensor));
  [n.lhs,n.rhs,n.expression,n.operand].forEach(c=>tensorsIn(c,out));
  return out;}

// Which reads feed the Reduce, and which the Map outside it.
function splitReads(R,reads){
  const inner=tensorsIn(binaryOf(R.einsum.expression,R.reduceSpec.label));
  return {inner:reads.filter(r=>!r.tensor||inner.has(r.tensor)),
          outer:reads.filter(r=>r.tensor&&!inner.has(r.tensor))};}

// Which contributions a min or max kept: those equal to the evaluator's own
// result. Empty for a reduction that combines them all, like + or ANY.
function keptBy(R,used){
  if(!R.reduceSpec)return [];
  const op=R.reduceSpec.compute_op.symbol||R.reduceSpec.compute_op.name;
  if(op!=='min'&&op!=='max')return [];
  const m=used[0];
  const v=m&&m.afterReduce?(m.afterReduce.present?m.afterReduce.value:undefined)
                          :R.result[EXEC.sel];
  return v===undefined?[]:used.filter(p=>atMap(p).value===v);}

// One contribution's working: `G[0,1] 10 + D[0] 0`, in the Map's own operator.
function working(R,p){
  const every=p.prov&&p.prov.reads||[];
  const all=p.afterReduce?splitReads(R,every).inner:every;
  const reads=all.filter(r=>!(r.scalar&&!r.rank));
  const one=r=>r.rank?r.rank+' '+fmt(r.value):
    shownName(r.tensor)+(r.coord?'['+r.coord+']':'')+' '+
    (r.present?fmt(r.value):'absent');
  const map=(R.einsum.specs||[]).find(s=>s.kind==='map'&&s.label===R.reduceSpec.label);
  // Only a plain two-operand Map reads as `a op b`. A literal among the reads
  // means the Map was a lowering (a unary against 1), not this operator.
  if(all.length===2&&reads.length===2&&map){
    const op=map.compute_op.symbol||map.compute_op.name;
    return one(reads[0])+' '+EdgeDisplay.glyph(op,'compute')+' '+one(reads[1]);}
  return reads.map(one).join(', ');}

// An expression in words, from the Einsum itself. Literals a lowering added
// (the 1 of a degenerate Map) are not part of what the author wrote.
function exprText(n,specs){
  if(!n)return '';
  if(n.kind==='input'){
    const d=declOf(n.proj.tensor);
    if(d&&!d.ranks.length&&d.value!==undefined&&d.value!==null)return '';
    return shownName(n.proj.tensor);}
  if(n.kind==='rank_value')return n.expr.name||'';
  if(n.kind==='anonymous')return exprText(n.expression,specs);
  if(n.kind==='unary')return '¬'+exprText(n.operand,specs);
  if(n.kind!=='binary')return '';
  const l=exprText(n.lhs,specs), r=exprText(n.rhs,specs);
  const m=specs.find(s=>s.kind==='map'&&s.label===n.label);
  const op=m?(m.compute_op.symbol||m.compute_op.name):'';
  if(l&&r)return l+' '+EdgeDisplay.glyph(op,'compute')+' '+r;
  return op==='floor'?'⌊'+(l||r)+'⌋':(l||r);}

// The binary carrying a label, wherever it sits in the expression.
function binaryOf(n,label){
  if(!n)return null;
  if(n.kind==='binary'&&n.label===label)return n;
  return binaryOf(n.lhs,label)||binaryOf(n.rhs,label)||
         binaryOf(n.expression,label)||binaryOf(n.operand,label);}

// A Reduce on a real Map. A bare reduce (`E = F :: ⋁ +(∪)`) is lowered to a Map
// that passes its operand through, and has nothing to show between the two.
function foldsAMap(R){
  const specs=R.einsum.specs||[], label=R.reduceSpec.label;
  const n=binaryOf(R.einsum.expression,label);
  if(!n)return false;
  const m=specs.find(s=>s.kind==='map'&&s.label===label);
  const op=m?(m.compute_op.symbol||m.compute_op.name):'';
  return !!(exprText(n.lhs,specs)&&exprText(n.rhs,specs))||
         !['take_left','take_right','identity'].includes(op);}

function hasAfterMap(R){
  return !!R.reduceSpec&&foldsAMap(R)&&
         R.iterVars.length>0&&R.iterVars.length<=2;}

// What the Reduce folds: the Map on its own label, not the whole Einsum.
function mapFormula(expr,specs,label){
  const n=binaryOf(expr,label);
  const text=exprText(n||expr,specs);
  const m=specs.find(s=>s.kind==='map'&&s.label===label);
  const both=n&&exprText(n.lhs,specs)&&exprText(n.rhs,specs);
  return text+(m&&both?' ('+EdgeDisplay.glyph(m.merge_op.symbol,'merge')+')':'');}

/* The Map's result at every point of the iteration space, before the Reduce.
   Recorded values only. Not a tensor of the program: its axes are the
   iteration space's, the output's ranks plus the ranks being reduced. Laid out
   to match the grids beside it; past two ranks a flat grid cannot show it. */
function afterMapCard(R,members){
  if(!hasAfterMap(R))return null;
  const over=R.reduceSpec.rank_list||[];
  const place=v=>AXIS_OF_VAR[v]==='down'?0:AXIS_OF_VAR[v]==='across'?2:
    over.includes(v)?0:1;
  const vars=[...R.iterVars].sort((a,b)=>place(a)-place(b));
  const key=p=>vars.map(v=>p.bind[v]).join(',');
  const at=p=>p.afterMap||p, cells={};
  R.points.forEach(p=>{if(at(p).present)cells[key(p)]=at(p).value;});
  const mark=new Set(members.filter(p=>at(p).present).map(key));
  // The whole line this Reduce folds, empty cells included.
  mark.fiber=new Set(members.map(key));
  const how=mapFormula(R.einsum.expression,R.einsum.specs||[],R.reduceSpec.label);
  return tcard('After Map: '+how,
    miniGrid('__aftermap',cells,mark,'rd',null,vars,vars.map(rankOfVar)),' aftermap');}

/* The partial tensor the Reduce leaves, before the Map outside the parentheses
   uses it (paper, Example 4). Recorded values, over the output's own ranks. */
function afterReduceCard(R){
  if(!hasAfterReduce(R))return null;
  const cells={};
  R.points.forEach(p=>{if(p.afterReduce.present)cells[p.coord]=p.afterReduce.value;});
  const ranks=dataVars(R.output,(R.einsum.output_ranks||[]).map(rankNameOf));
  const op=R.reduceSpec.compute_op.symbol||R.reduceSpec.compute_op.name;
  return tcard('After Reduce: '+EdgeDisplay.glyph(op,'compute')+' over '+
      (R.reduceSpec.rank_list||[]).join(', '),
    miniGrid('__afterreduce',cells,new Set([EXEC.sel]),'rd',null,ranks,
             dataRankNames(R.output)),' afterreduce');}

function renderTensors(members,shown){
  const {R,before,s}=EXEC, strip=$('tstrip'); strip.innerHTML='';
  // Reads: what contributed to a reduction, otherwise just this point. A point
  // with no value contributes nothing, so highlighting it would only mislead.
  const acc={}, used=contributions(members,shown);
  (used.length?used:[shown]).forEach(p=>collectReads(p.prov,acc));
  // Nothing contributed: the operands still show, with nothing lit.
  if(!used.length)Object.values(acc).forEach(e=>e.cells.clear());
  // A Map outside the parentheses runs after the Reduce, so its operands are
  // drawn after it, reading only the output's own cell.
  const outer=[];
  if(hasAfterReduce(R)){
    const late=splitReads(R,shown.prov.reads||[]).outer;
    Object.keys(acc).forEach(k=>{
      const r=late.find(l=>l.tensor===acc[k].tensor);
      if(r){const e=acc[k]; e.cells=new Set([r.coord]); outer.push(e); delete acc[k];}});}
  const operand=(e)=>{
    const dict=before[shownName(e.tensor)]||{};
    return tcard(capOf(e.tensor,e.ranks,s.iteration),
      miniGrid(e.tensor,dict,e.cells,'rd',null,dataVars(e.tensor,e.ranks)));};
  Object.values(acc).forEach((e,i)=>{
    if(i)strip.appendChild(Object.assign(document.createElement('div'),
      {className:'arrow',textContent:'·'}));
    strip.appendChild(operand(e));
  });
  // Intermediates: each parenthesised sub-expression, as its own tensor.
  const pts=R.reduceSpec?members:[shown];
  collectInter(R).forEach(it=>{
    strip.appendChild(Object.assign(document.createElement('div'),
      {className:'arrow',textContent:'→'}));
    const ranks=it.vars.map(rankOfVar);
    const cap=it.cap+
      '<sub class="gen">'+(it.gen?resolveGen(it.gen,s.iteration)+',':'')+
      it.vars.join(',')+'</sub>';
    strip.appendChild(tcard(cap,
      miniGrid('__inter'+it.label,it.cells,interMarks(it,pts),'rd',null,
               it.vars,ranks),' inter'));});

  // A reduction runs on the Map's results, not on its inputs, so show those.
  const am=afterMapCard(R,members);
  if(am){strip.appendChild(Object.assign(document.createElement('div'),
      {className:'arrow',textContent:'→'}));
    strip.appendChild(am);}
  const ar=afterReduceCard(R);
  if(ar){strip.appendChild(Object.assign(document.createElement('div'),
      {className:'arrow',textContent:'→'}));
    strip.appendChild(ar);
    outer.forEach(e=>{strip.appendChild(Object.assign(document.createElement('div'),
      {className:'arrow',textContent:'·'}));
      strip.appendChild(operand(e));});}
  strip.appendChild(Object.assign(document.createElement('div'),
    {className:'arrow',textContent:'→'}));
  // The output card is also the picker: click a cell to follow that value.
  const outRanks=(R.einsum.output_ranks||[]).map(rankNameOf);
  strip.appendChild(tcard(capOf(R.output,outRanks,s.iteration),
    miniGrid(R.output,R.result,new Set([EXEC.sel]),'wr',
             k=>{EXEC.sel=k;writeSpaceNote();renderPoint();},
             dataVars(R.output,outRanks)),
    ' out'));}

function rankNameOf(r){
  if(!r)return '?';
  if(r.kind==='var')return r.name;
  if(r.kind==='literal')return String(r.value);
  if(r.kind==='arith')return rankNameOf(r.lhs)+r.op+rankNameOf(r.rhs);
  return '?';}

// ---- provenance -> cards, post-order so operands come before the ops -----
function walkProv(p,out){
  if(!p)return;
  if(p.reads){ out.push(readsCard(p.reads)); return; }
  if(p.tensor!==undefined&&!p.scalar){ return; }        // leaf, shown inline
  if(p.scalar){ return; }
  if(p.anonymous){ walkProv(p.inner,out); return; }
  if(p.op==='not'){ walkProv(p.inner,out); return; }
  if(p.merge!==undefined){
    walkProv(p.lhs,out); walkProv(p.rhs,out);
    out.push(opCard(p));
  }}

function readsCard(reads){
  return '<div class="step"><h4>Operands read</h4>'+reads.map(operandLine).join('')+
    '</div>';}

function operandLine(p){
  if(!p)return '';
  if(p.rank)return '<div class="opnd">'+p.rank+' = <span class="v">'+fmt(p.value)+'</span></div>';
  if(p.scalar)return '<div class="opnd">literal <span class="v">'+fmt(p.value)+'</span></div>';
  if(p.anonymous)
    return '<div class="opnd">( … )<sub>'+(p.boundTo||[]).join(',')+'</sub> = '+
      (p.present?'<span class="v">'+fmt(p.value)+'</span>'
                :'<span class="abs">absent</span>')+'</div>';
  if(p.op==='occupancy')
    return '<div class="opnd">‖'+shownName(p.tensor)+'‖ <span style="color:#aaa">(entries it holds)</span> = <span class="v">'+fmt(p.value)+'</span></div>';
  if(p.op==='not')
    return '<div class="opnd">¬'+plain(p.inner)+' = '+
      (p.value?'<span class="v">true</span>':'<span class="abs">false</span>')+'</div>';
  if(p.merge!==undefined)
    return '<div class="opnd">'+'⟨label '+p.label+'⟩ = '+
      (p.present?'<span class="v">'+fmt(p.value)+'</span>'
                :'<span class="abs">absent</span>')+'</div>';
  const g=emptyGlyph(p.tensor);
  return '<div class="opnd">'+plain(p)+' = '+
    (p.present?'<span class="v">'+fmt(p.value)+'</span>'
              :'<span class="abs">absent'+(g&&g!=='false'?' (empty = '+g+')':'')+
               '</span>')+'</div>';}

function plain(p){
  if(!p)return '?';
  if(p.scalar)return fmt(p.value);
  if(p.tensor)return shownName(p.tensor)+'<sub>'+(p.ranks||[]).join(',')+'</sub>'+
    (p.coord!==null?'&nbsp;<span style="color:#aaa">['+p.coord+']</span>':'');
  if(p.anonymous)return '( … )';
  if(p.op==='not')return '¬'+plain(p.inner);
  return '⟨label '+p.label+'⟩';}

function opCard(p){
  const tt=EdgeDisplay.MERGE_TT[p.merge];
  const hit=(p.lhsPresent?2:0)+(p.rhsPresent?1:0);
  const cells=[[0,'—','—'],[1,'—','✓'],[2,'✓','—'],[3,'✓','✓']];
  const ttHtml='<table class="tt"><tr><th>left</th><th>right</th><th>out</th></tr>'+
    cells.map(([i,l,r])=>'<tr class="'+(i===hit?'hit':'')+'">'+
      '<td class="'+(i===hit?'hit':'')+'">'+l+'</td>'+
      '<td class="'+(i===hit?'hit':'')+'">'+r+'</td>'+
      '<td class="'+(i===hit?'hit':'')+'">'+(tt[i]?'present':'absent')+'</td></tr>')
      .join('')+'</table>';
  return '<div class="step"><h4>Label '+p.label+
    ' &nbsp;<span class="op cp">'+p.computeGlyph+'</span>'+
    '<span class="op mg">'+p.mergeGlyph+'</span></h4>'+
    operandLine(p.lhs)+operandLine(p.rhs)+
    '<div style="margin:7px 0 3px;font-size:11px;color:#888">'+
      'Merge <b>'+p.mergeGlyph+'</b> decides presence from the two operands:'+
      '</div>'+ttHtml+
    '<div class="opnd" style="margin-top:7px">'+
      (p.present
        ? 'present, so compute <b>'+p.computeGlyph+'</b> → <span class="v">'+
          fmt(p.value)+'</span>'
        : '<span class="abs">absent — the compute never runs</span>')+
    '</div></div>';}

// ---- wiring --------------------------------------------------------------

render();
document.getElementById('mjx').addEventListener('load',()=>{
  if(window.MathJax&&MathJax.startup&&MathJax.startup.promise)MathJax.startup.promise.then(render);});
</script></body></html>"""
# Placeholder names must not contain one another: `.replace("TRACE", ...)`
# would otherwise chew the middle out of "SEQTRACE" and leave a syntax error.
_PH=["TRACE","DOMAINCFG","EXTENTMAP","RANKMAP","GROUPMAP","RANKNAMES","DESCS","ALIASMAP",
     "PAGETITLE","CRUMBHTML",
     "IRPROGRAM","EINSUMIDX","TSIDEMAP","PANELTITLE"]
for _a in _PH:
    for _b in _PH:
        if _a!=_b and _a in _b:
            sys.exit(f"placeholder {_a!r} is a substring of {_b!r}; rename one")

out=(HTML.replace("/*INTERPRETER*/",INTERP)
     .replace("/*DOMAINVIEWS*/",DVIEWS)
     .replace("TRACE",json.dumps(trace_header(T)))
     .replace("DOMAINCFG",json.dumps(DOMAIN)).replace("EXTENTMAP",json.dumps(EXTENTS))
     .replace("PAGETITLE",TITLE).replace("CRUMBHTML",CRUMB)
     .replace("PANELTITLE",PANEL_TITLE)
     .replace("RANKMAP",json.dumps(RANKS)).replace("GROUPMAP",json.dumps(GROUPS))
     .replace("RANKNAMES",json.dumps(RANKNAMES))
     .replace("TSIDEMAP",json.dumps(TENSORSIDE)).replace("DESCS",json.dumps(DESCS))
     .replace("IRPROGRAM",json.dumps(IR)).replace("EINSUMIDX",json.dumps(EINSUM_IDX))
     .replace("ALIASMAP",json.dumps(ALIAS)))
open(os.path.join(OUT,"index.html"),"w").write(out)
print("index.html written:",os.path.join(OUT,"index.html"),len(out),"bytes")
