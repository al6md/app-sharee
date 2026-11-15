# -*- coding: utf-8 -*-
"""
Share COC Cloud Client for Desktop App
كامل الصلاحيات مع خادم Share COC المحلي الدائم (https://share.162.35.16.252.sslip.io)

الإصدار 5.0 – نسخة السحابة المحلية المستقلة:
  • اتصال مباشر بواجهات /api/drive/files و /api/drive/stream و /api/drive/permissions.
  • رفع مباشر للملفات الصغيرة (<= 8MB) ورفع مجزأ قابل للاستئناف (INIT_UPLOAD / UPLOAD_CHUNK) للملفات الضخمة.
  • تنزيل متدفق آمن إلى ملف مؤقت ثم استبدال ذري متوافق مع أقفال Microsoft Office / Access.
  • استكشاف تغيّرات السحابة السريع (/api/drive/files?changes=1&sig=...) وتوليد Delta Changes فوري.
  • حماية كاملة من أخطاء الترميز (UTF-8 Safe Logging) في الوضع الصامت والتنفيذي (windowed exe).
"""
import os
import sys
import re
import json
import time
import shutil
import hashlib
import mimetypes
import threading
import urllib.parse
from pathlib import Path

import requests


def _ensure_valid_ca_bundle():
    """ضمان توفر شهادة TLS صالحة في مجلد دائم حتى لا تتعطل جلسات requests في تطبيق PyInstaller"""
    persistent_cacert = Path(os.environ.get("APPDATA", Path.home())) / "FileExchange" / "cacert.pem"
    try:
        persistent_cacert.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    certifi_path = None
    try:
        import certifi
        c_path = certifi.where()
        if c_path and os.path.isfile(c_path) and os.path.getsize(c_path) > 10000:
            certifi_path = c_path
    except Exception:
        certifi_path = None

    if certifi_path:
        try:
            need_copy = (
                not persistent_cacert.is_file()
                or persistent_cacert.stat().st_size != os.path.getsize(certifi_path)
            )
            if need_copy:
                tmp_cacert = persistent_cacert.with_suffix(".pem.tmp")
                shutil.copy2(certifi_path, tmp_cacert)
                os.replace(tmp_cacert, persistent_cacert)
        except Exception:
            pass

    if persistent_cacert.is_file() and persistent_cacert.stat().st_size > 10000:
        ca_str = str(persistent_cacert)
        os.environ["REQUESTS_CA_BUNDLE"] = ca_str
        os.environ["SSL_CERT_FILE"] = ca_str
        return ca_str

    for env_key in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        env_val = os.environ.get(env_key)
        if env_val and not os.path.exists(env_val):
            os.environ.pop(env_key, None)

    if certifi_path:
        os.environ["REQUESTS_CA_BUNDLE"] = certifi_path
        os.environ["SSL_CERT_FILE"] = certifi_path
        return certifi_path

    # Fallback: never raise OSError on a deleted _MEI path
    return False


_ensure_valid_ca_bundle()

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

SHARECOC_SERVER_URL = os.environ.get(
    "SHARECOC_SERVER_URL",
    "https://share.162.35.16.252.sslip.io",
).strip().rstrip("/")

DEFAULT_ROOT_FOLDER_ID = "root"
LEGACY_GENERAL_DEPT = "المجلد العام"
FOLDER_MIME = "application/vnd.google-apps.folder"
PERMISSIONS_CONFIG_FILENAME = ".sharecoc_permissions.json"
SNAPSHOT_MAX_AGE = 12.0
NETWORK_TIMEOUT = 20
TRANSFER_TIMEOUT = 300
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024      # 8 ميجابايت لكل شريحة رفع
DOWNLOAD_CHUNK_SIZE = 1024 * 1024        # 1 ميجابايت لكل شريحة تنزيل
PERMS_CACHE_TTL = 60.0

_IGNORED_EXACT = {"desktop.ini", "thumbs.db", ".ds_store"}
_IGNORED_SUFFIXES = (".tmp", ".laccdb", ".ldb", ".crdownload", ".partial", ".part", "~")
_GENERAL_FOLDER_ALIASES = {"", ".", "root", "القسم العام", "المجلد العام", "__ALL__"}


def _safe_log(msg):
    """طباعة آمنة لا تسبب أبداً خطأ UnicodeEncodeError أو تعطل الخيط في النسخة التنفيذية"""
    try:
        out = getattr(sys, "stdout", None)
        if out is not None:
            out.write(str(msg) + "\n")
            out.flush()
    except Exception:
        pass


_EXCEL_TEMP_RE = re.compile(r"^[0-9A-Fa-f]{8}$")


def is_ignored_name(name):
    """ملفات مؤقتة/نظامية لا يجب مزامنتها أبداً (ملفات قفل Office، ملفات مؤقتة...)"""
    if not name:
        return True
    low = name.lower()
    if low in _IGNORED_EXACT:
        return True
    if name.startswith("~$") or name.startswith(".") or name.startswith("~WRL"):
        return True
    if _EXCEL_TEMP_RE.match(name):
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


def _md5_file(file_path):
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_gdrive_config():
    """إرجاع تهيئة الاتصال بخادم Share COC المحلي (للتوافق مع بقية وحدات التطبيق)"""
    return {
        "server_url": os.environ.get("SHARECOC_SERVER_URL", SHARECOC_SERVER_URL).strip().rstrip("/"),
        "folder_id": DEFAULT_ROOT_FOLDER_ID,
    }


class DriveSnapshot:
    """صورة كاملة لشجرة الملفات والمجلدات في خادم Share COC في لحظة معينة"""

    def __init__(self, root_id=DEFAULT_ROOT_FOLDER_ID):
        self.root_id = root_id or DEFAULT_ROOT_FOLDER_ID
        self.folders = {"": self.root_id}          # rel_folder_path -> folder id
        self.folder_meta = {}                      # rel_folder_path -> metadata
        self.id_to_path = {self.root_id: ""}       # folder id -> rel path
        self.files = {}                            # rel_file_path -> metadata
        self.file_ids = {}                         # file id -> rel_file_path
        self.taken_at = time.time()


CloudSnapshot = DriveSnapshot


class GoogleDriveClient:
    """عميل التزامن الرسمي عبر خادم Share COC المستقل"""

    def __init__(self, root_folder_id=None):
        self.config = load_gdrive_config()
        self.server_url = self.config.get("server_url") or SHARECOC_SERVER_URL
        self.root_folder_id = root_folder_id or DEFAULT_ROOT_FOLDER_ID
        self.sync_folder = None  # يُضبط من main.py لتحديد المسارات النسبية تلقائياً
        self.service = True
        self._local = threading.local()
        self._snapshot_lock = threading.Lock()
        self._folder_lock = threading.RLock()
        self._path_locks = {}
        self._path_locks_guard = threading.Lock()
        self._snapshot = None
        self.last_error = None
        self._last_change_sig = None
        self._last_trash_files = []
        self._raw_cloud_devices = []
        self._cloud_devices_list = []
        self._has_fetched_cloud_perms = False
        self._perms_cache_data = {}
        self._perms_cache_ts = 0.0
        self._perms_refreshing = False
        self._priority_uploads_active = 0
        self._folder_ids = {"": self.root_folder_id}

    def _get_session(self):
        ca_path = _ensure_valid_ca_bundle()
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update({
                "x-admin-role": "admin",
                "User-Agent": "ShareCOC-Desktop/5.0",
            })
            sess.verify = ca_path
            self._local.session = sess
        elif isinstance(sess.verify, str) and not os.path.exists(sess.verify):
            sess.verify = ca_path
        elif ca_path and sess.verify is False:
            sess.verify = ca_path
        return sess

    def _api(self, path):
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.server_url}{path}"

    def reload_config(self):
        self.config = load_gdrive_config()
        self.server_url = self.config.get("server_url") or SHARECOC_SERVER_URL
        self._local.session = None

    def is_configured(self):
        return bool(self.server_url)

    def _path_lock(self, key):
        with self._path_locks_guard:
            lk = self._path_locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._path_locks[key] = lk
            return lk

    def peek_snapshot(self):
        """إرجاع آخر لقطة سحابية محفوظة فوراً دون أي طلب شبكة أو انتظار قفل"""
        return self._snapshot

    def invalidate(self):
        snap = self._snapshot
        if snap is not None:
            snap.taken_at = 0.0

    # ------------------------------------------------------------------ #
    # قراءة الشجرة الكاملة والمراقبة
    # ------------------------------------------------------------------ #
    def _normalize_permissions_payload(self, depts_obj, hub_sec, devices_list):
        normalized = {}
        if isinstance(depts_obj, dict):
            for dept_name, cfg in depts_obj.items():
                if dept_name in ("version", "updatedAt") or not isinstance(cfg, dict):
                    continue
                can_upload = bool(cfg.get("canUpload", cfg.get("canWrite", True)))
                can_edit = bool(cfg.get("canEdit", cfg.get("canWrite", True)))
                can_delete = bool(cfg.get("canDelete", True))
                auth_devs = list(cfg.get("authorizedDevices", []) or cfg.get("authorized_devices", []) or [])
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
                    "dept_username": str(cfg.get("deptUsername", "") or cfg.get("dept_username", "") or ""),
                    "dept_password": str(cfg.get("deptPassword", "") or cfg.get("dept_password", "") or ""),
                    "authorized_devices": auth_devs,
                    "pinCode": str(cfg.get("pinCode", "") or ""),
                    "deptUsername": str(cfg.get("deptUsername", "") or cfg.get("dept_username", "") or ""),
                    "deptPassword": str(cfg.get("deptPassword", "") or cfg.get("dept_password", "") or ""),
                    "authorizedDevices": auth_devs,
                }

        if hub_sec and isinstance(hub_sec, dict):
            hub_auths = list(hub_sec.get("authorizedDevices", []) or [])
            hub_user = str(hub_sec.get("username", "") or "")
            hub_pass = str(hub_sec.get("password", "") or "")
            hub_pin = str(hub_sec.get("pinCode", "") or "")
            sec_epoch = int(hub_sec.get("securityEpoch", 0) or hub_sec.get("security_epoch", 0) or 0)
            is_protected = bool(
                hub_sec.get("isProtected")
                or hub_sec.get("is_protected")
                or hub_sec.get("enabled")
                or hub_sec.get("hasCreds")
                or hub_user
                or hub_pass
                or hub_pin
            )
            normalized["مركز بيانات Access"] = {
                "can_view": True,
                "can_download": True,
                "can_upload": True,
                "can_create_folder": True,
                "can_edit": True,
                "can_rename": True,
                "can_move": True,
                "can_delete": True,
                "can_permanent_delete": True,
                "can_write": True,
                "pin_code": hub_pin,
                "dept_username": hub_user,
                "dept_password": hub_pass,
                "authorized_devices": hub_auths,
                "pinCode": hub_pin,
                "deptUsername": hub_user,
                "deptPassword": hub_pass,
                "authorizedDevices": hub_auths,
                "enabled": is_protected,
                "is_protected": is_protected,
                "isProtected": is_protected,
                "security_epoch": sec_epoch,
                "securityEpoch": sec_epoch,
            }

        self._raw_cloud_devices = list(devices_list or [])
        self._cloud_devices_list = self._raw_cloud_devices
        return normalized

    def snapshot(self, force=False, max_age=SNAPSHOT_MAX_AGE):
        """جلب الشجرة الكاملة للمجلدات والملفات من /api/drive/files"""
        snap = self._snapshot
        if not force and snap is not None and snap.taken_at > 0 and (time.time() - snap.taken_at) < max_age:
            return snap

        with self._snapshot_lock:
            snap = self._snapshot
            if not force and snap is not None and snap.taken_at > 0 and (time.time() - snap.taken_at) < max_age:
                return snap
            try:
                sess = self._get_session()
                url = self._api("/api/drive/files")
                params = {"refresh": "1"} if force else {}
                params["t"] = str(int(time.time() * 1000))
                resp = sess.get(url, params=params, timeout=NETWORK_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict) or not data.get("success", True):
                    raise RuntimeError(data.get("error") if isinstance(data, dict) else "Invalid server response")

                new = DriveSnapshot(self.root_folder_id)

                for folder_obj in data.get("allFolders", []) or []:
                    rel = norm_rel(folder_obj.get("path") or folder_obj.get("name") or "")
                    fid = folder_obj.get("id") or ""
                    if not rel or not fid:
                        continue
                    if any(part.startswith(".") for part in rel.split("/")):
                        continue
                    new.folders[rel] = fid
                    new.folder_meta[rel] = folder_obj
                    new.id_to_path[fid] = rel

                trash_items = []
                for item in data.get("files", []) or []:
                    if item.get("isDeleted"):
                        trash_items.append(item)
                        continue
                    fname = item.get("name") or ""
                    if not fname or is_ignored_name(fname):
                        continue
                    folder_raw = norm_rel(item.get("folder") or "")
                    folder = "" if folder_raw in _GENERAL_FOLDER_ALIASES else folder_raw
                    rel = norm_rel(f"{folder}/{fname}") if folder else norm_rel(fname)
                    if any(part.startswith(".") for part in rel.split("/")):
                        continue
                    fid = item.get("id") or ""
                    parent_id = item.get("folderId") or (new.folders.get(folder) if folder else self.root_folder_id) or self.root_folder_id
                    new.files[rel] = {
                        "id": fid,
                        "name": fname,
                        "rel_path": rel,
                        "folder": folder,
                        "parent_id": parent_id,
                        "size": int(item.get("size", 0) or 0),
                        "md5Checksum": item.get("md5Checksum") or "",
                        "modifiedTime": item.get("modifiedTime") or "",
                        "mimeType": item.get("mimeType") or "application/octet-stream",
                    }
                    if folder and folder not in new.folders:
                        new.folders[folder] = parent_id
                        new.id_to_path[parent_id] = folder

                new.file_ids = {meta["id"]: rel for rel, meta in new.files.items() if meta.get("id")}
                new.taken_at = time.time()
                self._snapshot = new
                self._last_trash_files = trash_items
                with self._folder_lock:
                    self._folder_ids.update(new.folders)

                if isinstance(data.get("permissions"), dict):
                    norm_perms = self._normalize_permissions_payload(
                        data.get("permissions"),
                        data.get("accessHubSecurity"),
                        data.get("devices"),
                    )
                    self._perms_cache_data = norm_perms
                    self._perms_cache_ts = time.time()

                self.last_error = None
                return new
            except Exception as e:
                self.last_error = str(e)
                _safe_log(f"[SHARECOC] Snapshot failed: {e}")
                return None

    def poll_changes_since_last(self):
        """استعلام خفيف وسريع من /api/drive/files?changes=1 للكشف الفوري عن أي تعديل سحابي"""
        try:
            sess = self._get_session()
            params = {"changes": "1", "t": str(int(time.time() * 1000))}
            if self._last_change_sig:
                params["sig"] = self._last_change_sig

            resp = sess.get(self._api("/api/drive/files"), params=params, timeout=NETWORK_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            new_sig = data.get("sig")

            if not self._last_change_sig:
                self._last_change_sig = new_sig
                return False, []

            changed = bool(data.get("changed")) or bool(new_sig and new_sig != self._last_change_sig)
            if new_sig:
                self._last_change_sig = new_sig

            if not changed:
                return False, []

            old_snap = self._snapshot
            old_files = dict(old_snap.files) if old_snap and hasattr(old_snap, "files") else {}
            new_snap = self.snapshot(force=True)
            if new_snap is None:
                return True, []

            delta_changes = []
            for rel, new_meta in new_snap.files.items():
                old_meta = old_files.get(rel)
                if (
                    old_meta is None
                    or (new_meta.get("md5Checksum") and new_meta.get("md5Checksum") != old_meta.get("md5Checksum"))
                    or new_meta.get("modifiedTime") != old_meta.get("modifiedTime")
                    or int(new_meta.get("size", 0) or 0) != int(old_meta.get("size", 0) or 0)
                ):
                    delta_changes.append({
                        "fileId": new_meta["id"],
                        "removed": False,
                        "_resolved_rel": rel,
                        "file": {
                            "id": new_meta["id"],
                            "name": new_meta["name"],
                            "trashed": False,
                            "md5Checksum": new_meta.get("md5Checksum") or "",
                            "modifiedTime": new_meta.get("modifiedTime") or "",
                            "size": new_meta.get("size", 0),
                            "mimeType": new_meta.get("mimeType") or "application/octet-stream",
                        },
                    })

            for rel, old_meta in old_files.items():
                if rel not in new_snap.files:
                    delta_changes.append({
                        "fileId": old_meta["id"],
                        "removed": True,
                        "_resolved_rel": rel,
                        "file": {
                            "id": old_meta["id"],
                            "name": old_meta["name"],
                            "trashed": True,
                        },
                    })

            return True, delta_changes
        except Exception as e:
            _safe_log(f"[SHARECOC CHANGES POLL ERROR]: {e}")
            return False, []

    # ------------------------------------------------------------------ #
    # واجهات متوافقة مع بقية وحدات التطبيق (gui.py / local_bridge.py)
    # ------------------------------------------------------------------ #
    def refresh_folders(self, force=False):
        snap = self.snapshot(force=force, max_age=15)
        if snap is None:
            return []
        return [
            {"id": fid, "name": rel.split("/")[-1], "path": rel}
            for rel, fid in snap.folders.items() if rel
        ]

    def list_folders(self):
        """الأقسام (المجلدات من المستوى الأول)"""
        snap = self.snapshot(max_age=15)
        if snap is None:
            return []
        return [
            {"name": rel, "id": fid}
            for rel, fid in sorted(snap.folders.items())
            if rel and "/" not in rel
        ]

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
                "id": item["id"],
                "file_name": item["name"],
                "file_path": rel,
                "department": dept,
                "folder": folder or dept,
                "storage_path": item["id"],
                "file_size": int(item.get("size", 0) or 0),
                "md5": item.get("md5Checksum"),
                "updated_at": item.get("modifiedTime", ""),
                "last_modified_by_name": "خادم Share COC",
                "is_deleted": False,
            })
        return out

    def list_accessible_files(self):
        return self.list_files()

    def list_deleted_files(self):
        """جلب قائمة الملفات المحذوفة في سلة مهملات الخادم المحلي"""
        try:
            self.snapshot(max_age=10)
            out = []
            for f in self._last_trash_files or []:
                fname = f.get("name", "")
                if not fname or is_ignored_name(fname):
                    continue
                folder_raw = norm_rel(f.get("folder") or "")
                folder = "" if folder_raw in _GENERAL_FOLDER_ALIASES else folder_raw
                rel_path = f"{folder}/{fname}" if folder else fname
                dept = f.get("department") or (folder.split("/")[0] if folder else "القسم العام")
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
            _safe_log(f"[SHARECOC] Error listing deleted files: {e}")
            return []

    def get_folder_permissions(self, force_refresh=False):
        """قراءة الصلاحيات والأجهزة المفصلة من /api/drive/permissions"""
        now = time.time()
        if not force_refresh and (now - self._perms_cache_ts < PERMS_CACHE_TTL) and self._perms_cache_data:
            return self._perms_cache_data
        try:
            sess = self._get_session()
            params = {"admin": "1", "t": str(int(now * 1000))}
            if force_refresh:
                params["force"] = "1"
            resp = sess.get(self._api("/api/drive/permissions"), params=params, timeout=NETWORK_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or not data.get("success"):
                return getattr(self, "_perms_cache_data", {}) or {}

            normalized = self._normalize_permissions_payload(
                data.get("permissions", {}),
                data.get("accessHubSecurity", {}),
                data.get("devices", []),
            )
            self._perms_cache_data = normalized
            self._perms_cache_ts = now
            self._has_fetched_cloud_perms = True
            try:
                lf = self._get_local_perms_file()
                lf.parent.mkdir(parents=True, exist_ok=True)
                lf.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            return normalized
        except Exception as e:
            _safe_log(f"[SHARECOC] Error reading folder permissions: {e}")
            return getattr(self, "_perms_cache_data", {}) or {}

    def save_folder_permissions(self, permissions_map):
        try:
            sess = self._get_session()
            resp = sess.post(
                self._api("/api/drive/permissions"),
                json={"permissions": permissions_map, "isAdmin": True},
                timeout=NETWORK_TIMEOUT,
            )
            resp.raise_for_status()
            self.get_folder_permissions(force_refresh=True)
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC] Error saving folder permissions: {e}")
            return False

    def authorize_device_for_dept(self, dept_name, machine_guid, device_name, os_info="Windows"):
        """اعتماد وتسجيل الجهاز لقسم معين أو مركز Access عبر /api/drive/permissions"""
        try:
            clean_guid = str(machine_guid).strip()
            clean_name = str(device_name).strip() or "حاسوب موظف"
            clean_dept = str(dept_name).strip()
            if not clean_guid or not clean_dept:
                return False

            sess = self._get_session()
            if clean_dept in ("مركز بيانات Access", "__ACCESS_HUB__"):
                payload = {
                    "action": "REGISTER_ACCESS_HUB_DEVICE",
                    "machineGuid": clean_guid,
                    "deviceName": clean_name,
                    "os": os_info,
                    "user": clean_name,
                    "isAdmin": True,
                }
            else:
                payload = {
                    "action": "REGISTER_DEPARTMENT_DEVICE",
                    "departmentName": clean_dept,
                    "machineGuid": clean_guid,
                    "deviceName": clean_name,
                    "os": os_info,
                    "user": clean_name,
                    "isAdmin": True,
                }

            resp = sess.post(self._api("/api/drive/permissions"), json=payload, timeout=NETWORK_TIMEOUT)
            resp.raise_for_status()
            res_json = resp.json()
            if not res_json.get("success"):
                raise RuntimeError(res_json.get("error") or "Authorization failed")

            self.get_folder_permissions(force_refresh=True)
            _safe_log(f"[SHARECOC] Authorized device {clean_name} ({clean_guid}) for {clean_dept}")
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC ERROR] authorize_device_for_dept failed: {e}")
            return False

    def _get_local_perms_file(self):
        folder = getattr(self, "sync_folder", None)
        if not folder:
            folder = Path(os.environ.get("USERPROFILE", "C:")) / "FileExchangeShared"
        return Path(folder) / ".sharecoc_perms_cache.json"

    def get_cached_folder_permissions(self):
        """قراءة فورية للصلاحيات من الذاكرة أو الملف المحلي مع تحديث غير حاصر في الخلفية"""
        if not self._perms_cache_data:
            try:
                lf = self._get_local_perms_file()
                if lf.exists():
                    self._perms_cache_data = json.loads(lf.read_text(encoding="utf-8"))
            except Exception:
                pass

            if not self._perms_refreshing:
                self._perms_refreshing = True

                def _bg_init():
                    try:
                        self.get_folder_permissions(force_refresh=True)
                    finally:
                        self._perms_refreshing = False

                threading.Thread(target=_bg_init, daemon=True).start()
            return self._perms_cache_data or {}

        if (time.time() - self._perms_cache_ts) >= PERMS_CACHE_TTL and not self._perms_refreshing:
            self._perms_refreshing = True

            def _bg():
                try:
                    self.get_folder_permissions(force_refresh=True)
                finally:
                    self._perms_refreshing = False

            threading.Thread(target=_bg, daemon=True).start()
        return self._perms_cache_data or {}

    def check_file_lock(self, file_name):
        return False, None

    def get_file_by_name(self, file_name, folder=None):
        snap = self.snapshot(max_age=30)
        if snap is None or not file_name:
            return None
        folder = norm_rel(folder) if folder and folder not in _GENERAL_FOLDER_ALIASES else None
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
        return {
            "id": item["id"],
            "file_name": item["name"],
            "file_path": rel,
            "storage_path": item["id"],
            "file_size": int(item.get("size", 0) or 0),
        }

    # ------------------------------------------------------------------ #
    # المجلدات
    # ------------------------------------------------------------------ #
    def ensure_folder(self, rel_folder):
        """التأكد من وجود مسار مجلدات كامل (مثل: قسم/مجلد/فرعي) وإنشاؤه على الخادم"""
        rel_folder = norm_rel(rel_folder)
        if not rel_folder or rel_folder in _GENERAL_FOLDER_ALIASES:
            return self.root_folder_id
        with self._folder_lock:
            cached = self._folder_ids.get(rel_folder)
            if cached:
                return cached
            try:
                sess = self._get_session()
                resp = sess.post(
                    self._api("/api/drive/files"),
                    json={"action": "ENSURE_FOLDER_PATH", "folderPath": rel_folder},
                    timeout=NETWORK_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                fid = data.get("folderId")
                if fid:
                    self._folder_ids[rel_folder] = fid
                    self.invalidate()
                    return fid
            except Exception as e:
                _safe_log(f"[SHARECOC] ensure_folder error ({rel_folder}): {e}")
        return self.root_folder_id

    def create_folder(self, folder_name):
        try:
            rel = norm_rel(folder_name)
            if not rel:
                return None
            sess = self._get_session()
            resp = sess.post(
                self._api("/api/drive/files"),
                json={"action": "CREATE_FOLDER", "folderPath": rel, "name": rel.split("/")[-1]},
                timeout=NETWORK_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            fid = (data.get("folder") or {}).get("id")
            if fid:
                with self._folder_lock:
                    self._folder_ids[rel] = fid
                self.invalidate()
                return fid
            return None
        except Exception as e:
            _safe_log(f"[SHARECOC] Failed to create folder {folder_name}: {e}")
            return None

    def resolve_folder_id(self, rel_folder, use_cache=True):
        rel_folder = norm_rel(rel_folder)
        if not rel_folder or rel_folder in _GENERAL_FOLDER_ALIASES:
            return self.root_folder_id
        if use_cache:
            with self._folder_lock:
                if rel_folder in self._folder_ids:
                    return self._folder_ids[rel_folder]
        snap = self.snapshot(force=not use_cache, max_age=5)
        if snap is not None and rel_folder in snap.folders:
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
        if not folder_rel:
            return False
        try:
            fid = self.resolve_folder_id(folder_rel, use_cache=False) or folder_rel
            sess = self._get_session()
            resp = sess.post(
                self._api("/api/drive/files"),
                json={"action": "DELETE", "id": fid},
                timeout=NETWORK_TIMEOUT,
            )
            if not resp.ok:
                return False
            self._forget_folder_prefix(folder_rel)
            self.invalidate()
            _safe_log(f"[SHARECOC] Trashed folder: {folder_rel}")
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC] Error deleting folder {folder_rel}: {e}")
            return False

    def rename_folder(self, old_rel, new_name):
        old_rel = norm_rel(old_rel)
        new_name = norm_rel(new_name).split("/")[-1]
        if not old_rel or not new_name:
            return False
        try:
            fid = self.resolve_folder_id(old_rel, use_cache=False) or old_rel
            sess = self._get_session()
            resp = sess.post(
                self._api("/api/drive/files"),
                json={"action": "RENAME", "id": fid, "name": new_name},
                timeout=NETWORK_TIMEOUT,
            )
            resp.raise_for_status()
            self._forget_folder_prefix(old_rel)
            self.invalidate()
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC] Error renaming folder: {e}")
            return False

    # ------------------------------------------------------------------ #
    # الملفات (رفع، تنزيل، حذف، استرجاع، نقل)
    # ------------------------------------------------------------------ #
    def _rel_from_local(self, local_path):
        if self.sync_folder:
            try:
                return norm_rel(Path(local_path).resolve().relative_to(Path(self.sync_folder).resolve()))
            except Exception:
                pass
        return Path(local_path).name

    def upload_file(
        self,
        local_path,
        file_name=None,
        file_path=None,
        rel_path=None,
        user_name="تطبيق الحاسوب",
        device_name=None,
        existing_id=None,
        progress_callback=None,
        **kwargs,
    ):
        """رفع ملف مباشر (<= 8MB) أو مجزأ قابل للاستئناف (> 8MB) إلى خادم Share COC"""
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
        if rel and any(part.startswith(".") for part in rel.split("/")):
            return True, {"ignored": True}

        parent_rel = rel.rsplit("/", 1)[0] if "/" in rel else ""
        if parent_rel in _GENERAL_FOLDER_ALIASES:
            parent_rel = ""

        is_priority = bool(kwargs.get("is_priority", False))
        if is_priority:
            self._priority_uploads_active += 1

        try:
            with self._path_lock(rel or fname):
                try:
                    total_size = p.stat().st_size
                    mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
                    sess = self._get_session()

                    if callable(progress_callback):
                        try:
                            progress_callback(0, max(total_size, 1))
                        except Exception:
                            pass

                    if total_size <= UPLOAD_CHUNK_SIZE:
                        with open(p, "rb") as fh:
                            resp = sess.post(
                                self._api("/api/drive/files"),
                                files={"file": (fname, fh, mime)},
                                data={
                                    "fileName": fname,
                                    "folderId": self.root_folder_id,
                                    "folderPath": parent_rel,
                                },
                                timeout=TRANSFER_TIMEOUT,
                            )
                        resp.raise_for_status()
                        res_json = resp.json()
                        if not res_json.get("success"):
                            raise RuntimeError(res_json.get("error") or "Upload failed")
                        meta = res_json.get("file") or res_json
                        if callable(progress_callback):
                            try:
                                progress_callback(total_size, total_size)
                            except Exception:
                                pass
                    else:
                        init_resp = sess.post(
                            self._api("/api/drive/files"),
                            json={
                                "action": "INIT_UPLOAD",
                                "fileName": fname,
                                "mimeType": mime,
                                "fileSize": total_size,
                                "folderId": self.root_folder_id,
                                "folderPath": parent_rel,
                            },
                            timeout=NETWORK_TIMEOUT,
                        )
                        init_resp.raise_for_status()
                        init_data = init_resp.json()
                        session_uri = init_data.get("sessionUri")
                        if not session_uri:
                            raise RuntimeError(init_data.get("error") or "Missing sessionUri")

                        meta = None
                        offset = 0
                        with open(p, "rb") as fh:
                            while offset < total_size:
                                if not is_priority and self._priority_uploads_active > 0:
                                    wait_start = time.time()
                                    while self._priority_uploads_active > 0 and (time.time() - wait_start < 120):
                                        time.sleep(0.25)

                                fh.seek(offset)
                                chunk_bytes = fh.read(UPLOAD_CHUNK_SIZE)
                                if not chunk_bytes:
                                    break
                                end = offset + len(chunk_bytes) - 1

                                chunk_resp = sess.post(
                                    self._api("/api/drive/files"),
                                    data={
                                        "action": "UPLOAD_CHUNK",
                                        "sessionUri": session_uri,
                                        "start": str(offset),
                                        "end": str(end),
                                        "total": str(total_size),
                                    },
                                    files={"chunk": (fname, chunk_bytes, "application/octet-stream")},
                                    timeout=TRANSFER_TIMEOUT,
                                )
                                chunk_resp.raise_for_status()
                                chunk_data = chunk_resp.json()
                                if not chunk_data.get("success"):
                                    raise RuntimeError(chunk_data.get("error") or "Chunk upload failed")

                                offset = end + 1
                                if callable(progress_callback):
                                    try:
                                        progress_callback(offset, total_size)
                                    except Exception:
                                        pass
                                if chunk_data.get("done") and chunk_data.get("file"):
                                    meta = chunk_data["file"]

                        if not meta:
                            raise RuntimeError("Chunked upload finished without file metadata")

                    if isinstance(meta, dict) and not meta.get("md5Checksum"):
                        try:
                            meta["md5Checksum"] = _md5_file(p)
                        except Exception:
                            pass

                    _safe_log(f"[SHARECOC] Uploaded: {rel} ({total_size} bytes)")
                    self.invalidate()
                    return True, meta
                except Exception as e:
                    self.last_error = str(e)
                    _safe_log(f"[SHARECOC UPLOAD ERROR] {rel}: {e}")
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
        """تنزيل متدفق آمن من /api/drive/stream إلى ملف مؤقت ثم استبدال ذري"""
        if not self.is_configured():
            return False, "No service"
        try:
            fid = None
            sp = str(storage_path or "").strip()
            if sp:
                if sp.startswith("loc_") or sp.startswith("trash_"):
                    fid = sp
                elif "/" not in sp and len(sp) > 15 and "." not in sp:
                    # قد يكون معرفاً قديماً موجوداً في gdrive-id-map.json على الخادم أو مساراً نسبياً
                    fid = self.resolve_file_id(file_name) or sp
                else:
                    fid = self.resolve_file_id(sp) or sp
            else:
                info = self.get_file_by_name(file_name)
                if info:
                    fid = info.get("id")
                if not fid:
                    fid = self.resolve_file_id(file_name)

            if not fid:
                return False, f"File {file_name} not found in server"

            dest = Path(local_dest_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.parent / f".sharecoc-dl-{os.getpid()}-{threading.get_ident()}-{int(time.time() * 1000)}.part"
            try:
                sess = self._get_session()
                url = self._api("/api/drive/stream")
                with sess.get(
                    url,
                    params={"id": fid, "download": "1"},
                    stream=True,
                    timeout=TRANSFER_TIMEOUT,
                ) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    total_bytes = int(resp.headers.get("X-File-Size") or resp.headers.get("Content-Length") or 0)
                    done_bytes = 0
                    with open(tmp, "wb") as fh:
                        for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                            if not chunk:
                                continue
                            fh.write(chunk)
                            done_bytes += len(chunk)
                            if callable(progress_callback) and total_bytes > 0:
                                try:
                                    progress_callback(done_bytes, total_bytes)
                                except Exception:
                                    pass
                if callable(progress_callback):
                    try:
                        progress_callback(max(done_bytes, total_bytes, 1), max(total_bytes, done_bytes, 1))
                    except Exception:
                        pass

                try:
                    os.replace(tmp, dest)
                except (PermissionError, OSError) as os_err:
                    try:
                        from office_handler import OfficeHandler
                        applied = OfficeHandler.safe_apply_file(str(dest), str(tmp))
                        if not applied:
                            raise os_err
                    except Exception:
                        raise os_err
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass

            _safe_log(f"[SHARECOC] Downloaded: {file_name} -> {dest}")
            return True, "Downloaded successfully"
        except Exception as e:
            _safe_log(f"[SHARECOC DOWNLOAD ERROR]: {e}")
            return False, str(e)

    def download_file_from_storage(self, storage_path, local_dest_path):
        p = Path(local_dest_path)
        return self.download_file(p.name, local_dest_path, storage_path=storage_path)[0]

    def resolve_file_id(self, rel_path):
        rel_path = norm_rel(rel_path)
        if not rel_path:
            return None
        snap = self.snapshot(max_age=10)
        if snap is not None:
            if rel_path in snap.files:
                return snap.files[rel_path]["id"]
            for f_rel, meta in snap.files.items():
                if meta.get("name") == rel_path or f_rel.endswith("/" + rel_path):
                    return meta.get("id")
        return None

    def trash_by_id(self, file_id):
        if not file_id:
            return False
        sess = self._get_session()
        resp = sess.post(
            self._api("/api/drive/files"),
            json={"action": "DELETE", "id": file_id},
            timeout=NETWORK_TIMEOUT,
        )
        resp.raise_for_status()
        self.invalidate()
        return True

    def restore_by_id(self, file_id):
        if not file_id:
            return False
        try:
            sess = self._get_session()
            resp = sess.post(
                self._api("/api/drive/files"),
                json={"action": "RESTORE", "id": file_id},
                timeout=NETWORK_TIMEOUT,
            )
            resp.raise_for_status()
            self.invalidate()
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC RESTORE ERROR]: {e}")
            return False

    def purge_by_id(self, file_id):
        if not file_id:
            return False
        try:
            sess = self._get_session()
            resp = sess.post(
                self._api("/api/drive/files"),
                json={"action": "PERMANENT_DELETE", "id": file_id},
                timeout=NETWORK_TIMEOUT,
            )
            resp.raise_for_status()
            self.invalidate()
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC PURGE BY ID ERROR] {file_id}: {e}")
            return False

    def purge_file(self, rel_path=None, file_id=None, file_name=None):
        try:
            if file_id and self.purge_by_id(file_id):
                return True
            if rel_path:
                fid = self.resolve_file_id(rel_path) or self.resolve_folder_id(rel_path, use_cache=False)
                if fid and fid != self.root_folder_id:
                    return self.purge_by_id(fid)
            fname = file_name or (rel_path.split("/")[-1] if rel_path else "")
            if fname:
                for t in self.list_deleted_files():
                    if t.get("file_name") == fname and t.get("id"):
                        self.purge_by_id(t["id"])
                return True
        except Exception as e:
            _safe_log(f"[SHARECOC PURGE FILE ERROR]: {e}")
        return False

    def delete_file(self, file_path, server_file_id=None, **kwargs):
        try:
            if server_file_id:
                try:
                    self.trash_by_id(server_file_id)
                    _safe_log(f"[SHARECOC] Trashed by ID: {server_file_id} ({file_path})")
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
            _safe_log(f"[SHARECOC] Moved to trash: {file_path}")
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC DELETE ERROR]: {e}")
            return False

    def move_file(self, file_id, new_rel_path):
        """نقل/إعادة تسمية ملف أو مجلد في الخادم عبر /api/drive/files (MOVE + RENAME)"""
        new_rel_path = norm_rel(new_rel_path)
        new_name = new_rel_path.split("/")[-1]
        new_parent_rel = new_rel_path.rsplit("/", 1)[0] if "/" in new_rel_path else ""
        if new_parent_rel in _GENERAL_FOLDER_ALIASES:
            new_parent_rel = ""

        sess = self._get_session()
        current_id = file_id
        meta = {"id": current_id, "name": new_name}

        snap = self.peek_snapshot()
        old_rel = None
        if snap:
            old_rel = snap.file_ids.get(file_id) or snap.id_to_path.get(file_id)
        old_name = old_rel.split("/")[-1] if old_rel else None
        old_parent_rel = (old_rel.rsplit("/", 1)[0] if "/" in old_rel else "") if old_rel else None

        if old_parent_rel is None or old_parent_rel != new_parent_rel:
            move_payload = {
                "action": "MOVE",
                "id": current_id,
                "targetFolderId": self.root_folder_id,
            }
            if new_parent_rel:
                move_payload["targetFolderPath"] = new_parent_rel
            resp = sess.post(self._api("/api/drive/files"), json=move_payload, timeout=NETWORK_TIMEOUT)
            resp.raise_for_status()
            m_data = resp.json()
            if m_data.get("item"):
                meta = m_data["item"]
                current_id = meta.get("id") or current_id

        if old_name is None or old_name != new_name:
            resp = sess.post(
                self._api("/api/drive/files"),
                json={"action": "RENAME", "id": current_id, "name": new_name},
                timeout=NETWORK_TIMEOUT,
            )
            resp.raise_for_status()
            r_data = resp.json()
            if r_data.get("item"):
                meta = r_data["item"]

        self.invalidate()
        return meta

    def move_path_in_cloud(self, old_rel_path, new_rel_path, is_folder=False, server_file_id=None):
        try:
            old_rel_path = norm_rel(old_rel_path)
            new_rel_path = norm_rel(new_rel_path)
            fid = server_file_id
            if not fid:
                fid = self.resolve_folder_id(old_rel_path, use_cache=False) if is_folder else self.resolve_file_id(old_rel_path)
            if not fid or fid == self.root_folder_id:
                fid = old_rel_path
            meta = self.move_file(fid, new_rel_path)
            if is_folder:
                self._forget_folder_prefix(old_rel_path)
            self.invalidate()
            _safe_log(f"[SHARECOC] Moved in server: {old_rel_path} -> {new_rel_path}")
            return True, meta
        except Exception as e:
            _safe_log(f"[SHARECOC MOVE ERROR] {old_rel_path} -> {new_rel_path}: {e}")
            return False, str(e)

    def rename_file(self, old_file_path, new_name):
        if not old_file_path or not new_name:
            return False
        try:
            fid = self.resolve_file_id(old_file_path) or norm_rel(old_file_path)
            sess = self._get_session()
            resp = sess.post(
                self._api("/api/drive/files"),
                json={"action": "RENAME", "id": fid, "name": norm_rel(new_name).split("/")[-1]},
                timeout=NETWORK_TIMEOUT,
            )
            resp.raise_for_status()
            self.invalidate()
            return True
        except Exception as e:
            _safe_log(f"[SHARECOC RENAME ERROR]: {e}")
            return False
