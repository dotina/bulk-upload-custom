from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from alwayz_bulk_upload.errors import ApiError

PAGE_SIZE = 100
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.0


@dataclass
class ReferenceData:
    charger_types: dict
    connector_types: dict
    charger_statuses: dict
    ev_networks: dict


@dataclass
class SiteSummary:
    id: str
    name: str


@dataclass
class ChargerSummary:
    id: str
    serial_number: str
    site_id: str


class AlwayzApiClient:
    def __init__(self, base_url: str, token: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Content-Type"] = "application/json"

    def load_reference_data(self) -> ReferenceData:
        return ReferenceData(
            charger_types=self._name_to_id_map("/api.evhub.com/v1/charger-types"),
            connector_types=self._name_to_id_map("/api.evhub.com/v1/connector-types"),
            charger_statuses=self._name_to_id_map("/api.evhub.com/v1/charger-statuses"),
            ev_networks=self._name_to_id_map("/api.evhub.com/v1/ev-networks"),
        )

    def list_sites(self, company_id: str) -> dict:
        sites = {}
        for item in self._paginate(f"/api.evhub.com/v1/companies/{company_id}/sites"):
            sites[item["name"]] = SiteSummary(id=item["id"], name=item["name"])
        return sites

    def list_chargers(self, company_id: str) -> dict:
        chargers = {}
        for item in self._paginate(f"/api.evhub.com/v1/companies/{company_id}/chargers/all"):
            chargers[item["serialNumber"]] = ChargerSummary(
                id=item["id"], serial_number=item["serialNumber"], site_id=item["siteId"]
            )
        return chargers

    def create_site(self, company_id: str, payload: dict) -> dict:
        return self._request("POST", f"/api.evhub.com/v1/companies/{company_id}/sites", json=payload)

    def create_charger(self, company_id: str, site_id: str, payload: dict) -> dict:
        return self._request(
            "POST",
            f"/api.evhub.com/v1/companies/{company_id}/sites/{site_id}/chargers",
            json=payload,
        )

    def _name_to_id_map(self, path: str) -> dict:
        # The API exposes both an internal code ("name", e.g. LEVEL_02) and a
        # human-readable "displayName" (e.g. Level 2). Canonical inputs use the
        # human-readable form, so key on both to resolve either.
        mapping: dict = {}
        for item in self._paginate(path):
            item_id = item["id"]
            for key in (item.get("name"), item.get("displayName")):
                if key:
                    mapping[key.lower()] = item_id
        return mapping

    def _paginate(self, path: str):
        page = 0
        while True:
            data = self._request("GET", path, params={"page": page, "size": PAGE_SIZE})
            yield from data["content"]
            if data.get("last", True):
                break
            page += 1

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        last_exception = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.request(method, url, timeout=30, **kwargs)
            except requests.RequestException as exc:
                last_exception = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                raise ApiError(f"{method} {path} failed after {MAX_RETRIES} attempts: {exc}") from exc

            if response.status_code >= 500:
                last_exception = ApiError(f"{method} {path} returned {response.status_code}", response.status_code)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                raise last_exception

            if response.status_code >= 400:
                raise ApiError(
                    f"{method} {path} returned {response.status_code}: {response.text}", response.status_code
                )

            return response.json()
        raise last_exception  # pragma: no cover - loop always returns or raises
