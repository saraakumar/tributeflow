"""Core data types shared across the pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass
class Entry:
    """One row of the tribute sheet."""

    wall: str  # "pets" or "people"
    row_number: int  # 1-based row in the sheet tab (including header offset)
    tribute_name: str
    donor_name: str
    message: str = ""
    image_url: str = ""

    @property
    def key(self) -> str:
        return f"{self.wall}:{self.row_number}"

    def content_hash(self) -> str:
        payload = json.dumps(
            {
                "wall": self.wall,
                "tribute_name": self.tribute_name,
                "donor_name": self.donor_name,
                "message": self.message,
                "image_url": self.image_url,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_public_dict(self) -> dict:
        """Shape written to the website data files."""
        d = {
            "tribute_name": self.tribute_name,
            "donor_name": self.donor_name,
        }
        if self.message:
            d["message"] = self.message
        if self.image_url:
            d["image_url"] = self.image_url
        return d


@dataclass
class Issue:
    """A reason an entry was held back from publishing."""

    entry_key: str
    wall: str
    row_number: int
    tribute_name: str
    problem: str
    source: str  # "validation" or "agent"


@dataclass
class RunReport:
    """Everything the email summary needs about one publish run."""

    published_new: list[Entry] = field(default_factory=list)
    published_changed: list[Entry] = field(default_factory=list)
    unchanged_count: int = 0
    issues: list[Issue] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "published_new": [asdict(e) for e in self.published_new],
            "published_changed": [asdict(e) for e in self.published_changed],
            "unchanged_count": self.unchanged_count,
            "issues": [asdict(i) for i in self.issues],
            "dry_run": self.dry_run,
        }
