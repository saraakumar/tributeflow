"""Deterministic checks. Images are OPTIONAL — most CASPCA entries have none.

Also converts pasted Google Drive share links into direct thumbnail URLs so
staff can paste the plain Drive link instead of hand-building one.
"""

from __future__ import annotations

import logging
import re

import requests

from .models import Entry, Issue

log = logging.getLogger(__name__)

_DRIVE_PATTERNS = [
    re.compile(r"drive\.google\.com/file/d/([\w-]+)"),
    re.compile(r"drive\.google\.com/open\?id=([\w-]+)"),
    re.compile(r"drive\.google\.com/uc\?(?:export=\w+&)?id=([\w-]+)"),
]


def drive_file_id(url: str) -> str | None:
    """Extract the file ID from any common Google Drive link format."""
    for pattern in _DRIVE_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def normalize_image_url(url: str, width: int = 400) -> str:
    """Turn a Drive share link into a thumbnail URL; pass other URLs through."""
    file_id = drive_file_id(url)
    if file_id and "thumbnail" not in url:
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{width}"
    return url


def default_url_checker(url: str) -> bool:
    """Return True if the URL responds successfully."""
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        if resp.status_code == 405:  # some hosts reject HEAD
            resp = requests.get(url, timeout=10, stream=True)
        return resp.status_code < 400
    except requests.RequestException:
        return False


def validate_entry(entry: Entry, url_checker=default_url_checker) -> list[Issue]:
    """Check one entry. A missing image is NOT an error; a broken image link is."""
    issues = []

    def issue(problem: str) -> Issue:
        return Issue(
            entry_key=entry.key,
            wall=entry.wall,
            row_number=entry.row_number,
            tribute_name=entry.tribute_name or "(no name)",
            problem=problem,
            source="validation",
        )

    if not entry.tribute_name:
        issues.append(issue("This entry is missing a tribute name."))
    if not entry.donor_name:
        issues.append(issue("This entry is missing a donor name."))

    if entry.image_url:
        entry.image_url = normalize_image_url(entry.image_url)
        if not entry.image_url.lower().startswith(("http://", "https://")):
            issues.append(issue(f"The image link doesn't look like a URL: {entry.image_url}"))
        elif not url_checker(entry.image_url):
            issues.append(
                issue(
                    f"The image link appears to be broken or not publicly viewable: "
                    f"{entry.image_url}. If it's a Google Drive file, make sure sharing is "
                    f"set to 'Anyone with the link'."
                )
            )
    return issues
