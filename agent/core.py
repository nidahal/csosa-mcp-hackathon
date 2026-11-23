"""Shared MCP tool-calling agent loop.

Queries a Databricks-served LLM, lets it call tools on a deployed CSOSA MCP
server over streamable-HTTP, and collects the final answer plus every tool
call made along the way. Used by both the CLI (csosa_agent.py) and the
Streamlit web UI (webapp/app.py) so the two don't drift.
"""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import truststore
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

MAX_TOOL_ROUNDS = 6
DEFAULT_MODEL = "databricks-claude-sonnet-4-5"
SYSTEM_PROMPT = (
    "You are an assistant that answers questions about CSOSA (Court Services "
    "and Offender Supervision Agency) federal contract spending. Use the "
    "available tools to find real award and spending data before answering, "
    "and cite the usaspending_url for any award you mention."
)

OnToolsDiscovered = Callable[[list[str]], None]
OnToolCall = Callable[[int, str, dict[str, Any]], None]


@dataclass
class ToolCallRecord:
    """One tool call the model made, with its arguments and parsed result."""

    name: str
    arguments: dict[str, Any]
    result: Any  # parsed JSON if the tool returned JSON text, else raw text


@dataclass
class AgentRun:
    """The outcome of running one question through the agent loop."""

    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    discovered_tools: list[str] = field(default_factory=list)


def _mcp_tool_to_openai_schema(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


def _parse_tool_result(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def run_agent(
    question: str,
    *,
    host: str,
    token: str,
    mcp_url: str,
    model: str = DEFAULT_MODEL,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
    on_tools_discovered: OnToolsDiscovered | None = None,
    on_tool_call: OnToolCall | None = None,
) -> AgentRun:
    """Run one question through the MCP tool-calling loop end to end."""
    transport = StreamableHttpTransport(
        mcp_url, headers={"Authorization": f"Bearer {token}"}
    )

    # Use the OS trust store (not just certifi) so corporate TLS-inspecting
    # proxies on managed networks validate correctly.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    tool_calls: list[ToolCallRecord] = []

    async with (
        Client(transport) as mcp_client,
        httpx.AsyncClient(
            base_url=host.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
            verify=ssl_context,
        ) as llm_client,
    ):
        tools = await mcp_client.list_tools()
        tool_schemas = [_mcp_tool_to_openai_schema(t) for t in tools]
        tool_names = [t.name for t in tools]
        if on_tools_discovered:
            on_tools_discovered(tool_names)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        for round_num in range(1, max_tool_rounds + 1):
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
            calls = choice.get("tool_calls") or []

            if not calls:
                return AgentRun(
                    answer=(choice.get("content") or "").strip(),
                    tool_calls=tool_calls,
                    discovered_tools=tool_names,
                )

            messages.append(choice)
            for call in calls:
                name = call["function"]["name"]
                args = json.loads(call["function"]["arguments"] or "{}")
                if on_tool_call:
                    on_tool_call(round_num, name, args)
                result = await mcp_client.call_tool(name, args)
                tool_text = "".join(
                    getattr(block, "text", "") for block in result.content
                )
                tool_calls.append(
                    ToolCallRecord(
                        name=name, arguments=args, result=_parse_tool_result(tool_text)
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": tool_text,
                    }
                )

        return AgentRun(
            answer="Stopped after reaching max_tool_rounds without a final answer.",
            tool_calls=tool_calls,
            discovered_tools=tool_names,
        )
