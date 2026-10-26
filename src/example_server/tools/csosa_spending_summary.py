"""CSOSA spending summary — aggregated totals for trend charts and rankings.

Complements csosa_search_contract_awards (individual award records) with
aggregated views: spend by fiscal year (for a time-series chart) or top
recipients/product-service-codes (for a ranked breakdown). Backed by
USAspending.gov's spending_over_time and spending_by_category endpoints
(https://api.usaspending.gov/docs/endpoints). No API key required.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP

from example_server.config import settings
from example_server.utils import UpstreamServiceError

CSOSA_TOPTIER_AGENCY_NAME = "Court Services and Offender Supervision Agency"
CONTRACT_AWARD_TYPE_CODES = ["A", "B", "C", "D"]
MAX_RESPONSE_BYTES = 5_000_000
EARLIEST_SUPPORTED_DATE = "2007-10-01"


class SpendingGroupBy(str, Enum):
    """How to aggregate CSOSA contract spending."""

    FISCAL_YEAR = "fiscal_year"
    RECIPIENT = "recipient"
    PRODUCT_OR_SERVICE = "product_or_service"


async def _post_json(path: str, body: dict[str, Any]) -> Any:
    """POST to the fixed USAspending API origin and return parsed JSON.

    Mirrors the security posture of `utils.fetch_json` (no redirects, capped
    response size, sanitized errors).
    """
    try:
        async with httpx.AsyncClient(
            base_url=settings.usaspending_base_url,
            follow_redirects=False,
            timeout=30.0,
            trust_env=False,
        ) as client:
            async with client.stream("POST", path, json=body) as response:
                if response.status_code == 400:
                    content = await response.aread()
                    detail = json.loads(content).get("detail", "Bad request.")
                    raise UpstreamServiceError(detail)
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise UpstreamServiceError(
                            "Upstream response exceeded the size limit."
                        )
                return json.loads(content)
    except UpstreamServiceError:
        raise
    except httpx.HTTPStatusError as exc:
        raise UpstreamServiceError(
            f"Upstream service returned status {exc.response.status_code}."
        ) from None
    except (httpx.DecodingError, json.JSONDecodeError, UnicodeDecodeError):
        raise UpstreamServiceError("Upstream service returned invalid JSON.") from None
    except httpx.RequestError:
        raise UpstreamServiceError("Upstream service request failed.") from None


def register(mcp: FastMCP) -> None:
    """Register the CSOSA spending-summary tool."""

    @mcp.tool(
        name="csosa_spending_summary",
        annotations={
            "title": "Summarize CSOSA Contract Spending",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def csosa_spending_summary(
        group_by: Annotated[
            SpendingGroupBy,
            "How to aggregate spending: fiscal_year (a time series, good for "
            "a trend chart), recipient (top contractors by total obligated "
            "amount), or product_or_service (top PSC categories of work).",
        ] = SpendingGroupBy.FISCAL_YEAR,
        start_date: Annotated[
            str | None,
            f"ISO date (YYYY-MM-DD). Earliest supported is "
            f"{EARLIEST_SUPPORTED_DATE}. Defaults to the full available range.",
        ] = None,
        end_date: Annotated[str | None, "ISO date (YYYY-MM-DD)."] = None,
        limit: Annotated[
            int,
            "Max rows to return for recipient/product_or_service breakdowns "
            "(ignored for fiscal_year, which always returns every year).",
        ] = 10,
    ) -> dict[str, Any]:
        """Aggregate CSOSA contract spending for summaries and charts.

        Source: USAspending.gov spending_over_time / spending_by_category
        APIs, scoped to CSOSA contracts. Data refreshes daily; see
        csosa_search_contract_awards's module docstring for coverage limits.

        Returns:
            {"group_by": ..., "results": [{"label": ..., "amount": ...}, ...]}
        """
        limit = max(1, min(limit, 50))
        filters: dict[str, Any] = {
            "award_type_codes": CONTRACT_AWARD_TYPE_CODES,
            "agencies": [
                {
                    "type": "awarding",
                    "tier": "toptier",
                    "name": CSOSA_TOPTIER_AGENCY_NAME,
                }
            ],
        }
        if start_date or end_date:
            filters["time_period"] = [
                {
                    "start_date": start_date or EARLIEST_SUPPORTED_DATE,
                    "end_date": end_date or "2025-09-30",
                }
            ]

        try:
            if group_by is SpendingGroupBy.FISCAL_YEAR:
                payload = await _post_json(
                    "search/spending_over_time/",
                    {"filters": filters, "group": "fiscal_year"},
                )
                results = [
                    {
                        "label": row["time_period"]["fiscal_year"],
                        "amount": row.get("aggregated_amount"),
                    }
                    for row in payload.get("results", [])
                ]
            else:
                category = (
                    "recipient"
                    if group_by is SpendingGroupBy.RECIPIENT
                    else "psc"
                )
                payload = await _post_json(
                    f"search/spending_by_category/{category}/",
                    {
                        "filters": filters,
                        "category": category,
                        "limit": limit,
                    },
                )
                results = [
                    {"label": row.get("name"), "amount": row.get("amount")}
                    for row in payload.get("results", [])
                ]
        except UpstreamServiceError as exc:
            return {
                "error": str(exc),
                "hint": "Check that start_date/end_date are valid ISO dates.",
            }

        return {
            "source": "USAspending.gov /api/v2/search/ (CSOSA)",
            "group_by": group_by.value,
            "results": results,
        }
