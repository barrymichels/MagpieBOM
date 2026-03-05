# MagpieBOM Audit Remediation Design

## Context

A full codebase audit identified ~30 issues across code quality, test coverage, dead code, and architecture. This design addresses all findings with practical refactoring (no abstract base classes or strategy patterns).

## Execution Order: Bottom-Up

Each layer builds on the previous. Shared infrastructure makes writing tests easier. Tests provide a safety net before the big cli.py refactor.

## Section 1: Quick Fixes

1. Remove unused `extract_description` import from `cli.py:18`
2. Remove orphaned `main()` function from `server.py:215-223`
3. Move `import requests` to top level in `cli.py` (currently imported locally at lines 81 and 335)

## Section 2: Shared Infrastructure

### 2a. Constants module (`magpiebom/constants.py`)

Consolidate duplicated and scattered constants:

- `BROWSER_UA` — currently in `images.py:12` and hardcoded in `cli.py:87,338`
- `SKIP_PDF_PATTERNS` — identical in `cli.py:264` and `scraper.py:185`
- `MAX_PAGES_PER_SEARCH` (5), `MAX_SOURCES_FOR_EXTRACTION` (10), `MAX_SEARCH_RESULTS` (15)

Import from `constants.py` in `cli.py`, `images.py`, and `scraper.py`.

### 2b. TypedDicts (`magpiebom/types.py`)

Typed contracts for all dict returns:

- `SupplierResult` — base with description, image_url, datasheet_url, manufacturer
- `MouserResult(SupplierResult)` — adds mouser_pn, product_detail_url
- `DigiKeyResult(SupplierResult)` — adds digikey_pn
- `PipelineResult` — part_number, image_path, datasheet_url, datasheet_path, description, source, source_url
- `TextSignals` — title, meta_description, meta_keywords, url_path, url_category, paragraphs
- `PageInfo` — text_signals, image_urls, datasheet_urls

Update function signatures to use these types.

### 2c. Shared test fixtures (`tests/conftest.py`)

- `TINY_PNG` constant (deduplicated from 3 test files)
- `tiny_png_path(tmp_path)` fixture
- `mock_llm_client()` fixture

## Section 3: Error Handling

### 3a. Fix 6 bare `except Exception` clauses

| Location | Fix |
|---|---|
| `cli.py:96` _probe_url | `except (requests.RequestException, OSError)` |
| `cli.py:437` Mouser | `except requests.RequestException as e: tracer.error(...)` |
| `cli.py:477` DigiKey | Same |
| `images.py:76` chunk write | `except (IOError, OSError)` |
| `images.py:116` Playwright | Initialize `tmp = None` before try, check `if tmp` in cleanup |
| `server.py:140,190` | Keep broad catch (outermost SSE handler) but log to stderr |

### 3b. Fix UnboundLocalError trap (`images.py:116-120`)

Initialize `tmp = None` before the try block, replace `except UnboundLocalError: pass` with `if tmp:` guard.

### 3c. Rename `_validate_urls` to `_fix_broken_urls`

The function modifies result dict, deletes files, and makes network requests — name should reflect side effects.

## Section 4: Refactor cli.py

### 4a. Extract `_try_supplier_api()`

Shared handler for both Mouser and DigiKey paths (currently ~80 lines of near-identical code). Takes a search function and kwargs, returns `PipelineResult | None`.

### 4b. Extract `_try_web_search()`

Move Phase 1/2/3 block (lines 480-624) into a dedicated function handling Brave search, page scraping, description extraction, and image validation.

### 4c. Extract `_finalize_result()`

The repeated pattern of validate URLs, download datasheet, open file, log trace appears 3 times. Consolidate into one function.

### Net effect

`run_pipeline()` shrinks from 255 lines to ~40 lines of setup + dispatch.

## Section 5: Comprehensive Tests

### New test files

| File | Module | Key tests |
|---|---|---|
| `test_mouser.py` | mouser.py | Exact match, fallback to first, no results, no image, protocol-relative URLs, API errors (401/429/500), timeout, malformed JSON |
| `test_digikey.py` | digikey.py | Token exchange, search with exact match, fallback, Description dict vs string, no results, no image, token/search errors |
| `test_batch.py` | batch.py | Read from args/file/stdin, comment filtering, empty input, file not found fallback, batch_main happy/empty paths |
| `test_report.py` | report.py | Image to data URI (JPEG/PNG/unknown), HTML escaping (special chars), full report (found/not-found/mixed), missing image, empty results |
| `test_server.py` | server.py | Home page, batch_new, batch_view, batch_stream SSE, batch_retry, batch_image, error cases (missing batch, corrupt JSON), _result_to_part edges |

### Improvements to existing tests

| File | Changes |
|---|---|
| test_cli.py | Reduce mock count (mock at HTTP boundaries); add error path tests (missing BRAVE_API_KEY, LLM failure, all images fail); add _download_datasheet tests; use conftest fixtures |
| test_images.py | Playwright fallback, timeout, content-type rejection, _get_extension edges; use tmp_path |
| test_scraper.py | _extract_datasheets tests, aspect ratio filtering, _parse_int edges |
| test_validator.py | Fix temp file cleanup (tmp_path), wrong-field-name JSON, missing url_category field |
| test_search.py | _site_priority direct tests, special chars, sort stability |

### Test approach

- Mock at HTTP/LLM/filesystem boundaries, not internal functions
- `@responses.activate` for HTTP mocking
- Flask test client for server tests
- `tmp_path` fixture everywhere

## Section 6: Final Cleanup

1. Add missing type hints: `batch.py` args (`argparse.Namespace`), `server.py` return types
2. Run full test suite to verify nothing broke
3. Run a real pipeline test to verify end-to-end behavior
