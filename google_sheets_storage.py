
"""Google Sheets storage for anonymous LTLI QA events."""



import json

import logging

from datetime import datetime, timezone



from google.oauth2 import service_account

from googleapiclient.discovery import build



LOGGER = logging.getLogger(__name__)



CREDENTIALS_FILE = "/etc/ltli/secrets/google-service-account.json"

SPREADSHEET_ID = "1ikhPeouuKeFuvYgglIjtNguygKjJmsKmfqarDLwsiQY"



SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]





def append_event(session_id, event_name, metadata):

    """Append an anonymous event. Return False if storage fails."""

    try:

        credentials = service_account.Credentials.from_service_account_file(

            CREDENTIALS_FILE,

            scopes=SCOPES,

        )



        service = build(

            "sheets",

            "v4",

            credentials=credentials,

            cache_discovery=False,

        )



        row = [

            datetime.now(timezone.utc).isoformat(),

            str(session_id),

            str(event_name),

            json.dumps(metadata, ensure_ascii=False),

        ]



        service.spreadsheets().values().append(

            spreadsheetId=SPREADSHEET_ID,

            range="analytics_events!A:D",

            valueInputOption="RAW",

            insertDataOption="INSERT_ROWS",

            body={"values": [row]},

        ).execute()



        return True



    except Exception:

        LOGGER.exception("Google Sheets telemetry write failed")

        return False

