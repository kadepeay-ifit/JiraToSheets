import os

import requests
import status_mapping
import google_services
import confluence_report
import charts
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from datetime import datetime
from tqdm import tqdm  # For progress bars
from google_services import SPREADSHEET_ID
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup

# load_dotenv() will load variables from a local .env file during development.
# In GitHub Actions, it will be ignored as there is no .env file,
# and the variable is already set in the environment by the workflow file.
load_dotenv()

# BUILD = os.getenv("BUILD_VERSION")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://ifitdev.atlassian.net").rstrip("/")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("JIRA_REQUEST_TIMEOUT_SECONDS", "15"))
CURRENT_BUILD_PAGE_ID = os.getenv("CURRENT_BUILD_PAGE_ID")
# Sometimes the trackers have non-ticket rows. Use this to ignore them
SKIP_ROW_MARKERS = {"2026-01", "2026-02"}
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
     new_tickets,
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
     print(f"New tickets added: {len(new_tickets)}")
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
     if new_tickets:
          print("-" * 72)
          print("New ticket links:")
          for new_ticket in new_tickets:
               print(f" - {new_ticket['ticket']}: {new_ticket['url']}")
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

     BUILD, build_page_tickets = get_build_page_tickets()

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
     
     # TODO: Add new tickets to Tracker
     new_ticket_links = add_new_tickets(ticket_rows, build_page_tickets, creds)

     # Update Sheets
     num_updated_rows = update_sheet_data(ticket_rows, creds, last_checked_value)

     # Report stats from tracker-aligned values.
     status_counts = status_frequency(ticket_rows)
     pi_chart_path = charts.make_pie_chart(status_counts, BUILD)
     difference_percentage = _safe_percentage(difference, len(ticket_rows))

     priority_counts = priority_frequency(ticket_rows)
     bar_chart_path = charts.make_bar_graph(priority_counts, BUILD)
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
          new_ticket_links=new_ticket_links,
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
          new_tickets=new_ticket_links,
          confluence_page_id=confluence_page_id,
     )

def add_new_tickets(ticket_rows, build_page_tickets, creds):
     existing_tickets = {
          ticket_data.get("Ticket Name", "").strip()
          for ticket_data in ticket_rows
          if ticket_data.get("Ticket Name")
     }
     new_ticket_names = sorted(
          ticket_name
          for ticket_name in build_page_tickets
          if ticket_name and ticket_name not in existing_tickets and ticket_name not in SKIP_ROW_MARKERS
     )
     if not new_ticket_names:
          return []

     try:
          service = build("sheets", "v4", credentials=creds)
          rows_to_append = []
          for ticket_name in new_ticket_names:
               ticket_url = f"{JIRA_BASE_URL}/browse/{ticket_name}"
               ticket_formula = f'=HYPERLINK("{ticket_url}", "{ticket_name}")'
               try:
                    priority_value = check_jira_ticket_priority(ticket_name)
               except (requests.exceptions.RequestException, ValueError) as exc:
                    print(f"Unable to fetch Jira priority for {ticket_name}: {exc}")
                    priority_value = "needs prioritization"

               rows_to_append.append(
                    [
                         ticket_formula,
                         build_page_tickets.get(ticket_name, ""),
                         priority_value.title(),
                         "",
                         "",
                         "",
                         "",
                         "",
                         "",
                    ]
               )

          body = {"values": rows_to_append}
          service.spreadsheets().values().append(
               spreadsheetId=SPREADSHEET_ID,
               range=f"'{PAGE}'!A:I",
               valueInputOption="USER_ENTERED",
               insertDataOption="INSERT_ROWS",
               body=body,
          ).execute()
     except HttpError as err:
          print(f"Error adding new tickets: {err}")
          return []

     return [
          {"ticket": ticket_name, "url": f"{JIRA_BASE_URL}/browse/{ticket_name}"}
          for ticket_name in new_ticket_names
     ]


def check_jira_ticket_priority(ticket_id):
     """Retrieve normalized Jira priority for a ticket."""

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
          priority_data = ticket_data["fields"].get("priority")
          if not priority_data:
               return "needs prioritization"
          priority_name = priority_data.get("name", "").strip().lower()
          return priority_name or "needs prioritization"
     except (AttributeError, KeyError) as exc:
          raise ValueError(
               f"Unexpected Jira response shape for ticket '{ticket_id}' priority"
          ) from exc


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


# This function is intended to go to the current build page, and add any tickets that aren't 
# currently on the Tracker, to the Tracker
def get_build_page_tickets():
     # Grab current build page data
     url = f"{JIRA_BASE_URL}/wiki/api/v2/pages/{CURRENT_BUILD_PAGE_ID}?body-format=storage"
     headers = {
          "Accept": "application/json",
          "Content-Type": "application/json"
     }
     auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
     response = requests.get(url, headers=headers, auth=auth, timeout=REQUEST_TIMEOUT_SECONDS)
     response.raise_for_status()
     page_data = response.json()

     # Grab the build number from the page title
     # This gets saved to a constant variable
     build = page_data.get('title', {}).split('|')[1].strip()

     # Grab content from the page_data
     content = page_data.get('body', {}).get('storage', {}).get('value')

     # Parse the content to get just bug information
     soup = BeautifulSoup(content, 'html.parser')
     dirty_bugs = soup.find_all('li')
     clean_bugs = {}
     for li in dirty_bugs:
          if li and li not in clean_bugs:
               text_content = li.get_text(strip=True)
               parts = text_content.split('-', 2)
               bug_title = f"{parts[0]}-{parts[1]}"[1:]
               bug_body = parts[2].strip()
               clean_bugs[bug_title] = bug_body

     # This returns both the Build number as well as the dictionary of bugs present on the build page
     return(build, clean_bugs)

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


if __name__ == "__main__":
     main()
