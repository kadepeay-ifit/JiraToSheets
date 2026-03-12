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

## File Descriptions

| File | Purpose |
|------|---------|
| `src/main.py` | Entry point. Coordinates sync, comparison, status metrics, and chart generation. |
| `src/google_services.py` | Google authentication and Sheets API read helpers. |
| `src/status_mapping.py` | Mapping layer between Jira statuses and tracker statuses. |