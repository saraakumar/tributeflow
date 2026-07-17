"""Publish tribute data to each wall's GitHub repository.

Replaces the old manual flow (export CSV -> VS Code -> git push): we write the
Tribute.csv each wall's site already renders, via the GitHub Contents API. The
CSV format matches the existing app.js parser exactly (naive comma split,
semicolons as multi-value separators), so the sites need no changes.
"""

from __future__ import annotations

import base64
import logging

import requests

from .config import Config
from .models import Entry
from .retry import with_retries

log = logging.getLogger(__name__)

API = "https://api.github.com"

# Fallback header if a wall doesn't configure one (matches the People wall's file)
DEFAULT_CSV_HEADER = "In Honor or Memory Of:,Tribute Name,Donor Name,Image URL"


def build_wall_payloads(entries: list[Entry], cfg: Config) -> dict[str, str]:
    """Return {wall: csv_content} for each wall, deterministic ordering."""
    payloads = {}
    for wall, wall_cfg in cfg.walls.items():
        wall_entries = [e for e in entries if e.wall == wall]
        wall_entries.sort(key=lambda e: e.row_number)
        header = wall_cfg.csv_header or DEFAULT_CSV_HEADER
        rows = [header] + [e.to_csv_row() for e in wall_entries]
        payloads[wall] = "\n".join(rows) + "\n"
    return payloads


class GitHubPublisher:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {cfg.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    @with_retries(attempts=3, retry_on=(requests.RequestException,))
    def _get_existing(self, repo: str, branch: str, path: str) -> tuple[str, str] | None:
        """Return (sha, decoded content) for a file, or None if it doesn't exist."""
        url = f"{API}/repos/{repo}/contents/{path}"
        resp = self.session.get(url, params={"ref": branch}, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data.get("content", "")).decode()
        return data["sha"], content

    @with_retries(attempts=3, retry_on=(requests.RequestException,))
    def _put_file(self, repo: str, branch: str, path: str, content: str, message: str) -> bool:
        """Create or update one file. Returns True if a commit was made."""
        existing = self._get_existing(repo, branch, path)
        body = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if existing is not None:
            sha, current = existing
            if current == content:
                log.info("%s/%s unchanged, skipping commit", repo, path)
                return False
            body["sha"] = sha
        url = f"{API}/repos/{repo}/contents/{path}"
        resp = self.session.put(url, json=body, timeout=30)
        resp.raise_for_status()
        log.info("committed %s to %s@%s", path, repo, branch)
        return True

    def publish(self, entries: list[Entry], summary: str) -> list[str]:
        """Write each wall's CSV to its repo. Returns list of files that changed."""
        payloads = build_wall_payloads(entries, self.cfg)
        changed = []
        for wall, content in payloads.items():
            wall_cfg = self.cfg.walls[wall]
            if not wall_cfg.repo:
                log.warning("wall '%s' has no repo configured — skipping", wall)
                continue
            if self._put_file(
                wall_cfg.repo, wall_cfg.branch, wall_cfg.csv_path, content,
                f"TributeFlow: {summary}",
            ):
                changed.append(f"{wall_cfg.repo}/{wall_cfg.csv_path}")
        return changed
