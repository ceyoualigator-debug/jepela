"""Pydantic models as questions, and the answers back as an instance of the model.

    from typing import Annotated, Literal
    from pydantic import BaseModel, Field
    from jepela import JepelaClient, Levels, Options

    class Ticket(BaseModel):
        team: Annotated[Literal["billing", "support", "other"],
                        Options({"billing": "Charges, invoices and refunds", "support": "Product problems", "other": "None of these"})] = Field(
            description="Which team should handle this?")
        refund: bool = Field(description="Is the customer asking for money back?")
        urgency: Annotated[int, Levels("Can wait a week", "Should be handled today", "Blocking the customer now")] = Field(
            description="How urgent is this?")

    r = JepelaClient().system_one("We were charged twice and need the money back today.", Ticket)
    r.parsed.team, r.parsed.refund, r.parsed.urgency        # 'billing', True, 2

A Literal or an Enum field becomes a choice, a bool field a noul, and an int or float field marked with
Levels a score (an int gets the most likely level, a float the probability-weighted level). The field's
description is the question. Pydantic itself is not imported here; any Pydantic v2 model works.
"""
from __future__ import annotations

import enum
import types
import typing
from typing import Any, Literal


class Levels:
    """Marks an int or float field as a score question; the levels run from low to high (2 to 10)."""

    def __init__(self, *levels: Any):
        if len(levels) == 1 and isinstance(levels[0], (list, tuple)):
            levels = tuple(levels[0])
        if not 2 <= len(levels) <= 10:
            raise ValueError("a score needs 2 to 10 levels, low to high")
        self.levels = list(levels)

    def __repr__(self) -> str:
        return f"Levels({', '.join(map(repr, self.levels))})"


class Options:
    """Descriptions of a choice's options ({"billing": "Charges and refunds"}) or of a noul's
    answers ({"true": "...", "false": "..."}). Options not described are shown by their name."""

    def __init__(self, descriptions: dict | None = None, **more: Any):
        self.descriptions = {**(descriptions or {}), **more}

    def __repr__(self) -> str:
        return f"Options({self.descriptions!r})"


def _fields(model_cls) -> dict:
    fields = getattr(model_cls, "model_fields", None)
    if not isinstance(fields, dict) or not hasattr(model_cls, "model_validate"):
        raise TypeError(f"{model_cls!r} is not a Pydantic v2 model class")
    return fields


def _unwrap_optional(t):
    if typing.get_origin(t) in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(t) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return t


def _marker(field, kind):
    for m in getattr(field, "metadata", None) or []:
        if isinstance(m, kind):
            return m
    return None


def _described(field, name: str) -> dict:
    extra = field.json_schema_extra if isinstance(getattr(field, "json_schema_extra", None), dict) else {}
    marker = _marker(field, Options)
    out = dict(extra.get("options") or {})
    if marker:
        out.update(marker.descriptions)
    return out


def _choice_options(t) -> dict | None:
    """{option key: the Python value it stands for}, or None when the type is not a choice."""
    if typing.get_origin(t) is Literal:
        values = typing.get_args(t)
        if not all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in values):
            raise TypeError("Literal choices must be strings or whole numbers")
        return {str(v): v for v in values}
    if isinstance(t, type) and issubclass(t, enum.Enum):
        return {(m.value if isinstance(m.value, str) else m.name): m for m in t}
    return None


def _plan(model_cls) -> dict:
    """{field name: (kind, options or levels, the question as a dict)}."""
    plan = {}
    for name, field in _fields(model_cls).items():
        t = _unwrap_optional(field.annotation)
        instructions = field.description or field.title or name.replace("_", " ").strip() + "?"
        descriptions = _described(field, name)
        levels = _marker(field, Levels)
        options = _choice_options(t)
        if levels is not None:
            if t not in (int, float):
                raise TypeError(f"field {name!r}: Levels marks an int or float field, not {t!r}")
            plan[name] = ("score_int" if t is int else "score_float", levels.levels,
                          {"type": "score", "instructions": instructions, "criteria": list(levels.levels)})
        elif options is not None:
            unknown = set(descriptions) - set(options)
            if unknown:
                raise TypeError(f"field {name!r}: Options describe {sorted(unknown)}, which are not among the choices")
            plan[name] = ("choice", options, {"type": "choice", "instructions": instructions,
                                              "criteria": {k: descriptions.get(k, k) for k in options}})
        elif t is bool:
            q = {"type": "noul", "instructions": instructions}
            crit = {k: v for k, v in descriptions.items() if k in ("true", "false")}
            if crit:
                q["criteria"] = crit
            plan[name] = ("noul", None, q)
        else:
            raise TypeError(f"field {name!r} of type {t!r} cannot be a question: use a Literal or an Enum (a choice), "
                            "a bool (a noul), or an int or float with Levels(...) (a score)")
    if not plan:
        raise TypeError(f"{model_cls.__name__} has no fields to ask")
    return plan


def questions_from_model(model_cls) -> dict:
    """The model's fields as Jepela questions, keyed by field name."""
    return {name: q for name, (_, _, q) in _plan(model_cls).items()}


def to_model(model_cls, response, threshold: float = 0.5):
    """The response's answers as an instance of model_cls. A noul is True when its probability is at
    least `threshold`. The instance is validated by Pydantic, so the model's own validators run."""
    answers = response.answers if hasattr(response, "answers") else response
    values = {}
    for name, (kind, extra, _) in _plan(model_cls).items():
        a = answers.get(name)
        if a is None:
            raise KeyError(f"the response has no answer for {name!r}")
        get = (lambda k: a.get(k)) if isinstance(a, dict) else (lambda k: getattr(a, k))
        if kind == "choice":
            values[name] = extra[get("choice")]
        elif kind == "noul":
            values[name] = float(get("noul")) >= threshold
        elif kind == "score_int":
            probs = get("probabilities")
            values[name] = int(max(probs, key=probs.get))
        else:
            values[name] = float(get("score"))
    return model_cls.model_validate(values)
