"""
تبادل الملفات – File Exchange System
قاعدة البيانات المحلية وإدارة الحالة المحلية (Local State Manager)
"""
import sqlite3
import os
import threading
from pathlib import Path
from datetime import datetime


class LocalStateManager:
    def __init__(self, db_dir=None):
        if db_dir is None:
            db_dir = Path(os.environ.get('APPDATA', '.')) / 'FileExchange'
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.db_dir / 'local_state.db'
        self._local = threading.local()
        self._init_db()

    def _get_connection(self):
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=60.0)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout = 60000")
            except Exception:
                pass
            self._local.conn = conn
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS local_files (
                    relative_path TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    server_file_id TEXT,
                    sync_status TEXT NOT NULL, -- 'synced', 'syncing', 'pending_upload', 'conflict', 'locked'
                    last_synced_at TEXT,
                    last_modified_local TEXT NOT NULL,
                    remote_md5 TEXT,
                    local_mtime REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS upload_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    relative_path TEXT NOT NULL UNIQUE,
                    local_abs_path TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    last_error TEXT,
                    queued_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deleted_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    original_rel_path TEXT NOT NULL,
                    trash_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    deleted_at TEXT NOT NULL,
                    item_type TEXT DEFAULT 'file',
                    dept_name TEXT DEFAULT '',
                    server_file_id TEXT DEFAULT ''
                )
            """)
            for ddl in (
                "ALTER TABLE deleted_files ADD COLUMN item_type TEXT DEFAULT 'file'",
                "ALTER TABLE deleted_files ADD COLUMN dept_name TEXT DEFAULT ''",
                "ALTER TABLE deleted_files ADD COLUMN server_file_id TEXT DEFAULT ''",
                "ALTER TABLE local_files ADD COLUMN remote_md5 TEXT",
                "ALTER TABLE local_files ADD COLUMN local_mtime REAL",
            ):
                try:
                    conn.execute(ddl)
                except Exception:
                    pass
            # تنظيف ملفات قفل أوفيس المؤقتة (~$) إن وجدت سابقاً في سجل المحذوفات
            try:
                conn.execute("DELETE FROM deleted_files WHERE file_name LIKE '~$%' OR file_name LIKE '%.tmp'")
            except Exception:
                pass

    def set_file_state(self, relative_path, file_name, sha256_hash, file_size, sync_status, server_file_id=None, remote_md5=None):
        relative_path = str(relative_path).replace("\\", "/").strip("/")
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO local_files (relative_path, file_name, sha256_hash, file_size, server_file_id, sync_status, last_synced_at, last_modified_local, remote_md5)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    sha256_hash = excluded.sha256_hash,
                    file_size = excluded.file_size,
                    server_file_id = COALESCE(excluded.server_file_id, local_files.server_file_id),
                    remote_md5 = COALESCE(excluded.remote_md5, local_files.remote_md5),
                    sync_status = excluded.sync_status,
                    last_synced_at = CASE WHEN excluded.sync_status = 'synced' THEN excluded.last_synced_at ELSE local_files.last_synced_at END,
                    last_modified_local = excluded.last_modified_local
            """, (relative_path, file_name, sha256_hash, file_size, server_file_id, sync_status, now, now, remote_md5))

    def get_file_state(self, relative_path):
        relative_path = str(relative_path).replace("\\", "/").strip("/")
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM local_files WHERE relative_path = ?", (relative_path,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_states_map(self):
        """جلب كافة حالات الملفات بدفعة واحدة سريعة لتجنب مئات الاستعلامات في الواجهة"""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM local_files")
            return {str(r['relative_path']).replace("\\", "/").strip("/"): dict(r) for r in cur.fetchall()}

    def get_all_files(self):
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM local_files ORDER BY file_name ASC")
            return [dict(r) for r in cur.fetchall()]

    def enqueue_upload(self, relative_path, local_abs_path, sha256_hash):
        relative_path = str(relative_path).replace("\\", "/").strip("/")
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO upload_queue (relative_path, local_abs_path, sha256_hash, attempts, queued_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    sha256_hash = excluded.sha256_hash,
                    queued_at = excluded.queued_at,
                    attempts = 0,
                    last_error = NULL
            """, (relative_path, local_abs_path, sha256_hash, now))

    def get_pending_uploads(self):
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM upload_queue ORDER BY id ASC")
            return [dict(r) for r in cur.fetchall()]

    def dequeue_upload(self, relative_path):
        relative_path = str(relative_path).replace("\\", "/").strip("/")
        with self._get_connection() as conn:
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ?", (relative_path,))

    def mark_upload_failed(self, relative_path, error_msg):
        relative_path = str(relative_path).replace("\\", "/").strip("/")
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE upload_queue 
                SET attempts = attempts + 1, last_error = ?
                WHERE relative_path = ?
            """, (str(error_msg), relative_path))
            conn.execute("""
                UPDATE local_files
                SET sync_status = 'failed'
                WHERE relative_path = ?
            """, (relative_path,))

    def get_setting(self, key, default=None):
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row['value'] if row else default

    def set_setting(self, key, value):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, str(value)))

    def get_departments(self):
        """جلب قائمة الأقسام الإدارية المعتمدة المخزنة محلياً"""
        val = self.get_setting("active_departments_json")
        if val:
            try:
                import json
                return json.loads(val)
            except Exception:
                pass
        return None

    def set_departments(self, depts_list):
        """حفظ قائمة الأقسام الإدارية المعتمدة محلياً"""
        import json
        self.set_setting("active_departments_json", json.dumps(depts_list, ensure_ascii=False))

    def rename_file_record(self, old_rel_path, new_rel_path, new_file_name):
        """تحديث مسار واسم ملف في قاعدة البيانات المحلية وقائمة الرفع"""
        old_rel_path = old_rel_path.replace("\\", "/").strip("/")
        new_rel_path = new_rel_path.replace("\\", "/").strip("/")
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute("DELETE FROM local_files WHERE relative_path = ? AND relative_path != ?", (new_rel_path, old_rel_path))
            conn.execute("""
                UPDATE local_files 
                SET relative_path = ?, file_name = ?, last_modified_local = ?
                WHERE relative_path = ?
            """, (new_rel_path, new_file_name, now, old_rel_path))
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ? AND relative_path != ?", (new_rel_path, old_rel_path))
            conn.execute("""
                UPDATE upload_queue
                SET relative_path = ?
                WHERE relative_path = ?
            """, (new_rel_path, old_rel_path))

    def rename_folder_prefix(self, old_rel_folder, new_rel_folder):
        """تحديث بادئة مسار المجلد لكافة الملفات المنظمة داخله محلياً"""
        old_clean = old_rel_folder.replace("\\", "/").strip("/")
        new_clean = new_rel_folder.replace("\\", "/").strip("/")
        old_prefix = old_clean + "/"
        new_prefix = new_clean + "/"
        with self._get_connection() as conn:
            cur = conn.execute("SELECT relative_path, file_name FROM local_files WHERE relative_path LIKE ? OR relative_path = ?", (old_prefix + "%", old_clean))
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                p = r['relative_path']
                new_p = new_clean if p == old_clean else new_prefix + p[len(old_prefix):]
                conn.execute("DELETE FROM local_files WHERE relative_path = ? AND relative_path != ?", (new_p, p))
                conn.execute("UPDATE local_files SET relative_path = ? WHERE relative_path = ?", (new_p, p))

            cur_up = conn.execute("SELECT relative_path FROM upload_queue WHERE relative_path LIKE ? OR relative_path = ?", (old_prefix + "%", old_clean))
            for r in cur_up.fetchall():
                p = r['relative_path']
                new_p = new_clean if p == old_clean else new_prefix + p[len(old_prefix):]
                conn.execute("DELETE FROM upload_queue WHERE relative_path = ? AND relative_path != ?", (new_p, p))
                conn.execute("UPDATE upload_queue SET relative_path = ? WHERE relative_path = ?", (new_p, p))

    def rename_department(self, old_dept_name, new_dept_name):
        """تحديث اسم القسم في قائمة الأقسام وسلة المحذوفات وبادئة الملفات"""
        depts = self.get_departments() or []
        for d in depts:
            if d.get('name') == old_dept_name:
                d['name'] = new_dept_name
        self.set_departments(depts)
        with self._get_connection() as conn:
            conn.execute("UPDATE deleted_files SET dept_name = ? WHERE dept_name = ?", (new_dept_name, old_dept_name))
        self.rename_folder_prefix(old_dept_name, new_dept_name)

    def add_to_trash(self, file_name, original_rel_path, trash_path, file_size, item_type='file', dept_name='', server_file_id=None):
        """نقل ملف أو مجلد أو قسم إلى سجل سلة المحذوفات وحذفه من الملفات النشطة مع الاحتفاظ بـ server_file_id"""
        if not file_name or str(file_name).startswith("~$") or str(file_name).lower().endswith(".tmp"):
            return None
        original_rel_path = str(original_rel_path or file_name).replace("\\", "/").strip("/")
        now = datetime.now().isoformat()
        if not dept_name:
            if "/" in original_rel_path:
                dept_name = original_rel_path.split("/")[0]
            elif item_type == 'department':
                dept_name = file_name

        with self._get_connection() as conn:
            if not server_file_id:
                cur_id = conn.execute(
                    "SELECT server_file_id FROM local_files WHERE relative_path = ? LIMIT 1",
                    (original_rel_path,)
                )
                row_id = cur_id.fetchone()
                if row_id and row_id['server_file_id']:
                    server_file_id = row_id['server_file_id']

            conn.execute("DELETE FROM deleted_files WHERE original_rel_path = ?", (original_rel_path,))
            conn.execute("""
                INSERT INTO deleted_files (file_name, original_rel_path, trash_path, file_size, deleted_at, item_type, dept_name, server_file_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (file_name, original_rel_path, str(trash_path), file_size, now, item_type, dept_name or '', server_file_id or ''))
            conn.execute("DELETE FROM local_files WHERE relative_path = ? OR relative_path LIKE ?",
                         (original_rel_path, f"{original_rel_path}/%"))
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ? OR relative_path LIKE ?",
                         (original_rel_path, f"{original_rel_path}/%"))
        return server_file_id

    def remove_from_trash_batch(self, trash_ids):
        """إزالة مجموعة من العناصر من سلة المحذوفات دفعة واحدة في معاملة SQLite واحدة لمنع بطء التفريغ"""
        if not trash_ids:
            return []
        with self._get_connection() as conn:
            placeholders = ",".join("?" for _ in trash_ids)
            cur = conn.execute(f"SELECT * FROM deleted_files WHERE id IN ({placeholders})", tuple(trash_ids))
            rows = [dict(r) for r in cur.fetchall()]
            conn.execute(f"DELETE FROM deleted_files WHERE id IN ({placeholders})", tuple(trash_ids))
            return rows

    def get_trash_files(self, dept_name=None):
        """جلب الملفات المحذوفة مؤقتاً في سلة محذوفات القسم المحدد لضمان العزل التام"""
        with self._get_connection() as conn:
            if dept_name:
                cur = conn.execute("""
                    SELECT * FROM deleted_files 
                    WHERE dept_name = ? OR original_rel_path = ? OR original_rel_path LIKE ?
                    ORDER BY id DESC
                """, (dept_name, dept_name, f"{dept_name}/%"))
            else:
                cur = conn.execute("SELECT * FROM deleted_files ORDER BY id DESC")
            return [dict(r) for r in cur.fetchall()]

    def get_trash_count(self, dept_name=None):
        """حساب عدد الملفات الموجودة في سلة محذوفات القسم المحدد"""
        with self._get_connection() as conn:
            if dept_name:
                cur = conn.execute("""
                    SELECT COUNT(*) as count FROM deleted_files 
                    WHERE dept_name = ? OR original_rel_path = ? OR original_rel_path LIKE ?
                """, (dept_name, dept_name, f"{dept_name}/%"))
            else:
                cur = conn.execute("SELECT COUNT(*) as count FROM deleted_files")
            row = cur.fetchone()
            return row['count'] if row else 0

    def is_in_trash(self, file_name, rel_path=None):
        """فحص ما إذا كان المسار النسبي محدداً في سلة المحذوفات"""
        with self._get_connection() as conn:
            if rel_path:
                norm = str(rel_path).replace("\\", "/").strip("/")
                cur = conn.execute("SELECT 1 FROM deleted_files WHERE original_rel_path = ? LIMIT 1", (norm,))
            else:
                cur = conn.execute("SELECT 1 FROM deleted_files WHERE original_rel_path = ? OR file_name = ? LIMIT 1", (file_name, file_name))
            return cur.fetchone() is not None

    def remove_from_trash(self, trash_id):
        """إزالة مستند من سلة المحذوفات (عند الاستعادة أو الحذف النهائي)"""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM deleted_files WHERE id = ?", (trash_id,))
            row = cur.fetchone()
            if row:
                conn.execute("DELETE FROM deleted_files WHERE id = ?", (trash_id,))
                return dict(row)
        return None

    def clear_all_trash(self, dept_name=None):
        """إفراغ سلة محذوفات القسم المحدد فقط أو بالكامل"""
        with self._get_connection() as conn:
            if dept_name:
                cur = conn.execute("""
                    SELECT * FROM deleted_files 
                    WHERE dept_name = ? OR original_rel_path = ? OR original_rel_path LIKE ?
                """, (dept_name, dept_name, f"{dept_name}/%"))
                rows = [dict(r) for r in cur.fetchall()]
                conn.execute("""
                    DELETE FROM deleted_files 
                    WHERE dept_name = ? OR original_rel_path = ? OR original_rel_path LIKE ?
                """, (dept_name, dept_name, f"{dept_name}/%"))
                return rows
            else:
                cur = conn.execute("SELECT * FROM deleted_files")
                rows = [dict(r) for r in cur.fetchall()]
                conn.execute("DELETE FROM deleted_files")
                return rows
