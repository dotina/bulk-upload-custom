from unittest.mock import Mock, patch

import pytest

from alwayz_bulk_upload.api_client import AlwayzApiClient
from alwayz_bulk_upload.errors import ApiError


def _make_response(json_body, status_code=200, text=""):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = text
    return response


def test_load_reference_data_maps_charger_type_name_to_id():
    session = Mock()
    session.headers = {}
    session.request.return_value = _make_response(
        {"content": [{"id": "abc-1", "name": "LEVEL_02", "displayName": "Level 2"}], "last": True}
    )

    client = AlwayzApiClient("https://api.example.com", "token", session=session)
    reference_data = client.load_reference_data()

    # Both the human-readable displayName and the internal code resolve to the id.
    assert reference_data.charger_types["level 2"] == "abc-1"
    assert reference_data.charger_types["level_02"] == "abc-1"


def test_list_sites_aggregates_across_pages():
    session = Mock()
    session.headers = {}
    page_one = _make_response({"content": [{"id": "s1", "name": "Site One"}], "last": False})
    page_two = _make_response({"content": [{"id": "s2", "name": "Site Two"}], "last": True})
    session.request.side_effect = [page_one, page_two]

    client = AlwayzApiClient("https://api.example.com", "token", session=session)
    sites = client.list_sites("company-1")

    assert set(sites) == {"Site One", "Site Two"}


def test_list_chargers_keys_by_serial_number():
    session = Mock()
    session.headers = {}
    session.request.return_value = _make_response(
        {"content": [{"id": "c1", "serialNumber": "SN-1", "siteId": "s1"}], "last": True}
    )

    client = AlwayzApiClient("https://api.example.com", "token", session=session)
    chargers = client.list_chargers("company-1")

    assert chargers["SN-1"].id == "c1"
    called_url = session.request.call_args.args[1]
    assert called_url == "https://api.example.com/api.evhub.com/v1/companies/company-1/chargers/all"


def test_request_retries_on_500_then_succeeds():
    session = Mock()
    session.headers = {}
    failing = _make_response({}, status_code=500, text="boom")
    succeeding = _make_response({"id": "site-1"}, status_code=201)
    session.request.side_effect = [failing, succeeding]

    client = AlwayzApiClient("https://api.example.com", "token", session=session)
    with patch("alwayz_bulk_upload.api_client.time.sleep"):
        result = client.create_site("company-1", {"name": "Site"})

    assert result == {"id": "site-1"}


def test_request_fails_fast_on_400_without_retry():
    session = Mock()
    session.headers = {}
    session.request.return_value = _make_response({}, status_code=400, text="bad request")

    client = AlwayzApiClient("https://api.example.com", "token", session=session)
    with pytest.raises(ApiError):
        client.create_site("company-1", {"name": "Site"})


def test_request_fails_fast_on_400_makes_only_one_call():
    session = Mock()
    session.headers = {}
    session.request.return_value = _make_response({}, status_code=400, text="bad request")

    client = AlwayzApiClient("https://api.example.com", "token", session=session)
    try:
        client.create_site("company-1", {"name": "Site"})
    except ApiError:
        pass

    assert session.request.call_count == 1


def test_create_charger_posts_to_site_scoped_path():
    session = Mock()
    session.headers = {}
    session.request.return_value = _make_response({"id": "charger-1"}, status_code=201)

    client = AlwayzApiClient("https://api.example.com", "token", session=session)
    client.create_charger("company-1", "site-1", {"name": "Charger"})

    called_url = session.request.call_args.args[1]
    assert called_url == "https://api.example.com/api.evhub.com/v1/companies/company-1/sites/site-1/chargers"
