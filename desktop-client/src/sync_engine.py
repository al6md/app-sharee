# -*- coding: utf-8 -*-
"""
تبادل الملفات – File Exchange System
محرك المزامنة الثنائي (Sync Engine) – الإصدار 5.0 المحكم

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
import unicodedata
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from office_handler import OfficeHandler
from gdrive_client import is_ignored_name, norm_rel, norm_key, _safe_log
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
        self._watched_active_baselines = {}
        self._watched_active_lock = threading.Lock()
        self._upload_path_locks = {}
        self._upload_path_locks_guard = threading.Lock()
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

    def _find_state_normalized(self, rel):
        """البحث عن سجل الحالة في قاعدة البيانات مع مطابقة Unicode NFC وعدم حساسية حالة الأحرف"""
        rel_n = norm_rel(rel)
        if not rel_n:
            return None, None
        st = self.state_mgr.get_file_state(rel_n)
        if st:
            return rel_n, st
        k = norm_key(rel_n)
        for s_rel, s_row in self._load_states().items():
            if norm_key(s_rel) == k:
                return s_rel, s_row
        return None, None

    def _upgrade_state_row(self, old_rel, new_rel, new_server_id=None):
        """ترقية سجل قديم في local_state.db إلى المسار السحابي المعياري و/أو معرّف Share COC الحديث (loc_)"""
        old_rel = norm_rel(old_rel)
        new_rel = norm_rel(new_rel)
        if not old_rel or not new_rel:
            return False
        changed = False
        with self.state_mgr._get_connection() as conn:
            if old_rel != new_rel:
                existing_new = conn.execute(
                    "SELECT * FROM local_files WHERE relative_path = ?", (new_rel,)
                ).fetchone()
                if existing_new:
                    conn.execute("DELETE FROM local_files WHERE relative_path = ?", (old_rel,))
                    conn.execute("DELETE FROM upload_queue WHERE relative_path = ?", (old_rel,))
                else:
                    conn.execute(
                        "UPDATE local_files SET relative_path = ?, file_name = ? WHERE relative_path = ?",
                        (new_rel, new_rel.split("/")[-1], old_rel)
                    )
                    try:
                        conn.execute(
                            "UPDATE upload_queue SET relative_path = ? WHERE relative_path = ?",
                            (new_rel, old_rel)
                        )
                    except Exception:
                        conn.execute("DELETE FROM upload_queue WHERE relative_path = ?", (old_rel,))
                changed = True
            if new_server_id:
                cur = conn.execute(
                    "UPDATE local_files SET server_file_id = ? WHERE relative_path = ? AND (server_file_id IS NULL OR server_file_id != ?)",
                    (new_server_id, new_rel, new_server_id)
                )
                if cur.rowcount and cur.rowcount > 0:
                    changed = True
        return changed

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
        rk = norm_key(rel)
        if not rk:
            return
        with self._self_ops_lock:
            self._self_ops[rk] = time.time() + seconds

    def clear_self_op(self, rel):
        rk = norm_key(rel)
        if not rk:
            return
        with self._self_ops_lock:
            self._self_ops.pop(rk, None)
            for k in list(self._self_ops.keys()):
                if _is_under(rk, k) or _is_under(k, rk):
                    self._self_ops.pop(k, None)

    def _is_self_op(self, rel):
        rk = norm_key(rel)
        if not rk:
            return False
        now = time.time()
        with self._self_ops_lock:
            for k in [k for k, v in self._self_ops.items() if v < now]:
                self._self_ops.pop(k, None)
            return any(_is_under(rk, k) for k in self._self_ops)

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
        إدراج الملف في طابور الرفع الفوري المباشر إلى سيرفر Share COC فور حفظ التعديلات (Ctrl+S)
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

        rk = norm_key(rel)
        with self._fast_upload_lock:
            for k in [k for k in list(self._fast_upload_timers) if norm_key(k) == rk]:
                existing = self._fast_upload_timers.pop(k, None)
                if existing:
                    try:
                        existing.cancel()
                    except Exception:
                        pass

            t = threading.Timer(delay, self._execute_fast_upload, args=(rel,))
            t.daemon = True
            self._fast_upload_timers[rel] = t
            t.start()

    def _canonical_rel_from_snapshot(self, rel_path):
        """إرجاع المسار المعياري المطابق على الخادم عند توفر لقطة حالية دون الحاجة لطلب شبكة"""
        rel_n = norm_rel(rel_path)
        if not rel_n:
            return rel_n
        try:
            snap = self.client.peek_snapshot() if self.client and hasattr(self.client, "peek_snapshot") else None
            if snap and getattr(snap, "files", None):
                if rel_n in snap.files:
                    return rel_n
                rk = norm_key(rel_n)
                for r_rel in snap.files:
                    if norm_key(r_rel) == rk:
                        return r_rel
        except Exception:
            pass
        return rel_n

    def _execute_fast_upload(self, rel):
        with self._fast_upload_lock:
            self._fast_upload_timers.pop(rel, None)

        if not self.is_running:
            return

        rel = self._canonical_rel_from_snapshot(rel)
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
                if not OfficeHandler.can_read_shared(str(full_path)):
                    raise PermissionError("File locked exclusively")
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

        _, st = self._find_state_normalized(rel)
        if st and st.get("sha256_hash") == curr_hash and st.get("sync_status") == "synced" and st.get("remote_md5") == curr_hash:
            return

        # تجنب إعادة الرفع إذا كانت النسخة السحابية مطابقة بالفعل للبصمة الحالية
        try:
            snap = self.client.peek_snapshot() if self.client and hasattr(self.client, "peek_snapshot") else None
            snap_meta = snap.files.get(rel) if (snap and getattr(snap, "files", None)) else None
            if snap_meta and snap_meta.get("md5Checksum") and snap_meta.get("md5Checksum").lower() == curr_hash.lower():
                self._save_state(rel, curr_hash, curr_size, curr_mtime, snap_meta.get("id"), curr_hash, status="synced")
                return
        except Exception:
            pass

        if not self._has_dept_perm(rel, "edit") and not self._has_dept_perm(rel, "upload"):
            _safe_log(f"[FastAutoSync] Skipped upload for {rel}: No permission")
            return

        # ⚡ 1. إطلاق البث اللحظي الفائق عبر الشبكة المحلية (LAN Turbo-Sync) فوراً في أقل من 50ms!
        if hasattr(self, 'lan_sync') and self.lan_sync:
            try:
                existing_fid = st.get("server_file_id") if st else ""
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

        try:
            if not p.exists():
                return
            init_stat = p.stat()
            init_mtime = init_stat.st_mtime
            init_size = init_stat.st_size
        except OSError:
            return

        key = norm_key(rel)
        with self._watched_active_lock:
            prev = self._watched_active_baselines.get(key)
            next_gen = (prev[2] + 1) if prev else 1
            self._watched_active_baselines[key] = (init_mtime, init_size, next_gen)
            if key in self._watched_active_files:
                return
            self._watched_active_files.add(key)

        def _monitor():
            try:
                seen_gen = next_gen
                last_mtime = init_mtime
                last_size = init_size
                for _ in range(28800):  # فحص نشط مستمر لمدة تصل إلى 8 ساعات
                    time.sleep(0.8)
                    if not p.exists() or not self.is_running:
                        break
                    try:
                        with self._watched_active_lock:
                            base = self._watched_active_baselines.get(key)
                            if base and base[2] != seen_gen:
                                last_mtime, last_size, seen_gen = base
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
                with self._watched_active_lock:
                    self._watched_active_files.discard(key)
                    self._watched_active_baselines.pop(key, None)

        threading.Thread(target=_monitor, daemon=True).start()

    def _get_upload_path_lock(self, rel_path):
        rk = norm_key(rel_path)
        with self._upload_path_locks_guard:
            lk = self._upload_path_locks.get(rk)
            if lk is None:
                lk = threading.Lock()
                self._upload_path_locks[rk] = lk
            return lk

    def sync_file_now(self, local_abs_path, rel_path=None, progress_callback=None):
        """
        رفع مباشر وفوري لملف واحد إلى سيرفر Share COC مع تحديث قاعدة البيانات المحلية فوراً.
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

        rel_path = self._canonical_rel_from_snapshot(rel_path)

        if is_ignored_name(p.name):
            return True, {"ignored": True}

        with self._get_upload_path_lock(rel_path):
            self.clear_tombstone(rel_path)
            self.clear_self_op(rel_path)

            try:
                st_stat = p.stat()
                size, mtime = st_stat.st_size, st_stat.st_mtime
                curr_hash = self.calculate_hash(str(p))
            except OSError as e:
                return False, str(e)

            matched_s_rel, existing_state = self._find_state_normalized(rel_path)
            if matched_s_rel and matched_s_rel != rel_path:
                self._upgrade_state_row(matched_s_rel, rel_path)
                _, existing_state = self._find_state_normalized(rel_path)

            # منع تكرار الرفع المتزامن لنفس البصمة إذا تم رفعه للتو
            if (
                existing_state
                and existing_state.get("sync_status") == "synced"
                and existing_state.get("sha256_hash") == curr_hash
                and existing_state.get("remote_md5") == curr_hash
            ):
                return True, {
                    "id": existing_state.get("server_file_id"),
                    "md5Checksum": curr_hash,
                    "deduplicated": True,
                }

            existing_id = existing_state.get("server_file_id") if existing_state else None
            if existing_id and not str(existing_id).startswith("loc_"):
                snap = self.client.peek_snapshot() if self.client and hasattr(self.client, "peek_snapshot") else None
                snap_meta = snap.files.get(rel_path) if (snap and getattr(snap, "files", None)) else None
                if snap_meta and snap_meta.get("id"):
                    existing_id = snap_meta.get("id")
                    self._upgrade_state_row(rel_path, rel_path, new_server_id=existing_id)
                else:
                    existing_id = None

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
                remote_md5 = meta.get("md5Checksum") or curr_hash
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

                rel = self._canonical_rel_from_snapshot(rel)
                rk = norm_key(rel)
                full_p = self.sync_folder / rel

                # تجنب الكتابة فوق تعديل محلي جارٍ رفعه
                with self._fast_upload_lock:
                    if any(norm_key(k) == rk for k in self._fast_upload_timers):
                        continue
                st = next((s for s_rel, s in states.items() if norm_key(s_rel) == rk), None)
                if st and st.get("sync_status") in ("syncing", "pending_upload"):
                    continue

                if is_removed:
                    if any(norm_key(t_rel) == rk for t_rel in tombs):
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
                        apply_status = OfficeHandler.safe_apply_file_with_status(str(full_p), str(temp_path))
                        if apply_status == "applied" and full_p.exists():
                            st_after = full_p.stat()
                            actual_md5 = self.calculate_hash(str(full_p))
                            if not remote_md5 or actual_md5 == remote_md5:
                                self._save_state(rel, actual_md5, st_after.st_size, st_after.st_mtime, fid, remote_md5 or actual_md5, status="synced")
                                self.notify_status({"event": "synced", "file": rel, "status": "تم استلام أحدث نسخة معدلة"})
                                try:
                                    from local_bridge import LocalBridgeHandler
                                    LocalBridgeHandler.last_sync_time = time.time()
                                    LocalBridgeHandler.last_synced_file = rel
                                except Exception:
                                    pass
                        self.clear_self_op(rel)
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
        return OfficeHandler.read_md5_shared(str(filepath))

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
        return OfficeHandler.can_read_shared(str(p))

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
            apply_status = OfficeHandler.safe_apply_file_with_status(str(dest), str(temp_dest))
            try:
                temp_dest.unlink(missing_ok=True)
            except Exception:
                pass
            if apply_status == "applied" and dest.exists():
                st = dest.stat()
                actual_md5 = self.calculate_hash(str(dest))
                expected_md5 = rmeta.get("md5Checksum") or actual_md5
                if actual_md5 == expected_md5 or not rmeta.get("md5Checksum"):
                    self._save_state(rel, actual_md5, st.st_size, st.st_mtime, rmeta["id"], expected_md5)
                    self.clear_self_op(rel)
                    self.notify_status({"event": "synced", "file": rel, "status": "محدث من السحابة"})
                    try:
                        from local_bridge import LocalBridgeHandler
                        LocalBridgeHandler.last_sync_time = time.time()
                        LocalBridgeHandler.last_synced_file = rel
                    except Exception:
                        pass
                    return True
            self.clear_self_op(rel)
            return False
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
        self._save_state(rel, "", info["size"], info["mtime"], existing_id, None, status="failed")
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

        local_by_key = {norm_key(rel): (rel, info) for rel, info in local_files.items()}
        local_dir_by_key = {norm_key(d): d for d in local_dirs}
        remote_by_key = {norm_key(rel): (rel, rmeta) for rel, rmeta in remote_files.items()}
        remote_dir_by_key = {norm_key(d): d for d in remote_dirs}

        # ترقية تلقائية لسجلات local_state.db القديمة: توحيد المسار للمطابقة السحابية المعيارية
        # واستبدال أي server_file_id قديم (لا يبدأ بـ loc_) بمعرّف Share COC الحالي على الخادم
        state_upgraded = False
        for s_rel, st in list(states.items()):
            sk = norm_key(s_rel)
            remote_match = remote_by_key.get(sk)
            if remote_match:
                canon_rel, rmeta = remote_match
                canon_id = rmeta.get("id")
                old_fid = st.get("server_file_id")
                is_legacy_fid = bool(old_fid and not str(old_fid).startswith("loc_"))
                new_fid = canon_id if (canon_id and (is_legacy_fid or not old_fid or (str(canon_id).startswith("loc_") and old_fid != canon_id))) else None
                if s_rel != canon_rel or new_fid:
                    if self._upgrade_state_row(s_rel, canon_rel, new_server_id=new_fid):
                        state_upgraded = True
            else:
                # مسح المعرّف القديم الذي لا يبدأ بـ loc_ إذا كانت حالة الملف لم تعد مرتبطة بمعرّف صالح أثناء إعادة الرفع
                old_fid = st.get("server_file_id")
                if old_fid and not str(old_fid).startswith("loc_") and st.get("sync_status") in ("pending_upload", "syncing"):
                    with self.state_mgr._get_connection() as conn:
                        conn.execute("UPDATE local_files SET server_file_id = NULL WHERE relative_path = ?", (s_rel,))
                    state_upgraded = True
        if state_upgraded:
            states = self._load_states()

        state_by_key = {}
        for s_rel, s_row in states.items():
            sk = norm_key(s_rel)
            if sk not in state_by_key or s_rel in remote_files:
                state_by_key[sk] = (s_rel, s_row)

        state_by_remote_id = {s["server_file_id"]: rel for rel, s in states.items() if s.get("server_file_id")}

        # 0) تنظيف شواهد الحذف للمسارات التي عادت موجودة محلياً أو التي لم تعد موجودة في السحابة أصلاً
        for t_rel in list(tombs):
            tk = norm_key(t_rel)
            exists_locally = (tk in local_by_key) or (tk in local_dir_by_key) or any(_is_under(rk, tk) for rk in local_by_key)
            exists_remotely = (tk in remote_by_key) or (tk in remote_dir_by_key) or any(_is_under(rk, tk) for rk in remote_by_key) or any(_is_under(dk, tk) for dk in remote_dir_by_key)
            if exists_locally or not exists_remotely:
                self._drop_tombstone(t_rel)
                tombs.pop(t_rel, None)

        def tombstone_for(rel):
            rk = norm_key(rel)
            best = None
            for t_rel, t in tombs.items():
                if _is_under(rk, norm_key(t_rel)):
                    if best is None or t["created_at"] > best["created_at"]:
                        best = t
            return best

        handled_remote_ids = set()

        # 1) نقل/إعادة تسمية تمت داخل التطبيق: الملف موجود محلياً بمسار جديد ويحمل معرّف ملف سحابي بمسار قديم
        for rel, info in local_files.items():
            rk = norm_key(rel)
            _, st = state_by_key.get(rk, (None, None))
            rid = st.get("server_file_id") if st else None
            if not rid or rk in remote_by_key:
                continue
            old_rel = snap.file_ids.get(rid)
            if old_rel and norm_key(old_rel) != rk and norm_key(old_rel) not in local_by_key:
                try:
                    meta = self.client.move_file(rid, rel)
                    remote_files.pop(old_rel, None)
                    remote_by_key.pop(norm_key(old_rel), None)
                    m = dict(snap.files.get(old_rel) or {})
                    m.update(meta or {})
                    m["name"] = rel.split("/")[-1]
                    remote_files[rel] = m
                    remote_by_key[rk] = (rel, m)
                    handled_remote_ids.add(rid)
                    changes += 1
                    _safe_log(f"[Move Sync] {old_rel} -> {rel}")
                except Exception as e:
                    _safe_log(f"[Move Sync error] {old_rel} -> {rel}: {e}")

        # 2) المجلدات (مع مقارنة موحدة لا تتأثر بحالة الأحرف أو NFC مع الحفاظ على المسار المعياري للخادم)
        known_dir_keys = {norm_key(d) for d in known_dirs}
        for dk in sorted([k for k in remote_dir_by_key if k not in local_dir_by_key], key=lambda k: remote_dir_by_key[k].count("/")):
            if dk not in remote_dir_by_key:
                continue
            d = remote_dir_by_key[dk]
            t = tombstone_for(d)
            if t:
                if self.client.delete_folder(d):
                    changes += 1
                if norm_key(t.get("rel_path", "")) == dk:
                    self._drop_tombstone(t["rel_path"])
                    tombs.pop(t["rel_path"], None)
                remote_dirs = {x for x in remote_dirs if not _is_under(norm_key(x), dk)}
                remote_dir_by_key = {norm_key(x): x for x in remote_dirs}
                for r in [r for r in list(remote_files) if _is_under(norm_key(r), dk)]:
                    remote_files.pop(r, None)
                    remote_by_key.pop(norm_key(r), None)
                continue
            try:
                self._mark_self_op(d)
                (self.sync_folder / d).mkdir(parents=True, exist_ok=True)
                local_dirs.add(d)
                local_dir_by_key[dk] = d
                changes += 1
            except Exception as e:
                _safe_log(f"[Local mkdir error] {d}: {e}")

        for dk in sorted([k for k in local_dir_by_key if k not in remote_dir_by_key], key=lambda k: local_dir_by_key[k].count("/")):
            if dk not in local_dir_by_key:
                continue
            d = local_dir_by_key[dk]
            if dk in known_dir_keys and not tombstone_for(d):
                has_unsynced = any(
                    _is_under(rk, dk) and (
                        rk not in state_by_key or (
                            not state_by_key[rk][1].get("remote_md5")
                            and not state_by_key[rk][1].get("server_file_id")
                            and state_by_key[rk][1].get("sync_status") != "synced"
                        )
                    )
                    for rk in local_by_key
                )
                if not has_unsynced:
                    self._move_to_local_trash(d, is_folder=True)
                    local_dirs = {x for x in local_dirs if not _is_under(norm_key(x), dk)}
                    local_dir_by_key = {norm_key(x): x for x in local_dirs}
                    for rk in [k for k in list(local_by_key) if _is_under(k, dk)]:
                        lrel, _ = local_by_key.pop(rk)
                        local_files.pop(lrel, None)
                        if rk in state_by_key:
                            s_rel, _ = state_by_key.pop(rk)
                            self._delete_state(s_rel)
                        else:
                            self._delete_state(lrel)
                    changes += 1
                    continue
            if self.client.create_folder(d):
                remote_dirs.add(d)
                remote_dir_by_key[dk] = d
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
            rk = norm_key(rel)
            local_match = local_by_key.get(rk)
            linfo = local_match[1] if local_match else None
            _, st = state_by_key.get(rk, (None, None))
            if linfo is None:
                moved_to = state_by_remote_id.get(rmeta["id"])
                if moved_to and norm_key(moved_to) != rk and norm_key(moved_to) in local_by_key:
                    continue
                t = tombstone_for(rel)
                if t:
                    pending_remote_deletes.append((rel, rmeta))
                    continue
                if "/" not in rel:
                    legacy = f"{LEGACY_GENERAL_DEPT}/{rel}"
                    lk = norm_key(legacy)
                    if lk in local_by_key and lk not in remote_by_key:
                        orig_legacy, leg_info = local_by_key[lk]
                        try:
                            if self.calculate_hash(str(leg_info["abs"])) == rmeta.get("md5Checksum"):
                                self._mark_self_op(orig_legacy)
                                os.replace(leg_info["abs"], self.sync_folder / rel)
                                self._delete_state(orig_legacy)
                                local_files.pop(orig_legacy, None)
                                local_by_key.pop(lk, None)
                                stt = (self.sync_folder / rel).stat()
                                self._save_state(rel, rmeta.get("md5Checksum"), stt.st_size, stt.st_mtime,
                                                 rmeta["id"], rmeta.get("md5Checksum"))
                                continue
                        except Exception:
                            pass
                if self._download(rel, rmeta):
                    changes += 1
                continue

            # موجود محلياً وسحابياً (باستخدام المسار السحابي المعياري rel مع مطابقة حالة الأحرف و NFC)
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
                if t and norm_key(t.get("rel_path", "")) == norm_key(rel):
                    self._drop_tombstone(t["rel_path"])
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
            lk = norm_key(rel)
            if lk in remote_by_key:
                continue
            s_rel, st = state_by_key.get(lk, (None, None))
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
                    remote_deletion_candidates.append((rel, s_rel))
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
                if s_rel and s_rel != rel:
                    self._delete_state(s_rel)
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
            for rel, s_rel in remote_deletion_candidates:
                self._move_to_local_trash(rel)
                self._delete_state(rel)
                if s_rel and s_rel != rel:
                    self._delete_state(s_rel)
                changes += 1
                _safe_log(f"[Remote Delete Sync] moved to local trash: {rel}")

        # تنظيف شواهد الحذف (tombstones) التي لم يعد لها وجود في السحابة أصلاً
        for t_rel in list(tombs.keys()):
            tk = norm_key(t_rel)
            still_in_cloud = (
                tk in remote_by_key
                or tk in remote_dir_by_key
                or any(_is_under(rk, tk) for rk in remote_by_key)
                or any(_is_under(dk, tk) for dk in remote_dir_by_key)
            )
            if not still_in_cloud:
                self._drop_tombstone(t_rel)

        # 5) تنظيف سجلات الحالة لملفات لم تعد موجودة في أي مكان
        for rel in list(states):
            rk = norm_key(rel)
            if rk not in local_by_key and rk not in remote_by_key and not (self.sync_folder / rel).exists():
                self._delete_state(rel)

        known_dirs = set(remote_dirs)
        self._save_known_dirs(known_dirs)
        self.last_sync_ok = True
        self.last_sync_time = time.time()
        self.last_error = None
        self.notify_status({"event": "cycle", "changes": changes, "status": "متصل ومتزامن"})
