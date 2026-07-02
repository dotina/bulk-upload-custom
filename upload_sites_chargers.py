from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from alwayz_bulk_upload.api_client import AlwayzApiClient
from alwayz_bulk_upload.readers import read_canonical_csv, read_canonical_excel
from alwayz_bulk_upload.report import summarize, write_report
from alwayz_bulk_upload.uploader import upload_rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-create Alwayz sites and chargers from a canonical CSV/Excel file."
    )
    parser.add_argument("--input", required=True, help="Path to a canonical CSV or .xlsx file")
    parser.add_argument("--company-id", required=True, help="Target company UUID")
    parser.add_argument("--base-url", required=True, help="Alwayz API base URL, e.g. https://api.dev.alwayz.us")
    parser.add_argument(
        "--token", default=os.environ.get("ALWAYZ_API_TOKEN"), help="Bearer token (or set ALWAYZ_API_TOKEN)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen without creating anything")
    parser.add_argument(
        "--out-report", default=None, help="Path for the results CSV (default: results_<timestamp>.csv next to --input)"
    )
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("--token or ALWAYZ_API_TOKEN environment variable is required")
    return args


def _read_rows(input_path: str):
    if input_path.lower().endswith(".csv"):
        return read_canonical_csv(input_path)
    return read_canonical_excel(input_path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rows = _read_rows(args.input)

    client = AlwayzApiClient(args.base_url, args.token)
    reference_data = client.load_reference_data()

    results = upload_rows(rows, client, reference_data, args.company_id, dry_run=args.dry_run)

    default_report_dir = os.path.dirname(os.path.abspath(args.input))
    default_report_name = f"results_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out_report = args.out_report or os.path.join(default_report_dir, default_report_name)
    write_report(results, out_report)

    print(summarize(results))
    print(f"Full report written to {out_report}")
    return 1 if any(r.action == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
