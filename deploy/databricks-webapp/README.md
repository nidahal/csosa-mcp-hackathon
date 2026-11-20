# Databricks Apps Deployment — Spending Assistant (Streamlit UI)

Deploy `webapp/app.py` as a [Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/),
separate from the MCP server app in [`deploy/databricks/`](../databricks/). The
two don't share a source path or app name — each kit syncs its own copy of the
repo and deploys its own app.

- **Transport:** Streamlit over HTTP, served at the app's root path.
- **Port:** Databricks injects `DATABRICKS_APP_PORT`; `app.yaml`'s `command`
  passes it straight to `streamlit run --server.port`.

## Prerequisites

Same as [`deploy/databricks/README.md`](../databricks/README.md) Part 1
(Databricks CLI installed, authenticated, Apps enabled on your workspace).

## Deploy

```bash
cp deploy/databricks-webapp/.env.example deploy/databricks-webapp/.env
# edit APP_NAME / SOURCE_CODE_PATH / DATABRICKS_HOST / DATABRICKS_CONFIG_PROFILE

set -a; source deploy/databricks-webapp/.env; set +a
bash deploy/databricks-webapp/deploy-databricks-app.sh
```

Idempotent: creates the app on first run, redeploys on later runs.

## After it's deployed

The deployed app's `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` (an
OAuth service principal) are injected automatically, but `agent/core.py`
currently expects a plain bearer token — the app does **not** auto-auth yet.
Open the app URL and fill in the sidebar:

- `DATABRICKS_HOST` — this workspace's URL
- `DATABRICKS_TOKEN` — a token good for both the model-serving endpoint and
  the MCP server app (`databricks auth token --profile <profile>`)
- `MCP_SERVER_URL` — the MCP server app's `/mcp` endpoint (from
  `deploy/databricks/`)

Exchanging the injected service-principal credentials for a token
automatically (OAuth M2M, `POST /oidc/v1/token`) would remove that manual
step — not done yet, since it changes `agent/core.py`'s auth path for both
the CLI and this web UI.
