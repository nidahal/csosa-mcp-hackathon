"""Streamlit web UI for the CSOSA spending assistant.

Wraps the same MCP tool-calling agent loop as agent/csosa_agent.py (shared
code lives in agent/core.py) behind a multi-turn chat: type a natural-
language question, get a narrated answer, an auto-generated chart when the
tool data supports one, and the raw source records with a USAspending.gov
permalink for each one. Ask a follow-up and the conversation continues.

Run:
    uv sync --group webapp
    export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
    export DATABRICKS_TOKEN=<token from `databricks auth token --profile <p>`>
    export MCP_SERVER_URL=https://<app>.databricksapps.com/mcp
    uv run streamlit run webapp/app.py

DATABRICKS_HOST/TOKEN/MCP_SERVER_URL can also be typed into the sidebar at
runtime if not set as env vars. When deployed as a Databricks App, the
sidebar auto-authenticates using the app's own injected service-principal
credentials (DATABRICKS_CLIENT_ID/SECRET) — see _fetch_service_principal_token
— falling back to the manual token field only if that exchange fails.
"""

from __future__ import annotations

import asyncio
import os
import ssl
import sys
from pathlib import Path
from typing import Any

import httpx
import streamlit as st
import truststore

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from charts import ranked_bar, spending_time_series  # noqa: E402

from agent.core import DEFAULT_MODEL, ToolCallRecord, run_agent  # noqa: E402

# Sensible defaults for this specific deployment — still overridable via env
# var or the sidebar. Reduces setup friction to "paste a token" (or nothing,
# once auto-auth is working) rather than "go find three separate values."
DEFAULT_DATABRICKS_HOST = "https://dbc-aae0ba16-8727.cloud.databricks.com"
DEFAULT_MCP_SERVER_URL = (
    "https://csosa-mcp-server-7474654188777746.aws.databricksapps.com/mcp"
)

GROUP_BY_TITLES = {
    "fiscal_year": "CSOSA obligations by fiscal year",
    "recipient": "Top CSOSA recipients by obligated amount",
    "product_or_service": "Top CSOSA product/service categories",
}
SOURCE_LINK_COLUMNS = {
    "usaspending_url": st.column_config.LinkColumn(
        "Source", display_text="View on USAspending.gov"
    )
}


def _fetch_service_principal_token(
    host: str, client_id: str, client_secret: str
) -> str | None:
    """Exchange a Databricks Apps-injected service-principal credential for a
    bearer token via OAuth M2M (client_credentials). Returns None — never
    raises — on any failure, so the caller can fall back to a manual token
    instead of crashing the page (e.g. if the service principal hasn't been
    granted CAN_USE on the MCP app yet)."""
    try:
        ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        response = httpx.post(
            f"{host.rstrip('/')}/oidc/v1/token",
            data={"grant_type": "client_credentials", "scope": "all-apis"},
            auth=(client_id, client_secret),
            timeout=15.0,
            verify=ssl_context,
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception:
        return None


def _chart_for_tool_call(call: ToolCallRecord, budget: float | None):
    """Build a Plotly figure for a tool call's result, or None if it has no
    chartable shape (a table/JSON-only result, or an error)."""
    result = call.result
    if not isinstance(result, dict) or result.get("error"):
        return None

    if call.name == "csosa_spending_summary":
        group_by = result.get("group_by", "fiscal_year")
        results = result.get("results") or []
        if not results:
            return None
        title = GROUP_BY_TITLES.get(group_by, "CSOSA spending summary")
        if group_by == "fiscal_year":
            return spending_time_series(results, title, budget=budget)
        return ranked_bar(results, title, budget=budget)

    if call.name in ("csosa_search_contract_awards", "csosa_search_subawards"):
        items = result.get("items") or []
        amount_key = (
            "award_amount"
            if call.name == "csosa_search_contract_awards"
            else "subaward_amount"
        )
        name_key = (
            "recipient_name"
            if call.name == "csosa_search_contract_awards"
            else "subawardee_name"
        )
        ranked = [i for i in items if i.get(amount_key) is not None][:10]
        if len(ranked) > 1:
            chart_data = [
                {"label": r.get(name_key), "amount": r[amount_key]} for r in ranked
            ]
            return ranked_bar(chart_data, "Top awards by amount", budget=budget)

    return None


def _render_sources(call: ToolCallRecord) -> None:
    """Render a tool call's underlying data: an error, a table, or raw JSON."""
    result = call.result
    if not isinstance(result, dict):
        return
    if error := result.get("error"):
        st.error(f"`{call.name}` failed: {error}")
        return

    if call.name in (
        "csosa_search_contract_awards",
        "csosa_search_subawards",
        "csosa_list_idv_child_awards",
    ):
        items = result.get("items") or []
        if items:
            st.dataframe(items, column_config=SOURCE_LINK_COLUMNS, hide_index=True)
        return

    if call.name == "csosa_get_award_details":
        st.json(result)
        return

    if call.name == "csosa_spending_summary":
        results = result.get("results") or []
        if results:
            st.dataframe(results, hide_index=True)


def _render_turn(question: str, answer: str, tool_calls, budget: float | None) -> None:
    """Render one Q&A turn's assistant content: charts first, then the
    narrated answer, then the raw source data — reused both for the turn
    that just ran and for replaying prior turns in the chat history."""
    charts = [
        fig
        for call in tool_calls
        if (fig := _chart_for_tool_call(call, budget)) is not None
    ]
    if charts:
        st.markdown("### Spending overview")
        for fig in charts:
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Answer")
    st.markdown(answer or "_No answer returned._")

    if tool_calls:
        st.markdown("### Source data")
        for call in tool_calls:
            st.caption(f"`{call.name}`({call.arguments})")
            _render_sources(call)


def _sidebar_connection() -> tuple[str, str, str, str]:
    host_env = os.environ.get("DATABRICKS_HOST", DEFAULT_DATABRICKS_HOST)
    client_id = os.environ.get("DATABRICKS_CLIENT_ID", "")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET", "")
    manual_token_env = os.environ.get("DATABRICKS_TOKEN", "")

    if "_auto_token" not in st.session_state:
        st.session_state._auto_token = (
            _fetch_service_principal_token(host_env, client_id, client_secret)
            if not manual_token_env and client_id and client_secret
            else None
        )
    auto_token = st.session_state._auto_token

    with st.sidebar:
        st.header("Connection")
        if auto_token:
            st.caption(
                "🔑 Auto-authenticated as this app's service principal — "
                "override below for a different identity."
            )
        host = st.text_input("DATABRICKS_HOST", value=host_env)
        token = st.text_input(
            "DATABRICKS_TOKEN",
            value=manual_token_env or auto_token or "",
            type="password",
            help="Auto-filled from this app's injected service-principal "
            "credentials when available."
            if auto_token
            else None,
        )
        mcp_url = st.text_input(
            "MCP_SERVER_URL",
            value=os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL),
        )
        model = st.text_input("MODEL", value=os.environ.get("MODEL", DEFAULT_MODEL))
    return host, token, mcp_url, model


def _sidebar_budget() -> float | None:
    with st.sidebar:
        st.header("Guardrails")
        budget_str = st.text_input(
            "Budget threshold ($, optional)",
            value="",
            help=(
                "USAspending.gov doesn't expose an agency's appropriated "
                "budget, so this isn't live data — set your own ceiling and "
                "any amount above it is highlighted red on the charts below."
            ),
        )
        if not budget_str.strip():
            return None
        try:
            return float(budget_str.replace(",", "").replace("$", ""))
        except ValueError:
            st.error("Budget threshold must be a number.")
            return None


def main() -> None:
    st.set_page_config(
        page_title="CSOSA Spending Assistant", page_icon="📊", layout="wide"
    )
    st.title("CSOSA Spending Assistant")
    st.caption(
        "Ask a question about CSOSA (Court Services and Offender Supervision "
        "Agency) federal contract spending — and ask follow-ups; this is a "
        "conversation. Answers are generated live from USAspending.gov via "
        "MCP tool calls — this view retrieves, aggregates, and explains "
        "public spending data; it never writes back to USAspending.gov or "
        "any external record."
    )

    host, token, mcp_url, model = _sidebar_connection()
    budget = _sidebar_budget()

    if "turns" not in st.session_state:
        st.session_state.turns = []  # [{"question", "answer", "tool_calls"}]
    if "history" not in st.session_state:
        st.session_state.history = None  # agent/core AgentRun.messages

    with st.sidebar:
        if st.button("Clear conversation"):
            st.session_state.turns = []
            st.session_state.history = None
            st.rerun()

    for turn in st.session_state.turns:
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant"):
            _render_turn(turn["question"], turn["answer"], turn["tool_calls"], budget)

    question = st.chat_input(
        "What are CSOSA's three largest security-related contract awards?"
    )
    if not question:
        return
    if not (host and token and mcp_url):
        st.error(
            "Set DATABRICKS_HOST, DATABRICKS_TOKEN, and MCP_SERVER_URL in the "
            "sidebar first."
        )
        return

    with st.chat_message("user"):
        st.markdown(question)

    progress_lines: list[str] = []

    def on_tools_discovered(names: list[str]) -> None:
        progress_lines.append(f"Discovered {len(names)} tool(s): {', '.join(names)}")

    def on_tool_call(round_num: int, name: str, args: dict[str, Any]) -> None:
        progress_lines.append(f"Round {round_num}: called `{name}`({args})")

    with st.chat_message("assistant"):
        with st.status("Querying the CSOSA MCP server...", expanded=True) as status:
            try:
                run = asyncio.run(
                    run_agent(
                        question,
                        host=host,
                        token=token,
                        mcp_url=mcp_url,
                        model=model,
                        history=st.session_state.history,
                        on_tools_discovered=on_tools_discovered,
                        on_tool_call=on_tool_call,
                    )
                )
            except Exception as exc:  # surface upstream/auth errors directly
                status.update(label="Failed", state="error")
                st.error(str(exc))
                return
            for line in progress_lines:
                st.write(line)
            status.update(label="Done", state="complete")

        _render_turn(question, run.answer, run.tool_calls, budget)

    st.session_state.history = run.messages
    st.session_state.turns.append(
        {"question": question, "answer": run.answer, "tool_calls": run.tool_calls}
    )


if __name__ == "__main__":
    main()
