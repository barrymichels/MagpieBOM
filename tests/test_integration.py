# tests/test_integration.py
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import responses

from magpiebom.cli import run_pipeline

# 1x1 red PNG
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

PRODUCT_PAGE = """
<html>
<head><meta name="description" content="LM7805 5V TO-220 voltage regulator"></head>
<body>
<img src="https://images.example.com/lm7805.jpg" width="400" height="300">
</body>
</html>
"""


@responses.activate
@patch("magpiebom.cli.OpenAI")
@patch("magpiebom.cli.get_model_name", return_value="test-model")
@patch("magpiebom.cli.load_dotenv")
@patch("os.environ", {"BRAVE_API_KEY": "test-key"})
def test_full_pipeline_finds_match(mock_dotenv, mock_get_model, mock_openai_cls):
    # Mock Brave Search
    responses.add(
        responses.GET,
        "https://api.search.brave.com/res/v1/web/search",
        json={
            "web": {
                "results": [
                    {
                        "title": "LM7805 - Mouser",
                        "url": "https://www.mouser.com/LM7805",
                        "description": "5V voltage regulator",
                    }
                ]
            }
        },
    )
    # Mock product page
    responses.add(
        responses.GET,
        "https://www.mouser.com/LM7805",
        body=PRODUCT_PAGE,
        content_type="text/html",
    )
    # Mock image download
    responses.add(
        responses.GET,
        "https://images.example.com/lm7805.jpg",
        body=TINY_PNG,
        content_type="image/png",
    )

    # Mock LLM validation
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    choice = MagicMock()
    choice.message.content = '{"match": true, "reason": "Correct TO-220 voltage regulator"}'
    completion = MagicMock()
    completion.choices = [choice]
    mock_client.chat.completions.create.return_value = completion

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_pipeline("LM7805", output_dir=tmpdir, no_open=True, verbose=True)
        assert result["image_path"] is not None
        assert Path(result["image_path"]).exists()
        assert "LM7805" in result["image_path"]
        assert result["source"] == "web"
