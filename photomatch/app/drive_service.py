import io
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.config import settings


SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    """
    Creates Google Drive service using OAuth refresh token.
    Files are uploaded to the user's Google Drive, not to a service account.
    """

    if not settings.GOOGLE_CLIENT_ID:
        raise ValueError("Missing GOOGLE_CLIENT_ID environment variable.")

    if not settings.GOOGLE_CLIENT_SECRET:
        raise ValueError("Missing GOOGLE_CLIENT_SECRET environment variable.")

    if not settings.GOOGLE_REFRESH_TOKEN:
        raise ValueError("Missing GOOGLE_REFRESH_TOKEN environment variable.")

    credentials = Credentials(
        token=None,
        refresh_token=settings.GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=SCOPES
    )

    credentials.refresh(Request())

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
        fields="id, name, webViewLink",
        supportsAllDrives=True
    ).execute()

    return folder


def upload_bytes_to_drive(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    folder_id: str
) -> dict:
    service = get_drive_service()

    if not file_bytes:
        raise ValueError("Cannot upload empty file to Google Drive.")

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
        fields="id, name, webViewLink, size, mimeType",
        supportsAllDrives=True
    ).execute()

    return uploaded_file


def make_file_public(file_id: str) -> None:
    """
    Makes uploaded file readable by anyone with the link.
    For internal/private production we may disable this later.
    """

    service = get_drive_service()

    permission = {
        "type": "anyone",
        "role": "reader"
    }

    service.permissions().create(
        fileId=file_id,
        body=permission,
        supportsAllDrives=True
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
