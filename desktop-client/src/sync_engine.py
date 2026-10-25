"""
تبادل الملفات – File Exchange System
محرك المزامنة الثنائي ومراقبة ملفات Office المباشرة (Sync Engine)
يدعم سحابة Cloudflare R2 (10GB مجانية + نقل بيانات غير محدود 0$ Egress) وسحابة Supabase
"""
import os
import time
import hashlib
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from office_handler import OfficeHandler
from conflict_manager import ConflictManager

class LocalFolderWatcher(FileSystemEventHandler):
    def __init__(self, sync_engine):
        super().__init__()
        self.sync_engine = sync_engine
        self.debounce_timers = {}

    def on_modified(self, event):
        if event.is_directory:
            return
        self._handle_event(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_event(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        self.sync_engine.on_local_file_deleted(event.src_path)

    def _handle_event(self, filepath):
        filename = os.path.basename(filepath)

        # تجاهل ملفات القفل والمؤقتة لـ Office
        if filename.startswith("~$") or filename.endswith(".tmp") or filename.endswith("~"):
            return

        # رصد أحداث قفل قواعد بيانات Access (.laccdb)
        if filename.endswith(".laccdb") or filename.endswith(".ldb"):
            db_name = filename.replace(".laccdb", ".accdb").replace(".ldb", ".mdb")
            print(f"[ACCESS MONITOR] ملف قفل أكسس نشط: {filename} للقاعدة {db_name}")
            return

        # تطبيق Debounce لتجنب تكرار الأحداث أثناء الحفظ المتكرر
        if filepath in self.debounce_timers:
            self.debounce_timers[filepath].cancel()

        timer = threading.Timer(1.2, self.sync_engine.on_local_file_saved, [filepath])
        self.debounce_timers[filepath] = timer
        timer.start()

class SyncEngine:
    def __init__(self, sync_folder, cloud_client, local_state_mgr, device_id, device_name, username):
        self.sync_folder = Path(sync_folder)
        self.sync_folder.mkdir(parents=True, exist_ok=True)
        self.client = cloud_client  # إما CloudflareR2Client أو SupabaseClient
        self.state_mgr = local_state_mgr
        self.device_id = device_id
        self.device_name = device_name
        self.username = username

        self.observer = Observer()
        self.is_running = False
        self.sync_listeners = []
        self._is_syncing_remote = False

    def register_status_listener(self, callback):
        self.sync_listeners.append(callback)

    def notify_status(self, status_data):
        for cb in self.sync_listeners:
            try:
                cb(status_data)
            except Exception:
                pass

    def scan_initial_local_files(self):
        """فحص المجلد المشترك وإدراج كافة الملفات الحقيقية الموجودة فيه وفي مجلداته الفرعية تلقائياً"""
        try:
            for item in self.sync_folder.rglob("*"):
                if item.is_file():
                    if ".trash" in item.parts or item.name.startswith("."):
                        continue
                    filename = item.name
                    if filename.startswith("~$") or filename.endswith(".tmp") or filename.endswith(".laccdb") or filename.endswith(".ldb"):
                        continue
                    rel_path = str(item.relative_to(self.sync_folder)).replace("\\", "/")
                    file_size = item.stat().st_size
                    existing = self.state_mgr.get_file_state(rel_path)
                    if not existing:
                        file_hash = self.calculate_hash(str(item))
                        self.state_mgr.set_file_state(rel_path, filename, file_hash, file_size, 'synced')
        except Exception:
            pass

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        
        self.scan_initial_local_files()

        handler = LocalFolderWatcher(self)
        self.observer.schedule(handler, str(self.sync_folder), recursive=True)
        self.observer.start()

        threading.Thread(target=self._background_sync_loop, daemon=True).start()

    def stop(self):
        self.is_running = False
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()

    def calculate_hash(self, filepath):
        sha = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    def on_local_file_deleted(self, filepath):
        path = Path(filepath)
        try:
            rel_path = str(path.relative_to(self.sync_folder)).replace("\\", "/")
        except Exception:
            rel_path = str(path.name)
        with self.state_mgr._get_connection() as conn:
            conn.execute("DELETE FROM local_files WHERE relative_path = ? OR file_name = ?", (rel_path, path.name))
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ?", (rel_path,))
        self.notify_status({"event": "deleted", "file": rel_path, "status": "تم حذف الملف محلياً"})

    def on_local_file_saved(self, filepath):
        """يتم استدعاؤها عند ضغط Ctrl+S واكتمال حفظ الملف في Word أو Excel أو Access"""
        if self._is_syncing_remote:
            return

        path = Path(filepath)
        if not path.exists():
            return

        rel_path = str(path.relative_to(self.sync_folder)).replace("\\", "/")

        # التحقق من تحرر مقبض الملف من Office
        attempts = 0
        while OfficeHandler.is_file_locked_by_os(filepath) and attempts < 12:
            time.sleep(0.4)
            attempts += 1

        if OfficeHandler.is_file_locked_by_os(filepath):
            return

        file_size = os.path.getsize(filepath)
        file_hash = self.calculate_hash(filepath)

        current_state = self.state_mgr.get_file_state(rel_path)
        if current_state and current_state.get('sha256_hash') == file_hash and current_state.get('sync_status') == 'synced':
            return

        self.state_mgr.set_file_state(rel_path, path.name, file_hash, file_size, 'syncing')
        self.notify_status({"event": "syncing", "file": path.name, "status": "جارٍ الرفع السحابي..."})

        self.state_mgr.enqueue_upload(rel_path, str(filepath), file_hash)
        self.process_upload_queue()

    def process_upload_queue(self):
        """معالجة طابور الرفع التلقائي إلى سحابة Cloudflare R2"""
        if not self.client or not self.client.is_configured():
            for item in self.state_mgr.get_pending_uploads():
                self.state_mgr.set_file_state(
                    item['relative_path'], os.path.basename(item['local_abs_path']), 
                    item['sha256_hash'], os.path.getsize(item['local_abs_path']), 'synced'
                )
                self.state_mgr.dequeue_upload(item['relative_path'])
            return

        pending = self.state_mgr.get_pending_uploads()
        for item in pending:
            rel_path = item['relative_path']
            local_path = item['local_abs_path']
            file_hash = item['sha256_hash']

            if not os.path.exists(local_path):
                self.state_mgr.dequeue_upload(rel_path)
                continue

            try:
                # الرفع السحابي عبر Cloudflare R2
                if hasattr(self.client, 'upload_file'):
                    success, msg = self.client.upload_file(
                        local_path, 
                        file_name=os.path.basename(local_path),
                        user_name=self.username,
                        device_name=self.device_name
                    )
                else:
                    storage_dest = f"shared/{rel_path}"
                    success = self.client.upload_file_to_storage(local_path, storage_dest)

                if success:
                    file_size = os.path.getsize(local_path)
                    self.state_mgr.set_file_state(rel_path, os.path.basename(local_path), file_hash, file_size, 'synced')
                    self.state_mgr.dequeue_upload(rel_path)
                    self.notify_status({"event": "synced", "file": os.path.basename(local_path), "status": "تمت المزامنة بنجاح في R2"})
                else:
                    self.state_mgr.mark_upload_failed(rel_path, "بانتظار الاتصال بالسحابة")
                    self.notify_status({"event": "pending", "file": os.path.basename(local_path), "status": "محفوظ محلياً"})
            except Exception as e:
                self.state_mgr.mark_upload_failed(rel_path, str(e))

    def pull_remote_changes(self):
        """فحص التحديثات الجديدة من سحابة Cloudflare R2 وتنزيلها بأمان"""
        if not self.client or not self.client.is_configured():
            return

        try:
            if hasattr(self.client, 'list_files'):
                remote_files = self.client.list_files()
            else:
                remote_files = self.client.list_accessible_files()

            for r_file in remote_files:
                file_name = r_file['file_name']
                local_path = self.sync_folder / file_name

                if local_path.exists() and OfficeHandler.is_file_locked_by_os(str(local_path)):
                    continue

                local_state = self.state_mgr.get_file_state(file_name)
                needs_download = False

                if not local_path.exists():
                    needs_download = True
                elif local_state is None:
                    needs_download = True

                if needs_download:
                    self._is_syncing_remote = True
                    try:
                        self.notify_status({"event": "syncing", "file": file_name, "status": "تنزيل من R2..."})
                        if hasattr(self.client, 'download_file'):
                            success, msg = self.client.download_file(file_name, str(local_path))
                        else:
                            success = self.client.download_file_from_storage(r_file.get('storage_path', f"shared/{file_name}"), str(local_path))

                        if success:
                            file_size = os.path.getsize(str(local_path))
                            file_hash = self.calculate_hash(str(local_path))
                            self.state_mgr.set_file_state(file_name, file_name, file_hash, file_size, 'synced')
                            self.notify_status({"event": "synced", "file": file_name, "status": "محدث من R2"})
                    finally:
                        self._is_syncing_remote = False
        except Exception as e:
            print(f"[خطأ في جلب التحديثات من R2]: {e}")

    def _background_sync_loop(self):
        while self.is_running:
            self.scan_initial_local_files()
            self.process_upload_queue()
            self.pull_remote_changes()
            time.sleep(4)
