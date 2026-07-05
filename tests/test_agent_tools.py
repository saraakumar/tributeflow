"""Tests for the agent's tool functions and email fallback (no API calls)."""

from tributeflow.agent import fallback_email
from tributeflow.models import Entry, Issue, RunReport


def test_fallback_email_lists_published_and_issues():
    report = RunReport(
        published_new=[Entry("pets", 2, "Bella", "Smith")],
        published_changed=[],
        unchanged_count=10,
        issues=[
            Issue(
                entry_key="pets:5",
                wall="pets",
                row_number=5,
                tribute_name="Max",
                problem="This entry is missing a donor name.",
                source="validation",
            )
        ],
    )
    body = fallback_email(report)
    assert "Bella" in body
    assert "Row 5" in body
    assert "missing a donor name" in body
    assert "next run" in body


def test_fallback_email_dry_run_labeled():
    body = fallback_email(RunReport(dry_run=True))
    assert "Dry run" in body
