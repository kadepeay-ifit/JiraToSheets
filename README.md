# About
The goal of this project is a python script that should ensure parity between the google sheets bug tracker and the actualy bugs on Jira. 
It will also generate reports on the stability of the app based off of data from the sheet.

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