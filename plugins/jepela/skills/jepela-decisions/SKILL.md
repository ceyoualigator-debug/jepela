---
name: jepela-decisions
description: Use the Jepela MCP tools (decide, remember, forget, delete, memory, feedback, quality) to make typed decisions about a situation - route, classify, score, check yes/no - with a per-subject memory, instead of guessing an answer in prose.
---

# Deciding with Jepela

Jepela answers typed questions about a situation and returns a probability for every option. It does not
write text. Use it when a task needs a decision that should be consistent, measurable and, when a
subject is involved, informed by what is known about that subject.

## The tools

- `decide`: `state` (text or JSON) and `questions`, a map of id to question. Optional `subject` to use its
  memory, `compare: true` to also see the answer without memory, `robust: true` to average a choice of up
  to 20 options over three option orders (two for two options; billed per order), `derive` and `values` for facts computed in code.
- `remember` / `memory` / `forget` / `delete`: write, read, remove one concept, or remove everything
  about a subject. A subject is any id: a customer, a user, a player, a device.
- `feedback`: the right answer for one question of an earlier decision, by its `decision_id`.
- `quality`: accuracy and calibration per question from that feedback.

## Questions that work

- `choice`: unordered categories, `criteria` maps option names to short descriptions. Add an `other`
  option. Up to 20 options are read by the engine; larger sets are matched by vectors, so give every option a
  short description of what it means.
- `score`: 2 to 10 ordered levels, lowest first, each described as a situation, not as "low" or "high".
- `noul`: one yes/no statement phrased for yes. One thing per question; combine answers in code.
- Keep the state short: the engine reads up to about 475 tokens of it on the English model (measured with
  a short yes/no question; long questions, many options and memory lines leave less). The answer says
  when it read less than the whole state (`state_truncated`); send the part that matters.

## Memory that works

- One fact per line, saying what is true or what to do: "ACME holds an enterprise contract",
  "In the Coin Hall, the hero goes down the plain stair".
- Do not write what to avoid. A line such as "Never walk along the gold coins" pulled a decision toward
  the coins (83% to 94%, measured). `remember` returns a warning when a line does this.
- When an option must never be chosen, leave it out of the question (an application can also store an
  exclusion rule through the API, which removes it in code). A memory line makes allowed answers more or
  less likely; it cannot forbid one (on ten roulette states where 17 had just come up, a line saying which
  bets to make left 17 the bet in 10 of 10, against 9 of 10 with no memory; measured 2026-09-23).
- Numbers compared in words ("above 75 C") are read as words. Put the number in `values` and use `derive`,
  or a memory rule with `when` added through the API (`POST /v1/memory/rules`) or an SDK (`rules_add`,
  `rulesAdd`); these tools cannot add a rule, but `decide` fires the rules a subject has.

## Acting on answers

Gate actions on the probability and on what a mistake costs. Start from a guess, such as acting alone
above about 0.9, asking for confirmation between 0.6 and 0.9 and handing lower ones to a person, then set
the thresholds from `quality`, which gives per question the probability where 90% accuracy is reached.
When the right answer becomes known, send `feedback`, and check `quality` before trusting a question with
more automation.
