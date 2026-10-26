# -*- coding: utf-8 -*-
"""
Google Drive Client for Desktop App
كامل الصلاحيات مع Google Drive API v3 (15GB)
متوافق بنسبة 100% مع sync_engine.py و gui.py و local_bridge.py
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
    """Load Google Drive OAuth credentials from bundle, environment, or local paths"""
    # 1. Check frozen PyInstaller bundle (_MEIPASS)
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        meipass_p = Path(sys._MEIPASS) / "gdrive_credentials.json"
        if meipass_p.exists():
            try:
                with open(meipass_p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    # 2. Check next to executable
    if getattr(sys, 'frozen', False):
        exe_dir_p = Path(sys.executable).parent / "gdrive_credentials.json"
        if exe_dir_p.exists():
            try:
                with open(exe_dir_p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    # 3. Environment variables
    if os.environ.get("GDRIVE_REFRESH_TOKEN"):
        return {
            "client_id": os.environ.get("GDRIVE_CLIENT_ID", ""),
            "client_secret": os.environ.get("GDRIVE_CLIENT_SECRET", ""),
            "refresh_token": os.environ.get("GDRIVE_REFRESH_TOKEN", ""),
            "folder_id": os.environ.get("GDRIVE_FOLDER_ID", "1r984fj4btDKUnSfqfJlW2jzrRhVWaROB")
        }

    # 4. Standard local storage paths
    candidates = [
        Path(os.environ.get("APPDATA", "C:")) / "FileExchange" / "gdrive_credentials.json",
        Path.home() / "FileExchangeShared" / ".gdrive_credentials.json",
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
            self.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
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
            return self.root_folder_id
        if folder_name in self.folder_cache:
            return self.folder_cache[folder_name]
        try:
            safe_name = folder_name.replace("'", "\\'")
            res = self.service.files().list(
                q=f"'{self.root_folder_id}' in parents and name = '{safe_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="files(id, name)"
            ).execute()
            existing = res.get('files', [])
            if existing:
                self.folder_cache[folder_name] = existing[0]['id']
                return existing[0]['id']

            meta = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [self.root_folder_id]
            }
            fld = self.service.files().create(body=meta, fields='id, name').execute()
            self.folder_cache[folder_name] = fld['id']
            print(f"[GDRIVE] Created folder: {folder_name} ({fld['id']})")
            return fld['id']
        except Exception as e:
            print(f"[GDRIVE] Failed to create folder {folder_name}: {e}")
            return self.root_folder_id

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
                print(f"[GDRIVE] Trashed folder: {folder_name}")
                return True
        except Exception as e:
            print(f"[GDRIVE] Error deleting folder {folder_name}: {e}")
        return False

    def rename_folder(self, old_name, new_name):
        if not self.service or not old_name or not new_name:
            return False
        try:
            folder_id = self.folder_cache.get(old_name)
            if not folder_id:
                folders = self.refresh_folders()
                for f in folders:
                    if f['name'] == old_name:
                        folder_id = f['id']
                        break
            if folder_id:
                self.service.files().update(fileId=folder_id, body={'name': new_name}).execute()
                self.folder_cache.pop(old_name, None)
                self.folder_cache[new_name] = folder_id
                print(f"[GDRIVE] Renamed folder {old_name} -> {new_name}")
                return True
        except Exception as e:
            print(f"[GDRIVE] Error renaming folder: {e}")
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
                pid = item.get('parents', [''])[0] if item.get('parents') else ''
                dept = id_to_name.get(pid, "القسم العام")
                rel_path = f"{dept}/{item['name']}"
                files_list.append({
                    'id': item['id'],
                    'file_name': item['name'],
                    'file_path': rel_path,
                    'department': dept,
                    'folder': dept,
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
        if not self.service:
            return []
        try:
            # جلب أسماء الملفات النشطة أولاً لمنع اعتبار أي ملف نشط كمحذوف نهائياً
            active_files = self.list_files()
            active_names = {f['file_name'].strip().lower() for f in active_files}

            res = self.service.files().list(
                q="trashed = true and mimeType != 'application/vnd.google-apps.folder'",
                fields="files(id, name, size, modifiedTime, parents)",
                pageSize=100
            ).execute()
            deleted = []
            folders = self.folder_cache or {}
            id_to_name = {v: k for k, v in folders.items()}
            for item in res.get('files', []):
                # إذا كان الملف نشطاً في السحابة لا نعتبره محذوفاً إطلاقاً
                if item['name'].strip().lower() in active_names:
                    continue
                pid = item.get('parents', [''])[0] if item.get('parents') else ''
                dept = id_to_name.get(pid, '')
                rel_path = f"{dept}/{item['name']}" if dept else item['name']
                deleted.append({
                    'id': item['id'],
                    'file_name': item['name'],
                    'file_path': rel_path,
                    'storage_path': item['id'],
                    'file_size': int(item.get('size', 0)),
                    'updated_at': item.get('modifiedTime', '')
                })
            return deleted
        except Exception as e:
            print(f"[GDRIVE] Error listing deleted files: {e}")
            return []

    def get_folder_permissions(self):
        return {}

    def check_file_lock(self, file_name):
        return False, None

    def get_file_by_name(self, file_name):
        if not self.service or not file_name:
            return None
        try:
            safe_name = file_name.replace("'", "\\'")
            res = self.service.files().list(
                q=f"name = '{safe_name}' and trashed = false",
                fields="files(id, name, size, modifiedTime, parents)"
            ).execute()
            files = res.get('files', [])
            if files:
                f = files[0]
                return {
                    'id': f['id'],
                    'file_name': f['name'],
                    'storage_path': f['id'],
                    'file_size': int(f.get('size', 0))
                }
        except Exception as e:
            print(f"[GDRIVE] Error get_file_by_name: {e}")
        return None

    def upload_file(self, local_path, file_name=None, file_path=None, rel_path=None, user_name="تطبيق الحاسوب", device_name=None, **kwargs):
        """رفع أو تحديث ملف على Google Drive مع تحديد المجلد المناسب بدقة"""
        if not self.service:
            return False, "Service not initialized"
        p = Path(local_path)
        if not p.exists():
            return False, f"File not found: {local_path}"

        r_path = rel_path or file_path or ""
        fname = file_name or (os.path.basename(r_path) if r_path else p.name)

        # تحديد اسم القسم من المسار النسبي أو مجلد الملف
        dept_name = "القسم العام"
        clean_rel = r_path.replace("\\", "/").strip("/")
        if "/" in clean_rel:
            parts = clean_rel.split("/")
            if len(parts) > 1 and parts[0] != "FileExchangeShared":
                dept_name = parts[0]
        else:
            try:
                parent_name = p.parent.name
                if parent_name and parent_name != "FileExchangeShared":
                    dept_name = parent_name
            except Exception:
                pass

        target_parent = self.create_folder(dept_name)
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
                print(f"[GDRIVE] Updated existing file: {fname} in {dept_name}")
            else:
                meta = {'name': fname, 'parents': [target_parent]}
                self.service.files().create(body=meta, media_body=media, fields='id, name').execute()
                print(f"[GDRIVE] Uploaded new file: {fname} in {dept_name}")
            return True, "تم الرفع بنجاح"
        except Exception as e:
            print(f"[GDRIVE UPLOAD ERROR]: {e}")
            return False, str(e)

    def upload_file_to_storage(self, local_path, storage_dest):
        p = Path(local_path)
        return self.upload_file(local_path, file_name=p.name, rel_path=storage_dest)[0]

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
            print(f"[GDRIVE] Downloaded: {file_name} -> {local_dest_path}")
            return True, "Downloaded successfully"
        except Exception as e:
            print(f"[GDRIVE DOWNLOAD ERROR]: {e}")
            return False, str(e)

    def download_file_from_storage(self, storage_path, local_dest_path):
        p = Path(local_dest_path)
        return self.download_file(p.name, local_dest_path, storage_path=storage_path)[0]

    def delete_file(self, file_path, **kwargs):
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
                print(f"[GDRIVE] Moved to trash: {fname} ({f['id']})")
            return True
        except Exception as e:
            print(f"[GDRIVE DELETE ERROR]: {e}")
            return False

    def rename_file(self, old_file_path, new_name):
        if not self.service or not old_file_path or not new_name:
            return False
        try:
            fname = os.path.basename(old_file_path)
            safe_name = fname.replace("'", "\\'")
            res = self.service.files().list(
                q=f"name = '{safe_name}' and trashed = false",
                fields="files(id)"
            ).execute()
            files = res.get('files', [])
            for f in files:
                self.service.files().update(fileId=f['id'], body={'name': new_name}).execute()
                print(f"[GDRIVE] Renamed {fname} -> {new_name}")
            return True
        except Exception as e:
            print(f"[GDRIVE RENAME ERROR]: {e}")
            return False
