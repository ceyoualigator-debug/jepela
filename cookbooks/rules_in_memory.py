#!/usr/bin/env python3
"""Rules in memory, measured: which of Mia's rules the engine follows, and which only code can hold.

Part 1: the bet on ten table states where 17 has just come up: no memory, a rule that names the
forbidden bet, a rule that says what to do, and the same rule with only Mia's bets offered in code.
Part 2: the stop-loss at a loss of 12 and of 30, as a memory line, and as a rule with `when` that the
gateway checks in code against the session result sent in `values`.
"""
from collections import Counter

from _common import MODEL, client, table
from jepela import Choice, Noul

BETS = {"no_bet": "sit this spin out", "red": "red, pays 1 to 1", "black": "black, pays 1 to 1", "even": "even, pays 1 to 1", "odd": "odd, pays 1 to 1",
        "low": "1 to 18, pays 1 to 1", "high": "19 to 36, pays 1 to 1", "dozen_1": "first dozen, pays 2 to 1", "straight_17": "the single number 17, pays 35 to 1"}
MIAS_BETS = {k: BETS[k] for k in ("no_bet", "red", "black", "even", "odd", "low", "high")}   # a rule the engine cannot break: the options offered
STATES = [(33, -12, [17, 0, 4, 29, 33]), (12, 25, [17, 17, 3, 8, 9]), (6, -5, [15, 17, 22, 1, 30]), (9, 10, [2, 9, 17, 17, 36]), (20, -8, [17, 5, 12, 8, 26]),
          (3, 4, [17, 31, 17]), (15, -20, [11, 17, 24, 17, 2]), (27, 18, [30, 17, 6, 19, 17]), (8, -2, [17, 17, 17, 4]), (40, -15, [5, 17, 28, 13, 17])]
POSITIVE = "Mia bets red, black, even, odd, low or high."
WORDINGS = [("no memory", None, BETS),
            ("names the forbidden bet", "Mia's rule: only even-money bets, never a single number such as 17, never a dozen.", BETS),
            ("says what to do", POSITIVE, BETS),
            ("says what to do, only Mia's bets offered", POSITIVE, MIAS_BETS)]
STOP = {"stop": Noul("Should the player stop playing for this session now?")}


def state(spin, net, last):
    return f"European roulette, single zero. Player Mia. Bankroll {100 + net} units. Session result so far {net:+d} units after {spin} spins. Last results: {', '.join(map(str, last))}."


with client() as c:
    rows = []
    for label, rule, options in WORDINGS:
        c.delete("mia")
        if rule:
            c.remember("mia", rule)
        bet = {"bet": Choice("Which bet should the player place on this spin?", options)}
        picks = [c.system_one(state(*s), bet, model=MODEL, subject="mia" if rule else None).answers["bet"].choice for s in STATES]
        rows.append([label, picks.count("straight_17"), ", ".join(f"{b} x{n}" for b, n in Counter(picks).most_common())])
    table(rows, ["memory", f"picked 17 (of {len(STATES)})", "bets"])
    print()
    rows = []
    for label, kind in (("no memory", None), ("the stop-loss as a memory line", "line"), ("a rule with when, checked in code", "rule")):
        c.delete("mia")
        if kind == "line":
            c.remember("mia", "Mia's stop-loss for a session is 30 units.")
        if kind == "rule":                                  # checked against `values` at every decision; the engine sees the text only when it holds
            c.rules_add("mia", "session_result <= -30", "Mia's stop-loss is reached: she stops playing now.")
        cells = []
        for net in (-12, -30):
            stops = [c.system_one(state(spin, net, last), STOP, model=MODEL, subject="mia" if kind else None, values={"session_result": net}).answers["stop"].noul
                     for spin, last in ((25, [8, 10, 13, 20, 26]), (10, [0, 5, 31, 2, 17]))]
            cells.append(f"{min(stops):.2f} to {max(stops):.2f}")
        rows.append([label, *cells])
    table(rows, ["memory", "stop answer at -12", "stop answer at -30"])
    c.delete("mia")
    print(f"\nmodel {MODEL}; a bet the code does not offer is never picked, and a limit checked in code fires only when it is reached")
