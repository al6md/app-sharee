# -*- coding: utf-8 -*-
"""
Google Drive Client for Desktop App
كامل الصلاحيات مع Google Drive API v3

الإصدار 3.0 – إعادة بناء شاملة:
  • مرآة كاملة لشجرة المجلدات (مجلدات فرعية بأي عمق) بدلاً من المستوى الأول فقط.
  • ترقيم صفحات كامل (Pagination) فلا يختفي أي ملف مهما بلغ عدد الملفات.
  • اتصال مستقل لكل خيط (Thread-local) بدلاً من قفل عام يجمّد الواجهة أثناء الرفع والتنزيل.
  • مهلة زمنية للشبكة (Timeout) تمنع التعليق اللانهائي.
  • عند فشل الاتصال تُعاد None (وليس قائمة فارغة) حتى لا يُفسَّر الفشل على أنه "حُذفت كل الملفات".
"""
import os
import sys
import json
import time
import mimetypes
import threading
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

try:
    import httplib2
    import google_auth_httplib2
except Exception:  # pragma: no cover
    httplib2 = None
    google_auth_httplib2 = None

DEFAULT_ROOT_FOLDER_ID = "1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB"
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
NETWORK_TIMEOUT = 60  # ثانية
LIST_FIELDS = "nextPageToken, files(id, name, mimeType, size, md5Checksum, modifiedTime, createdTime, parents)"

_IGNORED_EXACT = {"desktop.ini", "thumbs.db", ".ds_store"}
_IGNORED_SUFFIXES = (".tmp", ".laccdb", ".ldb", ".crdownload", ".partial", "~")


def is_ignored_name(name):
    """ملفات مؤقتة/نظامية لا يجب مزامنتها أبداً (ملفات قفل Office، ملفات مؤقتة...)"""
    if not name:
        return True
    low = name.lower()
    if low in _IGNORED_EXACT:
        return True
    if name.startswith("~$") or name.startswith(".") or name.startswith("~WRL"):
        return True
    return low.endswith(_IGNORED_SUFFIXES)


def norm_rel(path):
    """توحيد صيغة المسار النسبي: فواصل / وبدون فواصل في البداية أو النهاية"""
    if path is None:
        return ""
    p = str(path).replace("\\", "/").strip().strip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return "" if p == "." else p


def _q_escape(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


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
            "folder_id": os.environ.get("GDRIVE_FOLDER_ID", DEFAULT_ROOT_FOLDER_ID)
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


class DriveSnapshot:
    """صورة كاملة لشجرة السحابة في لحظة معينة"""

    def __init__(self, root_id):
        self.root_id = root_id
        self.folders = {"": root_id}          # rel_folder_path -> folder id
        self.folder_meta = {}                 # rel_folder_path -> metadata
        self.id_to_path = {root_id: ""}       # folder id -> rel path
        self.files = {}                       # rel_file_path -> metadata
        self.file_ids = {}                    # file id -> rel_file_path
        self.taken_at = time.time()


class GoogleDriveClient:
    def __init__(self, root_folder_id=None):
        self.config = load_gdrive_config()
        self.root_folder_id = root_folder_id or self.config.get("folder_id", DEFAULT_ROOT_FOLDER_ID)
        self.sync_folder = None  # يُضبط من main.py لتحديد المسارات النسبية تلقائياً
        self._local = threading.local()
        self._snapshot_lock = threading.Lock()
        self._folder_lock = threading.RLock()
        self._path_locks = {}
        self._path_locks_guard = threading.Lock()
        self._snapshot = None
        self.last_error = None
        # ذاكرة مسارات المجلدات المعروفة: rel_path -> id
        self._folder_ids = {"": self.root_folder_id}

    # ------------------------------------------------------------------ #
    # الاتصال
    # ------------------------------------------------------------------ #
    def is_configured(self):
        """فحص فوري بدون أي اتصال شبكي (آمن للاستدعاء من واجهة المستخدم)"""
        c = self.config
        return bool(c.get("client_id") and c.get("client_secret") and c.get("refresh_token"))

    @property
    def service(self):
        """خدمة Drive مستقلة لكل خيط – httplib2 غير آمن للمشاركة بين الخيوط"""
        svc = getattr(self._local, "service", None)
        if svc is not None:
            return svc
        if not self.is_configured():
            return None
        creds = Credentials.from_authorized_user_info({
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": self.config["refresh_token"],
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        if httplib2 is not None and google_auth_httplib2 is not None:
            authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=NETWORK_TIMEOUT))
            svc = build('drive', 'v3', http=authed_http, cache_discovery=False)
        else:
            svc = build('drive', 'v3', credentials=creds, cache_discovery=False)
        self._local.service = svc
        return svc

    def _reset_thread_service(self):
        self._local.service = None

    def _execute(self, request_factory, retries=3):
        """تنفيذ طلب مع إعادة المحاولة عند أخطاء الشبكة المؤقتة"""
        last_exc = None
        for attempt in range(retries):
            try:
                return request_factory(self.service).execute(num_retries=2)
            except Exception as e:
                last_exc = e
                status = getattr(getattr(e, "resp", None), "status", None)
                try:
                    status = int(status) if status is not None else None
                except Exception:
                    status = None
                if status in (400, 401, 404):
                    raise
                self._reset_thread_service()
                time.sleep(1.5 * (attempt + 1))
        raise last_exc

    def _path_lock(self, key):
        with self._path_locks_guard:
            lk = self._path_locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._path_locks[key] = lk
            return lk

    # ------------------------------------------------------------------ #
    # قراءة الشجرة الكاملة
    # ------------------------------------------------------------------ #
    def _list_children(self, parent_ids):
        """جلب كل العناصر داخل مجموعة من المجلدات مع ترقيم الصفحات الكامل"""
        q_parents = " or ".join(f"'{pid}' in parents" for pid in parent_ids)
        query = f"({q_parents}) and trashed = false"
        items = []
        page_token = None
        while True:
            res = self._execute(lambda s: s.files().list(
                q=query, fields=LIST_FIELDS, pageSize=1000, pageToken=page_token,
                spaces="drive"))
            items.extend(res.get("files", []))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return items

    def snapshot(self, force=False, max_age=8):
        """
        بناء صورة كاملة لشجرة السحابة (كل المجلدات الفرعية وكل الملفات).
        تُرجع None عند فشل الاتصال – لا تُرجع أبداً صورة ناقصة.
        """
        if not self.is_configured():
            return None
        snap = self._snapshot
        if not force and snap is not None and (time.time() - snap.taken_at) < max_age:
            return snap

        with self._snapshot_lock:
            snap = self._snapshot
            if not force and snap is not None and (time.time() - snap.taken_at) < max_age:
                return snap
            try:
                new = DriveSnapshot(self.root_folder_id)
                level = [self.root_folder_id]
                visited = {self.root_folder_id}
                while level:
                    next_level = []
                    for i in range(0, len(level), 25):
                        chunk = level[i:i + 25]
                        for item in self._list_children(chunk):
                            parents = item.get("parents") or []
                            parent_path = None
                            for pid in parents:
                                if pid in new.id_to_path:
                                    parent_path = new.id_to_path[pid]
                                    break
                            if parent_path is None:
                                continue
                            name = item.get("name", "")
                            rel = f"{parent_path}/{name}" if parent_path else name
                            if item.get("mimeType") == FOLDER_MIME:
                                if item["id"] in visited:
                                    continue
                                visited.add(item["id"])
                                new.id_to_path[item["id"]] = rel
                                if rel not in new.folders:
                                    new.folders[rel] = item["id"]
                                    new.folder_meta[rel] = item
                                next_level.append(item["id"])
                            else:
                                if is_ignored_name(name):
                                    continue
                                if str(item.get("mimeType", "")).startswith(GOOGLE_NATIVE_PREFIX):
                                    continue  # مستندات Google الأصلية لا يمكن تنزيلها كملفات
                                existing = new.files.get(rel)
                                # عند وجود نسختين بنفس المسار نعتمد الأحدث
                                if existing is None or item.get("modifiedTime", "") > existing.get("modifiedTime", ""):
                                    new.files[rel] = item
                    level = next_level
                new.file_ids = {meta["id"]: rel for rel, meta in new.files.items()}
                new.taken_at = time.time()
                self._snapshot = new
                with self._folder_lock:
                    self._folder_ids.update(new.folders)
                self.last_error = None
                return new
            except Exception as e:
                self.last_error = str(e)
                print(f"[GDRIVE] Snapshot failed: {e}")
                return None

    def invalidate(self):
        snap = self._snapshot
        if snap is not None:
            snap.taken_at = 0

    # ------------------------------------------------------------------ #
    # واجهات متوافقة مع الإصدارات السابقة (gui.py / local_bridge.py)
    # ------------------------------------------------------------------ #
    def refresh_folders(self, force=False):
        snap = self.snapshot(force=force, max_age=15)
        if snap is None:
            return []
        return [{"id": fid, "name": rel.split("/")[-1], "path": rel}
                for rel, fid in snap.folders.items() if rel]

    def list_folders(self):
        """الأقسام (المجلدات من المستوى الأول)"""
        snap = self.snapshot(max_age=15)
        if snap is None:
            return []
        return [{"name": rel, "id": fid} for rel, fid in sorted(snap.folders.items()) if rel and "/" not in rel]

    def list_all_folder_paths(self):
        snap = self.snapshot(max_age=15)
        if snap is None:
            return []
        return sorted(rel for rel in snap.folders if rel)

    def list_files(self, force=False):
        snap = self.snapshot(force=force)
        if snap is None:
            return []
        out = []
        for rel, item in snap.files.items():
            folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
            dept = rel.split("/")[0] if "/" in rel else "القسم العام"
            out.append({
                'id': item['id'],
                'file_name': item['name'],
                'file_path': rel,
                'department': dept,
                'folder': folder or dept,
                'storage_path': item['id'],
                'file_size': int(item.get('size', 0) or 0),
                'md5': item.get('md5Checksum'),
                'updated_at': item.get('modifiedTime', ''),
                'last_modified_by_name': 'Google Drive',
                'is_deleted': False
            })
        return out

    def list_accessible_files(self):
        return self.list_files()

    def list_deleted_files(self):
        return []

    def get_folder_permissions(self):
        return {}

    def check_file_lock(self, file_name):
        return False, None

    def get_file_by_name(self, file_name, folder=None):
        snap = self.snapshot(max_age=30)
        if snap is None or not file_name:
            return None
        folder = norm_rel(folder) if folder and folder != "__ALL__" else None
        best = None
        for rel, item in snap.files.items():
            if item.get("name") != file_name:
                continue
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            if folder is not None and parent == folder:
                best = (rel, item)
                break
            if best is None:
                best = (rel, item)
        if not best:
            return None
        rel, item = best
        return {'id': item['id'], 'file_name': item['name'], 'file_path': rel,
                'storage_path': item['id'], 'file_size': int(item.get('size', 0) or 0)}

    # ------------------------------------------------------------------ #
    # المجلدات
    # ------------------------------------------------------------------ #
    def _find_child_folder(self, parent_id, name):
        res = self._execute(lambda s: s.files().list(
            q=f"'{parent_id}' in parents and name = '{_q_escape(name)}' and mimeType = '{FOLDER_MIME}' and trashed = false",
            fields="files(id, name, createdTime)", orderBy="createdTime", pageSize=10))
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def ensure_folder(self, rel_folder):
        """التأكد من وجود مسار مجلدات كامل (مثل: قسم/مجلد/فرعي) وإنشاؤه عند الحاجة"""
        rel_folder = norm_rel(rel_folder)
        if not rel_folder:
            return self.root_folder_id
        with self._folder_lock:
            cached = self._folder_ids.get(rel_folder)
            if cached:
                return cached
            parent_id = self.root_folder_id
            acc = ""
            for seg in rel_folder.split("/"):
                acc = f"{acc}/{seg}" if acc else seg
                fid = self._folder_ids.get(acc)
                if not fid:
                    fid = self._find_child_folder(parent_id, seg)
                    if not fid:
                        created = self._execute(lambda s: s.files().create(
                            body={'name': seg, 'mimeType': FOLDER_MIME, 'parents': [parent_id]},
                            fields='id, name'))
                        fid = created['id']
                        print(f"[GDRIVE] Created folder: {acc}")
                    self._folder_ids[acc] = fid
                parent_id = fid
            self.invalidate()
            return parent_id

    def create_folder(self, folder_name):
        try:
            return self.ensure_folder(folder_name)
        except Exception as e:
            print(f"[GDRIVE] Failed to create folder {folder_name}: {e}")
            return None

    def resolve_folder_id(self, rel_folder, use_cache=True):
        rel_folder = norm_rel(rel_folder)
        if not rel_folder:
            return self.root_folder_id
        if use_cache:
            with self._folder_lock:
                if rel_folder in self._folder_ids:
                    return self._folder_ids[rel_folder]
        snap = self.snapshot(max_age=5)
        if snap is not None:
            return snap.folders.get(rel_folder)
        return None

    def _forget_folder_prefix(self, rel_folder):
        with self._folder_lock:
            prefix = rel_folder + "/"
            for k in list(self._folder_ids.keys()):
                if k == rel_folder or k.startswith(prefix):
                    self._folder_ids.pop(k, None)

    def delete_folder(self, folder_rel):
        folder_rel = norm_rel(folder_rel)
        if not folder_rel or not self.is_configured():
            return False
        try:
            fid = self.resolve_folder_id(folder_rel, use_cache=False)
            if not fid or fid == self.root_folder_id:
                return False
            self._execute(lambda s: s.files().update(fileId=fid, body={'trashed': True}, fields='id'))
            self._forget_folder_prefix(folder_rel)
            self.invalidate()
            print(f"[GDRIVE] Trashed folder: {folder_rel}")
            return True
        except Exception as e:
            print(f"[GDRIVE] Error deleting folder {folder_rel}: {e}")
            return False

    def rename_folder(self, old_rel, new_name):
        old_rel = norm_rel(old_rel)
        new_name = norm_rel(new_name).split("/")[-1]
        if not old_rel or not new_name:
            return False
        try:
            fid = self.resolve_folder_id(old_rel, use_cache=False)
            if not fid or fid == self.root_folder_id:
                return False
            self._execute(lambda s: s.files().update(fileId=fid, body={'name': new_name}, fields='id'))
            self._forget_folder_prefix(old_rel)
            self.invalidate()
            return True
        except Exception as e:
            print(f"[GDRIVE] Error renaming folder: {e}")
            return False

    # ------------------------------------------------------------------ #
    # الملفات
    # ------------------------------------------------------------------ #
    def _rel_from_local(self, local_path):
        if self.sync_folder:
            try:
                return norm_rel(Path(local_path).resolve().relative_to(Path(self.sync_folder).resolve()))
            except Exception:
                pass
        return Path(local_path).name

    def upload_file(self, local_path, file_name=None, file_path=None, rel_path=None,
                    user_name="تطبيق الحاسوب", device_name=None, existing_id=None, **kwargs):
        """
        رفع ملف إلى نفس مساره النسبي في السحابة (مع إنشاء المجلدات الفرعية).
        تُرجع (True, file_metadata) عند النجاح أو (False, رسالة الخطأ).
        """
        if not self.is_configured():
            return False, "Service not configured"
        p = Path(local_path)
        if not p.exists() or not p.is_file():
            return False, f"File not found: {local_path}"

        rel = norm_rel(rel_path or file_path) or self._rel_from_local(p)
        fname = rel.split("/")[-1] if rel else (file_name or p.name)
        if file_name and not (rel_path or file_path):
            fname = file_name
        if is_ignored_name(fname):
            return True, {"ignored": True}
        parent_rel = rel.rsplit("/", 1)[0] if "/" in rel else ""

        with self._path_lock(rel or fname):
            try:
                parent_id = self.ensure_folder(parent_rel)
                mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
                fid = existing_id
                if not fid:
                    res = self._execute(lambda s: s.files().list(
                        q=f"'{parent_id}' in parents and name = '{_q_escape(fname)}' and mimeType != '{FOLDER_MIME}' and trashed = false",
                        fields="files(id, modifiedTime)", orderBy="modifiedTime desc", pageSize=10))
                    found = res.get('files', [])
                    fid = found[0]['id'] if found else None

                fields = 'id, name, size, md5Checksum, modifiedTime, parents'
                if fid:
                    def req(s):
                        media = MediaFileUpload(str(p), mimetype=mime, resumable=True, chunksize=8 * 1024 * 1024)
                        return s.files().update(fileId=fid, media_body=media, fields=fields)
                    try:
                        meta = self._execute(req)
                    except Exception as e:
                        if existing_id and "404" in str(e):
                            return self.upload_file(local_path, file_name=file_name, rel_path=rel)
                        raise
                else:
                    def req(s):
                        media = MediaFileUpload(str(p), mimetype=mime, resumable=True, chunksize=8 * 1024 * 1024)
                        return s.files().create(body={'name': fname, 'parents': [parent_id]},
                                                media_body=media, fields=fields)
                    meta = self._execute(req)
                print(f"[GDRIVE] Uploaded: {rel}")
                self.invalidate()
                return True, meta
            except Exception as e:
                print(f"[GDRIVE UPLOAD ERROR] {rel}: {e}")
                return False, str(e)

    def upload_file_to_storage(self, local_path, storage_dest):
        dest = norm_rel(storage_dest)
        if dest.startswith("shared/"):
            dest = dest[len("shared/"):]
        return self.upload_file(local_path, rel_path=dest)[0]

    def download_file(self, file_name, local_dest_path, storage_path=None):
        """تنزيل آمن إلى ملف مؤقت ثم استبدال ذري – لا تظهر ملفات نصف منزّلة أبداً"""
        if not self.is_configured():
            return False, "No service"
        try:
            fid = None
            if storage_path and len(storage_path) > 15 and "/" not in storage_path and "." not in storage_path:
                fid = storage_path
            else:
                info = self.get_file_by_name(file_name)
                if info:
                    fid = info['id']
            if not fid:
                return False, f"File {file_name} not found in cloud"

            dest = Path(local_dest_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.parent / f".sharecoc-dl-{os.getpid()}-{threading.get_ident()}-{int(time.time()*1000)}.part"
            try:
                req = self.service.files().get_media(fileId=fid)
                with open(tmp, 'wb') as fh:
                    downloader = MediaIoBaseDownload(fh, req, chunksize=8 * 1024 * 1024)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk(num_retries=3)
                os.replace(tmp, dest)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass
            print(f"[GDRIVE] Downloaded: {file_name} -> {dest}")
            return True, "Downloaded successfully"
        except Exception as e:
            self._reset_thread_service()
            print(f"[GDRIVE DOWNLOAD ERROR]: {e}")
            return False, str(e)

    def download_file_from_storage(self, storage_path, local_dest_path):
        p = Path(local_dest_path)
        return self.download_file(p.name, local_dest_path, storage_path=storage_path)[0]

    def resolve_file_id(self, rel_path):
        rel_path = norm_rel(rel_path)
        if not rel_path:
            return None
        snap = self.snapshot(max_age=5)
        if snap is not None and rel_path in snap.files:
            return snap.files[rel_path]["id"]
        parent_rel = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
        name = rel_path.split("/")[-1]
        parent_id = self.resolve_folder_id(parent_rel)
        if not parent_id:
            return None
        res = self._execute(lambda s: s.files().list(
            q=f"'{parent_id}' in parents and name = '{_q_escape(name)}' and mimeType != '{FOLDER_MIME}' and trashed = false",
            fields="files(id)", pageSize=10))
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def trash_by_id(self, file_id):
        self._execute(lambda s: s.files().update(fileId=file_id, body={'trashed': True}, fields='id'))
        self.invalidate()
        return True

    def delete_file(self, file_path, **kwargs):
        """نقل ملف إلى سلة محذوفات السحابة حسب مساره الكامل (وليس بالاسم في كل الدرايف)"""
        if not self.is_configured() or not file_path:
            return False
        try:
            fid = self.resolve_file_id(file_path)
            if not fid:
                fid = self.resolve_folder_id(file_path, use_cache=False)
                if fid and fid != self.root_folder_id:
                    return self.delete_folder(file_path)
                return False
            self.trash_by_id(fid)
            print(f"[GDRIVE] Moved to trash: {file_path}")
            return True
        except Exception as e:
            print(f"[GDRIVE DELETE ERROR]: {e}")
            return False

    def move_file(self, file_id, new_rel_path):
        """نقل/إعادة تسمية ملف في السحابة مع الحفاظ على معرّفه وسجل إصداراته"""
        new_rel_path = norm_rel(new_rel_path)
        new_name = new_rel_path.split("/")[-1]
        new_parent_rel = new_rel_path.rsplit("/", 1)[0] if "/" in new_rel_path else ""
        new_parent_id = self.ensure_folder(new_parent_rel)
        cur = self._execute(lambda s: s.files().get(fileId=file_id, fields="parents"))
        old_parents = ",".join(cur.get("parents", []))
        kwargs = {"fileId": file_id, "body": {"name": new_name},
                  "fields": "id, name, size, md5Checksum, modifiedTime, parents"}
        if new_parent_id not in cur.get("parents", []):
            kwargs["addParents"] = new_parent_id
            kwargs["removeParents"] = old_parents
        meta = self._execute(lambda s: s.files().update(**kwargs))
        self.invalidate()
        return meta

    def rename_file(self, old_file_path, new_name):
        if not self.is_configured() or not old_file_path or not new_name:
            return False
        try:
            fid = self.resolve_file_id(old_file_path)
            if not fid:
                return False
            old = norm_rel(old_file_path)
            parent = old.rsplit("/", 1)[0] if "/" in old else ""
            self.move_file(fid, f"{parent}/{new_name}" if parent else new_name)
            return True
        except Exception as e:
            print(f"[GDRIVE RENAME ERROR]: {e}")
            return False
