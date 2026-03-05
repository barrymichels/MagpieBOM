# tests/test_validator.py
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from magpiebom.validator import validate_image, get_model_name, extract_description, extract_description_from_sources


# 1x1 red PNG
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_mock_client(response_content: str):
    """Create a mock OpenAI client that returns the given content."""
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = response_content
    completion = MagicMock()
    completion.choices = [choice]
    client.chat.completions.create.return_value = completion
    return client


def test_validate_image_match():
    client = _make_mock_client('{"match": true, "reason": "Image shows a TO-220 voltage regulator"}')
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(TINY_PNG)
        f.flush()
        result = validate_image(
            client=client,
            model="test-model",
            image_path=f.name,
            part_number="LM7805",
            description="5V voltage regulator",
        )
    assert result["match"] is True
    assert "reason" in result
    Path(f.name).unlink()


def test_validate_image_no_match():
    client = _make_mock_client('{"match": false, "reason": "Image shows a capacitor, not a voltage regulator"}')
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(TINY_PNG)
        f.flush()
        result = validate_image(
            client=client,
            model="test-model",
            image_path=f.name,
            part_number="LM7805",
            description="5V voltage regulator",
        )
    assert result["match"] is False
    Path(f.name).unlink()


def test_validate_image_handles_malformed_llm_response():
    client = _make_mock_client("I think this looks like the right part!")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(TINY_PNG)
        f.flush()
        result = validate_image(
            client=client,
            model="test-model",
            image_path=f.name,
            part_number="LM7805",
            description="5V voltage regulator",
        )
    # Non-JSON response should default to no match
    assert result["match"] is False
    Path(f.name).unlink()


def test_validate_image_extracts_json_from_verbose_response():
    """LLM returns reasoning text with JSON embedded in it."""
    verbose_response = (
        '**Analysis:**\n1. The image shows a connector\n'
        '2. It matches the description\n\n'
        '{"match": true, "reason": "Image shows the correct connector"}\n'
    )
    client = _make_mock_client(verbose_response)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(TINY_PNG)
        f.flush()
        result = validate_image(
            client=client,
            model="test-model",
            image_path=f.name,
            part_number="B-2100S08P",
            description="8-pin connector",
        )
    assert result["match"] is True
    Path(f.name).unlink()


def test_validate_image_extracts_json_from_code_fence():
    """LLM wraps JSON in markdown code fences."""
    fenced_response = 'Here is my analysis:\n```json\n{"match": false, "reason": "Wrong part"}\n```'
    client = _make_mock_client(fenced_response)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(TINY_PNG)
        f.flush()
        result = validate_image(
            client=client,
            model="test-model",
            image_path=f.name,
            part_number="LM7805",
            description="5V voltage regulator",
        )
    assert result["match"] is False
    assert result["reason"] == "Wrong part"
    Path(f.name).unlink()


def test_get_model_name():
    client = MagicMock()
    model = MagicMock()
    model.id = "local-vision-model"
    client.models.list.return_value = MagicMock(data=[model])
    name = get_model_name(client)
    assert name == "local-vision-model"


# --- extract_description tests ---

def test_extract_description_returns_technical_text():
    """LLM should synthesize a technical description from text signals."""
    client = _make_mock_client('{"description": "Female Header 10 Position 2.54mm Pitch Dual Row Through Hole"}')
    signals = {
        "title": "PM254V-12-10P-H85 | XFCN | Price | In Stock | LCSC Electronics",
        "meta_description": "PM254V-12-10P-H85 by XFCN - In-stock components at LCSC.",
        "meta_keywords": "PM254V-12-10P-H85,XFCN,Female Headers,Connectors",
        "url_path": "/product-detail/Pin-Header-Female-Header_XFCN-PM254V-12-10P-H85_C492399.html",
        "paragraphs": ["Female Header 10 Position 2.54mm Pitch Dual Row Through Hole, available for assembly."],
    }
    result = extract_description(client, "test-model", "PM254V-12-08-H85", signals)
    assert result == "Female Header 10 Position 2.54mm Pitch Dual Row Through Hole"


def test_extract_description_empty_when_no_info():
    """LLM returns empty description when signals contain no useful info."""
    client = _make_mock_client('{"description": ""}')
    signals = {
        "title": "Page Not Found",
        "meta_description": "",
        "meta_keywords": "",
        "url_path": "/404",
        "paragraphs": [],
    }
    result = extract_description(client, "test-model", "PM254V-12-08-H85", signals)
    assert result == ""


def test_extract_description_handles_llm_failure():
    """Should return empty string when LLM call fails."""
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("Connection refused")
    signals = {
        "title": "Some Page",
        "meta_description": "Some description",
        "meta_keywords": "",
        "url_path": "/part",
        "paragraphs": [],
    }
    result = extract_description(client, "test-model", "PM254V-12-08-H85", signals)
    assert result == ""


def test_extract_description_extracts_json_from_verbose_response():
    """LLM wraps JSON in reasoning text — should still extract."""
    verbose = 'Let me analyze this.\n\n{"description": "5V Linear Voltage Regulator TO-220"}\n\nThat is my answer.'
    client = _make_mock_client(verbose)
    signals = {
        "title": "LM7805 Regulator",
        "meta_description": "LM7805 voltage regulator",
        "meta_keywords": "LM7805,regulator",
        "url_path": "/product/LM7805",
        "paragraphs": ["The LM7805 is a popular 5V linear voltage regulator in TO-220 package."],
    }
    result = extract_description(client, "test-model", "LM7805", signals)
    assert result == "5V Linear Voltage Regulator TO-220"


def test_extract_description_unparseable_returns_empty():
    """Completely unparseable LLM response should return empty."""
    client = _make_mock_client("I don't know what this component is.")
    signals = {
        "title": "Unknown",
        "meta_description": "",
        "meta_keywords": "",
        "url_path": "/",
        "paragraphs": [],
    }
    result = extract_description(client, "test-model", "XYZ123", signals)
    assert result == ""


def test_extract_description_truncated_json():
    """Truncated JSON (max_tokens hit) should still extract the description text."""
    truncated = '{"description": "2.54mm female header connector, 8-pin, 3A current rating'
    client = _make_mock_client(truncated)
    signals = {"title": "Part", "meta_description": "", "meta_keywords": "", "url_path": "/", "paragraphs": []}
    result = extract_description(client, "test-model", "PM254V-12-08-H85", signals)
    assert "2.54mm female header connector" in result
    assert "3A current rating" in result


# --- extract_description_from_sources tests ---

def test_extract_from_sources_combines_multiple_sources():
    """Should send all sources in a single LLM call and return the result."""
    client = _make_mock_client('{"description": "Female Header 8 Position 2.54mm Pitch Dual Row Through Hole"}')
    sources = [
        {
            "title": "PM254V-12-08-H85 | LCSC",
            "meta_description": "PM254V-12-08-H85 by XFCN",
            "meta_keywords": "Female Headers,Connectors",
            "url_path": "/product-detail/Pin-Header-Female-Header_XFCN-PM254V-12-08-H85.html",
            "url_category": "Pin Header Female Header",
            "paragraphs": ["Female Header 8 Position 2.54mm Pitch"],
        },
        {
            "title": "PM254V-12-08-H85 - JLCPCB",
            "meta_description": "8-pin female header connector",
            "meta_keywords": "",
            "url_path": "/parts/PM254V-12-08-H85",
            "url_category": "",
            "paragraphs": [],
        },
    ]
    result = extract_description_from_sources(client, "test-model", "PM254V-12-08-H85", sources)
    assert result == "Female Header 8 Position 2.54mm Pitch Dual Row Through Hole"
    # Should have made exactly one LLM call
    assert client.chat.completions.create.call_count == 1
    # Prompt should contain both source titles
    call_args = client.chat.completions.create.call_args
    prompt = call_args[1]["messages"][0]["content"]
    assert "Source 1" in prompt
    assert "Source 2" in prompt
    assert "Pin Header Female Header" in prompt  # url_category included


def test_extract_from_sources_empty_list():
    """Should return empty string for empty sources list without calling LLM."""
    client = MagicMock()
    result = extract_description_from_sources(client, "test-model", "LM7805", [])
    assert result == ""
    client.chat.completions.create.assert_not_called()


def test_extract_from_sources_handles_llm_failure():
    """Should return empty string when LLM call fails."""
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("Connection refused")
    sources = [{"title": "Part", "meta_description": "", "meta_keywords": "", "url_path": "/", "url_category": "", "paragraphs": []}]
    result = extract_description_from_sources(client, "test-model", "LM7805", sources)
    assert result == ""


def test_extract_from_sources_uses_temperature_zero():
    """LLM call should use temperature=0 for deterministic output."""
    client = _make_mock_client('{"description": "5V Regulator"}')
    sources = [{"title": "LM7805", "meta_description": "regulator", "meta_keywords": "", "url_path": "/", "url_category": "", "paragraphs": []}]
    extract_description_from_sources(client, "test-model", "LM7805", sources)
    call_kwargs = client.chat.completions.create.call_args[1]
    assert call_kwargs["temperature"] == 0


def test_extract_from_sources_includes_brave_snippets():
    """Brave search snippets (title + description only) should be valid sources."""
    client = _make_mock_client('{"description": "Pin Header Connector 2.54mm"}')
    sources = [
        # Brave snippet — minimal fields
        {
            "title": "PM254V-12-08-H85 Pin Header",
            "meta_description": "Pin header connector 2.54mm pitch 8 position",
            "meta_keywords": "",
            "url_path": "",
            "url_category": "",
            "paragraphs": [],
        },
    ]
    result = extract_description_from_sources(client, "test-model", "PM254V-12-08-H85", sources)
    assert result == "Pin Header Connector 2.54mm"
