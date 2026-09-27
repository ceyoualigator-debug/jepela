#!/usr/bin/env python3
"""Speculative fan-out: every question that might matter, in one request per ticket, the code picks.

Five questions per ticket. Severity and steps matter only for bug reports, refund only for billing;
they are asked anyway because one request costs the same engine pass. Prints one row per ticket and
the measured time and cost.
"""
from _common import MODEL, Timer, client, table
from jepela import Choice, Noul, Score

TICKETS = [
    "The export button does nothing since yesterday's update. Console shows a 500. Steps: open a report, click Export, nothing happens.",
    "You charged my card twice for September. I want the second charge refunded today.",
    "It would be great if the dashboard could show last quarter next to this one.",
    "I can't log in, password reset emails never arrive, and I have a demo in an hour!!!",
    "How do I change the billing email on my account?",
    "Thanks for the quick fix last week, everything works now.",
]
QUESTIONS = {
    "category": Choice("What kind of ticket is this?", {"bug_report": "something is broken", "billing": "charges, invoices, refunds",
                                                        "feature_request": "asks for something new", "account": "login, settings, access", "other": "none of these"}),
    "bug_severity": Score("If this is a bug, how severe?", ["cosmetic", "degraded but a workaround exists", "blocking, no workaround"]),
    "has_steps": Noul("Does the ticket give steps to reproduce a problem?"),
    "refund_requested": Noul("Is the customer asking for a refund?"),
    "frustration": Score("How frustrated is the writer?", ["calm", "annoyed", "angry"]),
}

with client() as c:
    rows, total_ms, total_cost = [], 0.0, 0.0
    for t in TICKETS:
        tm = Timer(); r = c.system_one(t, QUESTIONS, model=MODEL); ms = tm.ms()
        a = r.answers; cat = a["category"].choice
        detail = (f"severity {a['bug_severity'].score:.1f}, steps {a['has_steps'].noul:.2f}" if cat == "bug_report"
                  else f"refund {a['refund_requested'].noul:.2f}" if cat == "billing" else "")
        rows.append([t[:48] + "…", cat, f"{a['category'].confidence:.2f}", detail, f"{a['frustration'].score:.1f}", ms])
        total_ms += ms; total_cost += r.usage.cost
    table(rows, ["ticket", "category", "conf", "used because of the category", "frustr.", "ms"])
    print(f"\n{len(TICKETS)} tickets, 5 questions each, {len(TICKETS) * 5} answers: {total_ms:.0f} ms round trip in total, cost {total_cost:.5f} {r.usage.currency}; model {r.model} (checkpoint {r.engine['checkpoint']})")
