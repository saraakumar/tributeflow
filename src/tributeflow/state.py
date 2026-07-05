"""Track what has already been published so each run knows what's new or changed.

State is a JSON map of entry key -> content hash, stored in this repo. The
publish itself always regenerates the full data files from the sheet, so state
only drives reporting and agent review — a stale or lost state file can never
corrupt the wall, it just makes the next email over-report "new" entries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .models import Entry

log = logging.getLogger(__name__)


@dataclass
class Diff:
    new: list[Entry] = field(default_factory=list)
    changed: list[Entry] = field(default_factory=list)
    unchanged: list[Entry] = field(default_factory=list)


def load_state(path: str | Path) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def save_state(path: str | Path, entries: list[Entry]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    state = {e.key: e.content_hash() for e in entries}
    p.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def diff_entries(entries: list[Entry], state: dict[str, str]) -> Diff:
    diff = Diff()
    for entry in entries:
        previous = state.get(entry.key)
        if previous is None:
            diff.new.append(entry)
        elif previous != entry.content_hash():
            diff.changed.append(entry)
        else:
            diff.unchanged.append(entry)
    return diff
