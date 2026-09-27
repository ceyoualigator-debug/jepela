#!/usr/bin/env python3
"""Composite scoring: one Score per dimension, normalised and weighted in code, two rankings from the same answers."""
from _common import MODEL, client, table
from jepela import Score

PROFILES = {
    "Ada": "Eight years of Python, built the data pipeline that the whole company uses; led a team of five for two years; designed a multi-region ingestion system; picked up Rust last year for a side project.",
    "Ben": "Three years of Python and Go; no reports; designed two internal services; learns new stacks quickly and has moved teams three times.",
    "Cy":  "Twelve years, mostly Java, some Python scripts; managed twelve engineers across two teams; owns architecture reviews; rarely codes now.",
}
Q = {                                                  # levels are situations, not degree words
    "python": Score("Depth of Python experience", ["no Python mentioned", "scripts or under two years", "several years in production", "built something others depend on", "many years, owns core systems in Python"]),
    "leadership": Score("Experience leading people", ["no reports", "mentored or led a project informally", "led a small team", "managed a team for years", "managed several teams or managers"]),
    "design": Score("System design experience", ["no design work", "designed one small service", "designed several services", "designed a large or distributed system", "owns architecture across systems"]),
    "generalist": Score("Ability to learn new domains and stacks", ["one stack only", "tried another stack once", "worked in two stacks", "moves between stacks or teams readily", "picks up new domains repeatedly"]),
}
LEVELS = range(5)
WEIGHTS = {"senior engineer": {"python": 0.4, "leadership": 0.1, "design": 0.4, "generalist": 0.1},
           "engineering manager": {"python": 0.15, "leadership": 0.4, "design": 0.2, "generalist": 0.25}}

with client() as c:
    scores = {name: {k: v.score / (len(LEVELS) - 1) for k, v in c.system_one(text, Q, model=MODEL).answers.items()} for name, text in PROFILES.items()}
    rows = [[n, *(f"{s[k]:.2f}" for k in Q)] for n, s in scores.items()]
    table(rows, ["candidate", *Q])
    for role, w in WEIGHTS.items():
        ranked = sorted(scores, key=lambda n: -sum(w[k] * scores[n][k] for k in w))
        print(f"\n{role}: " + ", ".join(f"{n} {sum(w[k] * scores[n][k] for k in w):.2f}" for n in ranked))
    print(f"\nmodel {MODEL}; the same four answers per candidate, two weightings, no second request")
