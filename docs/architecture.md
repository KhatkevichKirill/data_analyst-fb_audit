# Architecture

```text
Browser -> FastAPI notebook app -> LiteLLM provider
                |-> analyst_app Postgres (users, notebooks, cells, events)
                |-> read-only analytics Postgres (demo or your warehouse)
                |-> optional python_exec sandbox (bubblewrap)
                |-> knowledge markdown pages (read_wiki tool)
```

## Core Components

| Component | Purpose |
|---|---|
| `web/app.py` | FastAPI entrypoint, migrations on boot, schema crib bootstrap |
| `web/agent.py` | SSE agent loop, tool dispatch, turn caps |
| `tools.py` | `sql`, `read_wiki`, `chart`, `export_csv`, `python_exec` |
| `analyst.py` | CLI REPL, model profile registry, schema crib loader |
| `migrations/` | `analyst_app` schema for auth + notebooks |
| `knowledge/` | Markdown pages exposed through `read_wiki` |

## Agent Loop

1. User submits a prompt in a notebook cell.
2. Server creates a `cells` row and opens an SSE stream.
3. Agent rebuilds history from prior completed cells in the same notebook.
4. LiteLLM is called with tool specs.
5. Tool results are persisted to `events` and streamed to the browser.
6. Cell ends `done` when the model returns a final answer without tool calls.

## Two Database Users

| User | Database | Role |
|---|---|---|
| `data_analyst_ro` | analytics warehouse | read-only SQL tool |
| `data_analyst_app` | `analyst_app` | app state read/write |

Do not reuse a dashboard write-capable DB role for the SQL tool.

## Tools

### `sql`
Read-only Postgres queries with a 30s timeout and 100-row markdown cap. Successful results can be persisted as parquet for follow-up analysis.

### `read_wiki`
Loads markdown from `KNOWLEDGE_DIR` (defaults to `data_analyst/knowledge/`).

### `chart`
Runs SQL and renders Vega-Lite v5 specs client-side.

### `export_csv`
Writes authenticated CSV downloads into the notebook workspace.

### `python_exec`
Optional sandboxed Python over prior SQL results. Disabled by default in the starter kit.

## Schema Crib

At boot, the app introspects `pg_class` / `pg_attribute` for every table, view, and materialized view the read-only role can `SELECT`. This intentionally avoids `information_schema`, which omits materialized views.

## Production Extensions

Common production additions:

- nginx `auth_request` SSO in front of a larger dashboard host
- custom knowledge base for your warehouse semantics
- model routing / escalation between cheap and strong profiles
- background runner for mid-run disconnect survival

Those should plug into the same tool layer rather than replacing the notebook model.
