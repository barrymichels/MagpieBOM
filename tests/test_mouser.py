"""Tests for magpiebom.mouser module."""

import responses
import pytest
from magpiebom.mouser import mouser_search, MOUSER_API_URL


def _mouser_response(parts):
    return {"SearchResults": {"Parts": parts}}


def _part(mpn="LM7805", image="https://mouser.com/img.jpg", desc="5V Regulator",
          ds_url="https://mouser.com/ds.pdf", mfr="Texas Instruments",
          mouser_pn="595-LM7805", detail_url="https://mouser.com/ProductDetail/595-LM7805"):
    return {
        "ManufacturerPartNumber": mpn,
        "ImagePath": image,
        "Description": desc,
        "DataSheetUrl": ds_url,
        "Manufacturer": mfr,
        "MouserPartNumber": mouser_pn,
        "ProductDetailUrl": detail_url,
    }


@responses.activate
def test_exact_match():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(mpn="NE555"), _part(mpn="LM7805")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None
    assert result["description"] == "5V Regulator"
    assert result["manufacturer"] == "Texas Instruments"


@responses.activate
def test_fallback_to_first_result():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(mpn="LM7805CT")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None  # Falls back to first even though MPN doesn't match exactly


@responses.activate
def test_case_insensitive_match():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(mpn="lm7805")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None


@responses.activate
def test_no_parts_returns_none():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([]), status=200)
    assert mouser_search("XYZFAKE", api_key="key") is None


@responses.activate
def test_no_image_returns_none():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(image="")]), status=200)
    assert mouser_search("LM7805", api_key="key") is None


@responses.activate
def test_protocol_relative_url_fixed():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(image="//mouser.com/img.jpg")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result["image_url"] == "https://mouser.com/img.jpg"


@responses.activate
def test_null_datasheet_url():
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([_part(ds_url="")]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result["datasheet_url"] is None


@responses.activate
def test_api_401_raises():
    responses.add(responses.POST, MOUSER_API_URL, json={"error": "Unauthorized"}, status=401)
    with pytest.raises(Exception):
        mouser_search("LM7805", api_key="bad-key")


@responses.activate
def test_api_500_raises():
    responses.add(responses.POST, MOUSER_API_URL, json={"error": "Server Error"}, status=500)
    with pytest.raises(Exception):
        mouser_search("LM7805", api_key="key")


@responses.activate
def test_timeout_raises():
    responses.add(responses.POST, MOUSER_API_URL, body=ConnectionError("timeout"))
    with pytest.raises(ConnectionError):
        mouser_search("LM7805", api_key="key")


@responses.activate
def test_missing_fields_handled():
    """Parts with missing optional fields should still work."""
    responses.add(responses.POST, MOUSER_API_URL,
                  json=_mouser_response([{
                      "ManufacturerPartNumber": "LM7805",
                      "ImagePath": "https://mouser.com/img.jpg",
                  }]), status=200)
    result = mouser_search("LM7805", api_key="key")
    assert result is not None
    assert result["description"] == ""
    assert result["datasheet_url"] is None
