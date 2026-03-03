import matplotlib.pyplot as plt
import os.path

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

        # Keep track of status counts
        status_counts = {
            'PASSED': 0,
            'FAILED': 0,
            'Untestable': 0,
            'In Progress': 0,
            'Monitoring': 0,
            'Blocked': 0,
        }
    
        # Print out read values
        print("Ticket, Status:")
        for row in values:
            try:
                print(f"{row[0]}, {row[5]}")
                status_counts[row[5]] += 1
            except IndexError:
                print("Invalid row: Missing data")

        # plt.pie(status_counts.values) 
        # plt.title("Pie Chart")
        # plt.show()
    
    except HttpError as err:
        print(err)

if __name__ == "__main__":
    main()
