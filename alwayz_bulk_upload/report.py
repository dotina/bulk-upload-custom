from __future__ import annotations

import csv

from alwayz_bulk_upload.uploader import RowResult

REPORT_COLUMNS = ["row_number", "site_name", "serial_number", "action", "site_id", "charger_id", "error"]


def write_report(results: list[RowResult], out_path: str) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "row_number": result.row_number,
                    "site_name": result.site_name,
                    "serial_number": result.serial_number,
                    "action": result.action,
                    "site_id": result.site_id or "",
                    "charger_id": result.charger_id or "",
                    "error": result.error or "",
                }
            )


def summarize(results: list[RowResult]) -> str:
    counts = {"created": 0, "skipped_existing": 0, "would_create": 0, "failed": 0}
    for result in results:
        counts[result.action] = counts.get(result.action, 0) + 1
    return (
        f"{counts['created']} created, {counts['skipped_existing']} skipped (existing), "
        f"{counts['would_create']} would-create (dry-run), {counts['failed']} failed"
    )
