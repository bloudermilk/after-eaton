"""Paginated ArcGIS FeatureServer fetcher with retry logic."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Raised when an ArcGIS source cannot be fetched after retries."""


_PAGE_SIZE = 1000
_REQUEST_TIMEOUT = 60.0


def fetch_all(
    url: str,
    params: dict[str, str],
    *,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Paginate a FeatureServer query endpoint and return all features.

    Each returned dict is the feature's flat attributes merged with a
    `_geometry` key carrying the raw ArcGIS geometry dict. Features with
    null geometry are dropped and logged.
    """
    base_params: dict[str, str] = {
        "where": "1=1",
        "outFields": "*",
        "f": "json",
        "returnGeometry": "true",
        "outSR": "4326",
        **params,
    }

    results: list[dict[str, Any]] = []
    offset = 0

    with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
        while True:
            page_params = {
                **base_params,
                "resultOffset": str(offset),
                "resultRecordCount": str(_PAGE_SIZE),
            }
            try:
                page = _fetch_page(client, url, page_params, max_retries=max_retries)
            except RetryError as exc:
                raise SourceError(
                    f"failed to fetch {url} after {max_retries} retries"
                ) from exc

            features = page.get("features", [])
            for feat in features:
                attrs = feat.get("attributes") or {}
                geom = feat.get("geometry")
                if geom is None:
                    logger.warning(
                        "dropping feature with null geometry (offset=%d, attrs=%s)",
                        offset,
                        attrs,
                    )
                    continue
                record: dict[str, Any] = dict(attrs)
                record["_geometry"] = geom
                results.append(record)

            if not page.get("exceededTransferLimit") or not features:
                break
            offset += len(features)

    return results


def _fetch_page(
    client: httpx.Client,
    url: str,
    params: dict[str, str],
    *,
    max_retries: int,
) -> dict[str, Any]:
    @retry(
        reraise=False,
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=30, exp_base=4, min=30, max=480),
        retry=retry_if_exception_type((httpx.HTTPError, _TransientArcGISError)),
    )
    def _do() -> dict[str, Any]:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            err = body["error"]
            code = err.get("code")
            message = err.get("message", "unknown ArcGIS error")
            if code in (500, 504, 429):
                raise _TransientArcGISError(f"{code}: {message}")
            raise SourceError(f"ArcGIS error {code}: {message}")
        return body  # type: ignore[no-any-return]

    return _do()


class _TransientArcGISError(RuntimeError):
    """Internal: signals an ArcGIS error worth retrying."""
