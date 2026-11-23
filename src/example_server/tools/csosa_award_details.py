"""CSOSA award details — full contract record for a single award.

Complements csosa_search_contract_awards: that tool finds candidate awards,
this one drills into one of them (competition data, NAICS/PSC codes, place
of performance, recipient, parent IDV) via USAspending.gov's award-detail
endpoint (https://api.usaspending.gov/docs/endpoints). No API key required.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP

from example_server.config import settings
from example_server.utils import UpstreamServiceError

MAX_RESPONSE_BYTES = 5_000_000


async def _get_json(path: str) -> Any:
    """GET a path from the fixed USAspending API origin and return parsed JSON.

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
            async with client.stream("GET", path) as response:
                if response.status_code == 404:
                    raise UpstreamServiceError(
                        "No award found for that award_detail_id."
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
    """Register the CSOSA award-detail lookup tool."""

    @mcp.tool(
        name="csosa_get_award_details",
        annotations={
            "title": "Get CSOSA Award Details",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def csosa_get_award_details(
        award_detail_id: Annotated[
            str,
            "The award_detail_id from a csosa_search_contract_awards result "
            "(e.g. 'CONT_AWD_CSOSA13D1044_9594_GS07F0256L_4730'). The short "
            "award_id/PIID alone will not resolve.",
        ],
    ) -> dict[str, Any]:
        """Fetch the full contract record for one CSOSA award.

        Source: USAspending.gov award-detail API. Returns competition data
        (how many offers were received, how it was solicited), NAICS/PSC
        industry codes, place and period of performance, the recipient (and
        its parent company, if any), and the parent IDV/schedule contract
        this award was issued under, if applicable.

        If `parent_idv_award_id` is present, pass it to
        csosa_list_idv_child_awards to see the other orders issued under the
        same IDV.
        """
        try:
            payload = await _get_json(f"awards/{award_detail_id}/")
        except UpstreamServiceError as exc:
            return {
                "error": str(exc),
                "hint": "award_detail_id must be the long generated award ID "
                "returned by csosa_search_contract_awards, not the short PIID.",
            }

        recipient = payload.get("recipient") or {}
        naics = (payload.get("naics_hierarchy") or {}).get("base_code") or {}
        psc = (payload.get("psc_hierarchy") or {}).get("base_code") or {}
        pop = payload.get("period_of_performance") or {}
        place = payload.get("place_of_performance") or {}
        parent_award = payload.get("parent_award") or {}
        contract_data = payload.get("latest_transaction_contract_data") or {}

        return {
            "award_id": payload.get("piid"),
            "description": payload.get("description"),
            "contract_type": payload.get("type_description"),
            "total_obligation": payload.get("total_obligation"),
            "base_and_all_options_value": payload.get("base_and_all_options"),
            "date_signed": payload.get("date_signed"),
            "period_of_performance": {
                "start_date": pop.get("start_date"),
                "end_date": pop.get("end_date"),
            },
            "place_of_performance": {
                "city": place.get("city_name"),
                "state": place.get("state_name"),
                "country": place.get("country_name"),
            },
            "recipient": {
                "name": recipient.get("recipient_name"),
                "uei": recipient.get("recipient_uei"),
                "parent_company": recipient.get("parent_recipient_name"),
                "location": recipient.get("location", {}).get("city_name"),
            },
            "naics_code": naics.get("code"),
            "naics_description": naics.get("description"),
            "psc_code": psc.get("code"),
            "psc_description": psc.get("description"),
            "competition": {
                "extent_competed": contract_data.get("extent_competed"),
                "number_of_offers_received": contract_data.get(
                    "number_of_offers_received"
                ),
                "solicitation_procedures": contract_data.get("solicitation_procedures"),
            },
            "parent_idv_piid": parent_award.get("piid"),
            "parent_idv_award_id": parent_award.get("generated_unique_award_id"),
            "usaspending_url": (
                f"https://www.usaspending.gov/award/{payload['generated_unique_award_id']}"
                if payload.get("generated_unique_award_id")
                else None
            ),
        }
