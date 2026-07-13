"""RentCast API fetchers for post-fire sales + active sale listings.

RentCast (https://developers.rentcast.io) is a *supplementary*, paid source —
unlike the public ArcGIS feeds it needs an `X-Api-Key` header (``RENTCAST_API_KEY``).
Billing is one credit per request regardless of how many records a page returns
(up to 500), so both fetchers query the whole burn area by lat/long + radius and
we join the results back to parcels locally — never one request per parcel.

- ``fetch_rentcast_properties`` → GET /properties, filtered by ``saleDateRange``
  (days since last sold) so it returns only recently-sold homes plus their owner.
- ``fetch_rentcast_sale_listings`` → GET /listings/sale (status=Active) for every
  currently-listed home in the area.

Both paginate at 500/page via ``offset`` and stop on a short page. A 404 from
RentCast means "no matching records" and is treated as an empty result, not an
error.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .schemas import (
    RentCastListing,
    RentCastProperty,
    validate_rentcast_listings,
    validate_rentcast_properties,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.rentcast.io/v1"
_PROPERTIES_PATH = "/properties"
_SALE_LISTINGS_PATH = "/listings/sale"

_PAGE_SIZE = 500
_REQUEST_TIMEOUT = 60.0
# Safety cap so a runaway area/filter can never page the whole county and blow
# the request budget. 40 pages = 20k records — far above the burn area's real
# sold/listing volume. Hitting it is logged, never silently truncated.
_MAX_PAGES = 40


class RentCastError(RuntimeError):
    """Raised when a RentCast endpoint cannot be fetched after retries."""


class _TransientRentCastError(RuntimeError):
    """Internal: signals a RentCast error worth retrying."""


def fetch_rentcast_properties(
    latitude: float,
    longitude: float,
    radius: float,
    *,
    sale_date_range: int,
) -> list[RentCastProperty]:
    """Fetch properties in the area last sold within ``sale_date_range`` days.

    Each record carries the current owner (the post-fire buyer), ``lastSaleDate``,
    ``lastSalePrice`` and ``assessorID`` for the local join.
    """
    params = {
        "latitude": _fmt(latitude),
        "longitude": _fmt(longitude),
        "radius": _fmt(radius),
        "saleDateRange": str(int(sale_date_range)),
    }
    raw = _fetch_paginated(_PROPERTIES_PATH, params)
    return validate_rentcast_properties(raw)


def fetch_rentcast_sale_listings(
    latitude: float,
    longitude: float,
    radius: float,
    *,
    status: str = "Active",
) -> list[RentCastListing]:
    """Fetch sale listings in the area (Active by default), with listing dates."""
    params = {
        "latitude": _fmt(latitude),
        "longitude": _fmt(longitude),
        "radius": _fmt(radius),
        "status": status,
    }
    raw = _fetch_paginated(_SALE_LISTINGS_PATH, params)
    return validate_rentcast_listings(raw)


def _fetch_paginated(path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    key = os.environ.get("RENTCAST_API_KEY")
    if not key:
        raise RentCastError("RENTCAST_API_KEY not set; cannot query RentCast")

    url = f"{_BASE_URL}{path}"
    headers = {"X-Api-Key": key, "Accept": "application/json"}
    results: list[dict[str, Any]] = []
    offset = 0

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        for page_num in range(_MAX_PAGES):
            page_params = {
                **params,
                "limit": str(_PAGE_SIZE),
                "offset": str(offset),
            }
            try:
                page = _fetch_page(client, url, page_params, headers)
            except RetryError as exc:
                raise RentCastError(f"failed to fetch {url} after retries") from exc

            results.extend(page)
            if len(page) < _PAGE_SIZE:
                return results
            offset += _PAGE_SIZE
            if page_num == _MAX_PAGES - 1:
                logger.warning(
                    "RentCast %s hit the %d-page cap (%d records); "
                    "results may be truncated",
                    path,
                    _MAX_PAGES,
                    len(results),
                )
    return results


def _fetch_page(
    client: httpx.Client,
    url: str,
    params: dict[str, str],
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    @retry(
        reraise=False,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=3, exp_base=4, min=3, max=48),
        retry=retry_if_exception_type((httpx.HTTPError, _TransientRentCastError)),
    )
    def _do() -> list[dict[str, Any]]:
        resp = client.get(url, params=params, headers=headers)
        # RentCast returns 404 with a JSON status body when a query matches no
        # records — a normal empty result for a small burn area, not an error.
        if resp.status_code == 404:
            return []
        if resp.status_code in (429, 500, 502, 503, 504):
            raise _TransientRentCastError(
                f"transient {resp.status_code}: {resp.text[:200]}"
            )
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list):
            return body
        raise RentCastError(f"unexpected RentCast response shape: {body!r}"[:200])

    return _do()


def _fmt(value: float) -> str:
    return f"{value:.6f}"
