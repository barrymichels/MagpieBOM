import time

import requests

from magpiebom.tracer import Tracer
from magpiebom.types import SearchResult

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

KNOWN_COMPONENT_SITES = [
    "mouser.com",
    "digikey.com",
    "lcsc.com",
    "jlcpcb.com",
    "newark.com",
    "farnell.com",
    "arrow.com",
    "ti.com",
    "st.com",
]


def brave_search(
    part_number: str,
    api_key: str,
    count: int = 5,
    query_template: str = '"{part}" electronic component',
    tracer: Tracer | None = None,
) -> list[SearchResult]:
    """Search Brave for a part number. Returns list of {url, title, description}."""
    query = query_template.format(part=part_number)
    start = time.monotonic()
    try:
        resp = requests.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": count},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=10,
        )
        duration_ms = (time.monotonic() - start) * 1000
        resp.raise_for_status()
        if tracer:
            tracer.http(url=BRAVE_SEARCH_URL, method="GET", status=resp.status_code,
                        headers=dict(resp.headers), body=resp.text,
                        duration_ms=duration_ms, query=query)
    except requests.RequestException as e:
        duration_ms = (time.monotonic() - start) * 1000
        if tracer:
            tracer.http(url=BRAVE_SEARCH_URL, method="GET", status=0,
                        headers={}, body=str(e),
                        duration_ms=duration_ms, query=query)
        return []
    raw_results = resp.json().get("web", {}).get("results", [])
    results = [
        {
            "url": r["url"],
            "title": r.get("title", ""),
            "description": r.get("description", ""),
        }
        for r in raw_results
    ]
    # Sort known component sites to the front
    return sorted(results, key=lambda r: _site_priority(r["url"]))


def _site_priority(url: str) -> int:
    """Lower number = higher priority. Known sites get 0, others get 1."""
    for site in KNOWN_COMPONENT_SITES:
        if site in url:
            return 0
    return 1
