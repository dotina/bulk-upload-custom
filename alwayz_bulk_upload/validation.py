from __future__ import annotations

from dataclasses import asdict, dataclass, field

from alwayz_bulk_upload.api_client import AlwayzApiClient, ReferenceData
from alwayz_bulk_upload.canonical_schema import CanonicalRow
from alwayz_bulk_upload.errors import UploadError
from alwayz_bulk_upload.uploader import build_charger_payload, build_site_payload


@dataclass
class ChargerPreview:
    row_number: int
    serial_number: str
    charger_name: str
    planned_action: str
    charger_payload: dict | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SitePreview:
    site_name: str
    planned_action: str
    site_payload: dict
    existing_site_id: str | None
    chargers: list[ChargerPreview] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    sites: list[SitePreview]
    summary: dict
    reference_labels: dict


def _site_identity_key(payload: dict) -> tuple:
    address = payload.get("address") or {}
    contact = payload.get("contact") or {}
    return (
        address.get("streetAddress"),
        address.get("city"),
        address.get("state"),
        address.get("zipCode"),
        address.get("country"),
        contact.get("email"),
    )


def _validate_row(
    row: CanonicalRow,
    reference_data: ReferenceData,
    existing_sites: dict,
    existing_chargers: dict,
    seen_serials: dict[str, int],
) -> ChargerPreview:
    errors: list[str] = []
    warnings: list[str] = []

    if row.serial_number in seen_serials:
        errors.append(
            f"duplicate serial_number '{row.serial_number}' (first seen on row {seen_serials[row.serial_number]})"
        )
    else:
        seen_serials[row.serial_number] = row.row_number

    existing_charger = existing_chargers.get(row.serial_number)
    if existing_charger is not None:
        return ChargerPreview(
            row_number=row.row_number,
            serial_number=row.serial_number,
            charger_name=row.charger_name,
            planned_action="skip_existing",
            charger_payload=None,
            errors=errors,
            warnings=warnings,
        )

    site_payload = build_site_payload(row)
    charger_payload = None
    try:
        charger_payload = build_charger_payload(row, reference_data, warnings)
    except UploadError as exc:
        errors.append(str(exc))

    existing_site = existing_sites.get(row.site_name)
    if existing_site is not None:
        planned_action = "reuse_site_create_charger"
    else:
        planned_action = "create_site_and_charger"

    return ChargerPreview(
        row_number=row.row_number,
        serial_number=row.serial_number,
        charger_name=row.charger_name,
        planned_action=planned_action,
        charger_payload=charger_payload,
        errors=errors,
        warnings=warnings,
    )


def validate_rows(
    rows: list[CanonicalRow],
    client: AlwayzApiClient,
    reference_data: ReferenceData,
    company_id: str,
) -> ValidationReport:
    existing_sites = client.list_sites(company_id)
    existing_chargers = client.list_chargers(company_id)
    seen_serials: dict[str, int] = {}

    by_site: dict[str, list[tuple[CanonicalRow, ChargerPreview]]] = {}
    for row in rows:
        preview = _validate_row(row, reference_data, existing_sites, existing_chargers, seen_serials)
        by_site.setdefault(row.site_name, []).append((row, preview))

    sites: list[SitePreview] = []
    counts = {
        "total_sites": 0,
        "new_sites": 0,
        "reused_sites": 0,
        "total_chargers": 0,
        "chargers_to_create": 0,
        "chargers_skipped": 0,
        "errors": 0,
        "warnings": 0,
    }

    for site_name, entries in by_site.items():
        first_row, _ = entries[0]
        site_payload = build_site_payload(first_row)
        existing_site = existing_sites.get(site_name)
        site_planned = "reuse_existing" if existing_site is not None else "create"
        site_errors: list[str] = []
        site_warnings: list[str] = []

        identity_keys = {_site_identity_key(build_site_payload(row)) for row, _ in entries}
        if len(identity_keys) > 1:
            site_warnings.append("rows for this site have differing address or contact details")

        chargers = [preview for _, preview in entries]
        for preview in chargers:
            counts["total_chargers"] += 1
            counts["errors"] += len(preview.errors)
            counts["warnings"] += len(preview.warnings)
            if preview.planned_action == "skip_existing":
                counts["chargers_skipped"] += 1
            elif not preview.errors:
                counts["chargers_to_create"] += 1

        sites.append(
            SitePreview(
                site_name=site_name,
                planned_action=site_planned,
                site_payload=site_payload,
                existing_site_id=existing_site.id if existing_site else None,
                chargers=chargers,
                errors=site_errors,
                warnings=site_warnings,
            )
        )
        counts["total_sites"] += 1
        if site_planned == "create":
            counts["new_sites"] += 1
        else:
            counts["reused_sites"] += 1
        counts["errors"] += len(site_errors)
        counts["warnings"] += len(site_warnings)

    can_commit = counts["errors"] == 0
    summary = {**counts, "can_commit": can_commit}

    reference_labels = {
        "charger_types": sorted(reference_data.charger_types.keys()),
        "connector_types": sorted(reference_data.connector_types.keys()),
        "charger_statuses": sorted(reference_data.charger_statuses.keys()),
        "ev_networks": sorted(reference_data.ev_networks.keys()),
    }

    return ValidationReport(sites=sites, summary=summary, reference_labels=reference_labels)


def validation_report_to_dict(report: ValidationReport) -> dict:
    return asdict(report)
