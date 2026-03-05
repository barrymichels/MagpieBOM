# tests/test_images.py
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import responses
import pytest
from magpiebom.images import download_image, save_final_image, _get_extension, _download_requests
from tests.helpers import TINY_PNG


@responses.activate
def test_download_image_saves_to_temp():
    responses.add(
        responses.GET,
        "https://example.com/part.png",
        body=TINY_PNG,
        content_type="image/png",
        status=200,
    )
    path = download_image("https://example.com/part.png")
    assert path is not None
    assert Path(path).exists()
    assert Path(path).read_bytes() == TINY_PNG
    Path(path).unlink()


@responses.activate
def test_download_image_returns_none_on_error():
    responses.add(
        responses.GET,
        "https://example.com/broken.png",
        status=404,
    )
    path = download_image("https://example.com/broken.png")
    assert path is None


def test_save_final_image():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a temp source file
        src = Path(tmpdir) / "temp.png"
        src.write_bytes(TINY_PNG)
        output_dir = Path(tmpdir) / "output"
        result = save_final_image(str(src), "LM7805", str(output_dir))
        assert Path(result).exists()
        assert "LM7805" in result
        assert Path(result).read_bytes() == TINY_PNG


@responses.activate
def test_download_image_rejects_non_image_content_type():
    responses.add(responses.GET, "https://example.com/blocked.jpg",
                  body=b"<html>Access Denied</html>", content_type="text/html", status=200)
    assert download_image("https://example.com/blocked.jpg") is None


@responses.activate
def test_download_image_timeout():
    import requests as req_lib
    responses.add(responses.GET, "https://example.com/slow.jpg",
                  body=req_lib.exceptions.Timeout("Connection timed out"))
    with patch("magpiebom.images._download_playwright", return_value=None):
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
