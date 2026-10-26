"""Minimal MCP-using agent: queries a Databricks-served LLM, lets it call
tools on the deployed CSOSA MCP server, and prints the final answer.

This is the "build an agent and test the custom tool" milestone deliverable.
It talks to the already-deployed server over streamable-HTTP (see
deploy/databricks/) rather than stdio, so it exercises the same path a real
client (watsonx Orchestrate, Databricks Playground) would use.

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
import json
import os
import ssl
import sys

import httpx
import truststore
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

MAX_TOOL_ROUNDS = 6
SYSTEM_PROMPT = (
    "You are an assistant that answers questions about CSOSA (Court Services "
    "and Offender Supervision Agency) federal contract spending. Use the "
    "csosa_search_contract_awards tool to find real award data before "
    "answering, and cite the usaspending_url for any award you mention."
)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _mcp_tool_to_openai_schema(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


async def run_agent(question: str) -> None:
    host = _require_env("DATABRICKS_HOST").rstrip("/")
    token = _require_env("DATABRICKS_TOKEN")
    mcp_url = _require_env("MCP_SERVER_URL")
    model = os.environ.get("MODEL", "databricks-claude-sonnet-4-5")

    transport = StreamableHttpTransport(
        mcp_url, headers={"Authorization": f"Bearer {token}"}
    )

    # Use the OS trust store (not just certifi) so corporate TLS-inspecting
    # proxies on managed networks validate correctly.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    async with Client(transport) as mcp_client, httpx.AsyncClient(
        base_url=host,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
        verify=ssl_context,
    ) as llm_client:
        tools = await mcp_client.list_tools()
        tool_schemas = [_mcp_tool_to_openai_schema(t) for t in tools]
        print(f"Discovered {len(tools)} tool(s) on the MCP server: "
              f"{[t.name for t in tools]}")

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            response = await llm_client.post(
                f"/serving-endpoints/{model}/invocations",
                json={
                    "messages": messages,
                    "tools": tool_schemas,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]["message"]
            tool_calls = choice.get("tool_calls") or []

            if not tool_calls:
                print("\n=== Final answer ===")
                print(choice.get("content", "").strip())
                return

            messages.append(choice)
            print(f"\n[round {round_num}] model requested "
                  f"{len(tool_calls)} tool call(s)")
            for call in tool_calls:
                name = call["function"]["name"]
                args = json.loads(call["function"]["arguments"] or "{}")
                print(f"  -> {name}({args})")
                result = await mcp_client.call_tool(name, args)
                tool_text = "".join(
                    getattr(block, "text", "") for block in result.content
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": tool_text,
                    }
                )

        print("Stopped after reaching MAX_TOOL_ROUNDS without a final answer.")


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or (
        "What are CSOSA's three largest security-related contract awards?"
    )
    asyncio.run(run_agent(query))
