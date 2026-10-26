"""CSOSA contract spending — searches real federal contract award data.

Queries USAspending.gov's public award-search API
(https://api.usaspending.gov/docs/endpoints), scoped to the Court Services
and Offender Supervision Agency for the District of Columbia (CSOSA,
toptier agency code 9594). No API key is required; the endpoint is public.

Data freshness: USAspending.gov refreshes daily from agency submissions in
the federal procurement systems; very recent awards (last few days) may not
yet appear. Award history is reliably available from fiscal year 2008
(2007-10-01) onward.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP

from example_server.config import settings
from example_server.models import PaginationParams, ResponseFormat
from example_server.utils import UpstreamServiceError

# Keep the agency scope fixed in code, not a tool argument, so the server can
# only ever query CSOSA's own spending data (see utils.py's guidance on
# operator-controlled outbound requests).
CSOSA_TOPTIER_AGENCY_NAME = "Court Services and Offender Supervision Agency"

# Contract award type codes: BPA Call, Purchase Order, Delivery Order,
# Definitive Contract. Excludes grants, loans, and IDV shells.
CONTRACT_AWARD_TYPE_CODES = ["A", "B", "C", "D"]

MAX_RESPONSE_BYTES = 5_000_000
EARLIEST_SUPPORTED_DATE = "2007-10-01"


class ContractSortField(str, Enum):
    """USAspending field to sort results by."""

    AWARD_AMOUNT = "Award Amount"
    START_DATE = "Start Date"
    END_DATE = "End Date"
    RECIPIENT_NAME = "Recipient Name"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


_RESULT_FIELDS = [
    "Award ID",
    "Recipient Name",
    "Award Amount",
    "Start Date",
    "End Date",
    "Description",
    "Contract Award Type",
    "Funding Agency",
    "Place of Performance Country Code",
]


async def _post_json(path: str, body: dict[str, Any]) -> Any:
    """POST to the fixed USAspending API origin and return parsed JSON.

    Mirrors the security posture of `utils.fetch_json` (no redirects, capped
    response size, sanitized errors) but uses POST, which USAspending's
    search endpoints require for their filter payloads.
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
                    # USAspending returns a readable {"detail": "..."} for bad
                    # filters (e.g. limit too high) — safe to surface as-is.
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


def _fiscal_year_range(fiscal_year: int) -> tuple[str, str]:
    """Federal fiscal year N runs 2007-style Oct 1 of (N-1) through Sep 30 of N."""
    return f"{fiscal_year - 1}-10-01", f"{fiscal_year}-09-30"


def register(mcp: FastMCP) -> None:
    """Register the CSOSA contract-spending search tool."""

    @mcp.tool(
        name="csosa_search_contract_awards",
        annotations={
            "title": "Search CSOSA Contract Awards",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def csosa_search_contract_awards(
        query: Annotated[
            str | None,
            "Keyword search across award descriptions and recipient names "
            "(e.g. 'security services', 'drug treatment'). Omit to list all "
            "CSOSA contracts, most recent/largest first.",
        ] = None,
        recipient_name: Annotated[
            str | None,
            "Filter to a specific contractor/recipient name (partial match, "
            "e.g. 'Salvation Army').",
        ] = None,
        fiscal_year: Annotated[
            int | None,
            "Federal fiscal year (Oct 1 of year-1 through Sep 30 of year), "
            "e.g. 2024. Takes precedence over start_date/end_date.",
        ] = None,
        start_date: Annotated[
            str | None,
            f"ISO date (YYYY-MM-DD) for the start of the award period. "
            f"Earliest supported date is {EARLIEST_SUPPORTED_DATE}. Ignored "
            "if fiscal_year is set.",
        ] = None,
        end_date: Annotated[
            str | None,
            "ISO date (YYYY-MM-DD) for the end of the award period. Ignored "
            "if fiscal_year is set.",
        ] = None,
        min_award_amount: Annotated[
            float | None, "Only include awards at or above this dollar amount."
        ] = None,
        max_award_amount: Annotated[
            float | None, "Only include awards at or below this dollar amount."
        ] = None,
        sort_by: Annotated[
            ContractSortField, "Field to sort results by."
        ] = ContractSortField.AWARD_AMOUNT,
        sort_order: Annotated[SortOrder, "Sort direction."] = SortOrder.DESC,
        pagination: PaginationParams | None = None,
        response_format: Annotated[
            ResponseFormat,
            "Return machine-readable JSON (default) or human-readable Markdown.",
        ] = ResponseFormat.JSON,
    ) -> dict[str, Any] | str:
        """Search real federal contract award data for CSOSA.

        Source: USAspending.gov public award-search API, scoped to the Court
        Services and Offender Supervision Agency for the District of Columbia.
        Data is sourced from agency procurement system submissions and
        refreshed daily; see the module docstring for freshness and coverage
        limits.

        Each result includes a `usaspending_url` permalink to the award's
        page on USAspending.gov so answers can cite their source.

        Returns:
            A pagination envelope (JSON) with `items`, `count`, `offset`,
            `has_more`, `next_offset`; or a Markdown summary of the matches.
        """
        pagination = pagination or PaginationParams()
        limit = pagination.limit
        offset = pagination.offset

        if offset % limit != 0:
            return {
                "error": "offset must be a multiple of limit for this tool.",
                "hint": f"Try offset=0 or offset={limit} with limit={limit}.",
            }
        page = offset // limit + 1

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
        if query:
            filters["keywords"] = [query]
        if recipient_name:
            filters["recipient_search_text"] = [recipient_name]
        if fiscal_year:
            fy_start, fy_end = _fiscal_year_range(fiscal_year)
            filters["time_period"] = [{"start_date": fy_start, "end_date": fy_end}]
        elif start_date or end_date:
            filters["time_period"] = [
                {
                    "start_date": start_date or EARLIEST_SUPPORTED_DATE,
                    "end_date": end_date or "2025-09-30",
                }
            ]
        if min_award_amount is not None or max_award_amount is not None:
            amount_filter: dict[str, float] = {}
            if min_award_amount is not None:
                amount_filter["lower_bound"] = min_award_amount
            if max_award_amount is not None:
                amount_filter["upper_bound"] = max_award_amount
            filters["award_amounts"] = [amount_filter]

        body = {
            "filters": filters,
            "fields": _RESULT_FIELDS,
            "page": page,
            "limit": limit,
            "sort": sort_by.value,
            "order": sort_order.value,
        }

        try:
            payload = await _post_json("search/spending_by_award/", body)
        except UpstreamServiceError as exc:
            return {
                "error": str(exc),
                "hint": "Check that min/max amounts and dates are valid, and "
                "that limit is between 1 and 100.",
            }

        raw_items = payload.get("results", [])
        has_more = bool(payload.get("page_metadata", {}).get("hasNext"))
        items = [
            {
                "award_id": r.get("Award ID"),
                "recipient_name": r.get("Recipient Name"),
                "award_amount": r.get("Award Amount"),
                "start_date": r.get("Start Date"),
                "end_date": r.get("End Date"),
                "description": r.get("Description"),
                "contract_award_type": r.get("Contract Award Type"),
                "funding_agency": r.get("Funding Agency"),
                "usaspending_url": (
                    f"https://www.usaspending.gov/award/{r['generated_internal_id']}"
                    if r.get("generated_internal_id")
                    else None
                ),
            }
            for r in raw_items
        ]

        envelope = {
            "source": "USAspending.gov /api/v2/search/spending_by_award/ (CSOSA)",
            "count": len(items),
            "offset": offset,
            "items": items,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        }

        if response_format is ResponseFormat.MARKDOWN:
            title_bits = [b for b in [query, recipient_name] if b]
            title = "# CSOSA contract awards" + (
                f" matching {' / '.join(title_bits)}" if title_bits else ""
            )
            lines = [title, ""]
            for item in items:
                amount = item["award_amount"]
                amount_str = f"${amount:,.2f}" if amount is not None else "n/a"
                lines.append(
                    f"- **{item['recipient_name']}** — {amount_str} "
                    f"({item['start_date']} to {item['end_date']}): "
                    f"{item['description']} [source]({item['usaspending_url']})"
                )
            lines.append("")
            more = (
                f" More available at offset={envelope['next_offset']}."
                if has_more
                else ""
            )
            lines.append(f"_Showing {len(items)} results._{more}")
            return "\n".join(lines)

        return envelope
