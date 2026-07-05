"""Read tribute entries from the Google Sheet via a service account."""

from __future__ import annotations

import json
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config import Config
from .models import Entry
from .retry import with_retries

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _client(cfg: Config):
    info = json.loads(cfg.google_service_account_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def rows_to_entries(wall: str, values: list[list[str]], columns: dict[str, str]) -> list[Entry]:
    """Convert a raw values grid (header row first) into Entry objects.

    Rows with no tribute name AND no donor name are treated as blank and skipped.
    """
    if not values:
        return []
    headers = [h.strip() for h in values[0]]
    index = {}
    for field_name, header in columns.items():
        if header in headers:
            index[field_name] = headers.index(header)

    entries = []
    for i, row in enumerate(values[1:], start=2):  # sheet row numbers, header = row 1
        def cell(field_name: str) -> str:
            j = index.get(field_name)
            if j is None or j >= len(row):
                return ""
            return str(row[j]).strip()

        tribute, donor = cell("tribute_name"), cell("donor_name")
        if not tribute and not donor:
            continue
        entries.append(
            Entry(
                wall=wall,
                row_number=i,
                tribute_name=tribute,
                donor_name=donor,
                message=cell("message"),
                image_url=cell("image_url"),
            )
        )
    return entries


@with_retries(attempts=3)
def fetch_entries(cfg: Config) -> list[Entry]:
    """Fetch all entries from every configured wall tab."""
    svc = _client(cfg)
    entries: list[Entry] = []
    for wall, wall_cfg in cfg.walls.items():
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.sheet_id, range=wall_cfg.tab)
            .execute()
        )
        wall_entries = rows_to_entries(wall, result.get("values", []), cfg.columns)
        log.info("fetched %d entries from tab '%s' (%s wall)", len(wall_entries), wall_cfg.tab, wall)
        entries.extend(wall_entries)
    return entries
