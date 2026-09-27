#!/usr/bin/env python3
"""Intent routing with confidence gates: a choice and a score decide which handler gets the message.

Simple lookups go to code, domain questions to a specialist with the right context, uncertain or complex
cases to a person. The expensive resource is called only when the cheap decision says so.
"""
from _common import MODEL, client, table
from jepela import Choice, Score

MESSAGES = [
    "Where is my order 88213?",
    "Does the Pro plan include SSO with Okta, and can we get a data-processing agreement?",
    "I want to return the shoes I bought last week, they don't fit.",
    "Your app deleted three months of my notes and support hasn't replied in a week. This is unacceptable.",
    "hi",
    "Can I change the delivery address for order 88213 to my office?",
]
Q = {
    "intent": Choice("What does the customer want?", {"order_status": "where an order is", "product_question": "what a product or plan includes",
                                                      "return": "return or exchange an item", "complaint": "a grievance about service or product",
                                                      "change_order": "change an order that is placed", "other": "unclear or none of these"}),
    "complexity": Score("How much work is a good answer?", ["a lookup or one-line answer", "needs product knowledge or several steps", "needs judgment, policy or negotiation"]),
}
HUMAN_BELOW = 0.5

with client() as c:
    rows = []
    for m in MESSAGES:
        a = c.system_one(m, Q, model=MODEL).answers
        intent, conf, cx = a["intent"].choice, a["intent"].confidence or 0.0, a["complexity"].score
        if conf < HUMAN_BELOW or intent == "other":
            handler = "person (uncertain)"
        elif intent in ("order_status", "change_order") and cx < 1.0:
            handler = "code: order system"
        elif cx >= 1.8 or intent == "complaint":
            handler = "person"
        else:
            handler = f"specialist model with {intent} context"
        rows.append([m[:44] + "…", intent, f"{conf:.2f}", f"{cx:.1f}", handler])
    table(rows, ["message", "intent", "conf", "complexity", "handler"])
    print(f"\nmodel {MODEL}; the gate sends confidence under {HUMAN_BELOW} to a person")
