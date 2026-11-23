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
OAuth service principal) are injected automatically, and `webapp/app.py`
tries to exchange them for a bearer token via OAuth M2M
(`POST {host}/oidc/v1/token`, `grant_type=client_credentials`) before ever
asking for a manual one. That exchange only *succeeds* once this app's
service principal has been granted access to what it's calling, though:

1. **`CAN_USE` on the MCP server app** (`csosa-mcp-server`), so it can call
   `/mcp`. One-time grant, from a machine with admin/owner access to both
   apps. First get this app's service-principal client ID:
   ```bash
   databricks apps get csosa-spending-webapp --output json | grep service_principal_client_id
   ```
   Then grant it `CAN_USE` on the MCP server app (`update-permissions` is
   additive — it won't touch existing grants):
   ```bash
   cat > /tmp/grant.json <<'JSON'
   {
     "access_control_list": [
       {"service_principal_name": "<client id from the previous command>", "permission_level": "CAN_USE"}
     ]
   }
   JSON
   databricks apps update-permissions csosa-mcp-server --json @/tmp/grant.json
   ```
2. **Query access to the model-serving endpoint** (`databricks-claude-sonnet-4-5`
   or whichever `MODEL` is configured) for the same service principal —
   check `databricks serving-endpoints get-permissions <endpoint>` and grant
   `CAN_QUERY` if it isn't already open to the workspace.

Until both are granted (or if the token exchange fails for any other
reason), the app **degrades gracefully** to exactly the manual flow below —
it never crashes the page. Open the app URL and fill in the sidebar:

- `DATABRICKS_HOST` — pre-filled with this workspace's URL
- `DATABRICKS_TOKEN` — a token good for both the model-serving endpoint and
  the MCP server app (`databricks auth token --profile <profile>`)
- `MCP_SERVER_URL` — pre-filled with the MCP server app's `/mcp` endpoint
