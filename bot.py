import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load the JSON from Render environment variable
creds_json = os.getenv("GOOGLE_CREDENTIALS")
creds_dict = json.loads(creds_json)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("DoorToDoor_Territories").sheet1


test_variable = 1
# Test print
rows = sheet.get_all_records()
print("First 5 rows from the sheet:")
for row in rows[:5]:
    print(row)
