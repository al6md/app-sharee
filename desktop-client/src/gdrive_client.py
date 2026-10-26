# -*- coding: utf-8 -*-
"""
Google Drive Client for Desktop App
كامل الصلاحيات مع Google Drive API v3 (15GB)
"""
import os
import io
import sys
import json
import mimetypes
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

def load_gdrive_config():
    """Load Google Drive OAuth credentials from local storage locations or environment"""
    # 1. Environment variables
    if os.environ.get("GDRIVE_REFRESH_TOKEN"):
        return {
            "client_id": os.environ.get("GDRIVE_CLIENT_ID", ""),
            "client_secret": os.environ.get("GDRIVE_CLIENT_SECRET", ""),
            "refresh_token": os.environ.get("GDRIVE_REFRESH_TOKEN", ""),
            "folder_id": os.environ.get("GDRIVE_FOLDER_ID", "1r984fj4btDKUnSfqfJlW2jzrRhVWaROB")
        }

    # 2. Candidate file locations
    candidates = [
        Path.home() / "FileExchangeShared" / ".gdrive_credentials.json",
        Path(os.environ.get("APPDATA", "C:")) / "FileExchange" / "gdrive_credentials.json",
        Path(__file__).parent.parent / "gdrive_credentials.json",
        Path(__file__).parent / "gdrive_credentials.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    return {}

class GoogleDriveClient:
    def __init__(self, root_folder_id=None):
        self.config = load_gdrive_config()
        self.root_folder_id = root_folder_id or self.config.get("folder_id", "1r984fj4btDKUnSfqfJlW2jzrRhVWaROB")
        self.service = None
        self.folder_cache = {}  # name -> id
        self._init_service()

    def _init_service(self):
        try:
            client_id = self.config.get("client_id")
            client_secret = self.config.get("client_secret")
            refresh_token = self.config.get("refresh_token")

            if not (client_id and client_secret and refresh_token):
                print("[GDRIVE] Warning: Google Drive credentials not found")
                return

            creds_data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token"
            }
            creds = Credentials.from_authorized_user_info(creds_data)
            self.service = build('drive', 'v3', credentials=creds)
            print("[GDRIVE] Connected successfully to Google Drive (15GB)")
            self.refresh_folders()
        except Exception as e:
            print(f"[GDRIVE ERROR] Init failed: {e}")

    def is_configured(self):
        return self.service is not None

    def refresh_folders(self):
        if not self.service:
            return []
        try:
            res = self.service.files().list(
                q=f"'{self.root_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="files(id, name, modifiedTime)"
            ).execute()
            folders = res.get('files', [])
            self.folder_cache = {f['name']: f['id'] for f in folders}
            return folders
        except Exception as e:
            print(f"[GDRIVE] Error refreshing folders: {e}")
            return []

    def list_folders(self):
        folders = self.refresh_folders()
        return [{'name': f['name'], 'id': f['id']} for f in folders]

    def create_folder(self, folder_name):
        if not self.service or not folder_name:
            return None
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
            return None

    def delete_folder(self, folder_name):
        if not self.service or not folder_name:
            return False
        try:
            folder_id = self.folder_cache.get(folder_name)
            if not folder_id:
                folders = self.refresh_folders()
                for f in folders:
                    if f['name'] == folder_name:
                        folder_id = f['id']
                        break
            if folder_id:
                self.service.files().update(fileId=folder_id, body={'trashed': True}).execute()
                self.folder_cache.pop(folder_name, None)
                return True
        except Exception as e:
            print(f"[GDRIVE] Error deleting folder {folder_name}: {e}")
        return False

    def list_files(self):
        if not self.service:
            return []
        try:
            folders = self.refresh_folders()
            id_to_name = {f['id']: f['name'] for f in folders}
            id_to_name[self.root_folder_id] = "القسم العام"

            parent_ids = [self.root_folder_id] + [f['id'] for f in folders]
            query_parents = " or ".join([f"'{pid}' in parents" for pid in parent_ids])
            query = f"({query_parents}) and mimeType != 'application/vnd.google-apps.folder' and trashed = false"

            res = self.service.files().list(
                q=query,
                fields="files(id, name, size, modifiedTime, parents)",
                pageSize=200
            ).execute()

            files_list = []
            for item in res.get('files', []):
                pid = item.get('parents', [''])[0]
                dept = id_to_name.get(pid, "القسم العام")
                rel_path = f"{dept}/{item['name']}" if dept != "القسم العام" else item['name']
                files_list.append({
                    'id': item['id'],
                    'file_name': item['name'],
                    'file_path': rel_path,
                    'storage_path': item['id'],
                    'file_size': int(item.get('size', 0)),
                    'updated_at': item.get('modifiedTime', ''),
                    'last_modified_by_name': 'Google Drive',
                    'is_deleted': False
                })
            return files_list
        except Exception as e:
            print(f"[GDRIVE] Error listing files: {e}")
            return []

    def list_accessible_files(self):
        return self.list_files()

    def list_deleted_files(self):
        return []

    def get_folder_permissions(self):
        return {}

    def upload_file(self, local_path, file_name=None, file_path=None, user_name="تطبيق الحاسوب"):
        if not self.service:
            return False, "Service not initialized"
        p = Path(local_path)
        if not p.exists():
            return False, f"File not found: {local_path}"

        fname = file_name or p.name
        dept_name = "القسم العام"
        if file_path and "/" in file_path:
            dept_name = file_path.split("/")[0]
        else:
            try:
                sync_folder = p.parent
                if sync_folder.name and sync_folder.name != "FileExchangeShared":
                    dept_name = sync_folder.name
            except Exception:
                pass

        target_parent = self.create_folder(dept_name) if dept_name != "القسم العام" else self.root_folder_id

        mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'

        try:
            safe_fname = fname.replace("'", "\\'")
            res = self.service.files().list(
                q=f"'{target_parent}' in parents and name = '{safe_fname}' and trashed = false",
                fields="files(id)"
            ).execute()
            existing = res.get('files', [])

            media = MediaFileUpload(str(p), mimetype=mime, resumable=True)
            if existing:
                fid = existing[0]['id']
                self.service.files().update(fileId=fid, media_body=media, fields='id, name').execute()
                print(f"[GDRIVE] Updated: {fname} in {dept_name}")
            else:
                meta = {'name': fname, 'parents': [target_parent]}
                self.service.files().create(body=meta, media_body=media, fields='id, name').execute()
                print(f"[GDRIVE] Uploaded new: {fname} in {dept_name}")
            return True, "تم الرفع بنجاح"
        except Exception as e:
            print(f"[GDRIVE UPLOAD ERROR]: {e}")
            return False, str(e)

    def upload_file_to_storage(self, local_path, storage_dest):
        p = Path(local_path)
        return self.upload_file(local_path, file_name=p.name)[0]

    def download_file(self, file_name, local_dest_path, storage_path=None):
        if not self.service:
            return False, "No service"
        try:
            fid = None
            if storage_path and len(storage_path) > 15 and "/" not in storage_path:
                fid = storage_path
            else:
                safe_name = file_name.replace("'", "\\'")
                res = self.service.files().list(
                    q=f"name = '{safe_name}' and trashed = false",
                    fields="files(id, name)"
                ).execute()
                files = res.get('files', [])
                if files:
                    fid = files[0]['id']

            if not fid:
                return False, f"File {file_name} not found in cloud"

            Path(local_dest_path).parent.mkdir(parents=True, exist_ok=True)
            req = self.service.files().get_media(fileId=fid)
            with open(local_dest_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            return True, "Downloaded successfully"
        except Exception as e:
            print(f"[GDRIVE DOWNLOAD ERROR]: {e}")
            return False, str(e)

    def download_file_from_storage(self, storage_path, local_dest_path):
        p = Path(local_dest_path)
        return self.download_file(p.name, local_dest_path, storage_path=storage_path)[0]

    def delete_file(self, file_path):
        if not self.service or not file_path:
            return False
        try:
            fname = os.path.basename(file_path)
            safe_name = fname.replace("'", "\\'")
            res = self.service.files().list(
                q=f"name = '{safe_name}' and trashed = false",
                fields="files(id)"
            ).execute()
            files = res.get('files', [])
            for f in files:
                self.service.files().update(fileId=f['id'], body={'trashed': True}).execute()
            return True
        except Exception as e:
            print(f"[GDRIVE DELETE ERROR]: {e}")
            return False

    def check_file_lock(self, file_name):
        return False, None
