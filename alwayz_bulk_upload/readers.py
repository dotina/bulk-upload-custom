from __future__ import annotations

import csv

import openpyxl

from alwayz_bulk_upload.canonical_schema import CanonicalRow, parse_row
from convert_espn_ct import convert_workbook

FORMAT_CANONICAL = "canonical"
FORMAT_ESPN_CT = "espn_ct"


def read_input(
    path: str,
    format_type: str,
    *,
    default_contact_email: str | None = None,
) -> list[CanonicalRow]:
    if format_type == FORMAT_CANONICAL:
        if path.lower().endswith(".csv"):
            return read_canonical_csv(path)
        return read_canonical_excel(path)
    if format_type == FORMAT_ESPN_CT:
        if not default_contact_email:
            raise ValueError("default_contact_email is required for espn_ct format")
        raw_rows = convert_workbook(path, default_contact_email)
        return [parse_row(raw, row_number=i) for i, raw in enumerate(raw_rows, start=2)]
    raise ValueError(f"unknown format_type: {format_type!r}")


def read_canonical_csv(path: str) -> list[CanonicalRow]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [parse_row(raw, row_number=i) for i, raw in enumerate(reader, start=2)]


def read_canonical_excel(path: str, sheet_name: str | None = None) -> list[CanonicalRow]:
    workbook = openpyxl.load_workbook(path, data_only=True)
    sheet = workbook[sheet_name] if sheet_name else workbook.worksheets[0]
    rows_iter = sheet.iter_rows(values_only=True)
    headers = [str(h) for h in next(rows_iter)]
    rows = []
    for i, values in enumerate(rows_iter, start=2):
        raw = {header: ("" if value is None else str(value)) for header, value in zip(headers, values)}
        rows.append(parse_row(raw, row_number=i))
    return rows
