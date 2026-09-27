"""Questions you send and answers you get back, as plain objects with attributes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ------------------------------------------------------------------ questions
@dataclass
class Choice:
    """Pick one option. `criteria` maps option names to descriptions. Up to 20 options are read in
    one round; more are answered in two rounds by the gateway (see usage.engine_answers)."""
    instructions: Any
    criteria: dict[str, Any]

    def to_dict(self) -> dict:
        return {"type": "choice", "instructions": self.instructions, "criteria": dict(self.criteria)}


@dataclass
class Score:
    """Rate on ordered levels, low to high (2 to 10). The answer's score is the probability-weighted level."""
    instructions: Any
    criteria: list[Any]

    def to_dict(self) -> dict:
        return {"type": "score", "instructions": self.instructions, "criteria": list(self.criteria)}


@dataclass
class Noul:
    """A yes/no statement; the answer is the probability of yes. `criteria` may say what true and false mean."""
    instructions: Any
    criteria: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        out = {"type": "noul", "instructions": self.instructions}
        if self.criteria:
            out["criteria"] = dict(self.criteria)
        return out


Question = Choice | Score | Noul


def questions_to_dict(questions: dict) -> dict:
    """Accepts question objects or already-built dictionaries."""
    return {qid: (q.to_dict() if hasattr(q, "to_dict") else dict(q)) for qid, q in questions.items()}


# ------------------------------------------------------------------ answers
@dataclass
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float | None = None
    type: str = "choice"
    rounds: int | None = None                 # 2 when the options were asked in groups
    orders: int | None = None                 # option orders averaged (robust)
    agreement: float | None = None            # share of those orders that picked `choice`
    calibration: dict | None = None           # the tenant temperature applied, if any
    raw_probabilities: dict | None = None     # before that temperature
    window: int | None = None                 # the window that decided, when read in windows
    method: str | None = None                 # "engine" (read by the engine) or "match" (matched by vectors)
    similarity: dict | None = None            # matched answers: {"best", "second"} cosine similarities


@dataclass
class ScoreAnswer:
    score: float
    probabilities: dict[str, float]
    legend: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    type: str = "score"
    calibration: dict | None = None
    raw_probabilities: dict | None = None
    raw_score: float | None = None
    window: int | None = None
    method: str | None = None                 # "engine"

    @property
    def level(self) -> int:
        """The most likely level."""
        return int(max(self.probabilities, key=self.probabilities.get))


@dataclass
class NoulAnswer:
    noul: float
    confidence: float | None = None
    type: str = "noul"
    calibration: dict | None = None
    raw_noul: float | None = None
    window: int | None = None
    method: str | None = None                 # "engine"

    @property
    def yes(self) -> bool:
        return self.noul >= 0.5


Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer


def answer_from(d: dict) -> Answer:
    kind = d.get("type")
    if kind == "choice":
        return ChoiceAnswer(d.get("choice"), dict(d.get("probabilities") or {}), d.get("confidence"), rounds=d.get("rounds"),
                            orders=d.get("orders"), agreement=d.get("agreement"), calibration=d.get("calibration"),
                            raw_probabilities=d.get("raw_probabilities"), window=d.get("window"), method=d.get("method"),
                            similarity=d.get("similarity"))
    if kind == "score":
        return ScoreAnswer(float(d.get("score", 0.0)), dict(d.get("probabilities") or {}), dict(d.get("legend") or {}), d.get("confidence"),
                           calibration=d.get("calibration"), raw_probabilities=d.get("raw_probabilities"), raw_score=d.get("raw_score"),
                           window=d.get("window"), method=d.get("method"))
    if kind == "noul":
        return NoulAnswer(float(d.get("noul", 0.0)), d.get("confidence"), calibration=d.get("calibration"), raw_noul=d.get("raw_noul"),
                          window=d.get("window"), method=d.get("method"))
    raise ValueError(f"unknown answer type {kind!r}")


@dataclass
class Usage:
    input_characters: int = 0
    questions: int = 0
    answers: int = 0
    memory_lines_used: int = 0
    engine_ms: float = 0.0
    gateway_ms: float = 0.0
    cost: float = 0.0
    currency: str = ""
    balance: float | None = None
    input_tokens: int | None = None            # only when the engine counted them
    answers_billed: int = 0
    engine_answers: int = 0
    memory_lines_seen: int = 0
    state_tokens: int | None = None            # the state, in the engine's tokens
    state_tokens_read: int | None = None       # how much of it the engine read
    state_truncated: bool = False
    cached: bool = False
    raw: dict = field(default_factory=dict)
    match_questions: int | None = None         # choice questions answered by matching, when some were

    @classmethod
    def from_dict(cls, d: dict | None) -> "Usage":
        d = d or {}
        return cls(int(d.get("input_characters", 0)), int(d.get("questions", 0)), int(d.get("answers", 0)), int(d.get("memory_lines_used", 0)),
                   float(d.get("engine_ms", 0.0)), float(d.get("gateway_ms", 0.0)), float(d.get("cost", 0.0)), str(d.get("currency", "")),
                   d.get("balance"), d.get("input_tokens"), int(d.get("answers_billed", d.get("answers", 0))), int(d.get("engine_answers", 0)),
                   int(d.get("memory_lines_seen", 0)), d.get("state_tokens"), d.get("state_tokens_read"), bool(d.get("state_truncated", False)),
                   bool(d.get("cached", False)), dict(d), match_questions=d.get("match_questions"))


@dataclass
class JepelaWarning:
    """Advice about a known trap; the answer is returned either way."""
    code: str
    message: str
    question: str | None = None


@dataclass
class MemoryResult:
    """What the memory did for one decision. The subject is whatever the decision was about."""
    subject: str
    lines_used: int
    hits: list[dict]
    recall_ms: float | None = None
    without_memory: dict[str, Answer] | None = None
    changes: dict | None = None
    lines_seen: int = 0                       # memory lines the engine actually read
    lines_dropped: int = 0                    # fired rules and recalled lines left out of the engine's 64 context lines
    rules_fired: list[dict] = field(default_factory=list)
    rules_broken: list[dict] = field(default_factory=list)
    placebo: dict | None = None               # content_effect, memory_effect, presence_only
    pinned: list[str] = field(default_factory=list)            # ids of the pinned rules sent
    excluded: dict[str, dict[str, str]] = field(default_factory=dict)   # per question: {option: why} removed by exclusion rules
    exclusions_skipped: list[dict] = field(default_factory=list)        # exclusions that would have removed every option
    explain: list[dict] | None = None         # with memory={"explain": True}: [{"line", "kind", "effect"}]

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryResult":
        without = d.get("without_memory")
        return cls(d.get("subject", d.get("customer")), int(d.get("lines_used", 0)), list(d.get("hits") or []), d.get("recall_ms"),
                   {k: answer_from(v) for k, v in without.items()} if isinstance(without, dict) else None, d.get("changes"),
                   int(d.get("lines_seen", d.get("lines_used", 0))), int(d.get("lines_dropped", 0)), list(d.get("rules_fired") or []),
                   list(d.get("rules_broken") or []), d.get("placebo"), list(d.get("pinned") or []), dict(d.get("excluded") or {}),
                   list(d.get("exclusions_skipped") or []), d.get("explain"))


@dataclass
class Response:
    model: str
    answers: dict[str, Answer]
    usage: Usage
    engine: dict = field(default_factory=dict)
    memory: MemoryResult | None = None
    decision_id: str | None = None
    warnings: list[JepelaWarning] = field(default_factory=list)
    reading: dict = field(default_factory=dict)
    derived: dict = field(default_factory=dict)
    windows: dict | None = None
    raw: dict = field(default_factory=dict)
    parsed: Any = None                        # an instance of the Pydantic model, when one was given as the questions

    @classmethod
    def from_dict(cls, d: dict) -> "Response":
        return cls(d.get("model"), {k: answer_from(v) for k, v in (d.get("answers") or {}).items()}, Usage.from_dict(d.get("usage")),
                   dict(d.get("engine") or {}), MemoryResult.from_dict(d["memory"]) if isinstance(d.get("memory"), dict) else None,
                   d.get("decision_id"), [JepelaWarning(w.get("code"), w.get("message"), w.get("question")) for w in d.get("warnings") or []],
                   dict(d.get("reading") or {}), dict(d.get("derived") or {}), d.get("windows"), d)

    def to_model(self, model_cls, threshold: float = 0.5):
        """The answers as an instance of a Pydantic model whose fields were turned into questions."""
        from .pydantic_support import to_model
        return to_model(model_cls, self, threshold)


@dataclass
class MemoryInfo:
    subject: str
    lines_stored: int | None
    raw: dict = field(default_factory=dict)
    rules: int = 0
    lines: list[str] | None = None            # only when asked for with lines=True
    rule_list: list[dict] | None = None


@dataclass
class Models:
    models: list[dict]
    default: str
    aliases: dict

    def names(self) -> list[str]:
        return [m["name"] for m in self.models]

    def available(self) -> list[str]:
        return [m["name"] for m in self.models if m.get("available")]
