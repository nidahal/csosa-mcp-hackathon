"""Streamlit web UI for the CSOSA spending assistant.

Wraps the same MCP tool-calling agent loop as agent/csosa_agent.py (shared
code lives in agent/core.py) behind a page where a user types a natural-
language question and gets back a narrated answer, an auto-generated chart
when the tool data supports one, and the raw source records with a
USAspending.gov permalink for each one.

Run:
    uv sync --group webapp
    export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
    export DATABRICKS_TOKEN=<token from `databricks auth token --profile <p>`>
    export MCP_SERVER_URL=https://<app>.databricksapps.com/mcp
    uv run streamlit run webapp/app.py

DATABRICKS_HOST/TOKEN/MCP_SERVER_URL can also be typed into the sidebar at
runtime if not set as env vars.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from charts import ranked_bar, spending_time_series  # noqa: E402

from agent.core import DEFAULT_MODEL, ToolCallRecord, run_agent  # noqa: E402

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


def _sidebar_connection() -> tuple[str, str, str, str]:
    with st.sidebar:
        st.header("Connection")
        host = st.text_input(
            "DATABRICKS_HOST", value=os.environ.get("DATABRICKS_HOST", "")
        )
        token = st.text_input(
            "DATABRICKS_TOKEN",
            value=os.environ.get("DATABRICKS_TOKEN", ""),
            type="password",
        )
        mcp_url = st.text_input(
            "MCP_SERVER_URL", value=os.environ.get("MCP_SERVER_URL", "")
        )
        model = st.text_input(
            "MODEL", value=os.environ.get("MODEL", DEFAULT_MODEL)
        )
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
        "Agency) federal contract spending. Answers are generated live from "
        "USAspending.gov via MCP tool calls — this view retrieves, "
        "aggregates, and explains public spending data; it never writes "
        "back to USAspending.gov or any external record."
    )

    host, token, mcp_url, model = _sidebar_connection()
    budget = _sidebar_budget()

    question = st.text_input(
        "Your question",
        placeholder="What are CSOSA's three largest security-related contract awards?",
    )
    ask = st.button("Ask", type="primary")

    if not ask:
        return
    if not (host and token and mcp_url):
        st.error(
            "Set DATABRICKS_HOST, DATABRICKS_TOKEN, and MCP_SERVER_URL in the "
            "sidebar first."
        )
        return
    if not question.strip():
        st.error("Type a question first.")
        return

    progress_lines: list[str] = []

    def on_tools_discovered(names: list[str]) -> None:
        progress_lines.append(f"Discovered {len(names)} tool(s): {', '.join(names)}")

    def on_tool_call(round_num: int, name: str, args: dict[str, Any]) -> None:
        progress_lines.append(f"Round {round_num}: called `{name}`({args})")

    with st.status("Querying the CSOSA MCP server...", expanded=True) as status:
        try:
            run = asyncio.run(
                run_agent(
                    question,
                    host=host,
                    token=token,
                    mcp_url=mcp_url,
                    model=model,
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

    charts = [
        fig
        for call in run.tool_calls
        if (fig := _chart_for_tool_call(call, budget)) is not None
    ]
    if charts:
        st.markdown("### Spending overview")
        for fig in charts:
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Answer")
    st.markdown(run.answer or "_No answer returned._")

    if run.tool_calls:
        st.markdown("### Source data")
        for call in run.tool_calls:
            st.caption(f"`{call.name}`({call.arguments})")
            _render_sources(call)


if __name__ == "__main__":
    main()
