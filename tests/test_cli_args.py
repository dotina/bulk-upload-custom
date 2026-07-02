import pytest

from upload_sites_chargers import parse_args


def test_parse_args_reads_required_flags():
    args = parse_args(
        ["--input", "data.csv", "--company-id", "c1", "--base-url", "https://api.example.com", "--token", "tok"]
    )
    assert args.company_id == "c1"


def test_parse_args_falls_back_to_env_token(monkeypatch):
    monkeypatch.setenv("ALWAYZ_API_TOKEN", "env-token")
    args = parse_args(["--input", "data.csv", "--company-id", "c1", "--base-url", "https://api.example.com"])
    assert args.token == "env-token"


def test_parse_args_missing_token_exits(monkeypatch):
    monkeypatch.delenv("ALWAYZ_API_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        parse_args(["--input", "data.csv", "--company-id", "c1", "--base-url", "https://api.example.com"])


def test_parse_args_dry_run_flag_defaults_false():
    args = parse_args(
        ["--input", "data.csv", "--company-id", "c1", "--base-url", "https://api.example.com", "--token", "tok"]
    )
    assert args.dry_run is False
