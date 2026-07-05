"""Orchestrator: one publish run, end to end.

Flow: read sheet -> diff vs published state -> validate -> agent review ->
publish clean entries to GitHub -> update state -> email summary.

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

from . import agent, emailer, sheets, state, validation
from .config import Config, load_config
from .models import RunReport
from .publisher import GitHubPublisher

log = logging.getLogger("tributeflow")


def run(cfg: Config, dry_run: bool = False) -> RunReport:
    entries = sheets.fetch_entries(cfg)
    log.info("total entries in sheet: %d", len(entries))

    previous = state.load_state(cfg.state_path)
    diff = state.diff_entries(entries, previous)
    to_review = diff.new + diff.changed
    log.info("diff: %d new, %d changed, %d unchanged",
             len(diff.new), len(diff.changed), len(diff.unchanged))

    # 1. Deterministic validation on new/changed entries
    issues = []
    for entry in to_review:
        issues.extend(validation.validate_entry(entry))

    # 2. Agent review (dedup, wall mismatch) on entries that passed validation
    failed_keys = {i.entry_key for i in issues}
    reviewable = [e for e in to_review if e.key not in failed_keys]
    client = None
    if cfg.anthropic_api_key or _has_ambient_credentials():
        client = Anthropic()
        try:
            issues.extend(agent.review_entries(client, cfg.model, reviewable, entries))
        except Exception:
            log.exception("agent review failed — publishing without it (validation still ran)")
    else:
        log.warning("no Anthropic credentials — skipping agent review")

    # 3. Publish everything except held-back entries
    held_keys = {i.entry_key for i in issues}
    publishable = [e for e in entries if e.key not in held_keys]
    report = RunReport(
        published_new=[e for e in diff.new if e.key not in held_keys],
        published_changed=[e for e in diff.changed if e.key not in held_keys],
        unchanged_count=len(diff.unchanged),
        issues=issues,
        dry_run=dry_run,
    )

    if dry_run:
        log.info("dry run — would publish %d entries, %d held back",
                 len(publishable), len(held_keys))
    else:
        summary = (f"{len(report.published_new)} new, "
                   f"{len(report.published_changed)} updated tribute(s)")
        GitHubPublisher(cfg).publish(publishable, summary)
        # State records only what actually published, so held entries are
        # re-reviewed (and re-reported) until fixed.
        state.save_state(cfg.state_path, [e for e in entries if e.key not in held_keys])

    # 4. Email summary
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
    if not dry_run:
        emailer.send_email(cfg, subject, body)
    else:
        log.info("dry run — email body:\n%s", body)

    return report


def _has_ambient_credentials() -> bool:
    """The anthropic SDK can also resolve an `ant auth login` profile."""
    import os
    return bool(os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def cli() -> None:
    parser = argparse.ArgumentParser(description="Publish the tribute wall from Google Sheets.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run all checks but don't commit or email.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config(args.config)
    try:
        report = run(cfg, dry_run=args.dry_run)
    except Exception:
        log.exception("run failed before publishing — the wall was not modified")
        sys.exit(1)

    print(
        f"Done: {len(report.published_new)} new, {len(report.published_changed)} updated, "
        f"{len(report.issues)} held back."
    )


if __name__ == "__main__":
    cli()
