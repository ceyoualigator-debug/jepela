#!/usr/bin/env python3
"""A game character with a memory of the player: the subject is the player, the state is the scene.

The merchant decides how to treat the player. With no memory every visit is the first; with the
player's deeds in memory the same scene gets a different answer. Compare is on, so both show.
"""
from _common import MODEL, client, table
from jepela import Choice, Noul

PLAYER = "player-7"
DEEDS = ("The player stole three potions from the merchant's stall last week.\n"
         "The player returned a lost purse to a villager and refused a reward.")
SCENES = [
    "The player walks up to the merchant's stall and asks to buy a healing potion.",
    "The player asks the merchant to keep a package safe until tomorrow.",
    "The player offers to guard the stall while the merchant fetches supplies.",
]
Q = {
    "attitude": Choice("How does the merchant treat the player?", {"warm": "friendly, offers a discount", "neutral": "business as usual",
                                                                      "wary": "polite but watchful, no favours", "refuse": "refuses to deal"}),
    "calls_guard": Noul("Does the merchant call the town guard?"),
}

with client() as c:
    c.delete(PLAYER); c.remember(PLAYER, DEEDS)
    rows = []
    for scene in SCENES:
        r = c.system_one({"scene": scene, "player": PLAYER}, Q, model=MODEL, subject=PLAYER, memory={"compare": True})
        a, w = r.answers, r.memory.without_memory
        rows.append([scene[:52] + "…", f"{w['attitude'].choice} -> {a['attitude'].choice}", f"{w['calls_guard'].noul:.2f} -> {a['calls_guard'].noul:.2f}", r.memory.lines_used])
    table(rows, ["scene", "attitude: without -> with memory", "calls guard", "lines"])
    c.delete(PLAYER)
    print(f"\nmodel {MODEL}; the subject is a player, the memory holds deeds, the scene is the state")
