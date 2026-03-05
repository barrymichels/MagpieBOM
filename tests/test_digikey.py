"""Tests for magpiebom.digikey module."""

import responses
import pytest
from magpiebom.digikey import digikey_search, _get_token, TOKEN_URL, SEARCH_URL


@responses.activate
def test_get_token_success():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "test-token"}, status=200)
    token = _get_token("client-id", "client-secret")
    assert token == "test-token"


@responses.activate
def test_get_token_401_raises():
    responses.add(responses.POST, TOKEN_URL, json={"error": "invalid_client"}, status=401)
    with pytest.raises(Exception):
        _get_token("bad-id", "bad-secret")


@responses.activate
def test_search_exact_match():
    responses.add(responses.POST, TOKEN_URL,
                  json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": {"ProductDescription": "5V Regulator"}, "DatasheetUrl": "https://dk.com/ds.pdf",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296-LM7805"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result is not None
    assert result["description"] == "5V Regulator"
    assert result["manufacturer"] == "TI"
    assert result["digikey_pn"] == "296-LM7805"


@responses.activate
def test_search_description_as_string():
    """DigiKey sometimes returns Description as a plain string, not a dict."""
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": "5V Regulator Plain String", "DatasheetUrl": "",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result["description"] == "5V Regulator Plain String"


@responses.activate
def test_search_no_products():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL, json={"Products": []}, status=200)
    assert digikey_search("XYZFAKE", client_id="id", client_secret="secret") is None


@responses.activate
def test_search_no_image():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "",
                       "Description": "5V Reg", "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    assert digikey_search("LM7805", client_id="id", client_secret="secret") is None


@responses.activate
def test_search_fallback_to_first():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805CT", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": {"ProductDescription": "5V Reg CT"}, "DatasheetUrl": "",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result is not None


@responses.activate
def test_search_api_error_raises():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL, json={"error": "Server Error"}, status=500)
    with pytest.raises(Exception):
        digikey_search("LM7805", client_id="id", client_secret="secret")


@responses.activate
def test_null_datasheet():
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "token"}, status=200)
    responses.add(responses.POST, SEARCH_URL,
                  json={"Products": [
                      {"ManufacturerProductNumber": "LM7805", "PhotoUrl": "https://dk.com/img.jpg",
                       "Description": {"ProductDescription": "5V"}, "DatasheetUrl": "",
                       "Manufacturer": {"Name": "TI"}, "DigiKeyProductNumber": "296"},
                  ]}, status=200)
    result = digikey_search("LM7805", client_id="id", client_secret="secret")
    assert result["datasheet_url"] is None
