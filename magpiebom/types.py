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
