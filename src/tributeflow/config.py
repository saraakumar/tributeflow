"""Configuration loading: config.yaml for structure, environment for secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class WallConfig:
    tab: str
    repo: str = ""  # "owner/name" of this wall's website repo
    branch: str = "main"
    csv_path: str = "Tribute.csv"  # path of the data file inside the repo
    csv_header: str = ""  # exact header row the site's CSV uses
    columns: dict[str, str] = field(default_factory=dict)  # per-wall header overrides


@dataclass
class EmailConfig:
    sender: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass
class Config:
    sheet_id: str
    walls: dict[str, WallConfig]
    columns: dict[str, str]
    email: EmailConfig
    model: str = "claude-opus-4-8"
    state_path: str = "state/published.json"
    summary_path: str = "last_run_summary.json"  # polled by the Apps Script for the email

    # secrets, from environment only
    github_token: str = ""
    anthropic_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    google_service_account_json: str = ""

    def wall_columns(self, wall: str) -> dict[str, str]:
        """Global column mapping with this wall's overrides applied."""
        merged = dict(self.columns)
        merged.update(self.walls[wall].columns)
        return merged


REQUIRED_COLUMNS = ("tribute_name", "donor_name")


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())

    missing = [k for k in ("sheet_id", "walls", "columns") if k not in raw]
    if missing:
        raise ValueError(f"config is missing required keys: {missing}")
    for col in REQUIRED_COLUMNS:
        if col not in raw["columns"]:
            raise ValueError(f"config columns must map '{col}' to a sheet header")

    return Config(
        sheet_id=raw["sheet_id"],
        walls={name: WallConfig(**w) for name, w in raw["walls"].items()},
        columns=raw["columns"],
        email=EmailConfig(**raw.get("email", {})),
        model=raw.get("model", "claude-opus-4-8"),
        state_path=raw.get("state_path", "state/published.json"),
        summary_path=raw.get("summary_path", "last_run_summary.json"),
        github_token=os.environ.get("GITHUB_TOKEN", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT", "465")),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        google_service_account_json=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
    )
