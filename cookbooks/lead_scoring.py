#!/usr/bin/env python3
"""Lead scoring: a gate and five scoring questions per inbound message, one request, a route computed in code.

A lead who asks to stop receiving messages is taken out before any scoring: the gate is a noul and code
acts on it. The money signal is two nouls, an approved budget and a vendor already paid, combined in code:
one condition per noul.
"""
from _common import MODEL, client, table
from jepela import Choice, Noul, Score

LEADS = [
    "Hi, we're a 400-person logistics company evaluating decision APIs for our support desk. Budget approved for Q4, need SSO and an on-prem option. Can we talk this week?",
    "student here, is there a free tier? doing a school project on AI",
    "We run three restaurants and want to automate our reservation emails. Not sure what we need yet.",
    "URGENT: our current vendor is shutting down in 30 days, we process 2M decisions a month, need a migration plan and pricing today.",
    "unsubscribe",
]
Q = {
    "stop": Noul("Has the lead asked to stop receiving messages?"),
    "fit": Score("How well does this lead fit a business decision API?", ["a personal or school project", "a small business with an unclear need",
                                                                          "a business with a clear need", "a large organisation with a well-defined need"]),
    "timing": Score("How soon would they buy?", ["no purchase intent", "someday", "this quarter", "now"]),
    "approved": Noul("Does the lead mention an approved budget?"),
    "pays": Noul("Does the lead already pay a vendor for this?"),
    "size": Choice("How large is the organisation?", {"individual": "a single person, such as a student or a freelancer",
                                                      "small": "a small business, such as a shop or a few restaurants",
                                                      "mid": "a company with hundreds of employees", "large": "an enterprise with thousands of employees",
                                                      "unknown": "the message does not say"}),
}
SIZE = {"individual": 0, "small": 0.3, "mid": 0.7, "large": 1, "unknown": 0.3}

with client() as c:
    rows = []
    for lead in LEADS:
        r = c.system_one(lead, Q, model=MODEL)
        a = r.answers
        if a["stop"].noul >= 0.5:                       # the gate: no scoring, no sequence
            rows.append([lead[:48] + "…", f"{a['stop'].noul:.2f}", "", "", "", "", "", "stop all messages"])
            continue
        money = max(a["approved"].noul, a["pays"].noul)
        score = 0.4 * a["fit"].score / 3 + 0.3 * a["timing"].score / 3 + 0.2 * money + 0.1 * SIZE[a["size"].choice]
        route = "sales call today" if score >= 0.7 else "nurture sequence" if score >= 0.4 else "auto-reply"
        rows.append([lead[:48] + "…", f"{a['stop'].noul:.2f}", f"{a['fit'].score:.1f}", f"{a['timing'].score:.1f}", f"{money:.2f}", a["size"].choice, f"{score:.2f}", route])
    table(rows, ["lead", "stop", "fit", "timing", "budget", "size", "score", "route"])
    print(f"\nmodel {r.model}; the gate, the weights and the thresholds are code, change them without touching a prompt")
