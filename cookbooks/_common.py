"""Shared bits for the cookbooks: the client, and a small table printer. Standard library only."""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sdk", "python"))

from jepela import JepelaClient  # noqa: E402

MODEL = os.environ.get("JEPELA_MODEL", "jepela-english")


def client() -> JepelaClient:
    if not os.environ.get("JEPELA_API_KEY"):
        sys.exit("set JEPELA_API_KEY (and JEPELA_BASE_URL if the gateway is not on 127.0.0.1:8797)")
    return JepelaClient()


def table(rows: list[list], headers: list[str]) -> None:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    print(line); print("-" * len(line))
    for r in rows:
        print("  ".join(str(x).ljust(w) for x, w in zip(r, widths)))


class Timer:
    def __init__(self):
        self.t0 = time.perf_counter()

    def ms(self) -> float:
        return round(1000 * (time.perf_counter() - self.t0), 1)
