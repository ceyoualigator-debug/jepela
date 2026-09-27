// Questions you send and answers you get back. A choice keeps its option names as a type, so
// `response.answers.route.choice` is typed "billing" | "support" | "other", not string.

export interface ChoiceQuestion<K extends string = string> {
  type: "choice";
  instructions: string;
  criteria: Record<K, string>;
}

export interface ScoreQuestion {
  type: "score";
  instructions: string;
  criteria: string[];
}

export interface NoulQuestion {
  type: "noul";
  instructions: string;
  criteria?: { true?: string; false?: string };
}

export type Question = ChoiceQuestion<string> | ScoreQuestion | NoulQuestion;
export type Questions = Record<string, Question>;

/** Pick one option. Up to 20 options are read in one round; larger sets are answered in two rounds. */
export function choice<const K extends string>(instructions: string, criteria: Record<K, string>): ChoiceQuestion<K> {
  return { type: "choice", instructions, criteria };
}

/** Rate on 2 to 10 ordered levels, lowest first, each described as a situation. */
export function score(instructions: string, levels: string[]): ScoreQuestion {
  return { type: "score", instructions, criteria: levels };
}

/** A yes/no statement; the answer is the probability of yes. */
export function noul(instructions: string, criteria?: { true?: string; false?: string }): NoulQuestion {
  return criteria ? { type: "noul", instructions, criteria } : { type: "noul", instructions };
}

export interface Calibration {
  scope: string;
  temperature: number;
  [k: string]: unknown;
}

export interface ChoiceAnswer<K extends string = string> {
  type: "choice";
  choice: K;
  probabilities: Record<K, number>;
  confidence?: number;
  rounds?: number;              // 2 when the options were asked in groups
  orders?: number;              // option orders averaged (robust)
  agreement?: number;           // share of those orders that picked `choice`
  calibration?: Calibration;    // the tenant temperature applied, if any
  raw_probabilities?: Record<K, number>;
  window?: number;
  method?: "engine" | "match";  // read by the engine, or matched by vectors
  similarity?: { best: number; second: number | null };   // matched answers: the best and second-best cosine
}

export interface ScoreAnswer {
  type: "score";
  score: number;
  probabilities: Record<string, number>;
  legend: Record<string, string>;
  confidence?: number;
  calibration?: Calibration;
  raw_probabilities?: Record<string, number>;
  raw_score?: number;
  window?: number;
  method?: "engine";
}

export interface NoulAnswer {
  type: "noul";
  noul: number;
  confidence?: number;
  calibration?: Calibration;
  raw_noul?: number;
  window?: number;
  method?: "engine";
}

export type AnswerFor<Q> = Q extends ChoiceQuestion<infer K> ? ChoiceAnswer<K> : Q extends ScoreQuestion ? ScoreAnswer : NoulAnswer;
export type Answers<Q extends Questions> = { [Id in keyof Q]: AnswerFor<Q[Id]> };

export interface Usage {
  input_characters: number;
  questions: number;
  answers: number;
  answers_billed: number;
  engine_answers: number;
  memory_lines_used: number;
  memory_lines_seen: number;
  engine_ms: number;
  gateway_ms: number;
  cached: boolean;
  cost: number;
  currency: string;
  balance?: number;
  input_tokens?: number;         // only when the engine counted them
  state_tokens?: number;         // the state, in the engine's tokens
  state_tokens_read?: number;    // how much of it the engine read
  state_truncated?: boolean;
  match_questions?: number;      // choice questions answered by matching, when some were
}

export interface JepelaWarning {
  code: string;
  message: string;
  question?: string;
}

export interface MemoryResult<Q extends Questions = Questions> {
  subject: string;
  lines_used: number;
  lines_seen: number;
  lines_dropped: number;   // fired rules and recalled lines left out of the engine's 64 context lines
  hits: { text: string; [k: string]: unknown }[];
  rules_fired: { id: string; text: string }[];
  rules_broken: { id: string; error: string }[];
  recall_ms?: number;
  without_memory?: Answers<Q>;
  changes?: Record<string, unknown>;
  placebo?: { content_effect: Record<string, number>; memory_effect: Record<string, number>; presence_only: string[]; [k: string]: unknown };
  pinned?: string[];                                    // ids of the pinned rules sent
  excluded?: Record<string, Record<string, string>>;    // per question: { option: why } removed by exclusion rules
  exclusions_skipped?: { question: string; options: string[]; reason: string }[];
  explain?: { line: string; kind: "pinned" | "rule" | "recalled"; effect: Record<string, number> }[];
}

export interface Response<Q extends Questions = Questions> {
  decision_id: string;
  model: string;
  answers: Answers<Q>;
  usage: Usage;
  warnings: JepelaWarning[];
  engine: Record<string, unknown>;
  memory?: MemoryResult<Q>;
  reading?: Record<string, { state_tokens: number; read: number; room: number; chars_read: number; truncated: boolean }>;
  derived?: Record<string, unknown>;
  windows?: { count: number; [k: string]: unknown };
}

export interface MemoryOptions {
  use?: boolean;
  top_k?: number;       // lines recalled, 1 to 20 (default 6)
  min_share?: number;   // keep lines scoring at least this share of the best one, 0.05 to 1 (default 0.2)
  compare?: boolean;    // also answer without memory
  placebo?: boolean;    // also answer with neutral lines, to show the memory worked by its content
  names?: boolean;      // search the subject's name and aliases with the state (default true)
  question_words?: boolean;   // search the questions' instructions too (default true)
  focus?: boolean;      // keep only lines that share a word with the state beyond those names (default false)
  explain?: boolean;    // per memory line (at most 8), how far the answer moves when it alone is left out (default false)
}

export interface DecideOptions {
  model?: string;
  subject?: string;
  memory?: MemoryOptions;
  robust?: boolean | { orders: number };   // choices of up to 20 options; true is 3 orders, at most 5
  windows?: boolean | { combine?: Record<string, "max" | "mean" | "min"> };   // up to 16 overlapping windows
  derive?: Record<string, string | { when: string; fact: string; else?: string }>;
  values?: Record<string, unknown>;
  cache?: boolean;
  method?: "auto" | "engine" | "match";   // auto (default): match choices of more than 20 options, ask the engine the rest
}

export interface FinetuneJob {
  job: string;
  model: string;                 // the name to use in requests once usable
  state: "running" | "saving" | "done" | "failed";
  base?: string;
  cases?: number;
  held_out?: number;
  cases_with_memory?: number;
  result?: Record<string, unknown> | null;   // won, base_accuracy, tuned_accuracy, held_out_questions, log losses, training_seconds
  usable: boolean;               // true when the model is in service
  error?: string | null;
  warnings: string[];
  [k: string]: unknown;
}

export interface MemoryInfo {
  subject: string;
  lines_stored: number;
  rules: number;
  lines?: string[];
  rule_list?: { id: string; when: string; text: string; expires_at?: string | null }[];
}
