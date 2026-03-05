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
