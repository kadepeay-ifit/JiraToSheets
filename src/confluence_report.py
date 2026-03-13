from datetime import datetime
from pathlib import Path
import os
from typing import Optional

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://ifitdev.atlassian.net").rstrip("/")
CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL", JIRA_BASE_URL).rstrip("/")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("CONFLUENCE_REQUEST_TIMEOUT_SECONDS", "30"))

# User authentication constants
API_TOKEN = os.getenv("API_TOKEN")
USER_EMAIL = os.getenv("USER_EMAIL")

# Confluence page constants
SPACE_KEY = os.getenv("SPACE_KEY")
PARENT_PAGE_ID = os.getenv("PARENT_PAGE_ID")

STATUS_ORDER = ["passed", "failed", "untestable", "in progress", "monitoring", "blocked"]


def _safe_percentage(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 2)


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{minutes}:{remaining_seconds:02d}"


def _confluence_api_url(path: str) -> str:
    return f"{CONFLUENCE_BASE_URL}/wiki/rest/api{path}"


def _build_page_title(build_version: str) -> str:
    formatted_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"Health Report: {build_version}_{formatted_datetime}"


def _build_page_body(
    *,
    build_version: str,
    different_ticket_values: int,
    difference_percentage: float,
    status_counts: dict,
    viewed_rows: int,
    execution_seconds: float,
    last_checked_value: Optional[str] = None,
    chart_filename: Optional[str] = None,
) -> str:
    status_lines = []
    for status in STATUS_ORDER:
        count = int(status_counts.get(status, 0))
        status_lines.append(
            (
                f"<li>{status.title()}: {count} - - - - "
                f"({_safe_percentage(count, viewed_rows)}%)</li>"
            )
        )
    # Include unexpected statuses too so no data is hidden.
    for status, count in status_counts.items():
        if status not in STATUS_ORDER:
            status_lines.append(
                (
                    f"<li>{status.title()}: {count} - - - - "
                    f"({_safe_percentage(int(count), viewed_rows)}%)</li>"
                )
            )

    chart_markup = ""
    if chart_filename:
        chart_markup = f"""
        <h2>Stability Chart</h2>
        <ac:image ac:alt="Pie Chart for {build_version}">
            <ri:attachment ri:filename="{chart_filename}" />
        </ac:image>
        """

    last_checked_markup = ""
    if last_checked_value:
        last_checked_markup = f"<p>Last Checked value written to Tracker: {last_checked_value}</p>"

    return f"""
        <h1>Reporting stats for build version {build_version}</h1>
        <hr />
        <p>Number of Different Ticket Values: {different_ticket_values}</p>
        <p>Difference before Updating Sheet: {round(difference_percentage, 2)}%</p>

        <p>Count of each Status:</p>
        <ul>
            {''.join(status_lines)}
        </ul>

        <p>Viewed {viewed_rows} rows on the Tracker.</p>
        {last_checked_markup}
        <p>Program execution time: {_format_duration(execution_seconds)}</p>
        {chart_markup}
    """


def _create_page(title: str, body: str) -> dict:
    payload = {
        "type": "page",
        "title": title,
        "space": {"key": SPACE_KEY},
        "body": {"storage": {"value": body, "representation": "storage"}},
    }
    if PARENT_PAGE_ID:
        payload["ancestors"] = [{"id": str(PARENT_PAGE_ID)}]

    response = requests.post(
        _confluence_api_url("/content"),
        json=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        auth=HTTPBasicAuth(USER_EMAIL, API_TOKEN),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _upload_attachment(page_id: str, image_path: Path) -> dict:
    with image_path.open("rb") as chart_file:
        response = requests.post(
            _confluence_api_url(f"/content/{page_id}/child/attachment"),
            headers={"X-Atlassian-Token": "no-check", "Accept": "application/json"},
            files={"file": (image_path.name, chart_file, "image/png")},
            auth=HTTPBasicAuth(USER_EMAIL, API_TOKEN),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    response.raise_for_status()
    return response.json()


def _update_page(page_id: str, title: str, version: int, body: str) -> dict:
    payload = {
        "id": str(page_id),
        "type": "page",
        "title": title,
        "version": {"number": version + 1},
        "body": {"storage": {"value": body, "representation": "storage"}},
    }
    response = requests.put(
        _confluence_api_url(f"/content/{page_id}"),
        json=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        auth=HTTPBasicAuth(USER_EMAIL, API_TOKEN),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def publish_report(
    *,
    build_version: str,
    different_ticket_values: int,
    difference_percentage: float,
    status_counts: dict,
    viewed_rows: int,
    execution_seconds: float,
    chart_path: Optional[Path] = None,
    last_checked_value: Optional[str] = None,
) -> Optional[str]:
    if not (USER_EMAIL and API_TOKEN and SPACE_KEY):
        print("Confluence config is incomplete (USER_EMAIL, API_TOKEN, SPACE_KEY). Skipping publish.\n")
        return None

    page_title = _build_page_title(build_version)
    initial_body = _build_page_body(
        build_version=build_version,
        different_ticket_values=different_ticket_values,
        difference_percentage=difference_percentage,
        status_counts=status_counts,
        viewed_rows=viewed_rows,
        execution_seconds=execution_seconds,
        last_checked_value=last_checked_value,
    )
    created_page = _create_page(page_title, initial_body)
    page_id = created_page["id"]
    page_version = int(created_page["version"]["number"])
    print(f"Confluence page created with ID: {page_id}\n")

    if chart_path and chart_path.exists():
        _upload_attachment(page_id, chart_path)
        body_with_chart = _build_page_body(
            build_version=build_version,
            different_ticket_values=different_ticket_values,
            difference_percentage=difference_percentage,
            status_counts=status_counts,
            viewed_rows=viewed_rows,
            execution_seconds=execution_seconds,
            last_checked_value=last_checked_value,
            chart_filename=chart_path.name,
        )
        _update_page(page_id, page_title, page_version, body_with_chart)
        print(f"Uploaded and embedded chart: {chart_path.name}\n")
    elif chart_path:
        print(f"Chart path was provided but not found: {chart_path}\n")

    return page_id