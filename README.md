# About
The goal of this project is a python script that should ensure parity between the google sheets bug tracker and the actualy bugs on Jira. 
It will also generate reports on the stability of the app based off of data from the sheet.


## Prerequisites
Before being able to run this command, you wil need to add your credentials and then the script will prompt you to login with your google account. 

To get your credentials, you will need to navigate to your Google Cloud account (if it isn't clear, if you don't have a Google Cloud account, now is the time to go create that) -> APIs & Services -> Credentials.

Here, you will create your new credentials, copy the json file they give you and rename it to ```credentials.json```. Move that file into the directory of the script, and now the file is ready to run. 

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