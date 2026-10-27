# -*- coding: utf-8 -*-
"""
Google Drive Client for Desktop App
كامل الصلاحيات مع Google Drive API v3

الإصدار 4.0 – نسخة محكمة وعالية الأداء:
  • رفع مجزأ قابل للاستئناف الحقيقي (True Resumable Chunked Upload) بحجم شريحة 2MB
    ومؤشر تقدم لحظي (Progress Callback) لا ينقطع حتى مع الملفات الضخمة (300MB - 2GB).
  • رفع مباشر (Single-Shot) للملفات الصغيرة (<= 2MB) لمضاعفة سرعة مزامنة ملفات Word و Excel.
  • حماية كاملة من أخطاء الترميز (UTF-8 Safe Logging) في الوضع الصامت والتنفيذي (windowed exe).
  • مرآة كاملة لشجرة المجلدات وترقيم صفحات شامل (Pagination) واتصال مستقل لكل خيط.
"""
import os
import sys
import json
import time
import socket
import http.client
import urllib.parse
import mimetypes
import threading
from pathlib import Path

import requests

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

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
NETWORK_TIMEOUT = 120                     # ثانية لكل شريحة لمنع انقطاع الاتصال
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024      # 16 ميجابايت لكل شريحة HTTP لمضاعفة سرعة الرفع القصوى (بدلاً من 512KB)
SOCKET_STREAM_BLOCK = 256 * 1024          # 256 كيلوبايت للبث اللحظي عبر المقبس وتحديث المؤشر بسلاسة فائقة
DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024     # 8 ميجابايت لكل شريحة تنزيل
LIST_FIELDS = "nextPageToken, files(id, name, mimeType, size, md5Checksum, modifiedTime, createdTime, parents)"

_IGNORED_EXACT = {"desktop.ini", "thumbs.db", ".ds_store"}
_IGNORED_SUFFIXES = (".tmp", ".laccdb", ".ldb", ".crdownload", ".partial", ".part", "~")


def _safe_log(msg):
    """طباعة آمنة لا تسبب أبداً خطأ UnicodeEncodeError أو تعطل الخيط في النسخة التنفيذية"""
    try:
        out = getattr(sys, "stdout", None)
        if out is not None:
            out.write(str(msg) + "\n")
            out.flush()
    except Exception:
        pass


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
        self._priority_uploads_active = 0
        self._priority_lock = threading.Lock()
        self._token_lock = threading.Lock()
        self._access_token = None
        self._token_expiry = 0.0
        # ذاكرة مسارات المجلدات المعروفة: rel_path -> id
        self._folder_ids = {"": self.root_folder_id}

    def _get_access_token(self, force_refresh=False):
        """جلب رمز وصول OAuth2 نشط ومخزن مؤقتاً لعمليات البث السريع المباشر عبر المقبس"""
        now = time.time()
        with self._token_lock:
            if not force_refresh and self._access_token and now < self._token_expiry - 60:
                return self._access_token
            resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.config["client_id"],
                    "client_secret": self.config["client_secret"],
                    "refresh_token": self.config["refresh_token"],
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
            resp.raise_for_status()
            tok = resp.json()
            self._access_token = tok["access_token"]
            self._token_expiry = now + int(tok.get("expires_in", 3500))
            return self._access_token

    def _stream_resumable_upload_fast(self, file_path_str, fname, parent_id, fid, mime,
                                      total_size, fields, progress_callback=None, is_priority=False):
        """
        بث سريع مباشر (High-Speed Socket Streaming Resumable Upload) إلى Google Drive:
        يرسل شرائح HTTP كبيرة (16MB) عبر اتصال TLS مستمر (Keep-Alive) لتفادي بطء الشرائح الصغيرة،
        مع ضخ البيانات عبر المقبس بكتل (256KB) لتحديث شريط التقدم والسرعة في الوقت الفعلي بسلاسة تامة.
        """
        token = self._get_access_token()
        q_fields = urllib.parse.quote(fields)
        if fid:
            init_url = f"https://www.googleapis.com/upload/drive/v3/files/{fid}?uploadType=resumable&fields={q_fields}"
            init_method = "PATCH"
            init_payload = "{}"
        else:
            init_url = f"https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields={q_fields}"
            init_method = "POST"
            init_payload = json.dumps({"name": fname, "parents": [parent_id]})

        init_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": mime,
            "X-Upload-Content-Length": str(total_size),
        }
        init_resp = requests.request(
            init_method,
            init_url,
            data=init_payload.encode("utf-8"),
            headers=init_headers,
            timeout=30,
        )
        if init_resp.status_code == 401:
            token = self._get_access_token(force_refresh=True)
            init_headers["Authorization"] = f"Bearer {token}"
            init_resp = requests.request(
                init_method,
                init_url,
                data=init_payload.encode("utf-8"),
                headers=init_headers,
                timeout=30,
            )
        if init_resp.status_code == 404 and fid:
            raise FileNotFoundError("404 Target fileId not found on Google Drive")
        init_resp.raise_for_status()
        session_uri = init_resp.headers.get("Location")
        if not session_uri:
            raise RuntimeError("Missing resumable session Location header from Google Drive")

        parsed = urllib.parse.urlsplit(session_uri)
        host = parsed.netloc
        path_query = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path

        def _open_conn():
            c = http.client.HTTPSConnection(host, timeout=NETWORK_TIMEOUT)
            c.connect()
            try:
                c.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                c.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 524288)
            except Exception:
                pass
            return c

        conn = None
        offset = 0
        chunk_errors = 0
        try:
            with open(file_path_str, "rb") as f_obj:
                while offset < total_size:
                    if not is_priority and getattr(self, "_priority_uploads_active", 0) > 0:
                        wait_start = time.time()
                        while getattr(self, "_priority_uploads_active", 0) > 0 and (time.time() - wait_start < 120):
                            time.sleep(0.25)

                    chunk_end_excl = min(offset + UPLOAD_CHUNK_SIZE, total_size)
                    chunk_len = chunk_end_excl - offset

                    try:
                        if conn is None:
                            conn = _open_conn()

                        conn.putrequest("PUT", path_query)
                        conn.putheader("Content-Length", str(chunk_len))
                        conn.putheader("Content-Range", f"bytes {offset}-{chunk_end_excl - 1}/{total_size}")
                        conn.putheader("Content-Type", mime)
                        conn.putheader("Connection", "keep-alive")
                        conn.endheaders()

                        f_obj.seek(offset)
                        remaining = chunk_len
                        sent_in_chunk = 0
                        last_cb_t = 0.0

                        while remaining > 0:
                            read_sz = min(SOCKET_STREAM_BLOCK, remaining)
                            buf = f_obj.read(read_sz)
                            if not buf:
                                break
                            conn.send(buf)
                            sent_in_chunk += len(buf)
                            remaining -= len(buf)

                            if callable(progress_callback):
                                now_t = time.time()
                                if (now_t - last_cb_t) >= 0.10 or remaining == 0:
                                    last_cb_t = now_t
                                    try:
                                        progress_callback(offset + sent_in_chunk, total_size)
                                    except Exception:
                                        pass

                        resp = conn.getresponse()
                        resp_body = resp.read()
                        status_code = resp.status

                        if status_code == 308:
                            chunk_errors = 0
                            range_hdr = resp.getheader("Range") or resp.getheader("range")
                            if range_hdr and "-" in range_hdr:
                                try:
                                    offset = int(range_hdr.split("-")[-1].strip()) + 1
                                except Exception:
                                    offset = chunk_end_excl
                            else:
                                offset = chunk_end_excl
                            if callable(progress_callback):
                                try:
                                    progress_callback(offset, total_size)
                                except Exception:
                                    pass
                        elif status_code in (200, 201):
                            offset = total_size
                            if callable(progress_callback):
                                try:
                                    progress_callback(total_size, total_size)
                                except Exception:
                                    pass
                            return json.loads(resp_body.decode("utf-8")) if resp_body else {"id": fid or ""}
                        elif status_code in (400, 401, 403, 404, 410):
                            raise RuntimeError(f"Google Drive HTTP {status_code}: {resp_body.decode('utf-8', 'ignore')[:200]}")
                        else:
                            raise RuntimeError(f"Unexpected HTTP {status_code}")

                    except Exception as chunk_exc:
                        if conn is not None:
                            try:
                                conn.close()
                            except Exception:
                                pass
                            conn = None

                        msg = str(chunk_exc)
                        if any(code in msg for code in ("HTTP 400", "HTTP 401", "HTTP 403", "HTTP 404", "HTTP 410")):
                            raise
                        chunk_errors += 1
                        if chunk_errors > 8:
                            raise
                        time.sleep(min(1.5 * chunk_errors, 8.0))
                        try:
                            q_resp = requests.put(
                                session_uri,
                                headers={
                                    "Content-Length": "0",
                                    "Content-Range": f"bytes */{total_size}",
                                },
                                timeout=20,
                            )
                            if q_resp.status_code == 308:
                                r_hdr = q_resp.headers.get("Range") or q_resp.headers.get("range")
                                if r_hdr and "-" in r_hdr:
                                    offset = int(r_hdr.split("-")[-1].strip()) + 1
                            elif q_resp.status_code in (200, 201):
                                if callable(progress_callback):
                                    try:
                                        progress_callback(total_size, total_size)
                                    except Exception:
                                        pass
                                return q_resp.json()
                        except Exception:
                            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

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
            raw_http = httplib2.Http(timeout=NETWORK_TIMEOUT)
            # حرج جداً: استبعاد الكود 308 (Resume Incomplete) من أكواد إعادة التوجيه في httplib2
            # لأن Google Drive يستخدم 308 للإشارة لاكتمال رفع الشريحة وليس كإعادة توجيه، وبدونه يفشل رفع أي ملف متعدد الشرائح!
            raw_http.redirect_codes = set(getattr(raw_http, "redirect_codes", ())) - {308}
            authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=raw_http)
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
                time.sleep(1.2 * (attempt + 1))
        raise last_exc

    def _execute_resumable_upload(self, request_factory, total_size, progress_callback=None, is_priority=False):
        """
        رفع مجزأ قابل للاستئناف (Chunked Resumable Upload) يستأنف من نفس الشريحة عند أي انقطاع
        ولا يعيد رفع الملف الضخم من الصفر أبداً، مع منح الأولوية القصوى للرفع التفاعلي للمستخدم.
        """
        max_session_retries = 3
        last_exc = None
        for session_attempt in range(max_session_retries):
            try:
                req = request_factory(self.service)
                if not getattr(req, "resumable", None):
                    meta = req.execute(num_retries=3)
                    if callable(progress_callback):
                        try:
                            progress_callback(total_size, total_size)
                        except Exception:
                            pass
                    return meta

                response = None
                chunk_errors = 0
                while response is None:
                    # إذا كان هناك رفع تفاعلي نشط من المستخدم، يتوقف الرفع الخلفي الضخم مؤقتاً بين الشرائح لمنح كامل سرعة الإنترنت للمستخدم
                    if not is_priority and getattr(self, "_priority_uploads_active", 0) > 0:
                        wait_start = time.time()
                        while getattr(self, "_priority_uploads_active", 0) > 0 and (time.time() - wait_start < 120):
                            time.sleep(0.25)

                    try:
                        status, response = req.next_chunk(num_retries=4)
                        chunk_errors = 0
                        if status is not None and callable(progress_callback):
                            try:
                                progress_callback(int(status.resumable_progress), int(total_size or status.total_size or 1))
                            except Exception:
                                pass
                    except Exception as chunk_exc:
                        http_status = getattr(getattr(chunk_exc, "resp", None), "status", None)
                        try:
                            http_status = int(http_status) if http_status is not None else None
                        except Exception:
                            http_status = None
                        if http_status in (400, 401, 403, 404, 410):
                            raise
                        chunk_errors += 1
                        if chunk_errors > 6:
                            raise
                        time.sleep(min(2.0 * chunk_errors, 10.0))

                if callable(progress_callback):
                    try:
                        progress_callback(total_size, total_size)
                    except Exception:
                        pass
                return response
            except Exception as e:
                last_exc = e
                http_status = getattr(getattr(e, "resp", None), "status", None)
                try:
                    http_status = int(http_status) if http_status is not None else None
                except Exception:
                    http_status = None
                if http_status in (400, 401, 404):
                    raise
                self._reset_thread_service()
                time.sleep(2.0 * (session_attempt + 1))
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
                                    continue
                                existing = new.files.get(rel)
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
                _safe_log(f"[GDRIVE] Snapshot failed: {e}")
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
        """جلب قائمة الملفات المحذوفة في سلة مهملات Google Drive لتوحيد السلة بين الويب والتطبيق"""
        if not self.is_configured():
            return []
        try:
            snap = self.snapshot(max_age=20)
            id_to_rel = {}
            if snap is not None:
                id_to_rel = {fid: rel for rel, fid in snap.folders.items()}
            res = self._execute(lambda s: s.files().list(
                q=f"trashed = true and mimeType != '{FOLDER_MIME}'",
                fields="files(id, name, size, mimeType, modifiedTime, parents)",
                orderBy="modifiedTime desc",
                pageSize=200
            ))
            out = []
            for f in res.get("files", []):
                fname = f.get("name", "")
                if is_ignored_name(fname):
                    continue
                parents = f.get("parents") or []
                parent_id = parents[0] if parents else ""
                rel_folder = id_to_rel.get(parent_id, "")
                rel_path = f"{rel_folder}/{fname}" if rel_folder else fname
                dept = rel_folder.split("/")[0] if rel_folder else "القسم العام"
                out.append({
                    "id": f.get("id"),
                    "server_file_id": f.get("id"),
                    "file_name": fname,
                    "original_rel_path": rel_path,
                    "dept_name": dept,
                    "file_size": int(f.get("size", 0) or 0),
                    "deleted_at": f.get("modifiedTime", ""),
                    "item_type": "file",
                    "is_cloud_trash": True,
                })
            return out
        except Exception as e:
            _safe_log(f"[GDRIVE] Error listing deleted files: {e}")
            return []

    def get_folder_permissions(self, force_refresh=False):
        """قراءة الصلاحيات المفصلة للأقسام المخزنة سحابياً في ملف .sharecoc_permissions.json"""
        if not self.is_configured():
            return getattr(self, "_perms_cache_data", {}) or {}
        now = time.time()
        cache_ts = getattr(self, "_perms_cache_ts", 0)
        if not force_refresh and (now - cache_ts < 8.0) and hasattr(self, "_perms_cache_data"):
            return self._perms_cache_data
        try:
            res = self._execute(lambda s: s.files().list(
                q=f"'{self.root_folder_id}' in parents and name = '.sharecoc_permissions.json' and trashed = false",
                fields="files(id, name, modifiedTime)",
                pageSize=5
            ))
            files = res.get("files", [])
            if not files:
                self._perms_cache_data = {}
                self._perms_cache_ts = now
                return {}
            cfg_id = files[0]["id"]
            raw_bytes = self._execute(lambda s: s.files().get_media(fileId=cfg_id))
            if isinstance(raw_bytes, bytes):
                raw_text = raw_bytes.decode("utf-8", errors="replace")
            else:
                raw_text = str(raw_bytes)
            data = json.loads(raw_text or "{}")
            depts_obj = data.get("departments", data) if isinstance(data, dict) else {}
            normalized = {}
            if isinstance(depts_obj, dict):
                for dept_name, cfg in depts_obj.items():
                    if dept_name in ("version", "updatedAt") or not isinstance(cfg, dict):
                        continue
                    can_upload = bool(cfg.get("canUpload", cfg.get("canWrite", True)))
                    can_edit = bool(cfg.get("canEdit", cfg.get("canWrite", True)))
                    can_delete = bool(cfg.get("canDelete", True))
                    normalized[dept_name] = {
                        "can_view": bool(cfg.get("canView", True)),
                        "can_download": bool(cfg.get("canDownload", True)),
                        "can_upload": can_upload,
                        "can_create_folder": bool(cfg.get("canCreateFolder", can_upload)),
                        "can_edit": can_edit,
                        "can_rename": bool(cfg.get("canRename", can_edit)),
                        "can_move": bool(cfg.get("canMove", can_edit)),
                        "can_delete": can_delete,
                        "can_permanent_delete": bool(cfg.get("canPermanentDelete", can_delete)),
                        "can_write": can_upload or can_edit,
                        "pin_code": str(cfg.get("pinCode", "") or ""),
                    }
            self._perms_cache_data = normalized
            self._perms_cache_ts = now
            return normalized
        except Exception as e:
            _safe_log(f"[GDRIVE] Error reading folder permissions: {e}")
            return getattr(self, "_perms_cache_data", {}) or {}

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
                        _safe_log(f"[GDRIVE] Created folder: {acc}")
                    self._folder_ids[acc] = fid
                parent_id = fid
            self.invalidate()
            return parent_id

    def create_folder(self, folder_name):
        try:
            return self.ensure_folder(folder_name)
        except Exception as e:
            _safe_log(f"[GDRIVE] Failed to create folder {folder_name}: {e}")
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
        if snap is not None and rel_folder in snap.folders:
            return snap.folders.get(rel_folder)
        # البحث المباشر عبر السلسلة إن لم تكن الصورة المسبقة محدثة
        parent_id = self.root_folder_id
        for seg in rel_folder.split("/"):
            fid = self._find_child_folder(parent_id, seg)
            if not fid:
                return None
            parent_id = fid
        with self._folder_lock:
            self._folder_ids[rel_folder] = parent_id
        return parent_id

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
            _safe_log(f"[GDRIVE] Trashed folder: {folder_rel}")
            return True
        except Exception as e:
            _safe_log(f"[GDRIVE] Error deleting folder {folder_rel}: {e}")
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
            _safe_log(f"[GDRIVE] Error renaming folder: {e}")
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
                    user_name="تطبيق الحاسوب", device_name=None, existing_id=None,
                    progress_callback=None, **kwargs):
        """
        رفع ملف إلى نفس مساره النسبي في السحابة (مع إنشاء المجلدات الفرعية).
        يدعم شريط التقدم اللحظي والاستئناف التلقائي للملفات الضخمة.
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

        is_priority = bool(kwargs.get("is_priority", False))
        if is_priority:
            self._priority_uploads_active += 1
        try:
            with self._path_lock(rel or fname):
                try:
                    total_size = p.stat().st_size
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

                    if callable(progress_callback):
                        try:
                            progress_callback(0, max(total_size, 1))
                        except Exception:
                            pass

                    if total_size > 0:
                        try:
                            meta = self._stream_resumable_upload_fast(
                                str(p), fname, parent_id, fid, mime,
                                total_size, fields,
                                progress_callback=progress_callback,
                                is_priority=is_priority
                            )
                        except FileNotFoundError:
                            if existing_id:
                                return self.upload_file(
                                    local_path, file_name=file_name, rel_path=rel,
                                    progress_callback=progress_callback, is_priority=is_priority
                                )
                            raise
                    else:
                        if fid:
                            def req_update(s):
                                media = MediaFileUpload(str(p), mimetype=mime, resumable=False)
                                return s.files().update(fileId=fid, media_body=media, fields=fields)
                            meta = self._execute_resumable_upload(req_update, total_size, progress_callback=progress_callback, is_priority=is_priority)
                        else:
                            def req_create(s):
                                media = MediaFileUpload(str(p), mimetype=mime, resumable=False)
                                return s.files().create(body={'name': fname, 'parents': [parent_id]},
                                                        media_body=media, fields=fields)
                            meta = self._execute_resumable_upload(req_create, total_size, progress_callback=progress_callback, is_priority=is_priority)

                    _safe_log(f"[GDRIVE] Uploaded: {rel} ({total_size} bytes)")
                    self.invalidate()
                    return True, meta
                except Exception as e:
                    self.last_error = str(e)
                    _safe_log(f"[GDRIVE UPLOAD ERROR] {rel}: {e}")
                    return False, str(e)
        finally:
            if is_priority:
                self._priority_uploads_active = max(0, self._priority_uploads_active - 1)

    def upload_file_to_storage(self, local_path, storage_dest):
        dest = norm_rel(storage_dest)
        if dest.startswith("shared/"):
            dest = dest[len("shared/"):]
        return self.upload_file(local_path, rel_path=dest)[0]

    def download_file(self, file_name, local_dest_path, storage_path=None, progress_callback=None):
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
                    downloader = MediaIoBaseDownload(fh, req, chunksize=DOWNLOAD_CHUNK_SIZE)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk(num_retries=4)
                        if status is not None and callable(progress_callback):
                            try:
                                progress_callback(int(status.resumable_progress), int(status.total_size or 1))
                            except Exception:
                                pass
                os.replace(tmp, dest)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass
            _safe_log(f"[GDRIVE] Downloaded: {file_name} -> {dest}")
            return True, "Downloaded successfully"
        except Exception as e:
            self._reset_thread_service()
            _safe_log(f"[GDRIVE DOWNLOAD ERROR]: {e}")
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
        if not file_id or not self.is_configured():
            return False
        self._execute(lambda s: s.files().update(fileId=file_id, body={'trashed': True}, fields='id'))
        self.invalidate()
        return True

    def restore_by_id(self, file_id):
        if not file_id or not self.is_configured():
            return False
        try:
            self._execute(lambda s: s.files().update(fileId=file_id, body={'trashed': False}, fields='id'))
            self.invalidate()
            return True
        except Exception as e:
            _safe_log(f"[GDRIVE RESTORE ERROR]: {e}")
            return False

    def purge_by_id(self, file_id):
        """حذف نهائي لعنصر من سحابة Google Drive باستخدام معرفه"""
        if not file_id or not self.is_configured():
            return False
        try:
            self._execute(lambda s: s.files().delete(fileId=file_id))
            self.invalidate()
            return True
        except Exception as e:
            _safe_log(f"[GDRIVE PURGE BY ID ERROR] {file_id}: {e}")
            return False

    def purge_file(self, rel_path=None, file_id=None, file_name=None):
        """حذف نهائي لملف أو مجلد من Google Drive (سواء كان في السلة أو نشطاً)"""
        if not self.is_configured():
            return False
        try:
            if file_id:
                if self.purge_by_id(file_id):
                    return True
            if rel_path:
                fid = self.resolve_file_id(rel_path) or self.resolve_folder_id(rel_path, use_cache=False)
                if fid and fid != self.root_folder_id:
                    return self.purge_by_id(fid)
            fname = file_name or (rel_path.split("/")[-1] if rel_path else "")
            if fname:
                res = self._execute(lambda s: s.files().list(
                    q=f"trashed = true and name = '{_q_escape(fname)}'",
                    fields="files(id, name)",
                    pageSize=10
                ))
                for f in res.get("files", []):
                    if f.get("id"):
                        self.purge_by_id(f["id"])
                return True
        except Exception as e:
            _safe_log(f"[GDRIVE PURGE FILE ERROR]: {e}")
        return False

    def delete_file(self, file_path, server_file_id=None, **kwargs):
        """نقل ملف أو مجلد إلى سلة محذوفات السحابة حسب معرفه أو مساره الكامل فوراً"""
        if not self.is_configured():
            return False
        try:
            if server_file_id:
                try:
                    self.trash_by_id(server_file_id)
                    _safe_log(f"[GDRIVE] Trashed by ID: {server_file_id} ({file_path})")
                    return True
                except Exception:
                    pass
            if not file_path:
                return False
            fid = self.resolve_file_id(file_path)
            if not fid:
                fid = self.resolve_folder_id(file_path, use_cache=False)
                if fid and fid != self.root_folder_id:
                    return self.delete_folder(file_path)
                return False
            self.trash_by_id(fid)
            _safe_log(f"[GDRIVE] Moved to trash: {file_path}")
            return True
        except Exception as e:
            _safe_log(f"[GDRIVE DELETE ERROR]: {e}")
            return False

    def move_file(self, file_id, new_rel_path):
        """نقل/إعادة تسمية ملف أو مجلد في السحابة مع الحفاظ على معرّفه وسجل إصداراته"""
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

    def move_path_in_cloud(self, old_rel_path, new_rel_path, is_folder=False, server_file_id=None):
        """نقل ملف أو مجلد من مسار نسبي قديم إلى مسار نسبي جديد في Google Drive"""
        if not self.is_configured():
            return False, None
        try:
            old_rel_path = norm_rel(old_rel_path)
            new_rel_path = norm_rel(new_rel_path)
            fid = server_file_id
            if not fid:
                if is_folder:
                    fid = self.resolve_folder_id(old_rel_path, use_cache=False)
                else:
                    fid = self.resolve_file_id(old_rel_path)
            if not fid or fid == self.root_folder_id:
                return False, "Item not found in cloud"
            meta = self.move_file(fid, new_rel_path)
            if is_folder:
                self._forget_folder_prefix(old_rel_path)
            self.invalidate()
            _safe_log(f"[GDRIVE] Moved in cloud: {old_rel_path} -> {new_rel_path}")
            return True, meta
        except Exception as e:
            _safe_log(f"[GDRIVE MOVE ERROR] {old_rel_path} -> {new_rel_path}: {e}")
            return False, str(e)

    def poll_changes_since_last(self):
        """فحص خفيف وسريع عبر Google Drive Changes API لمعرفة ما إذا حدث أي تعديل أو حذف أو نقل من الويب أو الأجهزة الأخرى"""
        if not self.is_configured():
            return False
        try:
            token = getattr(self, "_changes_page_token", None)
            if not token:
                res = self._execute(lambda s: s.changes().getStartPageToken())
                self._changes_page_token = res.get("startPageToken")
                return False
            res = self._execute(lambda s: s.changes().list(
                pageToken=token,
                spaces="drive",
                includeItemsFromAllDrives=False,
                supportsAllDrives=False,
                fields="newStartPageToken, nextPageToken, changes(fileId, removed, file(id, name, trashed, parents, modifiedTime))",
                pageSize=100
            ))
            changes = res.get("changes", [])
            new_token = res.get("newStartPageToken") or res.get("nextPageToken")
            if new_token:
                self._changes_page_token = new_token
            if changes:
                self.invalidate()
                return True
            return False
        except Exception as e:
            _safe_log(f"[GDRIVE CHANGES POLL ERROR]: {e}")
            return False

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
            _safe_log(f"[GDRIVE RENAME ERROR]: {e}")
            return False
