#!/usr/bin/env python3
"""Forgetting on request: remember, decide, forget one concept with a verified removal, decide again, delete.

The trail a data-protection officer wants: what was known, what the decision used, what was removed,
and the proof that recall no longer finds it.
"""
from _common import MODEL, client, table
from jepela import Noul

SUBJECT = "fabrikam"
FACTS = ("Fabrikam's contact Anna Berg asked on 2026-09-01 that no marketing mail be sent to her.\n"
         "Fabrikam pays yearly; the next invoice is due in December.\n"
         "Fabrikam's support tickets go to the enterprise desk.")
STATE = {"task": "A new product launch mail is ready to send to all Fabrikam contacts, including Anna Berg."}
Q = {"send": Noul("Should this mail be sent as planned?"), "opt_out": Noul("Has any recipient asked not to receive marketing mail?")}

with client() as c:
    c.delete(SUBJECT)
    rem = c.remember(SUBJECT, FACTS)
    rows = []
    def step(label):
        r = c.system_one(STATE, Q, model=MODEL, subject=SUBJECT, memory={"compare": False})
        rows.append([label, c.memory(SUBJECT).lines_stored, r.memory.lines_used, f"{r.answers['send'].noul:.2f}", f"{r.answers['opt_out'].noul:.2f}",
                     "; ".join(h["text"][:40] + "…" for h in r.memory.hits)])
        return r
    step("after remember")
    fg = c.forget(SUBJECT, "no marketing mail")
    step(f"after forget (verified {fg['verified_forgotten']}, removed {len(fg['removed_lines'])})")
    c.delete(SUBJECT)
    r = step("after delete")
    table(rows, ["step", "stored", "used", "send", "opt-out known", "lines the engine saw"])
    print(f"\nmodel {r.model} (checkpoint {r.engine['checkpoint']}); forgetting is checked against recall before it is reported as done")
