"""
تبادل الملفات – File Exchange System
قاعدة البيانات المحلية وإدارة قائمة الانتظار في وضع عدم الاتصال (Offline Queue)
"""
import sqlite3
import os
from pathlib import Path
from datetime import datetime

class LocalStateManager:
    def __init__(self, db_dir=None):
        if db_dir is None:
            db_dir = Path(os.environ.get('APPDATA', '.')) / 'FileExchange'
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.db_dir / 'local_state.db'
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.row_factory = sqlite3.Row
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
                    last_modified_local TEXT NOT NULL
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
                    item_type TEXT DEFAULT 'file'
                )
            """)
            try:
                conn.execute("ALTER TABLE deleted_files ADD COLUMN item_type TEXT DEFAULT 'file'")
            except Exception:
                pass

    def set_file_state(self, relative_path, file_name, sha256_hash, file_size, sync_status, server_file_id=None):
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO local_files (relative_path, file_name, sha256_hash, file_size, server_file_id, sync_status, last_synced_at, last_modified_local)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    sha256_hash = excluded.sha256_hash,
                    file_size = excluded.file_size,
                    server_file_id = COALESCE(excluded.server_file_id, local_files.server_file_id),
                    sync_status = excluded.sync_status,
                    last_synced_at = CASE WHEN excluded.sync_status = 'synced' THEN excluded.last_synced_at ELSE local_files.last_synced_at END,
                    last_modified_local = excluded.last_modified_local
            """, (relative_path, file_name, sha256_hash, file_size, server_file_id, sync_status, now, now))

    def get_file_state(self, relative_path):
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM local_files WHERE relative_path = ?", (relative_path,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_files(self):
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM local_files ORDER BY file_name ASC")
            return [dict(r) for r in cur.fetchall()]

    def enqueue_upload(self, relative_path, local_abs_path, sha256_hash):
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
        with self._get_connection() as conn:
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ?", (relative_path,))

    def mark_upload_failed(self, relative_path, error_msg):
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

    def add_to_trash(self, file_name, original_rel_path, trash_path, file_size, item_type='file'):
        """نقل ملف أو مجلد أو قسم إلى سجل سلة المحذوفات وحذفه من الملفات النشطة"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO deleted_files (file_name, original_rel_path, trash_path, file_size, deleted_at, item_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (file_name, original_rel_path, str(trash_path), file_size, now, item_type))
            conn.execute("DELETE FROM local_files WHERE relative_path = ? OR file_name = ? OR relative_path LIKE ?", 
                         (original_rel_path, file_name, f"{original_rel_path}/%"))
            conn.execute("DELETE FROM upload_queue WHERE relative_path = ? OR relative_path LIKE ?", 
                         (original_rel_path, f"{original_rel_path}/%"))

    def get_trash_files(self):
        """جلب جميع الملفات المحذوفة مؤقتاً في سلة المحذوفات"""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM deleted_files ORDER BY id DESC")
            return [dict(r) for r in cur.fetchall()]

    def get_trash_count(self):
        """حساب عدد الملفات الموجودة في سلة المحذوفات"""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) as count FROM deleted_files")
            row = cur.fetchone()
            return row['count'] if row else 0

    def remove_from_trash(self, trash_id):
        """إزالة مستند من سلة المحذوفات (عند الاستعادة أو الحذف النهائي)"""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM deleted_files WHERE id = ?", (trash_id,))
            row = cur.fetchone()
            if row:
                conn.execute("DELETE FROM deleted_files WHERE id = ?", (trash_id,))
                return dict(row)
        return None

    def clear_all_trash(self):
        """إفراغ سلة المحذوفات بالكامل"""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM deleted_files")
            rows = [dict(r) for r in cur.fetchall()]
            conn.execute("DELETE FROM deleted_files")
            return rows
