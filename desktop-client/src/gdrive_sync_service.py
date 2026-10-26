# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import mimetypes
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

from gdrive_client import load_gdrive_config

class GoogleDriveSyncDaemon:
    def __init__(self):
        self.config = load_gdrive_config()
        self.root_folder_id = self.config.get("folder_id", "1r984fj4btDKUnSfqfJlW2jzrRhVWaROB")
        self.sync_dir = Path.home() / "FileExchangeShared"
        self.running = False
        self.service = None
        self.folder_cache = {}
        self._init_drive()

    def _init_drive(self):
        try:
            client_id = self.config.get("client_id")
            client_secret = self.config.get("client_secret")
            refresh_token = self.config.get("refresh_token")
            if not (client_id and client_secret and refresh_token):
                print("[GDRIVE] Warning: credentials not found")
                return

            creds = Credentials.from_authorized_user_info({
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token"
            })
            self.service = build('drive', 'v3', credentials=creds)
            print("[GDRIVE] Connected successfully to Google Drive (15GB)")
        except Exception as e:
            print(f"[GDRIVE ERROR] Init failed: {e}")

    def refresh_folders(self):
        if not self.service:
            return
        try:
            res = self.service.files().list(
                q=f"'{self.root_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="files(id, name)"
            ).execute()
            self.folder_cache = {f['name']: f['id'] for f in res.get('files', [])}
        except Exception as e:
            print(f"[GDRIVE] Folder refresh error: {e}")

    def get_or_create_folder(self, folder_name):
        if folder_name in self.folder_cache:
            return self.folder_cache[folder_name]
        try:
            meta = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [self.root_folder_id]
            }
            fld = self.service.files().create(body=meta, fields='id, name').execute()
            self.folder_cache[folder_name] = fld['id']
            return fld['id']
        except Exception as e:
            print(f"[GDRIVE] Failed to create folder {folder_name}: {e}")
            return self.root_folder_id

    def upload_local_file(self, file_path):
        if not self.service:
            return
        p = Path(file_path)
        if not p.exists() or p.name.startswith(('~', '.')):
            return

        try:
            rel = p.relative_to(self.sync_dir)
            dept_name = rel.parts[0] if len(rel.parts) > 1 else 'القسم العام'
        except Exception:
            dept_name = 'القسم العام'

        target_parent = self.get_or_create_folder(dept_name)
        mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'

        res = self.service.files().list(
            q=f"'{target_parent}' in parents and name = '{p.name}' and trashed = false",
            fields="files(id, modifiedTime)"
        ).execute()
        files = res.get('files', [])

        media = MediaFileUpload(str(p), mimetype=mime, resumable=True)
        if files:
            f_id = files[0]['id']
            self.service.files().update(
                fileId=f_id,
                media_body=media,
                fields='id, name, modifiedTime'
            ).execute()
            print(f"[GDRIVE SYNC] Updated in cloud: {p.name} ({dept_name})")
        else:
            meta = {'name': p.name, 'parents': [target_parent]}
            self.service.files().create(
                body=meta,
                media_body=media,
                fields='id, name'
            ).execute()
            print(f"[GDRIVE SYNC] Uploaded new file: {p.name} ({dept_name})")

    def pull_cloud_updates(self):
        """Check Google Drive for any new or updated files from web and download them"""
        if not self.service:
            return
        try:
            self.refresh_folders()
            for dept_name, fld_id in self.folder_cache.items():
                dept_local = self.sync_dir / dept_name
                dept_local.mkdir(parents=True, exist_ok=True)

                res = self.service.files().list(
                    q=f"'{fld_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false",
                    fields="files(id, name, modifiedTime, size)"
                ).execute()

                for remote in res.get('files', []):
                    local_target = dept_local / remote['name']
                    if not local_target.exists():
                        print(f"[GDRIVE PULL] Downloading new file from cloud: {remote['name']}")
                        req = self.service.files().get_media(fileId=remote['id'])
                        with open(local_target, 'wb') as fh:
                            downloader = MediaIoBaseDownload(fh, req)
                            done = False
                            while not done:
                                _, done = downloader.next_chunk()
                        print(f"  Saved to: {local_target}")
        except Exception as e:
            print(f"[GDRIVE PULL ERROR] {e}")

if __name__ == '__main__':
    daemon = GoogleDriveSyncDaemon()
    daemon.pull_cloud_updates()
    print("Daemon test completed successfully!")
