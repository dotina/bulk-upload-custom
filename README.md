# Alwayz Site/Charger Bulk Upload

Bulk-creates Sites and Chargers in the Alwayz API from a canonical CSV/Excel file.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements-dev.txt
```

## Canonical input schema

One row per charger. Required columns: `site_name`, `site_street_address`, `site_city`,
`site_contact_email`, `charger_name`, `serial_number`, `charger_type`, `port_count`.
Optional columns include `site_state`, `site_zip`, `site_country`, `site_latitude`,
`site_longitude`, `connector_type`, `model`, `charger_status`, `ev_network`,
`warranties_and_agreements`, and repeating `port{N}_connector_type` /
`port{N}_voltage_v` / `port{N}_current_a` for `N` = 1..`port_count`. `mac_address`,
`usage_category`, `external_id`, and `manufacturer` have no field on the API's create
request — they get folded into the charger's `warrantiesAndAgreements` text as an
`[Import metadata] ...` note so nothing from the source is silently dropped.

Ports are created as a **count** (`numberOfPorts`), not with per-port metadata — the
API only allows real per-port `ChargerPort` records to link to a pre-existing OCPI/CPMS
integration record, which a plain CSV import doesn't have.

## Convert the ESPN CT chargers export

```bash
python convert_espn_ct.py --input "CT chargers.xlsx" --output espn_canonical.csv --default-contact-email ops@example.com
```

## Upload

```bash
set ALWAYZ_API_TOKEN=<bearer token>
python upload_sites_chargers.py --input espn_canonical.csv --company-id <uuid> --base-url https://api.dev.alwayz.us --dry-run
```

Drop `--dry-run` to actually create records. Re-running the same file is safe — Sites
are matched by name and Chargers by serial number within the company, and existing
matches are skipped rather than duplicated.

Output: a console summary line (created/skipped/failed counts) and a
`results_<timestamp>.csv` report (or the path given to `--out-report`) with one row
per input row: action taken, resulting `site_id`/`charger_id`, and any error.

## Web UI

For entering the token/company ID and running an upload without the command line:

```bash
python webapp.py
```

Open `http://127.0.0.1:5000` in a browser.

### Wizard flow

The UI is a four-step wizard:

1. **Configure** — Choose input format (canonical CSV/Excel or ESPN CT workbook), upload
   the file, and enter Base URL, Company ID, and Bearer Token. For ESPN CT workbooks,
   also provide a default site contact email (not present in the source export).
2. **Validation** — Reviews every site and charger that would be created, shows the API
   payloads that will be sent, flags errors (missing references, duplicate serials) and
   warnings (inconsistent site details). Continue is blocked until all errors are fixed.
3. **Confirmation** — Summary counts of new sites, reused sites, and chargers to create
   or skip.
4. **Commit** — Creates records via the API with a progress bar; results stream into a
   table as each row completes. A full results CSV is written when finished.

The token is never saved anywhere — the field is always blank when you reload the
page. This app is for local personal use only: it binds to `127.0.0.1` and has no
authentication of its own, so don't expose it on a network.

## Tests

```bash
pytest -v
```
