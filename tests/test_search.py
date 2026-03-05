import responses
import pytest
from magpiebom.search import brave_search


SAMPLE_BRAVE_RESPONSE = {
    "web": {
        "results": [
            {
                "title": "LM7805 Voltage Regulator - Mouser",
                "url": "https://www.mouser.com/ProductDetail/LM7805",
                "description": "The LM7805 is a 5V fixed positive voltage regulator.",
            },
            {
                "title": "LM7805 - DigiKey",
                "url": "https://www.digikey.com/product/LM7805",
                "description": "LM7805 TO-220 package voltage regulator IC.",
            },
        ]
    }
}


@responses.activate
def test_brave_search_returns_results():
    responses.add(
        responses.GET,
        "https://api.search.brave.com/res/v1/web/search",
        json=SAMPLE_BRAVE_RESPONSE,
        status=200,
    )
    results = brave_search("LM7805", api_key="test-key", count=5)
    assert len(results) == 2
    assert results[0]["url"] == "https://www.mouser.com/ProductDetail/LM7805"
    assert results[0]["title"] == "LM7805 Voltage Regulator - Mouser"
    assert results[0]["description"] == "The LM7805 is a 5V fixed positive voltage regulator."


@responses.activate
def test_brave_search_sends_correct_query():
    responses.add(
        responses.GET,
        "https://api.search.brave.com/res/v1/web/search",
        json=SAMPLE_BRAVE_RESPONSE,
        status=200,
    )
    brave_search("NE555", api_key="test-key", count=5)
    assert '"NE555" electronic component' in responses.calls[0].request.params.get("q", "")


@responses.activate
def test_brave_search_handles_empty_response():
    responses.add(
        responses.GET,
        "https://api.search.brave.com/res/v1/web/search",
        json={"web": {"results": []}},
        status=200,
    )
    results = brave_search("XYZNONEXISTENT", api_key="test-key", count=5)
    assert results == []


@responses.activate
def test_brave_search_returns_empty_on_http_error():
    responses.add(
        responses.GET,
        "https://api.search.brave.com/res/v1/web/search",
        json={"error": "Unauthorized"},
        status=401,
    )
    results = brave_search("LM7805", api_key="bad-key", count=5)
    assert results == []


@responses.activate
def test_brave_search_prioritizes_known_sites():
    responses.add(
        responses.GET,
        "https://api.search.brave.com/res/v1/web/search",
        json={
            "web": {
                "results": [
                    {"title": "Random Blog", "url": "https://blog.example.com/lm7805", "description": "blog post"},
                    {"title": "Mouser LM7805", "url": "https://www.mouser.com/lm7805", "description": "mouser page"},
                    {"title": "DigiKey LM7805", "url": "https://www.digikey.com/lm7805", "description": "digikey page"},
                ]
            }
        },
        status=200,
    )
    results = brave_search("LM7805", api_key="test-key", count=5)
    # Known sites should be first
    assert "mouser.com" in results[0]["url"]
