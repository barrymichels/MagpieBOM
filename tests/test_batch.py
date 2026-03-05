"""Tests for magpiebom.batch module."""

import argparse
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from magpiebom.batch import _read_part_numbers, batch_main


def _make_args(parts=None, output_dir="./parts", verbose=False):
    return argparse.Namespace(parts=parts or [], output_dir=output_dir, verbose=verbose)


def test_read_from_args():
    args = _make_args(parts=["LM7805", "NE555"])
    result = _read_part_numbers(args)
    assert result == ["LM7805", "NE555"]


def test_read_from_file(tmp_path):
    f = tmp_path / "parts.txt"
    f.write_text("LM7805\n# comment\nNE555\n\n  LM317  \n")
    args = _make_args(parts=[str(f)])
    result = _read_part_numbers(args)
    assert result == ["LM7805", "NE555", "LM317"]


def test_read_filters_comments_and_blanks(tmp_path):
    f = tmp_path / "parts.txt"
    f.write_text("# Header comment\nLM7805\n\n# Another comment\n")
    args = _make_args(parts=[str(f)])
    result = _read_part_numbers(args)
    assert result == ["LM7805"]


def test_read_nonexistent_file_treated_as_part_number():
    args = _make_args(parts=["NOT_A_FILE_LM7805"])
    result = _read_part_numbers(args)
    assert result == ["NOT_A_FILE_LM7805"]


def test_read_from_stdin(monkeypatch):
    fake_stdin = StringIO("LM7805\nNE555\n")
    fake_stdin.isatty = lambda: False
    monkeypatch.setattr("sys.stdin", fake_stdin)
    args = _make_args(parts=[])
    result = _read_part_numbers(args)
    assert result == ["LM7805", "NE555"]


def test_read_empty_args_tty(monkeypatch):
    """No parts and tty stdin should return empty list."""
    fake_stdin = StringIO("")
    fake_stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", fake_stdin)
    args = _make_args(parts=[])
    result = _read_part_numbers(args)
    assert result == []


@patch("magpiebom.batch.run_pipeline")
@patch("magpiebom.batch.generate_report", return_value="./parts/report.html")
def test_batch_main_processes_parts(mock_report, mock_pipeline):
    mock_pipeline.side_effect = [
        {"part_number": "LM7805", "image_path": "./parts/LM7805.jpg"},
        {"part_number": "NE555", "image_path": None},
    ]
    args = _make_args(parts=["LM7805", "NE555"])
    batch_main(args)
    assert mock_pipeline.call_count == 2
    mock_report.assert_called_once()


@patch("magpiebom.batch.run_pipeline")
def test_batch_main_exits_on_empty_parts(mock_pipeline, monkeypatch):
    fake_stdin = StringIO("")
    fake_stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", fake_stdin)
    args = _make_args(parts=[])
    with pytest.raises(SystemExit) as exc_info:
        batch_main(args)
    assert exc_info.value.code == 1
    mock_pipeline.assert_not_called()
