#!/usr/bin/env python3
"""Jepela as an MCP server: decisions with memory as tools for Claude and other MCP clients.

Speaks the Model Context Protocol (JSON-RPC 2.0, one message per line) on stdin and stdout.
Standard library only, so it needs no virtual environment: any Python 3.10 or newer runs it.

Environment:
    JEPELA_API_KEY    the API key (tool calls explain how to get one when it is missing)
    JEPELA_BASE_URL   the gateway; by default the API of the key's region (jj_live_eu_... goes to eu.api.jepela.com)
    JEPELA_MODEL      the model decide uses when a call names none, optional

Tools: decide, remember, forget, delete, memory, feedback, quality.
"""
from __future__ import annotations

import json
import re
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "jepela", "title": "Jepela: decisions with memory", "version": "0.1.0"}
INSTRUCTIONS = ("Jepela answers typed questions about a situation: a choice among named options, a score on ordered levels, "
                "or a yes/no probability. It does not write text. Give a subject (a customer, user, player or device id) to "
                "use what Jepela remembers about it; store facts with remember, one per line, saying what is true or what to do "
                "rather than what to avoid. One thing per question; add an 'other' option to choices. Report feedback with the "
                "decision_id when the right answer becomes known, and read quality to see how accurate Jepela is on your data.")

SUBJECT = {"type": "string", "description": "Whose memory: a customer, user, player or device id; letters, digits, _ and -, up to 36."}
TOOLS = [
    {"name": "decide", "title": "Decide",
     "description": "Answer typed questions about a situation with the Jepela engine and return a probability for every option. "
                    "Question types: choice {type:'choice', instructions, criteria:{option: description}}; score {type:'score', "
                    "instructions, criteria:[lowest, ..., highest]} with 2 to 10 levels described as situations; noul {type:'noul', "
                    "instructions} for a yes/no statement. With a subject, Jepela reads what it remembers about that subject first.",
     "inputSchema": {"type": "object", "properties": {
         "state": {"type": ["string", "object", "array"], "description": "The situation: plain text, or a JSON object or array."},
         "questions": {"type": "object", "minProperties": 1, "description": "Question id mapped to a question.",
                       "additionalProperties": {"type": "object", "required": ["type", "instructions"], "properties": {
                           "type": {"type": "string", "enum": ["choice", "score", "noul"]},
                           "instructions": {"type": "string"},
                           "criteria": {"type": ["object", "array"]}}}},
         "subject": SUBJECT,
         "model": {"type": "string", "description": "jepela (default), jepela-english, jepela-multilingual or jepela-typed-decisions."},
         "compare": {"type": "boolean", "description": "Also answer without the memory, to see what it changed."},
         "robust": {"type": "boolean", "description": "Ask each choice of up to 20 options in three option orders (two for a two-option choice) and average them; billed per order."},
         "values": {"type": "object", "description": "Numbers and strings that derive expressions and memory rules may use."},
         "derive": {"type": "object", "description": "Facts computed in code, for example {\"over\": \"reading.t > 75\"}."}},
         "required": ["state", "questions"]},
     "annotations": {"title": "Decide", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}},
    {"name": "remember", "title": "Remember",
     "description": "Store facts about a subject, one per line; later decisions about it read the relevant lines first. Say what "
                    "is true or what to do: a line that names a forbidden option can pull the answer toward it, and Jepela warns about it. "
                    "When an option must never be chosen, leave it out of the question instead.",
     "inputSchema": {"type": "object", "properties": {"subject": SUBJECT, "text": {"type": "string", "description": "One fact per line."}},
                     "required": ["subject", "text"]},
     "annotations": {"title": "Remember", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}},
    {"name": "forget", "title": "Forget",
     "description": "Remove every memory line and rule about a concept from a subject's memory, and check that recall no longer finds it.",
     "inputSchema": {"type": "object", "properties": {"subject": SUBJECT, "concept": {"type": "string", "description": "What to forget, in a few words."}},
                     "required": ["subject", "concept"]},
     "annotations": {"title": "Forget", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True}},
    {"name": "delete", "title": "Delete a subject's memory",
     "description": "Delete everything Jepela remembers about a subject: every line and every rule. It cannot be undone.",
     "inputSchema": {"type": "object", "properties": {"subject": SUBJECT}, "required": ["subject"]},
     "annotations": {"title": "Delete a subject's memory", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True}},
    {"name": "memory", "title": "Read a subject's memory",
     "description": "What Jepela remembers about a subject, word for word: every stored line and every rule.",
     "inputSchema": {"type": "object", "properties": {"subject": SUBJECT}, "required": ["subject"]},
     "annotations": {"title": "Read a subject's memory", "readOnlyHint": True, "openWorldHint": True}},
    {"name": "feedback", "title": "Feedback",
     "description": "Give the right answer for one question of an earlier decision: an option name, a level number, or true/false. "
                    "Labels drive the quality report and the per-question calibration.",
     "inputSchema": {"type": "object", "properties": {
         "decision_id": {"type": "string", "description": "The decision_id decide returned."},
         "question": {"type": "string", "description": "The question id."},
         "correct": {"type": ["string", "integer", "boolean"], "description": "The right answer."}},
         "required": ["decision_id", "question", "correct"]},
     "annotations": {"title": "Feedback", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}},
    {"name": "quality", "title": "Quality report",
     "description": "Accuracy, calibration error, and the share of decisions that can be automated at a target accuracy, per "
                    "question, from the feedback given so far.",
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string", "description": "Only this question id."},
         "days": {"type": "number", "description": "Only labels from the last N days (default 30)."}}},
     "annotations": {"title": "Quality report", "readOnlyHint": True, "openWorldHint": True}},
]
TOOL_NAMES = {t["name"] for t in TOOLS}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Jepela:
    def __init__(self, key: str | None, base_url: str, model: str | None = None, timeout: float = 120.0):
        self.key, self.base_url, self.model, self.timeout = key, base_url.rstrip("/"), model, timeout

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        if not self.key:
            raise ApiError(None, "no API key: set JEPELA_API_KEY in the environment Claude starts this server from "
                                 "(the gateway owner creates keys with: python3 decision_api_server.py keys add --tenant NAME --credit 1)")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "User-Agent": "jepela-mcp/0.1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            try:
                err = json.loads(exc.read()).get("error") or {}
            except (ValueError, AttributeError):
                err = {}
            kind = err.get("type") if isinstance(err, dict) else None
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise ApiError(exc.code, f"{kind or 'error'}: {message or exc.reason}")
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError(None, f"cannot reach Jepela at {self.base_url}: {exc}")


# ------------------------------------------------------------------ tool results as text
def pct(p) -> str:
    return f"{round(100 * float(p))}%"


def describe_answer(qid: str, a: dict) -> str:
    kind = a.get("type")
    if kind == "choice":
        probs = sorted((a.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
        rest = ", ".join(f"{k} {pct(v)}" for k, v in probs[1:4])
        line = f"{qid}: {a.get('choice')} {pct(probs[0][1]) if probs else ''}" + (f" ({rest})" if rest else "")
        if a.get("orders"):
            line += f"; {a['orders']} option orders, agreement {pct(a.get('agreement', 0))}"
        return line
    if kind == "score":
        probs = a.get("probabilities") or {}
        top = max(probs, key=probs.get) if probs else None
        legend = (a.get("legend") or {}).get(top, "")
        return f"{qid}: {float(a.get('score', 0)):.2f} on 0-{len(probs) - 1}" + (f"; most likely {top}: {legend}" if top is not None else "")
    if kind == "noul":
        p = float(a.get("noul", 0))
        return f"{qid}: {'yes' if p >= 0.5 else 'no'}, probability of yes {pct(p)}"
    return f"{qid}: {json.dumps(a)}"


def describe_decision(out: dict) -> str:
    lines = [describe_answer(q, a) for q, a in (out.get("answers") or {}).items()]
    mem = out.get("memory")
    if mem:
        lines.append(f"memory of {mem.get('subject')}: {mem.get('lines_seen', 0)} of {mem.get('lines_used', 0)} recalled lines read")
        for rule in mem.get("rules_fired") or []:
            lines.append(f"rule fired: {rule.get('text')}")
        without = mem.get("without_memory")
        if without:
            changed = [q for q, a in without.items() if a.get("choice") != (out["answers"].get(q) or {}).get("choice")
                       or abs(float(a.get("noul", 0)) - float((out["answers"].get(q) or {}).get("noul", 0))) >= 0.1]
            lines.append("without the memory: " + "; ".join(describe_answer(q, a) for q, a in without.items())
                         + (f" (changed: {', '.join(changed)})" if changed else " (no change)"))
    for w in out.get("warnings") or []:
        lines.append(f"warning {w.get('code')}: {w.get('message')}")
    usage = out.get("usage") or {}
    if usage.get("state_truncated"):
        lines.append(f"the engine read {usage.get('state_tokens_read')} of {usage.get('state_tokens')} state tokens")
    lines.append(f"decision_id {out.get('decision_id')}; model {out.get('model')}; cost {usage.get('cost', 0):.5f} {usage.get('currency', '')}".rstrip())
    return "\n".join(lines)


def run_tool(jepela: Jepela, name: str, args: dict) -> tuple:
    """(text, structured result) or ApiError / ValueError."""
    def need(*keys):
        missing = [k for k in keys if args.get(k) in (None, "")]
        if missing:
            raise ValueError(f"missing {', '.join(missing)}")

    if name == "decide":
        need("state", "questions")
        if not isinstance(args["questions"], dict) or not args["questions"]:
            raise ValueError("questions is an object of question id to question")
        body = {"state": args["state"], "questions": args["questions"]}
        if args.get("model") or jepela.model:
            body["model"] = args.get("model") or jepela.model
        for k in ("subject", "robust", "values", "derive"):
            if args.get(k) not in (None, ""):
                body[k] = args[k]
        if args.get("compare") and args.get("subject"):
            body["memory"] = {"compare": True}
        out = jepela.call("POST", "/v1/systemone", body)
        return describe_decision(out), out
    if name == "remember":
        need("subject", "text")
        out = jepela.call("POST", "/v1/memory/remember", {"subject": args["subject"], "text": args["text"]})
        text = f"stored {out.get('lines_added', 0)} line(s) for {out.get('subject')}; {out.get('lines_stored')} stored in all"
        for w in out.get("warnings") or []:
            text += f"\nwarning {w.get('code')}: {w.get('message')}"
        return text, out
    if name == "forget":
        need("subject", "concept")
        out = jepela.call("POST", "/v1/memory/forget", {"subject": args["subject"], "concept": args["concept"]})
        return (f"removed {out.get('lines_removed', 0)} line(s) and {out.get('rules_removed', 0)} rule(s) about {args['concept']!r}; "
                f"recall checked: {'nothing left' if out.get('verified_forgotten') else 'something may remain'}"), out
    if name == "delete":
        need("subject")
        out = jepela.call("POST", "/v1/memory/delete", {"subject": args["subject"]})
        return f"deleted the memory of {out.get('subject')}: {out.get('lines_removed', 0)} line(s)", out
    if name == "memory":
        need("subject")
        out = jepela.call("GET", "/v1/memory?subject=" + urllib.parse.quote(str(args["subject"])) + "&lines=true")
        lines = out.get("lines") or []
        rules = out.get("rule_list") or []
        text = f"{out.get('subject')}: {len(lines)} line(s), {len(rules)} rule(s)"
        text += "".join(f"\n- {l}" for l in lines)
        text += "".join(f"\nrule when {r.get('when')}: {r.get('text')}" for r in rules)
        return text, out
    if name == "feedback":
        need("decision_id", "question")
        if "correct" not in args:
            raise ValueError("missing correct")
        out = jepela.call("POST", "/v1/feedback", {"decision_id": args["decision_id"], "question": args["question"], "correct": args["correct"]})
        text = f"label stored for {args['question']}: the answer was {'right' if out.get('correct') else 'wrong'}; {out.get('labels_for_this_question')} label(s) for this question"
        return text, out
    if name == "quality":
        query = {k: args[k] for k in ("question", "days") if args.get(k) not in (None, "")}
        out = jepela.call("GET", "/v1/quality" + ("?" + urllib.parse.urlencode(query) if query else ""))
        rows = out.get("questions") or []
        if not rows:
            return "no labels yet: give feedback with the decision_id when the right answer is known", out
        def line(q):
            auto = q.get("automate_at") or {}
            best = auto.get("0.9") or auto.get(0.9) or {}
            return (f"{q.get('question')} ({q.get('model')}): {q.get('labels')} labels, accuracy {pct(q.get('accuracy', 0))}, "
                    f"calibration error {float(q.get('calibration_error', 0)):.3f}"
                    + (f", {pct(best.get('share', 0))} of decisions reach 90% accuracy" if best else ""))
        return "\n".join(line(q) for q in rows), out
    raise KeyError(name)


# ------------------------------------------------------------------ JSON-RPC
def error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(jepela: Jepela, msg) -> dict | None:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    method, msg_id, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:                                   # a notification: never answered
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in TOOL_NAMES:
            return error(msg_id, -32602, f"Unknown tool: {name}")
        if not isinstance(args, dict):
            return error(msg_id, -32602, "arguments must be an object")
        try:
            text, structured = run_tool(jepela, name, args)
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": text}], "structuredContent": structured,
                                                              "isError": False}}
        except (ApiError, ValueError) as exc:
            status = f" ({exc.status})" if getattr(exc, "status", None) else ""
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": f"Jepela{status}: {exc}"}], "isError": True}}
    return error(msg_id, -32601, f"Method not found: {method}")


def answer(jepela: Jepela, msg):
    """One message, or a batch of them (MCP 2025-03-26 allows a JSON array); notifications get no reply."""
    if isinstance(msg, list):
        if not msg:
            return error(None, -32600, "Invalid Request")
        replies = [r for r in (answer(jepela, m) for m in msg) if r is not None]
        return replies or None
    try:
        return handle(jepela, msg)
    except Exception as exc:                                # never a traceback on stdout: it would break the protocol
        print(f"jepela-mcp: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return error(msg.get("id") if isinstance(msg, dict) else None, -32603, "Internal error")


def main() -> int:
    key = os.environ.get("JEPELA_API_KEY") or None
    region = re.match(r"^jj_live_([a-z]{2})_[0-9a-f]{32}$", key or "")
    jepela = Jepela(key, os.environ.get("JEPELA_BASE_URL") or (f"https://{region.group(1)}.api.jepela.com" if region else "https://api.jepela.com"),
                os.environ.get("JEPELA_MODEL") or None)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            reply = error(None, -32700, "Parse error")
        else:
            reply = answer(jepela, msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
