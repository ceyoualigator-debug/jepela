#!/usr/bin/env python3
"""Devices as subjects: the same reading means different things for different machines.

A limit is a number, and the engine reads words, not arithmetic. So each device's limit stays in code:
`derive` compares the reading with it and, when the reading is over, hands the engine one sentence that
says so. Each device's memory keeps what a technician knows, in words.
"""
from _common import MODEL, client, table
from jepela import Choice, Noul

LIMIT_C = {"pump-12": 95, "pump-13": 75}          # bearing temperature limits, from the maintenance manual
MEMORY = {"pump-12": "Pump-12 runs hot by design; a technician checked it on 2026-09-15.",
          "pump-13": "Pump-13 had a bearing failure in June."}
Q = {
    "alert": Choice("What should the monitoring system do with this reading?", {"ignore": "normal for this machine", "log": "note it, no action",
                                                                                "ticket": "open a maintenance ticket", "stop": "stop the machine now"}),
    "same_day": Noul("Does this reading need a technician today?"),
}


def over_limit(dev):
    return {"over_limit": {"when": "reading.bearing_temperature_c > values.limit_c",
                           "fact": f"{dev.capitalize()} is above its bearing temperature limit right now; "
                                   f"a technician must look at {dev} today and a maintenance ticket is required."}}


with client() as c:
    for dev, fact in MEMORY.items():
        c.delete(dev); c.remember(dev, fact)
    rows = []
    for dev in MEMORY:
        for temp in (78, 92):
            reading = {"device": dev, "reading": {"bearing_temperature_c": temp, "vibration": "normal", "hours_running": 6}}
            words = c.system_one(reading, Q, model=MODEL, subject=dev).answers
            r = c.system_one(reading, Q, model=MODEL, subject=dev, derive=over_limit(dev), values={"limit_c": LIMIT_C[dev]})
            a = r.answers
            rows.append([dev, temp, LIMIT_C[dev], "yes" if r.derived["over_limit"] else "no", f"{words['alert'].choice} -> {a['alert'].choice}",
                         f"{words['alert'].probabilities['ticket']:.2f} -> {a['alert'].probabilities['ticket']:.2f}",
                         f"{words['same_day'].noul:.2f} -> {a['same_day'].noul:.2f}"])
    table(rows, ["device", "temp C", "limit C", "over (code)", "action: memory only -> with the fact", "p(ticket)", "technician today"])
    for dev in MEMORY:
        c.delete(dev)
    print(f"\nmodel {r.model}; the limit is compared in code and reaches the engine as a sentence, the memory holds what a technician knows")
