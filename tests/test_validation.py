from unittest.mock import Mock

from alwayz_bulk_upload.api_client import ChargerSummary, ReferenceData, SiteSummary
from alwayz_bulk_upload.canonical_schema import parse_row
from alwayz_bulk_upload.validation import validate_rows, validation_report_to_dict


def _row(**overrides):
    row_number = overrides.pop("row_number", 2)
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
    return parse_row(raw, row_number=row_number)


def _reference_data():
    return ReferenceData(
        charger_types={"level 2": "type-1"},
        connector_types={"j1772": "conn-1"},
        charger_statuses={},
        ev_networks={},
    )


def _client(sites=None, chargers=None):
    client = Mock()
    client.list_sites.return_value = sites or {}
    client.list_chargers.return_value = chargers or {}
    return client


def test_validate_rows_groups_by_site_name():
    row_a = _row(site_name="Site A", serial_number="SN-1", row_number=2)
    row_b = _row(site_name="Site A", serial_number="SN-2", row_number=3)
    report = validate_rows([row_a, row_b], _client(), _reference_data(), "company-1")

    assert len(report.sites) == 1
    assert report.sites[0].site_name == "Site A"
    assert len(report.sites[0].chargers) == 2


def test_validate_rows_new_site_planned_action():
    report = validate_rows([_row()], _client(), _reference_data(), "company-1")

    assert report.sites[0].planned_action == "create"
    assert report.sites[0].chargers[0].planned_action == "create_site_and_charger"
    assert report.summary["new_sites"] == 1
    assert report.summary["chargers_to_create"] == 1


def test_validate_rows_reuses_existing_site():
    sites = {"ESPN / ESPN 11-2": SiteSummary(id="site-1", name="ESPN / ESPN 11-2")}
    report = validate_rows([_row()], _client(sites=sites), _reference_data(), "company-1")

    assert report.sites[0].planned_action == "reuse_existing"
    assert report.sites[0].existing_site_id == "site-1"
    assert report.sites[0].chargers[0].planned_action == "reuse_site_create_charger"
    assert report.summary["reused_sites"] == 1


def test_validate_rows_skips_existing_charger():
    chargers = {
        "172841008201": ChargerSummary(id="c-1", serial_number="172841008201", site_id="site-1")
    }
    report = validate_rows([_row()], _client(chargers=chargers), _reference_data(), "company-1")

    assert report.sites[0].chargers[0].planned_action == "skip_existing"
    assert report.summary["chargers_skipped"] == 1
    assert report.summary["chargers_to_create"] == 0


def test_validate_rows_duplicate_serial_is_blocking():
    row_a = _row(serial_number="SN-DUP", row_number=2)
    row_b = _row(serial_number="SN-DUP", row_number=3)
    report = validate_rows([row_a, row_b], _client(), _reference_data(), "company-1")

    assert report.summary["can_commit"] is False
    assert any("duplicate serial_number" in e for c in report.sites[0].chargers for e in c.errors)


def test_validate_rows_unresolvable_charger_type_blocks_commit():
    # No charger types at all: even the "Level 2" default can't resolve, so it blocks.
    reference_data = ReferenceData(
        charger_types={}, connector_types={"j1772": "conn-1"}, charger_statuses={}, ev_networks={}
    )
    report = validate_rows([_row(charger_type="Unknown")], _client(), reference_data, "company-1")

    assert report.summary["can_commit"] is False
    assert report.sites[0].chargers[0].charger_payload is None
    assert any("charger_type" in e for e in report.sites[0].chargers[0].errors)


def test_validate_rows_unknown_connector_type_is_nonblocking():
    report = validate_rows(
        [_row(connector_type="Unknown Connector")], _client(), _reference_data(), "company-1"
    )
    charger = report.sites[0].chargers[0]

    assert report.summary["can_commit"] is True
    assert "connectorTypeId" not in charger.charger_payload
    assert any("connector_type" in w for w in charger.warnings)


def test_validate_rows_unknown_charger_type_defaults_and_allows_commit():
    report = validate_rows(
        [_row(charger_type="Unknown")], _client(), _reference_data(), "company-1"
    )
    charger = report.sites[0].chargers[0]

    assert report.summary["can_commit"] is True
    assert charger.charger_payload["chargerTypeId"] == "type-1"
    # Defaulting is reported as a non-blocking warning, not a blocking error.
    assert charger.errors == []
    assert any("defaulted to 'Level 2'" in w for w in charger.warnings)
    assert report.summary["warnings"] >= 1


def test_validate_rows_site_address_mismatch_warning():
    row_a = _row(site_street_address="1 Main St", row_number=2)
    row_b = _row(site_street_address="2 Other St", serial_number="SN-2", row_number=3)
    report = validate_rows([row_a, row_b], _client(), _reference_data(), "company-1")

    assert report.summary["can_commit"] is True
    assert any("differing address" in w for w in report.sites[0].warnings)


def test_validation_report_to_dict_is_json_serializable():
    report = validate_rows([_row()], _client(), _reference_data(), "company-1")
    data = validation_report_to_dict(report)

    assert data["summary"]["can_commit"] is True
    assert data["sites"][0]["site_payload"]["name"] == "ESPN / ESPN 11-2"
