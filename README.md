# Jira -> Sheets Tracker Sync

This project compares Jira ticket status values against a Google Sheets tracker, updates the tracker, and generates run metrics/charts. It can also publish a run report to Confluence.

## What the script does

`src/main.py` runs this flow:

1. Reads Jira and Google configuration from environment variables.
2. Pulls tracker rows from Google Sheets.
3. Looks up each Jira ticket status.
4. Compares tracker status vs Jira status.
5. Updates Google Sheets status and last-checked columns.
6. Builds summary metrics and chart images.
7. Optionally publishes a Confluence report.

## Prerequisites

- Python 3.10+
- `credentials.json` (Google OAuth client credentials) in repository root
- Jira/Atlassian API token
- Jira user email

### Google Cloud setup

In Google Cloud Console:

1. Open **APIs & Services -> Credentials**
2. Create an OAuth client
3. Download the JSON file
4. Save it as `credentials.json` at repo root

## Configuration

Create a local `.env` file (or set environment variables in CI).

### Required for script execution

```bash
API_TOKEN="your_jira_api_token"
USER_EMAIL="your_email@example.com"
SPREADSHEET_ID="your_google_sheet_id"
RANGE_NAME="'Tickets'!A2:I"
CURRENT_BUILD_PAGE_ID="your_confluence_build_page_id"
```

### Optional settings

```bash
# Jira
JIRA_BASE_URL="https://ifitdev.atlassian.net"   # default shown
JIRA_REQUEST_TIMEOUT_SECONDS=15                  # default: 15

# Confluence publish (enabled only when SPACE_KEY is set)
SPACE_KEY="your_confluence_space_key"
PARENT_PAGE_ID="optional_parent_page_id"
CONFLUENCE_BASE_URL="https://ifitdev.atlassian.net"  # default: JIRA_BASE_URL
CONFLUENCE_REQUEST_TIMEOUT_SECONDS=30                 # default: 30
```

## Install and run

```bash
pip3 install -r requirements.txt
python3 src/main.py
```

On first run, Google OAuth prompts for authorization and creates `token.json`.

## Outputs

- Google Sheets updates:
  - Status column `F`
  - Last Checked column `I`
- Local charts in `images/`:
  - `*_PI_*.png` (status pie chart)
  - `*_BAR_*.png` (priority bar chart)
- Console run summary (counts, differences, execution time, links for failed tickets)

## Confluence report publishing

Publishing is attempted when `USER_EMAIL`, `API_TOKEN`, and `SPACE_KEY` are available.

- Creates a page using Confluence REST API.
- Uploads generated chart images as page attachments.
- Updates the page body to embed uploaded attachments.
- Skips publishing safely if required Confluence settings are missing.

## File overview

| File | Purpose |
|------|---------|
| `src/main.py` | Entry point; orchestrates sync, comparison, updates, metrics, and reporting. |
| `src/google_services.py` | Google OAuth + Sheets API helpers. |
| `src/status_mapping.py` | Jira status to tracker status translation map. |
| `src/charts.py` | Pie/bar chart generation and image export. |
| `src/confluence_report.py` | Confluence page creation, attachment upload, and report publishing. |