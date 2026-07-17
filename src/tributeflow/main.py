"""Orchestrator: one publish run, end to end.

Flow: read sheet -> diff vs published state -> consolidate exact duplicates ->
validate -> optional agent review -> publish clean entries to GitHub ->
update state -> email summary.

Failure model: any error before the publish step aborts the run with nothing
written (the wall is never left half-updated). The publish itself is a full
rebuild from the sheet, so re-running after any failure is always safe.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from anthropic import Anthropic

from . import agent, dedup, emailer, sheets, state, validation
from .config import Config, load_config
from .models import RunReport
from .publisher import GitHubPublisher

log = logging.getLogger("tributeflow")


def load_fixture(path: str, cfg: Config) -> list:
    """Load entries from a local JSON fixture instead of Google Sheets (demo mode)."""
    import json
    raw = json.loads(open(path).read())
    entries = []
    for wall, values in raw.items():
        entries.extend(sheets.rows_to_entries(wall, values, cfg.wall_columns(wall)))
    return entries


def run(cfg: Config, dry_run: bool = False, fixture: str | None = None) -> RunReport:
    if fixture:
        entries = load_fixture(fixture, cfg)
        log.info("loaded %d entries from fixture %s", len(entries), fixture)
    else:
        entries = sheets.fetch_entries(cfg)
        log.info("total entries in sheet: %d", len(entries))

    previous = state.load_state(cfg.state_path)
    diff = state.diff_entries(entries, previous)
    to_review = diff.new + diff.changed
    log.info("diff: %d new, %d changed, %d unchanged",
             len(diff.new), len(diff.changed), len(diff.unchanged))

    # 1. Deterministic dedup across the whole sheet: same wall + honoree +
    # donor -> keep the first row, drop the rest. Duplicates are consolidated
    # automatically (client's rule), so they're reported as FYI — only the
    # first time we see them, hence the to_review filter.
    dup_notices, duplicate_keys = dedup.find_duplicates(entries)
    review_keys = {e.key for e in to_review}
    consolidated = [n for n in dup_notices if n.entry_key in review_keys]
    log.info("dedup: %d duplicate row(s) consolidated (%d newly reported)",
             len(duplicate_keys), len(consolidated))

    # 2. Deterministic validation on new/changed entries (skip dropped duplicates)
    issues = []
    for entry in to_review:
        if entry.key not in duplicate_keys:
            issues.extend(validation.validate_entry(entry))

    # 3. Optional agent review (fuzzy dedup, wall mismatch) on entries that
    # passed validation. CASPCA runs without an API key, so this is normally
    # skipped — exact-match dedup above does not depend on it.
    failed_keys = {i.entry_key for i in issues}
    reviewable = [
        e for e in to_review if e.key not in failed_keys and e.key not in duplicate_keys
    ]
    client = None
    if cfg.anthropic_api_key or _has_ambient_credentials():
        client = Anthropic()
        try:
            issues.extend(agent.review_entries(client, cfg.model, reviewable, entries))
        except Exception:
            log.exception("agent review failed — publishing without it (validation still ran)")
    else:
        log.warning("no Anthropic credentials — skipping agent review")

    # 4. Publish everything except held-back entries and consolidated duplicates
    held_keys = {i.entry_key for i in issues}
    dropped = held_keys | duplicate_keys
    publishable = [e for e in entries if e.key not in dropped]
    report = RunReport(
        published_new=[e for e in diff.new if e.key not in dropped],
        published_changed=[e for e in diff.changed if e.key not in dropped],
        unchanged_count=len(diff.unchanged),
        issues=issues,
        consolidated=consolidated,
        dry_run=dry_run,
    )

    if dry_run:
        log.info("dry run — would publish %d entries, %d held back, %d duplicates consolidated",
                 len(publishable), len(held_keys), len(duplicate_keys))
    else:
        summary = (f"{len(report.published_new)} new, "
                   f"{len(report.published_changed)} updated tribute(s)")
        GitHubPublisher(cfg).publish(publishable, summary)
        # State records what published PLUS consolidated duplicates: a held
        # entry is re-reviewed (and re-reported) until fixed, but a duplicate
        # was handled automatically — report it once, then stay quiet unless
        # the row changes.
        state.save_state(cfg.state_path, [e for e in entries if e.key not in held_keys])

    # 5. Summary: drafted here, delivered by the Apps Script.
    # The workflow commits summary_path back to this repo; the "Publish to Wall"
    # script polls it and emails it via MailApp (no SMTP credentials needed).
    if client is not None:
        try:
            body = agent.draft_email(client, cfg.model, report)
        except Exception:
            log.exception("email drafting failed — using template fallback")
            body = agent.fallback_email(report)
    else:
        body = agent.fallback_email(report)

    date = datetime.now(timezone.utc).strftime("%b %d")
    attention = f", {len(issues)} need attention" if issues else ""
    subject = (f"Tribute wall published ({date}): "
               f"{len(report.published_new)} new{attention}")

    if dry_run:
        log.info("dry run — email body:\n%s", body)
    else:
        _write_summary(cfg.summary_path, subject, body, report)
        if cfg.smtp_host:  # optional direct-SMTP path, unused for CASPCA
            emailer.send_email(cfg, subject, body)

    return report


def _write_summary(path: str, subject: str, body: str, report: RunReport) -> None:
    """Write the run summary the Apps Script polls and emails to staff."""
    import json
    from pathlib import Path

    Path(path).write_text(json.dumps(
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "subject": subject,
            "body": body,
            "counts": {
                "new": len(report.published_new),
                "updated": len(report.published_changed),
                "unchanged": report.unchanged_count,
                "needs_attention": len(report.issues),
                "duplicates_consolidated": len(report.consolidated),
            },
        },
        indent=2, ensure_ascii=False,
    ) + "\n")
    log.info("wrote run summary to %s", path)


def _has_ambient_credentials() -> bool:
    """The anthropic SDK can also resolve an `ant auth login` profile."""
    import os
    return bool(os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def cli() -> None:
    parser = argparse.ArgumentParser(description="Publish the tribute wall from Google Sheets.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run all checks but don't commit or email.")
    parser.add_argument("--fixture", default=None,
                        help="Load entries from a local JSON file instead of Google Sheets.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config(args.config)
    try:
        report = run(cfg, dry_run=args.dry_run, fixture=args.fixture)
    except Exception:
        log.exception("run failed before publishing — the wall was not modified")
        sys.exit(1)

    print(
        f"Done: {len(report.published_new)} new, {len(report.published_changed)} updated, "
        f"{len(report.issues)} held back."
    )


if __name__ == "__main__":
    cli()
