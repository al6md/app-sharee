"""
تبادل الملفات – File Exchange System
خادم الجسر المحلي لربط لوحة التحكم (الويب / الجوال) ببرامج Microsoft Office الأصلية على الحاسوب
Local Companion Bridge Server (Port 18290)
"""
import os
import sys
import json
import subprocess
import urllib.parse
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import winreg

from office_handler import OfficeHandler

BRIDGE_PORT = 18290


class LocalBridgeHandler(BaseHTTPRequestHandler):
    sync_folder = None
    cloud_client = None
    sync_engine = None
    show_window_callback = None

    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', f'{content_type}; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == '/ping':
            self._set_headers(200)
            data = {
                "status": "ok",
                "app": "share coc",
                "version": "3.0",
                "pid": os.getpid(),
                "sync_folder": str(self.sync_folder) if self.sync_folder else None
            }
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
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
                if self.sync_engine:
                    self.sync_engine.wake(delay=0.05)
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))
            return

        if path == '/open':
            file_name = params.get('file', [''])[0].strip()
            folder_name = params.get('folder', [''])[0].strip()
            storage_path = params.get('storage_path', [''])[0].strip()

            if not file_name:
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "file parameter required"}).encode('utf-8'))
                return

            try:
                # 1. إذا كان الملف موجوداً محلياً، فتحه فوراً بالبرنامج الأصلي
                target_path = self._find_local_file(file_name, folder_name)
                if target_path and target_path.exists():
                    OfficeHandler.open_native_file(str(target_path))
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "status": "opened",
                        "message": f"تم فتح المستند '{file_name}' في البرنامج الأصلي بنجاح.",
                        "path": str(target_path)
                    }, ensure_ascii=False).encode('utf-8'))
                    return

                # 2. إذا لم يكن موجوداً محلياً، بدء التنزيل في خيط خلفي والرد فوراً للمتصفح لتفادي انقطاع الاتصال
                if self.cloud_client:
                    threading.Thread(
                        target=self._download_and_open_worker,
                        args=(file_name, folder_name, storage_path),
                        daemon=True
                    ).start()
                    self._set_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "status": "downloading",
                        "message": f"جاري تنزيل '{file_name}' من السحابة وسيتم تشغيله تلقائياً في البرنامج الأصلي فور اكتماله...",
                        "path": None
                    }, ensure_ascii=False).encode('utf-8'))
                    return

                self._set_headers(404)
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"الملف '{file_name}' غير موجود محلياً ولا يتوفر اتصال سحابي."
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False).encode('utf-8'))
            return

        if path == '/unlock':
            file_name = params.get('file', [''])[0].strip()
            folder_name = params.get('folder', [''])[0].strip()
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
            file_name = params.get('file', [''])[0].strip()
            folder_name = params.get('folder', [''])[0].strip()
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

        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "endpoint not found"}).encode('utf-8'))

    def _find_local_file(self, file_name, folder_name=""):
        if not self.sync_folder:
            return None

        import re
        def clean_bidi(s):
            return re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(s)).strip()

        clean_file = clean_bidi(file_name)
        base = Path(self.sync_folder)
        norm_folder = folder_name.replace("\\", "/").strip("/") if folder_name and folder_name not in ('__ALL__', 'المجلد العام') else ""

        # 1. فحص المسار المباشر داخل المجلد المحدد (يدعم المجلدات الفرعية المتداخلة)
        if norm_folder:
            clean_folder = "/".join(clean_bidi(p) for p in norm_folder.split("/"))
            for cand in [base / norm_folder / file_name, base / clean_folder / clean_file, base / norm_folder / clean_file]:
                if cand.exists() and cand.is_file():
                    return cand

        # 2. فحص المسار المباشر في جذر مجلد المزامنة
        for cand in [base / file_name, base / clean_file]:
            if cand.exists() and cand.is_file():
                return cand

        # 3. بحث متكرر عن الملف في المجلدات الفرعية
        target_lower = clean_file.lower()
        for sub in base.rglob("*"):
            if sub.is_file() and ".trash" not in sub.parts:
                if sub.name == file_name or clean_bidi(sub.name).lower() == target_lower:
                    return sub

        return None

    def _download_and_open_worker(self, file_name, folder_name="", storage_path=""):
        """تنزيل الملف في الخلفية وتشغيله بالبرنامج الأصلي فور اكتماله بدون تجميد اتصال الويب"""
        try:
            target_path = self._find_or_download_file(file_name, folder_name, storage_path)
            if target_path and target_path.exists():
                OfficeHandler.open_native_file(str(target_path))
                print(f"[LocalBridge] Successfully opened '{file_name}' via background worker.")
        except Exception as e:
            print(f"[LocalBridge] Error opening '{file_name}' in background worker: {e}")

    def _find_or_download_file(self, file_name, folder_name="", storage_path=""):
        if not self.sync_folder:
            return None

        import re
        def clean_bidi(s):
            return re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(s)).strip()

        clean_file = clean_bidi(file_name)
        base = Path(self.sync_folder)
        norm_folder = folder_name.replace("\\", "/").strip("/") if folder_name and folder_name not in ('__ALL__', 'المجلد العام') else ""

        # 1. فحص المسار المباشر داخل المجلد المحدد (يدعم المجلدات الفرعية المتداخلة)
        if norm_folder:
            clean_folder = "/".join(clean_bidi(p) for p in norm_folder.split("/"))
            for cand in [base / norm_folder / file_name, base / clean_folder / clean_file, base / norm_folder / clean_file]:
                if cand.exists() and cand.is_file():
                    return cand

        # 2. فحص المسار المباشر في جذر مجلد المزامنة
        for cand in [base / file_name, base / clean_file]:
            if cand.exists() and cand.is_file():
                return cand

        # 3. بحث متكرر عن الملف في المجلدات الفرعية
        target_lower = clean_file.lower()
        for sub in base.rglob("*"):
            if sub.is_file() and ".trash" not in sub.parts:
                if sub.name == file_name or clean_bidi(sub.name).lower() == target_lower:
                    return sub

        # 4. إذا لم يكن موجوداً محلياً، جلبه من السحابة فوراً إلى نفس المجلد الفرعي
        if self.cloud_client:
            try:
                dest_dir = base / norm_folder if norm_folder else base
                dest_dir.mkdir(parents=True, exist_ok=True)
                local_file = dest_dir / file_name

                safe_sp = storage_path
                if not safe_sp and hasattr(self.cloud_client, 'get_file_by_name'):
                    f_info = self.cloud_client.get_file_by_name(file_name, folder=norm_folder)
                    if f_info and f_info.get('storage_path'):
                        safe_sp = f_info['storage_path']

                if hasattr(self.cloud_client, 'download_file'):
                    res = self.cloud_client.download_file(file_name, str(local_file), storage_path=safe_sp)
                    success = res[0] if isinstance(res, tuple) else bool(res)
                    if success and local_file.exists():
                        if self.sync_engine:
                            self.sync_engine.wake(delay=1.0)
                        return local_file
            except Exception as dl_err:
                print(f"[LocalBridge] Cloud download on-demand failed: {dl_err}")

        return None

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
            server = ThreadingHTTPServer(('127.0.0.1', BRIDGE_PORT), LocalBridgeHandler)
            print(f"[LocalBridge] Running on http://127.0.0.1:{BRIDGE_PORT}")
            server.serve_forever()
        except OSError as e:
            print(f"[LocalBridge] Port {BRIDGE_PORT} is already in use: {e}")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
