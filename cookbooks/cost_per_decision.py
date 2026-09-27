"""Cost per decision: the whole customer history in every request, against the history in memory.

A stateless decision API (Jev is one) knows only what the request carries, so an application sends the customer's
history with every decision and pays for all of it. With Jepela the history is written to the subject's memory once;
each decision sends the situation and names the subject, and only the recalled lines go to the engine.

Both ways run here on the same Jepela engine, with the same 60 decisions (20 customers, 3 decisions each) whose right
answers are known by construction: each depends on one fact among about 30 history lines per customer (support tier,
reply language, marketing consent; the rest is ordinary history). Printed per way: tokens sent (what a per-token
bill counts when everything sent is billed), tokens the engine read (Jepela bills these), accuracy, and time.

What this does not measure: Jev itself. Jev's tokenizer, window and accuracy differ; the tokens sent in the
first way are what an application would send to any stateless API. Accuracy here compares the two ways on the
Jepela engine only.

Run:  JEPELA_API_KEY=... JEPELA_BASE_URL=http://127.0.0.1:8797 python3 cookbooks/cost_per_decision.py
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import MODEL, client, table  # noqa: E402

COMPANIES = ["Northwind Traders", "Contoso", "Fabrikam", "Tailspin Toys", "Globex", "Initech", "Umbrella Foods", "Stark Parts",
             "Wayne Freight", "Acme Tools", "Hooli", "Vandelay Imports", "Soylent Farms", "Cyberdyne Labs", "Wonka Sweets",
             "Oscorp Metals", "Gringotts Finance", "Pied Piper", "Dunder Paper", "Massive Dynamic"]
LANGS = {"english": "English", "swedish": "Swedish", "german": "German"}
FILLER = ["{c} ordered {n} licences in {m} 2025.", "{c}'s account manager is {p}.", "{c} had a billing question about invoice {n} in {m}.",
          "{c} attended our webinar on data exports in {m}.", "{c} renewed its contract in {m} for two years.",
          "{c} uses the reporting module every week.", "{c} asked for a training session for {n} new users in {m}.",
          "{c}'s main office moved to a new address in {m}.", "{c} integrated our API with their warehouse system in {m}.",
          "{c} rated our support {n} out of 10 in the {m} survey.", "{c} added {n} users to their workspace in {m}.",
          "{c} requested a copy of invoice {n} in {m}.", "{c}'s finance team pays by bank transfer.",
          "{c} tested the beta of the mobile app in {m}.", "{c} closed a ticket about slow exports in {m}."]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October"]
PEOPLE = ["Lena Holm", "Omar Aziz", "Sara Ek", "Jonas Berg", "Anna Lind", "Peter Olsen"]

ESCALATE = {"type": "noul", "instructions": "Should this ticket be escalated to a senior engineer now?"}
LANGUAGE = {"type": "choice", "instructions": "Which language should the reply be written in?",
            "criteria": {k: v for k, v in LANGS.items()}}
SEND = {"type": "noul", "instructions": "Should this launch mail be sent to them now?"}


def customers(seed: int = 7) -> list:
    rnd = random.Random(seed)
    out = []
    for i, name in enumerate(COMPANIES):
        premium, lang, consent = i % 2 == 0, list(LANGS)[i % 3], i % 4 in (0, 3)
        key = [f"{name} pays for premium support; escalate every outage to a senior engineer at once." if premium else
               f"{name} is on the free plan with community support only; its outages are not escalated.",
               f"{name}'s team wants every reply written in {LANGS[lang]}.",
               f"{name} subscribed to our newsletter and wants launch news." if consent else
               f"{name} asked to receive no marketing mail."]
        filler = [rnd.choice(FILLER).format(c=name, n=rnd.randint(2, 900), m=rnd.choice(MONTHS), p=rnd.choice(PEOPLE)) for _ in range(27)]
        history = filler[:]
        for line in key:
            history.insert(rnd.randint(0, len(history)), line)
        subject = "c-" + name.lower().split()[0]
        out.append({"name": name, "subject": subject, "history": history, "key": key, "decisions": [
            (f"{name}: our dashboard has been down since 9:00 and nobody can log in.", "escalate", ESCALATE, premium),
            (f"{name} sent a support question about exporting reports.", "language", LANGUAGE, lang),
            (f"A product launch mail is ready to send to {name}.", "send", SEND, consent)]})
    return out


def right(q: dict, answer: dict, expected) -> bool:
    return (answer["noul"] >= 0.5) == expected if q["type"] == "noul" else answer["choice"] == expected


WAYS = {
    "whole history in every request": {},
    "memory, recall by state only (before 2026-09-26)": {"memory": True, "question_words": False},
    "memory (default: question words in recall)": {"memory": True, "question_words": True},
    "memory, account facts pinned, state only": {"memory": True, "pin": True, "question_words": False},
    "memory, pinned + question words": {"memory": True, "pin": True, "question_words": True},
}


def patient(call, *args):
    """A call that waits when the key's rate limit is reached, as a production client would."""
    from jepela.errors import RateLimitError
    for _ in range(20):
        try:
            return call(*args)
        except RateLimitError as exc:
            time.sleep(exc.retry_after or 5)
    return call(*args)


used: dict = {}


def run(jepela, data: list, way: dict) -> dict:
    sent, read, ok, ms, n = [], [], 0, [], 0
    with_memory = way.get("memory", False)
    for c in data:
        if with_memory:
            patient(jepela.delete, c["subject"])
            if way.get("pin"):                  # the account facts pinned, the rest of the history remembered
                for line in c["key"]:
                    patient(jepela.pin, c["subject"], line)
                patient(jepela.remember, c["subject"], "\n".join(l for l in c["history"] if l not in c["key"]))
            else:
                patient(jepela.remember, c["subject"], "\n".join(c["history"]))
        for state, qid, q, expected in c["decisions"]:
            body = {"model": MODEL, "questions": {qid: q}}
            if with_memory:
                body.update(state=state, subject=c["subject"])
                body["memory"] = {"question_words": bool(way.get("question_words"))}
            else:
                body.update(state="History of this customer:\n" + "\n".join(c["history"]) + "\n\nNow: " + state)
            t0 = time.perf_counter()
            out = patient(jepela.request, "POST", "/v1/systemone", body)
            ms.append((time.perf_counter() - t0) * 1000)      # includes any wait for the rate limit; the median hides it
            used.update(model=out.get("model"), checkpoint=(out.get("engine") or {}).get("checkpoint"))
            u = out["usage"]
            read.append(u["input_tokens"])
            sent.append(u["input_tokens"] + u.get("state_tokens", 0) - u.get("state_tokens_read", 0))
            ok += right(q, out["answers"][qid], expected)
            n += 1
    return {"decisions": n, "tokens_sent": statistics.mean(sent), "tokens_read": statistics.mean(read),
            "accuracy": ok / n, "median_ms": statistics.median(ms)}


def main() -> None:
    jepela = client()
    data = customers()
    results = {label: run(jepela, data, way) for label, way in WAYS.items()}
    price = 0.042 / 1e6
    rows = [[label, r["decisions"], f"{r['tokens_sent']:.0f}", f"{r['tokens_read']:.0f}", f"{100 * r['accuracy']:.1f}%",
             f"${r['tokens_sent'] * price * 1e6:.2f}", f"{r['median_ms']:.0f}"] for label, r in results.items()]
    table(rows, ["way", "decisions", "tokens sent per decision", "tokens read", "accuracy", "cost per million decisions*", "median ms"])
    print(f"\n* tokens sent x $0.042 per million tokens. History: about 30 lines per customer, {len(data)} customers.")
    print(f"\nmodel {used.get('model')} (checkpoint {used.get('checkpoint')}); Jev itself is not measured here")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
