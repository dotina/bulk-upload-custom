from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from alwayz_bulk_upload.api_client import AlwayzApiClient, ChargerSummary, ReferenceData, SiteSummary
from alwayz_bulk_upload.canonical_schema import CanonicalRow
from alwayz_bulk_upload.errors import ReferenceNotFoundError, UploadError

logger = logging.getLogger(__name__)

DEFAULT_CHARGER_TYPE = "Level 2"


def build_site_payload(row: CanonicalRow) -> dict:
    payload = {
        "name": row.site_name,
        "address": {
            "streetAddress": row.site_street_address,
            "city": row.site_city,
            "state": row.site_state,
            "zipCode": row.site_zip,
            "country": row.site_country,
            "latitude": row.site_latitude,
            "longitude": row.site_longitude,
        },
        "contact": {
            "email": row.site_contact_email,
            "contactFirstName": row.site_contact_first_name,
            "contactLastName": row.site_contact_last_name,
            "phoneNumber": row.site_contact_phone,
        },
        "notes": row.site_notes,
    }
    if row.site_external_id:
        payload["externalId"] = row.site_external_id
    return payload


def _resolve_reference_id(name: str | None, lookup: dict, label: str) -> str | None:
    if not name:
        return None
    resolved = lookup.get(name.lower())
    if resolved is None:
        raise ReferenceNotFoundError(f"{label} '{name}' not found")
    return resolved


def _resolve_optional_reference_id(
    name: str | None, lookup: dict, label: str, row: CanonicalRow, warnings: list[str] | None = None
) -> str | None:
    """Resolve an optional reference id. Unknown values are reported and omitted, not raised."""
    if not name:
        return None
    resolved = lookup.get(name.lower())
    if resolved is not None:
        return resolved
    message = f"{label} '{name}' not found; omitted (optional field)"
    logger.warning("row %s: %s", row.row_number, message)
    if warnings is not None:
        warnings.append(message)
    return None


def _resolve_charger_type_id(
    row: CanonicalRow, reference_data: ReferenceData, warnings: list[str] | None = None
) -> str | None:
    resolved = reference_data.charger_types.get(row.charger_type.lower())
    if resolved is not None:
        return resolved

    default_id = reference_data.charger_types.get(DEFAULT_CHARGER_TYPE.lower())
    if default_id is None:
        # Nothing to fall back to — we can't invent a valid charger type id.
        raise ReferenceNotFoundError(
            f"charger_type '{row.charger_type}' not found and default "
            f"'{DEFAULT_CHARGER_TYPE}' is unavailable"
        )

    message = f"charger_type '{row.charger_type}' not found; defaulted to '{DEFAULT_CHARGER_TYPE}'"
    logger.warning("row %s: %s", row.row_number, message)
    if warnings is not None:
        warnings.append(message)
    return default_id


def _resolved_connector_type(row: CanonicalRow) -> str | None:
    if row.connector_type:
        resolved = row.connector_type
    elif row.ports:
        resolved = row.ports[0].connector_type
    else:
        return None
    for i, port in enumerate(row.ports, start=1):
        if port.connector_type and port.connector_type != resolved:
            logger.warning(
                "row %s: port%s connector_type '%s' differs from charger-level connector type '%s'",
                row.row_number, i, port.connector_type, resolved,
            )
    return resolved


def _import_metadata_note(row: CanonicalRow) -> str:
    parts = []
    if row.external_id:
        parts.append(f"external_id={row.external_id}")
    if row.mac_address:
        parts.append(f"mac_address={row.mac_address}")
    if row.usage_category:
        parts.append(f"usage_category={row.usage_category}")
    if row.manufacturer:
        parts.append(f"manufacturer={row.manufacturer}")
    for i, port in enumerate(row.ports, start=1):
        if port.connector_type or port.voltage_v is not None or port.current_a is not None:
            voltage = f"{port.voltage_v:g}V" if port.voltage_v is not None else "?V"
            current = f"{port.current_a:g}A" if port.current_a is not None else "?A"
            parts.append(f"port{i}: {port.connector_type or '?'} {voltage}/{current}")
    return "[Import metadata] " + "; ".join(parts) if parts else ""


def _warranties_and_agreements(row: CanonicalRow) -> str | None:
    note = _import_metadata_note(row)
    if row.warranties_and_agreements and note:
        return f"{row.warranties_and_agreements}\n{note}"
    return row.warranties_and_agreements or note or None


def build_charger_payload(
    row: CanonicalRow, reference_data: ReferenceData, warnings: list[str] | None = None
) -> dict:
    payload = {
        "name": row.charger_name,
        "serialNumber": row.serial_number,
        "chargerTypeId": _resolve_charger_type_id(row, reference_data, warnings),
        "numberOfPorts": row.port_count,
        # Required by the DB (charger.is_warranty_active is NOT NULL); the column
        # default is not applied because the ORM writes the column explicitly.
        "isWarrantyActive": False,
    }
    # connector/status/network are optional on the backend: an unresolved value
    # is reported as a non-blocking warning and simply omitted, never a hard error.
    connector_id = _resolve_optional_reference_id(
        _resolved_connector_type(row), reference_data.connector_types, "connector_type", row, warnings
    )
    if connector_id:
        payload["connectorTypeId"] = connector_id
    status_id = _resolve_optional_reference_id(
        row.charger_status, reference_data.charger_statuses, "charger_status", row, warnings
    )
    if status_id:
        payload["chargerStatusId"] = status_id
    network_id = _resolve_optional_reference_id(
        row.ev_network, reference_data.ev_networks, "ev_network", row, warnings
    )
    if network_id:
        payload["evNetworkId"] = network_id
    if row.model:
        payload["model"] = row.model
    warranties = _warranties_and_agreements(row)
    if warranties:
        payload["warrantiesAndAgreements"] = warranties
    return payload


@dataclass
class RowResult:
    row_number: int
    site_name: str
    serial_number: str
    action: str
    site_id: str | None = None
    charger_id: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def iter_upload_rows(
    rows: list[CanonicalRow],
    client: AlwayzApiClient,
    reference_data: ReferenceData,
    company_id: str,
    dry_run: bool = False,
) -> Iterator[RowResult]:
    existing_sites = client.list_sites(company_id)
    existing_chargers = client.list_chargers(company_id)

    for row in rows:
        try:
            yield _upload_row(row, client, reference_data, company_id, existing_sites, existing_chargers, dry_run)
        except UploadError as exc:
            yield RowResult(
                row_number=row.row_number,
                site_name=row.site_name,
                serial_number=row.serial_number,
                action="failed",
                error=str(exc),
            )


def upload_rows(
    rows: list[CanonicalRow],
    client: AlwayzApiClient,
    reference_data: ReferenceData,
    company_id: str,
    dry_run: bool = False,
) -> list[RowResult]:
    return list(iter_upload_rows(rows, client, reference_data, company_id, dry_run))


def _upload_row(row, client, reference_data, company_id, existing_sites, existing_chargers, dry_run) -> RowResult:
    existing_charger = existing_chargers.get(row.serial_number)
    if existing_charger is not None:
        return RowResult(
            row_number=row.row_number,
            site_name=row.site_name,
            serial_number=row.serial_number,
            action="skipped_existing",
            site_id=existing_charger.site_id,
            charger_id=existing_charger.id,
        )

    # Validate charger payload early to fail fast if references don't exist.
    warnings: list[str] = []
    charger_payload = build_charger_payload(row, reference_data, warnings)

    existing_site = existing_sites.get(row.site_name)
    if existing_site is not None:
        site_id = existing_site.id
    elif dry_run:
        site_id = None
    else:
        created_site = client.create_site(company_id, build_site_payload(row))
        site_id = created_site["id"]
        existing_sites[row.site_name] = SiteSummary(id=site_id, name=row.site_name)

    if dry_run:
        return RowResult(
            row_number=row.row_number,
            site_name=row.site_name,
            serial_number=row.serial_number,
            action="would_create",
            site_id=site_id,
            warnings=warnings,
        )

    created_charger = client.create_charger(company_id, site_id, charger_payload)
    charger_id = created_charger["id"]
    existing_chargers[row.serial_number] = ChargerSummary(
        id=charger_id, serial_number=row.serial_number, site_id=site_id
    )
    return RowResult(
        row_number=row.row_number,
        site_name=row.site_name,
        serial_number=row.serial_number,
        action="created",
        site_id=site_id,
        charger_id=charger_id,
        warnings=warnings,
    )
