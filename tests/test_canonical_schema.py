import pytest

from alwayz_bulk_upload.canonical_schema import parse_row
from alwayz_bulk_upload.errors import ValidationError


def _valid_raw(**overrides):
    raw = {
        "site_name": "ESPN / ESPN 11-2",
        "site_street_address": "1 Espn Plaza",
        "site_city": "Bristol",
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
    }
    raw.update(overrides)
    return raw


def test_parse_row_maps_site_name():
    row = parse_row(_valid_raw(), row_number=1)
    assert row.site_name == "ESPN / ESPN 11-2"


def test_parse_row_missing_required_column_raises():
    raw = _valid_raw()
    del raw["site_contact_email"]
    with pytest.raises(ValidationError):
        parse_row(raw, row_number=1)


def test_parse_row_defaults_country_when_blank():
    row = parse_row(_valid_raw(site_country=""), row_number=1)
    assert row.site_country == "United States"


def test_parse_row_parses_two_ports():
    row = parse_row(_valid_raw(), row_number=1)
    assert len(row.ports) == 2


def test_parse_row_port_voltage_is_float():
    row = parse_row(_valid_raw(), row_number=1)
    assert row.ports[0].voltage_v == 240.0


def test_parse_row_missing_port_columns_for_declared_count_raises():
    raw = _valid_raw(port_count="3")
    with pytest.raises(ValidationError):
        parse_row(raw, row_number=1)


def test_parse_row_invalid_port_count_raises():
    raw = _valid_raw(port_count="not-a-number")
    with pytest.raises(ValidationError):
        parse_row(raw, row_number=1)
