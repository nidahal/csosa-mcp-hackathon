# CSOSA Spending Assistant (Streamlit UI)

A small web front end for the CSOSA MCP agent: a multi-turn chat where you
ask a natural-language question (and follow-ups — it remembers the
conversation) and get back a narrated answer plus an auto-generated chart
and the underlying source records (each linking to its USAspending.gov
permalink). It retrieves, aggregates, and explains public contract-spending
data — it never writes back to USAspending.gov or any external system.

This reuses the same tool-calling loop as the CLI agent
(`agent/csosa_agent.py`) — shared code lives in `agent/core.py` — so the two
stay in sync. It talks to the already-deployed MCP server over
streamable-HTTP (see `deploy/databricks/`), the same path a real client
(watsonx Orchestrate, Databricks Playground) would use.

## Run

```bash
uv sync --group webapp
export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
export DATABRICKS_TOKEN=$(databricks auth token --profile <profile> | jq -r .access_token)
export MCP_SERVER_URL=https://<app>.databricksapps.com/mcp
uv run streamlit run webapp/app.py
```

If any of those three env vars are unset, the sidebar has text fields for
entering them at runtime instead — pre-filled with this deployment's known
host and MCP server URL, so only a token is usually needed. When running as
the deployed Databricks App, it first tries to auto-authenticate using the
app's own injected service-principal credentials (see
`deploy/databricks-webapp/README.md`'s "After it's deployed" section for the
one-time grant that makes that actually succeed); until then, or if that
exchange fails for any reason, it falls back to the manual token field
exactly as before.

Use **Clear conversation** in the sidebar to start a fresh conversation
(each follow-up question otherwise keeps the full prior exchange in context,
so token usage grows with conversation length).

## What renders a chart vs. a table

| Tool result | Rendering |
|---|---|
| `csosa_spending_summary` (`group_by="fiscal_year"`) | Line chart — obligations over time |
| `csosa_spending_summary` (`recipient` / `product_or_service`) | Horizontal ranked bar chart |
| `csosa_search_contract_awards` / `csosa_search_subawards` | Ranked bar chart (top 10 by amount) + full table with a source link column |
| `csosa_list_idv_child_awards` | Table with a source link column |
| `csosa_get_award_details` | Raw JSON (single record, no chart) |

Chart colors follow the Anthropic dataviz skill's validated default palette
(`webapp/charts.py`): light-mode chart surface, single sequential blue hue.
Every chart here is one series, so no multi-hue palette validation applies.
