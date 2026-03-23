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
PRIORITY_ORDER = ["lowest", "low", "medium", "high", "highest"]


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
    return f"{build_version} Updated On {formatted_datetime}"


def _ordered_counts(counts: dict, preferred_order: list[str]) -> list[tuple[str, int]]:
    ordered = []
    seen = set()
    for key in preferred_order:
        if key in counts:
            seen.add(key)
            ordered.append((key, int(counts[key])))
    for key in sorted(k for k in counts if k not in seen):
        ordered.append((key, int(counts[key])))
    return ordered


def _build_counts_table(
    *,
    heading: str,
    counts: dict,
    preferred_order: list[str],
    total: int,
) -> str:
    rows = []
    for label, count in _ordered_counts(counts, preferred_order):
        rows.append(
            (
                "<tr>"
                f"<td>{label.title()}</td>"
                f"<td>{count}</td>"
                f"<td>{_safe_percentage(count, total):.2f}%</td>"
                "</tr>"
            )
        )

    return (
        f"<h2>{heading}</h2>"
        "<table>"
        "<tbody>"
        "<tr><th>Value</th><th>Count</th><th>% of Rows</th></tr>"
        f"{''.join(rows)}"
        "</tbody>"
        "</table>"
    )


def _build_attachment_markup(heading: str, filename: str, alt_text: str) -> str:
    return (
        f"<h2>{heading}</h2>"
        f'<ac:image ac:alt="{alt_text}">'
        f'<ri:attachment ri:filename="{filename}" />'
        "</ac:image>"
    )


def _build_page_body(
    *,
    build_version: str,
    different_ticket_values: int,
    difference_percentage: float,
    status_counts: dict,
    priority_counts: dict,
    viewed_rows: int,
    execution_seconds: float,
    last_checked_value: Optional[str] = None,
    pie_chart_filename: Optional[str] = None,
    bar_chart_filename: Optional[str] = None,
) -> str:
    summary_rows = [
        ("Build version", build_version),
        ("Rows viewed", str(viewed_rows)),
        ("Different ticket values", str(different_ticket_values)),
        ("Difference before update", f"{round(difference_percentage, 2):.2f}%"),
        ("Execution time", _format_duration(execution_seconds)),
    ]
    if last_checked_value:
        summary_rows.append(("Last checked written", last_checked_value))

    summary_markup = "".join(
        (
            "<tr>"
            f"<td>{label}</td>"
            f"<td>{value}</td>"
            "</tr>"
        )
        for label, value in summary_rows
    )

    status_table_markup = _build_counts_table(
        heading="Status breakdown",
        counts=status_counts,
        preferred_order=STATUS_ORDER,
        total=viewed_rows,
    )
    priority_table_markup = _build_counts_table(
        heading="Priority breakdown",
        counts=priority_counts,
        preferred_order=PRIORITY_ORDER,
        total=viewed_rows,
    )

    chart_sections = []
    if pie_chart_filename:
        chart_sections.append(
            _build_attachment_markup(
                "Stability chart",
                pie_chart_filename,
                f"Pie chart for {build_version}",
            )
        )
    if bar_chart_filename:
        chart_sections.append(
            _build_attachment_markup(
                "Priority chart",
                bar_chart_filename,
                f"Bar chart for {build_version}",
            )
        )

    return (
        f"<h1>Build report: {build_version}</h1>"
        "<h2>Run summary</h2>"
        "<table>"
        "<tbody>"
        "<tr><th>Metric</th><th>Value</th></tr>"
        f"{summary_markup}"
        "</tbody>"
        "</table>"
        f"{status_table_markup}"
        f"{priority_table_markup}"
        f"{''.join(chart_sections)}"
    )


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
    priority_counts: dict,
    viewed_rows: int,
    execution_seconds: float,
    pi_chart_path: Optional[Path] = None,
    bar_chart_path: Optional[Path] = None,
    last_checked_value: Optional[str] = None,
) -> Optional[str]:
    if not (USER_EMAIL and API_TOKEN and SPACE_KEY):
        print("Confluence publish skipped: missing USER_EMAIL, API_TOKEN, or SPACE_KEY.")
        return None

    page_title = _build_page_title(build_version)
    initial_body = _build_page_body(
        build_version=build_version,
        different_ticket_values=different_ticket_values,
        difference_percentage=difference_percentage,
        status_counts=status_counts,
        priority_counts=priority_counts,
        viewed_rows=viewed_rows,
        execution_seconds=execution_seconds,
        last_checked_value=last_checked_value,
    )
    created_page = _create_page(page_title, initial_body)
    page_id = created_page["id"]
    page_version = int(created_page["version"]["number"])
    print(f"Confluence page created: {page_id}")

    pie_chart_filename = None
    if pi_chart_path:
        if pi_chart_path.exists():
            _upload_attachment(page_id, pi_chart_path)
            pie_chart_filename = pi_chart_path.name
        else:
            print(f"Pie chart path not found: {pi_chart_path}")

    bar_chart_filename = None
    if bar_chart_path:
        if bar_chart_path.exists():
            _upload_attachment(page_id, bar_chart_path)
            bar_chart_filename = bar_chart_path.name
        else:
            print(f"Bar chart path not found: {bar_chart_path}")

    if pie_chart_filename or bar_chart_filename:
        body_with_charts = _build_page_body(
            build_version=build_version,
            different_ticket_values=different_ticket_values,
            difference_percentage=difference_percentage,
            status_counts=status_counts,
            priority_counts=priority_counts,
            viewed_rows=viewed_rows,
            execution_seconds=execution_seconds,
            last_checked_value=last_checked_value,
            pie_chart_filename=pie_chart_filename,
            bar_chart_filename=bar_chart_filename,
        )
        _update_page(page_id, page_title, page_version, body_with_charts)
        chart_names = [name for name in [pie_chart_filename, bar_chart_filename] if name]
        print(f"Confluence attachments uploaded: {', '.join(chart_names)}")

    return page_id