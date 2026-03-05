from magpiebom.scraper import extract_page_info, _extract_text_signals, _extract_category_from_url
from bs4 import BeautifulSoup


SAMPLE_HTML = """
<html>
<head>
    <meta name="description" content="LM7805 5V voltage regulator in TO-220 package">
    <meta property="og:image" content="https://example.com/lm7805-main.jpg">
</head>
<body>
    <div class="product-image">
        <img src="https://example.com/lm7805-photo.jpg" width="400" height="300">
    </div>
    <img src="https://example.com/logo.png" width="50" height="50">
    <img src="https://example.com/banner.jpg" width="800" height="60">
    <img src="/relative/image.jpg" width="200" height="200">
    <p>The LM7805 is a popular voltage regulator.</p>
</body>
</html>
"""

SIGNALS_HTML = """
<html>
<head>
    <title>PM254V-12-10P-H85 | XFCN | Price | In Stock | LCSC Electronics</title>
    <meta name="description" content="PM254V-12-10P-H85 by XFCN - In-stock components at LCSC.">
    <meta name="keywords" content="PM254V-12-10P-H85,XFCN,Female Headers,Connectors">
    <meta property="og:image" content="https://example.com/part.jpg">
</head>
<body>
    <p>Short text.</p>
    <p>Female Header 10 Position 2.54mm Pitch Dual Row Through Hole, available for assembly.</p>
    <p>Another paragraph with some product details here.</p>
</body>
</html>
"""


# --- Text signals extraction tests ---

def test_extract_text_signals_title():
    soup = BeautifulSoup(SIGNALS_HTML, "lxml")
    signals = _extract_text_signals(soup, "https://lcsc.com/product-detail/Pin-Header-Female-Header_XFCN-PM254V-12-10P-H85_C492399.html")
    assert "PM254V-12-10P-H85" in signals["title"]
    assert "LCSC" in signals["title"]


def test_extract_text_signals_meta_description():
    soup = BeautifulSoup(SIGNALS_HTML, "lxml")
    signals = _extract_text_signals(soup, "https://lcsc.com/product-detail/foo.html")
    assert "PM254V-12-10P-H85" in signals["meta_description"]


def test_extract_text_signals_meta_keywords():
    soup = BeautifulSoup(SIGNALS_HTML, "lxml")
    signals = _extract_text_signals(soup, "https://lcsc.com/product-detail/foo.html")
    assert "Female Headers" in signals["meta_keywords"]


def test_extract_text_signals_url_path():
    soup = BeautifulSoup(SIGNALS_HTML, "lxml")
    signals = _extract_text_signals(soup, "https://lcsc.com/product-detail/Pin-Header-Female-Header_XFCN-PM254V-12-10P-H85_C492399.html")
    assert "Pin-Header-Female-Header" in signals["url_path"]


def test_extract_text_signals_paragraphs():
    soup = BeautifulSoup(SIGNALS_HTML, "lxml")
    signals = _extract_text_signals(soup, "https://example.com/part")
    # "Short text." is <30 chars, should be filtered
    assert all(len(p) > 30 for p in signals["paragraphs"])
    assert len(signals["paragraphs"]) >= 1
    assert any("2.54mm" in p for p in signals["paragraphs"])


def test_extract_text_signals_max_paragraphs():
    """Should return at most 5 paragraphs."""
    html = "<html><body>" + "".join(
        f"<p>This is paragraph number {i} with enough text to be substantial.</p>"
        for i in range(10)
    ) + "</body></html>"
    soup = BeautifulSoup(html, "lxml")
    signals = _extract_text_signals(soup, "https://example.com")
    assert len(signals["paragraphs"]) <= 5


def test_extract_text_signals_url_category_lcsc():
    """LCSC-style URLs should extract category from path segments."""
    soup = BeautifulSoup(SIGNALS_HTML, "lxml")
    signals = _extract_text_signals(soup, "https://lcsc.com/product-detail/Pin-Header-Female-Header_XFCN-PM254V-12-10P-H85_C492399.html")
    assert signals["url_category"] == "Pin Header Female Header"


def test_extract_category_from_url_empty_for_simple_paths():
    """Simple paths without category info should return empty."""
    assert _extract_category_from_url("https://example.com/product/123") == ""
    assert _extract_category_from_url("https://example.com/") == ""


def test_extract_category_from_url_lcsc_style():
    result = _extract_category_from_url("https://lcsc.com/product-detail/Pin-Header-Female-Header_XFCN-PM254V-12-10P-H85_C492399.html")
    assert result == "Pin Header Female Header"


def test_extract_text_signals_missing_meta():
    """Gracefully handle pages with no meta tags."""
    html = "<html><head><title>Simple Page</title></head><body><p>Some content here that is long enough.</p></body></html>"
    soup = BeautifulSoup(html, "lxml")
    signals = _extract_text_signals(soup, "https://example.com")
    assert signals["title"] == "Simple Page"
    assert signals["meta_description"] == ""
    assert signals["meta_keywords"] == ""


def test_extract_page_info_returns_text_signals():
    """extract_page_info should return text_signals dict, not description string."""
    info = extract_page_info(SIGNALS_HTML, "https://example.com/part")
    assert "text_signals" in info
    assert "description" not in info
    assert isinstance(info["text_signals"], dict)
    assert "title" in info["text_signals"]


def test_extract_text_signals_from_sample_meta():
    info = extract_page_info(SAMPLE_HTML, "https://example.com/product")
    assert "LM7805" in info["text_signals"]["meta_description"]
    assert "voltage regulator" in info["text_signals"]["meta_description"]


def test_extract_text_signals_paragraph_fallback():
    html = "<html><body><p>A great component for power regulation.</p></body></html>"
    info = extract_page_info(html, "https://example.com/product")
    assert any("power regulation" in p for p in info["text_signals"]["paragraphs"])


# --- Image extraction tests ---

def test_extract_images_filters_small():
    info = extract_page_info(SAMPLE_HTML, "https://example.com/product")
    image_urls = info["image_urls"]
    assert "https://example.com/logo.png" not in image_urls


def test_extract_images_filters_banners():
    info = extract_page_info(SAMPLE_HTML, "https://example.com/product")
    image_urls = info["image_urls"]
    assert "https://example.com/banner.jpg" not in image_urls


def test_extract_images_resolves_relative_urls():
    info = extract_page_info(SAMPLE_HTML, "https://example.com/product")
    image_urls = info["image_urls"]
    assert "https://example.com/relative/image.jpg" in image_urls


def test_extract_images_includes_og_image():
    info = extract_page_info(SAMPLE_HTML, "https://example.com/product")
    assert "https://example.com/lm7805-main.jpg" in info["image_urls"]


def test_extract_images_limits_to_three():
    html = "<html><body>" + "".join(
        f'<img src="https://example.com/img{i}.jpg" width="200" height="200">'
        for i in range(10)
    ) + "</body></html>"
    info = extract_page_info(html, "https://example.com/product")
    assert len(info["image_urls"]) <= 3


def test_extract_images_filters_svg():
    html = '<html><body><img src="https://example.com/ad.svg" width="200" height="200"></body></html>'
    info = extract_page_info(html, "https://example.com/product")
    assert len(info["image_urls"]) == 0


def test_extract_images_filters_advertising_urls():
    html = '<html><body><img src="https://example.com/advertising/promo.jpg" width="200" height="200"></body></html>'
    info = extract_page_info(html, "https://example.com/product")
    assert len(info["image_urls"]) == 0


def test_extract_images_filters_svg_og_image():
    html = '<html><head><meta property="og:image" content="https://example.com/logo.svg"></head><body></body></html>'
    info = extract_page_info(html, "https://example.com/product")
    assert len(info["image_urls"]) == 0
