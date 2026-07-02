import inspect
from unittest.mock import Mock

from alwayz_bulk_upload.api_client import ChargerSummary, ReferenceData, SiteSummary
from alwayz_bulk_upload.canonical_schema import parse_row
from alwayz_bulk_upload.errors import ApiError
from alwayz_bulk_upload.uploader import upload_rows, iter_upload_rows


def _row(**overrides):
    raw = {
        "site_name": "ESPN / ESPN 11-2",
        "site_street_address": "1 Espn Plaza",
        "site_city": "Bristol",
        "site_contact_email": "ops@example.com",
        "charger_name": "ESPN / ESPN 11-2",
        "serial_number": "172841008201",
        "charger_type": "Level 2",
        "port_count": "1",
        "port1_connector_type": "J1772",
        "port1_voltage_v": "240",
        "port1_current_a": "30",
    }
    raw.update(overrides)
    return parse_row(raw, row_number=2)


def _reference_data():
    return ReferenceData(
        charger_types={"level 2": "type-1"}, connector_types={"j1772": "conn-1"},
        charger_statuses={}, ev_networks={},
    )


def _client(sites=None, chargers=None):
    client = Mock()
    client.list_sites.return_value = sites or {}
    client.list_chargers.return_value = chargers or {}
    return client


def test_upload_rows_creates_new_site_and_charger():
    client = _client()
    client.create_site.return_value = {"id": "site-1"}
    client.create_charger.return_value = {"id": "charger-1"}

    results = upload_rows([_row()], client, _reference_data(), "company-1")

    assert results[0].action == "created"


def test_upload_rows_skips_existing_charger_without_creating():
    client = _client(chargers={"172841008201": ChargerSummary(id="c1", serial_number="172841008201", site_id="s1")})

    upload_rows([_row()], client, _reference_data(), "company-1")

    client.create_charger.assert_not_called()


def test_upload_rows_reuses_existing_site_without_recreating():
    client = _client(sites={"ESPN / ESPN 11-2": SiteSummary(id="site-1", name="ESPN / ESPN 11-2")})
    client.create_charger.return_value = {"id": "charger-1"}

    upload_rows([_row()], client, _reference_data(), "company-1")

    client.create_site.assert_not_called()


def test_upload_rows_dry_run_makes_no_create_calls():
    client = _client()

    upload_rows([_row()], client, _reference_data(), "company-1", dry_run=True)

    client.create_site.assert_not_called()


def test_upload_rows_one_failure_does_not_stop_remaining_rows():
    client = _client()
    client.create_site.return_value = {"id": "site-1"}
    client.create_charger.side_effect = [ApiError("charger create failed"), {"id": "charger-1"}]
    bad_row = _row(serial_number="BAD-1")
    good_row = _row(serial_number="GOOD-1")

    results = upload_rows([bad_row, good_row], client, _reference_data(), "company-1")

    assert [r.action for r in results] == ["failed", "created"]


def test_upload_rows_defaulted_charger_type_is_created_with_warning():
    client = _client()
    client.create_site.return_value = {"id": "site-1"}
    client.create_charger.return_value = {"id": "charger-1"}

    results = upload_rows([_row(charger_type="Unknown Type")], client, _reference_data(), "company-1")

    assert results[0].action == "created"
    assert any("defaulted to 'Level 2'" in w for w in results[0].warnings)


def test_upload_rows_failure_records_error_message():
    client = _client()
    client.create_site.return_value = {"id": "site-1"}
    client.create_charger.side_effect = ApiError("charger create failed: boom")
    bad_row = _row()

    results = upload_rows([bad_row], client, _reference_data(), "company-1")

    assert "boom" in results[0].error


def test_upload_rows_reuses_newly_created_site_across_rows_in_same_run():
    client = _client()
    client.create_site.return_value = {"id": "site-1"}
    client.create_charger.side_effect = [{"id": "charger-1"}, {"id": "charger-2"}]
    row_a = _row(serial_number="SN-A")
    row_b = _row(serial_number="SN-B")

    upload_rows([row_a, row_b], client, _reference_data(), "company-1")

    client.create_site.assert_called_once()


def test_iter_upload_rows_returns_a_generator():
    result = iter_upload_rows([], None, None, "company-1")
    assert inspect.isgenerator(result)


def test_iter_upload_rows_matches_upload_rows_output():
    client_for_list = _client()
    client_for_list.create_site.return_value = {"id": "site-1"}
    client_for_list.create_charger.return_value = {"id": "charger-1"}
    client_for_iter = _client()
    client_for_iter.create_site.return_value = {"id": "site-1"}
    client_for_iter.create_charger.return_value = {"id": "charger-1"}

    via_list = upload_rows([_row()], client_for_list, _reference_data(), "company-1")
    via_iter = list(iter_upload_rows([_row()], client_for_iter, _reference_data(), "company-1"))

    assert via_list == via_iter
