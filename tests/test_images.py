# tests/test_images.py
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import responses
import pytest
from magpiebom.images import download_image, save_final_image


# 1x1 red PNG (smallest valid PNG)
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


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
