"""Tests for magpiebom.report module."""

from pathlib import Path

import pytest
from tests.helpers import TINY_PNG
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
