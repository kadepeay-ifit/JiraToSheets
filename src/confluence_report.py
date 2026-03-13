from datetime import datetime
import os
from atlassian import Confluence 
import json
from dotenv import load_dotenv

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://ifitdev.atlassian.net").rstrip("/")

BUILD = os.getenv("BUILD_VERSION")

# User authentication constants
API_TOKEN = os.getenv("API_TOKEN")
USER_EMAIL = os.getenv("USER_EMAIL")

# Confluence page constants
SPACE_KEY = os.getenv("SPACE_KEY")
PARENT_PAGE_ID = os.getenv("PARENT_PAGE_ID") # Let's try saving to a folder

def create_page():
    confluence = Confluence(
        url=JIRA_BASE_URL,
        username=USER_EMAIL,
        password=API_TOKEN,
        cloud=True
    )



    # Set page details 
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%Y-%m-%d_%H-%M-%S")
    page_title = f"Health Report: {BUILD}_{formatted_datetime}"


    # Empty variables for testing
    num_tickets = 100
    difference_percentage = 0.0
    count = 100
    passed = 10
    failed = 7
    untestable = 0
    in_progress = 0
    monitoring = 4
    blocked = 1
    time_taken = "1:25"

    page_body = f"""

        <h1> Reporting stats for build version {BUILD} </h1>
        <hr>
        <p> Number of Different Ticket Values: {num_tickets} </p>
        <p> Difference before Updating Sheet: {difference_percentage}% </p>

        <p> Count of each Status: </p>
        <ul>
            <li> Passed: {passed} - - - - ({passed / count}%) </li>
            <li> Passed: {failed} - - - - ({failed / count}%) </li>
            <li> Passed: {untestable} - - - - ({untestable / count}%) </li>
            <li> Passed: {in_progress} - - - - ({in_progress / count}%) </li>
            <li> Passed: {monitoring} - - - - ({monitoring / count}%) </li>
            <li> Passed: {blocked} - - - - ({blocked / count}%) </li>
        </ul>

        <p> Viewed 64 rows on the Tracker. </p>
        <p> Program execution time: {time_taken} <p>

        <img src="images/Retail-2026-02_2026-03-13_09-08-26.png" alt="Pie Chart for {BUILD}">
    """

    # Create the page 
    status = confluence.create_page(
        space=SPACE_KEY, 
        title=page_title,
        body=page_body,
        parent_id=PARENT_PAGE_ID
    )


    # print(status)
    if status.get('id'):
        print(f"Page created with ID: {status['id']}")
    else:
        print("Page creation failed or status is not as expected.")


if __name__ == '__main__':
    try:
        create_page()
    except Exception as e:
        print(f"An error occured: {e}")