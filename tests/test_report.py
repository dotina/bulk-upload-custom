import csv

from alwayz_bulk_upload.report import summarize, write_report
from alwayz_bulk_upload.uploader import RowResult


def test_write_report_writes_charger_id_column(tmp_path):
    out_path = tmp_path / "results.csv"
    results = [
        RowResult(row_number=2, site_name="Site A", serial_number="SN-1", action="created", site_id="s1", charger_id="c1")
    ]

    write_report(results, str(out_path))

    with open(out_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["charger_id"] == "c1"


def test_write_report_blank_error_for_successful_row(tmp_path):
    out_path = tmp_path / "results.csv"
    results = [
        RowResult(row_number=2, site_name="Site A", serial_number="SN-1", action="created", site_id="s1", charger_id="c1")
    ]

    write_report(results, str(out_path))

    with open(out_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["error"] == ""


def test_summarize_counts_created_rows():
    results = [
        RowResult(row_number=2, site_name="A", serial_number="1", action="created"),
        RowResult(row_number=3, site_name="B", serial_number="2", action="failed", error="boom"),
    ]

    summary = summarize(results)

    assert "1 created" in summary
