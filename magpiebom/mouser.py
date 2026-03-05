# magpiebom/mouser.py
import time

import requests

from magpiebom.tracer import Tracer

MOUSER_API_URL = "https://api.mouser.com/api/v1/search/partnumber"


def mouser_search(part_number: str, api_key: str, tracer: Tracer | None = None) -> dict | None:
    """Search Mouser for a part. Returns {description, image_url} or None."""
    start = time.monotonic()
    resp = requests.post(
        MOUSER_API_URL,
        params={"apiKey": api_key},
        json={
            "SearchByPartRequest": {
                "mouserPartNumber": part_number,
                "partSearchOptions": "None",
            }
        },
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=15,
    )
    duration_ms = (time.monotonic() - start) * 1000
    resp.raise_for_status()
    data = resp.json()
    if tracer:
        tracer.http(url=MOUSER_API_URL, method="POST", status=resp.status_code,
                    headers=dict(resp.headers), body=resp.text,
                    duration_ms=duration_ms)

    parts = data.get("SearchResults", {}).get("Parts", [])
    if not parts:
        return None

    # Find exact match first, fall back to first result
    part = None
    for p in parts:
        if p.get("ManufacturerPartNumber", "").upper() == part_number.upper():
            part = p
            break
    if part is None:
        part = parts[0]

    image_url = part.get("ImagePath", "")
    description = part.get("Description", "")
    datasheet_url = part.get("DataSheetUrl", "")

    if not image_url:
        return None

    # Mouser sometimes returns protocol-relative URLs
    if image_url.startswith("//"):
        image_url = "https:" + image_url

    return {
        "description": description,
        "image_url": image_url,
        "datasheet_url": datasheet_url or None,
        "manufacturer": part.get("Manufacturer", ""),
        "mouser_pn": part.get("MouserPartNumber", ""),
        "product_detail_url": part.get("ProductDetailUrl", ""),
    }
