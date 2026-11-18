"""Gold-question evaluation harness for the deployed CSOSA MCP server.

Runs each QA pair in gold_questions.xml through the same tool-calling loop as
agent/csosa_agent.py against the LIVE deployed server, grades the final
answer with an LLM judge (since dollar/name formatting varies), and writes a
report with per-question results plus a tool-usage summary.

Usage:
    uv sync --group agent
    export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
    export DATABRICKS_TOKEN=<token from `databricks auth token --profile <p>`>
    export MCP_SERVER_URL=https://<app>.databricksapps.com/mcp
    uv run python eval/run_evaluation.py
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import truststore
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

MAX_TOOL_ROUNDS = 8
SYSTEM_PROMPT = (
    "You are an assistant that answers questions about CSOSA (Court Services "
    "and Offender Supervision Agency) federal contract spending. Use the "
    "available tools to find real award data before answering — do not guess "
    "or rely on prior knowledge. Give a short, direct final answer containing "
    "just the requested value."
)
JUDGE_PROMPT_TEMPLATE = """\
You are grading an AI agent's answer to a factual question about federal \
contract spending data.

Question: {question}

Expected answer: {expected}

Agent's answer: {actual}

The agent's answer may be phrased differently, include extra context, or use \
different capitalization/formatting than the expected answer — that is fine. \
Judge only whether the core factual content matches the expected answer.

Respond with exactly one line in the form:
VERDICT: CORRECT | INCORRECT
Then a second line:
REASON: <one short sentence>
"""

GOLD_FILE = Path(__file__).parent / "gold_questions.xml"
REPORT_FILE = Path(__file__).parent / "eval_report.md"


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class QuestionResult:
    question: str
    expected: str
    actual: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    rounds: int = 0
    verdict: str = "UNKNOWN"
    reason: str = ""


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


def load_gold_questions() -> list[tuple[str, str]]:
    root = ET.parse(GOLD_FILE).getroot()
    pairs = []
    for qa in root.findall("qa_pair"):
        question = qa.findtext("question", "").strip()
        answer = qa.findtext("answer", "").strip()
        pairs.append((question, answer))
    return pairs


async def ask_judge(
    llm_client: httpx.AsyncClient, model: str, question: str, expected: str, actual: str
) -> tuple[str, str]:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        question=question, expected=expected, actual=actual
    )
    response = await llm_client.post(
        f"/serving-endpoints/{model}/invocations",
        json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"].get("content", "")
    verdict = "INCORRECT"
    reason = content.strip()
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("VERDICT:"):
            verdict_text = line.split(":", 1)[1].strip().upper()
            verdict = (
                "INCORRECT"
                if "INCORRECT" in verdict_text
                else ("CORRECT" if "CORRECT" in verdict_text else "INCORRECT")
            )
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return verdict, reason


async def run_question(
    mcp_client: Client,
    llm_client: httpx.AsyncClient,
    model: str,
    tool_schemas: list[dict],
    question: str,
    expected: str,
) -> QuestionResult:
    result = QuestionResult(question=question, expected=expected, actual="")
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
        result.rounds = round_num

        if not tool_calls:
            result.actual = (choice.get("content") or "").strip()
            return result

        messages.append(choice)
        for call in tool_calls:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"] or "{}")
            result.tool_calls.append(ToolCall(name=name, args=args))
            try:
                tool_result = await mcp_client.call_tool(name, args)
                tool_text = "".join(
                    getattr(block, "text", "") for block in tool_result.content
                )
            except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
                tool_text = json.dumps({"error": str(exc)})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": tool_text,
                }
            )

    result.actual = "(no final answer — exceeded MAX_TOOL_ROUNDS)"
    return result


async def main() -> None:
    host = _require_env("DATABRICKS_HOST").rstrip("/")
    token = _require_env("DATABRICKS_TOKEN")
    mcp_url = _require_env("MCP_SERVER_URL")
    model = os.environ.get("MODEL", "databricks-claude-sonnet-4-5")

    transport = StreamableHttpTransport(
        mcp_url, headers={"Authorization": f"Bearer {token}"}
    )
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    gold = load_gold_questions()
    results: list[QuestionResult] = []

    async with (
        Client(transport) as mcp_client,
        httpx.AsyncClient(
            base_url=host,
            headers={"Authorization": f"Bearer {token}"},
            timeout=90.0,
            verify=ssl_context,
        ) as llm_client,
    ):
        tools = await mcp_client.list_tools()
        tool_schemas = [_mcp_tool_to_openai_schema(t) for t in tools]
        print(f"Discovered {len(tools)} tool(s): {[t.name for t in tools]}")

        for i, (question, expected) in enumerate(gold, start=1):
            print(f"\n[{i}/{len(gold)}] {question}")
            result = await run_question(
                mcp_client, llm_client, model, tool_schemas, question, expected
            )
            verdict, reason = await ask_judge(
                llm_client, model, question, expected, result.actual
            )
            result.verdict = verdict
            result.reason = reason
            results.append(result)
            print(f"  -> actual: {result.actual!r}")
            print(f"  -> verdict: {verdict} ({reason})")

    write_report(results, model)
    print(f"\nReport written to {REPORT_FILE}")


def write_report(results: list[QuestionResult], model: str) -> None:
    n = len(results)
    n_correct = sum(1 for r in results if r.verdict == "CORRECT")
    total_tool_calls = sum(len(r.tool_calls) for r in results)
    avg_tool_calls = total_tool_calls / n if n else 0.0
    avg_rounds = sum(r.rounds for r in results) / n if n else 0.0

    tool_usage: dict[str, int] = {}
    for r in results:
        for tc in r.tool_calls:
            tool_usage[tc.name] = tool_usage.get(tc.name, 0) + 1

    lines = [
        "# CSOSA MCP Server — Gold Question Evaluation Report",
        "",
        f"Model: `{model}`  |  Questions: {n}  |  Accuracy: {n_correct}/{n} "
        f"({n_correct / n * 100:.0f}%)"
        if n
        else "No questions evaluated.",
        f"Average tool calls per question: {avg_tool_calls:.1f}  |  "
        f"Average rounds per question: {avg_rounds:.1f}",
        "",
        "## Tool usage across all questions",
        "",
        "| Tool | Calls |",
        "|---|---|",
    ]
    for tool_name, count in sorted(tool_usage.items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{tool_name}` | {count} |")
    if not tool_usage:
        lines.append("| _(no tools called)_ | 0 |")

    lines += ["", "## Per-question results", ""]
    for i, r in enumerate(results, start=1):
        status = "✅ PASS" if r.verdict == "CORRECT" else "❌ FAIL"
        lines.append(f"### Q{i}. {status}")
        lines.append("")
        lines.append(f"**Question:** {r.question}")
        lines.append("")
        lines.append(f"**Expected:** {r.expected}")
        lines.append("")
        lines.append(f"**Actual:** {r.actual}")
        lines.append("")
        lines.append(f"**Judge reason:** {r.reason}")
        lines.append("")
        lines.append(f"**Rounds:** {r.rounds}  |  **Tool calls:** {len(r.tool_calls)}")
        lines.append("")
        if r.tool_calls:
            lines.append("<details><summary>Tool call trace</summary>")
            lines.append("")
            for j, tc in enumerate(r.tool_calls, start=1):
                lines.append(f"{j}. `{tc.name}({json.dumps(tc.args)})`")
            lines.append("")
            lines.append("</details>")
        lines.append("")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
