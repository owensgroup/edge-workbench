# -*- coding: utf-8 -*-
"""Display metadata for the Algorithm X probe. Minimal on purpose."""
MEANING = {}
LATEX = {}
RANKNAMES = {"A": ["R", "C"], "S": ["R"], "Path": ["R"], "SelRow": ["R"],
             "CovCol": ["C"], "ActiveCol": ["C"], "ConflictRow": ["R"],
             "ActiveRow": ["R"], "Sol": ["R"], "RowCounts": ["C"],
             "ActiveCounts": ["C"], "PickedCol": ["C"], "Candidates": ["R"],
             "NewChoices": ["R"], "T": ["R"], "F": ["R"],
             "Col": ["C"], "Row": ["R"]}
DESC = {}
STATEFUL = {"S", "Path"}
GROUPS = {"static1": ["A"], "static2": ["Col"],
          "state1": ["S", "Path"], "state2": ["SelRow"]}
TITLE = "Algorithm X (probe)"
CRUMB = "Exact Cover (Algorithm X)"
