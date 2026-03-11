# About
The goal of this project is a python script that should ensure parity between the google sheets bug tracker and the actualy bugs on Jira. 
It will also generate reports on the stability of the app based off of data from the sheet.

## Prerequisites
Before being able to run this command, you wil need to add your credentials and then the script will prompt you to login with your google account. You will also need an API token from Confluence.

### Google Cloud
To get your credentials, you will need to navigate to your Google Cloud account (if it isn't clear, if you don't have a Google Cloud account, now is the time to go create that) -> APIs & Services -> Credentials.

Here, you will create your new credentials, copy the json file they give you and rename it to ```credentials.json```. Move that file into the directory of the script, and now the file is ready to run. 

### Confluence
To create your Confluence API token you will want to navigate to your account settings -> Security -> API tokens -> Create and manage API tokens. After verifying your email, click on the **Create API token** button at the top of the page.
You will be prompted for a name for the API token, and an expiration date. By Default, the expiration date is set for 1 year. 
After creating the token, match sure to copy the token and add it to your .env file. Ex. API_TOKEN=ATATT3xFfGF0d0uoesJ-4gvRCRlqQ_oGWpJjcteP_IS5EFBB80TOwwyuDVP6YGEYnsyD7vkS1v8EQWf8yfW7_bPjx5wAf_mtZ42JpH_-XinGehvnP-ld9VrfdhNYj61WFN9Dv5kEkEX1GjYb_jyhwAxIkOPKA88N-4VkS63u8dzMh9luQelFSgY=4B5D2264.

## Setting Paramaters

Within the ```google_services.py``` file, edit the ```SAMPLE_SPREADSHEET_ID``` to be the id of whichever spreadsheet you wish to update, and the ```SAMPLE_RANGE_NAME``` if the range of your spreadsheet exceeds the pre-defined range.

Within the ```main.py``` file, you will want to edit the ```BUILD``` variable to match the build version you are evaluating. 

Finally, ensure that either through github secrets, or by creating a local ```.env``` file to contain your Confluence API Token, and a user email.

## Running the script
To run the script, ensure that your python version is up to date. You can check this with:

```Bash
python3 --version
```

It should be 3.14 or newer. 

---

Then install the required packages. To install the required packages for this project, please run the following command in your terminal:

```Bash
pip3 install -r requirements.txt
```

---

Now you should be able to run the script with 

```Bash
python3 main.py
```

The first time the script is run, it will prompt you to log in with your google account. 

## File Descriptions

| File | Purpose |
|------|---------|
| `main.py` | Entry point for the script. Orchestrates the synchronization between Jira and Google Sheets, and handles all data calculations and report generation. |
| `google_services.py` | Manages Google API interactions and abstracts away authentication boilerplate code. |
| `status_mapping.py` | Translates ticket statuses between Jira and Google Sheets tracker formats. |