from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from alwayz_bulk_upload.api_client import AlwayzApiClient
from alwayz_bulk_upload.readers import FORMAT_ESPN_CT, read_input
from alwayz_bulk_upload.report import summarize, write_report
from alwayz_bulk_upload.uploader import iter_upload_rows
from alwayz_bulk_upload.validation import validate_rows, validation_report_to_dict

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config["REPORT_DIR"] = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
def index():
    return render_template("index.html")


def _save_uploaded_file(uploaded_file) -> str:
    suffix = os.path.splitext(uploaded_file.filename)[1] or ".csv"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()
    uploaded_file.save(tmp.name)
    return tmp.name


def _form_params():
    format_type = request.form.get("format_type", "canonical")
    default_contact_email = request.form.get("default_contact_email") or None
    if format_type == FORMAT_ESPN_CT and not default_contact_email:
        raise ValueError("default_contact_email is required for ESPN CT workbook format")
    return {
        "base_url": request.form["base_url"],
        "company_id": request.form["company_id"],
        "token": request.form["token"],
        "format_type": format_type,
        "default_contact_email": default_contact_email,
    }


def _stream_upload(file_path, params, report_dir):
    try:
        rows = read_input(
            file_path,
            params["format_type"],
            default_contact_email=params["default_contact_email"],
        )
        yield json.dumps({"type": "status", "message": "Loading reference data..."}) + "\n"
        client = AlwayzApiClient(params["base_url"], params["token"])
        reference_data = client.load_reference_data()
        yield json.dumps({"type": "start", "total": len(rows)}) + "\n"
    except Exception as exc:
        app.logger.exception("Upload preparation failed")
        yield json.dumps({"type": "error", "message": str(exc)}) + "\n"
        return

    results = []
    for result in iter_upload_rows(
        rows, client, reference_data, params["company_id"], dry_run=False
    ):
        results.append(result)
        yield json.dumps(
            {
                "type": "row",
                "row_number": result.row_number,
                "site_name": result.site_name,
                "serial_number": result.serial_number,
                "action": result.action,
                "site_id": result.site_id,
                "charger_id": result.charger_id,
                "error": result.error,
                "warnings": result.warnings,
            }
        ) + "\n"

    out_report = os.path.join(report_dir, f"results_{datetime.now():%Y%m%d_%H%M%S}.csv")
    write_report(results, out_report)
    yield json.dumps({"type": "done", "summary": summarize(results), "report_path": out_report}) + "\n"


@app.post("/validate")
def validate():
    uploaded_file = request.files["file"]
    tmp_path = _save_uploaded_file(uploaded_file)
    try:
        params = _form_params()
        rows = read_input(
            tmp_path,
            params["format_type"],
            default_contact_email=params["default_contact_email"],
        )
        client = AlwayzApiClient(params["base_url"], params["token"])
        reference_data = client.load_reference_data()
        report = validate_rows(rows, client, reference_data, params["company_id"])
        return jsonify(validation_report_to_dict(report))
    except Exception as exc:
        app.logger.exception("Validation failed")
        return jsonify({"error": str(exc)}), 400
    finally:
        os.remove(tmp_path)


@app.post("/run")
def run():
    uploaded_file = request.files["file"]
    tmp_path = _save_uploaded_file(uploaded_file)
    params = _form_params()
    report_dir = app.config["REPORT_DIR"]

    def generate():
        try:
            yield from _stream_upload(tmp_path, params, report_dir)
        finally:
            os.remove(tmp_path)

    return Response(generate(), mimetype="application/x-ndjson")


if __name__ == "__main__":
    app.run(host="127.0.0.1", debug=False)
