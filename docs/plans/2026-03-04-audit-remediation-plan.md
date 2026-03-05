# Audit Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address all findings from the full codebase audit — dead code, shared infrastructure, error handling, cli.py refactor, and comprehensive test coverage.

**Architecture:** Bottom-up approach. Quick fixes first, then shared infrastructure (constants, types, conftest), then error handling, then cli.py refactor, then comprehensive tests for all untested modules, then improvements to existing tests.

**Tech Stack:** Python 3.14, pytest, responses (HTTP mocking), Flask test client, unittest.mock

**Test command:** `. .venv/bin/activate && pytest tests/ -v`

---

### Task 1: Quick Fixes — Dead Code and Import Cleanup

**Files:**
- Modify: `magpiebom/cli.py:18` (remove unused import)
- Modify: `magpiebom/cli.py:81,335` (move requests to top-level)
- Modify: `magpiebom/server.py:215-223` (remove orphaned main)

**Step 1: Remove unused `extract_description` import**

In `magpiebom/cli.py:18`, change:
```python
from magpiebom.validator import get_model_name, extract_description, extract_description_from_sources, validate_image
```
to:
```python
from magpiebom.validator import get_model_name, extract_description_from_sources, validate_image
```

**Step 2: Move `requests` to top-level imports in cli.py**

Add `import requests` after line 4 (`import subprocess`). Then remove the local `import requests` at lines 81 and 335.

**Step 3: Remove orphaned `main()` from server.py**

Delete lines 215-223 (the standalone `main()` function). It's never called — `server_main(args)` is the real entry point.

**Step 4: Run tests**

Run: `. .venv/bin/activate && pytest tests/ -v`
Expected: All 99 tests pass.

**Step 5: Commit**

```bash
git add magpiebom/cli.py magpiebom/server.py
git commit -m "Remove dead code: unused import, orphaned main(), duplicate local imports"
```

---

### Task 2: Shared Constants Module

**Files:**
- Create: `magpiebom/constants.py`
- Modify: `magpiebom/images.py:12-15` (import BROWSER_UA)
- Modify: `magpiebom/cli.py:87-88,264,338-339` (import constants)
- Modify: `magpiebom/scraper.py:185` (import SKIP_PDF_PATTERNS)

**Step 1: Create `magpiebom/constants.py`**

```python
"""Shared constants for MagpieBOM."""

# Browser User-Agent for HTTP requests that need to look like a real browser
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)

# URL path segments that indicate non-product PDFs
SKIP_PDF_PATTERNS = ["terms", "privacy", "cookie", "legal", "compliance", "return"]

# Pipeline limits
MAX_PAGES_PER_SEARCH = 5
MAX_SOURCES_FOR_EXTRACTION = 10
MAX_SEARCH_RESULTS = 15
```

**Step 2: Update `magpiebom/images.py`**

Replace lines 12-15:
```python
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)
```
with:
```python
from magpiebom.constants import BROWSER_UA as _BROWSER_UA
```

**Step 3: Update `magpiebom/cli.py`**

Add import at top:
```python
from magpiebom.constants import BROWSER_UA, SKIP_PDF_PATTERNS as _SKIP_PDF_PATTERNS, MAX_PAGES_PER_SEARCH, MAX_SOURCES_FOR_EXTRACTION, MAX_SEARCH_RESULTS
```

Remove the inline `_SKIP_PDF_PATTERNS = [...]` at line 264.

Replace both inline User-Agent strings (in `_probe_url` and `_download_datasheet`) with `BROWSER_UA`.

Replace magic numbers:
- `pages_scraped >= 5` → `pages_scraped >= MAX_PAGES_PER_SEARCH`
- `[:10]` (sources cap) → `[:MAX_SOURCES_FOR_EXTRACTION]`
- `count=15` → `count=MAX_SEARCH_RESULTS`

**Step 4: Update `magpiebom/scraper.py`**

Replace line 185:
```python
SKIP_PDF_PATTERNS = ["terms", "privacy", "cookie", "legal", "compliance", "return"]
```
with:
```python
from magpiebom.constants import SKIP_PDF_PATTERNS
```

Note: Move this import to the top of the file with other imports.

**Step 5: Run tests**

Run: `. .venv/bin/activate && pytest tests/ -v`
Expected: All 99 tests pass.

**Step 6: Commit**

```bash
git add magpiebom/constants.py magpiebom/images.py magpiebom/cli.py magpiebom/scraper.py
git commit -m "Extract shared constants to constants.py, eliminate duplication"
```

---

### Task 3: TypedDicts for API Return Types

**Files:**
- Create: `magpiebom/types.py`
- Modify: `magpiebom/mouser.py` (return type annotation)
- Modify: `magpiebom/digikey.py` (return type annotation)
- Modify: `magpiebom/scraper.py` (return type annotations)
- Modify: `magpiebom/cli.py` (return type annotation on run_pipeline)

**Step 1: Create `magpiebom/types.py`**

```python
"""Type definitions for MagpieBOM pipeline data structures."""

from typing import TypedDict


class SupplierResult(TypedDict):
    """Base result from a supplier API search."""
    description: str
    image_url: str
    datasheet_url: str | None
    manufacturer: str


class MouserResult(SupplierResult):
    """Result from Mouser API search."""
    mouser_pn: str
    product_detail_url: str


class DigiKeyResult(SupplierResult):
    """Result from DigiKey API search."""
    digikey_pn: str


class PipelineResult(TypedDict):
    """Result from the full search pipeline."""
    part_number: str
    image_path: str | None
    datasheet_url: str | None
    datasheet_path: str | None
    description: str
    source: str
    source_url: str


class TextSignals(TypedDict):
    """Structured text signals extracted from a web page."""
    title: str
    meta_description: str
    meta_keywords: str
    url_path: str
    url_category: str
    paragraphs: list[str]


class PageInfo(TypedDict):
    """Full extraction result from a scraped web page."""
    text_signals: TextSignals
    image_urls: list[str]
    datasheet_urls: list[str]


class SearchResult(TypedDict):
    """A single result from Brave Search."""
    url: str
    title: str
    description: str
```

**Step 2: Update function signatures**

In `magpiebom/mouser.py`:
```python
from magpiebom.types import MouserResult
def mouser_search(...) -> MouserResult | None:
```

In `magpiebom/digikey.py`:
```python
from magpiebom.types import DigiKeyResult
def digikey_search(...) -> DigiKeyResult | None:
```

In `magpiebom/scraper.py`:
```python
from magpiebom.types import PageInfo, TextSignals
def scrape_page(...) -> PageInfo:
def extract_page_info(...) -> PageInfo:
def _extract_text_signals(...) -> TextSignals:
```

In `magpiebom/search.py`:
```python
from magpiebom.types import SearchResult
def brave_search(...) -> list[SearchResult]:
```

In `magpiebom/cli.py`:
```python
from magpiebom.types import PipelineResult
def run_pipeline(...) -> PipelineResult:
```

In `magpiebom/batch.py`, add type hint:
```python
import argparse
def _read_part_numbers(args: argparse.Namespace) -> list[str]:
def batch_main(args: argparse.Namespace) -> None:
```

**Step 3: Run tests**

Run: `. .venv/bin/activate && pytest tests/ -v`
Expected: All 99 tests pass. TypedDicts are structural, so no runtime changes.

**Step 4: Commit**

```bash
git add magpiebom/types.py magpiebom/mouser.py magpiebom/digikey.py magpiebom/scraper.py magpiebom/search.py magpiebom/cli.py magpiebom/batch.py
git commit -m "Add TypedDict definitions for all API return types"
```

---

### Task 4: Shared Test Fixtures (conftest.py)

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_validator.py` (use shared TINY_PNG)
- Modify: `tests/test_images.py` (use shared TINY_PNG)
- Modify: `tests/test_integration.py` (use shared TINY_PNG)

**Step 1: Create `tests/conftest.py`**

```python
"""Shared test fixtures for MagpieBOM test suite."""

import pytest
from unittest.mock import MagicMock


# 1x1 red PNG (smallest valid PNG)
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def tiny_png_path(tmp_path):
    """Write TINY_PNG to a temp file and return its path as a string."""
    p = tmp_path / "test.png"
    p.write_bytes(TINY_PNG)
    return str(p)


def make_mock_llm_client(response_content: str) -> MagicMock:
    """Create a mock OpenAI client that returns the given content."""
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = response_content
    completion = MagicMock()
    completion.choices = [choice]
    client.chat.completions.create.return_value = completion
    return client
```

**Step 2: Update test files to use shared fixtures**

In `tests/test_validator.py`: Remove local TINY_PNG (lines 12-17) and `_make_mock_client` (lines 20-28). Import from conftest:
```python
from conftest import TINY_PNG, make_mock_llm_client
```
Replace all `_make_mock_client` calls with `make_mock_llm_client`. Replace all manual temp file creation with the `tiny_png_path` fixture where applicable.

In `tests/test_images.py`: Remove local TINY_PNG (lines 11-17). Import:
```python
from conftest import TINY_PNG
```

In `tests/test_integration.py`: Remove local TINY_PNG (lines 11-16). Import:
```python
from conftest import TINY_PNG
```

**Step 3: Fix temp file cleanup in test_validator.py**

Replace the pattern:
```python
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    f.write(TINY_PNG)
    f.flush()
    result = validate_image(..., image_path=f.name, ...)
assert result["match"] is True
Path(f.name).unlink()
```
with using the `tiny_png_path` fixture:
```python
def test_validate_image_match(tiny_png_path):
    client = make_mock_llm_client('{"match": true, "reason": "..."}')
    result = validate_image(client=client, model="test-model", image_path=tiny_png_path,
                            part_number="LM7805", description="5V voltage regulator")
    assert result["match"] is True
```

Do this for all 5 validate_image tests that use NamedTemporaryFile.

**Step 4: Run tests**

Run: `. .venv/bin/activate && pytest tests/ -v`
Expected: All 99 tests pass.

**Step 5: Commit**

```bash
git add tests/conftest.py tests/test_validator.py tests/test_images.py tests/test_integration.py
git commit -m "Add shared test fixtures, deduplicate TINY_PNG, fix temp file cleanup"
```

---

### Task 5: Error Handling Improvements

**Files:**
- Modify: `magpiebom/cli.py` (3 bare excepts)
- Modify: `magpiebom/images.py` (2 bare excepts + UnboundLocalError trap)
- Modify: `magpiebom/server.py` (2 bare excepts)

**Step 1: Fix `_probe_url` in cli.py**

Change `except Exception:` to:
```python
except (requests.RequestException, OSError):
    return False
```

**Step 2: Fix Mouser/DigiKey bare excepts in cli.py**

Change `except Exception as e:` (Mouser block, around line 437) to:
```python
except (requests.RequestException, Exception) as e:
    tracer.error(f"Mouser API failed: {e}", exception=e)
```
Same for DigiKey block (around line 477):
```python
except (requests.RequestException, Exception) as e:
    tracer.error(f"DigiKey API failed: {e}", exception=e)
```

Note: Keep broad catch here since supplier APIs could raise various errors, but use `tracer.error` instead of `tracer.detail` so it always appears in stderr.

**Step 3: Fix `_download_requests` chunk write in images.py**

Change `except Exception:` at line 76 to:
```python
except (IOError, OSError):
    tmp.close()
    Path(tmp.name).unlink(missing_ok=True)
    return None
```

**Step 4: Fix UnboundLocalError trap in `_download_playwright` in images.py**

Replace lines 91-121:
```python
    tmp = None
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
        if tmp:
            Path(tmp.name).unlink(missing_ok=True)
        return None
```

**Step 5: Fix server.py bare excepts**

In `batch_stream` (line 140) and `batch_retry` (line 190), change:
```python
except Exception:
    result = {...}
```
to:
```python
except Exception as e:
    import sys
    print(f"Pipeline error for {pn}: {e}", file=sys.stderr)
    result = {...}
```

**Step 6: Rename `_validate_urls` to `_fix_broken_urls`**

In `magpiebom/cli.py`, rename the function `_validate_urls` to `_fix_broken_urls` at its definition and all 3 call sites (lines 429, 469, 612). Also update `tests/test_cli.py` — all references to `_validate_urls` become `_fix_broken_urls` (in imports at line 4 and all test functions/patches).

**Step 7: Run tests**

Run: `. .venv/bin/activate && pytest tests/ -v`
Expected: All 99 tests pass.

**Step 8: Commit**

```bash
git add magpiebom/cli.py magpiebom/images.py magpiebom/server.py tests/test_cli.py
git commit -m "Fix bare except clauses, UnboundLocalError trap, rename _validate_urls"
```

---

### Task 6: Refactor cli.py — Extract Helper Functions

**Files:**
- Modify: `magpiebom/cli.py`
- Modify: `tests/test_cli.py` (update imports for new functions)

This is the biggest task. The goal is to split `run_pipeline()` from 255 lines to ~40 lines.

**Step 1: Extract `_try_supplier_api()`**

Add this function before `run_pipeline()`:

```python
def _try_supplier_api(
    supplier_name: str,
    search_fn,
    search_kwargs: dict,
    part_number: str,
    tracer: Tracer,
) -> PipelineResult | None:
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
    except (requests.RequestException, Exception) as e:
        tracer.error(f"{supplier_name} API failed: {e}", exception=e)
        return None
```

**Step 2: Extract `_finalize_result()`**

```python
def _finalize_result(
    result: PipelineResult,
    api_key: str,
    output_dir: str,
    no_open: bool,
    tracer: Tracer,
) -> PipelineResult:
    """Validate URLs, download datasheet, optionally open image."""
    part_number = result["part_number"]
    manufacturer = result.get("manufacturer", "")

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
```

**Step 3: Extract `_try_web_search()`**

Move the entire Phase 1/2/3 block into this function. It takes `part_number, output_dir, api_key, client, model, no_open, tracer` and returns `PipelineResult`.

This is the largest extraction — it's the web search code from lines 480-624. The function should contain:
- The queries list
- Phase 1: Collect sources and image candidates
- Phase 2: Extract description from sources
- Phase 3: Validate images
- Return the result (or empty result if no match)

**Step 4: Simplify `run_pipeline()`**

After extraction, `run_pipeline` becomes approximately:

```python
def run_pipeline(part_number, output_dir="./parts", no_open=False, verbose=False) -> PipelineResult:
    result: PipelineResult = {
        "part_number": part_number, "image_path": None, "datasheet_url": None,
        "datasheet_path": None, "description": "", "source": "", "source_url": "",
    }
    load_dotenv()
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        print("Error: BRAVE_API_KEY not set.", file=sys.stderr)
        return result

    with Tracer(part_number, verbose=verbose) as tracer:
        llm_url = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
        client = OpenAI(base_url=llm_url, api_key=os.environ.get("LLM_API_KEY", "not-needed"))
        model = get_model_name(client)
        tracer.detail(f"Using LLM model: {model}")

        # Try Mouser
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
                result["manufacturer"] = supplier_hit["manufacturer"]
                api_result = supplier_hit["api_result"]
                result["source_url"] = api_result.get("product_detail_url") or f"https://www.mouser.com/ProductDetail/{api_result['mouser_pn']}"
                result["datasheet_url"] = api_result.get("datasheet_url")
                return _finalize_result(result, api_key, output_dir, no_open, tracer)

        # Try DigiKey
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
                result["manufacturer"] = supplier_hit["manufacturer"]
                api_result = supplier_hit["api_result"]
                result["source_url"] = f"https://www.digikey.com/en/products/detail/-/-/{api_result['digikey_pn']}"
                result["datasheet_url"] = api_result.get("datasheet_url")
                return _finalize_result(result, api_key, output_dir, no_open, tracer)

        # Web search fallback
        return _try_web_search(part_number, result, output_dir, api_key, client, model, no_open, tracer)
```

**Step 5: Run tests**

Run: `. .venv/bin/activate && pytest tests/ -v`
Expected: All 99 tests pass. This is a refactor — behavior should be identical.

**Step 6: Commit**

```bash
git add magpiebom/cli.py
git commit -m "Refactor: extract _try_supplier_api, _finalize_result, _try_web_search from run_pipeline"
```

---

### Task 7: New Tests — test_mouser.py

**Files:**
- Create: `tests/test_mouser.py`

**Step 1: Write tests**

```python
"""Tests for magpiebom.mouser module."""

import responses
import pytest
from magpiebom.mouser import mouser_search, MOUSER_API_URL


def _mouser_response(parts):
    return {"SearchResults": {"Parts": parts}}


def _part(mpn="LM7805", image="https://mouser.com/img.jpg", desc="5V Regulator",
          ds_url="https://mouser.com/ds.pdf", mfr="Texas Instruments",
          mouser_pn="595-LM7805", detail_url="https://mouser.com/ProductDetail/595-LM7805"):
    return {
        "ManufacturerPartNumber": mpn,
        "ImagePath": image,
        "Description": desc,
        "DataSheetUrl": ds_url,
        "Manufacturer": mfr,
        "MouserPartNumber": mouser_pn,
        "ProductDetailUrl": detail_url,
    }


@responses.activate
def test_exact_match():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(mpn="NE555"), _part(mpn="LM7805")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None
    assert result["description"] == "5V Regulator"
    assert result["manufacturer"] == "Texas Instruments"


@responses.activate
def test_fallback_to_first_result():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(mpn="LM7805CT")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None  # Falls back to first even though MPN doesn't match exactly


@responses.activate
def test_case_insensitive_match():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(mpn="lm7805")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None


@responses.activate
def test_no_parts_returns_none():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([]), status=200)
    assert mouser_search("XYZFAKE", api_key="key") is None


@responses.activate
def test_no_image_returns_none():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(image="")]), status=200)
    assert mouser_search("LM7805", api_key="key") is None


@responses.activate
def test_protocol_relative_url_fixed():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(image="//mouser.com/img.jpg")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result["image_url"] == "https://mouser.com/img.jpg"


@responses.activate
def test_null_datasheet_url():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(ds_url="")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result["datasheet_url"] is None


@responses.activate
def test_api_401_raises():
    responses.add(responses.POST, MOUSER_API_URL, json={"error": "Unauthorized"}, status=401)
    with pytest.raises(Exception):
        mouser_search("LM7805", api_key="bad-key")


@responses.activate
def test_api_500_raises():
    responses.add(responses.POST, MOUSER_API_URL, json={"error": "Server Error"}, status=500)
    with pytest.raises(Exception):
        mouser_search("LM7805", api_key="key")


@responses.activate
def test_timeout_raises():
    responses.add(responses.POST, MOUSER_API_URL, body=ConnectionError("timeout"))
    with pytest.raises(ConnectionError):
        mouser_search("LM7805", api_key="key")


@responses.activate
def test_missing_fields_handled():
    """Parts with missing optional fields should still work."""
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([{
                      "ManufacturerPartNumber": "LM7805",
                      "ImagePath": "https://mouser.com/img.jpg",
                  }]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None
    assert result["description"] == ""
    assert result["datasheet_url"] is None
```

**Step 2: Run tests**

Run: `. .venv/bin/activate && pytest tests/test_mouser.py -v`
Expected: All pass.

**Step 3: Commit**

```bash
git add tests/test_mouser.py
git commit -m "Add comprehensive tests for mouser.py"
```

---

### Task 8: New Tests — test_digikey.py

**Files:**
- Create: `tests/test_digikey.py`

**Step 1: Write tests**

```python
"""Tests for magpiebom.digikey module."""

import responses
import pytest
from magpiebom.digikey import digikey_search, _get_token, TOKEN_URL, SEARCH_URL


@responses.activate
def test_get_token_success():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "test-token"}, status=200)
    token = _get_token("client-id", "client-secret")
    assert token == "test-token"


@responses.activate
def test_get_token_401_raises():
    responses.add(responses.POST, TOKEN_URL, json={"error": "invalid_client"}, status=401)
    with pytest.raises(Exception):
        _get_token("bad-id", "bad-secret")


@responses.activate
def test_search_exact_match():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": {"ProductDescription": "5V Regulator"}, "DatasheetUrl": "https://dk.com/ds.pdf",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296-LM7805"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result is not None
    assert result["description"] == "5V Regulator"
    assert result["manufacturer"] == "TI"
    assert result["digikey_pn"] == "296-LM7805"


@responses.activate
def test_search_description_as_string():
    """DigiKey sometimes returns Description as a plain string, not a dict."""
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": "5V Regulator Plain String", "DatasheetUrl": "",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result["description"] == "5V Regulator Plain String"


@responses.activate
def test_search_no_products():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL, json={"Products": []}, status=200)
    assert digikey_search("XYZFAKE", client_id="id", client_secret="secret") is None


@responses.activate
def test_search_no_image():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "",
                       "Description": "5V Reg", "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    assert digikey_search("LM7805", client_id="id", client_secret="secret") is None


@responses.activate
def test_search_fallback_to_first():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805CT", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": {"ProductDescription": "5V Reg CT"}, "DatasheetUrl": "",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result is not None


@responses.activate
def test_search_api_error_raises():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL, json={"error": "Server Error"}, status=500)
    with pytest.raises(Exception):
        digikey_search("LM7805", client_id="id", client_secret="secret")


@responses.activate
def test_null_datasheet():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": {"ProductDescription": "5V"}, "DatasheetUrl": "",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result["datasheet_url"] is None
```

**Step 2: Run tests and commit**

Run: `. .venv/bin/activate && pytest tests/test_digikey.py -v`

```bash
git add tests/test_digikey.py
git commit -m "Add comprehensive tests for digikey.py"
```

---

### Task 9: New Tests — test_batch.py

**Files:**
- Create: `tests/test_batch.py`

**Step 1: Write tests**

```python
"""Tests for magpiebom.batch module."""

import argparse
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from magpiebom.batch import _read_part_numbers, batch_main


def _make_args(parts=None, output_dir="./parts", verbose=False):
    return argparse.Namespace(parts=parts or [], output_dir=output_dir, verbose=verbose)


def test_read_from_args():
    args = _make_args(parts=["LM7805", "NE555"])
    result = _read_part_numbers(args)
    assert result == ["LM7805", "NE555"]


def test_read_from_file(tmp_path):
    f = tmp_path / "parts.txt"
    f.write_text("LM7805\n# comment\nNE555\n\n  LM317  \n")
    args = _make_args(parts=[str(f)])
    result = _read_part_numbers(args)
    assert result == ["LM7805", "NE555", "LM317"]


def test_read_filters_comments_and_blanks(tmp_path):
    f = tmp_path / "parts.txt"
    f.write_text("# Header comment\nLM7805\n\n# Another comment\n")
    args = _make_args(parts=[str(f)])
    result = _read_part_numbers(args)
    assert result == ["LM7805"]


def test_read_nonexistent_file_treated_as_part_number():
    args = _make_args(parts=["NOT_A_FILE_LM7805"])
    result = _read_part_numbers(args)
    assert result == ["NOT_A_FILE_LM7805"]


def test_read_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", StringIO("LM7805\nNE555\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    args = _make_args(parts=[])
    result = _read_part_numbers(args)
    assert result == ["LM7805", "NE555"]


def test_read_empty_args_tty():
    """No parts and tty stdin should return empty list."""
    args = _make_args(parts=[])
    # stdin.isatty() returns True by default in test environments
    result = _read_part_numbers(args)
    assert result == []


@patch("magpiebom.batch.run_pipeline")
@patch("magpiebom.batch.generate_report", return_value="./parts/report.html")
def test_batch_main_processes_parts(mock_report, mock_pipeline):
    mock_pipeline.side_effect = [
        {"part_number": "LM7805", "image_path": "./parts/LM7805.jpg"},
        {"part_number": "NE555", "image_path": None},
    ]
    args = _make_args(parts=["LM7805", "NE555"])
    batch_main(args)
    assert mock_pipeline.call_count == 2
    mock_report.assert_called_once()


@patch("magpiebom.batch.run_pipeline")
def test_batch_main_exits_on_empty_parts(mock_pipeline):
    args = _make_args(parts=[])
    with pytest.raises(SystemExit) as exc_info:
        batch_main(args)
    assert exc_info.value.code == 1
    mock_pipeline.assert_not_called()
```

**Step 2: Run tests and commit**

Run: `. .venv/bin/activate && pytest tests/test_batch.py -v`

```bash
git add tests/test_batch.py
git commit -m "Add comprehensive tests for batch.py"
```

---

### Task 10: New Tests — test_report.py

**Files:**
- Create: `tests/test_report.py`

**Step 1: Write tests**

```python
"""Tests for magpiebom.report module."""

from pathlib import Path

import pytest
from conftest import TINY_PNG
from magpiebom.report import generate_report, _image_to_data_uri, _escape


def test_image_to_data_uri_png(tmp_path):
    img = tmp_path / "test.png"
    img.write_bytes(TINY_PNG)
    uri = _image_to_data_uri(str(img))
    assert uri.startswith("data:image/png;base64,")


def test_image_to_data_uri_jpg(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG magic bytes
    uri = _image_to_data_uri(str(img))
    assert uri.startswith("data:image/jpeg;base64,")


def test_image_to_data_uri_unknown_extension(tmp_path):
    img = tmp_path / "test.xyz"
    img.write_bytes(b"data")
    uri = _image_to_data_uri(str(img))
    assert uri.startswith("data:image/jpeg;base64,")  # Falls back to jpeg


def test_escape_special_chars():
    assert _escape("<script>alert('xss')</script>") == "&lt;script&gt;alert('xss')&lt;/script&gt;"
    assert _escape('He said "hello"') == 'He said &quot;hello&quot;'
    assert _escape("A & B") == "A &amp; B"


def test_escape_plain_text():
    assert _escape("LM7805 Voltage Regulator") == "LM7805 Voltage Regulator"


def test_generate_report_found(tmp_path):
    img = tmp_path / "LM7805.png"
    img.write_bytes(TINY_PNG)
    results = [{"part_number": "LM7805", "image_path": str(img), "description": "5V Regulator",
                "source": "mouser", "source_url": "https://mouser.com/LM7805", "datasheet_url": "https://mouser.com/ds.pdf"}]
    report_path = generate_report(results, str(tmp_path))
    assert Path(report_path).exists()
    html = Path(report_path).read_text()
    assert "LM7805" in html
    assert "5V Regulator" in html
    assert 'class="found"' in html
    assert "data:image/png;base64," in html


def test_generate_report_not_found(tmp_path):
    results = [{"part_number": "XYZFAKE", "image_path": None, "description": "",
                "source": "not_found", "source_url": "", "datasheet_url": None}]
    report_path = generate_report(results, str(tmp_path))
    html = Path(report_path).read_text()
    assert "XYZFAKE" in html
    assert 'class="not-found"' in html


def test_generate_report_mixed(tmp_path):
    img = tmp_path / "LM7805.png"
    img.write_bytes(TINY_PNG)
    results = [
        {"part_number": "LM7805", "image_path": str(img), "description": "5V Reg",
         "source": "mouser", "source_url": "", "datasheet_url": None},
        {"part_number": "FAKE", "image_path": None, "description": "",
         "source": "not_found", "source_url": "", "datasheet_url": None},
    ]
    report_path = generate_report(results, str(tmp_path))
    html = Path(report_path).read_text()
    assert "1 found" in html
    assert "1 not found" in html
    assert "2 total" in html


def test_generate_report_empty(tmp_path):
    report_path = generate_report([], str(tmp_path))
    html = Path(report_path).read_text()
    assert "0 found" in html


def test_generate_report_html_escaping(tmp_path):
    results = [{"part_number": '<script>alert("xss")</script>', "image_path": None,
                "description": "A & B", "source": "", "source_url": "", "datasheet_url": None}]
    report_path = generate_report(results, str(tmp_path))
    html = Path(report_path).read_text()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "A &amp; B" in html
```

**Step 2: Run tests and commit**

Run: `. .venv/bin/activate && pytest tests/test_report.py -v`

```bash
git add tests/test_report.py
git commit -m "Add comprehensive tests for report.py"
```

---

### Task 11: New Tests — test_server.py

**Files:**
- Create: `tests/test_server.py`

**Step 1: Write tests**

```python
"""Tests for magpiebom.server module."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from magpiebom.server import app, _result_to_part, _load_results, _save_results


@pytest.fixture
def client(tmp_path):
    """Flask test client with PARTS_DIR set to tmp_path."""
    with patch("magpiebom.server.PARTS_DIR", tmp_path):
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c, tmp_path


def _create_batch(tmp_path, batch_id, parts):
    batch_dir = tmp_path / batch_id
    batch_dir.mkdir(parents=True)
    data = {"created": "2026-03-04T22:00:00", "parts": parts}
    (batch_dir / "results.json").write_text(json.dumps(data))
    return batch_dir


def test_home_empty(client):
    c, tmp_path = client
    resp = c.get("/")
    assert resp.status_code == 200


def test_home_lists_batches(client):
    c, tmp_path = client
    _create_batch(tmp_path, "batch_2026-03-04_22-00-00", [
        {"part_number": "LM7805", "image_path": "LM7805.png", "source": "mouser"},
    ])
    resp = c.get("/")
    assert resp.status_code == 200
    assert b"batch_2026-03-04_22-00-00" in resp.data


def test_batch_new_creates_batch(client):
    c, tmp_path = client
    resp = c.post("/batch/new", data={"parts": "LM7805\nNE555"}, follow_redirects=False)
    assert resp.status_code == 302
    # Should have created a batch directory
    batches = list(tmp_path.glob("batch_*"))
    assert len(batches) == 1
    data = json.loads((batches[0] / "results.json").read_text())
    assert len(data["parts"]) == 2
    assert data["parts"][0]["part_number"] == "LM7805"


def test_batch_new_empty_redirects_home(client):
    c, tmp_path = client
    resp = c.post("/batch/new", data={"parts": ""}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_batch_view(client):
    c, tmp_path = client
    _create_batch(tmp_path, "batch_test", [
        {"part_number": "LM7805", "image_path": "LM7805.png", "source": "mouser",
         "description": "5V Reg", "source_url": "", "datasheet_url": None, "datasheet_path": None},
    ])
    resp = c.get("/batch/batch_test")
    assert resp.status_code == 200
    assert b"LM7805" in resp.data


def test_batch_image_serving(client):
    c, tmp_path = client
    batch_dir = tmp_path / "batch_test"
    batch_dir.mkdir()
    (batch_dir / "LM7805.png").write_bytes(b"\x89PNG")
    resp = c.get("/batch/batch_test/images/LM7805.png")
    assert resp.status_code == 200


def test_result_to_part_with_paths():
    result = {"image_path": "/full/path/LM7805.png", "datasheet_path": "/full/path/LM7805.pdf",
              "datasheet_url": "https://example.com/ds.pdf", "description": "5V Reg",
              "source": "mouser", "source_url": "https://mouser.com/LM7805"}
    part = _result_to_part("LM7805", result)
    assert part["image_path"] == "LM7805.png"  # Basename only
    assert part["datasheet_path"] == "LM7805.pdf"  # Basename only
    assert part["part_number"] == "LM7805"


def test_result_to_part_none_paths():
    result = {"image_path": None, "datasheet_path": None, "datasheet_url": None,
              "description": "", "source": "", "source_url": ""}
    part = _result_to_part("FAKE", result)
    assert part["image_path"] is None
    assert part["source"] == "not_found"


def test_load_save_results(tmp_path):
    with patch("magpiebom.server.PARTS_DIR", tmp_path):
        batch_dir = tmp_path / "test_batch"
        batch_dir.mkdir()
        data = {"created": "2026-01-01", "parts": []}
        _save_results("test_batch", data)
        loaded = _load_results("test_batch")
        assert loaded == data


def test_batch_stream_sse_format(client):
    c, tmp_path = client
    _create_batch(tmp_path, "batch_stream", [
        {"part_number": "LM7805", "image_path": None, "source": "",
         "source_url": "", "description": "", "datasheet_url": None, "datasheet_path": None},
    ])
    with patch("magpiebom.server.run_pipeline") as mock_pipeline:
        mock_pipeline.return_value = {
            "part_number": "LM7805", "image_path": "LM7805.png", "source": "web",
            "source_url": "", "description": "5V Reg", "datasheet_url": None, "datasheet_path": None,
        }
        resp = c.get("/batch/batch_stream/stream")
        assert resp.status_code == 200
        assert resp.content_type == "text/event-stream"
        data = resp.get_data(as_text=True)
        assert "event: status" in data
        assert "event: result" in data
        assert "event: done" in data


def test_batch_retry_part_not_found(client):
    c, tmp_path = client
    _create_batch(tmp_path, "batch_retry", [
        {"part_number": "LM7805", "image_path": None, "source": "",
         "source_url": "", "description": "", "datasheet_url": None, "datasheet_path": None},
    ])
    resp = c.get("/batch/batch_retry/retry/NONEXISTENT")
    data = resp.get_data(as_text=True)
    assert "event: error" in data
```

**Step 2: Run tests and commit**

Run: `. .venv/bin/activate && pytest tests/test_server.py -v`

```bash
git add tests/test_server.py
git commit -m "Add comprehensive tests for server.py"
```

---

### Task 12: Improve Existing Tests — test_images.py

**Files:**
- Modify: `tests/test_images.py`

**Step 1: Add missing tests**

Add these tests to the existing file:

```python
from magpiebom.images import _get_extension, _download_requests


@responses.activate
def test_download_image_rejects_non_image_content_type():
    responses.add(responses.GET, "https://example.com/blocked.jpg",
                  body=b"<html>Access Denied</html>", content_type="text/html", status=200)
    assert download_image("https://example.com/blocked.jpg") is None


@responses.activate
def test_download_image_timeout():
    responses.add(responses.GET, "https://example.com/slow.jpg",
                  body=ConnectionError("Connection timed out"))
    assert download_image("https://example.com/slow.jpg") is None


def test_get_extension_from_url():
    assert _get_extension("https://example.com/part.png", "") == ".png"
    assert _get_extension("https://example.com/part.jpeg", "") == ".jpeg"
    assert _get_extension("https://example.com/part.webp", "") == ".webp"


def test_get_extension_from_content_type():
    assert _get_extension("https://example.com/part", "image/png") == ".png"
    assert _get_extension("https://example.com/part", "image/jpeg") == ".jpg"
    assert _get_extension("https://example.com/part", "image/webp") == ".webp"


def test_get_extension_fallback():
    assert _get_extension("https://example.com/part", "application/octet-stream") == ".jpg"
    assert _get_extension("https://example.com/part", "") == ".jpg"


def test_save_final_image_creates_output_dir(tmp_path):
    src = tmp_path / "temp.png"
    src.write_bytes(TINY_PNG)
    output_dir = tmp_path / "nested" / "output"
    result = save_final_image(str(src), "LM7805", str(output_dir))
    assert Path(result).exists()
    assert output_dir.exists()


def test_save_final_image_sanitizes_filename(tmp_path):
    src = tmp_path / "temp.png"
    src.write_bytes(TINY_PNG)
    result = save_final_image(str(src), "Part/Number@Special#Chars", str(tmp_path / "out"))
    assert Path(result).exists()
    assert "/" not in Path(result).name
    assert "@" not in Path(result).name
```

**Step 2: Run tests and commit**

Run: `. .venv/bin/activate && pytest tests/test_images.py -v`

```bash
git add tests/test_images.py
git commit -m "Add edge case tests for images.py"
```

---

### Task 13: Improve Existing Tests — test_scraper.py and test_search.py

**Files:**
- Modify: `tests/test_scraper.py`
- Modify: `tests/test_search.py`

**Step 1: Add `_extract_datasheets` tests to test_scraper.py**

```python
from magpiebom.scraper import _extract_datasheets, _parse_int


def test_extract_datasheets_from_links():
    html = '<html><body><a href="https://example.com/datasheet.pdf">Datasheet</a></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _extract_datasheets(soup, html, "https://example.com")
    assert result == ["https://example.com/datasheet.pdf"]


def test_extract_datasheets_skips_terms():
    html = '<html><body><a href="https://example.com/terms.pdf">Terms</a><a href="https://example.com/ds.pdf">DS</a></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _extract_datasheets(soup, html, "https://example.com")
    assert "https://example.com/terms.pdf" not in result
    assert "https://example.com/ds.pdf" in result


def test_extract_datasheets_regex_fallback():
    html = '<html><body><script>var url = "https://cdn.example.com/LM7805.pdf";</script></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _extract_datasheets(soup, html, "https://example.com")
    assert "https://cdn.example.com/LM7805.pdf" in result


def test_extract_datasheets_limits_to_three():
    links = "".join(f'<a href="https://example.com/ds{i}.pdf">DS{i}</a>' for i in range(10))
    html = f"<html><body>{links}</body></html>"
    soup = BeautifulSoup(html, "lxml")
    result = _extract_datasheets(soup, html, "https://example.com")
    assert len(result) <= 3


def test_parse_int_valid():
    assert _parse_int("100") == 100
    assert _parse_int(200) == 200


def test_parse_int_invalid():
    assert _parse_int(None) is None
    assert _parse_int("abc") is None
    assert _parse_int("") is None
```

**Step 2: Add `_site_priority` tests to test_search.py**

```python
from magpiebom.search import _site_priority


def test_site_priority_known():
    assert _site_priority("https://www.mouser.com/LM7805") == 0
    assert _site_priority("https://www.digikey.com/product/LM7805") == 0
    assert _site_priority("https://lcsc.com/product-detail/foo") == 0


def test_site_priority_unknown():
    assert _site_priority("https://blog.example.com/review") == 1
    assert _site_priority("https://randomsite.org/part") == 1


@responses.activate
def test_brave_search_custom_query_template():
    responses.add(responses.GET, "https://api.search.brave.com/res/v1/web/search",
                  json={"web": {"results": []}}, status=200)
    brave_search("LM7805", api_key="key", query_template="{part} datasheet pdf")
    assert "LM7805 datasheet pdf" in responses.calls[0].request.params.get("q", "")
```

**Step 3: Run tests and commit**

Run: `. .venv/bin/activate && pytest tests/test_scraper.py tests/test_search.py -v`

```bash
git add tests/test_scraper.py tests/test_search.py
git commit -m "Add tests for _extract_datasheets, _parse_int, _site_priority"
```

---

### Task 14: Improve Existing Tests — test_cli.py Error Paths

**Files:**
- Modify: `tests/test_cli.py`

**Step 1: Add error path tests**

```python
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {})
def test_run_pipeline_missing_brave_api_key(mock_dotenv):
    """Should return empty result when BRAVE_API_KEY is not set."""
    result = run_pipeline("LM7805", output_dir="./parts", no_open=True)
    assert result["image_path"] is None
    assert result["source"] == ""


@patch("magpiebom.cli.Tracer")
@patch("magpiebom.cli.brave_search", return_value=[])
@patch("magpiebom.cli.get_model_name", return_value="test-model")
@patch("magpiebom.cli.OpenAI")
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {"BRAVE_API_KEY": "test-key"})
def test_run_pipeline_no_search_results(mock_dotenv, mock_openai, mock_model, mock_search, mock_tracer):
    """Should return empty result when all searches return nothing."""
    mock_tracer.return_value.__enter__ = MagicMock(return_value=mock_tracer.return_value)
    mock_tracer.return_value.__exit__ = MagicMock(return_value=False)
    mock_tracer.return_value.trace_path = "/tmp/fake-trace.jsonl"
    result = run_pipeline("XYZNONEXISTENT", output_dir="./parts", no_open=True)
    assert result["image_path"] is None
```

Also add a test for `_download_datasheet`:

```python
from magpiebom.cli import _download_datasheet

@responses.activate
def test_download_datasheet_success(tmp_path):
    pdf_content = b"%PDF-1.4 fake pdf content"
    resp_mock.add(resp_mock.GET, "https://example.com/ds.pdf", body=pdf_content,
                  content_type="application/pdf", status=200)
    result = _download_datasheet("https://example.com/ds.pdf", "LM7805", str(tmp_path))
    assert result is not None
    assert Path(result).exists()
    assert Path(result).read_bytes() == pdf_content


@responses.activate
def test_download_datasheet_not_pdf(tmp_path):
    resp_mock.add(resp_mock.GET, "https://example.com/fake.pdf", body=b"<html>Not a PDF</html>",
                  content_type="text/html", status=200)
    result = _download_datasheet("https://example.com/fake.pdf", "LM7805", str(tmp_path))
    assert result is None


@responses.activate
def test_download_datasheet_bad_magic_bytes(tmp_path):
    resp_mock.add(resp_mock.GET, "https://example.com/bad.pdf", body=b"NOT-PDF-CONTENT",
                  content_type="application/pdf", status=200)
    result = _download_datasheet("https://example.com/bad.pdf", "LM7805", str(tmp_path))
    assert result is None
```

**Step 2: Update imports to include `_download_datasheet` and renamed `_fix_broken_urls`**

**Step 3: Run tests and commit**

Run: `. .venv/bin/activate && pytest tests/test_cli.py -v`

```bash
git add tests/test_cli.py
git commit -m "Add error path and _download_datasheet tests to test_cli.py"
```

---

### Task 15: Final Verification

**Step 1: Run full test suite**

Run: `. .venv/bin/activate && pytest tests/ -v`
Expected: All tests pass (should be ~140+ tests now).

**Step 2: Run with coverage (if available)**

Run: `. .venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -20`

**Step 3: Verify no import errors**

Run: `python -c "import magpiebom.cli; import magpiebom.batch; import magpiebom.server; import magpiebom.types; import magpiebom.constants; print('All imports OK')"`

**Step 4: Final commit**

If any final adjustments were needed, commit them. Otherwise, tag the work done:
```bash
git log --oneline -15
```
