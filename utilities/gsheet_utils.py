from google.oauth2.service_account import Credentials
from model.model import DetailPage
from googleapiclient.discovery import build
import os
from dotenv import load_dotenv

load_dotenv()

COLUMNS = [DetailPage.model_fields[x].alias for x in DetailPage.model_fields]
COLUMNS.remove('Content')
COLUMNS.append("Article Url")
COLUMNS.append("Date Founded")
COLUMNS.append("Primary Keywords")
COLUMNS.append("Secondary Keywords")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDS = Credentials.from_service_account_file(
    os.getenv("SERVICE_ACCOUNT_FILE"), scopes=SCOPES
)
SERVICE = build("sheets", "v4", credentials=CREDS)
SHEETS = SERVICE.spreadsheets()


def create_new_tab(tab_name: str):
    """Create a new tab with columns in the specified spreadsheet."""
    # Step 1: Create a new tab
    new_sheet_request = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": tab_name,  # Name of the new tab
                        "gridProperties": {
                            "rowCount": 1000,  # Default rows
                        },
                    }
                }
            }
        ]
    }
    try:
        SHEETS.batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body=new_sheet_request
        ).execute()
        add_row(tab_name, COLUMNS)
        print(f"{tab_name} created with columns.")
    except Exception as e:
        if "HttpError 400 when requesting" in str(e):
            print("Sheet already exists.")


def add_row(tab_name: str, values: list[str | float | int]):
    """Append a new row with 13 columns to the 'Archive' sheet."""
    # create_new_tab(tab_name)
    create_new_tab(tab_name)
    # Get the current number of rows in the sheet to find the next available row
    result = (
        SHEETS.values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{tab_name}!A:Z",
        )
        .execute()
    )
    current_rows = len(result.get("values", [])) if "values" in result else 0
    next_row = current_rows + 1

    # Define the range for the new row
    range_to_write = f"{tab_name}!A{next_row}:Z{next_row}"

    # Prepare the request to append the row
    values_request = {
        "valueInputOption": "RAW",
        "data": [
            {
                "range": range_to_write,
                "values": [values],  # Single row with the provided values
            }
        ],
    }

    # Execute the update
    SHEETS.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body=values_request
    ).execute()
    print(f"Row appended at {range_to_write}")
