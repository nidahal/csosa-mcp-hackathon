"""CSOSA IDV child awards — orders issued under a parent IDV/schedule contract.

Complements csosa_get_award_details: that tool surfaces a single award's
`parent_idv_award_id` when the award was issued under an Indefinite Delivery
Vehicle (IDV) — a multiple-award schedule or blanket contract that itself has
no fixed value, just a ceiling and a roster of orders placed against it. This
tool takes that parent IDV's award ID and lists the task/delivery orders (or
nested IDVs) issued under it, via USAspending.gov's IDV award-family endpoint
(https://api.usaspending.gov/docs/endpoints). No API key is required.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP

from example_server.config import settings
from example_server.models import PaginationParams
from example_server.utils import UpstreamServiceError

MAX_RESPONSE_BYTES = 5_000_000


class IdvChildType(str, Enum):
    """Which generation of the IDV's award family to list."""

    CHILD_AWARDS = "child_awards"
    GRANDCHILD_AWARDS = "grandchild_awards"
    CHILD_IDVS = "child_idvs"


class IdvSortField(str, Enum):
    """USAspending field to sort IDV child-award results by."""

    PIID = "piid"
    OBLIGATED_AMOUNT = "obligated_amount"
    PERIOD_OF_PERFORMANCE_CURRENT_END_DATE = "period_of_performance_current_end_date"
    LAST_DATE_TO_ORDER = "last_date_to_order"
    AWARDING_AGENCY = "awarding_agency"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


async def _post_json(path: str, body: dict[str, Any]) -> Any:
    """POST to the fixed USAspending API origin and return parsed JSON.

    Mirrors the security posture of the other CSOSA tools (no redirects,
    capped response size, sanitized errors).
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
                if response.status_code == 404:
                    raise UpstreamServiceError(
                        "No IDV found for that idv_award_id."
                    )
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
    """Register the CSOSA IDV child-award listing tool."""

    @mcp.tool(
        name="csosa_list_idv_child_awards",
        annotations={
            "title": "List Orders Under a CSOSA IDV",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def csosa_list_idv_child_awards(
        idv_award_id: Annotated[
            str,
            "The parent IDV's award ID — the `parent_idv_award_id` field "
            "from a csosa_get_award_details result (e.g. "
            "'CONT_IDV_GS07F0256L_4730'). A bare PIID will not resolve.",
        ],
        child_type: Annotated[
            IdvChildType,
            "child_awards: orders placed directly under this IDV. "
            "grandchild_awards: orders placed under child IDVs of this IDV. "
            "child_idvs: nested IDVs issued under this IDV.",
        ] = IdvChildType.CHILD_AWARDS,
        sort_by: Annotated[
            IdvSortField, "Field to sort results by."
        ] = IdvSortField.OBLIGATED_AMOUNT,
        sort_order: Annotated[SortOrder, "Sort direction."] = SortOrder.DESC,
        pagination: PaginationParams | None = None,
    ) -> dict[str, Any]:
        """List task/delivery orders (or nested IDVs) issued under a parent IDV.

        Source: USAspending.gov IDV award-family API. An IDV (Indefinite
        Delivery Vehicle — a GWAC, BPA, or multiple-award schedule contract)
        has no fixed award amount of its own; its obligated dollars live in
        the individual orders placed against it. Use this tool after
        csosa_get_award_details surfaces a `parent_idv_award_id` to see the
        other orders issued under that same vehicle.

        Note: this endpoint is not scoped to CSOSA. Some IDVs (e.g. GSA
        multiple-award schedules) are shared across agencies, so results may
        include orders placed by agencies other than CSOSA — check each
        item's `awarding_agency` before attributing spend to CSOSA.

        Returns:
            A pagination envelope with `items`, `count`, `offset`,
            `has_more`, `next_offset`.
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

        body = {
            "award_id": idv_award_id,
            "type": child_type.value,
            "page": page,
            "limit": limit,
            "sort": sort_by.value,
            "order": sort_order.value,
        }

        try:
            payload = await _post_json("idvs/awards/", body)
        except UpstreamServiceError as exc:
            return {
                "error": str(exc),
                "hint": "idv_award_id must be the long generated award ID "
                "(parent_idv_award_id from csosa_get_award_details), not a "
                "bare PIID.",
            }

        raw_items = payload.get("results", [])
        has_more = bool(payload.get("page_metadata", {}).get("hasNext"))
        items = [
            {
                "award_id": r.get("piid"),
                "award_type": r.get("award_type"),
                "description": r.get("description"),
                "obligated_amount": r.get("obligated_amount"),
                "period_of_performance_start_date": r.get(
                    "period_of_performance_start_date"
                ),
                "period_of_performance_current_end_date": r.get(
                    "period_of_performance_current_end_date"
                ),
                "last_date_to_order": r.get("last_date_to_order"),
                "awarding_agency": r.get("awarding_agency"),
                "funding_agency": r.get("funding_agency"),
                "generated_unique_award_id": r.get("generated_unique_award_id"),
                "usaspending_url": (
                    f"https://www.usaspending.gov/award/{r['generated_unique_award_id']}"
                    if r.get("generated_unique_award_id")
                    else None
                ),
            }
            for r in raw_items
        ]

        return {
            "source": "USAspending.gov /api/v2/idvs/awards/",
            "idv_award_id": idv_award_id,
            "child_type": child_type.value,
            "count": len(items),
            "offset": offset,
            "items": items,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        }
