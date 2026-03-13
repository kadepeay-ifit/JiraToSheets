# About
This project syncs Jira ticket statuses to a Google Sheets bug tracker and generates a stability pie chart report from tracker data.

## Prerequisites
You need:

- A Google Cloud OAuth client credential file (`credentials.json`)
- A Jira/Atlassian API token
- A user email for Jira API authentication

### Google Cloud setup
In Google Cloud Console, go to **APIs & Services -> Credentials**, create OAuth credentials, download the JSON file, and save it as `credentials.json` in the repository root.

### Jira token setup
Create an API token in Atlassian account settings (**Security -> API tokens**), then add credentials to a local `.env` file (or GitHub secrets in CI).

Example `.env`:

```bash
API_TOKEN=your_jira_api_token
USER_EMAIL=your_email@example.com
BUILD_VERSION=Retail-2026-02
SAMPLE_SPREADSHEET_ID=your_google_sheet_id
SAMPLE_RANGE_NAME=A2:H
# Confluence publishing (optional)
SPACE_KEY=your_confluence_space_key
PARENT_PAGE_ID=optional_parent_page_id
# Optional override (defaults to JIRA_BASE_URL)
CONFLUENCE_BASE_URL=https://ifitdev.atlassian.net
# Optional timeout (seconds)
CONFLUENCE_REQUEST_TIMEOUT_SECONDS=30
# Optional
JIRA_BASE_URL=https://ifitdev.atlassian.net
JIRA_REQUEST_TIMEOUT_SECONDS=15
```

## Running the script
Use Python 3.10+.

Install dependencies:

```bash
pip3 install -r requirements.txt
```

Run:

```bash
python3 src/main.py
```

On first run, Google OAuth will prompt for account authorization and create `token.json`.

## Confluence report publishing
`src/main.py` now publishes a Confluence page automatically at the end of a run when these variables are configured: `USER_EMAIL`, `API_TOKEN`, and `SPACE_KEY`.

- The page is created via Confluence REST API.
- The generated pie chart from `images/` is uploaded as a page attachment.
- The page is updated to embed that uploaded attachment (instead of a local filesystem image path).
- If Confluence variables are not configured, publishing is skipped safely.

## File Descriptions

| File | Purpose |
|------|---------|
| `src/main.py` | Entry point. Coordinates sync, comparison, status metrics, and chart generation. |
| `src/google_services.py` | Google authentication and Sheets API read helpers. |
| `src/status_mapping.py` | Mapping layer between Jira statuses and tracker statuses. |