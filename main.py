import matplotlib.pyplot as plt
import os.path
from datetime import datetime
import requests 
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import json

# Imports for google API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# The ID and range of a sample spreadsheet 
SAMPLE_SPREADSHEET_ID = "1DDoeKkUs7LKQX8xrGrqkH83GyI4zFR1oW3wccayjbfw"
SAMPLE_RANGE_NAME = "A2:H"

# User authentication constants
USER_EMAIL = "kade.peay@ifit.com"
with open("apitoken.txt", "r") as file:
     API_TOKEN = file.read()

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
            print("No data found.")
            return


        # Check status of Jira ticket
        

        # Keep track of status counts
        status_counts = create_dict(values)

        # Save pie chart
        make_pi_chart(status_counts)
    
    except HttpError as err:
        print(err)

# Check status on Jira side
def check_jira_ticket_status(ticket_id):
     url = f"https://ifitdev.atlassian.net/rest/api/3/issue/{ticket_id}"
     headers = {
          "Accept": "application/json",
          "Content-Type": "application/json"
     }
     auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
     response = requests.get(url, headers=headers, auth=auth)
     raw_ticket_json = response.content 

     with open("response.json", "wb") as file:
          file.write(raw_ticket_json)     

     # Search json for the status of the ticket
     ticket_dict = json.loads(raw_ticket_json)

     # Ridiculous json 
     return (ticket_dict["fields"]["status"]["name"])

# Create and save a pie chart based off of the stability of the sheet
def make_pi_chart(status_counts):
        colors = ['green', 'red', 'blue', 'yellow', 'purple', 'orange', 'black']
        plt.pie(status_counts.values(), labels=status_counts.keys(), autopct='%1.1f%%', startangle=45, rotatelabels=True, colors=colors) 
        plt.title("Pie Chart")

        # Save the pie chart with datetime in ISO format
        current_datetime = datetime.now()
        formated_datetime = current_datetime.strftime("%Y-%m-%d %H:%M:%S")
        plt.savefig(f"images/{formated_datetime}")

# Create a python dictionary object from values grabbed from google sheets page
def create_dict(values):
    # Keep track of status counts
        status_counts = {
            'PASSED': 0,
            'FAILED': 0,
            'Untestable': 0,
            'In Progress': 0,
            'Monitoring': 0,
            'Blocked': 0,
            '': 0, # This one helps handle blank entries
        }

        for row in values:
            try:
                status_counts[row[5]] += 1
            except IndexError:
                print("Invalid row: Missing data")

        return status_counts

if __name__ == "__main__":
    #  main()
     print(check_jira_ticket_status('CRY-419'))