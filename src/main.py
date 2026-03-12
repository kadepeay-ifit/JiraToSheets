import os
from pathlib import Path

import requests
import status_mapping
import google_services
import matplotlib.pyplot as plt
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from datetime import datetime
from tqdm import tqdm  # For progress bars
from google_services import SAMPLE_SPREADSHEET_ID
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# load_dotenv() will load variables from a local .env file during development.
# In GitHub Actions, it will be ignored as there is no .env file,
# and the variable is already set in the environment by the workflow file.
load_dotenv()

DEFAULT_BUILD = "Retail-2026-02"
BUILD = os.getenv("BUILD_VERSION", DEFAULT_BUILD)
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://ifitdev.atlassian.net").rstrip("/")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("JIRA_REQUEST_TIMEOUT_SECONDS", "15"))
SKIP_ROW_MARKERS = {"2026-01"}

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
     print("API credentials loaded successfully.\n")

def main():
     start = datetime.now() # Start the timer
     validate_env_vars()

     # Get Credentials
     creds = google_services.get_credential_data()

     # Get a set of values from the Tracker
     values = google_services.get_sheet_data(creds)
     if not values:
          print("No tracker values were returned. Exiting.\n")
          return
     
     # Create a dictionary of values for both sheets and jira
     ticket_dict = create_dict(values)
     if not ticket_dict:
          print("No ticket rows were processed. Exiting.\n")
          return

     # Print percentage difference between Sheets and Jira
     difference = calculate_difference(ticket_dict)
     
     # Update Sheets
     num_updated_rows = update_sheet_data(ticket_dict, creds)

     # Report Stats
     status_counts = status_frequency(ticket_dict)
     make_pie_chart(status_counts)

     print(f"    ------------------------------------------------    \n")

     print(f"Reporting stats for build version {BUILD}.\n")

     print(f"Number of Different Ticket Values: {difference}\n")

     print(f"Difference before updating: {round((difference / len(ticket_dict)) * 100, 2)}%\n")

     print(f"Count of each Status:")
     for status, count in status_counts.items():
          print(f"    {status}: {count}\n")

     print(f"Looked at {num_updated_rows} rows on the Tracker.\n")

     # Report time taken to execute script
     end = datetime.now()
     print(f"Program Finished in: {(end - start).total_seconds() // 60:.0f}:{(end - start).total_seconds() % 60:.0f}\n")

def update_sheet_data(ticket_dict, creds):
     """
     Update Google Sheets with Jira ticket status data.
     This function takes a dictionary of ticket data and Google Sheets API credentials,
     then updates the status column (F2:F) in the specified spreadsheet with formatted
     Jira status values.
     Args:
          ticket_dict (dict): Dictionary containing ticket data where each value contains
               a "Jira Status" key with the ticket's current status.
          creds: Google API credentials object for authenticating with the Sheets API.
     Returns:
          None
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
          - Updates are applied to column F (status column) starting from row 2 (F2:F)
          - SAMPLE_SPREADSHEET_ID must be defined in the module scope
     """

     try:
          service = build("sheets", "v4", credentials=creds)
                    
          updates = []
          for ticket_data in tqdm(ticket_dict.values(), "Updating Sheet"):
               jira_status = ticket_data.get("Jira Status")
               
               # Capitalize for sheet format
               # Sheet uses title for most, passed and failed are all caps
               # Potentially update on sheets itself how statuses are capitalized
               if jira_status is not None:
                    jira_status = jira_status.title()
                    if jira_status.lower() == "passed" or jira_status.lower() == "failed":
                         jira_status = jira_status.upper()
               else:
                    jira_status = 'In Progress'
               updates.append([jira_status])
          
          # Update the sheet with new values
          body = {"values": updates}
          service.spreadsheets().values().update(
               spreadsheetId=SAMPLE_SPREADSHEET_ID,
               range="F2:F",
               valueInputOption="USER_ENTERED",
               body=body
          ).execute()
          
          print("Sheet updated successfully.\n")
          return len(updates) # Return rows changed
     
     except HttpError as err:
          print(f"Error updating sheet: {err}\n")
          return 0

# Calculate the difference between ticket values on the Tracker and in Jira
def calculate_difference(ticket_dict):
     """
     Calculate the percentage of tickets with mismatched statuses between Sheet and Jira.
     Args:
          ticket_dict (dict): A dictionary where each value contains ticket data with 
                                 "Sheet Status" and "Jira Status" keys.
     Returns:
          str: A string representation of the percentage of tickets with differing statuses,
                rounded to 2 decimal places (e.g., "25.50%").
     """

     difference = 0
     for _, ticket_data in tqdm(ticket_dict.items(), "Calculating Difference"):
          sheet = ticket_data["Sheet Status"]
          jira = ticket_data["Jira Status"]
          # print(f"Sheet: {sheet}, Jira: {jira}\n")
          if(sheet != jira): 
               difference += 1

     print(f"Difference Percentage Calculated Successfully.\n")

     return difference

# Backwards-compatible alias for historical misspelling.
def caclulate_difference(ticket_dict):
     return calculate_difference(ticket_dict)

# Create a dictionary of ticket names with the status of google sheets and jira as the values
def create_dict(values): 
     """
     Create a dictionary mapping ticket names to their status information from both Sheets and Jira.
     
     Args:
          values (list): A list of rows where each row contains ticket information.
                           Expected format: row[0] = ticket_name, row[5] = sheet_status
     
     Returns:
          dict: A dictionary with ticket names as keys and status information as values.
                 Each value is a dict with:
                 - "Sheet Status": The status from the sheet (lowercase), defaults to 'in progress' if not provided
                 - "Jira Status": The translated Jira status (lowercase)
     
     Raises:
          Prints error message if IndexError occurs while processing a row, but continues execution.
     
     Note:
          - Uses tqdm to display progress bar during dictionary creation
          - Requires check_jira_ticket_status() function and status_mapping.MAP for translations
          - Handles missing or empty status values gracefully with a default value
          - Skips rows where columns A-C contain date objects
     """

     ticket_dict = {}
     unknown_statuses = set()
     for row in tqdm(values, "Creating Dictionary"):
          if not row:
               continue
          try:
               ticket_name = row[0]
               if not ticket_name or ticket_name in SKIP_ROW_MARKERS:
                    continue

               sheet_status = row[5].lower() if len(row) > 5 and row[5] else "in progress"

               # Translate ticket types between jira and sheets
               jira_status = check_jira_ticket_status(ticket_name)
               if jira_status not in status_mapping.MAP:
                    unknown_statuses.add(jira_status)
               translated_jira_status = status_mapping.MAP.get(jira_status, "in progress")

               ticket_dict[ticket_name] = {
                    "Sheet Status": sheet_status,
                    "Jira Status": translated_jira_status
               }
          except (IndexError, requests.exceptions.RequestException, ValueError) as exc:
               print(f"Skipping row due to processing error: {row} ({exc})\n")

     print("Ticket Dictionary Created Successfully.\n")
     if unknown_statuses:
          print(
               "Encountered Jira statuses missing from status_mapping.MAP: "
               f"{', '.join(sorted(unknown_statuses))}\n"
          )
     return ticket_dict

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
def status_frequency(ticket_dict):
     """
     Count the frequency of each status in the ticket dictionary.
     This function iterates through a dictionary of tickets and tallies the number
     of occurrences for each status type. It tracks six status categories: passed,
     failed, untestable, in progress, monitoring, and blocked.
     Args:
          ticket_dict (dict): A dictionary where keys are row identifiers and values
                                 are dictionaries containing ticket information. Each ticket
                                 dictionary must have a "Sheet Status" key.
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

     for ticket_data in tqdm(ticket_dict.values(), "Counting Status Frequency"):
          status = ticket_data.get("Sheet Status", "in progress")
          if status not in status_counts:
               status_counts[status] = 0
          status_counts[status] += 1

     print("Status Frequency Counted Successfully.\n")
     return status_counts

# Create and save a pie chart based off of the stability of the sheet
def make_pie_chart(status_counts):
     """
     Create and save a pie chart visualization of status counts.
     Args:
          status_counts (dict): A dictionary with status names as keys and their counts as values.
     Returns:
          None
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
          'passed': 'green',
          'failed': 'red',
          'untestable': 'blue',
          'in progress': 'yellow',
          'monitoring': 'purple',
          'blocked': 'orange',
          '': 'black' # Just in case there is any blank values
     }
     
     filtered_counts = {}
     colors = []
     for key, val in tqdm(status_counts.items(), "Creating Pie Chart"):
          if val > 0:
               filtered_counts[key] = val
               colors.append(color_mapping.get(key, "gray"))

     if not filtered_counts:
          print("No status counts available to chart.\n")
          return

     plt.figure(figsize=(8, 8))
     
     plt.pie(filtered_counts.values(), labels=filtered_counts.keys(), autopct='%1.1f%%', startangle=45, rotatelabels=True, colors=colors) 
     plt.title(f"Current Health of {BUILD}")

     # Save the pie chart with datetime in ISO format
     current_datetime = datetime.now()
     formatted_datetime = current_datetime.strftime("%Y-%m-%d_%H-%M-%S")
     fig_name = f"{BUILD}_{formatted_datetime}.png"
     output_dir = Path("images")
     output_dir.mkdir(parents=True, exist_ok=True)
     output_path = output_dir / fig_name
     plt.savefig(output_path)
     plt.close()

     print(f"Saved figure to {output_path}\n")

# Backwards-compatible alias.
def make_pi_chart(status_counts):
     make_pie_chart(status_counts)

if __name__ == "__main__":
     main()
