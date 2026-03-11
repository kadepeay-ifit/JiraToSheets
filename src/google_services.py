import os
from google.auth.transport.requests import Request  
from google.oauth2.credentials import Credentials 
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# The ID and range of a sample spreadsheet 
SAMPLE_SPREADSHEET_ID = "1DDoeKkUs7LKQX8xrGrqkH83GyI4zFR1oW3wccayjbfw"
SAMPLE_RANGE_NAME = "A2:H"


def get_credential_data():
     """
     Retrieves and manages Google API credentials for the application.
     This function handles credential retrieval from a stored token file or initiates
     a new OAuth 2.0 authorization flow if no valid credentials exist. It automatically
     refreshes expired credentials when a refresh token is available.
     Process flow:
     1. Checks for an existing token.json file containing saved credentials
     2. If credentials exist and are valid, uses them
     3. If credentials are expired but have a refresh token, refreshes them
     4. If no valid credentials exist, initiates a new OAuth 2.0 login flow
     5. Saves the credentials to token.json for future use
     Returns:
          google.oauth2.credentials.Credentials: Valid Google API credentials object
               authenticated with the scopes defined in the SCOPES constant.
     Note:
          Requires 'credentials.json' file in the working directory for initial
          OAuth 2.0 authentication flow.
     """

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

     print(f"Credentials Data Received.\n")

     return creds


def get_sheet_data(creds):
     """
     Retrieves data from a Google Sheet.
     This function authenticates with Google Sheets API using stored credentials,
     then fetches values from a predefined spreadsheet and range.
     Returns:
          list: A list of rows containing the sheet data, where each row is a list of cell values.
                 Returns None if no data is found in the specified range.
          creds: Google API credentials object for authenticating with the Sheets API.
     Raises:
          Prints error message if an HttpError occurs during API communication.
     Note:
          Requires SAMPLE_SPREADSHEET_ID and SAMPLE_RANGE_NAME to be defined globally.
          Requires valid credentials to be available via get_credential_data().
     """

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
         
         print(f"Tracker Data Received.\n")
         return values
     
     except HttpError as err:
          print(err)
