import re
import time
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

from magpiebom.constants import SKIP_PDF_PATTERNS
from magpiebom.tracer import Tracer

# Image dimension attributes below this are considered icons/logos
MIN_IMAGE_DIMENSION = 100
MAX_IMAGES_PER_PAGE = 3
# Aspect ratios beyond this are likely banners
MAX_ASPECT_RATIO = 4.0
# File extensions that are never product images
SKIP_EXTENSIONS = {".svg", ".ico", ".gif"}
# URL path segments that indicate non-product images
SKIP_URL_PATTERNS = ["advertising", "banner", "logo", "icon", "sprite", "favicon"]


MAX_PARAGRAPHS = 5


def scrape_page(url: str, timeout: int = 10, tracer: Tracer | None = None) -> dict:
    """Fetch a URL and extract text signals + image URLs."""
    start = time.monotonic()
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "MagpieBOM/0.1"})
    duration_ms = (time.monotonic() - start) * 1000
    resp.raise_for_status()
    if tracer:
        tracer.http(url=url, method="GET", status=resp.status_code,
                    headers=dict(resp.headers), body=resp.text,
                    duration_ms=duration_ms)
    result = extract_page_info(resp.text, url)
    if tracer:
        tracer.detail(f"Scraped {url}",
                      images=len(result["image_urls"]),
                      datasheets=len(result["datasheet_urls"]),
                      has_description=bool(result["text_signals"]["meta_description"]))
    return result


def extract_page_info(html: str, base_url: str) -> dict:
    """Parse HTML and return {text_signals, image_urls, datasheet_urls}."""
    soup = BeautifulSoup(html, "lxml")
    text_signals = _extract_text_signals(soup, base_url)
    image_urls = _extract_images(soup, base_url)
    datasheet_urls = _extract_datasheets(soup, html, base_url)
    return {"text_signals": text_signals, "image_urls": image_urls, "datasheet_urls": datasheet_urls}


def _extract_text_signals(soup: BeautifulSoup, url: str) -> dict:
    """Extract structured text signals from a page for LLM description extraction."""
    # Title
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    # Meta description
    meta_desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content", "").strip():
        meta_desc = meta["content"].strip()
    if not meta_desc:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content", "").strip():
            meta_desc = og["content"].strip()

    # Meta keywords
    meta_kw = ""
    kw_tag = soup.find("meta", attrs={"name": "keywords"})
    if kw_tag and kw_tag.get("content", "").strip():
        meta_kw = kw_tag["content"].strip()

    # URL path (decoded, useful for sites that encode category info)
    url_path = unquote(urlparse(url).path)

    # First substantial paragraphs
    paragraphs = []
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 30:
            paragraphs.append(text)
            if len(paragraphs) >= MAX_PARAGRAPHS:
                break

    url_category = _extract_category_from_url(url)

    return {
        "title": title,
        "meta_description": meta_desc,
        "meta_keywords": meta_kw,
        "url_path": url_path,
        "url_category": url_category,
        "paragraphs": paragraphs,
    }


def _extract_category_from_url(url: str) -> str:
    """Extract a human-readable component category from URL path segments.

    E.g. '/product-detail/Pin-Header-Female-Header_XFCN-PM254V-12-10P-H85_C492399.html'
    → 'Pin Header Female Header'
    """
    path = unquote(urlparse(url).path)
    # Look for the last meaningful path segment (before .html etc)
    segments = [s for s in path.split("/") if s and not s.startswith(".")]
    if not segments:
        return ""
    # Use the most descriptive segment — often the last or second-to-last
    # Try to find a segment with category-like hyphenated words
    for seg in reversed(segments):
        # Strip file extensions
        seg = re.sub(r'\.[a-zA-Z]{2,5}$', '', seg)
        # LCSC-style: "Pin-Header-Female-Header_XFCN-PM254V..."
        if "_" in seg:
            category_part = seg.split("_")[0]
            words = category_part.replace("-", " ").strip()
            if len(words) > 3 and not words.isdigit():
                return words
        # Generic hyphenated: "pin-header-female-header"
        if "-" in seg and len(seg) > 10:
            words = seg.replace("-", " ").strip()
            # Skip segments that look like part numbers (mostly alphanumeric with few spaces)
            if " " in words and not re.match(r'^[A-Z0-9 ]+$', words.upper()):
                return words
    return ""


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract and filter image URLs from HTML."""
    candidates = []
    # Collect og:image first (high priority)
    og_img = soup.find("meta", attrs={"property": "og:image"})
    if og_img and og_img.get("content"):
        og_url = urljoin(base_url, og_img["content"])
        if not any(og_url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
            candidates.append(og_url)
    # Collect img tags
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        full_url = urljoin(base_url, src)
        # Filter by extension
        if any(full_url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
            continue
        # Filter by URL path patterns
        url_lower = full_url.lower()
        if any(pattern in url_lower for pattern in SKIP_URL_PATTERNS):
            continue
        # Filter by dimension attributes if present
        width = _parse_int(img.get("width"))
        height = _parse_int(img.get("height"))
        if width and height:
            if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                continue
            aspect = max(width, height) / max(min(width, height), 1)
            if aspect > MAX_ASPECT_RATIO:
                continue
        if full_url not in candidates:
            candidates.append(full_url)
    # Fallback: scan raw HTML for image URLs not in <img> tags (JS-rendered pages)
    if len(candidates) < MAX_IMAGES_PER_PAGE:
        raw_html = str(soup)
        raw_urls = re.findall(
            r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', raw_html
        )
        for raw_url in raw_urls:
            if raw_url in candidates:
                continue
            url_lower = raw_url.lower()
            if any(url_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue
            if any(pattern in url_lower for pattern in SKIP_URL_PATTERNS):
                continue
            candidates.append(raw_url)
            if len(candidates) >= MAX_IMAGES_PER_PAGE:
                break
    return candidates[:MAX_IMAGES_PER_PAGE]


MAX_DATASHEETS = 3


def _extract_datasheets(soup: BeautifulSoup, html: str, base_url: str) -> list[str]:
    """Extract datasheet PDF URLs from links and raw HTML."""
    candidates = []
    # Check <a> tags with .pdf hrefs
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        full_url = urljoin(base_url, href)
        url_lower = full_url.lower()
        if any(pattern in url_lower for pattern in SKIP_PDF_PATTERNS):
            continue
        if full_url not in candidates:
            candidates.append(full_url)
        if len(candidates) >= MAX_DATASHEETS:
            break
    # Regex fallback for JS-rendered pages
    if len(candidates) < MAX_DATASHEETS:
        raw_urls = re.findall(r'https?://[^\s"\'<>]+\.pdf', html)
        for raw_url in raw_urls:
            url_lower = raw_url.lower()
            if any(pattern in url_lower for pattern in SKIP_PDF_PATTERNS):
                continue
            if raw_url not in candidates:
                candidates.append(raw_url)
            if len(candidates) >= MAX_DATASHEETS:
                break
    return candidates[:MAX_DATASHEETS]


def _parse_int(value) -> int | None:
    """Parse an integer from a string or return None."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
