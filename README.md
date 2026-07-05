# TributeFlow

[![CI](https://github.com/saraakumar/tributeflow/actions/workflows/ci.yml/badge.svg)](https://github.com/saraakumar/tributeflow/actions/workflows/ci.yml)

**Try it in 30 seconds, no credentials needed:**

```sh
pip install -e . && tributeflow --config examples/demo-config.yaml \
  --fixture examples/sample_sheet.json --dry-run --verbose
```

This runs the full pipeline on sample data: you'll see validation hold back a
row with a missing donor name, a pasted Google Drive link get converted to a
thumbnail URL (and flagged as broken, since it's fake), and the summary email
that would have been sent.

Agentic one-click publishing for the CASPCA tribute walls. Staff edit a Google
Sheet and click **Publish to Wall**; TributeFlow validates every entry, uses a
Claude agent to catch duplicates and wall mix-ups, commits the data to the
website's GitHub repo, and emails the team a plain-English summary. No CSV
exports, no VS Code, no git.

## Architecture

```
Google Sheet ──"Publish" menu (Apps Script)──▶ repository_dispatch
                                                     │
                                        GitHub Action (publish.yml)
                                                     │
        ┌───────────── tributeflow (Python) ─────────┴──────────────┐
        │ 1. sheets.py      read both wall tabs                     │
        │ 2. state.py       diff against last published state       │
        │ 3. validation.py  required fields, image links (optional),│
        │                   Drive link → thumbnail conversion       │
        │ 4. agent.py       Claude tool-use loop: fuzzy duplicates, │
        │                   pet/people wall check                   │
        │ 5. publisher.py   commit pets.json / people.json to the   │
        │                   website repo (site rebuilds as before)  │
        │ 6. agent.py       Claude drafts the plain-English email   │
        │ 7. emailer.py     send summary via SMTP                   │
        └────────────────────────────────────────────────────────────┘
```

Design properties:

- **Idempotent** — every publish is a full rebuild from the sheet; clicking
  twice, or re-running after a failure, is always safe.
- **Fail closed** — entries with problems are held back (never auto-published)
  and reported with a fix-it explanation; everything else still publishes.
- **Degrades gracefully** — if the Claude API is unavailable, deterministic
  validation still runs and a templated email is sent instead of failing.
- **Images are optional** — most entries have none; only *broken* image links
  are flagged. Pasted Google Drive share links are converted to thumbnail
  URLs automatically.

## Setup

1. **Google service account**: create one in Google Cloud Console, enable the
   Sheets API, share the tribute sheet with the service account's email
   (viewer). Put the JSON key in the `GOOGLE_SERVICE_ACCOUNT_JSON` secret.
2. **GitHub token**: fine-grained PAT with `Contents: read/write` on the
   website repo → `WEBSITE_REPO_TOKEN` secret. A second PAT scoped to *this*
   repo goes in the Apps Script properties for the button.
3. **Anthropic API key** → `ANTHROPIC_API_KEY` secret.
4. **SMTP**: e.g. Gmail app password → `SMTP_*` secrets.
5. Copy `config.example.yaml` to `config.yaml`, fill in the sheet ID, tab
   names, column headers, and website repo, and commit it.
6. Install the sheet button: see `apps-script/PublishButton.gs`.

## Local development

```sh
pip install -e ".[dev]"
pytest                      # unit tests, no network or API key needed
cp .env.example .env        # fill in secrets
tributeflow --config config.yaml --dry-run   # full run, commits/emails nothing
```

## Runbook

| Symptom | Likely cause | Fix |
|---|---|---|
| Button says "Something went wrong" | Apps Script token expired/revoked | Regenerate the PAT, update Script Properties |
| Action fails at "Publish" step | Sheet/service-account or website-repo token issue | Check Action logs; re-share sheet or rotate `WEBSITE_REPO_TOKEN` |
| Email says entry held back but it looks fine | Agent false positive (e.g. dedup) | Edit the row slightly (touch any cell) and re-publish; if it persists, review `agent.py` system prompt |
| No email arrives | SMTP secret wrong or recipients empty | The run still publishes; check Action logs for the email warning |
| Wall shows stale data | Site rebuild, not TributeFlow | Confirm the commit landed in the website repo, then check the site's own deploy |

State lives in `state/published.json` (committed back by the Action after each
run). Deleting it is safe: the next run re-reports everything as "new" but
publishes identical data.

## Agent evals

The judgment calls the agent makes (fuzzy duplicates, pet/people wall checks)
are measured, not assumed. `evals/golden.json` holds labeled cases — including
adversarial ones like two different pets named Bella (must NOT flag) and a cat
named Oliver whose message reveals it's on the wrong wall (must flag).

```sh
export ANTHROPIC_API_KEY=sk-ant-...
tributeflow-eval           # runs every case, prints precision/recall/F1
```

Results land in `evals/results.json`. The `eval.yml` workflow re-runs the
suite on any PR that touches `agent.py` or the dataset, so prompt changes
can't silently regress dedup quality. The scorer itself is unit-tested
offline (`tests/test_evals.py`).

## Tests & CI

`ci.yml` runs `ruff` + `pytest` on every push/PR. Tests cover sheet parsing,
validation rules (including image-optional behavior and Drive-link
conversion), state diffing, publish payload generation, and the agent's
fallback email — all without network access.
