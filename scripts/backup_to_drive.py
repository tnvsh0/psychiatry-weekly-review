#!/usr/bin/env python3
"""
Backup weekly podcast MP3s and markdown summaries to Google Drive.

Used as a redundancy layer on top of GitHub Releases / git, so the content
survives even if the GitHub repository is taken down.

Required environment variables:
    GDRIVE_SERVICE_ACCOUNT_JSON  Full JSON content of a Google Cloud
                                 service account key with Drive access.
    GDRIVE_FOLDER_ID             ID of a Drive folder that has been shared
                                 with the service account email
                                 (Editor permission).

Usage:
    python scripts/backup_to_drive.py --date 2026-05-17
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _load_drive_service():
    """Return a Drive v3 service built from the service account JSON."""
    sa_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_json:
        print("  Drive backup skipped: GDRIVE_SERVICE_ACCOUNT_JSON not set.")
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        print("  Drive backup skipped: google-api-python-client not installed.")
        return None
    try:
        info = json.loads(sa_json)
    except json.JSONDecodeError as e:
        print(f"  Drive backup skipped: bad service-account JSON: {e}")
        return None
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_or_create_folder(service, name: str, parent_id: str) -> str | None:
    """Return the ID of a Drive folder named `name` under `parent_id`."""
    safe_name = name.replace("'", "\\'")
    query = (
        f"name = '{safe_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents and trashed = false"
    )
    resp = service.files().list(
        q=query, fields="files(id, name)", pageSize=10,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    items = resp.get("files", [])
    if items:
        return items[0]["id"]
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(
        body=meta, fields="id", supportsAllDrives=True,
    ).execute()
    return created.get("id")


def _upload_file(service, local_path: Path, parent_id: str) -> bool:
    """Upload one file to the given Drive folder. Returns True on success."""
    from googleapiclient.http import MediaFileUpload
    try:
        media = MediaFileUpload(str(local_path), resumable=True)
        meta = {"name": local_path.name, "parents": [parent_id]}
        service.files().create(
            body=meta, media_body=media, fields="id",
            supportsAllDrives=True,
        ).execute()
        return True
    except Exception as e:
        print(f"    FAILED {local_path.name}: {e}")
        return False


def backup(date_str: str) -> int:
    """Upload everything under podcasts/{date}/ and summaries/{date}/.
    Returns shell-style exit code (0 on success, 1 on hard error)."""
    parent_id = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
    if not parent_id:
        print("  Drive backup skipped: GDRIVE_FOLDER_ID not set.")
        return 0  # non-fatal: feature simply off

    service = _load_drive_service()
    if service is None:
        return 0

    repo_root = Path(__file__).resolve().parent.parent
    podcast_dir = repo_root / "podcasts" / date_str
    summary_dir = repo_root / "summaries" / date_str

    files: list[Path] = []
    if podcast_dir.exists():
        files += sorted(podcast_dir.glob("*.mp3"))
    if summary_dir.exists():
        files += sorted(summary_dir.glob("*.md"))
        articles = summary_dir / "articles.json"
        if articles.exists():
            files.append(articles)

    if not files:
        print(f"  Drive backup: nothing to upload for {date_str}")
        return 0

    print(f"  Drive backup: {len(files)} file(s) for {date_str}")
    folder_id = _find_or_create_folder(service, f"Weekly Review {date_str}", parent_id)
    if not folder_id:
        print("  Drive backup: could not create or find target folder.")
        return 1

    ok = 0
    for f in files:
        if _upload_file(service, f, folder_id):
            ok += 1
    print(f"  Drive backup: uploaded {ok}/{len(files)} file(s).")
    return 0 if ok == len(files) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup weekly review to Google Drive")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    return backup(args.date)


if __name__ == "__main__":
    sys.exit(main())
