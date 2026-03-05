# tests/test_cli.py
from unittest.mock import patch, MagicMock, call
import responses as resp_mock
from magpiebom.cli import parse_args, run_pipeline, _is_url_structurally_valid, _probe_url, _find_source_url_fallback, _validate_urls, _search_datasheet_url, _scrape_datasheet_playwright


def _mock_tracer_cls():
    """Create a mock Tracer class that supports context manager protocol."""
    mock_cls = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=mock_cls.return_value)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_cls.return_value.trace_path = "/tmp/fake-trace.jsonl"
    return mock_cls


def _text_signals(title="", meta_description="", meta_keywords="", url_path="/", paragraphs=None):
    """Helper to build a text_signals dict."""
    return {
        "title": title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords,
        "url_path": url_path,
        "paragraphs": paragraphs or [],
    }


def test_parse_args_minimal():
    args = parse_args(["search", "LM7805"])
    assert args.part_number == "LM7805"
    assert args.output_dir == "./parts"
    assert args.no_open is False
    assert args.verbose is False


def test_parse_args_all_flags():
    args = parse_args(["search", "--output-dir", "/tmp/out", "--no-open", "-v", "NE555"])
    assert args.part_number == "NE555"
    assert args.output_dir == "/tmp/out"
    assert args.no_open is True
    assert args.verbose is True


def test_parse_args_search_subcommand():
    args = parse_args(["search", "LM7805"])
    assert args.command == "search"
    assert args.part_number == "LM7805"
    assert args.output_dir == "./parts"
    assert args.no_open is False
    assert args.verbose is False


def test_parse_args_search_all_flags():
    args = parse_args(["search", "--output-dir", "/tmp/out", "--no-open", "-v", "NE555"])
    assert args.command == "search"
    assert args.part_number == "NE555"
    assert args.output_dir == "/tmp/out"
    assert args.no_open is True
    assert args.verbose is True


def test_parse_args_batch_subcommand():
    args = parse_args(["batch", "LM7805", "NE555"])
    assert args.command == "batch"
    assert args.parts == ["LM7805", "NE555"]


def test_parse_args_server_subcommand():
    args = parse_args(["server"])
    assert args.command == "server"


@patch("magpiebom.cli.Tracer")
@patch("magpiebom.cli._validate_urls")
@patch("magpiebom.cli.brave_search")
@patch("magpiebom.cli.scrape_page")
@patch("magpiebom.cli.download_image")
@patch("magpiebom.cli.validate_image")
@patch("magpiebom.cli.extract_description_from_sources", return_value="LM7805 5V regulator")
@patch("magpiebom.cli.save_final_image")
@patch("magpiebom.cli.get_model_name", return_value="test-model")
@patch("magpiebom.cli.OpenAI")
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {"BRAVE_API_KEY": "test-key"})
def test_run_pipeline_success(
    mock_dotenv, mock_openai_cls, mock_get_model, mock_save, mock_extract_sources,
    mock_validate, mock_download, mock_scrape, mock_search, mock_validate_urls,
    mock_tracer_cls
):
    mock_tracer_cls.return_value.__enter__ = MagicMock(return_value=mock_tracer_cls.return_value)
    mock_tracer_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_tracer_cls.return_value.trace_path = "/tmp/fake-trace.jsonl"

    mock_search.return_value = [
        {"url": "https://example.com/part", "title": "LM7805 Voltage Regulator", "description": "LM7805 5V regulator"},
    ]
    mock_scrape.return_value = {
        "text_signals": _text_signals(title="LM7805 Voltage Regulator", meta_description="LM7805 5V regulator", meta_keywords="LM7805"),
        "image_urls": ["https://example.com/part.jpg"],
        "datasheet_urls": [],
    }
    mock_download.return_value = "/tmp/part.jpg"
    mock_validate.return_value = {"match": True, "reason": "Looks correct"}
    mock_save.return_value = "./parts/LM7805.jpg"

    result = run_pipeline("LM7805", output_dir="./parts", no_open=True, verbose=False)
    assert result["image_path"] == "./parts/LM7805.jpg"
    assert result["part_number"] == "LM7805"
    assert result["source"] == "web"


@patch("magpiebom.cli.Tracer")
@patch("magpiebom.cli.brave_search")
@patch("magpiebom.cli.scrape_page")
@patch("magpiebom.cli.download_image")
@patch("magpiebom.cli.validate_image")
@patch("magpiebom.cli.extract_description_from_sources", return_value="XYZFAKE part")
@patch("magpiebom.cli.get_model_name", return_value="test-model")
@patch("magpiebom.cli.OpenAI")
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {"BRAVE_API_KEY": "test-key"})
def test_run_pipeline_no_match(
    mock_dotenv, mock_openai_cls, mock_get_model, mock_extract_sources,
    mock_validate, mock_download, mock_scrape, mock_search,
    mock_tracer_cls
):
    mock_tracer_cls.return_value.__enter__ = MagicMock(return_value=mock_tracer_cls.return_value)
    mock_tracer_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_tracer_cls.return_value.trace_path = "/tmp/fake-trace.jsonl"

    mock_search.return_value = [
        {"url": "https://example.com/part", "title": "XYZFAKE Component", "description": "XYZFAKE part"},
    ]
    mock_scrape.return_value = {
        "text_signals": _text_signals(title="XYZFAKE Component", meta_description="XYZFAKE part", meta_keywords="XYZFAKE"),
        "image_urls": ["https://example.com/img.jpg"],
        "datasheet_urls": [],
    }
    mock_download.return_value = "/tmp/img.jpg"
    mock_validate.return_value = {"match": False, "reason": "Wrong part"}

    result = run_pipeline("XYZFAKE", output_dir="./parts", no_open=True, verbose=False)
    assert result["image_path"] is None


@patch("magpiebom.cli.Tracer")
@patch("magpiebom.cli._validate_urls")
@patch("magpiebom.cli.brave_search")
@patch("magpiebom.cli.scrape_page")
@patch("magpiebom.cli.download_image")
@patch("magpiebom.cli.validate_image")
@patch("magpiebom.cli.extract_description_from_sources", return_value="8-pin connector")
@patch("magpiebom.cli.save_final_image")
@patch("magpiebom.cli.get_model_name", return_value="test-model")
@patch("magpiebom.cli.OpenAI")
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {"BRAVE_API_KEY": "test-key"})
def test_run_pipeline_skips_wrong_part_number(
    mock_dotenv, mock_openai_cls, mock_get_model, mock_save, mock_extract_sources,
    mock_validate, mock_download, mock_scrape, mock_search, mock_validate_urls,
    mock_tracer_cls
):
    """Pages about a different part variant should be skipped without LLM image calls."""
    mock_tracer_cls.return_value.__enter__ = MagicMock(return_value=mock_tracer_cls.return_value)
    mock_tracer_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_tracer_cls.return_value.trace_path = "/tmp/fake-trace.jsonl"

    mock_search.return_value = [
        {"url": "https://example.com/wrong", "title": "B-2100S04P-A110", "description": "4-pin connector"},
        {"url": "https://example.com/right", "title": "B-2100S08P-B110", "description": "8-pin connector"},
    ]
    mock_scrape.side_effect = [
        {
            "text_signals": _text_signals(title="B-2100S04P-A110", meta_description="B-2100S04P-A110 4-pin connector"),
            "image_urls": ["https://example.com/wrong.jpg"],
            "datasheet_urls": [],
        },
        {
            "text_signals": _text_signals(title="B-2100S08P-B110", meta_description="B-2100S08P-B110 8-pin connector"),
            "image_urls": ["https://example.com/right.jpg"],
            "datasheet_urls": [],
        },
    ]
    mock_download.return_value = "/tmp/right.jpg"
    mock_validate.return_value = {"match": True, "reason": "Correct 8-pin connector"}
    mock_save.return_value = "./parts/B-2100S08P-B110.jpg"

    result = run_pipeline("B-2100S08P-B110", output_dir="./parts", no_open=True, verbose=False)
    assert result["image_path"] == "./parts/B-2100S08P-B110.jpg"
    # The wrong part's image should never have been downloaded
    mock_download.assert_called_once_with("https://example.com/right.jpg", tracer=mock_tracer_cls.return_value)


def test_structurally_valid_url():
    assert _is_url_structurally_valid("https://www.mouser.com/ProductDetail/123") is True


def test_empty_url_invalid():
    assert _is_url_structurally_valid("") is False
    assert _is_url_structurally_valid(None) is False
    assert _is_url_structurally_valid("   ") is False


def test_digikey_placeholder_invalid():
    assert _is_url_structurally_valid("https://www.digikey.com/en/products/detail/-/-/") is False
    assert _is_url_structurally_valid("https://www.digikey.com/en/products/detail/-/-/ABC123") is True


def test_truncated_datasheet_url():
    assert _is_url_structurally_valid(
        "https://yageogroup.com/content/datasheet/asset/file/UPY-GPHC_X7R_6_3V-TO-250V"
    ) is True


def test_non_http_url_invalid():
    assert _is_url_structurally_valid("ftp://example.com/file") is False
    assert _is_url_structurally_valid("not-a-url") is False


# --- _probe_url tests ---

@resp_mock.activate
def test_probe_url_success():
    resp_mock.add(resp_mock.HEAD, "https://example.com/good", status=200)
    assert _probe_url("https://example.com/good") is True


@resp_mock.activate
def test_probe_url_redirect_ok():
    resp_mock.add(resp_mock.HEAD, "https://example.com/redir", status=301,
                  headers={"Location": "https://example.com/final"})
    resp_mock.add(resp_mock.HEAD, "https://example.com/final", status=200)
    assert _probe_url("https://example.com/redir") is True


@resp_mock.activate
def test_probe_url_404():
    resp_mock.add(resp_mock.HEAD, "https://example.com/missing", status=404)
    assert _probe_url("https://example.com/missing") is False


@resp_mock.activate
def test_probe_url_timeout():
    resp_mock.add(resp_mock.HEAD, "https://example.com/slow",
                  body=ConnectionError("timeout"))
    assert _probe_url("https://example.com/slow") is False


def test_probe_url_none():
    assert _probe_url(None) is False
    assert _probe_url("") is False


# --- _search_datasheet_url tests ---

@patch("magpiebom.cli.brave_search")
def test_search_datasheet_skips_unrelated_pdf(mock_search):
    """Datasheet search should skip PDFs whose title/description don't mention the part."""
    mock_search.return_value = [
        {"url": "https://www.farnell.com/datasheets/308650.pdf",
         "title": "Some Other Connector Datasheet", "description": "Random connector PDF"},
        {"url": "https://www.molex.com/pdm_docs/sd/395021002_sd.pdf",
         "title": "39502-1002 Datasheet", "description": "Molex 39502-1002 terminal block"},
    ]
    result = _search_datasheet_url("39502-1002", "test-key")
    assert result == "https://www.molex.com/pdm_docs/sd/395021002_sd.pdf"

@patch("magpiebom.cli.brave_search")
def test_search_datasheet_returns_none_when_no_match(mock_search):
    """Should return None when no PDF results mention the part number."""
    mock_search.return_value = [
        {"url": "https://www.farnell.com/datasheets/308650.pdf",
         "title": "Unrelated Part", "description": "Something else entirely"},
    ]
    result = _search_datasheet_url("39502-1002", "test-key")
    assert result is None

@patch("magpiebom.cli.brave_search")
def test_search_datasheet_matches_part_in_url(mock_search):
    """Should match when part number (stripped of dashes) appears in the URL."""
    mock_search.return_value = [
        {"url": "https://example.com/datasheets/395021002.pdf",
         "title": "Datasheet", "description": "PDF download"},
    ]
    result = _search_datasheet_url("39502-1002", "test-key")
    assert result == "https://example.com/datasheets/395021002.pdf"


# --- _scrape_datasheet_playwright tests ---

@patch("playwright.sync_api.sync_playwright")
def test_scrape_datasheet_playwright_finds_part_match(mock_pw_cls):
    """Should find PDF link whose URL contains the part number."""
    mock_page = MagicMock()
    mock_page.eval_on_selector_all.return_value = [
        {"href": "https://mouser.com/legal/terms.pdf", "text": "Terms"},
        {"href": "https://molex.com/pdm_docs/sd/395021002_sd.pdf", "text": "Datasheet"},
        {"href": "https://example.com/other.pdf", "text": "Other"},
    ]
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser
    mock_pw_cls.return_value.__enter__ = MagicMock(return_value=mock_pw)
    mock_pw_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = _scrape_datasheet_playwright("https://mouser.com/product/123", "39502-1002")
    assert result == "https://molex.com/pdm_docs/sd/395021002_sd.pdf"

@patch("playwright.sync_api.sync_playwright")
def test_scrape_datasheet_playwright_keyword_fallback(mock_pw_cls):
    """Should fall back to keyword match ('datasheet') when no part number in URL."""
    mock_page = MagicMock()
    mock_page.eval_on_selector_all.return_value = [
        {"href": "https://example.com/generic-ds.pdf", "text": "View Datasheet"},
        {"href": "https://example.com/brochure.pdf", "text": "Product Brochure"},
    ]
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser
    mock_pw_cls.return_value.__enter__ = MagicMock(return_value=mock_pw)
    mock_pw_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = _scrape_datasheet_playwright("https://mouser.com/product/123", "39502-1002")
    assert result == "https://example.com/generic-ds.pdf"

@patch("playwright.sync_api.sync_playwright")
def test_scrape_datasheet_playwright_no_pdfs(mock_pw_cls):
    """Should return None when no PDF links found."""
    mock_page = MagicMock()
    mock_page.eval_on_selector_all.return_value = [
        {"href": "https://example.com/page.html", "text": "Some Page"},
    ]
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser
    mock_pw_cls.return_value.__enter__ = MagicMock(return_value=mock_pw)
    mock_pw_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = _scrape_datasheet_playwright("https://mouser.com/product/123", "39502-1002")
    assert result is None


# --- _validate_urls with Playwright fallback ---

@patch("magpiebom.cli._scrape_datasheet_playwright", return_value="https://molex.com/ds.pdf")
@patch("magpiebom.cli._search_datasheet_url", return_value=None)
@patch("magpiebom.cli._probe_url", return_value=True)
def test_validate_urls_playwright_fallback_for_missing_datasheet(mock_probe, mock_search, mock_pw):
    """When no datasheet_url exists and Brave search fails, try Playwright on source_url."""
    result = {
        "part_number": "39502-1002",
        "source": "mouser",
        "source_url": "https://www.mouser.com/ProductDetail/Molex/39502-1002",
        "datasheet_url": None,
        "datasheet_path": None,
    }
    _validate_urls(result, api_key="key")
    assert result["datasheet_url"] == "https://molex.com/ds.pdf"
    mock_pw.assert_called_once_with(
        "https://www.mouser.com/ProductDetail/Molex/39502-1002", "39502-1002", tracer=None,
    )


# --- _find_source_url_fallback tests ---

@patch("magpiebom.cli.brave_search")
def test_find_source_url_fallback_digikey(mock_search):
    mock_search.return_value = [
        {"url": "https://www.digikey.com/en/products/detail/yageo/CC0603KRX7R7BB225/123",
         "title": "CC0603 Cap", "description": "..."},
    ]
    result = _find_source_url_fallback("CC0603KRX7R7BB225", "digikey", "test-key")
    assert result == "https://www.digikey.com/en/products/detail/yageo/CC0603KRX7R7BB225/123"
    mock_search.assert_called_once_with(
        "CC0603KRX7R7BB225", api_key="test-key", count=3,
        query_template="{part} site:digikey.com",
        tracer=None,
    )


@patch("magpiebom.cli.brave_search")
def test_find_source_url_fallback_no_results(mock_search):
    mock_search.return_value = []
    result = _find_source_url_fallback("XYZFAKE", "digikey", "test-key")
    assert result is None


def test_find_source_url_fallback_web_source():
    """Web source should not attempt fallback (already has real URL)."""
    result = _find_source_url_fallback("LM7805", "web", "test-key")
    assert result is None


# --- _validate_urls tests ---

@patch("magpiebom.cli._probe_url", return_value=True)
def test_validate_urls_all_good(mock_probe):
    result = {
        "part_number": "LM7805",
        "source": "mouser",
        "source_url": "https://www.mouser.com/ProductDetail/LM7805",
        "datasheet_url": "https://example.com/LM7805.pdf",
        "datasheet_path": "/tmp/LM7805.pdf",
    }
    _validate_urls(result, api_key="key")
    assert result["source_url"] == "https://www.mouser.com/ProductDetail/LM7805"
    assert result["datasheet_url"] == "https://example.com/LM7805.pdf"

@patch("magpiebom.cli._find_source_url_fallback", return_value=None)
@patch("magpiebom.cli._probe_url", return_value=False)
def test_validate_urls_bad_source_url_nulled(mock_probe, mock_fallback):
    result = {
        "part_number": "CC0603KRX7R7BB225",
        "source": "digikey",
        "source_url": "https://www.digikey.com/en/products/detail/-/-/",
        "datasheet_url": "https://example.com/good.pdf",
        "datasheet_path": None,
    }
    _validate_urls(result, api_key="key")
    assert result["source_url"] is None

@patch("magpiebom.cli._search_datasheet_url", return_value="https://example.com/replacement.pdf")
@patch("magpiebom.cli._probe_url", side_effect=lambda url, tracer=None: url != "https://bad.com/truncated")
def test_validate_urls_bad_datasheet_gets_replacement(mock_probe, mock_search):
    result = {
        "part_number": "ABC123",
        "source": "digikey",
        "source_url": "https://www.digikey.com/en/products/detail/mfr/ABC123/789",
        "datasheet_url": "https://bad.com/truncated",
        "datasheet_path": "/tmp/ABC123.pdf",
    }
    _validate_urls(result, api_key="key")
    assert result["datasheet_url"] == "https://example.com/replacement.pdf"

@patch("magpiebom.cli._search_datasheet_url", return_value=None)
@patch("magpiebom.cli._probe_url", return_value=False)
@patch("magpiebom.cli._find_source_url_fallback", return_value=None)
def test_validate_urls_bad_datasheet_nulled_cleans_path(mock_fallback, mock_probe, mock_search, tmp_path):
    pdf_file = tmp_path / "PART.pdf"
    pdf_file.write_text("fake pdf")
    result = {
        "part_number": "PART",
        "source": "mouser",
        "source_url": "https://www.mouser.com/ProductDetail/PART",
        "datasheet_url": "https://bad.com/broken",
        "datasheet_path": str(pdf_file),
    }
    _validate_urls(result, api_key="key")
    assert result["datasheet_url"] is None
    assert result["datasheet_path"] is None
    assert not pdf_file.exists()

@patch("magpiebom.cli.Tracer")
@patch("magpiebom.cli._validate_urls")
@patch("magpiebom.cli.brave_search")
@patch("magpiebom.cli.scrape_page")
@patch("magpiebom.cli.download_image")
@patch("magpiebom.cli.validate_image")
@patch("magpiebom.cli.extract_description_from_sources", return_value="LM7805 TO-220 5V 1.5A Linear Voltage Regulator")
@patch("magpiebom.cli.save_final_image")
@patch("magpiebom.cli.get_model_name", return_value="test-model")
@patch("magpiebom.cli.OpenAI")
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {"BRAVE_API_KEY": "test-key"})
def test_run_pipeline_uses_aggregated_extraction(
    mock_dotenv, mock_openai_cls, mock_get_model, mock_save,
    mock_extract_sources, mock_validate, mock_download, mock_scrape,
    mock_search, mock_validate_urls, mock_tracer_cls
):
    """Web search path should extract description ONCE from all sources."""
    mock_tracer_cls.return_value.__enter__ = MagicMock(return_value=mock_tracer_cls.return_value)
    mock_tracer_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_tracer_cls.return_value.trace_path = "/tmp/fake-trace.jsonl"

    mock_search.return_value = [
        {"url": "https://a.com/part", "title": "LM7805 Regulator", "description": "LM7805 generic desc"},
        {"url": "https://b.com/part", "title": "LM7805 TO-220", "description": "LM7805 TO-220 5V 1.5A Voltage Regulator IC"},
    ]
    mock_scrape.side_effect = [
        {
            "text_signals": _text_signals(title="LM7805 Regulator", meta_description="Buy components at A.com", meta_keywords="LM7805"),
            "image_urls": ["https://a.com/img.jpg"],
            "datasheet_urls": [],
        },
        {
            "text_signals": _text_signals(title="LM7805 TO-220", meta_description="LM7805 TO-220 5V 1.5A", meta_keywords="LM7805"),
            "image_urls": ["https://b.com/img.jpg"],
            "datasheet_urls": [],
        },
    ]
    mock_download.return_value = "/tmp/img.jpg"
    mock_validate.side_effect = [
        {"match": False, "reason": "No match"},
        {"match": True, "reason": "Correct part"},
    ]
    mock_save.return_value = "./parts/LM7805.jpg"

    result = run_pipeline("LM7805", output_dir="./parts", no_open=True, verbose=False)
    assert result["image_path"] == "./parts/LM7805.jpg"
    assert result["description"] == "LM7805 TO-220 5V 1.5A Linear Voltage Regulator"
    # Should call extract_description_from_sources exactly ONCE (not per page)
    assert mock_extract_sources.call_count == 1
    # Sources should include both Brave snippets and scraped page signals
    call_args = mock_extract_sources.call_args
    sources = call_args[0][3]  # 4th positional arg
    assert len(sources) >= 2  # At least Brave snippets + scraped pages


@patch("magpiebom.cli.Tracer")
@patch("magpiebom.cli._validate_urls")
@patch("magpiebom.cli.digikey_search")
@patch("magpiebom.cli.download_image")
@patch("magpiebom.cli.save_final_image")
@patch("magpiebom.cli.get_model_name", return_value="test-model")
@patch("magpiebom.cli.OpenAI")
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {"BRAVE_API_KEY": "test-key", "DIGIKEY_CLIENT_ID": "id", "DIGIKEY_CLIENT_SECRET": "secret"})
def test_run_pipeline_calls_validate_urls_on_digikey(
    mock_dotenv, mock_openai_cls, mock_get_model, mock_save, mock_download,
    mock_digikey, mock_validate_urls, mock_tracer_cls
):
    mock_tracer_cls.return_value.__enter__ = MagicMock(return_value=mock_tracer_cls.return_value)
    mock_tracer_cls.return_value.__exit__ = MagicMock(return_value=False)
    mock_tracer_cls.return_value.trace_path = "/tmp/fake-trace.jsonl"

    mock_digikey.return_value = {
        "description": "Cap 2.2uF",
        "image_url": "https://digikey.com/img.jpg",
        "datasheet_url": "https://bad.com/truncated",
        "manufacturer": "Yageo",
        "digikey_pn": "123-ABC",
    }
    mock_download.return_value = "/tmp/cap.jpg"
    mock_save.return_value = "./parts/CC0603.jpg"

    run_pipeline("CC0603KRX7R7BB225", output_dir="./parts", no_open=True, verbose=False)
    mock_validate_urls.assert_called_once()
    call_args = mock_validate_urls.call_args
    assert call_args[0][0]["source"] == "digikey"


def test_validate_urls_skips_structurally_bad_source():
    """Structurally bad URLs skip HEAD probe entirely."""
    result = {
        "part_number": "X",
        "source": "digikey",
        "source_url": "https://www.digikey.com/en/products/detail/-/-/",
        "datasheet_url": None,
        "datasheet_path": None,
    }
    with patch("magpiebom.cli._find_source_url_fallback", return_value=None) as mock_fb:
        with patch("magpiebom.cli._probe_url") as mock_probe:
            _validate_urls(result, api_key="key")
            # Should NOT probe the structurally bad URL
            mock_probe.assert_not_called()
    assert result["source_url"] is None
