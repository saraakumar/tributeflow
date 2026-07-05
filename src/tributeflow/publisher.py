"""Publish tribute data to the website's GitHub repository.

Replaces the old manual flow (export CSV -> VS Code -> git push): we write one
JSON file per wall via the GitHub Contents API. The site rebuilds from the
commit exactly as it did before.
"""

from __future__ import annotations

import base64
import json
import logging

import requests

from .config import Config
from .models import Entry
from .retry import with_retries

log = logging.getLogger(__name__)

API = "https://api.github.com"


def build_wall_payloads(entries: list[Entry], walls: list[str]) -> dict[str, str]:
    """Return {filename: file_content} for each wall, deterministic ordering."""
    payloads = {}
    for wall in walls:
        wall_entries = [e for e in entries if e.wall == wall]
        wall_entries.sort(key=lambda e: e.row_number)
        payloads[f"{wall}.json"] = (
            json.dumps([e.to_public_dict() for e in wall_entries], indent=2, ensure_ascii=False)
            + "\n"
        )
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
    def _get_existing_sha(self, path: str) -> str | None:
        url = f"{API}/repos/{self.cfg.website.repo}/contents/{path}"
        resp = self.session.get(url, params={"ref": self.cfg.website.branch}, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()["sha"]

    @with_retries(attempts=3, retry_on=(requests.RequestException,))
    def _put_file(self, path: str, content: str, message: str) -> bool:
        """Create or update one file. Returns True if a commit was made."""
        sha = self._get_existing_sha(path)
        body = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": self.cfg.website.branch,
        }
        if sha is not None:
            # Skip the commit entirely if content is unchanged
            current = self.session.get(
                f"{API}/repos/{self.cfg.website.repo}/contents/{path}",
                params={"ref": self.cfg.website.branch},
                timeout=30,
            ).json()
            existing = base64.b64decode(current.get("content", "")).decode()
            if existing == content:
                log.info("%s unchanged, skipping commit", path)
                return False
            body["sha"] = sha
        url = f"{API}/repos/{self.cfg.website.repo}/contents/{path}"
        resp = self.session.put(url, json=body, timeout=30)
        resp.raise_for_status()
        log.info("committed %s to %s@%s", path, self.cfg.website.repo, self.cfg.website.branch)
        return True

    def publish(self, entries: list[Entry], summary: str) -> list[str]:
        """Write per-wall data files. Returns list of files that changed."""
        payloads = build_wall_payloads(entries, list(self.cfg.walls.keys()))
        changed = []
        for filename, content in payloads.items():
            path = f"{self.cfg.website.data_dir}/{filename}"
            if self._put_file(path, content, f"TributeFlow: {summary}"):
                changed.append(path)
        return changed
