"""
تبادل الملفات – File Exchange System
محرك المزامنة الثنائي (Sync Engine) – الإصدار 3.0

مبادئ التصميم:
  • خيط عامل واحد فقط ينفذ كل عمليات الشبكة (لا تعارض ولا رفع مكرر ولا تجميد للواجهة).
  • مرآة كاملة: المسار النسبي داخل FileExchangeShared == المسار داخل مجلد السحابة الجذري،
    بكل المجلدات الفرعية وبأي عمق، والمجلدات الفارغة أيضاً.
  • المقارنة بالبصمة MD5 (نفس البصمة التي يحسبها Google Drive) فلا تنزيل/رفع بلا داعٍ.
  • الحذف السحابي لا يتم أبداً إلا بإجراء صريح من المستخدم (Tombstone) – فلو فُقد المجلد المحلي
    أو انقطع الإنترنت لا تُحذف ملفات بقية الأجهزة.
  • عند فشل الاتصال لا يُعتبر أي ملف "محذوفاً".
"""
import os
import json
import time
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from office_handler import OfficeHandler
from gdrive_client import is_ignored_name, norm_rel

CYCLE_SECONDS = 15
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
    """مراقب المجلد المحلي: لا يقوم بأي عمل شبكي – فقط يوقظ المحرك ويسجل الحذف الصريح"""

    def __init__(self, sync_engine):
        super().__init__()
        self.engine = sync_engine

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

    def on_any_event(self, event):
        try:
            etype = event.event_type
            if etype in ("opened", "closed", "closed_no_write"):
                return
            src_rel = self._rel(event.src_path)
            if etype in ("deleted", "moved") and self._relevant(src_rel):
                self.engine.note_local_delete(src_rel, is_folder=event.is_directory, from_watcher=True)
            if etype in ("created", "modified", "moved"):
                dest = getattr(event, "dest_path", None) or event.src_path
                if self._relevant(self._rel(dest)):
                    self.engine.wake(delay=2.0)
        except Exception as e:
            print(f"[Watcher error]: {e}")


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
        self._worker = None
        self.last_sync_ok = None
        self.last_sync_time = None
        self.last_error = None
        self._init_schema()

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
        now = datetime.now().isoformat()
        with self.state_mgr._get_connection() as conn:
            conn.execute("""
                INSERT INTO local_files (relative_path, file_name, sha256_hash, file_size, server_file_id,
                                         sync_status, last_synced_at, last_modified_local, remote_md5, local_mtime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    file_name = excluded.file_name,
                    sha256_hash = excluded.sha256_hash,
                    file_size = excluded.file_size,
                    server_file_id = COALESCE(excluded.server_file_id, local_files.server_file_id),
                    sync_status = excluded.sync_status,
                    last_synced_at = excluded.last_synced_at,
                    last_modified_local = excluded.last_modified_local,
                    remote_md5 = COALESCE(excluded.remote_md5, local_files.remote_md5),
                    local_mtime = excluded.local_mtime
            """, (rel, rel.split("/")[-1], md5 or "", int(size or 0), remote_id, status, now,
                  datetime.fromtimestamp(mtime).isoformat() if mtime else now, remote_md5, mtime))

    def _set_status(self, rel, status):
        with self.state_mgr._get_connection() as conn:
            conn.execute("UPDATE local_files SET sync_status = ? WHERE relative_path = ?", (status, rel))

    def _delete_state(self, rel):
        with self.state_mgr._get_connection() as conn:
            conn.execute("DELETE FROM local_files WHERE relative_path = ?", (rel,))
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ?", (rel,))

    def _load_tombstones(self):
        with self.state_mgr._get_connection() as conn:
            rows = conn.execute("SELECT * FROM tombstones").fetchall()
        return {norm_rel(r["rel_path"]): dict(r) for r in rows}

    def _drop_tombstone(self, rel):
        with self.state_mgr._get_connection() as conn:
            conn.execute("DELETE FROM tombstones WHERE rel_path = ?", (rel,))

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
            if self._wake_at == 0 or target > self._wake_at:
                self._wake_at = target
        self._wake_event.set()

    def _mark_self_op(self, rel, seconds=10):
        with self._self_ops_lock:
            self._self_ops[rel] = time.time() + seconds

    def _is_self_op(self, rel):
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
            self._mark_self_op(rel)
        with self.state_mgr._get_connection() as conn:
            conn.execute("""
                INSERT INTO tombstones (rel_path, is_folder, created_at) VALUES (?, ?, ?)
                ON CONFLICT(rel_path) DO UPDATE SET created_at = excluded.created_at, is_folder = excluded.is_folder
            """, (rel, 1 if is_folder else 0, time.time()))
        self.wake(delay=3.0)

    def note_local_move(self, old_rel, new_rel):
        """إعادة تسمية/نقل من داخل التطبيق: ننقل الملف في السحابة بدلاً من حذفه وإعادة رفعه"""
        old_rel, new_rel = norm_rel(old_rel), norm_rel(new_rel)
        self._mark_self_op(old_rel)
        states = self._load_states()
        st = states.get(new_rel) or states.get(old_rel)
        if not st or not st.get("server_file_id"):
            self.note_local_delete(old_rel)
        self.wake(delay=1.0)

    def on_local_file_saved(self, filepath):
        self.wake(delay=1.5)

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

    def sync_now(self, timeout=120):
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
            print(f"[Watcher start error]: {e}")
        self._worker = threading.Thread(target=self._background_sync_loop, name="SyncWorker", daemon=True)
        self._worker.start()
        self.wake(delay=2.0)

    def stop(self):
        self.is_running = False
        self._wake_event.set()
        try:
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join(timeout=2)
        except Exception:
            pass

    def _background_sync_loop(self):
        while self.is_running:
            self._wake_event.wait(timeout=CYCLE_SECONDS)
            self._wake_event.clear()
            # احترام مهلة التجميع
            while self.is_running:
                with self._wake_lock:
                    remaining = self._wake_at - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 1.0))
            with self._wake_lock:
                self._wake_at = 0.0
            if not self.is_running:
                break
            try:
                self.run_cycle()
            except Exception as e:
                self.last_error = str(e)
                print(f"[Background Sync Error]: {e}")
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
                and state.get("local_mtime") and abs(float(state["local_mtime"]) - info["mtime"]) < 0.001 \
                and int(state.get("file_size") or -1) == info["size"]:
            return state["sha256_hash"]
        return self.calculate_hash(str(info["abs"]))

    def _is_open_in_office(self, path):
        p = str(path)
        if OfficeHandler.is_access_db(p):
            return OfficeHandler.is_access_file_open_locally(p)
        return OfficeHandler.is_file_locked_by_os(p)

    def _readable_and_stable(self, info):
        if time.time() - info["mtime"] < 2.0:
            return False
        p = info["abs"]
        if OfficeHandler.is_access_db(str(p)):
            lock = OfficeHandler.get_access_lock_file(str(p))
            if lock and lock.exists():
                return False
        try:
            with open(p, "rb"):
                pass
            return True
        except OSError:
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
            # إزالة سجلات الحالة الخاصة بالمسار (add_to_trash يحذف بالاسم أيضاً لذا نعيد ضبطها بدقة)
            print(f"[Cloud Deletion Sync]: {rel} -> local trash")
        except Exception as e:
            print(f"[Local trash move error] {rel}: {e}")

    def _download(self, rel, rmeta):
        dest = self.sync_folder / rel
        self._mark_self_op(rel)
        self.notify_status({"event": "syncing", "file": rel, "status": "تنزيل من السحابة..."})
        ok, msg = self.client.download_file(rmeta["name"], str(dest), storage_path=rmeta["id"])
        if ok and dest.exists():
            st = dest.stat()
            md5 = rmeta.get("md5Checksum") or self.calculate_hash(str(dest))
            self._save_state(rel, md5, st.st_size, st.st_mtime, rmeta["id"], rmeta.get("md5Checksum"))
            self.notify_status({"event": "synced", "file": rel, "status": "محدث من السحابة"})
            return True
        print(f"[Download failed] {rel}: {msg}")
        return False

    def _upload(self, rel, info, md5, existing_id=None):
        self.notify_status({"event": "syncing", "file": rel, "status": "جارٍ الرفع السحابي..."})
        ok, meta = self.client.upload_file(str(info["abs"]), rel_path=rel, existing_id=existing_id,
                                           user_name=self.username, device_name=self.device_name)
        if ok and isinstance(meta, dict) and not meta.get("ignored"):
            try:
                st = info["abs"].stat()
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                size, mtime = info["size"], info["mtime"]
            self._save_state(rel, md5, size, mtime, meta.get("id"), meta.get("md5Checksum") or md5)
            self.notify_status({"event": "synced", "file": rel, "status": "تمت المزامنة بنجاح"})
            return True
        self._save_state(rel, md5, info["size"], info["mtime"], existing_id, None, status="failed")
        return False

    def _conflict_name(self, rel):
        p = Path(rel)
        stamp = datetime.now().strftime("%Y-%m-%d %H%M")
        dev = (self.device_name or "جهاز").replace("/", "-")
        new_name = f"{p.stem} (نسخة {dev} {stamp}){p.suffix}"
        return norm_rel(str(p.parent / new_name)) if str(p.parent) not in ("", ".") else new_name

    # ------------------------------------------------------------------ #
    # الدورة الكاملة
    # ------------------------------------------------------------------ #
    def run_cycle(self):
        if not self.client or not self.client.is_configured():
            return
        snap = self.client.snapshot(force=True)
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
        remote_files = snap.files
        remote_dirs = {d for d in snap.folders if d}
        state_by_remote_id = {s["server_file_id"]: rel for rel, s in states.items() if s.get("server_file_id")}

        # 0) إسقاط شواهد الحذف للمسارات التي عادت موجودة محلياً (استعادة من سلة المحذوفات)
        for t_rel in list(tombs):
            if t_rel in local_files or t_rel in local_dirs:
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
                    print(f"[Move Sync] {old_rel} -> {rel}")
                except Exception as e:
                    print(f"[Move Sync error] {old_rel} -> {rel}: {e}")

        # 2) المجلدات
        for d in sorted(remote_dirs - local_dirs, key=lambda x: x.count("/")):
            t = tombstone_for(d)
            created = _iso_to_ts(snap.folder_meta.get(d, {}).get("createdTime"))
            if t and t["created_at"] >= created:
                # حذف صريح من هذا الجهاز -> حذف من السحابة (بعد نقل الملفات المنقولة في الخطوة 1)
                if self.client.delete_folder(d):
                    changes += 1
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
                print(f"[Local mkdir error] {d}: {e}")

        for d in sorted(local_dirs - remote_dirs, key=lambda x: x.count("/")):
            if d in known_dirs and not tombstone_for(d):
                # كان موجوداً في السحابة وحُذف منها (من جهاز آخر أو من الويب)
                has_unsynced = any(_is_under(r, d) and (r not in states or not states[r].get("remote_md5"))
                                   for r in local_files)
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

        # 3) الملفات الموجودة في السحابة
        pending_remote_deletes = []
        for rel, rmeta in list(remote_files.items()):
            if rmeta.get("id") in handled_remote_ids:
                continue
            linfo = local_files.get(rel)
            st = states.get(rel)
            if linfo is None:
                # (أ) نُقل محلياً إلى مسار آخر وسيتم التعامل معه في الخطوة 1 بالدورة القادمة
                moved_to = state_by_remote_id.get(rmeta["id"])
                if moved_to and moved_to != rel and moved_to in local_files:
                    continue
                # (ب) حذف صريح من المستخدم
                t = tombstone_for(rel)
                if t and t["created_at"] >= _iso_to_ts(rmeta.get("modifiedTime")):
                    pending_remote_deletes.append((rel, rmeta))
                    continue
                if t:
                    # رُفع من جديد بعد الحذف -> إلغاء الشاهد
                    self._drop_tombstone(t.get("rel_path", rel))
                # (ج) ترحيل نسخة قديمة كانت تُحفظ داخل "القسم العام" لملفات جذر السحابة
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
                # (د) ملف جديد/غير موجود محلياً -> تنزيل
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
                        or st.get("sync_status") != "synced" or st.get("local_mtime") != linfo["mtime"]:
                    self._save_state(rel, lmd5, linfo["size"], linfo["mtime"], rmeta["id"], rmd5)
                continue

            local_changed = st is None or st.get("sha256_hash") != lmd5
            remote_changed = st is None or not st.get("remote_md5") or st.get("remote_md5") != rmd5

            if st is None:
                # لا يوجد سجل سابق: الأحدث يفوز
                if linfo["mtime"] > _iso_to_ts(rmeta.get("modifiedTime")) + 2:
                    local_changed, remote_changed = True, False
                else:
                    local_changed, remote_changed = False, True

            if local_changed and not remote_changed:
                if self._readable_and_stable(linfo) and self._upload(rel, linfo, lmd5, existing_id=rmeta["id"]):
                    changes += 1
            elif remote_changed and not local_changed:
                if self._is_open_in_office(linfo["abs"]):
                    continue  # الملف مفتوح حالياً في Word/Excel/Access – ننتظر إغلاقه
                if self._download(rel, rmeta):
                    changes += 1
            else:
                # تعارض: تعديل محلي وسحابي معاً -> نحفظ النسختين بدون فقدان أي بيانات
                if not self._readable_and_stable(linfo) or self._is_open_in_office(linfo["abs"]):
                    continue
                conflict_rel = self._conflict_name(rel)
                try:
                    self._mark_self_op(rel)
                    os.replace(linfo["abs"], self.sync_folder / conflict_rel)
                    self._delete_state(rel)
                    print(f"[Conflict] {rel} -> kept local copy as {conflict_rel}")
                    self._download(rel, rmeta)
                    cinfo = {"abs": self.sync_folder / conflict_rel, "size": linfo["size"], "mtime": time.time() - 10}
                    self._upload(conflict_rel, cinfo, lmd5)
                    changes += 1
                except Exception as e:
                    print(f"[Conflict handling error] {rel}: {e}")

        for rel, rmeta in pending_remote_deletes:
            try:
                self.client.trash_by_id(rmeta["id"])
                self._delete_state(rel)
                t = tombstone_for(rel)
                if t and t.get("rel_path") == rel:
                    self._drop_tombstone(rel)
                changes += 1
                print(f"[Delete Sync] trashed in cloud: {rel}")
            except Exception as e:
                print(f"[Delete Sync error] {rel}: {e}")

        # 4) الملفات الموجودة محلياً فقط
        remote_deletion_candidates = []
        for rel, linfo in local_files.items():
            if rel in remote_files:
                continue
            st = states.get(rel)
            if st and st.get("server_file_id") in handled_remote_ids:
                continue
            if st and st.get("remote_md5") and st.get("server_file_id") and \
                    st["server_file_id"] not in snap.file_ids:
                # كان متزامناً ثم اختفى من السحابة -> حُذف من جهاز آخر أو من الويب
                try:
                    lmd5 = self._local_md5(rel, linfo, st)
                except OSError:
                    continue
                if lmd5 == st.get("sha256_hash"):
                    remote_deletion_candidates.append(rel)
                    continue
            if st and st.get("server_file_id") and st["server_file_id"] in snap.file_ids:
                continue  # نقل قيد المعالجة
            if not self._readable_and_stable(linfo):
                continue
            try:
                lmd5 = self._local_md5(rel, linfo, st)
            except OSError:
                continue
            if self._upload(rel, linfo, lmd5):
                changes += 1

        # حماية من الحذف الجماعي (مثلاً سحابة فارغة بسبب خطأ في الإعداد)
        synced_count = sum(1 for s in states.values() if s.get("remote_md5"))
        if remote_deletion_candidates:
            if len(remote_deletion_candidates) > 25 and len(remote_deletion_candidates) > 0.5 * max(synced_count, 1):
                print(f"[Safety] Skipped mass local deletion of {len(remote_deletion_candidates)} files")
            else:
                for rel in remote_deletion_candidates:
                    self._move_to_local_trash(rel)
                    self._delete_state(rel)
                    changes += 1

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
