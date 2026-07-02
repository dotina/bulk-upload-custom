import csv

import openpyxl
import pytest

from alwayz_bulk_upload.errors import ValidationError
from alwayz_bulk_upload.readers import FORMAT_CANONICAL, FORMAT_ESPN_CT, read_canonical_csv, read_canonical_excel, read_input

CANONICAL_HEADERS = [
    "site_name", "site_street_address", "site_city", "site_contact_email",
    "charger_name", "serial_number", "charger_type", "port_count",
    "port1_connector_type", "port1_voltage_v", "port1_current_a",
]

VALID_ROW = [
    "ESPN / ESPN 11-2", "1 Espn Plaza", "Bristol", "ops@example.com",
    "ESPN / ESPN 11-2", "172841008201", "Level 2", "1",
    "J1772", "240", "30",
]


def test_read_canonical_csv_parses_one_row(tmp_path):
    csv_path = tmp_path / "input.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CANONICAL_HEADERS)
        writer.writerow(VALID_ROW)

    rows = read_canonical_csv(str(csv_path))

    assert len(rows) == 1


def test_read_canonical_csv_row_number_accounts_for_header(tmp_path):
    csv_path = tmp_path / "input.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CANONICAL_HEADERS)
        writer.writerow(VALID_ROW)

    rows = read_canonical_csv(str(csv_path))

    assert rows[0].row_number == 2


def test_read_canonical_csv_invalid_row_raises(tmp_path):
    csv_path = tmp_path / "input.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CANONICAL_HEADERS)
        writer.writerow(["", *VALID_ROW[1:]])

    with pytest.raises(ValidationError):
        read_canonical_csv(str(csv_path))


def test_read_canonical_excel_parses_one_row(tmp_path):
    xlsx_path = tmp_path / "input.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(CANONICAL_HEADERS)
    sheet.append(VALID_ROW)
    workbook.save(xlsx_path)

    rows = read_canonical_excel(str(xlsx_path))

    assert rows[0].serial_number == "172841008201"


def test_read_input_canonical_csv(tmp_path):
    csv_path = tmp_path / "input.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CANONICAL_HEADERS)
        writer.writerow(VALID_ROW)

    rows = read_input(str(csv_path), FORMAT_CANONICAL)

    assert len(rows) == 1
    assert rows[0].serial_number == "172841008201"


def test_read_input_espn_ct_requires_contact_email(tmp_path):
    xlsx_path = tmp_path / "input.xlsx"
    workbook = openpyxl.Workbook()
    workbook.save(xlsx_path)

    with pytest.raises(ValueError, match="default_contact_email"):
        read_input(str(xlsx_path), FORMAT_ESPN_CT)


def test_read_input_unknown_format_raises(tmp_path):
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("a\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown format_type"):
        read_input(str(csv_path), "bogus")
