"""Minimal MCP-using agent: queries a Databricks-served LLM, lets it call
tools on the deployed CSOSA MCP server, and prints the final answer.

This is the "build an agent and test the custom tool" milestone deliverable.
It talks to the already-deployed server over streamable-HTTP (see
deploy/databricks/) rather than stdio, so it exercises the same path a real
client (watsonx Orchestrate, Databricks Playground) would use. The agent
loop itself lives in agent/core.py, shared with the Streamlit web UI
(webapp/app.py).

Usage:
    uv sync --group agent
    export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
    export DATABRICKS_TOKEN=<token from `databricks auth token --profile <p>`>
    export MCP_SERVER_URL=https://<app>.databricksapps.com/mcp
    uv run python agent/csosa_agent.py "What are CSOSA's largest security contracts?"

Env vars:
    DATABRICKS_HOST   workspace URL (required)
    DATABRICKS_TOKEN  bearer token good for both the model endpoint and the
                       OAuth-gated MCP app (required)
    MCP_SERVER_URL    the deployed server's /mcp endpoint (required)
    MODEL             serving-endpoint name (default: databricks-claude-sonnet-4-5)
"""

from __future__ import annotations

import asyncio
import os
import sys

from core import DEFAULT_MODEL, run_agent


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _print_tools_discovered(names: list[str]) -> None:
    print(f"Discovered {len(names)} tool(s) on the MCP server: {names}")


def _print_tool_call(round_num: int, name: str, args: dict) -> None:
    print(f"\n[round {round_num}] model requested tool call")
    print(f"  -> {name}({args})")


async def main(question: str) -> None:
    host = _require_env("DATABRICKS_HOST")
    token = _require_env("DATABRICKS_TOKEN")
    mcp_url = _require_env("MCP_SERVER_URL")
    model = os.environ.get("MODEL", DEFAULT_MODEL)

    run = await run_agent(
        question,
        host=host,
        token=token,
        mcp_url=mcp_url,
        model=model,
        on_tools_discovered=_print_tools_discovered,
        on_tool_call=_print_tool_call,
    )

    print("\n=== Final answer ===")
    print(run.answer)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or (
        "What are CSOSA's three largest security-related contract awards?"
    )
    asyncio.run(main(query))
