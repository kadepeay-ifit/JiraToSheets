import os
from pathlib import Path

import requests
import status_mapping
import google_services
import confluence_report
import matplotlib.pyplot as plt
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from datetime import datetime
from tqdm import tqdm  # For progress bars
from google_services import SPREADSHEET_ID
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# load_dotenv() will load variables from a local .env file during development.
# In GitHub Actions, it will be ignored as there is no .env file,
# and the variable is already set in the environment by the workflow file.
load_dotenv()

BUILD = os.getenv("BUILD_VERSION")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://ifitdev.atlassian.net").rstrip("/")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("JIRA_REQUEST_TIMEOUT_SECONDS", "15"))
SKIP_ROW_MARKERS = {"2026-01"}
PAGE = "Tickets" # This could likely be hardcoded, but this is future-proofing
STATUS_COLUMN = "F"
LAST_CHECKED_COLUMN = "I"
STATUS_DISPLAY_ORDER = ["passed", "failed", "untestable", "in progress", "monitoring", "blocked"]
PRIORITY_DISPLAY_ORDER = ["lowest", "low", "medium", "high", "highest", "needs prioritization"]

# User authentication constants
API_TOKEN = os.getenv("API_TOKEN")
USER_EMAIL = os.getenv("USER_EMAIL")

def validate_env_vars():
     """Fail fast when required runtime configuration is missing."""
     missing = []
     if not API_TOKEN:
          missing.append("API_TOKEN")
     if not USER_EMAIL:
          missing.append("USER_EMAIL")
     if missing:
          raise RuntimeError(
               f"Missing required environment variables: {', '.join(missing)}"
          )
     print("Configuration loaded.")


def _safe_percentage(count, total):
     if total <= 0:
          return 0.0
     return round((count / total) * 100, 2)


def _format_duration(seconds):
     total_seconds = max(0, int(round(seconds)))
     minutes, remaining_seconds = divmod(total_seconds, 60)
     return f"{minutes}:{remaining_seconds:02d}"


def _iter_display_counts(counts, preferred_order):
     seen = set()
     for key in preferred_order:
          if key in counts:
               seen.add(key)
               yield key, int(counts[key])
     for key in sorted(k for k in counts if k not in seen):
          yield key, int(counts[key])


def _print_count_breakdown(title, counts, total, display_order):
     print(title)
     for label, count in _iter_display_counts(counts, display_order):
          print(
               f"  - {label.title():<20} {count:>4} ({_safe_percentage(count, total):>6.2f}%)"
          )


def _print_run_summary(
     *,
     build_version,
     difference,
     difference_percentage,
     status_counts,
     priority_counts,
     viewed_rows,
     updated_rows,
     last_checked_value,
     execution_seconds,
     pie_chart_path,
     bar_chart_path,
     failed_bugs,
     confluence_page_id,
):
     divider = "=" * 72
     print(divider)
     print("Run summary")
     print(divider)
     print(f"Build version: {build_version}")
     print(f"Rows viewed: {viewed_rows}")
     print(f"Rows updated: {updated_rows}")
     print(f"Status differences: {difference} ({difference_percentage:.2f}%)")
     print(f"Last checked written: {last_checked_value}")
     print(f"Execution time: {_format_duration(execution_seconds)}")
     print(f"Failed bugs: {len(failed_bugs)}")
     print(f"Pie chart: {pie_chart_path if pie_chart_path else 'not generated'}")
     print(f"Bar chart: {bar_chart_path if bar_chart_path else 'not generated'}")
     print(f"Confluence page: {confluence_page_id if confluence_page_id else 'not published'}")
     print("-" * 72)
     _print_count_breakdown(
          "Status breakdown (sheet values):",
          status_counts,
          viewed_rows,
          STATUS_DISPLAY_ORDER,
     )
     print("-" * 72)
     _print_count_breakdown(
          "Priority breakdown:",
          priority_counts,
          viewed_rows,
          PRIORITY_DISPLAY_ORDER,
     )
     if failed_bugs:
          print("-" * 72)
          print("Failed bug links:")
          for failed_bug in failed_bugs:
               print(f" - {failed_bug['ticket']}: {failed_bug['url']}")
     print(divider)

def get_failed_bug_links(ticket_rows):
     failed_bug_links = {}
     for ticket_data in ticket_rows:
          ticket_name = ticket_data.get("Ticket Name", "").strip()
          status = ticket_data.get("Sheet Status", "").strip().lower()
          if not ticket_name or status != "failed":
               continue
          failed_bug_links[ticket_name] = f"{JIRA_BASE_URL}/browse/{ticket_name}"

     return [
          {"ticket": ticket_name, "url": failed_bug_links[ticket_name]}
          for ticket_name in sorted(failed_bug_links)
     ]

def main():
     start = datetime.now() # Start the timer
     last_checked_value = start.strftime("%Y-%m-%d") # Date only for this value

     validate_env_vars()

     # Get Credentials
     creds = google_services.get_credential_data()

     # Get a set of values from the Tracker
     values = google_services.get_sheet_data(creds)
     if not values:
          print("No tracker values were returned. Exiting.\n")
          return
     
     # Create row-aware ticket payloads with both Sheets and Jira status values.
     ticket_rows = create_dict(values)
     if not ticket_rows:
          print("No ticket rows were processed. Exiting.\n")
          return

     # Print percentage difference between Sheets and Jira
     difference = calculate_difference(ticket_rows)
     
     # Update Sheets
     num_updated_rows = update_sheet_data(ticket_rows, creds, last_checked_value)

     # Report stats from tracker-aligned values.
     status_counts = status_frequency(ticket_rows)
     pi_chart_path = make_pie_chart(status_counts)
     difference_percentage = _safe_percentage(difference, len(ticket_rows))

     priority_counts = priority_frequency(ticket_rows)
     bar_chart_path = make_bar_graph(priority_counts)
     failed_bug_links = get_failed_bug_links(ticket_rows)

     # Report time taken to execute script
     end = datetime.now()
     execution_seconds = (end - start).total_seconds()

     # Publish report to Confluence when configured.
     confluence_page_id = confluence_report.publish_report(
          build_version=BUILD or "unknown-build",
          different_ticket_values=difference,
          difference_percentage=difference_percentage,
          status_counts=status_counts,
          priority_counts=priority_counts,
          viewed_rows=num_updated_rows,
          execution_seconds=execution_seconds,
          pi_chart_path=pi_chart_path,
          bar_chart_path=bar_chart_path,
          last_checked_value=last_checked_value,
          failed_bug_links=failed_bug_links,
     )

     _print_run_summary(
          build_version=BUILD or "unknown-build",
          difference=difference,
          difference_percentage=difference_percentage,
          status_counts=status_counts,
          priority_counts=priority_counts,
          viewed_rows=len(ticket_rows),
          updated_rows=num_updated_rows,
          last_checked_value=last_checked_value,
          execution_seconds=execution_seconds,
          pie_chart_path=pi_chart_path,
          bar_chart_path=bar_chart_path,
          failed_bugs=failed_bug_links,
          confluence_page_id=confluence_page_id,
     )

def update_sheet_data(ticket_rows, creds, last_checked_value):
    """
    Update Google Sheets with Jira ticket status data.
    This function takes row-aware ticket data and Google Sheets API credentials,
    then updates the status column (F) and Last Checked column (I) on each
    source row with formatted Jira status values and a run timestamp.
    Args:
         ticket_rows (list[dict]): Row-aware ticket records where each row contains
              "Row Number" and "Jira Status" keys.
         creds: Google API credentials object for authenticating with the Sheets API.
         last_checked_value (str): Timestamp string written to each tracker row in
              the Last Checked column.
    Returns:
         int: Number of tracker rows updated.
    Raises:
         HttpError: If an error occurs while communicating with the Google Sheets API.
    Side Effects:
         - Prints "Sheet updated successfully.\n" on successful completion.
         - Prints error message if HttpError occurs during sheet update.
         - Displays progress bar using tqdm while processing tickets.
    Notes:
         - Status values are formatted as follows:
              - "PASSED" and "FAILED" are converted to uppercase
              - Other non-None statuses are converted to title case
              - None/null statuses are replaced with "In Progress"
         - Updates are applied to columns F (status) and I (Last Checked)
           using explicit row ranges (e.g., F217, I217).
         - SAMPLE_SPREADSHEET_ID must be defined in the module scope
    """

    try:
         service = build("sheets", "v4", credentials=creds)
         updates = []
         normalized_status_updates = []
         updated_rows = 0
         for ticket_data in tqdm(ticket_rows, desc="Update sheet", leave=False, unit="row"):
              row_number = ticket_data.get("Row Number")
              if not row_number:
                   continue

              jira_status = ticket_data.get("Jira Status")
              normalized_tracker_status = jira_status.lower() if jira_status else "in progress"
              sheet_display_status = normalized_tracker_status.title()
              if normalized_tracker_status in {"passed", "failed"}:
                   sheet_display_status = normalized_tracker_status.upper()

              updates.append({"range": f"'{PAGE}'!{STATUS_COLUMN}{row_number}", "values": [[sheet_display_status]]})
              updates.append({"range": f"'{PAGE}'!{LAST_CHECKED_COLUMN}{row_number}", "values": [[last_checked_value]]})
              normalized_status_updates.append((ticket_data, normalized_tracker_status))
              updated_rows += 1

         if not updates:
              print("No row updates generated.")
              return 0

         # Update both Status and Last Checked columns together.
         body = {
              "valueInputOption": "USER_ENTERED",
              "data": updates,
         }
         service.spreadsheets().values().batchUpdate(
              spreadsheetId=SPREADSHEET_ID,
              body=body
         ).execute()

         for ticket_data, normalized_tracker_status in normalized_status_updates:
              ticket_data["Sheet Status"] = normalized_tracker_status

         return updated_rows  # Return rows changed

    except HttpError as err:
         print(f"Error updating sheet: {err}")
         return 0

# Calculate the difference between ticket values on the Tracker and in Jira
def calculate_difference(ticket_rows):
     """
     Calculate the percentage of tickets with mismatched statuses between Sheet and Jira.
     Args:
         ticket_rows (list[dict]): Row-aware ticket records containing
              "Sheet Status" and "Jira Status" keys.
     Returns:
          int: Number of ticket rows with differing sheet and Jira statuses.
     """

     difference = 0
     for ticket_data in tqdm(ticket_rows, desc="Compare statuses", leave=False, unit="row"):
          sheet = ticket_data["Sheet Status"].lower() # Just to REALLY make sure
          jira = ticket_data["Jira Status"].lower()
          # print(f"Sheet: {sheet}, Jira: {jira}\n")
          if(sheet != jira):
               difference += 1

     return difference

# Create a dictionary of ticket names with the status of google sheets and jira as the values
def create_dict(values): 
     """
     Create row-aware ticket records with status information from both Sheets and Jira.
     
     Args:
         values (list): A list of rows where each row contains ticket information.
                          Expected format: row[0] = ticket_name, row[5] = sheet_status
     
     Returns:
         list[dict]: Row-aware ticket records. Each item includes:
               - "Row Number": Sheet row number (starting at 2)
               - "Ticket Name": Jira ticket identifier from column A
               - "Sheet Status": The status from the sheet (lowercase)
               - "Jira Status": The translated Jira status (lowercase)
     
     Note:
          - Uses tqdm to display progress bar during dictionary creation
          - Requires check_jira_ticket_status() function and status_mapping.MAP for translations
          - Handles missing or empty status values gracefully with a default value
          - Skips rows where columns A-C contain date objects
     """

     ticket_rows = []
     unknown_statuses = set()
     fallback_count = 0
     fallback_samples = []
     for row_number, row in enumerate(tqdm(values, desc="Fetch Jira statuses", leave=False, unit="row"), start=2):
          if not row:
               continue
          ticket_name = row[0].strip() if row[0] else ""
          if not ticket_name or ticket_name in SKIP_ROW_MARKERS:
               continue

          sheet_status = row[5].strip().lower() if len(row) > 5 and row[5] else "in progress"

          priority = row[2].strip().lower() if len(row) > 2 and row[2] else "needs prioritization"

          # Translate ticket types between Jira and Sheets.
          try:
               jira_status = check_jira_ticket_status(ticket_name)
               if jira_status not in status_mapping.MAP:
                    unknown_statuses.add(jira_status)
               translated_jira_status = status_mapping.MAP.get(jira_status, "in progress")
          except (requests.exceptions.RequestException, ValueError) as exc:
               # Keep row alignment stable even when Jira lookups fail.
               fallback_count += 1
               if len(fallback_samples) < 5:
                    fallback_samples.append(f"{ticket_name}: {exc}")
               translated_jira_status = sheet_status

          ticket_rows.append({
               "Row Number": row_number,
               "Ticket Name": ticket_name,
               "Priority": priority,
               "Sheet Status": sheet_status,
               "Jira Status": translated_jira_status
          })

     if fallback_count:
          print(
               f"Used sheet status fallback for {fallback_count} Jira lookup(s). "
               f"Examples: {'; '.join(fallback_samples)}"
          )
     if unknown_statuses:
          print(
               "Encountered Jira statuses missing from status_mapping.MAP: "
               f"{', '.join(sorted(unknown_statuses))}"
          )
     return ticket_rows

# Check status on Jira side
def check_jira_ticket_status(ticket_id):
     """
     Retrieve the current status of a Jira ticket.
     
     Makes a REST API call to the Atlassian Jira instance to fetch ticket details
     and extracts the status field from the response.
     
     Args:
          ticket_id (str): The unique identifier of the Jira ticket.
     
     Returns:
          str: The name of the ticket's current status (e.g., "To Do", "In Progress", "Done").
     
     Raises:
          requests.exceptions.RequestException: If the HTTP request fails.
          json.JSONDecodeError: If the response cannot be parsed as JSON.
          KeyError: If the expected status field is not found in the response.
     """

     url = f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_id}"
     headers = {
          "Accept": "application/json",
          "Content-Type": "application/json"
     }
     auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
     response = requests.get(url, headers=headers, auth=auth, timeout=REQUEST_TIMEOUT_SECONDS)
     response.raise_for_status()
     ticket_data = response.json()

     try:
          # Most Recent status name
          return ticket_data["fields"]["status"]["name"]
     except KeyError as exc:
          raise ValueError(
               f"Unexpected Jira response shape for ticket '{ticket_id}'"
          ) from exc

# Count Frequency of each status type
def status_frequency(ticket_rows):
     """
     Count the frequency of each status in the ticket dictionary.
     This function iterates through a dictionary of tickets and tallies the number
     of occurrences for each status type. It tracks six status categories: passed,
     failed, untestable, in progress, monitoring, and blocked.
     Args:
         ticket_rows (list[dict]): Row-aware ticket records containing a
              "Sheet Status" key.
     Returns:
          dict: A dictionary with status types as keys and their frequency counts as values.
                 Keys: 'passed', 'failed', 'untestable', 'in progress', 'monitoring', 'blocked'
     Raises:
          KeyError: If a ticket's "Sheet Status" value does not match any of the predefined
                     status categories.
     Note:
          InvalidRow exceptions (missing data) are caught and logged but do not halt execution.
     """   
        
     # Keep track of status counts
     status_counts = {
          'passed': 0,
          'failed': 0,
          'untestable': 0,
          'in progress': 0,
          'monitoring': 0,
          'blocked': 0,
     }

     for ticket_data in tqdm(ticket_rows, desc="Count statuses", leave=False, unit="row"):
          status = ticket_data.get("Sheet Status", "in progress")
          if status not in status_counts:
               status_counts[status] = 0
          status_counts[status] += 1

     return status_counts

def priority_frequency(ticket_rows):
     priority_counts = {
          'lowest': 0,
          'low': 0,
          'medium': 0,
          'high': 0,
          'highest': 0,
     }

     for ticket_data in tqdm(ticket_rows, desc="Count priorities", leave=False, unit="row"):
          priority = ticket_data.get("Priority", "needs prioritization")
          if priority not in priority_counts:
               priority_counts[priority] = 0
          priority_counts[priority] += 1

     return priority_counts

# Create and save a pie chart based off of the stability of the sheet
def make_pie_chart(status_counts):
     """
     Create and save a pie chart visualization of status counts.
     Args:
          status_counts (dict): A dictionary with status names as keys and their counts as values.
     Returns:
          pathlib.Path | None: Path to the saved chart image if created, else None.
     Description:
          Filters out statuses with zero counts, creates a pie chart with the remaining statuses,
          and saves it as an image file with a timestamp. The chart includes percentage labels
          and is rotated for better readability. Each status is mapped to a specific color.
     Side Effects:
          - Displays a pie chart using matplotlib
          - Saves the figure to the 'images/' directory with format: {BUILD}_{timestamp}.png
          - Prints a message confirming the file save location
     """

     # Map statuses to their corresponding colors
     color_mapping = {
          'passed': 'springgreen',
          'failed': 'indianred',
          'untestable': 'skyblue',
          'in progress': 'yellow',
          'monitoring': 'mediumorchid',
          'blocked': 'orange',
          '': 'gray' # Just in case there is any blank values
     }
     
     filtered_counts = {}
     colors = []
     for key, val in status_counts.items():
          if val > 0:
               filtered_counts[key] = val
               colors.append(color_mapping.get(key, "gray"))

     if not filtered_counts:
          print("No status counts available to chart.")
          return None

     plt.figure(figsize=(8, 8))
     
     plt.pie(filtered_counts.values(), labels=filtered_counts.keys(), autopct='%1.1f%%', startangle=45, rotatelabels=True, colors=colors) 
     plt.title(f"Current Health of {BUILD}")

     # Save the pie chart with datetime in ISO format
     current_datetime = datetime.now()
     formatted_datetime = current_datetime.strftime("%Y-%m-%d_%H-%M-%S")
     fig_name = f"{BUILD}_PI_{formatted_datetime}.png"
     output_dir = Path("images")
     output_dir.mkdir(parents=True, exist_ok=True)
     output_path = output_dir / fig_name
     plt.savefig(output_path)
     plt.close()

     # print(f"Saved pie chart: {output_path}")
     return output_path


def make_bar_graph(priority_counts):
     
     # Map priorities to a corresponding color
     color_mapping = {
          'lowest': 'skyblue',
          'low': 'lightblue',
          'medium': 'yellow',
          'high': 'orange',
          'highest': 'red',
     }

     filtered_counts = {}
     colors = []
     for key, val in priority_counts.items():
          if val > 0:
               filtered_counts[key] = val
               colors.append(color_mapping.get(key, "gray"))

     if not filtered_counts:
          print("No priority counts available to graph.")
          return None
     
     plt.figure(figsize=(8, 8))

     plt.bar(filtered_counts.keys(), filtered_counts.values(), color=colors)
     plt.title(f"Priority Health of {BUILD}")

     # Save the bar graph with datetime in ISO format
     current_datetime = datetime.now()
     formatted_datetime = current_datetime.strftime("%Y-%m-%d_%H-%M-%S")
     fig_name = f"{BUILD}_BAR_{formatted_datetime}.png"
     output_dir = Path("images")
     output_dir.mkdir(parents=True, exist_ok=True)
     output_path = output_dir / fig_name
     plt.savefig(output_path)
     plt.close()

     # print(f"Saved bar chart: {output_path}")
     return output_path

if __name__ == "__main__":
     main()
