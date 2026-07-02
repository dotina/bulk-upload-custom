from __future__ import annotations

import argparse
import csv
import sys

import openpyxl

from alwayz_bulk_upload.canonical_schema import CANONICAL_HEADERS

SITE_SHEET = "chargers (3)"
CHARGER_SHEET = "CT chargers"


def _split_address(address: str) -> tuple:
    parts = [part.strip() for part in address.split(",")]
    padded = (parts + [""] * 5)[:5]
    street, city, state, country, zip_code = padded
    return street, city, state, country, zip_code


def _strip_unit_suffix(value) -> str:
    text = str(value).strip()
    while text and not (text[-1].isdigit() or text[-1] == "."):
        text = text[:-1]
    return text


def _sheet_rows_as_dicts(sheet) -> list:
    rows_iter = sheet.iter_rows(values_only=True)
    headers = [str(h) for h in next(rows_iter)]
    return [dict(zip(headers, values)) for values in rows_iter]


def convert_workbook(path: str, default_contact_email: str) -> list:
    workbook = openpyxl.load_workbook(path, data_only=True)
    site_rows = _sheet_rows_as_dicts(workbook[SITE_SHEET])
    charger_rows = _sheet_rows_as_dicts(workbook[CHARGER_SHEET])

    sites_by_name = {row["name"]: row for row in site_rows}

    canonical_rows = []
    for charger in charger_rows:
        display_name = charger["Display Name"]
        site = sites_by_name.get(display_name)
        if site is None:
            raise ValueError(f"No matching site row for Display Name '{display_name}'")

        # Prefer the dedicated site sheet's coordinates over the EVSE sheet's
        # near-duplicate lat/long columns to avoid picking between two sources of truth.
        street, city, state, country, zip_code = _split_address(site["address"])
        canonical_rows.append(
            {
                "site_name": display_name,
                "site_street_address": street,
                "site_city": city,
                "site_state": state,
                "site_zip": zip_code,
                "site_country": country,
                "site_latitude": site["latitude"],
                "site_longitude": site["longitude"],
                "site_contact_email": default_contact_email,
                "charger_name": display_name,
                "serial_number": charger["Serial Number"],
                "charger_type": "Level 2",
                "connector_type": charger["Port 1: Connector Type"],
                "external_id": charger["EVSE ID"],
                "mac_address": charger["MAC Address"],
                "usage_category": charger["EVSE Usage Category"],
                "port_count": 2,
                "port1_connector_type": charger["Port 1: Connector Type"],
                "port1_voltage_v": _strip_unit_suffix(charger["Port 1: Voltage (V)"]),
                "port1_current_a": _strip_unit_suffix(charger["Port 1: Current (A)"]),
                "port2_connector_type": charger["Port 2: Connector Type"],
                "port2_voltage_v": _strip_unit_suffix(charger["Port 2: Voltage (V)"]),
                "port2_current_a": _strip_unit_suffix(charger["Port 2: Current (A)"]),
            }
        )
    return canonical_rows


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert the ESPN CT chargers export to the canonical bulk-upload schema."
    )
    parser.add_argument("--input", required=True, help="Path to CT chargers.xlsx")
    parser.add_argument("--output", required=True, help="Path to write the canonical CSV")
    parser.add_argument(
        "--default-contact-email", required=True, help="Site contact email (not present in the source export)"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    canonical_rows = convert_workbook(args.input, args.default_contact_email)

    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_HEADERS)
        writer.writeheader()
        writer.writerows(canonical_rows)

    print(f"Wrote {len(canonical_rows)} canonical rows to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
