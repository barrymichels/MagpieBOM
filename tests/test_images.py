# tests/test_images.py
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import responses
import pytest
from magpiebom.images import download_image, save_final_image
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
