"""
تبادل الملفات – File Exchange System
خادم الجسر المحلي لربط لوحة التحكم (الويب / الجوال) ببرامج Microsoft Office الأصلية على الحاسوب
Local Companion Bridge Server (Port 18290)
"""
import os
import re
import sys
import json
import time
import subprocess
import urllib.parse
import threading
import unicodedata
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import winreg

from office_handler import OfficeHandler
from gdrive_client import norm_rel, norm_key, _md5_file

BRIDGE_PORT = 18290


class LocalBridgeHandler(BaseHTTPRequestHandler):
    sync_folder = None
    cloud_client = None
    sync_engine = None
    show_window_callback = None
    last_sync_time = 0.0
    last_synced_file = ""
    _transfers_lock = threading.Lock()
    _active_transfers = {}  # normalized_key -> {"downloading": bool, "opening": bool}

    @staticmethod
    def _clean_bidi(s):
        return re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(s or '')).strip()

    @classmethod
    def _norm_text(cls, s):
        return unicodedata.normalize("NFC", cls._clean_bidi(s))

    @classmethod
    def _norm_folder(cls, folder_name):
        nf = norm_rel(cls._norm_text(folder_name))
        if nf in ('__ALL__', 'المجلد العام', 'القسم العام', 'root', '.'):
            return ""
        return nf

    @staticmethod
    def _sanitize_rel_param(val):
        cleaned = str(val or "").strip().rstrip('/\\')
        while "../" in cleaned or "..\\" in cleaned:
            cleaned = cleaned.replace("../", "").replace("..\\", "")
        return cleaned

    def _build_transfer_keys(self, file_name, folder_name="", storage_path="", target_path=None):
        keys = []
        nf = self._norm_folder(folder_name)
        cf = self._norm_text(file_name).strip('/\\')
        if cf:
            req_rel = f"{nf}/{cf}" if nf else cf
            rk = norm_key(req_rel)
            if rk:
                keys.append(rk)
        if target_path is not None and self.sync_folder:
            try:
                disk_rel = norm_rel(Path(target_path).relative_to(Path(self.sync_folder)))
                dk = norm_key(disk_rel)
                if dk and dk not in keys:
                    keys.append(dk)
            except Exception:
                pass
        if storage_path:
            sk = f"sp:{str(storage_path).strip()}"
            if sk not in keys:
                keys.append(sk)
        return keys

    @classmethod
    def _start_transfer(cls, keys, downloading=False, opening=False):
        entry = {"downloading": bool(downloading), "opening": bool(opening)}
        reg_keys = list(keys or [])
        with cls._transfers_lock:
            for k in reg_keys:
                if k:
                    cls._active_transfers[k] = entry
        return entry, reg_keys

    @classmethod
    def _update_transfer(cls, entry, keys_list, downloading=None, opening=None, extra_keys=None):
        if entry is None:
            return
        with cls._transfers_lock:
            if downloading is not None:
                entry["downloading"] = bool(downloading)
            if opening is not None:
                entry["opening"] = bool(opening)
            if extra_keys:
                for ek in extra_keys:
                    if ek and ek not in keys_list:
                        keys_list.append(ek)
                        cls._active_transfers[ek] = entry

    @classmethod
    def _clear_transfer(cls, entry, keys_list):
        if entry is None or not keys_list:
            return
        with cls._transfers_lock:
            for k in keys_list:
                if cls._active_transfers.get(k) is entry:
                    cls._active_transfers.pop(k, None)

    @classmethod
    def _get_transfer_state(cls, keys):
        with cls._transfers_lock:
            for k in keys:
                if not k:
                    continue
                entry = cls._active_transfers.get(k)
                if entry is not None:
                    return bool(entry.get("downloading", False)), bool(entry.get("opening", False))
        return False, False

    def _calc_md5(self, file_path):
        if self.sync_engine and hasattr(self.sync_engine, "calculate_hash"):
            return str(self.sync_engine.calculate_hash(str(file_path)) or "").lower()
        return str(_md5_file(str(file_path)) or "").lower()

    def _find_remote_meta(self, snap, file_name, folder_name="", storage_path=""):
        if not snap or not hasattr(snap, "files"):
            return None, None
        sp = str(storage_path or "").strip()
        if sp and hasattr(snap, "file_ids") and sp in snap.file_ids:
            r = snap.file_ids[sp]
            if r in snap.files:
                return r, snap.files[r]
        nf = self._norm_folder(folder_name)
        cf = self._norm_text(file_name)
        target_rel = f"{nf}/{cf}" if nf else cf
        if target_rel in snap.files:
            return target_rel, snap.files[target_rel]
        target_k = norm_key(target_rel)
        for r, meta in snap.files.items():
            if norm_key(r) == target_k:
                return r, meta
        if not nf:
            cf_k = norm_key(cf)
            for r, meta in snap.files.items():
                if norm_key(meta.get("name") or "") == cf_k:
                    return r, meta
        return None, None

    def _is_local_newer(self, target_path, expected_md5, local_hash):
        if not self.sync_engine or not hasattr(self.sync_engine, "state_mgr") or not self.sync_folder:
            return False
        try:
            rel = norm_rel(Path(target_path).relative_to(Path(self.sync_folder)))
        except Exception:
            return False
        st = self.sync_engine.state_mgr.get_file_state(rel)
        if not st and hasattr(self.sync_engine.state_mgr, "get_all_states_map"):
            try:
                rk = norm_key(rel)
                for sr, srow in (self.sync_engine.state_mgr.get_all_states_map() or {}).items():
                    if norm_key(sr) == rk:
                        st = srow
                        break
            except Exception:
                pass
        if not st:
            return False
        if st.get("sync_status") in ("syncing", "pending_upload", "failed"):
            return True
        if st.get("sha256_hash") and st.get("remote_md5") and str(st.get("sha256_hash")).lower() != str(st.get("remote_md5")).lower():
            return True
        if expected_md5 and str(st.get("remote_md5") or "").lower() == expected_md5.lower() and st.get("sha256_hash"):
            if local_hash != str(st.get("sha256_hash")).lower():
                return True
        return False

    def _is_loopback(self):
        client_ip = getattr(self, 'client_address', ('',))[0]
        return client_ip in ('127.0.0.1', '::1', 'localhost', '::ffff:127.0.0.1') or str(client_ip).startswith('127.')

    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', f'{content_type}; charset=utf-8')
        origin = (self.headers.get('Origin') or '').strip() if getattr(self, 'headers', None) else ''
        self.send_header('Access-Control-Allow-Origin', origin if origin else '*')
        self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # منع استدعاء المسارات الحساسة والتحكم بالتطبيق من خارج الجهاز المحلي
        if path in ('/open', '/show', '/reveal', '/unlock', '/sync') and not self._is_loopback():
            self._set_headers(403)
            self.wfile.write(json.dumps({"success": False, "error": "Forbidden: Local loopback access only"}, ensure_ascii=False).encode('utf-8'))
            return

        if path == '/ping' or path == '/status':
            self._set_headers(200)
            data = {
                "status": "ok",
                "app": "share coc",
                "version": "5.0",
                "pid": os.getpid(),
                "last_sync_time": getattr(LocalBridgeHandler, "last_sync_time", 0.0),
                "last_synced_file": getattr(LocalBridgeHandler, "last_synced_file", ""),
                "sync_folder": str(self.sync_folder) if self.sync_folder else None
            }
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
            return

        if path == '/lan/file':
            req_path = params.get('path', [''])[0].strip()
            if not req_path:
                self._set_headers(400)
                self.wfile.write(b"path required")
                return
            safe_rel = req_path.replace("\\", "/").strip("/")
            while "../" in safe_rel or "..\\" in safe_rel:
                safe_rel = safe_rel.replace("../", "").replace("..\\", "")
            base_folder = Path(self.sync_folder) if self.sync_folder else Path(".")
            target_file = (base_folder / safe_rel).resolve()
            if not str(target_file).startswith(str(base_folder.resolve())) or not target_file.exists() or not target_file.is_file():
                self._set_headers(404)
                self.wfile.write(b"file not found")
                return
            try:
                f_size = target_file.stat().st_size
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(f_size))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(target_file, 'rb') as f:
                    while chunk := f.read(128 * 1024):
                        self.wfile.write(chunk)
            except Exception:
                pass
            return

        if path == '/show':
            try:
                cb = LocalBridgeHandler.__dict__.get('show_window_callback')
                if isinstance(cb, staticmethod):
                    cb = cb.__func__
                if callable(cb):
                    cb()
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
            return

        if path == '/sync':
            try:
                req_file = params.get('file', [''])[0].strip()
                req_folder = params.get('folder', [''])[0].strip()
                if self.cloud_client and hasattr(self.cloud_client, 'invalidate'):
                    self.cloud_client.invalidate()
                sync_result = {"success": True}
                if req_file and self.sync_engine:
                    target = self._find_local_file(req_file, req_folder)
                    if target and target.exists():
                        try:
                            rel = norm_rel(target.relative_to(Path(self.sync_folder)))
                            if OfficeHandler.is_access_db(str(target)) and OfficeHandler.is_access_file_open_locally(str(target)):
                                sync_result = {
                                    "success": False,
                                    "deferred": True,
                                    "locked": True,
                                    "file": rel,
                                    "error": "قاعدة بيانات Access مفتوحة حالياً ومحمية من الرفع حتى يتم إغلاقها.",
                                }
                            else:
                                ok, meta = self.sync_engine.sync_file_now(str(target), rel_path=rel)
                                sync_result = {"success": bool(ok), "file": rel}
                        except Exception as sync_err:
                            sync_result = {"success": False, "error": str(sync_err)}
                elif self.sync_engine:
                    self.sync_engine.wake(delay=0.05)
                self._set_headers(200)
                self.wfile.write(json.dumps(sync_result, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
            return

        if path == '/open':
            file_name = self._sanitize_rel_param(params.get('file', [''])[0])
            folder_name = self._sanitize_rel_param(params.get('folder', [''])[0])
            storage_path = params.get('storage_path', [''])[0].strip()
            passed_md5 = params.get('md5', [''])[0].strip().lower()

            if not file_name:
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "file parameter required"}).encode('utf-8'))
                return

            try:
                target_path = self._find_local_file(file_name, folder_name, storage_path=storage_path)
                cloud_fid = storage_path
                transfer_keys = self._build_transfer_keys(
                    file_name, folder_name, storage_path=storage_path, target_path=target_path
                )

                if target_path is None or not target_path.exists():
                    if not self.cloud_client:
                        self._set_headers(404)
                        self.wfile.write(json.dumps({
                            "success": False,
                            "error": f"الملف '{file_name}' غير موجود محلياً ولا يتوفر اتصال سحابي."
                        }, ensure_ascii=False).encode('utf-8'))
                        return

                    entry, reg_keys = self._start_transfer(transfer_keys, downloading=True, opening=False)
                    threading.Thread(
                        target=self._open_worker,
                        args=(file_name, folder_name, cloud_fid or storage_path, passed_md5, None, False, True, entry, reg_keys),
                        daemon=True
                    ).start()
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "status": "downloading",
                        "message": f"جاري تنزيل أحدث نسخة من '{file_name}' وسيتم تشغيلها تلقائياً...",
                        "path": None
                    }, ensure_ascii=False).encode('utf-8'))
                    return

                # الملف موجود محلياً: فحص سريع إن أمكن (<150ms)، وإلا إتمام الفحص السحابي في الخلفية
                if not self.cloud_client or not self.cloud_client.is_configured():
                    entry, reg_keys = self._start_transfer(transfer_keys, downloading=False, opening=True)
                    threading.Thread(
                        target=self._open_worker,
                        args=(file_name, folder_name, cloud_fid, passed_md5, target_path, False, False, entry, reg_keys),
                        daemon=True
                    ).start()
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "status": "opened",
                        "message": f"تم فتح المستند '{file_name}' في البرنامج الأصلي بنجاح.",
                        "path": str(target_path)
                    }, ensure_ascii=False).encode('utf-8'))
                    return

                expected_md5 = passed_md5
                needs_cloud_refresh = False
                if not expected_md5:
                    snap = self.cloud_client.peek_snapshot() if hasattr(self.cloud_client, "peek_snapshot") else None
                    snap_age = time.time() - float(getattr(snap, "taken_at", 0.0) or 0.0) if snap else 9999.0
                    if snap is not None and hasattr(snap, "files") and snap_age <= 5.0:
                        _, remote_info = self._find_remote_meta(snap, file_name, folder_name, storage_path)
                        if remote_info:
                            cloud_fid = remote_info.get("id") or cloud_fid
                            expected_md5 = str(remote_info.get("md5Checksum") or "").lower()
                        else:
                            needs_cloud_refresh = True
                    else:
                        needs_cloud_refresh = True

                try:
                    file_size = target_path.stat().st_size
                except OSError:
                    file_size = 0

                if not needs_cloud_refresh and expected_md5 and file_size <= 32 * 1024 * 1024:
                    local_hash = self._calc_md5(target_path)
                    if local_hash == expected_md5 or self._is_local_newer(target_path, expected_md5, local_hash):
                        entry, reg_keys = self._start_transfer(transfer_keys, downloading=False, opening=True)
                        threading.Thread(
                            target=self._open_worker,
                            args=(file_name, folder_name, cloud_fid, expected_md5, target_path, False, False, entry, reg_keys),
                            daemon=True
                        ).start()
                        self._set_headers(200)
                        self.wfile.write(json.dumps({
                            "success": True,
                            "status": "opened",
                            "message": f"تم فتح المستند '{file_name}' في البرنامج الأصلي بنجاح.",
                            "path": str(target_path)
                        }, ensure_ascii=False).encode('utf-8'))
                        return

                    # البصمة لا تطابق السحابة -> تنزيل أحدث نسخة في الخلفية
                    entry, reg_keys = self._start_transfer(transfer_keys, downloading=True, opening=False)
                    threading.Thread(
                        target=self._open_worker,
                        args=(file_name, folder_name, cloud_fid or storage_path, expected_md5, target_path, False, True, entry, reg_keys),
                        daemon=True
                    ).start()
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "status": "downloading",
                        "message": f"جاري تنزيل أحدث نسخة من '{file_name}' وسيتم تشغيلها تلقائياً...",
                        "path": None
                    }, ensure_ascii=False).encode('utf-8'))
                    return

                # يتطلب تحديث اللقطة السحابية (>5s أو غياب md5) أو فحص بصمة ملف ضخم في الخيط الخلفي دون حجب HTTP
                entry, reg_keys = self._start_transfer(transfer_keys, downloading=True, opening=False)
                threading.Thread(
                    target=self._open_worker,
                    args=(file_name, folder_name, cloud_fid or storage_path, expected_md5, target_path, True, False, entry, reg_keys),
                    daemon=True
                ).start()
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "status": "downloading",
                    "message": f"جاري التحقق وتنزيل أحدث نسخة من '{file_name}' وسيتم تشغيلها تلقائياً...",
                    "path": None
                }, ensure_ascii=False).encode('utf-8'))
                return
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False).encode('utf-8'))
            return

        if path == '/unlock':
            file_name = self._sanitize_rel_param(params.get('file', [''])[0])
            folder_name = self._sanitize_rel_param(params.get('folder', [''])[0])
            storage_path = params.get('storage_path', [''])[0].strip()
            target_path = self._find_or_download_file(file_name, folder_name, storage_path)
            if target_path and target_path.exists():
                OfficeHandler.cleanup_orphaned_office_locks(str(target_path))
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True, "message": "تم فك قفل المستند بنجاح."}).encode('utf-8'))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"success": False, "error": "file not found"}).encode('utf-8'))
            return

        if path == '/reveal':
            file_name = self._sanitize_rel_param(params.get('file', [''])[0])
            folder_name = self._sanitize_rel_param(params.get('folder', [''])[0])
            storage_path = params.get('storage_path', [''])[0].strip()
            target_path = self._find_or_download_file(file_name, folder_name, storage_path)
            if target_path and target_path.exists():
                subprocess.Popen(['explorer.exe', f'/select,{str(target_path)}'])
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"success": False, "error": "file not found"}).encode('utf-8'))
            return

        if path == '/file-status':
            file_name = self._sanitize_rel_param(params.get('file', [''])[0])
            folder_name = self._sanitize_rel_param(params.get('folder', [''])[0])
            storage_path = params.get('storage_path', [''])[0].strip()
            target_path = self._find_local_file(file_name, folder_name, storage_path=storage_path)
            status_keys = self._build_transfer_keys(
                file_name, folder_name, storage_path=storage_path, target_path=target_path
            )
            is_downloading, is_opening = self._get_transfer_state(status_keys)
            if target_path and target_path.exists():
                try:
                    stat = target_path.stat()
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "exists": True,
                        "downloading": is_downloading,
                        "opening": is_opening,
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                        "last_sync_time": getattr(LocalBridgeHandler, "last_sync_time", 0.0),
                        "last_synced_file": getattr(LocalBridgeHandler, "last_synced_file", ""),
                        "path": str(target_path)
                    }, ensure_ascii=False).encode('utf-8'))
                except Exception as e:
                    self._set_headers(500)
                    self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
            else:
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "exists": False,
                    "downloading": is_downloading,
                    "opening": is_opening,
                    "last_sync_time": getattr(LocalBridgeHandler, "last_sync_time", 0.0),
                    "last_synced_file": getattr(LocalBridgeHandler, "last_synced_file", "")
                }, ensure_ascii=False).encode('utf-8'))
            return

        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "endpoint not found"}).encode('utf-8'))

    def _find_local_file(self, file_name, folder_name="", storage_path=""):
        if not self.sync_folder:
            return None

        base = Path(self.sync_folder)
        if not base.exists():
            return None

        raw_file = str(file_name or "").strip().rstrip('/\\')
        clean_file = self._norm_text(raw_file)
        if not clean_file:
            return None

        nf = self._norm_folder(folder_name)
        raw_nf = norm_rel(folder_name) if folder_name and folder_name not in ('__ALL__', 'المجلد العام', 'القسم العام') else ""

        snap_rel = None
        if storage_path and self.cloud_client and hasattr(self.cloud_client, "peek_snapshot"):
            snap = self.cloud_client.peek_snapshot()
            if snap and hasattr(snap, "file_ids") and storage_path in snap.file_ids:
                snap_rel = snap.file_ids[storage_path]
                cand_snap = base / snap_rel
                if cand_snap.exists() and cand_snap.is_file():
                    return cand_snap

        # 1. فحص المسار المباشر داخل المجلد المحدد
        if nf:
            for cand in (
                base / raw_nf / raw_file,
                base / nf / clean_file,
                base / raw_nf / clean_file,
                base / nf / raw_file,
            ):
                if cand.exists() and cand.is_file():
                    return cand

            target_k = norm_key(f"{nf}/{clean_file}")
            snap_k = norm_key(snap_rel) if snap_rel else None
            for root, dnames, fnames in os.walk(base):
                dnames[:] = [d for d in dnames if not d.startswith(".")]
                root_p = Path(root)
                rel_root = norm_rel(root_p.relative_to(base))
                for fn in fnames:
                    rel = f"{rel_root}/{fn}" if rel_root else fn
                    rk = norm_key(rel)
                    if rk == target_k or (snap_k and rk == snap_k):
                        return root_p / fn
            return None

        # 2. فحص المسار المباشر في جذر مجلد المزامنة (أو المجلد العام القديم)
        for cand in (base / raw_file, base / clean_file):
            if cand.exists() and cand.is_file():
                return cand
        if folder_name in ('القسم العام', 'المجلد العام'):
            legacy_cand = base / folder_name / clean_file
            if legacy_cand.exists() and legacy_cand.is_file():
                return legacy_cand

        # 3. بحث بتطبيع Unicode NFC وتجاهل حالة الأحرف (في الجذر ثم في المجلدات الفرعية عند عدم تحديد مجلد)
        target_root_k = norm_key(clean_file)
        snap_k = norm_key(snap_rel) if snap_rel else None
        allow_any_folder = (not folder_name or folder_name.strip() in ('__ALL__', ''))
        fallback_match = None
        for root, dnames, fnames in os.walk(base):
            dnames[:] = [d for d in dnames if not d.startswith(".")]
            root_p = Path(root)
            rel_root = norm_rel(root_p.relative_to(base))
            for fn in fnames:
                rel = f"{rel_root}/{fn}" if rel_root else fn
                rk = norm_key(rel)
                if rk == target_root_k or (snap_k and rk == snap_k):
                    return root_p / fn
                if allow_any_folder and fallback_match is None and norm_key(fn) == target_root_k:
                    fallback_match = root_p / fn

        return fallback_match

    def _open_worker(
        self,
        file_name,
        folder_name="",
        storage_path="",
        passed_md5="",
        initial_target=None,
        need_check=False,
        force_download=False,
        transfer_entry=None,
        transfer_keys=None,
    ):
        """التحقق والتنزيل الذري وتشغيل الملف بالبرنامج الأصلي في الخلفية دون حجب طلب /open"""
        try:
            target_path = initial_target
            should_download = bool(force_download)
            cloud_fid = storage_path
            expected_md5 = (passed_md5 or "").strip().lower()

            if need_check:
                if not expected_md5 and self.cloud_client and self.cloud_client.is_configured():
                    snap = self.cloud_client.peek_snapshot() if hasattr(self.cloud_client, "peek_snapshot") else None
                    snap_age = time.time() - float(getattr(snap, "taken_at", 0.0) or 0.0) if snap else 9999.0
                    if snap is None or not hasattr(snap, "files") or snap_age > 5.0:
                        if hasattr(self.cloud_client, "snapshot"):
                            fresh = self.cloud_client.snapshot(force=True)
                            if fresh is not None:
                                snap = fresh
                    if snap and hasattr(snap, "files"):
                        _, remote_info = self._find_remote_meta(snap, file_name, folder_name, storage_path)
                        if remote_info:
                            cloud_fid = remote_info.get("id") or cloud_fid
                            expected_md5 = str(remote_info.get("md5Checksum") or "").lower()

                if target_path is None or not target_path.exists():
                    should_download = True
                elif expected_md5:
                    try:
                        local_hash = self._calc_md5(target_path)
                        if local_hash != expected_md5 and not self._is_local_newer(target_path, expected_md5, local_hash):
                            should_download = True
                    except Exception:
                        should_download = True

            if should_download or target_path is None or not target_path.exists():
                target_path = self._find_or_download_file(
                    file_name, folder_name, cloud_fid or storage_path, force_download=True
                )
                if target_path and self.sync_folder:
                    try:
                        extra_k = norm_key(norm_rel(target_path.relative_to(Path(self.sync_folder))))
                        self._update_transfer(transfer_entry, transfer_keys, extra_keys=[extra_k])
                    except Exception:
                        pass
            else:
                self._update_transfer(transfer_entry, transfer_keys, downloading=False, opening=True)

            if target_path and target_path.exists():
                self._update_transfer(transfer_entry, transfer_keys, opening=True)
                OfficeHandler.open_native_file(str(target_path))
                if self.sync_engine and hasattr(self.sync_engine, 'watch_active_file'):
                    self.sync_engine.watch_active_file(str(target_path))
                print(f"[LocalBridge] Successfully opened '{file_name}' via background worker.")
        except Exception as e:
            print(f"[LocalBridge] Error opening '{file_name}' in background worker: {e}")
        finally:
            self._clear_transfer(transfer_entry, transfer_keys)

    def _download_and_open_worker(self, file_name, folder_name="", storage_path="", force_download=False):
        """واجهة متوافقة للتنزيل والتشغيل في الخلفية"""
        keys = self._build_transfer_keys(file_name, folder_name, storage_path=storage_path)
        entry, reg_keys = self._start_transfer(keys, downloading=True, opening=False)
        self._open_worker(
            file_name,
            folder_name,
            storage_path=storage_path,
            force_download=force_download,
            transfer_entry=entry,
            transfer_keys=reg_keys,
        )

    def _find_or_download_file(self, file_name, folder_name="", storage_path="", force_download=False):
        if not self.sync_folder:
            return None

        base = Path(self.sync_folder)
        clean_file = self._norm_text(file_name)
        nf = self._norm_folder(folder_name)

        existing_local = self._find_local_file(file_name, folder_name, storage_path=storage_path)
        if existing_local is not None and not force_download:
            return existing_local

        # إذا لم يكن موجوداً محلياً أو طُلب التحديث القسري من السحابة، جلبه فوراً عبر مجلد مؤقت وتطبيقه بأمان
        if self.cloud_client:
            temp_dl = None
            try:
                safe_sp = storage_path
                canonical_rel = None
                snap = self.cloud_client.peek_snapshot() if hasattr(self.cloud_client, "peek_snapshot") else None
                if snap and hasattr(snap, "files"):
                    r_rel, r_meta = self._find_remote_meta(snap, file_name, folder_name, safe_sp)
                    if r_meta:
                        canonical_rel = r_rel
                        if not safe_sp:
                            safe_sp = r_meta.get("id") or ""

                if not safe_sp and hasattr(self.cloud_client, 'get_file_by_name'):
                    f_info = self.cloud_client.get_file_by_name(clean_file, folder=nf)
                    if f_info:
                        safe_sp = f_info.get('storage_path') or safe_sp
                        canonical_rel = canonical_rel or f_info.get('file_path')

                if existing_local is not None:
                    local_file = existing_local
                elif canonical_rel:
                    local_file = base / canonical_rel
                    local_file.parent.mkdir(parents=True, exist_ok=True)
                else:
                    dest_dir = base / nf if nf else base
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    local_file = dest_dir / clean_file

                if hasattr(self.cloud_client, 'download_file'):
                    temp_dir = base / ".sync_temp"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_dl = temp_dir / f"bridge_{int(time.time()*1000)}_{local_file.name}.tmp"
                    res = self.cloud_client.download_file(local_file.name, str(temp_dl), storage_path=safe_sp)
                    success = res[0] if isinstance(res, tuple) else bool(res)
                    if success and temp_dl.exists():
                        rel_calc = norm_rel(local_file.relative_to(base))
                        if self.sync_engine:
                            self.sync_engine._mark_self_op(rel_calc, seconds=5)
                        applied = OfficeHandler.safe_apply_file(str(local_file), str(temp_dl))
                        if applied and local_file.exists():
                            try:
                                if self.sync_engine:
                                    st_after = local_file.stat()
                                    md5 = self._calc_md5(local_file)
                                    self.sync_engine._save_state(rel_calc, md5, st_after.st_size, st_after.st_mtime, safe_sp, md5, status="synced")
                            except Exception:
                                pass
                            if self.sync_engine:
                                self.sync_engine.clear_self_op(rel_calc)
                            return local_file
            except Exception as dl_err:
                print(f"[LocalBridge] Cloud download on-demand failed: {dl_err}")
            finally:
                if temp_dl and temp_dl.exists():
                    try:
                        temp_dl.unlink(missing_ok=True)
                    except Exception:
                        pass

        return existing_local

    def log_message(self, format, *args):
        pass


def register_sharecoc_protocol():
    """تسجيل بروتوكول sharecoc:// في سجل نظام ويندوز (Windows Registry)"""
    try:
        if getattr(sys, 'frozen', False):
            target_exe = sys.executable
        else:
            installed_exe = Path(os.environ.get('LOCALAPPDATA', '')) / "Programs" / "ShareCOC" / "share coc.exe"
            desktop_exe = Path(os.environ.get('USERPROFILE', '')) / "OneDrive" / "Desktop" / "share coc.exe"
            if installed_exe.exists():
                target_exe = str(installed_exe)
            elif desktop_exe.exists():
                target_exe = str(desktop_exe)
            else:
                target_exe = sys.executable

        key_path = r"Software\Classes\sharecoc"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Share COC Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            with winreg.CreateKey(key, r"shell\open\command") as cmd_key:
                winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, f'"{target_exe}" --open "%1"')
        print("[LocalBridge] Registered sharecoc:// protocol successfully.")
    except Exception as e:
        print(f"[LocalBridge] Failed to register protocol: {e}")


def start_local_bridge(sync_folder, cloud_client=None, sync_engine=None, show_window_callback=None):
    """تشغيل خادم الجسر المحلي في خلفية التطبيق"""
    LocalBridgeHandler.sync_folder = sync_folder
    LocalBridgeHandler.cloud_client = cloud_client
    LocalBridgeHandler.sync_engine = sync_engine
    LocalBridgeHandler.show_window_callback = show_window_callback

    threading.Thread(target=register_sharecoc_protocol, daemon=True).start()

    def run_server():
        try:
            server = ThreadingHTTPServer(('0.0.0.0', BRIDGE_PORT), LocalBridgeHandler)
            print(f"[LocalBridge] Running on http://0.0.0.0:{BRIDGE_PORT}")
            server.serve_forever()
        except OSError as e:
            try:
                server = ThreadingHTTPServer(('127.0.0.1', BRIDGE_PORT), LocalBridgeHandler)
                print(f"[LocalBridge] Running on http://127.0.0.1:{BRIDGE_PORT}")
                server.serve_forever()
            except OSError as e2:
                print(f"[LocalBridge] Port {BRIDGE_PORT} is already in use: {e2}")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
