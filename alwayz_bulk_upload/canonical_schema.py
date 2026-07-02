from __future__ import annotations

from dataclasses import dataclass

from alwayz_bulk_upload.errors import ValidationError

REQUIRED_COLUMNS = (
    "site_name",
    "site_street_address",
    "site_city",
    "site_contact_email",
    "charger_name",
    "serial_number",
    "charger_type",
    "port_count",
)

DEFAULT_COUNTRY = "United States"

CANONICAL_HEADERS = (
    "site_name", "site_external_id", "site_street_address", "site_city", "site_state", "site_zip",
    "site_country", "site_latitude", "site_longitude", "site_contact_email", "site_contact_first_name",
    "site_contact_last_name", "site_contact_phone", "site_notes",
    "charger_name", "serial_number", "charger_type", "connector_type", "model", "manufacturer",
    "charger_status", "ev_network", "external_id", "warranties_and_agreements",
    "mac_address", "usage_category", "port_count",
    "port1_connector_type", "port1_voltage_v", "port1_current_a",
    "port2_connector_type", "port2_voltage_v", "port2_current_a",
)


@dataclass
class PortSpec:
    connector_type: str | None
    voltage_v: float | None
    current_a: float | None


@dataclass
class CanonicalRow:
    row_number: int
    site_name: str
    site_street_address: str
    site_city: str
    site_contact_email: str
    charger_name: str
    serial_number: str
    charger_type: str
    port_count: int
    ports: list[PortSpec]
    site_external_id: str | None = None
    site_state: str | None = None
    site_zip: str | None = None
    site_country: str = DEFAULT_COUNTRY
    site_latitude: float | None = None
    site_longitude: float | None = None
    site_contact_first_name: str | None = None
    site_contact_last_name: str | None = None
    site_contact_phone: str | None = None
    site_notes: str | None = None
    connector_type: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    charger_status: str | None = None
    ev_network: str | None = None
    external_id: str | None = None
    warranties_and_agreements: str | None = None
    mac_address: str | None = None
    usage_category: str | None = None


def _optional_str(value) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None


def _optional_float(value) -> float | None:
    text = _optional_str(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValidationError(f"expected a number, got {value!r}") from exc


def parse_row(raw: dict, row_number: int) -> CanonicalRow:
    for column in REQUIRED_COLUMNS:
        if not _optional_str(raw.get(column)):
            raise ValidationError(f"row {row_number}: missing required column '{column}'")

    try:
        port_count = int(str(raw["port_count"]).strip())
    except ValueError as exc:
        raise ValidationError(
            f"row {row_number}: port_count must be an integer, got {raw['port_count']!r}"
        ) from exc
    if port_count < 1:
        raise ValidationError(f"row {row_number}: port_count must be >= 1, got {port_count}")

    ports = []
    for i in range(1, port_count + 1):
        connector_key = f"port{i}_connector_type"
        voltage_key = f"port{i}_voltage_v"
        current_key = f"port{i}_current_a"
        if connector_key not in raw and voltage_key not in raw and current_key not in raw:
            raise ValidationError(
                f"row {row_number}: port_count={port_count} but no port{i}_* columns present"
            )
        ports.append(
            PortSpec(
                connector_type=_optional_str(raw.get(connector_key)),
                voltage_v=_optional_float(raw.get(voltage_key)),
                current_a=_optional_float(raw.get(current_key)),
            )
        )

    return CanonicalRow(
        row_number=row_number,
        site_name=str(raw["site_name"]).strip(),
        site_street_address=str(raw["site_street_address"]).strip(),
        site_city=str(raw["site_city"]).strip(),
        site_contact_email=str(raw["site_contact_email"]).strip(),
        charger_name=str(raw["charger_name"]).strip(),
        serial_number=str(raw["serial_number"]).strip(),
        charger_type=str(raw["charger_type"]).strip(),
        port_count=port_count,
        ports=ports,
        site_external_id=_optional_str(raw.get("site_external_id")),
        site_state=_optional_str(raw.get("site_state")),
        site_zip=_optional_str(raw.get("site_zip")),
        site_country=_optional_str(raw.get("site_country")) or DEFAULT_COUNTRY,
        site_latitude=_optional_float(raw.get("site_latitude")),
        site_longitude=_optional_float(raw.get("site_longitude")),
        site_contact_first_name=_optional_str(raw.get("site_contact_first_name")),
        site_contact_last_name=_optional_str(raw.get("site_contact_last_name")),
        site_contact_phone=_optional_str(raw.get("site_contact_phone")),
        site_notes=_optional_str(raw.get("site_notes")),
        connector_type=_optional_str(raw.get("connector_type")),
        model=_optional_str(raw.get("model")),
        manufacturer=_optional_str(raw.get("manufacturer")),
        charger_status=_optional_str(raw.get("charger_status")),
        ev_network=_optional_str(raw.get("ev_network")),
        external_id=_optional_str(raw.get("external_id")),
        warranties_and_agreements=_optional_str(raw.get("warranties_and_agreements")),
        mac_address=_optional_str(raw.get("mac_address")),
        usage_category=_optional_str(raw.get("usage_category")),
    )
