import requests
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASEROW_URL")
BASE_TOKEN = os.getenv("BASEROW_TOKEN")


def auth_user() -> str:
    payload = {"email": "admin@gmail.com", "password": "admin12345"}
    response = requests.post(f"{BASE_URL}/api/user/token-auth/", data=payload)
    response.raise_for_status()
    json_data = response.json()
    return json_data["token"]


def create_table(table_name: str) -> str:
    # Prepare the request payload
    HEADERS = {
        "Authorization": f"JWT {auth_user()}",
        "Content-Type": "application/json",
    }
    payload = {
        "name": table_name,
    }
    endpoint = f"{BASE_URL}/api/database/tables/database/197/"
    response = requests.get(endpoint, headers=HEADERS)
    for x in response.json():
        print(x, response.json(), payload)
        if x["name"] == payload["name"]:
            return x["id"]

    response = requests.post(endpoint, headers=HEADERS, json=payload)
    json_data = response.json()
    table_id = json_data["id"]
    for row_id in [1, 2]:
        requests.delete(
            f"{BASE_URL}/api/database/rows/table/{table_id}/{row_id}/",
            headers={"Authorization": f"Token {BASE_TOKEN}"},
        )

    return table_id


def update_fields(table_id: int):
    print(f"Table id - {table_id}")
    HEADERS = {
        "Authorization": f"JWT {auth_user()}",
        "Content-Type": "application/json",
    }
    # Prepare the request payload
    fields = [
        {"name": "Date Scraped", "type": "text"},
        {"name": "Date Of Article", "type": "text"},
        {"name": "News Article", "type": "text"},
        {"name": "Link", "type": "url"},
        {"name": "Suspect Name", "type": "text"},
        {"name": "Charges", "type": "text"},
        {"name": "Primary Keywords", "type": "text"},
        {"name": "Secondary Keywords", "type": "text"},
    ]
    for field in fields:
        endpoint = f"{BASE_URL}/api/database/fields/table/{table_id}/"
        response = requests.post(endpoint, headers=HEADERS, json=field)
        json_data = response.json()
        if json_data.get("error") == "ERROR_FIELD_WITH_SAME_NAME_ALREADY_EXISTS":
            pass

    response = requests.get(
        f"{BASE_URL}/api/database/fields/table/{table_id}/", headers=HEADERS
    )
    for field in response.json():
        if field["name"] == "Date Scraped":
            requests.post(
                f"{BASE_URL}/api/database/fields/table/{table_id}/change-primary-field/",
                json={"new_primary_field_id": field["id"]},
                headers=HEADERS,
            )
    for field in response.json():
        if field["name"] in ["Name", "Notes", "Active"]:
            requests.delete(
                f"{BASE_URL}/api/database/fields/{field['id']}/", headers=HEADERS
            )
    return table_id


# Headers for authentication and content type
def add_data(table_name: str, data: dict):
    table_id = update_fields(create_table(table_name))
    # baserow = BaserowApi(database_url=BASE_URL, token=BASE_TOKEN)
    response = requests.post(
        f"{BASE_URL}/api/database/rows/table/{table_id}/?user_field_names=true",
        headers={
            "Authorization": f"Token {BASE_TOKEN}",
            "Content-Type": "application/json",
        },
        json=data,
    )
    print(response.text)


# add_data(
#     table_name="text.com",
#     data={
#         "Date Scraped": "datetime.now().isoformat()",
#         "Date Of Article": "item.date",
#         "News Article": "item.title",
#         "Link": "https://www.api-football.com/documentation-v3#tag/Players",
#         "Suspect Name": "item.suspect_name",
#         "Charges": "item.charge",
#         "Primary Keywords": "primary_keywords",
#         "Secondary Keywords": "secondary_keywords",
#     },
# )
