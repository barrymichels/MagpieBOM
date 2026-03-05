# magpiebom/images.py
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from magpiebom.tracer import Tracer

from magpiebom.constants import BROWSER_UA as _BROWSER_UA


def download_image(url: str, timeout: int = 10, tracer: Tracer | None = None) -> str | None:
    """Download an image to a temp file. Falls back to Playwright for bot-protected CDNs."""
    path = _download_requests(url, timeout, tracer=tracer)
    if path is None:
        path = _download_playwright(url, timeout, tracer=tracer)
    if path and tracer:
        try:
            from PIL import Image
            with Image.open(path) as img:
                tracer.image(url=url, path=path, width=img.width, height=img.height,
                             size_bytes=Path(path).stat().st_size, format=img.format)
        except Exception:
            tracer.image(url=url, path=path, width=None, height=None,
                         size_bytes=Path(path).stat().st_size if Path(path).exists() else None,
                         format=None)
    return path


def _download_requests(url: str, timeout: int, tracer: Tracer | None = None) -> str | None:
    """Fast path: download with requests."""
    start = time.monotonic()
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": _BROWSER_UA},
            stream=True,
        )
        duration_ms = (time.monotonic() - start) * 1000
        resp.raise_for_status()
        if tracer:
            tracer.http(url=url, method="GET", status=resp.status_code,
                        headers=dict(resp.headers), body=None,
                        duration_ms=duration_ms)
    except requests.RequestException as e:
        duration_ms = (time.monotonic() - start) * 1000
        if tracer:
            tracer.http(url=url, method="GET", status=0,
                        headers={}, body=str(e),
                        duration_ms=duration_ms)
        return None

    # Reject non-image responses (e.g. "Access Denied" HTML pages)
    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        if tracer:
            tracer.detail(f"Rejected non-image response from {url}",
                          content_type=content_type)
        return None

    # Determine extension from URL or content type
    ext = _get_extension(url, resp.headers.get("content-type", ""))
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        return None


def _download_playwright(url: str, timeout: int, tracer: Tracer | None = None) -> str | None:
    """Slow path: use a headless browser to bypass bot protection."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if tracer:
            tracer.detail(f"Playwright not available for {url}")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            resp = page.goto(url, timeout=timeout * 1000, wait_until="load")
            if resp is None or not resp.ok:
                if tracer:
                    tracer.detail(f"Playwright fetch failed for {url}",
                                  status=resp.status if resp else None)
                browser.close()
                return None
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                if tracer:
                    tracer.detail(f"Playwright non-image response from {url}",
                                  content_type=content_type)
                browser.close()
                return None
            ext = _get_extension(url, content_type)
            body = resp.body()
            tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            tmp.write(body)
            tmp.close()
            browser.close()
            return tmp.name
    except Exception:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except UnboundLocalError:
            pass
        return None


def save_final_image(
    temp_path: str, part_number: str, output_dir: str = "./parts"
) -> str:
    """Copy the validated image from temp to the final output location."""
    ext = Path(temp_path).suffix or ".jpg"
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize part number for filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in part_number)
    dest = out_dir / f"{safe_name}{ext}"
    shutil.copy2(temp_path, dest)
    return str(dest)


def _get_extension(url: str, content_type: str) -> str:
    """Determine file extension from URL path or content-type header."""
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"):
        return ext
    ct_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    return ct_map.get(content_type.split(";")[0].strip(), ".jpg")
