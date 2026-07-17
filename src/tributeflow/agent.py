"""The agentic layer: Claude reviews new/changed entries with tools.

Deterministic code (validation.py) handles hard rules. The agent handles the
judgment calls a human editor would make:
  - fuzzy duplicates ("Bella (Smith family)" vs "Bella Smith")
  - entries that look like they landed on the wrong wall (pet vs person)

It works through a real tool-use loop: Claude searches the existing entries
itself and flags problems via a tool call, so every flag is structured data,
not parsed prose. A separate call drafts the plain-English summary email.
"""

from __future__ import annotations

import json
import logging

from anthropic import Anthropic, beta_tool

from .models import Entry, Issue, RunReport

log = logging.getLogger(__name__)

REVIEW_SYSTEM = """You are the editorial reviewer for an animal shelter's memorial tribute walls
(one wall for pets, one for people). You review entries that are about to be published.

For each entry under review:
1. Use search_existing_entries to check whether it duplicates an entry that is already
   published or another entry in this batch. Exact matches (identical honoree and donor) are
   already consolidated automatically before you see the batch — focus on near-matches, where
   names differ slightly ("Bella (Smith family)" vs "Bella Smith"). Use judgment, and search
   more than once with different terms if needed. Only flag a near-duplicate when BOTH the
   honoree and the donor appear to be the same people.
2. Check the entry is on the right wall: pet names on the pets wall, human memorials on the
   people wall. Only flag a wall mismatch when the names make it reasonably clear (e.g. a
   tribute name with a title like "Dr." or a full human first-and-last name on the pets wall,
   or an obvious pet name like "Whiskers" on the people wall).

Call flag_entry for every problem you find, with a short plain-English reason a nontechnical
marketing person can act on. If an entry looks fine, do nothing for it. Do not flag entries
for style, tone, or content quality — that is the shelter's call, not yours."""


def review_entries(
    client: Anthropic,
    model: str,
    to_review: list[Entry],
    all_entries: list[Entry],
) -> list[Issue]:
    """Run the agent over new/changed entries. Returns structured flags."""
    if not to_review:
        return []

    flags: list[Issue] = []
    review_keys = {e.key for e in to_review}

    @beta_tool
    def search_existing_entries(query: str) -> str:
        """Search all tribute entries (published and pending) by name.

        Args:
            query: A name or partial name to search for, e.g. "Bella" or "Smith".
        """
        q = query.lower().strip()
        matches = [
            {
                "wall": e.wall,
                "row": e.row_number,
                "tribute_name": e.tribute_name,
                "donor_name": e.donor_name,
                "under_review": e.key in review_keys,
            }
            for e in all_entries
            if q in e.tribute_name.lower() or q in e.donor_name.lower()
        ]
        if not matches:
            return f"No entries match '{query}'."
        return json.dumps(matches[:20], ensure_ascii=False)

    @beta_tool
    def flag_entry(wall: str, row_number: int, reason: str) -> str:
        """Flag an entry so it is held back from publishing and reported to staff.

        Args:
            wall: The wall the entry is on, "pets" or "people".
            row_number: The sheet row number of the entry being flagged.
            reason: A short plain-English explanation staff can act on.
        """
        entry = next(
            (e for e in to_review if e.wall == wall and e.row_number == row_number), None
        )
        if entry is None:
            return (
                f"No entry under review at {wall} row {row_number}. Only entries in the "
                f"review batch can be flagged."
            )
        flags.append(
            Issue(
                entry_key=entry.key,
                wall=entry.wall,
                row_number=entry.row_number,
                tribute_name=entry.tribute_name,
                problem=reason,
                source="agent",
            )
        )
        return "Flagged."

    batch = [
        {
            "wall": e.wall,
            "row": e.row_number,
            "tribute_name": e.tribute_name,
            "donor_name": e.donor_name,
            "tribute_type": e.tribute_type,
            "has_image": bool(e.image_url),
        }
        for e in to_review
    ]

    runner = client.beta.messages.tool_runner(
        model=model,
        max_tokens=16000,
        system=REVIEW_SYSTEM,
        tools=[search_existing_entries, flag_entry],
        messages=[
            {
                "role": "user",
                "content": (
                    "Review these entries before they publish:\n\n"
                    + json.dumps(batch, ensure_ascii=False, indent=2)
                ),
            }
        ],
    )
    for _ in runner:
        pass

    log.info("agent review complete: %d of %d entries flagged", len(flags), len(to_review))
    return flags


EMAIL_SYSTEM = """You write the publish-summary email for an animal shelter's marketing team.
They are not technical. Write warm, brief, plain English. Structure:
1. One-sentence summary of the run.
2. What was published (new entries first, then updates), listed by tribute name and wall.
3. "Duplicates consolidated" — entries dropped automatically because another row has the same
   honoree and donor. Reassure them nothing is required; they may delete the duplicate rows.
4. "Needs your attention" — each held-back entry with its sheet row number and how to fix it
   in the Google Sheet. Reassure them it will publish automatically on the next run once fixed.
Omit any section that is empty. No markdown syntax — plain text only. Do not invent entries
or numbers that are not in the data."""


def draft_email(client: Anthropic, model: str, report: RunReport) -> str:
    """Draft the plain-English summary email from structured run results."""
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=EMAIL_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": "Run results:\n" + json.dumps(report.to_dict(), indent=2),
            }
        ],
    )
    return next(b.text for b in response.content if b.type == "text")


def fallback_email(report: RunReport) -> str:
    """Templated email used when the Claude API is unavailable — the run still reports."""
    lines = ["Tribute wall publish summary", ""]
    if report.dry_run:
        lines.append("(Dry run — nothing was actually published.)")
    lines.append(
        f"Published: {len(report.published_new)} new, {len(report.published_changed)} updated. "
        f"{report.unchanged_count} entries unchanged."
    )
    for e in report.published_new:
        lines.append(f"  NEW ({e.wall} wall): {e.tribute_name} — from {e.donor_name}")
    for e in report.published_changed:
        lines.append(f"  UPDATED ({e.wall} wall): {e.tribute_name} — from {e.donor_name}")
    if report.consolidated:
        lines.append("")
        lines.append("Duplicates consolidated automatically (no action needed):")
        for i in report.consolidated:
            lines.append(f"  Row {i.row_number} on the {i.wall} wall ({i.tribute_name}): {i.problem}")
    if report.issues:
        lines.append("")
        lines.append("Needs your attention (held back from publishing):")
        for i in report.issues:
            lines.append(f"  Row {i.row_number} on the {i.wall} wall ({i.tribute_name}): {i.problem}")
        lines.append("Fix these in the Google Sheet and they'll publish on the next run.")
    return "\n".join(lines)
