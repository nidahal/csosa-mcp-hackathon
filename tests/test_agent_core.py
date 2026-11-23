"""Unit tests for the shared MCP tool-calling agent loop (agent/core.py).

Mocks the fastmcp Client and the Databricks model-serving HTTP client so the
loop can be exercised without a live Databricks workspace.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

import core  # noqa: E402


def _content_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def _fake_tool(name: str, description: str = "desc") -> SimpleNamespace:
    return SimpleNamespace(name=name, description=description, input_schema={})


class _FakeMcpClient:
    """Stands in for fastmcp.Client: one tool, records every call_tool call."""

    def __init__(self, tools: list[Any], tool_results: dict[str, str]):
        self._tools = tools
        self._tool_results = tool_results
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self) -> _FakeMcpClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def list_tools(self) -> list[Any]:
        return self._tools

    async def call_tool(self, name: str, args: dict) -> SimpleNamespace:
        self.calls.append((name, args))
        return SimpleNamespace(content=[_content_block(self._tool_results[name])])


class _FakeLlmClient:
    """Stands in for httpx.AsyncClient: returns scripted chat-completion replies."""

    def __init__(self, responses: list[dict]):
        self._responses = responses
        self.post_count = 0

    async def __aenter__(self) -> _FakeLlmClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: dict) -> httpx.Response:
        choice = self._responses[self.post_count]
        self.post_count += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": choice}]},
            request=httpx.Request("POST", "https://example.cloud.databricks.com" + url),
        )


def _patch_clients(
    monkeypatch: pytest.MonkeyPatch,
    mcp_client: _FakeMcpClient,
    llm_client: _FakeLlmClient,
) -> None:
    monkeypatch.setattr(core, "Client", lambda transport: mcp_client)
    monkeypatch.setattr(core.httpx, "AsyncClient", lambda **kwargs: llm_client)


def test_mcp_tool_to_openai_schema() -> None:
    tool = _fake_tool("csosa_spending_summary", "Summarize spend")
    schema = core._mcp_tool_to_openai_schema(tool)
    assert schema == {
        "type": "function",
        "function": {
            "name": "csosa_spending_summary",
            "description": "Summarize spend",
            "parameters": {},
        },
    }


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ("not json", "not json"),
        ("", ""),
    ],
)
def test_parse_tool_result(text: str, expected: Any) -> None:
    assert core._parse_tool_result(text) == expected


@pytest.mark.asyncio
async def test_run_agent_calls_tool_then_returns_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _fake_tool("csosa_spending_summary")
    mcp_client = _FakeMcpClient(
        tools=[tool],
        tool_results={
            "csosa_spending_summary": json.dumps(
                {"group_by": "fiscal_year", "results": [{"label": 2024, "amount": 100}]}
            )
        },
    )
    llm_client = _FakeLlmClient(
        responses=[
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "csosa_spending_summary",
                            "arguments": '{"group_by": "fiscal_year"}',
                        },
                    }
                ],
            },
            {"content": "CSOSA spent $100 in FY2024.", "tool_calls": []},
        ]
    )
    _patch_clients(monkeypatch, mcp_client, llm_client)

    discovered: list[str] = []
    calls: list[tuple[int, str, dict]] = []

    run = await core.run_agent(
        "How much did CSOSA spend?",
        host="https://example.cloud.databricks.com",
        token="fake-token",
        mcp_url="https://example.databricksapps.com/mcp",
        on_tools_discovered=discovered.append,
        on_tool_call=lambda r, n, a: calls.append((r, n, a)),
    )

    assert run.answer == "CSOSA spent $100 in FY2024."
    assert run.discovered_tools == ["csosa_spending_summary"]
    assert discovered == [["csosa_spending_summary"]]
    assert calls == [(1, "csosa_spending_summary", {"group_by": "fiscal_year"})]
    assert len(run.tool_calls) == 1
    recorded = run.tool_calls[0]
    assert recorded.name == "csosa_spending_summary"
    assert recorded.arguments == {"group_by": "fiscal_year"}
    assert recorded.result == {
        "group_by": "fiscal_year",
        "results": [{"label": 2024, "amount": 100}],
    }
    assert mcp_client.calls == [("csosa_spending_summary", {"group_by": "fiscal_year"})]


@pytest.mark.asyncio
async def test_run_agent_answers_directly_with_no_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp_client = _FakeMcpClient(tools=[], tool_results={})
    llm_client = _FakeLlmClient(
        responses=[{"content": "CSOSA is a federal agency.", "tool_calls": []}]
    )
    _patch_clients(monkeypatch, mcp_client, llm_client)

    run = await core.run_agent(
        "What is CSOSA?",
        host="https://example.cloud.databricks.com",
        token="fake-token",
        mcp_url="https://example.databricksapps.com/mcp",
    )

    assert run.answer == "CSOSA is a federal agency."
    assert run.tool_calls == []


@pytest.mark.asyncio
async def test_run_agent_stops_after_max_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _fake_tool("csosa_spending_summary")
    mcp_client = _FakeMcpClient(
        tools=[tool],
        tool_results={"csosa_spending_summary": json.dumps({"results": []})},
    )
    looping_tool_call = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_x",
                "function": {
                    "name": "csosa_spending_summary",
                    "arguments": "{}",
                },
            }
        ],
    }
    llm_client = _FakeLlmClient(responses=[looping_tool_call] * 3)
    _patch_clients(monkeypatch, mcp_client, llm_client)

    run = await core.run_agent(
        "Loop forever",
        host="https://example.cloud.databricks.com",
        token="fake-token",
        mcp_url="https://example.databricksapps.com/mcp",
        max_tool_rounds=3,
    )

    assert run.answer == (
        "Stopped after reaching max_tool_rounds without a final answer."
    )
    assert len(run.tool_calls) == 3
