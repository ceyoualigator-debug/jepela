"""The HTTP client. Standard library only.

One kept-open connection per thread (the gateway speaks HTTP/1.1). Retries 429, 502 and 503 with
backoff, and connection failures that happened before the request was sent. A request that was sent
and then timed out is not sent again unless it is a GET, so a decision is never billed twice.
"""
from __future__ import annotations

import asyncio
import functools
import http.client
import json
import os
import random
import re
import select
import ssl
import threading
import time
import urllib.parse
from typing import Any, Iterable

from .errors import ConnectionFailed, JepelaError, error_for
from .types import MemoryInfo, Models, Response, questions_to_dict

DEFAULT_BASE_URL = "https://api.jepela.com"
_REGION_KEY = re.compile(r"^jj_live_([a-z]{2})_[0-9a-f]{32}$")


def region_of(api_key: str | None) -> str | None:
    """The region a Jepela key belongs to (jj_live_eu_... is eu); None for keys made before regions (they are us)."""
    m = _REGION_KEY.match(api_key or "")
    return m.group(1) if m else None


def base_url_for(api_key: str | None = None, region: str | None = None) -> str:
    """The API address of a key's region, or of the region named; https://api.jepela.com when neither says one."""
    region = region or region_of(api_key)
    return f"https://{region}.api.jepela.com" if region else DEFAULT_BASE_URL
ENV_API_KEY, ENV_BASE_URL = "JEPELA_API_KEY", "JEPELA_BASE_URL"
RETRY_STATUSES = (429, 502, 503)
USER_AGENT = "jepela-sdk/0.2.0"
IDLE_SECONDS = 50.0              # the gateway closes a connection idle for 60 s; the client lets go first


class _Connections:
    """A kept-open HTTP connection per thread, dropped when the gateway has closed it."""

    def __init__(self, base_url: str, timeout: float):
        u = urllib.parse.urlsplit(base_url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise JepelaError(f"base_url must be http:// or https://, got {base_url!r}")
        self.https, self.host, self.port = u.scheme == "https", u.hostname, u.port
        self.prefix, self.timeout = u.path.rstrip("/"), timeout
        self.local, self.lock, self.all = threading.local(), threading.Lock(), []

    def get(self) -> http.client.HTTPConnection:
        conn = getattr(self.local, "conn", None)
        if conn is not None and conn.sock is not None:
            try:
                readable = select.select([conn.sock], [], [], 0)[0]
            except (OSError, ValueError):
                readable = True
            idle = time.monotonic() - getattr(self.local, "used", 0.0)
            if readable or idle > IDLE_SECONDS:             # closed by the server, or about to be
                self.drop()
                conn = None
        if conn is None:
            if self.https:
                conn = http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout, context=ssl.create_default_context())
            else:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
            self.local.conn = conn
            with self.lock:
                self.all.append(conn)
        return conn

    def drop(self) -> None:
        conn = getattr(self.local, "conn", None)
        self.local.conn = None
        if conn is not None:
            conn.close()
            with self.lock:
                if conn in self.all:
                    self.all.remove(conn)

    def close_all(self) -> None:
        with self.lock:
            conns, self.all = self.all, []
        for conn in conns:
            conn.close()
        self.local = threading.local()


class _NotSent(Exception):
    """The connection failed before the request left: always safe to try again."""


class _SentButFailed(Exception):
    """The request may have reached the gateway: only a GET is tried again."""


def _exchange(conns: _Connections, method: str, path: str, data: bytes | None, headers: dict) -> tuple:
    conn = conns.get()
    if conn.sock is None:
        try:
            conn.connect()
        except OSError as exc:
            conns.drop()
            raise _NotSent(exc)
    try:
        conn.request(method, conns.prefix + path, body=data, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
    except (OSError, http.client.HTTPException) as exc:
        conns.drop()
        raise _SentButFailed(exc)
    if resp.version == 10 or (resp.getheader("Connection") or "").lower() == "close":
        conns.drop()
    conns.local.used = time.monotonic()
    return resp.status, resp, body


def _error(status: int, resp, raw: bytes) -> JepelaError:
    try:
        err = json.loads(raw).get("error") or {}
    except (ValueError, AttributeError):
        err = {}
    message = err.get("message") if isinstance(err, dict) else str(err)
    retry_after = resp.getheader("Retry-After")
    try:
        retry_after = float(retry_after) if retry_after else None
    except ValueError:
        retry_after = None
    return error_for(status, message or raw[:200].decode(errors="replace"), err.get("type") if isinstance(err, dict) else None, retry_after)


def _call(conns: _Connections, method: str, path: str, *, api_key: str | None, body: Any = None, data: bytes | None = None,
          content_type: str = "application/json", raw: bool = False, max_retries: int = 2, backoff_seconds: float = 0.5,
          base_url: str = "") -> Any:
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if data is not None:
        headers["Content-Type"] = content_type
    attempt = 0
    while True:
        try:
            status, resp, payload = _exchange(conns, method, path, data, headers)
        except _NotSent as exc:
            if attempt < max_retries:
                attempt += 1
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
                continue
            raise ConnectionFailed(f"cannot reach {base_url}: {exc}")
        except _SentButFailed as exc:
            if method == "GET" and attempt < max_retries:
                attempt += 1
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
                continue
            raise ConnectionFailed(f"no answer from {base_url} to {method} {path}: {exc}"
                                   + ("" if method == "GET" else "; not sent again, so it cannot be billed twice"))
        if 200 <= status < 300:
            if raw or "ndjson" in (resp.getheader("Content-Type") or ""):
                return payload
            return json.loads(payload)
        error = _error(status, resp, payload)
        if status in RETRY_STATUSES and attempt < max_retries:
            attempt += 1
            time.sleep(min(error.retry_after or backoff_seconds * (2 ** (attempt - 1)) * (1 + random.random() / 4), 30.0))
            continue
        raise error


def signup(email: str, invite_code: str | None = None, base_url: str | None = None, timeout: float = 30.0,
           region: str | None = None) -> dict:
    """Ask for a new key with self-serve sign-up. Needs no key. The key is shown once, and belongs to `region`
    (see GET /v1/regions); its memories and usage stay there."""
    base = (base_url or os.environ.get(ENV_BASE_URL) or base_url_for(region=region)).rstrip("/")
    body = {"email": email}
    if region:
        body["region"] = region
    if invite_code:
        body["invite_code"] = invite_code
    conns = _Connections(base, timeout)
    try:
        return _call(conns, "POST", "/v1/signup", api_key=None, body=body, max_retries=0, base_url=base)
    finally:
        conns.close_all()


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


class JepelaClient:
    """Synchronous client. Safe to share between threads.

    Args:
        api_key: the key, or the JEPELA_API_KEY environment variable.
        base_url: the gateway, or JEPELA_BASE_URL, or the API of the key's region (jj_live_eu_... goes to
            https://eu.api.jepela.com; keys made before regions to https://api.jepela.com).
        timeout: seconds per HTTP call.
        max_retries: retries on 429, 502 and 503 (a 429's Retry-After is honoured) and on connections that
            failed before the request was sent.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 120.0, max_retries: int = 2,
                 backoff_seconds: float = 0.5):
        self.api_key = api_key or os.environ.get(ENV_API_KEY)
        if not self.api_key:
            raise JepelaError(f"no API key: pass api_key or set {ENV_API_KEY}")
        self.base_url = (base_url or os.environ.get(ENV_BASE_URL) or base_url_for(self.api_key)).rstrip("/")
        self.timeout, self.max_retries, self.backoff_seconds = timeout, max_retries, backoff_seconds
        self._conns = _Connections(self.base_url, timeout)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self) -> None:
        self._conns.close_all()

    # -- transport
    def request(self, method: str, path: str, body: dict | None = None, *, data: bytes | None = None,
                content_type: str = "application/json", raw: bool = False) -> Any:
        """Any gateway route. Returns the parsed JSON, or bytes for JSONL results or when raw=True."""
        return _call(self._conns, method, path, api_key=self.api_key, body=body, data=data, content_type=content_type, raw=raw,
                     max_retries=self.max_retries, backoff_seconds=self.backoff_seconds, base_url=self.base_url)

    # -- decisions
    def system_one(self, state: Any, questions: Any, model: str | None = None, subject: str | None = None,
                   memory: dict | None = None, *, robust: bool | dict | None = None,
                   windows: bool | dict | None = None, derive: dict | None = None, values: dict | None = None,
                   cache: bool | None = None, method: str | None = None, customer: str | None = None) -> Response:
        """One request, every question answered against the same state.

        questions: a dict of Choice / Score / Noul (or plain dicts), or a Pydantic model class whose fields
            become the questions; then `response.parsed` is an instance of that class.
        subject: whatever the decision is about (a customer, a user, a player, a device); its memory is used.
            `customer` is the older name.
        memory: {"use", "top_k", "min_share", "compare", "placebo", "names", "question_words", "focus", "explain"}.
            names (default True): the subject's name and aliases are searched with the state; question_words (default
            True): the questions' instructions are searched too; focus (default False): keep only lines that share a
            word with the state beyond those names; explain (default False): per memory line (at most 8), how far the
            answer moves when that line alone is left out.
        robust: True (3 orders), or {"orders": 1-5}: every choice of up to 20 options is asked with its options in
            several orders and averaged (a two-option choice has 2 orders); billed per order.
        windows: True, or {"combine": {"question_id": "max" | "mean" | "min"}}: a state longer than the engine reads
            is read in up to 16 overlapping windows, billed per window.
        derive: {"name": "expression"} or {"name": {"when": ..., "fact": ..., "else": ...}}, computed in code,
            never by the model; the facts are shown to the model as computed by the system.
        values: numbers and strings the derive expressions and memory rules may use.
        cache: identical requests without memory return the stored answers without new engine work.
        method: how choice questions are answered. "auto" (the gateway's default) matches choices of more than 20
            options by vectors and asks the engine the rest; "engine" reads every option; "match" matches every choice.
            Each answer's `method` says which answered it.
        """
        model_cls = None
        if isinstance(questions, type):
            from .pydantic_support import questions_from_model
            model_cls, questions = questions, questions_from_model(questions)
        body: dict = {"state": state, "questions": questions_to_dict(questions)}
        subject = subject if subject is not None else customer
        body.update(_drop_none({"model": model or None, "subject": subject, "memory": dict(memory) if memory is not None else None,
                                "robust": robust, "windows": windows, "derive": derive, "values": values, "cache": cache,
                                "method": method}))
        response = Response.from_dict(self.request("POST", "/v1/systemone", body))
        if model_cls is not None:
            response.parsed = response.to_model(model_cls)
        return response

    # -- memory
    def remember(self, subject: str, text: str) -> dict:
        """Store what is known about a subject. Returns lines_added and warnings about lines the engine reads badly."""
        return self.request("POST", "/v1/memory/remember", {"subject": subject, "text": text})

    def forget(self, subject: str, concept: str) -> dict:
        """Remove every memory line and rule about a concept, and check it is gone."""
        return self.request("POST", "/v1/memory/forget", {"subject": subject, "concept": concept})

    def delete(self, subject: str) -> dict:
        """Remove the subject's whole memory and rules."""
        return self.request("POST", "/v1/memory/delete", {"subject": subject})

    def memory(self, subject: str, lines: bool = False) -> MemoryInfo:
        """How much is stored about a subject; with lines=True also every stored line and rule, word for word."""
        d = self.request("GET", "/v1/memory?subject=" + urllib.parse.quote(subject) + ("&lines=true" if lines else ""))
        return MemoryInfo(d.get("subject", d.get("customer")), d.get("lines_stored"), d, int(d.get("rules") or 0),
                          d.get("lines"), d.get("rule_list"))

    def rules_add(self, subject: str, when: str, text: str, *, expires: str | None = None, ttl_seconds: float | None = None) -> dict:
        """A memory line that is used only while `when` is true, checked in code against `values`.
        Example: rules_add("mia", "session_result <= -30", "Mia stops playing after losing 30.")"""
        return self.request("POST", "/v1/memory/rules", _drop_none({"subject": subject, "when": when, "text": text, "expires": expires,
                                                                     "ttl_seconds": ttl_seconds}))

    def pin(self, subject: str, text: str, *, expires: str | None = None, ttl_seconds: float | None = None) -> dict:
        """A line sent first at every decision about the subject, whatever the state says.
        Example: pin("acme", "ACME pays for premium support.")"""
        return self.request("POST", "/v1/memory/rules", _drop_none({"subject": subject, "text": text, "pin": True, "expires": expires,
                                                                     "ttl_seconds": ttl_seconds}))

    def exclude(self, subject: str, options: list[str], text: str, *, question: str | None = None, when: str | None = None,
                expires: str | None = None, ttl_seconds: float | None = None) -> dict:
        """Options removed from choice questions in code for this subject (while `when` holds); the text says why and is
        never sent to the engine. Example: exclude("player-9", ["gold_coins"], "Coin bug.", question="reward")"""
        return self.request("POST", "/v1/memory/rules", _drop_none({"subject": subject, "exclude": list(options), "text": text,
                                                                     "question": question, "when": when, "expires": expires,
                                                                     "ttl_seconds": ttl_seconds}))

    def aliases(self, subject: str, names: list[str]) -> dict:
        """Other names the subject goes by; recall searches them with the state. An empty list clears them."""
        return self.request("POST", "/v1/memory/aliases", {"subject": subject, "aliases": list(names)})

    def rules(self, subject: str) -> list[dict]:
        return self.request("GET", "/v1/memory/rules?subject=" + urllib.parse.quote(subject)).get("rules", [])

    def rules_delete(self, subject: str, rule_id: str) -> dict:
        return self.request("POST", "/v1/memory/rules/delete", {"subject": subject, "rule_id": rule_id})

    # -- labels, quality, calibration, golden sets
    def feedback(self, decision_id: str, question: str, correct: Any) -> dict:
        """The right answer for one question of an earlier decision: an option name, a level, or true/false."""
        return self.request("POST", "/v1/feedback", {"decision_id": decision_id, "question": question, "correct": correct})

    def quality(self, question: str | None = None, *, days: float | None = None, model: str | None = None,
                source: str | None = None) -> dict:
        """Accuracy, calibration error and the automation coverage at a target accuracy, from your labels."""
        query = urllib.parse.urlencode(_drop_none({"question": question, "days": days, "model": model, "source": source}))
        return self.request("GET", "/v1/quality" + ("?" + query if query else ""))

    def calibration_fit(self, *, model: str | None = None, question: str | None = None, source: str | None = None,
                        min_labels: int | None = None) -> dict:
        """Fit a temperature per question from your labels; kept only if it helps on held-out labels."""
        return self.request("POST", "/v1/calibration/fit", _drop_none({"model": model, "question": question, "source": source,
                                                                        "min_labels": min_labels}))

    def calibration(self) -> list[dict]:
        return self.request("GET", "/v1/calibration").get("temperatures", [])

    def golden_add(self, cases: Iterable[dict]) -> dict:
        """Cases with known answers: {"id", "state", "questions", "expected", optional subject, values, derive, memory,
        robust, windows}. A run answers every case with the run's model."""
        return self.request("POST", "/v1/golden", {"cases": list(cases)})

    def golden(self) -> dict:
        return self.request("GET", "/v1/golden")

    def golden_delete(self, ids: list[str] | None = None) -> dict:
        """Delete these cases (an empty list deletes nothing), or every case when ids is None."""
        return self.request("POST", "/v1/golden/delete", {} if ids is None else {"ids": list(ids)})

    def golden_run(self, model: str | None = None) -> dict:
        """Answer every golden case; returns accuracy and what changed since the last run of that model."""
        return self.request("POST", "/v1/golden/run", _drop_none({"model": model}))

    def decisions_delete(self) -> dict:
        """Delete every stored decision record and label of this tenant."""
        return self.request("POST", "/v1/decisions/delete", {})

    # -- batches
    def batch_create(self, requests: Iterable[dict]) -> dict:
        """Many decisions as one background job. Each request is a /v1/systemone body with an optional custom_id."""
        return self.request("POST", "/v1/batches", {"requests": list(requests)})

    def batch_upload(self, path: str) -> dict:
        """A batch from a JSON Lines file, one /v1/systemone body (with an optional custom_id) per line."""
        with open(path, "rb") as f:
            return self.request("POST", "/v1/batches", data=f.read(), content_type="application/x-ndjson")

    def batch(self, batch_id: str) -> dict:
        return self.request("GET", "/v1/batches/" + urllib.parse.quote(batch_id))

    def batches(self) -> list[dict]:
        return self.request("GET", "/v1/batches").get("batches", [])

    def batch_results(self, batch_id: str) -> list[dict]:
        """One result per request, in the order sent: {"custom_id", "status", "response" or "error"}."""
        raw = self.request("GET", f"/v1/batches/{urllib.parse.quote(batch_id)}/results", raw=True)
        return [json.loads(line) for line in raw.decode().splitlines() if line.strip()]

    def batch_wait(self, batch_id: str, timeout: float = 600.0, poll_seconds: float = 1.0) -> dict:
        """Poll until the job has finished or stopped; raises TimeoutError after `timeout` seconds."""
        deadline = time.monotonic() + timeout
        while True:
            job = self.batch(batch_id)
            if job.get("status") not in ("queued", "running"):
                return job
            if time.monotonic() >= deadline:
                raise TimeoutError(f"batch {batch_id} still {job.get('status')} after {timeout} s")
            time.sleep(poll_seconds)

    # -- fine-tuning
    def finetune(self, base: str | None = None) -> dict:
        """Train a model of your own on your golden cases (at least 20). base: "english" (the gateway's default),
        "multilingual" or "typed-decisions". Returns the job: job, model, cases, held_out, state. One job runs at a
        time; a second one, or an engine that is off, is a ConflictError."""
        return self.request("POST", "/v1/finetune", _drop_none({"base": base}))

    def finetunes(self) -> dict:
        """Your fine-tuning jobs, newest first, with min_cases and the bases you can train from."""
        return self.request("GET", "/v1/finetune")

    def finetune_job(self, job: str) -> dict:
        """One job: state (running, saving, done, failed with error), result, and usable (the model is in service)."""
        return self.request("GET", "/v1/finetune/" + urllib.parse.quote(job))

    def finetune_wait(self, job: str, timeout: float = 3600.0, poll_seconds: float = 10.0) -> dict:
        """Poll until the job is done or failed; raises TimeoutError after `timeout` seconds."""
        deadline = time.monotonic() + timeout
        while True:
            got = self.finetune_job(job)
            if got.get("state") not in ("running", "saving"):
                return got
            if time.monotonic() >= deadline:
                raise TimeoutError(f"fine-tuning job {job} still {got.get('state')} after {timeout} s")
            time.sleep(poll_seconds)

    def finetune_delete(self, model: str) -> dict:
        """Delete a model you fine-tuned: its files are deleted and its name stops working."""
        return self.request("POST", "/v1/finetune/delete", {"model": model})

    # -- account
    def models(self) -> Models:
        d = self.request("GET", "/v1/models")
        return Models(d.get("models", []), d.get("default"), d.get("aliases", {}))

    def usage(self) -> dict:
        return self.request("GET", "/v1/usage")


class AsyncJepelaClient:
    """Every JepelaClient method as a coroutine. Each call runs the synchronous client in a worker thread,
    so a program can have several decisions in flight without a second HTTP library."""

    def __init__(self, **kwargs):
        self._sync = JepelaClient(**kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self._sync.close()
        return False

    async def system_one(self, *args, **kwargs) -> Response:
        return await asyncio.to_thread(self._sync.system_one, *args, **kwargs)

    def __getattr__(self, name: str):
        target = getattr(self._sync, name)
        if name.startswith("_") or not callable(target):
            return target

        @functools.wraps(target)
        async def call(*args, **kwargs):
            return await asyncio.to_thread(target, *args, **kwargs)
        return call
