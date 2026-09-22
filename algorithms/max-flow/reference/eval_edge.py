import json, random, sys, os
INF=float('inf')
N=6; S=0; T=5
SEED=int(os.environ.get("SEED","0"))
rng=random.Random(SEED)
CAP={(0,1):16,(0,2):13,(1,2):10,(2,1):4,(1,3):12,(3,2):9,(2,4):14,(4,3):7,(3,5):20,(4,5):4}
VS=range(N)

# ---- sparse tensor helpers.  dict coord->value ; absent == empty ----
def k(*c): return ",".join(map(str,c))
def uni(a,b,f,za=0,zb=0):           # union merge
    return {c:f(a.get(c,za),b.get(c,zb)) for c in set(a)|set(b)}
def nz(d):                            # value == empty(0)  =>  absent
    return {c:v for c,v in d.items() if v!=0}
def isect(a,b,f):                   # intersection merge
    return {c:f(a[c],b[c]) for c in set(a)&set(b)}
def cmp_isect(a,b,f):               # comparison: keep only where TRUE
    return {c:True for c in set(a)&set(b) if f(a[c],b[c])}

steps=[]; STATE={}
def rec(eid,expr,cap,out,hl=None):
    steps.append({"id":len(steps),"einsum":eid,"expr":expr,"caption":cap,
                  "output":out,"iteration":STATE.get("i"),
                  "graphHighlight":hl or {"nodes":[],"edges":[]},
                  "state":{n:dict(t) for n,t in STATE.items() if isinstance(t,dict)}})

# ---- initializations ----
C={k(u,v):c for (u,v),c in CAP.items()}
# G is a declared input the cascade never reads -- C carries the capacities --
# but it is part of the instance, and an input held on one side only shows up
# as a disagreement about the algorithm when it is a disagreement about setup.
G={k(u,v):1 for (u,v) in CAP}
Sv={k(S):True}; Tv={k(T):True}
D={k(u):(N if u==S else 0) for u in VS}          # D_{1,u}=0 ; D_{1,s}=|V|
STATE.update(G=G,C=C,S=Sv,T=Tv,D=D,F={},E={},R={})
rec("init","F_{0,u,v}=0, E_{0,u}=0, D_{1,u}=0, D_{1,u:u=s}=|V|, S_{u:u=s}, T_{u:u=t}",
    "Initializations.","D")

# ---- E01 saturate source edges ----
FS={k(u,v):c for (u,v),c in CAP.items() if u==S}
STATE["FS"]=FS
rec("E01","FS_{1,u,v} = S_u · C_{u,v} :: ⋀ *(∩)",
    "Saturate every edge out of the source:  f(s,v) = c(s,v).","FS",
    {"nodes":[S],"edges":[[S,v] for (u,v) in CAP if u==S]})

# ---- E02 mirror it as negative flow ----
F={}
for c in set(FS)|{k(v,u) for c in FS for u,v in [map(int,c.split(","))]}:
    u,v=map(int,c.split(","))
    val=FS.get(k(u,v),0)-FS.get(k(v,u),0)
    if val!=0: F[c]=val
STATE["F"]=F
rec("E02","F_{1,u,v} = FS_{1,u,v} · FS_{1,v,u} :: ⋀ -(∪)",
    "Mirror the preflow as negative flow on the reverse edge:  f(v,s) = -c(s,v).  F is now antisymmetric.","F",
    {"nodes":[S],"edges":[[S,v] for (u,v) in CAP if u==S]})

# ---- E03 excess = net inflow ----
E={}
for c,val in F.items():
    u,v=map(int,c.split(",")); E[k(v)]=E.get(k(v),0)+val
E={c:v for c,v in E.items() if v!=0}
STATE["E"]=E
rec("E03","E_{1,v} = F_{1,u,v} :: ⋁ +(∪)",
    "Excess is net inflow; outflow is already stored as negative entries.","E")

# ---- E05 residual init ----
dom=set(CAP)|{(v,u) for (u,v) in CAP}
R={}
for (u,v) in sorted(dom):
    if u==S:              pass                             # r(s,v)=0  ->  empty
    elif v==S and u!=S:   R[k(u,v)]=CAP.get((v,u),0)
    elif (u,v) in CAP:    R[k(u,v)]=CAP[(u,v)]
STATE["R"]=R
rec("E04","R_{1,u,v} = 0 if u=s ; C_{v,u} if v=s ∧ u≠s ; C_{u,v} otherwise",
    "Residual graph. r(s,v)=0 equals the empty value, so those cells are simply absent.","R")

NST={k(u):True for u in VS if u not in (S,T)}
STATE["NST"]=NST; rec("E05","NST_u = ¬S_u · ¬T_u :: ⋀ AND(∩)","Internal vertices.","NST")

# ---- main loop ----
i=1; MAXIT=300
while True:
    STATE["i"]=i
    Act={c:True for c in NST if E.get(c,0)>0}
    STATE["Act"]=Act
    rec("E06","Act_{i,u} = NST_u ·¹ (E_{i,u} ·² 0)_{i,u} :: ⋀¹ ←(∩) ⋀² >(∩)",
        f"Active vertices (internal, excess>0): {sorted(int(c) for c in Act)}","Act",
        {"nodes":[int(c) for c in Act],"edges":[]})

    if not Act:
        rec("stop","◇ : ‖Act_{i+1}‖ ≡ 0","No active vertex — done.","Act"); break
    if i>MAXIT: rec("abort","","ITERATION CAP HIT","Act"); break

    ActR={c:True for c in R if k(int(c.split(",")[0])) in Act}
    STATE["ActR"]=ActR
    rec("E07","ActR_{i,u,v} = Act_{i,u} · R_{i,u,v} :: ⋀ ←(∩)",
        "Residual edges leaving an active vertex. Saturated edges are absent, so ∩ skips them.","ActR")

    Lbl={}
    for u in VS:
        for v in VS:
            if D.get(k(u),INF)==D.get(k(v),INF)+1: Lbl[k(u,v)]=True
    STATE["Lbl"]=Lbl
    rec("E08","Lbl_{i,u,v} = D_{i,u} · (D_{i,v} + 1)_{i,v} :: ⋀ ≡(∩)","Distance rule D(u) = D(v)+1.","Lbl")

    Adm={c:True for c in set(ActR)&set(Lbl)}
    STATE["Adm"]=Adm
    rec("E09","Adm_{i,u,v} = ActR · Lbl :: ⋀ AND(∩)",
        f"Admissible edges: {sorted(Adm)}","Adm",
        {"nodes":[],"edges":[[int(x) for x in c.split(",")] for c in Adm]})

    PC={}
    for u in VS:
        cand=sorted(int(c.split(",")[1]) for c in Adm if int(c.split(",")[0])==u)
        if cand: PC[k(u,rng.choice(cand))]=True   # pick-admissible-edge: ANY admissible edge
    STATE["PushCand"]=PC
    rec("E10","PushCand_{i,u,v*} = Adm_{i,u,v} ⋘_{v*} 𝟙(pick-admissible-edge)",
        "One admissible edge per vertex — pick-admissible-edge may choose any.","PushCand",
        {"nodes":[],"edges":[[int(x) for x in c.split(",")] for c in PC]})

    delta={}
    for c in PC:
        u,v=map(int,c.split(","))
        delta[c]=min(E.get(k(u),0),R.get(c,0))
    delta={c:v for c,v in delta.items() if v!=0}
    STATE["delta"]=delta
    rec("E11","delta_{i,u,v} = (E_{i,u} ·¹ R_{i,u,v})_{i,u,v} ·² PushCand :: ⋀¹ min(∩) ⋀² ←(∩)",
        "; ".join(f"push {v} on {c}" for c,v in delta.items()) or "nothing to push","delta",
        {"nodes":[],"edges":[[int(x) for x in c.split(",")] for c in delta]})

    rev={k(v,u):d for c,d in delta.items() for u,v in [map(int,c.split(","))]}
    F=nz(uni(uni(F,delta,lambda a,b:a+b),rev,lambda a,b:a-b))
    STATE["F"]=F; rec("E12","F_{i+1,u,v} = (F ·¹ delta)_{i,u,v} ·² delta_{i,v,u} :: ⋀¹ +(∪) ⋀² -(∪)","Flow update.","F")

    InP={}; OutP={}
    for c,d in delta.items():
        u,v=map(int,c.split(",")); OutP[k(u)]=OutP.get(k(u),0)+d; InP[k(v)]=InP.get(k(v),0)+d
    STATE["InPush"]=InP;  rec("E13","InPush_{i,v} = delta_{i,u,v} :: ⋁ +(∪)","Flow pushed in.","InPush")
    STATE["OutPush"]=OutP; rec("E14","OutPush_{i,u} = delta_{i,u,v} :: ⋁ +(∪)","Flow pushed out.","OutPush")

    E=uni(uni(E,InP,lambda a,b:a+b),OutP,lambda a,b:a-b); E={c:v for c,v in E.items() if v!=0}
    STATE["E"]=E; rec("E15","E_{i+1,u} = (E ·¹ InPush)_{i,u} ·² OutPush :: ⋀¹ +(∪) ⋀² -(∪)","Excess update.","E")

    R=nz(uni(uni(R,delta,lambda a,b:a-b),rev,lambda a,b:a+b))
    STATE["R"]=R; rec("E16","R_{i+1,u,v} = (R ·¹ delta)_{i,u,v} ·² delta_{i,v,u} :: ⋀¹ -(∪) ⋀² +(∪)","Residual update.","R")

    # Written to AdmPost, not Adm. The write-up calls this Adm_{i+1}, but so
    # does E09 in the NEXT round -- two Einsums writing one generation of one
    # tensor. Under a generation-indexed reading, where an assignment adds to
    # a fiber rather than replacing it, E17's entries would survive into that
    # round's push: inactive vertices, the source among them, and edges to
    # vertices that have just relabelled. Giving it its own name is the fix
    # upstream made, and AdmPost is read only by E18.
    Adm2={c:True for c in set(R)&set(Lbl)}
    STATE["AdmPost"]=Adm2; rec("E17","AdmPost_{i+1,u,v} = R_{i+1,u,v} · Lbl_{i,u,v} :: ⋀ →(∩)","Still-admissible edges.","AdmPost")

    HasAdm={k(u):True for u in VS if any(int(c.split(",")[0])==u for c in Adm2)}
    STATE["HasAdm"]=HasAdm; rec("E18","HasAdm_{i+1,u} = AdmPost_{i+1,u,v} :: ⋁ OR(∪)","Vertices that still have somewhere to push.","HasAdm")

    Act2={k(u):True for u in VS if u not in (S,T) and E.get(k(u),0)>0}
    STATE["Act"]=Act2; rec("E19","Act_{i+1,u} = NST_u ·¹ (E_{i+1,u} ·² 0)_{i+1,u} :: ⋀¹ ←(∩) ⋀² >(∩)",
        f"Active after the push: {sorted(int(c) for c in Act2)}","Act",{"nodes":[int(c) for c in Act2],"edges":[]})

    Rel={c:True for c in Act2 if c not in HasAdm}
    STATE["Rel"]=Rel; rec("E20","Rel_{i+1,u} = Act_{i+1,u} · ¬HasAdm_{i+1,u} :: ⋀ AND(∩)",
        f"Must relabel: {sorted(int(c) for c in Rel)}","Rel",{"nodes":[int(c) for c in Rel],"edges":[]})

    NeiLbl={}
    for c in R:
        u,v=map(int,c.split(","))
        if k(u) in Rel and k(v) in D: NeiLbl[c]=D[k(v)]
    STATE["NeiLbl"]=NeiLbl; rec("E21","NeiLbl_{i,u,v} = (R_{i+1,u,v} ·¹ Rel_{i+1,u})_{i,u,v} ·² D_{i,v} :: ⋀¹ ←(∩) ⋀² →(∩)",
        "Distances of residual neighbours, for relabelling vertices only.","NeiLbl")

    MinN={}
    for c,h in NeiLbl.items():
        u=c.split(",")[0]; MinN[u]=min(MinN.get(u,INF),h)
    STATE["MinNeiLbl"]=MinN; rec("E22","MinNeiLbl_{i,u} = NeiLbl :: ⋁ min(∪)","Lowest neighbour distance.","MinNeiLbl")

    NewD={c:h+1 for c,h in MinN.items()}
    STATE["NewD"]=NewD; rec("E23","NewD_{i,u} = (MinNeiLbl · 1)_{i,u} :: ⋀ +(∩)","New distance = min + 1.","NewD")

    D={**D, **NewD}          # <<(∪): right where present, else left
    STATE["D"]=D
    rec("E24","D_{i+1,u} = D_{i,u} · NewD_{i,u} :: ⋀ <<(∪)",
        "; ".join(f"h({c})→{v}" for c,v in NewD.items()) or "no relabel","D",
        {"nodes":[int(c) for c in NewD],"edges":[]})
    i+=1

flow=E.get(k(T),0)
print("iterations:",i,"steps:",len(steps),"max flow:",flow)
print("final D:",{c:D[c] for c in sorted(D,key=int)})
print("final E:",E)
print("final F:",{c:v for c,v in sorted(F.items()) if v})
json.dump({"algorithm":"push-relabel, evaluated from the EDGE cascade","seed":SEED,
           "note":"pick-admissible-edge selects an arbitrary admissible edge; this trace is one sample",
           "graph":{"nodes":list(VS),"edges":[{"u":u,"v":v,"cap":c} for (u,v),c in CAP.items()],
                    "source":S,"sink":T},
           "iterations":i,"maxFlow":flow,"steps":steps},
          open("maxflow_edge_trace.json","w"),indent=1)
