import os
import json
import requests 
import status_mapping
import matplotlib.pyplot as plt
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from datetime import datetime
from tqdm import tqdm # For progress bars

# Imports for google API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

print() # whitespace

# If modifying these scopes, delete the file token.json
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# The ID and range of a sample spreadsheet 
SAMPLE_SPREADSHEET_ID = "1DDoeKkUs7LKQX8xrGrqkH83GyI4zFR1oW3wccayjbfw"
SAMPLE_RANGE_NAME = "A2:H"

# Upate to current build number for accurate naming
BUILD = "Retail-2026-02"

# load_dotenv() will load variables from a local .env file during development.
# In GitHub Actions, it will be ignored as there is no .env file,
# and the variable is already set in the environment by the workflow file.
load_dotenv() 

# User authentication constants
API_TOKEN = os.getenv('API_TOKEN')
USER_EMAIL = os.getenv('USER_EMAIL')

if API_TOKEN is None:
     print("Error: API key not found in environment variables.\n")
else:
     print("API Key successfully loaded.\n")

if USER_EMAIL is None: 
     print("Error: User Email not found in environment variables.\n")
else:
     print("User Email successfully loaded.\n")

def main():
    creds = None

    # The file token.json stores the user's access and refresh tokens, and is created automatically when the authorization flow completes for the first time 
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else: 
            flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("sheets", "v4", credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = (
                sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID, range=SAMPLE_RANGE_NAME).execute()
        )
        values = result.get("values", [])

        if not values:
            print("No data found.\n")
            return

     
        # Create a dictionary of values for both sheets and jira
        ticket_dict = create_dict(values)

        print(f"Difference: {caclulate_difference(ticket_dict)}\n")
        
        # TODO: Update Sheets


        # Report Stats
        status_counts = status_frequency(ticket_dict)
        make_pi_chart(status_counts)
    
    except HttpError as err:
        print(err)

# Calculate the difference between ticket values on the Tracker and in Jira
def caclulate_difference(ticket_dict):
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
     return f"{round((difference / len(ticket_dict)) * 100, 2)}%" # round to 2 decimal places

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
     """

     ticket_dict = {}
     for row in tqdm(values, "Creating Dictionary"):
          try:
                ticket_name = row[0]
                sheet_status = row[5].lower() if len(row) > 5 and row[5] else 'in progress' # default to in progress

                # Translate ticket types between jira and sheets
                jira_status = check_jira_ticket_status(ticket_name)
                translated_jira_status = status_mapping.MAP.get(jira_status) # Translation layer also makes all lowercase

                ticket_dict[ticket_name] = {
                     "Sheet Status": sheet_status,
                     "Jira Status": translated_jira_status
                }
          except IndexError:
               print(f"Error while creating dictionary. Problem row: {row}\n")

     print("Ticket Dictionary Created Successfully.\n")
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

     url = f"https://ifitdev.atlassian.net/rest/api/3/issue/{ticket_id}"
     headers = {
          "Accept": "application/json",
          "Content-Type": "application/json"
     }
     auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
     response = requests.get(url, headers=headers, auth=auth)
     raw_ticket_json = response.content 

     # Search json for the status of the ticket
     ticket_dict = json.loads(raw_ticket_json)

     # Most Recent status name
     return (ticket_dict["fields"]["status"]["name"])

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

     for row in tqdm(ticket_dict, "Counting Status Frequency"):
          try:
               status_counts[ticket_dict[row]["Sheet Status"]] += 1
          except IndexError:
               print("Invalid row: Missing data\n")

     print("Status Frequency Counted Successfully.\n")
     return status_counts

# Create and save a pie chart based off of the stability of the sheet
# TODO: Successfully ignoring zeroes, but now colors are off. Perhaps map them to specific values?
def make_pi_chart(status_counts):
     """
     Create and save a pie chart visualization of status counts.
     Args:
          status_counts (dict): A dictionary with status names as keys and their counts as values.
     Returns:
          None
     Description:
          Filters out statuses with zero counts, creates a pie chart with the remaining statuses,
          and saves it as an image file with a timestamp. The chart includes percentage labels
          and is rotated for better readability.
     Side Effects:
          - Displays a pie chart using matplotlib
          - Saves the figure to the 'images/' directory with format: {BUILD}_{timestamp}.png
          - Prints a message confirming the file save location
     """


     colors = ['green', 'red', 'blue', 'yellow', 'purple', 'orange']
     filtered_counts = {}
     for key, val in tqdm(status_counts.items(), "Creating Pie Chart"):
          if val > 0:
               filtered_counts[key] = val
     plt.pie(filtered_counts.values(), labels=filtered_counts.keys(), autopct='%1.1f%%', startangle=45, rotatelabels=True, colors=colors) 
     plt.title(f"Current Health of {BUILD}")

     # Save the pie chart with datetime in ISO format
     current_datetime = datetime.now()
     formated_datetime = current_datetime.strftime("%Y-%m-%d_%H:%M:%S")
     fig_name = f"{BUILD}_{formated_datetime}"
     plt.savefig(f"images/{fig_name}")

     print(f"Saved figure to images/{fig_name}\n")

if __name__ == "__main__":
     main()
