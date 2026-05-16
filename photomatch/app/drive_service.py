import io
import json
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.config import settings


SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    """
    Creates Google Drive service using service account JSON
    stored in Render environment variable.
    """

    if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable.")

    credentials_info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=SCOPES
    )

    return build("drive", "v3", credentials=credentials)


def create_folder(
    folder_name: str,
    parent_folder_id: Optional[str] = None
) -> dict:
    service = get_drive_service()

    parent_id = parent_folder_id or settings.GOOGLE_DRIVE_PARENT_FOLDER_ID

    if not parent_id:
        raise ValueError("Missing GOOGLE_DRIVE_PARENT_FOLDER_ID environment variable.")

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }

    folder = service.files().create(
        body=metadata,
        fields="id, name, webViewLink"
    ).execute()

    return folder


def upload_bytes_to_drive(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    folder_id: str
) -> dict:
    service = get_drive_service()

    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=mime_type,
        resumable=False
    )

    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink"
    ).execute()

    return uploaded_file


def make_file_public(file_id: str) -> None:
    """
    Makes uploaded file readable by anyone with the link.
    For internal/private workflows, we may remove this later.
    """

    service = get_drive_service()

    permission = {
        "type": "anyone",
        "role": "reader"
    }

    service.permissions().create(
        fileId=file_id,
        body=permission
    ).execute()


def safe_drive_folder_name(store_name: str, salesforce_grid: Optional[str] = None) -> str:
    clean_store = "".join(
        c if c.isalnum() or c in [" ", "_", "-", "."] else "_"
        for c in store_name
    ).strip()

    clean_grid = salesforce_grid or "no_grid"
    clean_grid = "".join(
        c if c.isalnum() or c in [" ", "_", "-", "."] else "_"
        for c in clean_grid
    ).strip()

    return f"PhotoMatch - {clean_store} - {clean_grid}"
