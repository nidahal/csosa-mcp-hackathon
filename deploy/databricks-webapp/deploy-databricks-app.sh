#!/usr/bin/env bash
# Deploy the CSOSA Spending Assistant (Streamlit web UI) to Databricks Apps.
#
# Flow:
#   1. Ensure the Databricks App exists (create-or-reuse).
#   2. Sync the repo source to a workspace path (SOURCE_CODE_PATH).
#   3. `databricks apps deploy` from that path.
#
# This is a second, independent Databricks App from the MCP server
# (deploy/databricks/) — it has its own APP_NAME and SOURCE_CODE_PATH so the
# two deploys never collide.
#
# Prerequisites:
#   - Databricks CLI (v0.205+):  https://docs.databricks.com/dev-tools/cli/install.html
#   - Authenticated:             databricks auth login --host <workspace-url>
#                                (or a configured profile / DATABRICKS_TOKEN)
#   - Apps enabled on your workspace.
#   - Config:                    cp deploy/databricks-webapp/.env.example deploy/databricks-webapp/.env && edit
#
# Usage:
#   set -a; source deploy/databricks-webapp/.env; set +a
#   bash deploy/databricks-webapp/deploy-databricks-app.sh
#
# Idempotent: creates the app on first run, redeploys on subsequent runs.
set -euo pipefail

# On Git Bash / MSYS (Windows), argv paths starting with "/" get silently
# rewritten to a local Windows path before reaching the (native, non-MSYS)
# databricks.exe — e.g. "/Workspace/Users/..." becomes "C:/Program
# Files/Git/Workspace/Users/...". Disable that conversion unconditionally;
# it's a no-op on Linux/macOS.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

# --- Validate config ----------------------------------------------------------
: "${APP_NAME:?set APP_NAME (source deploy/databricks-webapp/.env)}"
: "${SOURCE_CODE_PATH:?set SOURCE_CODE_PATH (absolute /Workspace path)}"

# Optional passthroughs to the CLI.
PROFILE_ARGS=()
if [[ -n "${DATABRICKS_CONFIG_PROFILE:-}" ]]; then
  PROFILE_ARGS=(--profile "${DATABRICKS_CONFIG_PROFILE}")
fi
if [[ -n "${DATABRICKS_HOST:-}" ]]; then
  export DATABRICKS_HOST
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# `databricks workspace import/export --file` opens the path with Windows'
# own file APIs, which don't understand a posix-style "/c/Users/..." path the
# way `sync`'s directory argument does — convert explicitly on Git Bash/MSYS
# (a no-op passthrough on Linux/macOS, where cygpath doesn't exist).
_native_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s' "$1"
  fi
}

echo "=== Target ==="
echo "  app name:         ${APP_NAME}"
echo "  source code path: ${SOURCE_CODE_PATH}"
echo "  profile:          ${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
echo "  repo root:        ${REPO_ROOT}"
echo ""

# --- Confirm the CLI is installed and authenticated ---------------------------
if ! command -v databricks >/dev/null 2>&1; then
  echo "FATAL: 'databricks' CLI not found." >&2
  echo "       Install: https://docs.databricks.com/dev-tools/cli/install.html" >&2
  exit 1
fi
if ! databricks "${PROFILE_ARGS[@]}" current-user me >/dev/null 2>&1; then
  echo "FATAL: not authenticated. Run:" >&2
  echo "       databricks auth login --host <workspace-url>" >&2
  exit 1
fi

# --- app.yaml must sit at the source root Databricks deploys from -------------
# Databricks Apps reads app.yaml from the deployed source directory. We keep
# the canonical copy in this kit and stage it at the repo root for the sync so
# the deploy sees it without polluting the repo. (Removed after deploy.)
STAGED_APP_YAML="${REPO_ROOT}/app.yaml"
CLEANUP_APP_YAML=0
if [[ ! -f "${STAGED_APP_YAML}" ]]; then
  cp "${SCRIPT_DIR}/app.yaml" "${STAGED_APP_YAML}"
  CLEANUP_APP_YAML=1
else
  echo "FATAL: ${STAGED_APP_YAML} already exists — refusing to overwrite." >&2
  echo "       Another deploy kit may be mid-run; remove it and retry." >&2
  exit 1
fi
# Anchored under REPO_ROOT, not /tmp: databricks.exe only reliably resolves
# the same posix-style path shape already proven to work for `sync`'s own
# local-source argument below — a bare /tmp/... path lands somewhere else
# entirely (Windows interprets a leading "/" as the current drive's root).
VERIFY_TMP="${REPO_ROOT}/.deploy-verify-tmp"
cleanup() {
  if [[ "${CLEANUP_APP_YAML}" == "1" ]]; then
    rm -f "${STAGED_APP_YAML}"
  fi
  rm -f "${VERIFY_TMP}"
}
trap cleanup EXIT

# --- Ensure the app exists (create-or-reuse) ----------------------------------
echo "=== Ensuring Databricks App '${APP_NAME}' ==="
if databricks "${PROFILE_ARGS[@]}" apps get "${APP_NAME}" >/dev/null 2>&1; then
  echo "  app exists — reusing."
else
  echo "  app not found — creating '${APP_NAME}'..."
  databricks "${PROFILE_ARGS[@]}" apps create "${APP_NAME}"
fi

# --- Sync the repo source to the workspace path -------------------------------
# `databricks sync --full` mirrors the whole repo (respecting .gitignore) to
# SOURCE_CODE_PATH. Full (not incremental) so the app.yaml staged above always
# reaches the workspace — see deploy/databricks/deploy-databricks-app.sh for
# why incremental sync silently missed this.
#
# Observed in practice, repeatedly, in different ways: `sync --full` can print
# "Initial Sync Complete" and exit 0 while an upload hasn't actually landed —
# an empty workspace folder, a stale webapp/app.py left over from the
# *previous* deploy, or (even after retrying `sync` itself up to 3x) the same
# file still not matching. `apps deploy` then serves outdated or broken code
# with no error at all. Retrying `sync` doesn't reliably fix it — whatever
# local change-detection it uses isn't trustworthy for this. So treat `sync`
# as best-effort bulk transfer only, then force-overwrite this app's actual
# Python entry points with a direct, unambiguous `workspace import`, and
# verify each one byte-for-byte before deploying.
echo "=== Syncing source to ${SOURCE_CODE_PATH} ==="
databricks "${PROFILE_ARGS[@]}" sync --full "${REPO_ROOT}" "${SOURCE_CODE_PATH}"

CRITICAL_FILES=(
  "webapp/app.py"
  "webapp/charts.py"
  "agent/core.py"
  "app.yaml"
)
echo "=== Force-uploading and verifying critical files ==="
for rel_path in "${CRITICAL_FILES[@]}"; do
  databricks "${PROFILE_ARGS[@]}" workspace import \
    "${SOURCE_CODE_PATH}/${rel_path}" \
    --file "$(_native_path "${REPO_ROOT}/${rel_path}")" \
    --format RAW \
    --overwrite >/dev/null
  rm -f "${VERIFY_TMP}"
  if ! databricks "${PROFILE_ARGS[@]}" workspace export \
      "${SOURCE_CODE_PATH}/${rel_path}" --file "$(_native_path "${VERIFY_TMP}")" >/dev/null 2>&1 \
      || ! diff -q "${VERIFY_TMP}" "${REPO_ROOT}/${rel_path}" >/dev/null 2>&1; then
    rm -f "${VERIFY_TMP}"
    echo "FATAL: ${SOURCE_CODE_PATH}/${rel_path} doesn't match local even after a direct import." >&2
    exit 1
  fi
  rm -f "${VERIFY_TMP}"
  echo "  ${rel_path} verified"
done

# --- Deploy -------------------------------------------------------------------
echo "=== Deploying app '${APP_NAME}' from ${SOURCE_CODE_PATH} ==="
databricks "${PROFILE_ARGS[@]}" apps deploy "${APP_NAME}" \
  --source-code-path "${SOURCE_CODE_PATH}"

# --- Report the app URL -------------------------------------------------------
APP_URL="$(databricks "${PROFILE_ARGS[@]}" apps get "${APP_NAME}" \
  --output json 2>/dev/null | grep -o '"url"[^,]*' | head -1 | cut -d'"' -f4 || true)"
echo ""
echo "=== Deployed ==="
if [[ -n "${APP_URL}" ]]; then
  echo "  App URL: ${APP_URL}"
  echo ""
  echo "Open it, then fill in DATABRICKS_HOST / DATABRICKS_TOKEN /"
  echo "MCP_SERVER_URL in the sidebar (see webapp/README.md)."
else
  echo "  Deployed. Get the URL with:"
  echo "    databricks ${PROFILE_ARGS[*]} apps get ${APP_NAME}"
fi
