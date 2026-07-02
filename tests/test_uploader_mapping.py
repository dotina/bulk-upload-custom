import pytest

from alwayz_bulk_upload.api_client import ReferenceData
from alwayz_bulk_upload.canonical_schema import parse_row
from alwayz_bulk_upload.errors import ReferenceNotFoundError
from alwayz_bulk_upload.uploader import build_charger_payload, build_site_payload


def _row(**overrides):
    raw = {
        "site_name": "ESPN / ESPN 11-2",
        "site_street_address": "1 Espn Plaza",
        "site_city": "Bristol",
        "site_state": "Connecticut",
        "site_zip": "06010",
        "site_contact_email": "ops@example.com",
        "charger_name": "ESPN / ESPN 11-2",
        "serial_number": "172841008201",
        "charger_type": "Level 2",
        "port_count": "2",
        "port1_connector_type": "J1772",
        "port1_voltage_v": "240",
        "port1_current_a": "30",
        "port2_connector_type": "J1772",
        "port2_voltage_v": "240",
        "port2_current_a": "30",
        "mac_address": "0024:B100:0002:872C",
        "usage_category": "Commercial with unrestricted access",
        "external_id": "220754",
    }
    raw.update(overrides)
    return parse_row(raw, row_number=2)


def _reference_data(**overrides):
    defaults = dict(
        charger_types={"level 2": "type-1"},
        connector_types={"j1772": "conn-1"},
        charger_statuses={},
        ev_networks={},
    )
    defaults.update(overrides)
    return ReferenceData(**defaults)


def test_build_site_payload_includes_contact_email():
    payload = build_site_payload(_row())
    assert payload["contact"]["email"] == "ops@example.com"


def test_build_site_payload_includes_address_city():
    payload = build_site_payload(_row())
    assert payload["address"]["city"] == "Bristol"


def test_build_charger_payload_sets_number_of_ports():
    payload = build_charger_payload(_row(), _reference_data())
    assert payload["numberOfPorts"] == 2


def test_build_charger_payload_sets_is_warranty_active():
    # charger.is_warranty_active is NOT NULL in the DB; payload must always send it.
    payload = build_charger_payload(_row(), _reference_data())
    assert payload["isWarrantyActive"] is False


def test_build_charger_payload_resolves_charger_type_id():
    payload = build_charger_payload(_row(), _reference_data())
    assert payload["chargerTypeId"] == "type-1"


def test_build_charger_payload_falls_back_to_port1_connector_type():
    payload = build_charger_payload(_row(connector_type=""), _reference_data())
    assert payload["connectorTypeId"] == "conn-1"


def test_build_charger_payload_unknown_charger_type_defaults_to_level_2():
    payload = build_charger_payload(_row(charger_type="Unknown Type"), _reference_data())
    assert payload["chargerTypeId"] == "type-1"


def test_build_charger_payload_unknown_charger_type_raises_when_level_2_missing():
    reference_data = _reference_data(charger_types={"level 3": "type-3"})
    with pytest.raises(ReferenceNotFoundError):
        build_charger_payload(_row(charger_type="Unknown Type"), reference_data)


def test_build_charger_payload_logs_warning_when_defaulting_charger_type(caplog):
    with caplog.at_level("WARNING"):
        build_charger_payload(_row(charger_type="Unknown Type"), _reference_data())
    assert "defaulted" in caplog.text
    assert "Level 2" in caplog.text


def test_build_charger_payload_reports_default_via_warnings_list():
    warnings = []
    payload = build_charger_payload(_row(charger_type="Unknown Type"), _reference_data(), warnings)
    assert payload["chargerTypeId"] == "type-1"
    assert len(warnings) == 1
    assert "Unknown Type" in warnings[0]
    assert "Level 2" in warnings[0]


def test_build_charger_payload_notes_include_mac_address():
    payload = build_charger_payload(_row(), _reference_data())
    assert "mac_address=0024:B100:0002:872C" in payload["warrantiesAndAgreements"]


def test_build_charger_payload_notes_include_external_id():
    payload = build_charger_payload(_row(), _reference_data())
    assert "external_id=220754" in payload["warrantiesAndAgreements"]


def test_build_charger_payload_prepends_existing_warranties_text():
    payload = build_charger_payload(
        _row(warranties_and_agreements="Under warranty until 2027"), _reference_data()
    )
    assert payload["warrantiesAndAgreements"].startswith("Under warranty until 2027")


def test_build_charger_payload_logs_warning_on_port_connector_mismatch(caplog):
    with caplog.at_level("WARNING"):
        build_charger_payload(_row(port2_connector_type="CCS"), _reference_data())
    assert "differs" in caplog.text
