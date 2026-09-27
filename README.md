# Jepela

Jepela is a decision API with memory: send a state and typed questions (choice, score, yes/no), get typed answers
with a probability for every option in one call. Name a subject, and Jepela also uses what that subject's memory
holds, and shows you what it changed.

Jepela is a hosted API at `https://api.jepela.com`. This repository holds the public client code:

| Folder | What it is |
|---|---|
| `sdk/python` | Python client, standard library only |
| `sdk/typescript` | TypeScript client, no dependencies |
| `plugins/jepela` | MCP server and Claude Code plugin |
| `skills/jepela` | An agent skill: when and how to use Jepela in the software an agent writes |
| `cookbooks` | Runnable recipes against the API |

Documentation: https://jepela.com/docs/index.html · Live demos: https://demo.jepela.com

## A key

Write to [ceyoualigator@gmail.com](mailto:ceyoualigator@gmail.com?subject=Jepela%20API%20key) with a sentence about
what you want to decide; you get a key and your starting credit.

## One request

```bash
export JEPELA_API_KEY=jj_live_...
curl -s https://api.jepela.com/v1/systemone \
  -H "Authorization: Bearer $JEPELA_API_KEY" -H "Content-Type: application/json" \
  -d '{"state": "You charged me twice for September. Please send the second payment back.",
       "questions": {"refund": {"type": "noul", "instructions": "Is the customer asking for money back?"}}}'
```

## Python

```bash
pip install "git+https://github.com/ceyoualigator-debug/jepela#subdirectory=sdk/python"
```

## Claude Code

```
/plugin marketplace add ceyoualigator-debug/jepela
/plugin install jepela@jepela
```
