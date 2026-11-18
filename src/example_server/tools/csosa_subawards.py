"""CSOSA sub-awards — subcontractors paid through a CSOSA prime contract.

Complements csosa_search_contract_awards (prime awards only): a prime
contractor can pass part of its CSOSA-funded work to subcontractors, and that
money is invisible in prime-award data. This tool queries the same
USAspending.gov award-search endpoint with `subawards=true`
(https://api.usaspending.gov/docs/endpoints), which switches the result shape
from prime awards to sub-award records while reusing the same agency/time/
keyword filters. No API key is required.
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

CSOSA_TOPTIER_AGENCY_NAME = "Court Services and Offender Supervision Agency"
CONTRACT_AWARD_TYPE_CODES = ["A", "B", "C", "D"]

MAX_RESPONSE_BYTES = 5_000_000
EARLIEST_SUPPORTED_DATE = "2007-10-01"

_RESULT_FIELDS = [
    "Sub-Award ID",
    "Sub-Awardee Name",
    "Sub-Award Amount",
    "Sub-Award Date",
    "Sub-Award Description",
    "Sub-Recipient Location",
    "Prime Award ID",
    "Prime Recipient Name",
    "Awarding Agency",
]


class SubawardSortField(str, Enum):
    """USAspending field to sort sub-award results by."""

    SUB_AWARD_AMOUNT = "Sub-Award Amount"
    SUB_AWARD_DATE = "Sub-Award Date"
    SUB_AWARDEE_NAME = "Sub-Awardee Name"
    PRIME_RECIPIENT_NAME = "Prime Recipient Name"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


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
    """Register the CSOSA sub-award search tool."""

    @mcp.tool(
        name="csosa_search_subawards",
        annotations={
            "title": "Search CSOSA Sub-Awards",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def csosa_search_subawards(
        query: Annotated[
            str | None,
            "Keyword search across sub-award descriptions (e.g. 'janitorial', "
            "'transportation'). Omit to list all CSOSA sub-awards, largest "
            "first.",
        ] = None,
        subawardee_name: Annotated[
            str | None,
            "Filter to a specific subcontractor/sub-recipient name (partial "
            "match, e.g. 'Acme Facilities').",
        ] = None,
        fiscal_year: Annotated[
            int | None,
            "Federal fiscal year (Oct 1 of year-1 through Sep 30 of year), "
            "e.g. 2024. Takes precedence over start_date/end_date.",
        ] = None,
        start_date: Annotated[
            str | None,
            f"ISO date (YYYY-MM-DD) for the start of the sub-award period. "
            f"Earliest supported date is {EARLIEST_SUPPORTED_DATE}. Ignored "
            "if fiscal_year is set.",
        ] = None,
        end_date: Annotated[
            str | None,
            "ISO date (YYYY-MM-DD) for the end of the sub-award period. "
            "Ignored if fiscal_year is set.",
        ] = None,
        sort_by: Annotated[
            SubawardSortField, "Field to sort results by."
        ] = SubawardSortField.SUB_AWARD_AMOUNT,
        sort_order: Annotated[SortOrder, "Sort direction."] = SortOrder.DESC,
        pagination: PaginationParams | None = None,
        response_format: Annotated[
            ResponseFormat,
            "Return machine-readable JSON (default) or human-readable Markdown.",
        ] = ResponseFormat.JSON,
    ) -> dict[str, Any] | str:
        """Search sub-award (subcontractor) records tied to CSOSA prime contracts.

        Source: USAspending.gov award-search API in sub-award mode, scoped to
        prime contracts awarded by the Court Services and Offender Supervision
        Agency. Each result is money a CSOSA prime contractor passed to a
        subcontractor, not a direct CSOSA obligation — use
        csosa_search_contract_awards for prime-award totals. Data is sourced
        from prime-contractor subcontract reporting (FSRS) and refreshed
        daily; coverage is sparser than prime-award data because sub-award
        reporting is not universal.

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
        if subawardee_name:
            filters["recipient_search_text"] = [subawardee_name]
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

        body = {
            "subawards": True,
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
                "hint": "Check that dates are valid and that limit is "
                "between 1 and 100.",
            }

        raw_items = payload.get("results", [])
        has_more = bool(payload.get("page_metadata", {}).get("hasNext"))
        items = [
            {
                "subaward_id": r.get("Sub-Award ID"),
                "subawardee_name": r.get("Sub-Awardee Name"),
                "subaward_amount": r.get("Sub-Award Amount"),
                "subaward_date": r.get("Sub-Award Date"),
                "description": r.get("Sub-Award Description"),
                "subrecipient_location": r.get("Sub-Recipient Location"),
                "prime_award_id": r.get("Prime Award ID"),
                "prime_recipient_name": r.get("Prime Recipient Name"),
                "awarding_agency": r.get("Awarding Agency"),
            }
            for r in raw_items
        ]

        envelope = {
            "source": "USAspending.gov /api/v2/search/spending_by_award/ "
            "(subawards=true, CSOSA)",
            "count": len(items),
            "offset": offset,
            "items": items,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        }

        if response_format is ResponseFormat.MARKDOWN:
            title_bits = [b for b in [query, subawardee_name] if b]
            title = "# CSOSA sub-awards" + (
                f" matching {' / '.join(title_bits)}" if title_bits else ""
            )
            lines = [title, ""]
            for item in items:
                amount = item["subaward_amount"]
                amount_str = f"${amount:,.2f}" if amount is not None else "n/a"
                lines.append(
                    f"- **{item['subawardee_name']}** — {amount_str} "
                    f"({item['subaward_date']}), via prime "
                    f"**{item['prime_recipient_name']}** "
                    f"({item['prime_award_id']}): {item['description']}"
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
