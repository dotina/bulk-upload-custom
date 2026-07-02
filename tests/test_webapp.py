import io
import json
from unittest.mock import MagicMock, patch

import pytest

from webapp import app


def test_index_returns_200():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200


def test_index_contains_company_id_field():
    client = app.test_client()
    response = client.get("/")
    assert b'name="company_id"' in response.data


def test_index_token_field_is_password_type():
    client = app.test_client()
    response = client.get("/")
    assert b'type="password"' in response.data


def test_index_contains_wizard_steps():
    client = app.test_client()
    response = client.get("/")
    assert b"Validation" in response.data
    assert b"Validate data" in response.data


@pytest.fixture(autouse=True)
def _redirect_report_dir(tmp_path):
    original = app.config.get("REPORT_DIR")
    app.config["REPORT_DIR"] = str(tmp_path)
    yield
    app.config["REPORT_DIR"] = original


def _mock_client():
    client = MagicMock()
    client.load_reference_data.return_value = MagicMock(
        charger_types={"level 2": "type-1"},
        connector_types={"j1772": "conn-1"},
        charger_statuses={},
        ev_networks={},
    )
    client.list_sites.return_value = {}
    client.list_chargers.return_value = {}
    client.create_site.return_value = {"id": "site-1"}
    client.create_charger.return_value = {"id": "charger-1"}
    return client


CANONICAL_CSV = (
    "site_name,site_street_address,site_city,site_contact_email,"
    "charger_name,serial_number,charger_type,port_count,"
    "port1_connector_type,port1_voltage_v,port1_current_a\n"
    "ESPN / Test,1 Espn Plaza,Bristol,ops@example.com,"
    "ESPN / Test,SN-1,Level 2,1,"
    "J1772,240,30\n"
)


def _post_run(csv_text, **extra):
    test_client = app.test_client()
    data = {
        "file": (io.BytesIO(csv_text.encode("utf-8")), "input.csv"),
        "base_url": "https://api.example.com",
        "company_id": "company-1",
        "token": "tok",
        "format_type": "canonical",
        **extra,
    }
    response = test_client.post("/run", data=data, content_type="multipart/form-data")
    return [json.loads(line) for line in response.data.decode("utf-8").splitlines() if line]


def _post_validate(csv_text, **extra):
    test_client = app.test_client()
    data = {
        "file": (io.BytesIO(csv_text.encode("utf-8")), "input.csv"),
        "base_url": "https://api.example.com",
        "company_id": "company-1",
        "token": "tok",
        "format_type": "canonical",
        **extra,
    }
    response = test_client.post("/validate", data=data, content_type="multipart/form-data")
    return response


@patch("webapp.AlwayzApiClient")
def test_run_emits_status_line_first(mock_client_cls):
    mock_client_cls.return_value = _mock_client()
    lines = _post_run(CANONICAL_CSV)
    assert lines[0]["type"] == "status"


@patch("webapp.AlwayzApiClient")
def test_run_emits_start_with_total(mock_client_cls):
    mock_client_cls.return_value = _mock_client()
    lines = _post_run(CANONICAL_CSV)
    start_line = next(line for line in lines if line["type"] == "start")
    assert start_line["total"] == 1


@patch("webapp.AlwayzApiClient")
def test_run_emits_row_line_with_created_action(mock_client_cls):
    mock_client_cls.return_value = _mock_client()
    lines = _post_run(CANONICAL_CSV)
    row_lines = [line for line in lines if line["type"] == "row"]
    assert row_lines[0]["action"] == "created"


@patch("webapp.AlwayzApiClient")
def test_run_emits_done_line_with_summary(mock_client_cls):
    mock_client_cls.return_value = _mock_client()
    lines = _post_run(CANONICAL_CSV)
    done_line = next(line for line in lines if line["type"] == "done")
    assert "1 created" in done_line["summary"]


@patch("webapp.AlwayzApiClient")
def test_run_emits_error_line_for_malformed_csv(mock_client_cls):
    mock_client_cls.return_value = _mock_client()
    lines = _post_run("not,a,valid,canonical,csv\n1,2,3,4,5\n")
    assert lines[0]["type"] == "error"


@patch("webapp.AlwayzApiClient")
def test_validate_returns_report_json(mock_client_cls):
    mock_client_cls.return_value = _mock_client()
    response = _post_validate(CANONICAL_CSV)
    assert response.status_code == 200
    data = response.get_json()
    assert data["summary"]["can_commit"] is True
    assert len(data["sites"]) == 1
    assert data["sites"][0]["chargers"][0]["planned_action"] == "create_site_and_charger"


@patch("webapp.AlwayzApiClient")
def test_validate_returns_400_for_malformed_csv(mock_client_cls):
    mock_client_cls.return_value = _mock_client()
    response = _post_validate("not,a,valid,canonical,csv\n1,2,3,4,5\n")
    assert response.status_code == 400
    assert "error" in response.get_json()


@patch("webapp.read_input")
@patch("webapp.AlwayzApiClient")
def test_validate_espn_ct_format(mock_client_cls, mock_read_input):
    from alwayz_bulk_upload.canonical_schema import parse_row

    mock_read_input.return_value = [
        parse_row(
            {
                "site_name": "ESPN / Test",
                "site_street_address": "1 Espn Plaza",
                "site_city": "Bristol",
                "site_contact_email": "ops@example.com",
                "charger_name": "ESPN / Test",
                "serial_number": "SN-1",
                "charger_type": "Level 2",
                "port_count": "1",
                "port1_connector_type": "J1772",
                "port1_voltage_v": "240",
                "port1_current_a": "30",
            },
            row_number=2,
        )
    ]
    mock_client_cls.return_value = _mock_client()
    response = _post_validate(
        CANONICAL_CSV,
        format_type="espn_ct",
        default_contact_email="ops@example.com",
    )
    assert response.status_code == 200
    mock_read_input.assert_called_once()
