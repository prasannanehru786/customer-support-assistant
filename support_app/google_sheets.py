from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from support_app.config import GOOGLE_SHEETS_STATE_PATH, ensure_runtime_dirs
from support_app.models import RunRecord

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
SHEET_HEADERS = [
    "created_at",
    "run_id",
    "mode",
    "status",
    "model",
    "rag_hit",
    "web_fallback",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "embedding_tokens",
    "estimated_openai_cost_usd",
    "estimated_embedding_cost_usd",
    "serpapi_searches",
    "estimated_serpapi_cost_usd",
    "image_generation_count",
    "estimated_image_cost_usd",
    "uploaded_image_count",
    "generated_image_count",
    "source_count",
    "guardrail_status",
    "error",
    "langsmith_trace_id",
    "query_hash",
]


def google_sheets_enabled() -> bool:
    return os.getenv("ENABLE_GOOGLE_SHEETS_LOGGING", "false").lower() == "true"


def google_sheets_status_summary() -> str:
    enabled = google_sheets_enabled()
    state = load_state()
    has_service_account = bool(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "").strip()
    )
    has_oauth_refresh = bool(
        os.getenv("GOOGLE_CLIENT_ID", "").strip()
        and os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        and os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    )
    auth_mode = "service_account" if has_service_account else "oauth_refresh" if has_oauth_refresh else "missing"
    if not enabled:
        return "Google Sheets reporting is disabled."
    if auth_mode == "missing":
        return (
            "Google Sheets reporting is enabled but not ready. Configure a service account, "
            "or set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
        )
    destination = "known" if state.get("spreadsheet_id") else "will be created or reused by deterministic app code"
    return (
        "Google Sheets reporting is enabled. "
        f"Authentication mode: {auth_mode}. "
        f"Destination: {destination}. "
        "Only safe run-summary metadata is appended; raw queries, images, audio, and full answers are not sent."
    )


def configured_sheet_tab() -> str:
    return os.getenv("GOOGLE_SHEET_TAB", "Run Logs")


def load_state() -> dict[str, Any]:
    if not GOOGLE_SHEETS_STATE_PATH.exists():
        return {}
    try:
        return json.loads(GOOGLE_SHEETS_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    GOOGLE_SHEETS_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def google_api_available() -> bool:
    try:
        import googleapiclient.discovery  # noqa: F401
        from google.auth.transport.requests import Request  # noqa: F401
    except ImportError:
        return False
    return True


def service_account_credentials() -> Any | None:
    try:
        from google.oauth2 import service_account
    except ImportError:
        return None

    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    service_account_base64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "").strip()

    if service_account_json:
        path = Path(service_account_json)
        if path.exists():
            return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
        try:
            return service_account.Credentials.from_service_account_info(
                json.loads(service_account_json),
                scopes=SCOPES,
            )
        except json.JSONDecodeError:
            return None

    if service_account_base64:
        decoded = base64.b64decode(service_account_base64).decode("utf-8")
        return service_account.Credentials.from_service_account_info(json.loads(decoded), scopes=SCOPES)

    return None


def oauth_refresh_credentials() -> Any | None:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    if not client_id or not client_secret or not refresh_token:
        return None

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    return credentials


def make_credentials() -> Any:
    if not google_api_available():
        raise RuntimeError("Google API packages are not installed. Install requirements.txt and rebuild Docker.")

    credentials = service_account_credentials() or oauth_refresh_credentials()
    if credentials is None:
        raise RuntimeError(
            "Google Sheets logging needs either GOOGLE_SERVICE_ACCOUNT_JSON or "
            "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
        )
    return credentials


def make_services() -> tuple[Any, Any]:
    from googleapiclient.discovery import build

    credentials = make_credentials()
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return sheets, drive


def drive_query_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_drive_file(drive: Any, name: str, mime_type: str, parent_id: str | None = None) -> str | None:
    query_parts = [
        f"name = '{drive_query_literal(name)}'",
        f"mimeType = '{mime_type}'",
        "trashed = false",
    ]
    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")
    response = (
        drive.files()
        .list(
            q=" and ".join(query_parts),
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
        )
        .execute()
    )
    files = response.get("files", [])
    return files[0]["id"] if files else None


def ensure_drive_folder(drive: Any, state: dict[str, Any]) -> str | None:
    configured_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    if configured_folder_id:
        state["folder_id"] = configured_folder_id
        return configured_folder_id

    if state.get("folder_id"):
        return str(state["folder_id"])

    folder_name = os.getenv("GOOGLE_DRIVE_FOLDER_NAME", "CrewAI Support Logs")
    folder_id = find_drive_file(drive, folder_name, "application/vnd.google-apps.folder")
    if folder_id is None:
        folder = (
            drive.files()
            .create(
                body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            )
            .execute()
        )
        folder_id = folder["id"]
    state["folder_id"] = folder_id
    return folder_id


def ensure_spreadsheet(drive: Any, state: dict[str, Any], folder_id: str | None) -> str:
    configured_sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if configured_sheet_id:
        state["spreadsheet_id"] = configured_sheet_id
        return configured_sheet_id

    if state.get("spreadsheet_id"):
        return str(state["spreadsheet_id"])

    sheet_title = os.getenv("GOOGLE_SHEET_TITLE", "CrewAI Support Run Logs")
    spreadsheet_id = find_drive_file(
        drive,
        sheet_title,
        "application/vnd.google-apps.spreadsheet",
        parent_id=folder_id,
    )
    if spreadsheet_id is None:
        body: dict[str, Any] = {
            "name": sheet_title,
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }
        if folder_id:
            body["parents"] = [folder_id]
        created = drive.files().create(body=body, fields="id").execute()
        spreadsheet_id = created["id"]
    state["spreadsheet_id"] = spreadsheet_id
    state["spreadsheet_url"] = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    return spreadsheet_id


def share_file_if_configured(drive: Any, file_id: str) -> None:
    share_with_email = os.getenv("GOOGLE_SHARE_WITH_EMAIL", "").strip()
    if not share_with_email:
        return
    role = os.getenv("GOOGLE_SHARE_ROLE", "writer").strip() or "writer"
    try:
        drive.permissions().create(
            fileId=file_id,
            body={"type": "user", "role": role, "emailAddress": share_with_email},
            fields="id",
            sendNotificationEmail=False,
        ).execute()
    except Exception:
        return


def ensure_sheet_tab_and_headers(sheets: Any, spreadsheet_id: str, tab_name: str) -> None:
    spreadsheet = (
        sheets.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(title))")
        .execute()
    )
    existing_tabs = {
        sheet["properties"]["title"]
        for sheet in spreadsheet.get("sheets", [])
        if "properties" in sheet and "title" in sheet["properties"]
    }
    if tab_name not in existing_tabs:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()

    header_range = f"{tab_name}!A1:X1"
    existing = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=header_range)
        .execute()
        .get("values", [])
    )
    if not existing or existing[0] != SHEET_HEADERS:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=header_range,
            valueInputOption="RAW",
            body={"values": [SHEET_HEADERS]},
        ).execute()


def ensure_google_reporting_destination() -> dict[str, Any]:
    if not google_sheets_enabled():
        return {"enabled": False}
    try:
        sheets, drive = make_services()
        state = load_state()
        folder_id = ensure_drive_folder(drive, state)
        spreadsheet_id = ensure_spreadsheet(drive, state, folder_id)
        if folder_id:
            share_file_if_configured(drive, folder_id)
        share_file_if_configured(drive, spreadsheet_id)
        tab_name = configured_sheet_tab()
        ensure_sheet_tab_and_headers(sheets, spreadsheet_id, tab_name)
        state["tab_name"] = tab_name
        save_state(state)
        return {
            "enabled": True,
            "ready": True,
            "folder_id": folder_id,
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": state.get("spreadsheet_url"),
            "tab_name": tab_name,
        }
    except Exception as exc:
        return {"enabled": True, "ready": False, "error": str(exc)}


def guardrail_status(record: RunRecord) -> str:
    failed_sections: list[str] = []
    for section, value in record.guardrails.items():
        if isinstance(value, dict) and value.get("passed") is False:
            failed_sections.append(section)
    return "pass" if not failed_sections else "failed:" + ",".join(failed_sections)


def run_record_to_sheet_row(record: RunRecord) -> list[Any]:
    cost = record.usage_cost
    return [
        record.created_at,
        record.run_id,
        record.mode,
        record.status,
        record.model,
        record.rag_hit,
        record.web_fallback,
        record.latency_ms,
        cost.prompt_tokens,
        cost.completion_tokens,
        cost.embedding_tokens,
        cost.estimated_openai_cost_usd,
        cost.estimated_embedding_cost_usd,
        cost.serpapi_searches,
        cost.estimated_serpapi_cost_usd,
        cost.image_generation_count,
        cost.estimated_image_cost_usd,
        len(record.uploaded_images),
        len([image for image in record.generated_images if image.storage_path and not image.error]),
        len(record.sources),
        guardrail_status(record),
        record.error or "",
        record.langsmith_trace_id or "",
        record.query_hash,
    ]


def append_run_to_google_sheet(record: RunRecord) -> dict[str, Any]:
    if not google_sheets_enabled():
        return {"enabled": False}
    try:
        destination = ensure_google_reporting_destination()
        if not destination.get("ready"):
            return destination
        sheets, _drive = make_services()
        spreadsheet_id = str(destination["spreadsheet_id"])
        tab_name = str(destination["tab_name"])
        response = (
            sheets.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A:X",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [run_record_to_sheet_row(record)]},
            )
            .execute()
        )
        return {
            "enabled": True,
            "ready": True,
            "updated_range": response.get("updates", {}).get("updatedRange"),
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": destination.get("spreadsheet_url"),
            "tab_name": tab_name,
        }
    except Exception as exc:
        return {"enabled": True, "ready": False, "error": str(exc)}
