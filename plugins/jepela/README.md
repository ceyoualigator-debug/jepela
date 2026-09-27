# Jepela plugin for Claude Code

Jepela, the decision API with memory, as MCP tools for Claude: `decide`, `remember`, `forget`, `delete`,
`memory`, `feedback` and `quality`, plus a skill that says how to write questions and memory lines that
work. The server (`server/jepela_mcp.py`) is one file of standard-library Python; it needs Python 3.10 or
newer and nothing else.

## Install

```bash
export JEPELA_API_KEY=jj_live_...                 # your key
export JEPELA_MODEL=jepela-english                 # optional: the model decide uses when a call names none
```

Then, in Claude Code:

```
/plugin marketplace add ceyoualigator-debug/jepela
/plugin install jepela@jepela
```

Start Claude Code from the shell where the variables are set. Without a key the server still starts and
every tool call says how to get one.

## Use it without Claude Code

Any MCP client can start the server over stdio:

```bash
JEPELA_API_KEY=jj_live_... python3 plugins/jepela/server/jepela_mcp.py
```

It speaks MCP versions 2025-06-18, 2025-03-26 (including batches of messages) and 2024-11-05. Every
successful tool result has a short text for the model and the full API response as `structuredContent`;
an error result has the text only.
