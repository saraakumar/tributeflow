"""Deterministic duplicate consolidation.

Per the client's rule (Jessica, 2026-07-16): consolidate only entries where
BOTH the honoree (tribute name) and the donor match, on the same wall. The
first sheet row in each group is published; later copies are dropped and
reported so staff can delete the redundant rows at their leisure.

Matching is exact after normalization (case and whitespace) — never fuzzy.
Anything looser is the optional agent's job, not this module's.
"""

from __future__ import annotations

from .models import Entry, Issue


def _norm(value: str) -> str:
    return " ".join(value.split()).casefold()


def find_duplicates(entries: list[Entry]) -> tuple[list[Issue], set[str]]:
    """Group entries by (wall, honoree, donor); mark all but the first as duplicates.

    Returns the consolidation notices and the keys of the dropped entries.
    """
    kept: dict[tuple[str, str, str], Entry] = {}
    notices: list[Issue] = []
    duplicate_keys: set[str] = set()

    for entry in sorted(entries, key=lambda e: (e.wall, e.row_number)):
        group = (entry.wall, _norm(entry.tribute_name), _norm(entry.donor_name))
        original = kept.get(group)
        if original is None or not entry.tribute_name or not entry.donor_name:
            # Rows missing a name can't be called duplicates of each other —
            # they're validation's problem. Never consolidate them.
            kept.setdefault(group, entry)
            continue
        duplicate_keys.add(entry.key)
        notices.append(
            Issue(
                entry_key=entry.key,
                wall=entry.wall,
                row_number=entry.row_number,
                tribute_name=entry.tribute_name,
                problem=(
                    f"Duplicate of row {original.row_number} (same honoree and donor). "
                    f"Only row {original.row_number} was published — you can delete "
                    f"this row from the sheet."
                ),
                source="dedup",
            )
        )
    return notices, duplicate_keys
