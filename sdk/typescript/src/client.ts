// The HTTP client, on the fetch built into Node 18+, Deno, Bun and browsers. No dependencies.
//
// Retries 429, 502 and 503 with backoff (a 429's Retry-After is honoured), and connections that failed
// before the request was sent. A request that was sent and then failed is sent again only if it is a
// GET, so a decision is never billed twice.

import { ConnectionFailed, JepelaError, errorFor } from "./errors.ts";
import type { DecideOptions, FinetuneJob, MemoryInfo, Questions, Response } from "./types.ts";

export const DEFAULT_BASE_URL = "https://api.jepela.com";

/** The region a Jepela key belongs to (jj_live_eu_... is "eu"); undefined for keys made before regions (they are us). */
export function regionOf(apiKey?: string): string | undefined {
  return /^jj_live_([a-z]{2})_[0-9a-f]{32}$/.exec(apiKey ?? "")?.[1];
}

/** The API address of a key's region, or of the region named; https://api.jepela.com when neither says one. */
export function baseUrlFor(apiKey?: string, region?: string): string {
  const r = region ?? regionOf(apiKey);
  return r ? `https://${r}.api.jepela.com` : DEFAULT_BASE_URL;
}
const RETRY_STATUSES = new Set([429, 502, 503]);
const NOT_SENT = new Set(["ECONNREFUSED", "ENOTFOUND", "EAI_AGAIN", "UND_ERR_CONNECT_TIMEOUT", "EHOSTUNREACH", "ENETUNREACH"]);
const USER_AGENT = "jepela-sdk-ts/0.1.0";

export interface ClientOptions {
  apiKey?: string;       // or JEPELA_API_KEY
  baseUrl?: string;      // or JEPELA_BASE_URL, or the API of the key's region (jj_live_eu_... goes to https://eu.api.jepela.com)
  timeoutMs?: number;    // per HTTP call, default 120 000
  maxRetries?: number;   // default 2
  backoffMs?: number;    // default 500
}

interface Sent {
  method: string;
  path: string;
  body?: unknown;
  data?: string;
  contentType?: string;
  raw?: boolean;
}

const env = (name: string): string | undefined =>
  typeof process !== "undefined" && process.env ? process.env[name] || undefined : undefined;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const q = encodeURIComponent;

function causeCode(err: unknown): string | undefined {
  const cause = (err as { cause?: { code?: string; errors?: { code?: string }[] } })?.cause;
  return cause?.code ?? cause?.errors?.[0]?.code;
}

async function call(baseUrl: string, apiKey: string | undefined, sent: Sent, timeoutMs: number, maxRetries: number, backoffMs: number): Promise<any> {
  const headers: Record<string, string> = { Accept: "application/json", "User-Agent": USER_AGENT };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  let payload: string | undefined = sent.data;
  if (sent.body !== undefined) payload = JSON.stringify(sent.body);
  if (payload !== undefined) headers["Content-Type"] = sent.contentType ?? "application/json";
  for (let attempt = 0; ; attempt++) {
    let res: globalThis.Response;
    try {
      res = await fetch(baseUrl + sent.path, { method: sent.method, headers, body: payload, signal: AbortSignal.timeout(timeoutMs) });
    } catch (err) {
      const code = causeCode(err);
      const notSent = code !== undefined && NOT_SENT.has(code);
      if ((notSent || sent.method === "GET") && attempt < maxRetries) {
        await sleep(backoffMs * 2 ** attempt);
        continue;
      }
      throw new ConnectionFailed(notSent ? `cannot reach ${baseUrl}: ${code}`
        : `no answer from ${baseUrl} to ${sent.method} ${sent.path}: ${code ?? (err as Error).name}` +
          (sent.method === "GET" ? "" : "; not sent again, so it cannot be billed twice"));
    }
    const text = await res.text();
    if (res.ok) {
      if (sent.raw || (res.headers.get("Content-Type") ?? "").includes("ndjson")) return text;
      return JSON.parse(text);
    }
    let kind: string | undefined, message: string | undefined;
    try {
      const err = JSON.parse(text).error;
      kind = typeof err === "object" ? err.type : undefined;
      message = typeof err === "object" ? err.message : String(err);
    } catch { /* not JSON */ }
    const retryAfter = Number(res.headers.get("Retry-After")) || undefined;
    const error = errorFor(res.status, message ?? text.slice(0, 200), kind, retryAfter);
    if (RETRY_STATUSES.has(res.status) && attempt < maxRetries) {
      await sleep(Math.min(retryAfter ? retryAfter * 1000 : backoffMs * 2 ** attempt * (1 + Math.random() / 4), 30_000));
      continue;
    }
    throw error;
  }
}

/** Ask a gateway with self-serve sign-up for a new key. Needs no key; the key is shown once. */
export async function signup(email: string, opts: { inviteCode?: string; baseUrl?: string; timeoutMs?: number; region?: string } = {}) {
  const baseUrl = (opts.baseUrl ?? env("JEPELA_BASE_URL") ?? baseUrlFor(undefined, opts.region)).replace(/\/+$/, "");
  const body: Record<string, string> = { email };
  if (opts.region) body.region = opts.region;
  if (opts.inviteCode) body.invite_code = opts.inviteCode;
  return call(baseUrl, undefined, { method: "POST", path: "/v1/signup", body }, opts.timeoutMs ?? 30_000, 0, 0) as
    Promise<{ tenant: string; key: string; key_id: string; credit: number; currency: string }>;
}

const clean = <T extends Record<string, unknown>>(o: T): Partial<T> =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as Partial<T>;

export class JepelaClient {
  readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly timeoutMs: number;
  private readonly maxRetries: number;
  private readonly backoffMs: number;

  constructor(opts: ClientOptions = {}) {
    const key = opts.apiKey ?? env("JEPELA_API_KEY");
    if (!key) throw new JepelaError("no API key: pass apiKey or set JEPELA_API_KEY");
    this.apiKey = key;
    this.baseUrl = (opts.baseUrl ?? env("JEPELA_BASE_URL") ?? baseUrlFor(key)).replace(/\/+$/, "");
    this.timeoutMs = opts.timeoutMs ?? 120_000;
    this.maxRetries = opts.maxRetries ?? 2;
    this.backoffMs = opts.backoffMs ?? 500;
  }

  /** Any gateway route: parsed JSON, or text for JSON Lines results. */
  request<T = any>(method: string, path: string, body?: unknown, extra: Partial<Sent> = {}): Promise<T> {
    return call(this.baseUrl, this.apiKey, { method, path, body, ...extra }, this.timeoutMs, this.maxRetries, this.backoffMs);
  }

  // -- decisions
  /** Every question answered against the same state. With a subject, its memory is read first. */
  systemOne<Q extends Questions>(state: unknown, questions: Q, opts: DecideOptions = {}): Promise<Response<Q>> {
    return this.request("POST", "/v1/systemone", clean({ state, questions, ...opts }));
  }

  // -- memory
  remember(subject: string, text: string) {
    return this.request<{ subject: string; lines_added: number; lines_stored: number; warnings: { code: string; message: string }[] }>(
      "POST", "/v1/memory/remember", { subject, text });
  }
  forget(subject: string, concept: string) {
    return this.request<{ subject: string; lines_removed: number; rules_removed: number; verified_forgotten: boolean }>(
      "POST", "/v1/memory/forget", { subject, concept });
  }
  delete(subject: string) {
    return this.request<{ subject: string; lines_removed: number }>("POST", "/v1/memory/delete", { subject });
  }
  memory(subject: string, lines = false): Promise<MemoryInfo> {
    return this.request("GET", `/v1/memory?subject=${q(subject)}${lines ? "&lines=true" : ""}`);
  }
  rulesAdd(subject: string, when: string, text: string, opts: { expires?: string; ttlSeconds?: number } = {}) {
    return this.request("POST", "/v1/memory/rules", clean({ subject, when, text, expires: opts.expires, ttl_seconds: opts.ttlSeconds }));
  }
  /** A line sent first at every decision about the subject, whatever the state says. */
  pin(subject: string, text: string, opts: { expires?: string; ttlSeconds?: number } = {}) {
    return this.request("POST", "/v1/memory/rules", clean({ subject, text, pin: true, expires: opts.expires, ttl_seconds: opts.ttlSeconds }));
  }
  /** Options removed from choice questions in code for this subject; the text says why and is never sent to the engine. */
  exclude(subject: string, options: string[], text: string, opts: { question?: string; when?: string; expires?: string; ttlSeconds?: number } = {}) {
    return this.request("POST", "/v1/memory/rules", clean({ subject, exclude: options, text, question: opts.question, when: opts.when,
                                                            expires: opts.expires, ttl_seconds: opts.ttlSeconds }));
  }
  /** Other names the subject goes by; recall searches them with the state. An empty list clears them. */
  aliases(subject: string, names: string[]) {
    return this.request("POST", "/v1/memory/aliases", { subject, aliases: names });
  }
  async rules(subject: string): Promise<{ id: string; when: string; text: string; expires_at?: string | null; created?: string }[]> {
    return (await this.request("GET", `/v1/memory/rules?subject=${q(subject)}`)).rules ?? [];
  }
  rulesDelete(subject: string, ruleId: string) {
    return this.request("POST", "/v1/memory/rules/delete", { subject, rule_id: ruleId });
  }

  // -- labels, quality, calibration, golden sets
  feedback(decisionId: string, question: string, correct: string | number | boolean) {
    return this.request("POST", "/v1/feedback", { decision_id: decisionId, question, correct });
  }
  quality(opts: { question?: string; days?: number; model?: string; source?: string } = {}) {
    const query = new URLSearchParams(Object.entries(clean(opts)).map(([k, v]) => [k, String(v)])).toString();
    return this.request("GET", "/v1/quality" + (query ? `?${query}` : ""));
  }
  calibrationFit(opts: { model?: string; question?: string; source?: string; minLabels?: number } = {}) {
    return this.request("POST", "/v1/calibration/fit", clean({ model: opts.model, question: opts.question, source: opts.source, min_labels: opts.minLabels }));
  }
  async calibration(): Promise<unknown[]> {
    return (await this.request("GET", "/v1/calibration")).temperatures ?? [];
  }
  goldenAdd(cases: unknown[]) {
    return this.request("POST", "/v1/golden", { cases });
  }
  golden() {
    return this.request("GET", "/v1/golden");
  }
  goldenDelete(ids?: string[]) {
    return this.request("POST", "/v1/golden/delete", ids !== undefined ? { ids } : {});   // [] deletes nothing; no ids, every case
  }
  goldenRun(model?: string) {
    return this.request("POST", "/v1/golden/run", clean({ model }));
  }
  decisionsDelete() {
    return this.request("POST", "/v1/decisions/delete", {});
  }

  // -- batches
  batchCreate(requests: unknown[]) {
    return this.request("POST", "/v1/batches", { requests });
  }
  /** A batch from JSON Lines text, one /v1/systemone body (with an optional custom_id) per line. */
  batchUpload(jsonl: string) {
    return this.request("POST", "/v1/batches", undefined, { data: jsonl, contentType: "application/x-ndjson" });
  }
  batch(id: string) {
    return this.request("GET", `/v1/batches/${q(id)}`);
  }
  async batches(): Promise<any[]> {
    return (await this.request("GET", "/v1/batches")).batches ?? [];
  }
  async batchResults(id: string): Promise<any[]> {
    const text: string = await this.request("GET", `/v1/batches/${q(id)}/results`, undefined, { raw: true });
    return text.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
  }
  async batchWait(id: string, timeoutMs = 600_000, pollMs = 1000) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const job = await this.batch(id);
      if (job.status !== "queued" && job.status !== "running") return job;
      if (Date.now() >= deadline) throw new JepelaError(`batch ${id} still ${job.status} after ${timeoutMs} ms`);
      await sleep(pollMs);
    }
  }

  // -- fine-tuning
  /** Train a model of your own on your golden cases (at least 20); base "english" (default), "multilingual" or "typed-decisions". */
  finetune(base?: "english" | "multilingual" | "typed-decisions") {
    return this.request<FinetuneJob>("POST", "/v1/finetune", clean({ base }));
  }
  /** Your jobs, newest first, with the fewest cases a job needs and the bases you can train from. */
  finetunes() {
    return this.request<{ jobs: FinetuneJob[]; min_cases: number; bases: string[] }>("GET", "/v1/finetune");
  }
  finetuneJob(id: string) {
    return this.request<FinetuneJob>("GET", `/v1/finetune/${q(id)}`);
  }
  async finetuneWait(id: string, timeoutMs = 3_600_000, pollMs = 10_000): Promise<FinetuneJob> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const job = await this.finetuneJob(id);
      if (job.state !== "running" && job.state !== "saving") return job;
      if (Date.now() >= deadline) throw new JepelaError(`fine-tuning job ${id} still ${job.state} after ${timeoutMs} ms`);
      await sleep(pollMs);
    }
  }
  /** Delete a model you fine-tuned: its files go and its name stops working. */
  finetuneDelete(model: string) {
    return this.request<{ deleted: string }>("POST", "/v1/finetune/delete", { model });
  }

  // -- account
  models() {
    return this.request<{ models: { name: string; available: boolean; description: string }[]; default: string; aliases: Record<string, string> }>(
      "GET", "/v1/models");
  }
  usage() {
    return this.request("GET", "/v1/usage");
  }
}
