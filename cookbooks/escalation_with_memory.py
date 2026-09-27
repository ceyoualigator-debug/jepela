#!/usr/bin/env python3
"""Memory-first routing: the same complaint from two accounts; only one has standing facts in memory.

Writes the priority account's facts once, then decides the same message for both with compare on,
so the answer shows what the memory changed. The control account must not move.
"""
from _common import MODEL, client, table
from jepela import Choice, Noul

FACTS = ("Northwind Traders holds a priority support contract: every complaint from Northwind is escalated to a named person within the hour.\n"
         "Northwind Traders threatened to leave in August after a slow reply.")
MESSAGE = "Hi, this is {name}. Our integration has been failing since this morning and nobody has answered our email."
QUESTIONS = {
    "escalate": Noul("Should this message be escalated to a person right now?"),
    "route": Choice("Who should handle it?", {"bot": "the automated assistant", "support_queue": "the general support queue", "named_person": "a named account manager"}),
}

with client() as c:
    c.delete("northwind"); c.delete("contoso")
    c.remember("northwind", FACTS)
    rows = []
    for name, customer in (("Northwind Traders", "northwind"), ("Contoso", "contoso")):
        r = c.system_one({"message": MESSAGE.format(name=name)}, QUESTIONS, model=MODEL, subject=customer, memory={"compare": True})
        a, w = r.answers, r.memory.without_memory
        rows.append([name, r.memory.lines_used, f"{w['escalate'].noul:.2f} -> {a['escalate'].noul:.2f}", f"{w['route'].choice} -> {a['route'].choice}",
                     f"{w['route'].probabilities.get('named_person', 0):.2f} -> {a['route'].probabilities.get('named_person', 0):.2f}"])
    table(rows, ["account", "lines", "escalate: without -> with", "route: without -> with", "p(named person)"])
    print(f"\nmodel {r.model} (checkpoint {r.engine['checkpoint']}); the control account has no memory, so its two answers are identical by construction")
