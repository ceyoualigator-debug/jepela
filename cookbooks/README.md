# Jepela cookbooks

Runnable recipes against a Jepela gateway. Each prints what it measured; nothing is hard-coded.

```bash
export JEPELA_API_KEY=jj_live_...            # your Jepela key
export JEPELA_BASE_URL=https://api.jepela.com  # the default
python3 cookbooks/support_triage.py
```

Each script deletes and rewrites the memory of its own subjects under your key's tenant (`northwind`, `contoso`,
`fabrikam`, `mia`, `player-7`, `pump-12`, `pump-13`), and its requests are billed; use a tenant of its own.

| Script | Pattern | What it shows |
|---|---|---|
| `support_triage.py` | speculative fan-out | five questions per ticket in one request; code uses the ones the category makes relevant |
| `escalation_with_memory.py` | memory-first routing | the same complaint from a priority account and a control account, with and without memory |
| `forget_on_request.py` | forgetting | remember, decide, forget with a verified removal, decide again, delete |
| `cost_per_decision.py` | cost per decision | the whole customer history in every request against the history in memory: tokens, accuracy, time |
| `rules_in_memory.py` | rules in memory | forbidden options left out in code, a stop-loss as a rule with `when`, and what memory wording can and cannot do, measured |
| `guardrails.py` | screening | nouls plus a severity score route messages to pass, review, block or support |
| `intent_routing.py` | confidence-gated routing | intent and complexity choose the handler: code, specialist, person |
| `composite_scoring.py` | composite scoring | one score per dimension, two weightings in code |
| `game_npc_memory.py` | a player as the subject | how characters treat a player, with and without what the player did |
| `device_alerts.py` | a machine as the subject | limits checked in code with `derive`, memory for what a technician knows |
| `lead_scoring.py` | lead scoring | an unsubscribe gate first, then fit, timing, budget and size combined in code |

`JEPELA_MODEL` picks the model (default `jepela-english`). For the Jepela team: the published results in
`docs/jepela/cookbooks.md` and `docs/jepela/examples.md` are regenerated against a gateway and product started from this
repository, in front of the engine at `LAYA_URL`, which must already be running; keys and memory go to a temporary
directory:

```bash
python3 cookbooks/build_docs.py --own-stack
python3 cookbooks/build_examples.py --own-stack
```
