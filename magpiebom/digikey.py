# magpiebom/digikey.py
import time

import requests

from magpiebom.tracer import Tracer

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"


def _get_token(client_id: str, client_secret: str, tracer: Tracer | None = None) -> str:
    """Exchange client credentials for a bearer token."""
    start = time.monotonic()
    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        duration_ms = (time.monotonic() - start) * 1000
        resp.raise_for_status()
        if tracer:
            tracer.http(url=TOKEN_URL, method="POST", status=resp.status_code,
                        headers=dict(resp.headers), body=resp.text,
                        duration_ms=duration_ms)
    except requests.RequestException as e:
        duration_ms = (time.monotonic() - start) * 1000
        if tracer:
            tracer.http(url=TOKEN_URL, method="POST",
                        status=getattr(getattr(e, 'response', None), 'status_code', 0) or 0,
                        headers={}, body=str(e), duration_ms=duration_ms)
        raise
    return resp.json()["access_token"]


def digikey_search(part_number: str, client_id: str, client_secret: str, tracer: Tracer | None = None) -> dict | None:
    """Search DigiKey for a part. Returns {description, image_url} or None."""
    token = _get_token(client_id, client_secret, tracer=tracer)

    start = time.monotonic()
    try:
        resp = requests.post(
            SEARCH_URL,
            json={"Keywords": part_number, "RecordCount": 10},
            headers={
                "Authorization": f"Bearer {token}",
                "X-DIGIKEY-Client-Id": client_id,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15,
        )
        duration_ms = (time.monotonic() - start) * 1000
        resp.raise_for_status()
        data = resp.json()
        if tracer:
            tracer.http(url=SEARCH_URL, method="POST", status=resp.status_code,
                        headers=dict(resp.headers), body=resp.text,
                        duration_ms=duration_ms)
    except requests.RequestException as e:
        duration_ms = (time.monotonic() - start) * 1000
        if tracer:
            tracer.http(url=SEARCH_URL, method="POST",
                        status=getattr(getattr(e, 'response', None), 'status_code', 0) or 0,
                        headers={}, body=str(e), duration_ms=duration_ms)
        raise

    products = data.get("Products", [])
    if not products:
        return None

    # Find exact match first, fall back to first result
    part = None
    for p in products:
        if p.get("ManufacturerProductNumber", "").upper() == part_number.upper():
            part = p
            break
    if part is None:
        part = products[0]

    image_url = part.get("PhotoUrl", "")
    desc = part.get("Description", {})
    description = desc.get("ProductDescription", "") if isinstance(desc, dict) else str(desc)
    datasheet_url = part.get("DatasheetUrl", "")

    if not image_url:
        return None

    return {
        "description": description,
        "image_url": image_url,
        "datasheet_url": datasheet_url or None,
        "manufacturer": part.get("Manufacturer", {}).get("Name", ""),
        "digikey_pn": part.get("DigiKeyProductNumber", ""),
    }
