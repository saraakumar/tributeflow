"""Core data types shared across the pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


def sanitize_csv_field(value: str) -> str:
    """Make a field safe for the walls' naive comma-split CSV parser.

    The site's app.js splits rows on "," with no quoting, and renders ";" as
    ", " — so converting commas to semicolons keeps the display identical
    while never breaking a row.
    """
    return value.replace(",", ";").replace("\n", " ").strip()


@dataclass
class Entry:
    """One row of the tribute sheet."""

    wall: str  # "pets" or "people"
    row_number: int  # 1-based row in the sheet tab (including header offset)
    tribute_name: str
    donor_name: str
    tribute_type: str = ""  # "In honor of" or "In memory of"
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
                "tribute_type": self.tribute_type,
                "image_url": self.image_url,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_csv_row(self) -> str:
        """One row of the wall's Tribute.csv: type, tribute, donor, image."""
        return ",".join(
            sanitize_csv_field(v)
            for v in (self.tribute_type, self.tribute_name, self.donor_name, self.image_url)
        )


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
    consolidated: list[Issue] = field(default_factory=list)  # auto-merged duplicates, FYI only
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "published_new": [asdict(e) for e in self.published_new],
            "published_changed": [asdict(e) for e in self.published_changed],
            "unchanged_count": self.unchanged_count,
            "issues": [asdict(i) for i in self.issues],
            "consolidated": [asdict(i) for i in self.consolidated],
            "dry_run": self.dry_run,
        }
