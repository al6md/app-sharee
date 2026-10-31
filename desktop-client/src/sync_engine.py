# -*- coding: utf-8 -*-
"""
تبادل الملفات – File Exchange System
محرك المزامنة الثنائي (Sync Engine) – الإصدار 4.0 المحكم

مبادئ التصميم:
  • أولوية ذكية للملفات الصغيرة والمتوسطة أولاً (Small-Files-First Priority Queue) فلا يتأخر
    أي مستند Word أو Excel أو PDF بسبب قاعدة بيانات Access ضخمة.
  • رفع فوري ومباشر (sync_file_now) للملفات والمجلدات التي يضيفها المستخدم من الواجهة مع
    شريط تقدم لحظي حقيقي، وحفظ فوري لمعرّف السحابة وبصمة MD5.
  • تنظيف تلقائي لشواهد الحذف (Tombstones) فور تأكيد غيابها من السحابة لمنع الحذف العكسي.
  • تخزين مؤقت لبصمة MD5 حتى للملفات الضخمة لتفادي إعادة قراءة مئات الميجابايتات في كل دورة.
"""
import os
import sys
import json
import time
import shutil
import hashlib
import threading
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from office_handler import OfficeHandler
from gdrive_client import is_ignored_name, norm_rel, _safe_log
from lan_sync import LanSyncService

CYCLE_SECONDS = 8
LEGACY_GENERAL_DEPT = "القسم العام"


def _iso_to_ts(value):
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _is_under(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


class LocalFolderWatcher(FileSystemEventHandler):
    """مراقب المجلد المحلي: يرصد الحفظ الفوري (Ctrl+S) وإغلاق برامج Office لتشغيل الرفع المباشر فورياً مع منع الشواهد الزائفة أثناء الحفظ الذري"""

    def __init__(self, sync_engine):
        super().__init__()
        self.engine = sync_engine
        self._pending_deletes = {}
        self._pending_deletes_lock = threading.Lock()

    def _rel(self, p):
        try:
            return norm_rel(Path(p).relative_to(self.engine.sync_folder))
        except Exception:
            return None

    def _relevant(self, rel):
        if not rel:
            return False
        parts = rel.split("/")
        if any(x.startswith(".") for x in parts):
            return False
        return not is_ignored_name(parts[-1])

    def _schedule_verify_delete(self, rel, is_directory):
        """تأخير تأكيد الحذف لمدة ثانية واحدة للتحقق من عدم كونه حفظاً ذرياً لبرامج Office (تسمية ملف مؤقت)"""
        def _verify():
            with self._pending_deletes_lock:
                self._pending_deletes.pop(rel, None)
            target = self.engine.sync_folder / rel
            if target.exists():
                # الملف ما زال موجوداً على القرص (استبدال ذري لـ Office أو تعديل سريع)
                self.engine.clear_tombstone(rel)
                if not is_directory:
                    self.engine.queue_fast_upload(rel, delay=0.1)
            else:
                # الملف محذوف فعلياً بعد انقضاء المهلة -> حذف صريح من المستخدم
                self.engine.note_local_delete(rel, is_folder=is_directory, from_watcher=True)

        with self._pending_deletes_lock:
            old_timer = self._pending_deletes.pop(rel, None)
            if old_timer:
                try:
                    old_timer.cancel()
                except Exception:
                    pass
            t = threading.Timer(1.0, _verify)
            t.daemon = True
            self._pending_deletes[rel] = t
            t.start()

    def on_any_event(self, event):
        try:
            etype = event.event_type
            if etype in ("opened", "closed", "closed_no_write"):
                return
            src_rel = self._rel(event.src_path)

            # رصد تحرير أقفال Office (مثل إغلاق Access أو Word أو Excel)
            if etype == "deleted" and src_rel:
                fn = src_rel.split("/")[-1].lower()
                parent_dir = src_rel.rsplit("/", 1)[0] if "/" in src_rel else ""
                main_rel = None
                if fn.endswith(".laccdb") or fn.endswith(".ldb"):
                    stem = fn[:-7] if fn.endswith(".laccdb") else fn[:-4]
                    for ext in (".accdb", ".mdb"):
                        cand = f"{parent_dir}/{stem}{ext}" if parent_dir else f"{stem}{ext}"
                        if (self.engine.sync_folder / cand).exists():
                            main_rel = cand
                            break
                elif fn.startswith("~$") and len(fn) > 2:
                    real_name = fn[2:]
                    cand = f"{parent_dir}/{real_name}" if parent_dir else real_name
                    if (self.engine.sync_folder / cand).exists():
                        main_rel = cand

                if main_rel:
                    with self._pending_deletes_lock:
                        pt = self._pending_deletes.pop(main_rel, None)
                        if pt:
                            try:
                                pt.cancel()
                            except Exception:
                                pass
                    self.engine.clear_tombstone(main_rel)
                    self.engine.queue_fast_upload(main_rel, delay=0.15)
                    return

            if etype in ("deleted", "moved") and self._relevant(src_rel):
                self._schedule_verify_delete(src_rel, event.is_directory)

            if etype in ("created", "modified", "moved"):
                dest = getattr(event, "dest_path", None) or event.src_path
                dest_rel = self._rel(dest)
                if self._relevant(dest_rel):
                    # إلغاء أي حذف مؤقت معلق لنفس المسار فوراً
                    with self._pending_deletes_lock:
                        pt = self._pending_deletes.pop(dest_rel, None)
                        if pt:
                            try:
                                pt.cancel()
                            except Exception:
                                pass
                    self.engine.clear_tombstone(dest_rel)
                    if not event.is_directory:
                        # تشغيل الرفع الفوري فائق السرعة لرصد وحفظ التعديلات فورياً في أقل من 150ms
                        self.engine.queue_fast_upload(dest_rel, delay=0.15)
                    else:
                        self.engine.wake(delay=0.3)
        except Exception as e:
            _safe_log(f"[Watcher error]: {e}")


class SyncEngine:
    def __init__(self, sync_folder, cloud_client, local_state_mgr, device_id, device_name, username):
        self.sync_folder = Path(sync_folder)
        self.sync_folder.mkdir(parents=True, exist_ok=True)
        self.client = cloud_client
        self.state_mgr = local_state_mgr
        self.device_id = device_id
        self.device_name = device_name
        self.username = username
        if hasattr(self.client, "sync_folder"):
            self.client.sync_folder = self.sync_folder

        self.observer = Observer()
        self.is_running = False
        self.sync_listeners = []
        self._wake_event = threading.Event()
        self._wake_at = 0.0
        self._wake_lock = threading.Lock()
        self._self_ops = {}          # rel -> expiry (عمليات المحرك نفسه لتجاهلها في المراقب)
        self._self_ops_lock = threading.Lock()
        self._fast_upload_timers = {}
        self._fast_upload_lock = threading.Lock()
        self._watched_active_files = set()
        self._worker = None
        self.last_sync_ok = None
        self.last_sync_time = None
        self.last_error = None
        self._init_schema()
        self.lan_sync = LanSyncService(
            sync_folder=self.sync_folder,
            device_id=self.device_id,
            device_name=self.device_name,
            sync_engine=self,
            local_state_mgr=self.state_mgr
        )

    # ------------------------------------------------------------------ #
    # الحالة المحلية
    # ------------------------------------------------------------------ #
    def _init_schema(self):
        with self.state_mgr._get_connection() as conn:
            for ddl in ("ALTER TABLE local_files ADD COLUMN remote_md5 TEXT",
                        "ALTER TABLE local_files ADD COLUMN local_mtime REAL"):
                try:
                    conn.execute(ddl)
                except Exception:
                    pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tombstones (
                    rel_path TEXT PRIMARY KEY,
                    is_folder INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                )
            """)

    def _load_states(self):
        with self.state_mgr._get_connection() as conn:
            rows = conn.execute("SELECT * FROM local_files").fetchall()
        return {norm_rel(r["relative_path"]): dict(r) for r in rows}

    def _save_state(self, rel, md5, size, mtime, remote_id, remote_md5, status="synced"):
        rel = norm_rel(rel)
        now = datetime.now().isoformat()
        with self.state_mgr._get_connection() as conn:
            conn.execute("""
                INSERT INTO local_files (relative_path, file_name, sha256_hash, file_size, server_file_id,
                                         sync_status, last_synced_at, last_modified_local, remote_md5, local_mtime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    file_name = excluded.file_name,
                    sha256_hash = CASE WHEN excluded.sha256_hash != '' THEN excluded.sha256_hash ELSE local_files.sha256_hash END,
                    file_size = excluded.file_size,
                    server_file_id = COALESCE(excluded.server_file_id, local_files.server_file_id),
                    sync_status = excluded.sync_status,
                    last_synced_at = excluded.last_synced_at,
                    last_modified_local = excluded.last_modified_local,
                    remote_md5 = COALESCE(excluded.remote_md5, local_files.remote_md5),
                    local_mtime = COALESCE(excluded.local_mtime, local_files.local_mtime)
            """, (rel, rel.split("/")[-1], md5 or "", int(size or 0), remote_id, status, now,
                  datetime.fromtimestamp(mtime).isoformat() if mtime else now, remote_md5, mtime))

    def _set_status(self, rel, status):
        with self.state_mgr._get_connection() as conn:
            conn.execute("UPDATE local_files SET sync_status = ? WHERE relative_path = ?", (status, norm_rel(rel)))

    def _delete_state(self, rel):
        rel = norm_rel(rel)
        with self.state_mgr._get_connection() as conn:
            conn.execute("DELETE FROM local_files WHERE relative_path = ?", (rel,))
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ?", (rel,))

    def _load_tombstones(self):
        with self.state_mgr._get_connection() as conn:
            rows = conn.execute("SELECT * FROM tombstones").fetchall()
        return {norm_rel(r["rel_path"]): dict(r) for r in rows}

    def _drop_tombstone(self, rel):
        rel = norm_rel(rel)
        with self.state_mgr._get_connection() as conn:
            conn.execute("DELETE FROM tombstones WHERE rel_path = ?", (rel,))

    def clear_tombstone(self, rel):
        """إزالة أي شاهد حذف يطابق المسار أو أحد آبائه أو أبنائه (عند إضافة ملف أو مجلد جديد)"""
        rel = norm_rel(rel)
        if not rel:
            return
        try:
            with self.state_mgr._get_connection() as conn:
                parts = rel.split("/")
                ancestors = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
                for anc in ancestors:
                    conn.execute("DELETE FROM tombstones WHERE rel_path = ?", (anc,))
                conn.execute("DELETE FROM tombstones WHERE rel_path LIKE ?", (f"{rel}/%",))
        except Exception:
            pass

    def _known_dirs(self):
        raw = self.state_mgr.get_setting("known_remote_dirs_json", "")
        try:
            return set(json.loads(raw)) if raw else set()
        except Exception:
            return set()

    def _save_known_dirs(self, dirs):
        self.state_mgr.set_setting("known_remote_dirs_json", json.dumps(sorted(dirs), ensure_ascii=False))

    # ------------------------------------------------------------------ #
    # واجهة عامة يستدعيها gui.py
    # ------------------------------------------------------------------ #
    def register_status_listener(self, callback):
        self.sync_listeners.append(callback)

    def notify_status(self, status_data):
        for cb in self.sync_listeners:
            try:
                cb(status_data)
            except Exception:
                pass

    def wake(self, delay=0.5):
        """طلب دورة مزامنة قريبة (مع تجميع الأحداث المتتالية)"""
        with self._wake_lock:
            target = time.time() + delay
            if self._wake_at == 0 or target < self._wake_at:
                self._wake_at = target
        self._wake_event.set()

    def _mark_self_op(self, rel, seconds=10):
        rel = norm_rel(rel)
        with self._self_ops_lock:
            self._self_ops[rel] = time.time() + seconds

    def clear_self_op(self, rel):
        rel = norm_rel(rel)
        if not rel:
            return
        with self._self_ops_lock:
            self._self_ops.pop(rel, None)
            for k in list(self._self_ops.keys()):
                if _is_under(rel, k) or _is_under(k, rel):
                    self._self_ops.pop(k, None)

    def _is_self_op(self, rel):
        rel = norm_rel(rel)
        now = time.time()
        with self._self_ops_lock:
            for k in [k for k, v in self._self_ops.items() if v < now]:
                self._self_ops.pop(k, None)
            return any(_is_under(rel, k) for k in self._self_ops)

    def note_local_delete(self, rel, is_folder=False, from_watcher=False):
        """تسجيل حذف صريح من المستخدم ليتم حذفه من السحابة في الدورة القادمة"""
        rel = norm_rel(rel)
        if not rel:
            return
        if from_watcher and self._is_self_op(rel):
            return
        if not from_watcher:
            self._mark_self_op(rel, seconds=5)
        with self.state_mgr._get_connection() as conn:
            conn.execute("""
                INSERT INTO tombstones (rel_path, is_folder, created_at) VALUES (?, ?, ?)
                ON CONFLICT(rel_path) DO UPDATE SET created_at = excluded.created_at, is_folder = excluded.is_folder
            """, (rel, 1 if is_folder else 0, time.time()))
        self.wake(delay=1.5)

    def note_local_move(self, old_rel, new_rel):
        """إعادة تسمية/نقل من داخل التطبيق: ننقل الملف في السحابة بدلاً من حذفه وإعادة رفعه"""
        old_rel, new_rel = norm_rel(old_rel), norm_rel(new_rel)
        self._mark_self_op(old_rel, seconds=5)
        self.clear_tombstone(new_rel)
        states = self._load_states()
        st = states.get(new_rel) or states.get(old_rel)
        if not st or not st.get("server_file_id"):
            self.note_local_delete(old_rel)
        self.wake(delay=0.5)

    def queue_fast_upload(self, rel_path, delay=0.15):
        """
        إدراج الملف في طابور الرفع الفوري المباشر لسحابة Google Drive فور حفظ التعديلات (Ctrl+S)
        دون الحاجة لانتظار دورة الفحص الشامل لجميع المجلدات.
        """
        rel = norm_rel(rel_path)
        if not rel:
            return
        fname = rel.split("/")[-1]
        if is_ignored_name(fname):
            return
        if self._is_self_op(rel):
            return

        self.clear_tombstone(rel)

        with self._fast_upload_lock:
            existing = self._fast_upload_timers.pop(rel, None)
            if existing:
                try:
                    existing.cancel()
                except Exception:
                    pass

            t = threading.Timer(delay, self._execute_fast_upload, args=(rel,))
            t.daemon = True
            self._fast_upload_timers[rel] = t
            t.start()

    def _execute_fast_upload(self, rel):
        with self._fast_upload_lock:
            self._fast_upload_timers.pop(rel, None)

        if not self.is_running:
            return

        full_path = self.sync_folder / rel
        if not full_path.exists() or not full_path.is_file():
            return

        # فحص استقرار الكتابة وتحرير مقبض النظام من Office
        # محاولات ذكية تصل إلى 15 محاولة (1.5 ثانية) لانتظار انتهاء Word/Excel من إغلاق مقبض الملف
        last_size = -1
        stable_count = 0
        for attempt in range(15):
            if OfficeHandler.is_access_db(str(full_path)):
                lock = OfficeHandler.get_access_lock_file(str(full_path))
                if lock and lock.exists():
                    # أكسس ما زال مفتوحاً محلياً، سيتم رفعه تلقائياً فور إغلاقه
                    return
            try:
                cur_size = full_path.stat().st_size
                with open(full_path, "rb") as f:
                    f.read(1024)
                if cur_size == last_size and cur_size > 0:
                    stable_count += 1
                    if stable_count >= 2:
                        break
                else:
                    last_size = cur_size
                    stable_count = 1
            except (OSError, PermissionError):
                stable_count = 0
            time.sleep(0.1)
        else:
            self.wake(delay=0.5)
            return

        try:
            curr_stat = full_path.stat()
            curr_size = curr_stat.st_size
            curr_mtime = curr_stat.st_mtime
            curr_hash = self.calculate_hash(str(full_path))
        except Exception:
            self.wake(delay=0.5)
            return

        st = self.state_mgr.get_file_state(rel)
        if st and st.get("sha256_hash") == curr_hash and st.get("sync_status") == "synced":
            return

        if not self._has_dept_perm(rel, "edit") and not self._has_dept_perm(rel, "upload"):
            _safe_log(f"[FastAutoSync] Skipped upload for {rel}: No permission")
            return

        # ⚡ 1. إطلاق البث اللحظي الفائق عبر الشبكة المحلية (LAN Turbo-Sync) فوراً في أقل من 50ms!
        if hasattr(self, 'lan_sync') and self.lan_sync:
            try:
                existing_st = self.state_mgr.get_file_state(rel)
                existing_fid = existing_st.get("server_file_id") if existing_st else ""
                self.lan_sync.broadcast_file_change(rel, curr_hash, curr_size, server_file_id=existing_fid)
            except Exception as lan_err:
                _safe_log(f"[LAN Turbo-Sync broadcast error]: {lan_err}")

        # ☁️ 2. رفع مباشر وفوري إلى السحابة بالتوازي
        _safe_log(f"[FastAutoSync] Local edit detected (Ctrl+S) -> Direct Immediate Upload: {rel}")
        ok, res = self.sync_file_now(str(full_path), rel_path=rel)
        if ok:
            _safe_log(f"[FastAutoSync] Successfully uploaded latest modifications: {rel}")
            try:
                from local_bridge import LocalBridgeHandler
                LocalBridgeHandler.last_sync_time = time.time()
                LocalBridgeHandler.last_synced_file = rel
            except Exception:
                pass
        else:
            _safe_log(f"[FastAutoSync] Direct upload postponed to full cycle: {res}")
            self.wake(delay=1.0)

    def watch_active_file(self, filepath):
        """مراقبة نشطة ومخصصة لأي ملف يتم تشغيله بالبرنامج الأصلي لرصد Ctrl+S بدقة متناهية"""
        try:
            p = Path(filepath).resolve()
            rel = norm_rel(p.relative_to(self.sync_folder.resolve()))
        except Exception:
            return

        if rel in self._watched_active_files:
            return
        self._watched_active_files.add(rel)

        def _monitor():
            try:
                if not p.exists():
                    return
                last_mtime = p.stat().st_mtime
                last_size = p.stat().st_size
                for _ in range(28800):  # فحص نشط مستمر لمدة تصل إلى 8 ساعات
                    time.sleep(0.8)
                    if not p.exists() or not self.is_running:
                        break
                    try:
                        cur = p.stat()
                        if cur.st_mtime != last_mtime or cur.st_size != last_size:
                            last_mtime = cur.st_mtime
                            last_size = cur.st_size
                            self.queue_fast_upload(rel, delay=0.6)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self._watched_active_files.discard(rel)

        threading.Thread(target=_monitor, daemon=True).start()

    def sync_file_now(self, local_abs_path, rel_path=None, progress_callback=None):
        """
        رفع مباشر وفوري لملف واحد إلى Google Drive مع تحديث قاعدة البيانات المحلية فوراً.
        تُستدعى عند إضافة ملف أو مجلد من واجهة التطبيق لضمان التخزين السحابي الحقيقي الفوري.
        """
        p = Path(local_abs_path)
        if not p.exists() or not p.is_file():
            return False, "الملف غير موجود على القرص"

        if not rel_path:
            try:
                rel_path = norm_rel(p.resolve().relative_to(self.sync_folder.resolve()))
            except Exception:
                rel_path = p.name
        else:
            rel_path = norm_rel(rel_path)

        if is_ignored_name(p.name):
            return True, {"ignored": True}

        self.clear_tombstone(rel_path)
        self.clear_self_op(rel_path)

        try:
            st_stat = p.stat()
            size, mtime = st_stat.st_size, st_stat.st_mtime
        except OSError as e:
            return False, str(e)

        existing_state = self.state_mgr.get_file_state(rel_path)
        existing_id = existing_state.get("server_file_id") if existing_state else None

        self._save_state(rel_path, "", size, mtime, existing_id, None, status="syncing")
        self.notify_status({"event": "syncing", "file": rel_path, "status": "جارٍ الرفع المباشر إلى السحابة..."})

        last_notify_t = [0.0]

        def _on_chunk(done_bytes, total_bytes):
            if callable(progress_callback):
                progress_callback(done_bytes, total_bytes)
            now_t = time.time()
            if (now_t - last_notify_t[0]) >= 0.45 or done_bytes >= total_bytes:
                last_notify_t[0] = now_t
                pct = int(min(100, round((done_bytes / max(total_bytes, 1)) * 100)))
                self.notify_status({"event": "syncing", "file": rel_path, "status": f"جارٍ الرفع السحابي ({pct}%)..."})

        ok, meta = self.client.upload_file(
            str(p),
            rel_path=rel_path,
            existing_id=existing_id,
            user_name=self.username,
            device_name=self.device_name,
            progress_callback=_on_chunk,
            is_priority=True,
        )

        if ok and isinstance(meta, dict):
            if meta.get("ignored"):
                return True, meta
            try:
                st_after = p.stat()
                size, mtime = st_after.st_size, st_after.st_mtime
            except OSError:
                pass
            remote_md5 = meta.get("md5Checksum") or self.calculate_hash(str(p))
            self._save_state(rel_path, remote_md5, size, mtime, meta.get("id"), remote_md5, status="synced")
            self.notify_status({"event": "synced", "file": rel_path, "status": "تمت المزامنة السحابية بنجاح"})
            try:
                from local_bridge import LocalBridgeHandler
                LocalBridgeHandler.last_sync_time = time.time()
                LocalBridgeHandler.last_synced_file = rel_path
            except Exception:
                pass
            return True, meta

        err_msg = str(meta) if meta else "فشل الرفع السحابي"
        self._save_state(rel_path, "", size, mtime, existing_id, None, status="pending_upload")
        self.notify_status({"event": "error", "file": rel_path, "status": f"تعذر الرفع الفوري – سيعاد تلقائياً"})
        return False, err_msg

    def on_local_file_saved(self, filepath):
        try:
            rel = norm_rel(Path(filepath).relative_to(self.sync_folder))
            if rel:
                self.queue_fast_upload(rel, delay=0.5)
                return
        except Exception:
            pass
        self.wake(delay=1.0)

    def on_local_file_deleted(self, filepath):
        try:
            rel = norm_rel(Path(filepath).relative_to(self.sync_folder))
        except Exception:
            return
        self.note_local_delete(rel)

    def scan_initial_local_files(self):
        self.wake(delay=0.1)

    def process_upload_queue(self):
        self.wake(delay=0.1)

    def pull_remote_changes(self):
        self.wake(delay=0.1)

    def sync_now(self, timeout=60):
        """تنفيذ دورة مزامنة كاملة (للاستدعاء من خيط خلفي فقط)"""
        done = threading.Event()
        self._pending_done = done
        self.wake(delay=0)
        done.wait(timeout)

    # ------------------------------------------------------------------ #
    # دورة الحياة
    # ------------------------------------------------------------------ #
    def start(self):
        if self.is_running:
            return
        self.is_running = True
        try:
            self.observer.schedule(LocalFolderWatcher(self), str(self.sync_folder), recursive=True)
            self.observer.daemon = True
            self.observer.start()
        except Exception as e:
            _safe_log(f"[Watcher start error]: {e}")
        if hasattr(self, 'lan_sync') and self.lan_sync:
            try:
                self.lan_sync.start()
            except Exception as e:
                _safe_log(f"[LAN Turbo-Sync start error]: {e}")
        self._worker = threading.Thread(target=self._background_sync_loop, name="SyncWorker", daemon=True)
        self._worker.start()
        self.wake(delay=0.5)

    def stop(self):
        self.is_running = False
        self._wake_event.set()
        if hasattr(self, 'lan_sync') and self.lan_sync:
            try:
                self.lan_sync.stop()
            except Exception:
                pass
        try:
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join(timeout=2)
        except Exception:
            pass

    def _apply_delta_pull(self, changes):
        """تنزيل وتطبيق فوري للملفات المعدلة أو المحذوفة القادمة من السحابة في أقل من ثانيتين"""
        if not changes:
            return
        snap = self.client.peek_snapshot() if hasattr(self.client, "peek_snapshot") else None
        states = self._load_states()
        tombs = self._load_tombstones()
        for ch in changes:
            temp_path = None
            try:
                fid = ch.get("fileId")
                is_removed = ch.get("removed", False)
                finfo = ch.get("file") or {}
                if finfo.get("trashed"):
                    is_removed = True
                fname = finfo.get("name") or ""
                if fname and is_ignored_name(fname):
                    continue

                rel = ch.get("_resolved_rel")
                if not rel and snap and hasattr(snap, "file_ids") and fid in snap.file_ids:
                    rel = snap.file_ids[fid]
                if not rel and fname:
                    for r, s in states.items():
                        if s.get("server_file_id") == fid:
                            rel = r
                            break

                if not rel:
                    continue

                full_p = self.sync_folder / rel

                # تجنب الكتابة فوق تعديل محلي جارٍ رفعه
                with self._fast_upload_lock:
                    if rel in self._fast_upload_timers:
                        continue
                st = states.get(rel)
                if st and st.get("sync_status") in ("syncing", "pending_upload"):
                    continue

                if is_removed:
                    if rel in tombs:
                        continue
                    if full_p.exists():
                        self._mark_self_op(rel, seconds=4)
                        try:
                            if full_p.is_file():
                                full_p.unlink(missing_ok=True)
                            elif full_p.is_dir():
                                shutil.rmtree(str(full_p), ignore_errors=True)
                        except Exception:
                            pass
                        self._delete_state(rel)
                        self.notify_status({"event": "remote_delete", "file": rel, "status": "تم حذف الملف سحابياً"})
                    continue

                remote_md5 = finfo.get("md5Checksum")
                if not remote_md5:
                    continue

                need_download = True
                if full_p.exists() and full_p.is_file():
                    local_md5 = self.calculate_hash(str(full_p))
                    if local_md5 == remote_md5:
                        need_download = False
                    elif st and st.get("remote_md5") == remote_md5 and st.get("sha256_hash") and local_md5 != st.get("sha256_hash"):
                        need_download = False

                if need_download:
                    _safe_log(f"[DeltaPull] Downloading modified file from cloud: {rel}")
                    self._mark_self_op(rel, seconds=5)
                    full_p.parent.mkdir(parents=True, exist_ok=True)
                    temp_dir = self.sync_folder / ".sync_temp"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = temp_dir / f"dl_{int(time.time()*1000)}_{full_p.name}.tmp"
                    
                    dl_ok, _ = self.client.download_file(fname or full_p.name, str(temp_path), storage_path=fid)
                    if dl_ok and temp_path.exists():
                        applied = OfficeHandler.safe_apply_file(str(full_p), str(temp_path))
                        if applied:
                            st_after = full_p.stat()
                            self._save_state(rel, remote_md5, st_after.st_size, st_after.st_mtime, fid, remote_md5, status="synced")
                            self.clear_self_op(rel)
                            self.notify_status({"event": "synced", "file": rel, "status": "تم استلام أحدث نسخة معدلة"})
                            try:
                                from local_bridge import LocalBridgeHandler
                                LocalBridgeHandler.last_sync_time = time.time()
                                LocalBridgeHandler.last_synced_file = rel
                            except Exception:
                                pass
            except Exception as e:
                _safe_log(f"[DeltaPull Error]: {e}")
            finally:
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

    def _background_sync_loop(self):
        delta_interval = 2.0
        last_poll_error_time = 0.0
        while self.is_running:
            waited = 0.0
            while self.is_running and waited < CYCLE_SECONDS:
                if self._wake_event.wait(timeout=min(delta_interval, CYCLE_SECONDS - waited)):
                    break
                waited += delta_interval
                now_t = time.time()
                # تهدئة الاستعلام عند انقطاع الاتصال لتفادي استهلاك الحصة أو المعالج
                if (now_t - last_poll_error_time) < 15.0:
                    continue
                try:
                    if hasattr(self.client, "poll_changes_since_last"):
                        res = self.client.poll_changes_since_last()
                        has_ch = res[0] if isinstance(res, tuple) else bool(res)
                        ch_list = res[1] if isinstance(res, tuple) and len(res) > 1 else []
                        if has_ch:
                            if ch_list:
                                self._apply_delta_pull(ch_list)
                            break
                except Exception as poll_e:
                    last_poll_error_time = time.time()
                    _safe_log(f"[Poll loop error]: {poll_e}")
            self._wake_event.clear()
            while self.is_running:
                with self._wake_lock:
                    remaining = self._wake_at - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.5))
            with self._wake_lock:
                self._wake_at = 0.0
            if not self.is_running:
                break
            try:
                self.run_cycle()
            except Exception as e:
                self.last_error = str(e)
                _safe_log(f"[Background Sync Error]: {e}")
            done = getattr(self, "_pending_done", None)
            if done is not None:
                self._pending_done = None
                done.set()

    # ------------------------------------------------------------------ #
    # أدوات
    # ------------------------------------------------------------------ #
    @staticmethod
    def calculate_hash(filepath):
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            while chunk := f.read(1024 * 1024):
                md5.update(chunk)
        return md5.hexdigest()

    def _scan_local(self):
        files, dirs = {}, set()
        for root, dnames, fnames in os.walk(self.sync_folder):
            dnames[:] = [d for d in dnames if not d.startswith(".")]
            root_p = Path(root)
            rel_root = norm_rel(root_p.relative_to(self.sync_folder))
            if rel_root:
                dirs.add(rel_root)
            for fn in fnames:
                if is_ignored_name(fn):
                    continue
                full = root_p / fn
                try:
                    st = full.stat()
                except OSError:
                    continue
                rel = f"{rel_root}/{fn}" if rel_root else fn
                files[rel] = {"abs": full, "size": st.st_size, "mtime": st.st_mtime}
        return files, dirs

    def _local_md5(self, rel, info, state):
        if state and state.get("sha256_hash") and len(state["sha256_hash"]) == 32 \
                and state.get("local_mtime") is not None \
                and abs(float(state["local_mtime"]) - info["mtime"]) < 0.05 \
                and int(state.get("file_size") or -1) == info["size"]:
            return state["sha256_hash"]
        return self.calculate_hash(str(info["abs"]))

    def _is_open_in_office(self, path):
        p = str(path)
        if OfficeHandler.is_access_db(p):
            return OfficeHandler.is_access_file_open_locally(p)
        return OfficeHandler.is_file_locked_by_os(p)

    def _readable_and_stable(self, info):
        p = info["abs"]
        if OfficeHandler.is_access_db(str(p)):
            lock = OfficeHandler.get_access_lock_file(str(p))
            if lock and lock.exists():
                return False
        try:
            with open(p, "rb") as f:
                f.read(1024)
            return True
        except (OSError, PermissionError):
            return False

    def _move_to_local_trash(self, rel, is_folder=False):
        src = self.sync_folder / rel
        if not src.exists():
            return
        trash_dir = self.sync_folder / ".trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        dest = trash_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{src.name}"
        self._mark_self_op(rel)
        try:
            size = 0 if is_folder else src.stat().st_size
            src.rename(dest)
            self.state_mgr.add_to_trash(src.name, rel, str(dest), size,
                                        item_type='folder' if is_folder else 'file')
            _safe_log(f"[Cloud Deletion Sync]: {rel} -> local trash")
        except Exception as e:
            _safe_log(f"[Local trash move error] {rel}: {e}")

    def _download(self, rel, rmeta):
        dest = self.sync_folder / rel
        self._mark_self_op(rel, seconds=20)
        self.notify_status({"event": "syncing", "file": rel, "status": "تنزيل من السحابة..."})

        def _on_dl_chunk(done_b, total_b):
            pct = int(min(100, round((done_b / max(total_b, 1)) * 100)))
            self.notify_status({"event": "syncing", "file": rel, "status": f"جارٍ التنزيل من السحابة ({pct}%)..."})

        temp_dir = self.sync_folder / ".sync_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_dest = temp_dir / f"dl_{int(time.time()*1000)}_{dest.name}.tmp"

        ok, msg = self.client.download_file(rmeta["name"], str(temp_dest), storage_path=rmeta["id"], progress_callback=_on_dl_chunk)
        if ok and temp_dest.exists():
            OfficeHandler.safe_apply_file(str(dest), str(temp_dest))
            try:
                temp_dest.unlink(missing_ok=True)
            except Exception:
                pass
            if dest.exists():
                st = dest.stat()
                md5 = rmeta.get("md5Checksum") or self.calculate_hash(str(dest))
                self._save_state(rel, md5, st.st_size, st.st_mtime, rmeta["id"], rmeta.get("md5Checksum"))
                self.notify_status({"event": "synced", "file": rel, "status": "محدث من السحابة"})
                try:
                    from local_bridge import LocalBridgeHandler
                    LocalBridgeHandler.last_sync_time = time.time()
                    LocalBridgeHandler.last_synced_file = rel
                except Exception:
                    pass
                return True
        _safe_log(f"[Download failed] {rel}: {msg}")
        try:
            if temp_dest.exists():
                temp_dest.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    def _upload(self, rel, info, md5, existing_id=None):
        self.notify_status({"event": "syncing", "file": rel, "status": "جارٍ الرفع السحابي..."})

        last_notify_t = [0.0]

        def _on_up_chunk(done_b, total_b):
            now_t = time.time()
            if (now_t - last_notify_t[0]) >= 0.50 or done_b >= total_b:
                last_notify_t[0] = now_t
                pct = int(min(100, round((done_b / max(total_b, 1)) * 100)))
                self.notify_status({"event": "syncing", "file": rel, "status": f"جارٍ الرفع السحابي ({pct}%)..."})

        ok, meta = self.client.upload_file(
            str(info["abs"]),
            rel_path=rel,
            existing_id=existing_id,
            user_name=self.username,
            device_name=self.device_name,
            progress_callback=_on_up_chunk,
            is_priority=False,
        )
        if ok and isinstance(meta, dict) and not meta.get("ignored"):
            try:
                st = info["abs"].stat()
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                size, mtime = info["size"], info["mtime"]
            self._save_state(rel, md5, size, mtime, meta.get("id"), meta.get("md5Checksum") or md5)
            self.notify_status({"event": "synced", "file": rel, "status": "تمت المزامنة بنجاح"})
            try:
                from local_bridge import LocalBridgeHandler
                LocalBridgeHandler.last_sync_time = time.time()
                LocalBridgeHandler.last_synced_file = rel
            except Exception:
                pass
            return True
        self._save_state(rel, md5, info["size"], info["mtime"], existing_id, None, status="failed")
        return False

    def _conflict_name(self, rel):
        p = Path(rel)
        stamp = datetime.now().strftime("%Y-%m-%d %H%M")
        dev = (self.device_name or "جهاز").replace("/", "-")
        new_name = f"{p.stem} (نسخة {dev} {stamp}){p.suffix}"
        return norm_rel(str(p.parent / new_name)) if str(p.parent) not in ("", ".") else new_name

    def _has_dept_perm(self, rel_path, action_key):
        """التحقق من صلاحية القسم السحابية قبل رفع أو تعديل أو حذف ملف من المزامنة الخلفية"""
        try:
            if not rel_path or not self.client:
                return True
            if hasattr(self.client, "get_cached_folder_permissions"):
                perms = self.client.get_cached_folder_permissions() or {}
            elif hasattr(self.client, "get_folder_permissions"):
                perms = self.client.get_folder_permissions() or {}
            else:
                return True
            if not isinstance(perms, dict):
                return True
            dept = norm_rel(rel_path).split("/")[0].strip()
            if not dept or dept not in perms:
                return True
            rule = perms.get(dept) or {}
            if action_key == "upload":
                return bool(rule.get("canUpload", rule.get("can_upload", rule.get("can_write", True))))
            if action_key == "edit":
                return bool(rule.get("canEdit", rule.get("can_edit", rule.get("can_write", True))))
            if action_key == "delete":
                return bool(rule.get("canDelete", rule.get("can_delete", True)))
            if action_key == "create_folder":
                return bool(rule.get("canCreateFolder", rule.get("can_create_folder", rule.get("can_write", True))))
            return True
        except Exception:
            return True

    # ------------------------------------------------------------------ #
    # الدورة الكاملة
    # ------------------------------------------------------------------ #
    def run_cycle(self):
        if not self.client or not self.client.is_configured():
            return
        snap = self.client.snapshot(force=False, max_age=15)
        if snap is None:
            self.last_sync_ok = False
            self.last_error = getattr(self.client, "last_error", "offline")
            self.notify_status({"event": "offline", "status": "تعذر الاتصال بالسحابة – سيعاد المحاولة تلقائياً"})
            return

        changes = 0
        local_files, local_dirs = self._scan_local()
        states = self._load_states()
        tombs = self._load_tombstones()
        known_dirs = self._known_dirs()
        remote_files = dict(snap.files)
        remote_dirs = {d for d in snap.folders if d}
        state_by_remote_id = {s["server_file_id"]: rel for rel, s in states.items() if s.get("server_file_id")}

        # 0) تنظيف شواهد الحذف للمسارات التي عادت موجودة محلياً أو التي لم تعد موجودة في السحابة أصلاً
        for t_rel in list(tombs):
            exists_locally = (t_rel in local_files) or (t_rel in local_dirs) or any(_is_under(r, t_rel) for r in local_files)
            exists_remotely = (t_rel in remote_files) or (t_rel in remote_dirs) or any(_is_under(r, t_rel) for r in remote_files) or any(_is_under(d, t_rel) for d in remote_dirs)
            if exists_locally or not exists_remotely:
                self._drop_tombstone(t_rel)
                tombs.pop(t_rel, None)

        def tombstone_for(rel):
            best = None
            for t_rel, t in tombs.items():
                if _is_under(rel, t_rel):
                    if best is None or t["created_at"] > best["created_at"]:
                        best = t
            return best

        handled_remote_ids = set()

        # 1) نقل/إعادة تسمية تمت داخل التطبيق: الملف موجود محلياً بمسار جديد ويحمل معرّف ملف سحابي بمسار قديم
        for rel, info in local_files.items():
            st = states.get(rel)
            rid = st.get("server_file_id") if st else None
            if not rid or rel in remote_files:
                continue
            old_rel = snap.file_ids.get(rid)
            if old_rel and old_rel != rel and old_rel not in local_files:
                try:
                    meta = self.client.move_file(rid, rel)
                    remote_files.pop(old_rel, None)
                    m = dict(snap.files.get(old_rel) or {})
                    m.update(meta or {})
                    m["name"] = rel.split("/")[-1]
                    remote_files[rel] = m
                    handled_remote_ids.add(rid)
                    changes += 1
                    _safe_log(f"[Move Sync] {old_rel} -> {rel}")
                except Exception as e:
                    _safe_log(f"[Move Sync error] {old_rel} -> {rel}: {e}")

        # 2) المجلدات
        for d in sorted(remote_dirs - local_dirs, key=lambda x: x.count("/")):
            t = tombstone_for(d)
            if t:
                if self.client.delete_folder(d):
                    changes += 1
                if t.get("rel_path") == d:
                    self._drop_tombstone(d)
                    tombs.pop(d, None)
                remote_dirs = {x for x in remote_dirs if not _is_under(x, d)}
                for r in [r for r in remote_files if _is_under(r, d)]:
                    remote_files.pop(r, None)
                continue
            try:
                self._mark_self_op(d)
                (self.sync_folder / d).mkdir(parents=True, exist_ok=True)
                local_dirs.add(d)
                changes += 1
            except Exception as e:
                _safe_log(f"[Local mkdir error] {d}: {e}")

        for d in sorted(local_dirs - remote_dirs, key=lambda x: x.count("/")):
            if d in known_dirs and not tombstone_for(d):
                has_unsynced = any(
                    _is_under(r, d) and (
                        r not in states or (
                            not states[r].get("remote_md5")
                            and not states[r].get("server_file_id")
                            and states[r].get("sync_status") != "synced"
                        )
                    )
                    for r in local_files
                )
                if not has_unsynced:
                    self._move_to_local_trash(d, is_folder=True)
                    local_dirs = {x for x in local_dirs if not _is_under(x, d)}
                    for r in [r for r in local_files if _is_under(r, d)]:
                        local_files.pop(r, None)
                        self._delete_state(r)
                    changes += 1
                    continue
            if self.client.create_folder(d):
                remote_dirs.add(d)
                changes += 1

        # 3) الملفات الموجودة في السحابة (تنزيل الملفات الصغيرة أولاً كملفات Word و Excel لملء المجلدات فورياً)
        pending_remote_deletes = []
        pending_modified_uploads = []

        sorted_remote_files = sorted(
            list(remote_files.items()),
            key=lambda x: int(x[1].get("size", 0) or 0)
        )
        for rel, rmeta in sorted_remote_files:
            if rmeta.get("id") in handled_remote_ids:
                continue
            linfo = local_files.get(rel)
            st = states.get(rel)
            if linfo is None:
                moved_to = state_by_remote_id.get(rmeta["id"])
                if moved_to and moved_to != rel and moved_to in local_files:
                    continue
                t = tombstone_for(rel)
                if t:
                    pending_remote_deletes.append((rel, rmeta))
                    continue
                if "/" not in rel:
                    legacy = f"{LEGACY_GENERAL_DEPT}/{rel}"
                    if legacy in local_files and legacy not in remote_files:
                        try:
                            if self.calculate_hash(str(local_files[legacy]["abs"])) == rmeta.get("md5Checksum"):
                                self._mark_self_op(legacy)
                                os.replace(local_files[legacy]["abs"], self.sync_folder / rel)
                                self._delete_state(legacy)
                                local_files.pop(legacy, None)
                                stt = (self.sync_folder / rel).stat()
                                self._save_state(rel, rmeta.get("md5Checksum"), stt.st_size, stt.st_mtime,
                                                 rmeta["id"], rmeta.get("md5Checksum"))
                                continue
                        except Exception:
                            pass
                if self._download(rel, rmeta):
                    changes += 1
                continue

            # موجود محلياً وسحابياً
            try:
                lmd5 = self._local_md5(rel, linfo, st)
            except OSError:
                continue
            rmd5 = rmeta.get("md5Checksum")
            if rmd5 and lmd5 == rmd5:
                if not st or st.get("remote_md5") != rmd5 or st.get("server_file_id") != rmeta["id"] \
                        or st.get("sync_status") != "synced" or abs(float(st.get("local_mtime") or 0) - linfo["mtime"]) > 0.05:
                    self._save_state(rel, lmd5, linfo["size"], linfo["mtime"], rmeta["id"], rmd5)
                continue

            local_changed = st is None or st.get("sha256_hash") != lmd5 or st.get("sync_status") in ("syncing", "pending_upload", "failed")
            remote_changed = st is None or not st.get("remote_md5") or st.get("remote_md5") != rmd5

            if st is not None and st.get("sync_status") in ("syncing", "pending_upload") and not st.get("remote_md5"):
                # ملف أضافه المستخدم صراحةً للرفع
                local_changed, remote_changed = True, False
            elif st is None:
                if linfo["mtime"] > _iso_to_ts(rmeta.get("modifiedTime")) + 2:
                    local_changed, remote_changed = True, False
                else:
                    local_changed, remote_changed = False, True

            if local_changed and not remote_changed:
                if self._readable_and_stable(linfo):
                    pending_modified_uploads.append((rel, linfo, lmd5, rmeta["id"]))
            elif remote_changed and not local_changed:
                if self._download(rel, rmeta):
                    changes += 1
            else:
                if not self._readable_and_stable(linfo) or self._is_open_in_office(linfo["abs"]):
                    continue
                conflict_rel = self._conflict_name(rel)
                # إذا تجاوز اسم ملف التعارض حدود نظام التشغيل (MAX_PATH)، استخدم اسماً مبسطاً
                if len(str(self.sync_folder / conflict_rel)) > 240:
                    base_stem = Path(rel).stem.split(" (نسخة")[0].split(" - (تعارض")[0]
                    short_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    conflict_rel = f"{base_stem} (نسخة_تعارض_{short_stamp}){Path(rel).suffix}"
                try:
                    self._mark_self_op(rel)
                    shutil.copy2(str(linfo["abs"]), str(self.sync_folder / conflict_rel))
                    self._delete_state(rel)
                    _safe_log(f"[Conflict] {rel} -> kept local copy as {conflict_rel}")
                    self._download(rel, rmeta)
                    cinfo = {"abs": self.sync_folder / conflict_rel, "size": linfo["size"], "mtime": time.time() - 10}
                    pending_modified_uploads.append((conflict_rel, cinfo, lmd5, None))
                    changes += 1
                except Exception as e:
                    _safe_log(f"[Conflict handling error] {rel}: {e}")

        for rel, rmeta in pending_remote_deletes:
            if not self._has_dept_perm(rel, "delete"):
                self._drop_tombstone(rel)
                continue
            try:
                self.client.trash_by_id(rmeta["id"])
                self._delete_state(rel)
                t = tombstone_for(rel)
                if t and t.get("rel_path") == rel:
                    self._drop_tombstone(rel)
                changes += 1
                _safe_log(f"[Delete Sync] trashed in cloud: {rel}")
            except Exception as e:
                _safe_log(f"[Delete Sync error] {rel}: {e}")

        # رفع التعديلات المحلية مرتبة من الأصغر حجماً للأكبر
        for rel, linfo, lmd5, ex_id in sorted(pending_modified_uploads, key=lambda x: x[1]["size"]):
            if not self.is_running:
                break
            if not self._has_dept_perm(rel, "edit"):
                continue
            if self._upload(rel, linfo, lmd5, existing_id=ex_id):
                changes += 1

        # 4) الملفات الموجودة محلياً فقط
        remote_deletion_candidates = []
        local_only_uploads = []

        for rel, linfo in local_files.items():
            if rel in remote_files:
                continue
            st = states.get(rel)
            if st and st.get("server_file_id") in handled_remote_ids:
                continue
            was_synced = bool(
                st and (
                    st.get("remote_md5")
                    or st.get("server_file_id")
                    or st.get("sync_status") == "synced"
                )
            )
            if was_synced and (not st.get("server_file_id") or st["server_file_id"] not in snap.file_ids):
                try:
                    lmd5 = self._local_md5(rel, linfo, st)
                except OSError:
                    continue
                if not st.get("sha256_hash") or lmd5 == st.get("sha256_hash"):
                    remote_deletion_candidates.append(rel)
                    continue
            if st and st.get("server_file_id") and st["server_file_id"] in snap.file_ids:
                continue
            if not self._readable_and_stable(linfo):
                continue
            # فقط الملفات التي تم إضافتها حديثاً وتنتظر الرفع تُرفع، أما الملفات القديمة غير المتزامنة فتنقل للمحذوفات
            if st and st.get("sync_status") in ("pending_upload", "syncing"):
                local_only_uploads.append((rel, linfo, st))
            else:
                _safe_log(f"[Clean old file] Moving un-synced old local file to local trash: {rel}")
                self._move_to_local_trash(rel)
                self._delete_state(rel)
                changes += 1

        # ترتيب الملفات الجديدة من الأصغر حجماً إلى الأكبر حتى تُرفع الملفات العادية فوراً قبل قواعد البيانات الضخمة
        for rel, linfo, st in sorted(local_only_uploads, key=lambda x: x[1]["size"]):
            if not self.is_running:
                break
            if not self._has_dept_perm(rel, "upload"):
                continue
            try:
                lmd5 = self._local_md5(rel, linfo, st)
            except OSError:
                continue
            if self._upload(rel, linfo, lmd5):
                changes += 1

        # تنفيذ الحذف القادم من السحابة (نقل آمن إلى سلة المهملات المحلية .trash)
        if remote_deletion_candidates:
            for rel in remote_deletion_candidates:
                self._move_to_local_trash(rel)
                self._delete_state(rel)
                changes += 1
                _safe_log(f"[Remote Delete Sync] moved to local trash: {rel}")

        # تنظيف شواهد الحذف (tombstones) التي لم يعد لها وجود في السحابة أصلاً
        for t_rel in list(tombs.keys()):
            still_in_cloud = (
                t_rel in remote_files
                or t_rel in remote_dirs
                or any(_is_under(r, t_rel) for r in remote_files)
                or any(_is_under(d, t_rel) for d in remote_dirs)
            )
            if not still_in_cloud:
                self._drop_tombstone(t_rel)

        # 5) تنظيف سجلات الحالة لملفات لم تعد موجودة في أي مكان
        for rel in list(states):
            if rel not in local_files and rel not in remote_files and not (self.sync_folder / rel).exists():
                self._delete_state(rel)

        known_dirs = set(remote_dirs)
        self._save_known_dirs(known_dirs)
        self.last_sync_ok = True
        self.last_sync_time = time.time()
        self.last_error = None
        self.notify_status({"event": "cycle", "changes": changes, "status": "متصل ومتزامن"})
