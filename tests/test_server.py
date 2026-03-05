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
        assert resp.content_type.startswith("text/event-stream")
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
