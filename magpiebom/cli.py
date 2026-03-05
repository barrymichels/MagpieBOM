# magpiebom/cli.py
import argparse
import os
import requests
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from magpiebom.constants import BROWSER_UA, SKIP_PDF_PATTERNS as _SKIP_PDF_PATTERNS, MAX_PAGES_PER_SEARCH, MAX_SOURCES_FOR_EXTRACTION, MAX_SEARCH_RESULTS
from magpiebom.types import PipelineResult
from magpiebom.digikey import digikey_search
from magpiebom.images import download_image, save_final_image
from magpiebom.mouser import mouser_search
from magpiebom.scraper import scrape_page
from magpiebom.search import KNOWN_COMPONENT_SITES, brave_search
from magpiebom.tracer import Tracer
from magpiebom.validator import get_model_name, extract_description_from_sources, validate_image


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="magpiebom",
        description="AI-powered visual search for electronic component images and datasheets.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # search subcommand
    search_parser = subparsers.add_parser("search", help="Search for a single part")
    search_parser.add_argument("part_number", help="The part number to search for")
    search_parser.add_argument(
        "--output-dir", default="./parts", help="Directory to save the image (default: ./parts)"
    )
    search_parser.add_argument(
        "--no-open", action="store_true", help="Save image without opening it"
    )
    search_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed progress"
    )

    # batch subcommand
    batch_parser = subparsers.add_parser("batch", help="Process multiple parts")
    batch_parser.add_argument(
        "parts", nargs="*",
        help="Part numbers (or a filename containing part numbers, one per line)",
    )
    batch_parser.add_argument(
        "--output-dir", default="./parts", help="Directory to save results (default: ./parts)"
    )
    batch_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed progress"
    )

    # server subcommand
    server_parser = subparsers.add_parser("server", help="Start the web UI")
    server_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    server_parser.add_argument("--port", type=int, default=5000, help="Port to bind to (default: 5000)")
    server_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed progress"
    )

    return parser.parse_args(argv)


def _is_url_structurally_valid(url: str | None) -> bool:
    """Check if a URL looks structurally valid (no network calls)."""
    if not url or not url.strip():
        return False
    if not url.startswith(("http://", "https://")):
        return False
    # DigiKey placeholder pattern: /detail/-/-/ with nothing after
    if "/-/-/" in url and url.rstrip("/").endswith("/-/-"):
        return False
    return True


def _probe_url(url: str | None, tracer: Tracer | None = None) -> bool:
    """HTTP HEAD check to see if a URL is reachable. Returns True for 2xx/3xx."""
    if not url:
        return False
    try:
        t0 = time.monotonic()
        resp = requests.head(
            url, timeout=5, allow_redirects=True,
            headers={"User-Agent": BROWSER_UA},
        )
        duration_ms = (time.monotonic() - t0) * 1000
        if tracer:
            tracer.http(url=url, method="HEAD", status=resp.status_code,
                        headers=dict(resp.headers), body=None, duration_ms=duration_ms)
        return resp.status_code < 400
    except (requests.RequestException, OSError):
        return False


_SOURCE_DOMAINS = {
    "mouser": "mouser.com",
    "digikey": "digikey.com",
}


def _find_source_url_fallback(
    part_number: str, source: str, api_key: str, tracer: Tracer | None = None,
) -> str | None:
    """Search for a product page URL when the original source_url is broken."""
    domain = _SOURCE_DOMAINS.get(source)
    if not domain:
        return None
    if tracer:
        tracer.detail(f"Searching for {source} product page: {part_number}")
    results = brave_search(
        part_number, api_key=api_key, count=3,
        query_template="{part} site:" + domain,
        tracer=tracer,
    )
    if results:
        if tracer:
            tracer.detail(f"Found fallback source URL: {results[0]['url']}")
        return results[0]["url"]
    if tracer:
        tracer.detail("No fallback source URL found")
    return None


def _fix_broken_urls(result: dict, api_key: str, tracer: Tracer | None = None) -> None:
    """Validate source_url and datasheet_url; attempt fallback or null out if broken."""
    part_number = result["part_number"]
    source = result.get("source", "")

    # Validate source_url
    source_url = result.get("source_url")
    if source_url:
        if not _is_url_structurally_valid(source_url):
            if tracer:
                tracer.detail(f"Source URL structurally invalid: {source_url}")
            source_url = None
        elif not _probe_url(source_url, tracer=tracer):
            if tracer:
                tracer.detail(f"Source URL unreachable: {source_url}")
            source_url = None
    if not source_url and result.get("source_url"):
        # Original was set but is now invalid — try fallback
        fallback = _find_source_url_fallback(part_number, source, api_key, tracer=tracer)
        source_url = fallback
    result["source_url"] = source_url or None

    # Validate datasheet_url
    ds_url = result.get("datasheet_url")
    if ds_url:
        if not _is_url_structurally_valid(ds_url):
            if tracer:
                tracer.detail(f"Datasheet URL structurally invalid: {ds_url}")
            ds_url = None
        elif not _probe_url(ds_url, tracer=tracer):
            if tracer:
                tracer.detail(f"Datasheet URL unreachable: {ds_url}")
            ds_url = None

    # Fallback chain: Brave search → Playwright scrape of product page
    manufacturer = result.get("manufacturer", "")
    if not ds_url:
        ds_url = _search_datasheet_url(part_number, api_key, tracer=tracer, manufacturer=manufacturer)
    if not ds_url and result.get("source_url"):
        ds_url = _scrape_datasheet_playwright(result["source_url"], part_number, tracer=tracer)

    # Clean up stale downloaded file if datasheet URL changed or gone
    if not ds_url:
        ds_path = result.get("datasheet_path")
        if ds_path:
            Path(ds_path).unlink(missing_ok=True)
            result["datasheet_path"] = None
    result["datasheet_url"] = ds_url or None


def _search_datasheet_url(
    part_number: str, api_key: str, tracer: Tracer | None = None, manufacturer: str = "",
) -> str | None:
    """Search the web for a datasheet PDF for the given part number."""
    pn_upper = part_number.upper()
    pn_stripped = pn_upper.replace("-", "").replace(" ", "")

    # Build (part_number_variant, query_template) pairs
    pn_variants = [part_number]
    stripped = part_number.lstrip("0")
    if stripped != part_number:
        pn_variants.append(stripped)
    # Common dash insertion (e.g., 0395021011 → 39502-1011)
    if stripped.isdigit() and len(stripped) >= 8:
        pn_variants.append(f"{stripped[:5]}-{stripped[5:]}")

    search_attempts = []
    for pn_var in pn_variants:
        if manufacturer:
            search_attempts.append((pn_var, '{part} ' + manufacturer + ' datasheet filetype:pdf'))
        search_attempts.append((pn_var, '{part} datasheet filetype:pdf'))
        search_attempts.append((pn_var, '{part} datasheet pdf'))
    # Deduplicate
    seen = set()
    search_attempts = [(pn, qt) for pn, qt in search_attempts if (pn, qt) not in seen and not seen.add((pn, qt))]

    for search_pn, query_template in search_attempts:
        if tracer:
            tracer.detail(f"Searching for datasheet: {query_template.format(part=search_pn)}")
        results = brave_search(
            search_pn, api_key=api_key, count=5,
            query_template=query_template,
            tracer=tracer,
        )
        if not results:
            continue

        # Pass 1: direct PDF links
        for r in results:
            url = r["url"]
            if not (url.lower().endswith(".pdf") or "/pdf/" in url.lower()):
                continue
            haystack = (r.get("title", "") + " " + r.get("description", "") + " " + url).upper()
            haystack_stripped = haystack.replace("-", "").replace(" ", "")
            if pn_upper in haystack or pn_stripped in haystack_stripped:
                if tracer:
                    tracer.detail(f"Found datasheet URL: {url}")
                return url
            if tracer:
                tracer.detail(f"Skipping unrelated datasheet: {url}")

        # Pass 2: scrape pages that mention the part for PDF links
        for r in results:
            url = r["url"]
            if url.lower().endswith(".pdf"):
                continue  # Already checked above
            haystack = (r.get("title", "") + " " + r.get("description", "") + " " + url).upper()
            haystack_stripped = haystack.replace("-", "").replace(" ", "")
            if not (pn_upper in haystack or pn_stripped in haystack_stripped):
                continue
            if tracer:
                tracer.detail(f"Scraping for datasheet links: {url}")
            try:
                from magpiebom.scraper import scrape_page
                page_info = scrape_page(url, tracer=tracer)
                for ds_url in page_info.get("datasheet_urls", []):
                    ds_haystack = ds_url.upper().replace("-", "").replace(" ", "")
                    if pn_stripped in ds_haystack or pn_upper in ds_url.upper():
                        if tracer:
                            tracer.detail(f"Found datasheet via page scrape: {ds_url}")
                        return ds_url
                # Accept first datasheet from the page even without part match in URL
                if page_info.get("datasheet_urls"):
                    if tracer:
                        tracer.detail(f"Found datasheet via page scrape (first on page): {page_info['datasheet_urls'][0]}")
                    return page_info["datasheet_urls"][0]
            except Exception as e:
                if tracer:
                    tracer.detail(f"Failed to scrape {url}: {e}")

    if tracer:
        tracer.detail("No matching datasheet PDF in search results")
    return None


def _scrape_datasheet_playwright(page_url: str, part_number: str, tracer: Tracer | None = None) -> str | None:
    """Last resort: load product page in Playwright and extract datasheet PDF links."""
    try:
        from playwright.sync_api import sync_playwright as _sync_pw
    except ImportError:
        if tracer:
            tracer.detail("Playwright not installed, skipping browser datasheet scrape")
        return None

    if tracer:
        tracer.detail(f"Loading product page in browser for datasheet: {page_url}")
    try:
        with _sync_pw() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(page_url, timeout=15000, wait_until="networkidle")

            # Extract all links from the rendered page
            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => ({href: e.href, text: e.textContent || ''}))",
            )
            browser.close()
    except Exception as e:
        if tracer:
            tracer.error(f"Playwright datasheet scrape failed: {e}")
        return None

    pn_upper = part_number.upper()
    pn_stripped = pn_upper.replace("-", "").replace(" ", "")

    for link in links:
        href = link.get("href", "")
        if not href.lower().endswith(".pdf"):
            continue
        if any(pat in href.lower() for pat in _SKIP_PDF_PATTERNS):
            continue
        # Prefer links whose URL or anchor text references the part number
        haystack = (href + " " + link.get("text", "")).upper()
        haystack_stripped = haystack.replace("-", "").replace(" ", "")
        if pn_upper in haystack or pn_stripped in haystack_stripped:
            if tracer:
                tracer.detail(f"Found datasheet via browser (part match): {href}")
            return href

    # If no part-specific match, accept the first PDF that looks like a datasheet
    for link in links:
        href = link.get("href", "")
        if not href.lower().endswith(".pdf"):
            continue
        if any(pat in href.lower() for pat in _SKIP_PDF_PATTERNS):
            continue
        text = link.get("text", "").lower()
        if any(kw in text for kw in ("datasheet", "data sheet", "spec")):
            if tracer:
                tracer.detail(f"Found datasheet via browser (keyword match): {href}")
            return href

    if tracer:
        tracer.detail("No datasheet found on rendered product page")
    return None


def _download_datasheet(url: str, part_number: str, output_dir: str, tracer: Tracer | None = None) -> str | None:
    """Download a datasheet PDF and save it to the output directory."""
    if tracer:
        tracer.detail(f"Downloading datasheet: {url}")
    try:
        t0 = time.monotonic()
        resp = requests.get(url, timeout=15, headers={"User-Agent": BROWSER_UA})
        duration_ms = (time.monotonic() - t0) * 1000
        resp.raise_for_status()
        if tracer:
            tracer.http(url=url, method="GET", status=resp.status_code,
                        headers=dict(resp.headers), body=None, duration_ms=duration_ms)
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if "pdf" not in content_type:
            if tracer:
                tracer.detail(f"Not a PDF (content-type: {content_type}), skipping")
            return None
        if not resp.content[:5].startswith(b"%PDF-"):
            if tracer:
                tracer.detail("Response does not start with PDF magic bytes, skipping")
            return None
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in part_number)
        dest = out_dir / f"{safe_name}.pdf"
        dest.write_bytes(resp.content)
        if tracer:
            tracer.detail(f"Saved datasheet: {dest}")
        return str(dest)
    except Exception as e:
        if tracer:
            tracer.error(f"Datasheet download failed: {e}")
        return None


def _try_supplier_api(
    supplier_name: str,
    search_fn,
    search_kwargs: dict,
    part_number: str,
    tracer: Tracer,
) -> dict | None:
    """Try a supplier API. Returns a partial result dict or None to fall through."""
    tracer.step(f"Trying {supplier_name} API...")
    try:
        api_result = search_fn(part_number, **search_kwargs, tracer=tracer)
        if not api_result or not api_result.get("image_url"):
            tracer.detail(f"{supplier_name}: no results")
            return None

        tracer.detail(f"{supplier_name} found: {api_result['description']}")
        tracer.detail(f"Downloading: {api_result['image_url']}")
        temp_path = download_image(api_result["image_url"], tracer=tracer)
        if not temp_path:
            tracer.detail(f"{supplier_name} image download failed, falling back to search")
            return None

        return {
            "temp_path": temp_path,
            "description": api_result["description"],
            "source": supplier_name.lower(),
            "manufacturer": api_result.get("manufacturer", ""),
            "source_url": api_result.get("product_detail_url", "") or api_result.get("digikey_pn", ""),
            "datasheet_url": api_result.get("datasheet_url"),
            "api_result": api_result,
        }
    except Exception as e:
        tracer.error(f"{supplier_name} API failed: {e}", exception=e)
        return None


def _finalize_result(
    result: PipelineResult,
    api_key: str,
    output_dir: str,
    no_open: bool,
    tracer: Tracer,
) -> PipelineResult:
    """Search for datasheet, download it, validate URLs, optionally open image."""
    part_number = result["part_number"]
    manufacturer = result.get("manufacturer", "")  # type: ignore[typeddict-item]

    if not result["datasheet_url"]:
        result["datasheet_url"] = _search_datasheet_url(
            part_number, api_key, tracer=tracer, manufacturer=manufacturer,
        )
    if result["datasheet_url"]:
        result["datasheet_path"] = _download_datasheet(
            result["datasheet_url"], part_number, output_dir, tracer=tracer,
        )
    _fix_broken_urls(result, api_key, tracer=tracer)
    if not no_open and result["image_path"]:
        subprocess.Popen(
            ["xdg-open", result["image_path"]],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    tracer.result(result)
    print(f"Trace: {tracer.trace_path}", file=sys.stderr)
    return result


def _try_web_search(
    part_number: str,
    result: PipelineResult,
    output_dir: str,
    api_key: str,
    client,
    model: str,
    no_open: bool,
    tracer: Tracer,
) -> PipelineResult:
    """Web search fallback: scrape pages, extract description, validate images."""
    queries = [
        '"{part}" electronic component',
        '{part} site:lcsc.com OR site:jlcpcb.com OR site:mouser.com',
        '"{part}" datasheet photo',
        '{part} component image',
    ]

    seen_urls: set[str] = set()
    seen_images: set[str] = set()

    # === Phase 1: Collect all data (scrape pages + gather Brave snippets) ===
    all_sources = []
    all_image_candidates = []

    for attempt, query_template in enumerate(queries):
        tracer.step(f"Search attempt {attempt + 1}: {query_template.format(part=part_number)}")

        search_results = brave_search(part_number, api_key=api_key, count=MAX_SEARCH_RESULTS, query_template=query_template, tracer=tracer)
        if not search_results:
            tracer.detail("No search results found")
            continue

        for sr in search_results:
            if sr.get("title") or sr.get("description"):
                all_sources.append({
                    "title": sr.get("title", ""),
                    "meta_description": sr.get("description", ""),
                    "meta_keywords": "",
                    "url_path": "",
                    "url_category": "",
                    "paragraphs": [],
                })

        pages_scraped = 0
        for sr in search_results:
            if pages_scraped >= MAX_PAGES_PER_SEARCH:
                break
            url = sr["url"]
            if url in seen_urls:
                tracer.detail(f"Already tried: {url}")
                continue
            seen_urls.add(url)
            tracer.detail(f"Scraping: {url}")
            try:
                page_info = scrape_page(url, tracer=tracer)
            except Exception as e:
                tracer.detail(f"Failed to scrape {url}: {e}")
                continue

            pages_scraped += 1
            text_signals = page_info["text_signals"]
            all_sources.append(text_signals)

            if not result["datasheet_url"] and page_info.get("datasheet_urls"):
                result["datasheet_url"] = page_info["datasheet_urls"][0]

            page_text = (
                text_signals.get("title", "") + " " +
                text_signals.get("meta_description", "") + " " +
                text_signals.get("meta_keywords", "") + " " +
                sr.get("title", "")
            ).upper()
            on_component_site = any(site in url for site in KNOWN_COMPONENT_SITES)
            if part_number.upper() not in page_text:
                if not on_component_site:
                    tracer.detail(f"Skipping images: page doesn't mention {part_number}")
                    continue
                tracer.detail(f"Page doesn't mention exact part number, but is a component site — collecting images")

            for img_url in page_info["image_urls"]:
                if img_url not in seen_images:
                    seen_images.add(img_url)
                    all_image_candidates.append((img_url, url))

    # === Phase 2: Extract description ONCE from all collected sources ===
    pn_upper = part_number.upper()
    exact_sources = [s for s in all_sources if pn_upper in (
        s.get("title", "") + " " + s.get("meta_description", "") + " " + s.get("meta_keywords", "")
    ).upper()]
    other_sources = [s for s in all_sources if s not in exact_sources]
    prioritized_sources = (exact_sources + other_sources)[:MAX_SOURCES_FOR_EXTRACTION]

    tracer.step("Extracting description from all sources...")
    tracer.detail(f"Using {len(prioritized_sources)} sources ({len(exact_sources)} exact matches, {len(all_sources)} total collected)")
    best_description = extract_description_from_sources(
        client, model, part_number, prioritized_sources, tracer=tracer,
    )
    if best_description:
        tracer.detail(f"Aggregated description: {best_description[:80]}")
    else:
        tracer.detail("No description could be extracted from any source")

    # === Phase 3: Validate images using the aggregated description ===
    for img_url, source_url in all_image_candidates:
        tracer.detail(f"Downloading: {img_url}")
        temp_path = download_image(img_url, tracer=tracer)
        if temp_path is None:
            tracer.detail("Download failed, skipping")
            continue

        tracer.step("Asking LLM to validate...")
        verdict = validate_image(
            client=client,
            model=model,
            image_path=temp_path,
            part_number=part_number,
            description=best_description,
            tracer=tracer,
        )
        tokens = ""
        if "prompt_tokens" in verdict:
            tokens = f" ({verdict['prompt_tokens']}+{verdict['completion_tokens']} tokens)"
        tracer.detail(f"LLM says: match={verdict['match']}, reason={verdict['reason']}{tokens}")

        if verdict["match"]:
            saved_path = save_final_image(temp_path, part_number, output_dir)
            Path(temp_path).unlink(missing_ok=True)
            print(f"Saved: {saved_path}")
            result["image_path"] = saved_path
            result["description"] = best_description
            result["source"] = "web"
            result["source_url"] = source_url
            return _finalize_result(result, api_key, output_dir, no_open, tracer)

        Path(temp_path).unlink(missing_ok=True)

    print(f"No matching image found for {part_number}", file=sys.stderr)
    tracer.result(result)
    print(f"Trace: {tracer.trace_path}", file=sys.stderr)
    return result


def run_pipeline(
    part_number: str,
    output_dir: str = "./parts",
    no_open: bool = False,
    verbose: bool = False,
) -> PipelineResult:
    """Run the full search-scrape-validate pipeline. Returns a result dict."""
    result = {
        "part_number": part_number,
        "image_path": None,
        "datasheet_url": None,
        "datasheet_path": None,
        "description": "",
        "source": "",
        "source_url": "",
    }

    load_dotenv()
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        print("Error: BRAVE_API_KEY not set. Add it to .env or environment.", file=sys.stderr)
        return result

    with Tracer(part_number, verbose=verbose) as tracer:
        llm_url = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
        client = OpenAI(base_url=llm_url, api_key=os.environ.get("LLM_API_KEY", "not-needed"))
        model = get_model_name(client)
        tracer.detail(f"Using LLM model: {model}")

        # Try Mouser API first (structured data, reliable images)
        mouser_key = os.environ.get("MOUSER_SEARCH_API_KEY")
        if mouser_key:
            supplier_hit = _try_supplier_api("Mouser", mouser_search, {"api_key": mouser_key}, part_number, tracer)
            if supplier_hit:
                temp_path = supplier_hit["temp_path"]
                saved_path = save_final_image(temp_path, part_number, output_dir)
                Path(temp_path).unlink(missing_ok=True)
                print(f"Saved: {saved_path} (via Mouser API)")
                result["image_path"] = saved_path
                result["description"] = supplier_hit["description"]
                result["source"] = "mouser"
                result["manufacturer"] = supplier_hit["manufacturer"]  # type: ignore[typeddict-unknown-key]
                api_result = supplier_hit["api_result"]
                result["source_url"] = api_result.get("product_detail_url") or f"https://www.mouser.com/ProductDetail/{api_result['mouser_pn']}"
                result["datasheet_url"] = api_result.get("datasheet_url")
                return _finalize_result(result, api_key, output_dir, no_open, tracer)

        # Try DigiKey API
        dk_id = os.environ.get("DIGIKEY_CLIENT_ID")
        dk_secret = os.environ.get("DIGIKEY_CLIENT_SECRET")
        if dk_id and dk_secret:
            supplier_hit = _try_supplier_api("DigiKey", digikey_search, {"client_id": dk_id, "client_secret": dk_secret}, part_number, tracer)
            if supplier_hit:
                temp_path = supplier_hit["temp_path"]
                saved_path = save_final_image(temp_path, part_number, output_dir)
                Path(temp_path).unlink(missing_ok=True)
                print(f"Saved: {saved_path} (via DigiKey API)")
                result["image_path"] = saved_path
                result["description"] = supplier_hit["description"]
                result["source"] = "digikey"
                result["manufacturer"] = supplier_hit["manufacturer"]  # type: ignore[typeddict-unknown-key]
                api_result = supplier_hit["api_result"]
                result["source_url"] = f"https://www.digikey.com/en/products/detail/-/-/{api_result['digikey_pn']}"
                result["datasheet_url"] = api_result.get("datasheet_url")
                return _finalize_result(result, api_key, output_dir, no_open, tracer)

        # Web search fallback
        return _try_web_search(part_number, result, output_dir, api_key, client, model, no_open, tracer)


def main():
    args = parse_args()
    if args.command == "search":
        result = run_pipeline(
            part_number=args.part_number,
            output_dir=args.output_dir,
            no_open=args.no_open,
            verbose=args.verbose,
        )
        sys.exit(0 if result["image_path"] else 1)
    elif args.command == "batch":
        from magpiebom.batch import batch_main
        batch_main(args)
    elif args.command == "server":
        from magpiebom.server import server_main
        server_main(args)
