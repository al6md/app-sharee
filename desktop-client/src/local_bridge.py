"""
تبادل الملفات – File Exchange System
خادم الجسر المحلي لربط لوحة التحكم (الويب / الجوال) ببرامج Microsoft Office الأصلية على الحاسوب
Local Companion Bridge Server (Port 18290)
"""
import os
import sys
import json
import urllib.parse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import winreg

from office_handler import OfficeHandler

BRIDGE_PORT = 18290

class LocalBridgeHandler(BaseHTTPRequestHandler):
    sync_folder = None
    cloud_client = None

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
                "version": "2.0",
                "sync_folder": str(self.sync_folder) if self.sync_folder else None
            }
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
            return

        if path == '/open':
            file_name = params.get('file', [''])[0].strip()
            folder_name = params.get('folder', [''])[0].strip()

            if not file_name:
                self._set_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "file parameter required"}).encode('utf-8'))
                return

            try:
                target_path = self._find_or_download_file(file_name, folder_name)
                if not target_path or not target_path.exists():
                    self._set_headers(404)
                    self.wfile.write(json.dumps({
                        "success": False, 
                        "error": f"الملف '{file_name}' غير موجود ولم نتمكن من تنزيله."
                    }, ensure_ascii=False).encode('utf-8'))
                    return

                # تشغيل البرنامج الأصلي عبر OfficeHandler
                OfficeHandler.open_native_file(str(target_path))

                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "message": f"تم فتح المستند '{file_name}' في البرنامج الأصلي بنجاح.",
                    "path": str(target_path)
                }, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False).encode('utf-8'))
            return

        if path == '/reveal':
            file_name = params.get('file', [''])[0].strip()
            folder_name = params.get('folder', [''])[0].strip()
            target_path = self._find_or_download_file(file_name, folder_name)
            if target_path and target_path.exists():
                os.system(f'explorer.exe /select,"{str(target_path)}"')
                self._set_headers(200)
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"success": False, "error": "file not found"}).encode('utf-8'))
            return

        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "endpoint not found"}).encode('utf-8'))

    def _find_or_download_file(self, file_name, folder_name=""):
        if not self.sync_folder:
            return None

        base = Path(self.sync_folder)

        # 1. فحص المسار المباشر داخل المجلد المحدد
        if folder_name and folder_name != '__ALL__':
            candidate = base / folder_name / file_name
            if candidate.exists():
                return candidate

        # 2. فحص المسار المباشر في جذر مجلد المزامنة
        candidate = base / file_name
        if candidate.exists():
            return candidate

        # 3. بحث متكرر عن الملف في المجلدات الفرعية
        for sub in base.rglob(file_name):
            if sub.is_file():
                return sub

        # 4. إذا لم يكن موجوداً محلياً، جلبه من السحابة فوراً
        if self.cloud_client:
            try:
                dest_dir = base / folder_name if (folder_name and folder_name != '__ALL__') else base
                dest_dir.mkdir(parents=True, exist_ok=True)
                local_file = dest_dir / file_name

                storage_path = f"shared/{folder_name}/{file_name}" if (folder_name and folder_name != '__ALL__') else f"shared/{file_name}"
                downloaded = self.cloud_client.download_file(storage_path, str(local_file))
                if downloaded and local_file.exists():
                    return local_file

                # تجربة مسار بديل بدون مجلد
                alt_storage_path = f"shared/{file_name}"
                downloaded2 = self.cloud_client.download_file(alt_storage_path, str(local_file))
                if downloaded2 and local_file.exists():
                    return local_file
            except Exception as dl_err:
                print(f"[LocalBridge] Cloud download on-demand failed: {dl_err}")

        return None

    def log_message(self, format, *args):
        # صامت لتجنب إغراق شاشات السجلات
        pass


def register_sharecoc_protocol():
    """تسجيل بروتوكول sharecoc:// في سجل نظام ويندوز (Windows Registry)"""
    try:
        if getattr(sys, 'frozen', False):
            target_exe = sys.executable
        else:
            # مسار النسخة القابلة للتشغيل المعتمدة
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


def start_local_bridge(sync_folder, cloud_client=None):
    """تشغيل خادم الجسر المحلي في خلفية التطبيق"""
    LocalBridgeHandler.sync_folder = sync_folder
    LocalBridgeHandler.cloud_client = cloud_client

    # تسجيل البروتوكول في الريجستري أولاً
    register_sharecoc_protocol()

    def run_server():
        try:
            server = HTTPServer(('127.0.0.1', BRIDGE_PORT), LocalBridgeHandler)
            print(f"[LocalBridge] Running on http://127.0.0.1:{BRIDGE_PORT}")
            server.serve_forever()
        except OSError as e:
            # المنفذ مستخدم مسبقاً من نسخة سابقة تعمل بالفعل
            print(f"[LocalBridge] Port {BRIDGE_PORT} is already in use (app already running): {e}")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
