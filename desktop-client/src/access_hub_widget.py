# -*- coding: utf-8 -*-
"""
غرفة تجارة كربلاء المقدسة – منظومة Share COC
مركز قواعد بيانات Access الموحد (Access Data Hub Desktop Widget)
يدعم الدمج الشامل، الخانات الحقيقية، الترتيب الأصلي الدقيق 100% للحقول،
الفرز الزمني (من الجديد إلى القديم والعكس)، إضافة وحذف الحقول ديناميكياً، والـ CRUD الكامل مع المزامنة السحابية.
"""

import os
import sys
import re
import json
import requests
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QButtonGroup, QFrame, QDialog, QMessageBox, QFileDialog,
    QScrollArea, QAbstractItemView, QProgressDialog, QComboBox,
    QMenu, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QCursor, QIcon

CLOUD_API_URL = "https://web-dashboard-pi-self.vercel.app/api/access-hub"
LOCAL_API_URL = "http://localhost:3000/api/access-hub"

# مسار مجلد البيانات المحلي كنسخة احتياطية سريعة
LOCAL_DATA_DIR = Path(__file__).parent.parent.parent / "web-dashboard" / "data" / "access-hub"

# كاش الذاكرة اللحظي للبيانات - In-Memory Ultra-Fast RAM Cache
_FILE_RAM_CACHE = {}  # path_str -> (mtime, parsed_json_dict)

def get_local_data_dir() -> Path:
    """تحديد المسار المحلي الفعلي لبيانات Access Hub"""
    candidates = [
        Path(sys.executable).parent / "data" / "access-hub",
        Path(r"C:\Users\tohiba\OneDrive\Desktop\ShareCOC\data\access-hub"),
        Path(__file__).resolve().parent.parent.parent / "web-dashboard" / "data" / "access-hub",
        Path(r"c:\Users\tohiba\OneDrive\Desktop\شييييير\web-dashboard\data\access-hub"),
        Path(os.environ.get("APPDATA", "")) / "ShareCOC" / "access-hub",
    ]
    for c in candidates:
        if c.exists() and (c / "index.json").exists():
            return c
    return candidates[0]

def get_cached_json_file(file_path: Path):
    """قراءة وفك ملف الـ JSON بسرعة الرام اللحظية (0 ميلي ثانية) بعد أول قراءة"""
    if not file_path.exists():
        return None
    path_str = str(file_path.resolve())
    try:
        cur_mtime = file_path.stat().st_mtime
    except Exception:
        cur_mtime = 0

    cached = _FILE_RAM_CACHE.get(path_str)
    if cached and cached[0] == cur_mtime:
        return cached[1]

    with open(file_path, "r", encoding="utf-8") as jf:
        data = json.load(jf)
    _FILE_RAM_CACHE[path_str] = (cur_mtime, data)
    return data

DATE_KEYWORDS = ['date', 'تاريخ', 'affiliation', 'expiration', 'year', 'سنة', 'مواليد']

# مصفوفة الأولوية المنطقية لترتيب جداول غرفة التجارة لضمان ظهور التجار والشركات والدلالين أولاً
TABLE_PRIORITY = {
    "التجار": 1,
    "الشركات": 2,
    "الدلالين": 3,
    "دلالين": 3,
    "التعديل": 4,
    "المعامل": 5,
    "الفنادق": 6,
    "المطاعم": 7,
    "المقاهي": 8,
    "الصيدليات": 9,
    "الساحات": 10,
    "الشطب": 11,
}

def sort_tables_by_priority(tables):
    """ترتيب الجداول ترتيباً منطقياً معتمداً لغرفة التجارة يبدأ بالتجار ثم الشركات ثم الدلالين"""
    return sorted(tables, key=lambda t: (TABLE_PRIORITY.get(t, 50), t))


def parse_date_value(val):
    """تحليل ذكي لقيم التواريخ لتحويلها إلى Timestamp للمقارنة والفرز"""
    if val is None or val == "":
        return None
    s = str(val).strip()

    # YYYY-MM-DD أو YYYY/MM/DD
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).timestamp()
        except Exception:
            pass

    # DD/MM/YYYY أو DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).timestamp()
        except Exception:
            pass

    # محاولة التحليل القياسي
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        pass

    # سنة فقط e.g. 2024
    if re.match(r"^\d{4}$", s):
        try:
            return datetime(int(s), 1, 1).timestamp()
        except Exception:
            pass

    return None


class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_name, table_name, search_query="", page=1, limit=50, sort_dir="none", sort_col="date_auto"):
        super().__init__()
        self.file_name = file_name
        self.table_name = table_name
        self.search_query = search_query
        self.page = page
        self.limit = limit
        self.sort_dir = sort_dir
        self.sort_col = sort_col

    def run(self):
        # 1. القراءة الفورية فائقة السرعة من الذاكرة والقرص المحلي أولاً (Instant 0ms)
        local_dir = get_local_data_dir()
        if local_dir.exists() and (local_dir / "index.json").exists():
            try:
                result = self._load_from_local_disk(local_dir)
                if result:
                    self.data_loaded.emit(result)
                    return
            except Exception as e:
                pass

        # 2. في حال عدم توفر البيانات محلياً، الاستعلام من السحابة السريعة
        params = {
            "file": self.file_name,
            "table": self.table_name,
            "search": self.search_query,
            "page": self.page,
            "limit": self.limit,
            "sort_dir": self.sort_dir,
            "sort_col": self.sort_col
        }
        try:
            r = requests.get(CLOUD_API_URL, params=params, timeout=10)
            if r.status_code == 200:
                self.data_loaded.emit(r.json())
                return
            else:
                self.error_occurred.emit(f"خطأ في الخادم السحابي: {r.status_code}")
        except Exception as e:
            self.error_occurred.emit(f"تعذر استرجاع البيانات: {e}")

    def _load_from_local_disk(self, local_dir=None):
        if local_dir is None:
            local_dir = get_local_data_dir()
        idx_path = local_dir / "index.json"
        idx = get_cached_json_file(idx_path)
        if not idx:
            return None

        req_file = self.file_name
        req_table = self.table_name
        search = self.search_query.strip().lower()

        # قراءة الطفرات السحابية المخزنة محلياً إن وجدت
        mutations = {"adds": [], "updates": {}, "deletes": [], "added_columns": {}, "deleted_columns": {}}
        mut_path = local_dir / "mutations.json"
        if mut_path.exists():
            cached_mut = get_cached_json_file(mut_path)
            if cached_mut:
                mutations = cached_mut

        rows = []
        columns = []
        available_tables = []

        if req_file == "all":
            tables_set = set()
            for f in idx.get("files", []):
                for t in f.get("tables", []):
                    tables_set.add(t)
            for a in mutations.get("adds", []):
                if a.get("_adh_table"):
                    tables_set.add(a["_adh_table"])
            available_tables = sort_tables_by_priority(list(tables_set))
            if not req_table or req_table not in tables_set:
                req_table = available_tables[0] if available_tables else "التجار"

            cols_order = []
            cols_seen = set()

            for f in idx.get("files", []):
                fpath = local_dir / f"{f['name']}.json"
                data = get_cached_json_file(fpath)
                if not data:
                    continue

                orig_cols = data.get("columns", {}).get(req_table, [])
                for c in orig_cols:
                    if c not in cols_seen:
                        cols_seen.add(c)
                        cols_order.append(c)

                for r in data.get("tables", {}).get(req_table, []):
                    r_copy = dict(r)
                    r_copy["_adh_file"] = f["name"]
                    r_copy["_adh_table"] = req_table
                    rows.append(r_copy)

            columns = cols_order
        else:
            fpath = local_dir / f"{req_file}.json"
            data = get_cached_json_file(fpath)
            if not data:
                return None

            available_tables = sort_tables_by_priority(list(data.get("tables", {}).keys()))
            if not req_table or req_table not in data.get("tables", {}):
                req_table = available_tables[0] if available_tables else ""

            columns = list(data.get("columns", {}).get(req_table, []))
            for r in data.get("tables", {}).get(req_table, []):
                r_copy = dict(r)
                r_copy["_adh_file"] = req_file
                r_copy["_adh_table"] = req_table
                rows.append(r_copy)

        # دمج الحقول المضافة والمحذوفة
        added_for_tbl = []
        deleted_for_tbl = []
        for k, v in mutations.get("added_columns", {}).items():
            if k.endswith(f":{req_table}") or (req_file != "all" and k == f"{req_file}:{req_table}"):
                for c in v:
                    if c not in added_for_tbl:
                        added_for_tbl.append(c)

        for k, v in mutations.get("deleted_columns", {}).items():
            if k.endswith(f":{req_table}") or (req_file != "all" and k == f"{req_file}:{req_table}"):
                for c in v:
                    if c not in deleted_for_tbl:
                        deleted_for_tbl.append(c)

        active_columns = [c for c in columns if c not in deleted_for_tbl]
        for c in added_for_tbl:
            if c not in active_columns and c not in deleted_for_tbl:
                active_columns.append(c)

        # استخراج أعمدة التواريخ
        date_columns = []
        for c in active_columns:
            clow = c.lower()
            if any(k in clow for k in DATE_KEYWORDS):
                date_columns.append(c)

        # تطبيق الحذف والتعديل والإضافة
        deleted_ids = set(mutations.get("deletes", []))
        updates = mutations.get("updates", {})

        filtered_rows = []
        for r in rows:
            r_id = r.get("_adh_id") or f"{r.get('_adh_file')}:{r.get('_adh_table')}:{r.get('ID') or r.get('id') or r.get('ت')}"
            if r_id in deleted_ids:
                continue
            merged = dict(r)
            if r_id in updates:
                merged.update(updates[r_id])
            merged["_adh_id"] = r_id
            if search:
                match = any(v and search in str(v).lower() for k, v in merged.items() if not k.startswith("_adh_"))
                if not match:
                    continue
            filtered_rows.append(merged)

        # إضافة السجلات الجديدة
        for a in mutations.get("adds", []):
            if req_file == "all" or a.get("_adh_file") == req_file:
                if a.get("_adh_table") == req_table:
                    a_id = a.get("_adh_id")
                    if a_id and a_id in deleted_ids:
                        continue
                    merged = dict(a)
                    if a_id and a_id in updates:
                        merged.update(updates[a_id])
                    if search:
                        match = any(v and search in str(v).lower() for k, v in merged.items() if not k.startswith("_adh_"))
                        if not match:
                            continue
                    filtered_rows.insert(0, merged)

        # الفرز الزمني إذا طُلب
        actual_sort_col = self.sort_col
        if self.sort_dir in ('desc', 'asc'):
            if actual_sort_col == 'date_auto' or not actual_sort_col:
                actual_sort_col = date_columns[0] if date_columns else (active_columns[0] if active_columns else "")

            if actual_sort_col:
                def sort_key(row):
                    val = row.get(actual_sort_col)
                    ts = parse_date_value(val)
                    if ts is not None:
                        return (0, ts)
                    return (1, str(val or ""))

                filtered_rows.sort(key=sort_key, reverse=(self.sort_dir == 'desc'))

        total_matches = len(filtered_rows)
        start_idx = (self.page - 1) * self.limit
        page_rows = filtered_rows[start_idx:start_idx + self.limit]

        return {
            "success": True,
            "files": idx.get("files", []),
            "total_records": idx.get("total_records", 0) + len(mutations.get("adds", [])) - len(mutations.get("deletes", [])),
            "active_file": req_file,
            "active_table": req_table,
            "available_tables": available_tables,
            "columns": active_columns,
            "date_columns": date_columns,
            "sort_col": actual_sort_col,
            "sort_dir": self.sort_dir,
            "total_matches": total_matches,
            "page": self.page,
            "limit": self.limit,
            "total_pages": max(1, (total_matches + self.limit - 1) // self.limit),
            "rows": page_rows
        }


class RecordFormDialog(QDialog):
    """نافذة لإضافة أو تعديل قيد بالحفاظ الكامل على ترتيب الحقول الأصلية 100%"""
    def __init__(self, title, columns, initial_data=None, files_list=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(580, 650)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.columns = columns
        self.files_list = files_list or []
        self.inputs = {}
        self.selected_file = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QLabel(title)
        header.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #14372e; padding-bottom: 6px; border-bottom: 2px solid #c59b27;")
        layout.addWidget(header)

        # اختيار الملف في حالة الإضافة وكان في وضع الدمج الشامل
        if self.files_list and initial_data is None:
            file_box = QVBoxLayout()
            file_box.setSpacing(4)
            lbl_file = QLabel("📁 حفظ القيد في ملف / قسم:")
            lbl_file.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            lbl_file.setStyleSheet("color: #344054;")
            file_box.addWidget(lbl_file)

            self.file_combo = QComboBox()
            self.file_combo.setFont(QFont("IBM Plex Sans Arabic", 9))
            self.file_combo.setStyleSheet("""
                QComboBox {
                    background: #F8F9FA;
                    border: 1.5px solid #14372e;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-weight: bold;
                    color: #14372e;
                }
            """)
            for f in self.files_list:
                fname = f.get("name", "") if isinstance(f, dict) else str(f)
                self.file_combo.addItem(fname)
            file_box.addWidget(self.file_combo)
            layout.addLayout(file_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        for col in self.columns:
            row_box = QVBoxLayout()
            row_box.setSpacing(3)
            lbl = QLabel(col)
            lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            lbl.setStyleSheet("color: #344054;")
            row_box.addWidget(lbl)

            inp = QLineEdit()
            inp.setFont(QFont("IBM Plex Sans Arabic", 9))
            inp.setStyleSheet("""
                QLineEdit {
                    background: #FFFFFF;
                    border: 1px solid #D0D5DD;
                    border-radius: 6px;
                    padding: 6px 10px;
                    color: #1B1F24;
                }
                QLineEdit:focus {
                    border: 1.5px solid #14372e;
                }
            """)
            if initial_data and col in initial_data and initial_data[col] is not None:
                inp.setText(str(initial_data[col]))
            row_box.addWidget(inp)
            self.inputs[col] = inp
            scroll_layout.addLayout(row_box)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 حفظ ومزامنة سحابية فورية")
        btn_save.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_save.setStyleSheet("""
            background: #14372e;
            color: #FFFFFF;
            border-radius: 6px;
            padding: 8px 18px;
        """)
        btn_save.clicked.connect(self.accept)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cancel.setStyleSheet("""
            background: #F2F4F7;
            color: #344054;
            border-radius: 6px;
            padding: 8px 16px;
            border: 1px solid #D0D5DD;
        """)
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def get_data(self):
        return {col: self.inputs[col].text().strip() for col in self.columns}

    def get_target_file(self):
        if hasattr(self, 'file_combo'):
            return self.file_combo.currentText()
        return None


class AddColumnDialog(QDialog):
    """نافذة لإضافة حقل جديد إلى الجدول مع تعميمه سحابياً"""
    def __init__(self, table_name, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة حقل جديد")
        self.resize(440, 230)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        lbl_title = QLabel("➕ إضافة حقل جديد إلى قاعدة البيانات")
        lbl_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #14372e;")
        layout.addWidget(lbl_title)

        info = QLabel(f"الجدول المستهدف: {table_name} | القسم: {file_name}")
        info.setFont(QFont("IBM Plex Sans Arabic", 9))
        info.setStyleSheet("color: #667085;")
        layout.addWidget(info)

        lbl_name = QLabel("اسم الحقل الجديد:")
        lbl_name.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl_name.setStyleSheet("color: #344054;")
        layout.addWidget(lbl_name)

        self.input_col = QLineEdit()
        self.input_col.setPlaceholderText("مثال: رقم الهاتف الثاني، الملاحظات، الرقم الضريبي...")
        self.input_col.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.input_col.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                border: 1.5px solid #D0D5DD;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border-color: #14372e; }
        """)
        layout.addWidget(self.input_col)

        hint = QLabel("💡 سيتم تعميم هذا الحقل فورياً في السحابة لجميع الموظفين ولوحة الويب.")
        hint.setFont(QFont("IBM Plex Sans Arabic", 8))
        hint.setStyleSheet("color: #027A48;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("إضافة وتعميم سحابي")
        btn_add.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_add.setStyleSheet("background: #14372e; color: #FFFFFF; border-radius: 6px; padding: 8px 16px;")
        btn_add.clicked.connect(self._validate_and_accept)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_cancel.setStyleSheet("background: #F2F4F7; color: #344054; border: 1px solid #D0D5DD; border-radius: 6px; padding: 8px 16px;")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_add)
        layout.addLayout(btn_row)

    def _validate_and_accept(self):
        val = self.input_col.text().strip()
        if not val:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة اسم الحقل أولاً.")
            return
        self.accept()

    def get_column_name(self):
        return self.input_col.text().strip()


class DeleteColumnDialog(QDialog):
    """نافذة لحذف أو إخفاء حقل من الجدول وتعميمه سحابياً"""
    def __init__(self, table_name, columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة وحذف الحقول")
        self.resize(440, 240)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        lbl_title = QLabel("🗑️ حذف حقل من الجدول")
        lbl_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #B42318;")
        layout.addWidget(lbl_title)

        info = QLabel(f"الجدول المستهدف: {table_name}")
        info.setFont(QFont("IBM Plex Sans Arabic", 9))
        info.setStyleSheet("color: #667085;")
        layout.addWidget(info)

        lbl_pick = QLabel("اختر الحقل المراد حذفه:")
        lbl_pick.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl_pick.setStyleSheet("color: #344054;")
        layout.addWidget(lbl_pick)

        self.combo_cols = QComboBox()
        self.combo_cols.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.combo_cols.setStyleSheet("""
            QComboBox {
                background: #FFFFFF;
                border: 1.5px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        for c in columns:
            self.combo_cols.addItem(c)
        layout.addWidget(self.combo_cols)

        warn = QLabel("⚠️ تحذير: سيتم إخفاء هذا الحقل وحذفه من العرض لجميع المستخدمين في كافة المنصات.")
        warn.setFont(QFont("IBM Plex Sans Arabic", 8))
        warn.setStyleSheet("color: #B42318;")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        btn_row = QHBoxLayout()
        btn_del = QPushButton("تأكيد حذف الحقل")
        btn_del.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_del.setStyleSheet("background: #D92D20; color: #FFFFFF; border-radius: 6px; padding: 8px 16px;")
        btn_del.clicked.connect(self.accept)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_cancel.setStyleSheet("background: #F2F4F7; color: #344054; border: 1px solid #D0D5DD; border-radius: 6px; padding: 8px 16px;")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_del)
        layout.addLayout(btn_row)

    def get_selected_column(self):
        return self.combo_cols.currentText()


class RecordDetailsDialog(QDialog):
    """نافذة لعرض التفاصيل الكاملة للقيد بشكل منسق ومقروء"""
    def __init__(self, record, columns, title="تفاصيل القيد", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 620)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        hdr = QLabel(f"📄 {title}")
        hdr.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #14372e; padding-bottom: 6px; border-bottom: 2px solid #c59b27;")
        layout.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E4E7EC; border-radius: 8px; background: #FFFFFF; }")

        card = QWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(8)

        for col in columns:
            val = record.get(col, "")
            val_str = "—" if val is None or str(val).strip() == "" else str(val).strip()

            row_box = QFrame()
            row_box.setStyleSheet("background: #F8F9FA; border: 1px solid #E4E7EC; border-radius: 6px; padding: 6px 10px;")
            r_lay = QVBoxLayout(row_box)
            r_lay.setContentsMargins(0, 0, 0, 0)
            r_lay.setSpacing(2)

            lbl_k = QLabel(col)
            lbl_k.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            lbl_k.setStyleSheet("color: #667085;")

            lbl_v = QLabel(val_str)
            lbl_v.setFont(QFont("IBM Plex Sans Arabic", 10))
            lbl_v.setStyleSheet("color: #1B1F24;")
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_v.setWordWrap(True)

            r_lay.addWidget(lbl_k)
            r_lay.addWidget(lbl_v)
            card_layout.addWidget(row_box)

        scroll.setWidget(card)
        layout.addWidget(scroll, stretch=1)

        btn_close = QPushButton("إغلاق")
        btn_close.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet("""
            QPushButton {
                background: #14372e;
                color: #FFFFFF;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
            }
            QPushButton:hover { background: #1b493d; }
        """)
        btn_close.clicked.connect(self.accept)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)


class AccessHubWidget(QWidget):
    """القسم المستقل لمركز بيانات Access الموحد داخل تطبيق الحاسوب - تصميم بيانات مركّز ومريح"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # تحديد القسم الافتراضي من أول ملف محلي متاح
        init_file = "all"
        if LOCAL_DATA_DIR.exists():
            idx_p = LOCAL_DATA_DIR / "index.json"
            if idx_p.exists():
                try:
                    with open(idx_p, "r", encoding="utf-8") as f:
                        _idx = json.load(f)
                        if _idx.get("files"):
                            init_file = _idx["files"][0]["name"]
                except Exception:
                    pass

        self.active_file = init_file
        self.active_table = ""
        self.current_page = 1
        self.limit = 50
        self.sort_dir = "none"  # "none", "desc", "asc"
        self.sort_col = ""
        self.date_columns = []
        self.current_data = None
        self.loader_thread = None

        self._build_ui()
        self.load_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # ========================================================
        # 1. شريط الملاحة والمصدر الموحد (Compact Nav Bar - Height ~40px)
        # ========================================================
        nav_frame = QFrame()
        nav_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-right: 4px solid #14372e;
                border-radius: 8px;
            }
        """)
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(8)

        # عنوان المركز المدمج
        lbl_title = QLabel("🏛️ مركز بيانات Access")
        lbl_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #14372e; border: none; background: transparent;")
        nav_layout.addWidget(lbl_title)

        # فاصل
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #E4E7EC; max-height: 22px;")
        nav_layout.addWidget(sep1)

        # اختيار القسم / الملف (Sleek QComboBox)
        lbl_sec = QLabel("📁 القسم:")
        lbl_sec.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.Bold))
        lbl_sec.setStyleSheet("color: #344054; border: none; background: transparent;")
        nav_layout.addWidget(lbl_sec)

        self.combo_file = QComboBox()
        self.combo_file.setFont(QFont("IBM Plex Sans Arabic", 10))
        self.combo_file.setMinimumWidth(280)
        self.combo_file.setStyleSheet("""
            QComboBox {
                background: #F8F9FA;
                border: 1.5px solid #D0D5DD;
                border-radius: 6px;
                padding: 5px 12px;
                color: #14372e;
                font-weight: bold;
                font-size: 13px;
            }
            QComboBox:hover { border-color: #14372e; background: #FFFFFF; }
            QComboBox QAbstractItemView {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                selection-background-color: #EDF5F2;
                selection-color: #14372e;
                padding: 6px;
                font-size: 13px;
            }
        """)
        self.combo_file.currentIndexChanged.connect(self._on_file_combo_changed)
        nav_layout.addWidget(self.combo_file)

        nav_layout.addStretch()

        # شارة إجمالي السجلات وزر التحديث المدمج
        self.stat_badge = QLabel("88,987 قيد")
        self.stat_badge.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.stat_badge.setStyleSheet("""
            background: #EDF5F2;
            color: #14372e;
            padding: 5px 12px;
            border-radius: 6px;
            border: 1px solid #CBE3DA;
        """)
        nav_layout.addWidget(self.stat_badge)

        self.btn_refresh = QPushButton("🔄 تحديث")
        self.btn_refresh.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: #14372e;
                color: #FFFFFF;
                padding: 6px 16px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #1b493d; }
        """)
        self.btn_refresh.clicked.connect(self.load_data)
        nav_layout.addWidget(self.btn_refresh)

        main_layout.addWidget(nav_frame)

        # ========================================================
        # 2. شريط الأصناف والجداول الفرعية الواسع والواضح (توزيع شبكي ذكي)
        # ========================================================
        tables_frame = QFrame()
        tables_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 8px;
            }
        """)
        tables_layout = QHBoxLayout(tables_frame)
        tables_layout.setContentsMargins(12, 6, 12, 6)
        tables_layout.setSpacing(12)

        self.lbl_tbl = QLabel("🏷️ الأصناف والجداول:")
        self.lbl_tbl.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.Bold))
        self.lbl_tbl.setMinimumWidth(155)
        self.lbl_tbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_tbl.setStyleSheet("color: #14372e; border: none; background: transparent; padding-right: 4px;")
        tables_layout.addWidget(self.lbl_tbl)

        # حاوية أزرار الأصناف بتوزيع شبكي مرن يتسع لكافة الأصناف بالكامل دون أي قص أو اختفاء
        self.subtables_scroll = QScrollArea()
        self.subtables_scroll.setWidgetResizable(True)
        self.subtables_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.subtables_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.subtables_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.subtables_container = QWidget()
        self.subtables_container.setStyleSheet("background: transparent; border: none;")
        self.subtables_grid = QGridLayout(self.subtables_container)
        self.subtables_grid.setContentsMargins(0, 0, 0, 0)
        self.subtables_grid.setHorizontalSpacing(8)
        self.subtables_grid.setVerticalSpacing(6)
        self.subtable_btn_group = QButtonGroup(self)
        self.subtable_btn_group.setExclusive(True)

        self.subtables_scroll.setWidget(self.subtables_container)
        tables_layout.addWidget(self.subtables_scroll, stretch=1)

        main_layout.addWidget(tables_frame)

        # ========================================================
        # 2. شريط البحث والعمليات السريعة (Actions Bar - Height ~38px)
        # ========================================================
        action_frame = QFrame()
        action_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 8px;
            }
        """)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(6, 3, 6, 3)
        action_layout.setSpacing(8)

        # حقل البحث الرئيسي
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 بحث فوري في كافة الحقول والسجلات والأسماء والشركات...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #F8F9FA;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                color: #1B1F24;
            }
            QLineEdit:focus { border: 1.5px solid #14372e; background: #FFFFFF; }
        """)
        # مؤقت تأخير البحث لمنع أي ثقل أثناء الكتابة (Debounce 250ms)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self._execute_search)

        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._execute_search)
        action_layout.addWidget(self.search_input, stretch=1)

        # أزرار الإجراءات الأساسية (تم سحب زر الحذف لحماية البيانات وحصر الحذف في لوحة الأدمن)
        self.btn_add = QPushButton("➕ إضافة قيد")
        self.btn_add.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: #14372e;
                color: #FFFFFF;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #1b493d; }
        """)
        self.btn_add.clicked.connect(self._on_add_clicked)
        action_layout.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏️ تعديل")
        self.btn_edit.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_edit.setStyleSheet("""
            QPushButton {
                background: #F7F8FA;
                color: #14372e;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #E4E7EC; }
        """)
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        action_layout.addWidget(self.btn_edit)

        self.btn_export = QPushButton("📥 تصدير Excel")
        self.btn_export.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #344054;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #F2F4F7; }
        """)
        self.btn_export.clicked.connect(self._on_export_clicked)
        action_layout.addWidget(self.btn_export)

        # قائمة أدوات الحقول والفرز المتقدمة (Menu Button)
        self.btn_tools = QPushButton("⚙️ خيارات متقدمة ▾")
        self.btn_tools.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.btn_tools.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tools.setStyleSheet("""
            QPushButton {
                background: #F8F9FA;
                color: #475467;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover { background: #E4E7EC; color: #101828; }
        """)
        self.btn_tools.clicked.connect(self._open_tools_menu)
        action_layout.addWidget(self.btn_tools)

        main_layout.addWidget(action_frame)

        # ========================================================
        # 3. الجدول الرئيسي للبيانات (Main Data Grid - يغطي 80% من الشاشة)
        # ========================================================
        self.table_widget = QTableWidget()
        self.table_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.verticalHeader().setDefaultSectionSize(36)
        self.table_widget.horizontalHeader().setStretchLastSection(False)
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table_widget.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table_widget.setFont(QFont("IBM Plex Sans Arabic", 10))
        self.table_widget.doubleClicked.connect(self._on_edit_clicked)

        # قائمة الزر الأيمن المخصصة
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self._show_context_menu)

        self.table_widget.setStyleSheet("""
            QTableWidget {
                background: #FFFFFF;
                alternate-background-color: #F8F9FA;
                border: 1px solid #E4E7EC;
                border-radius: 8px;
                gridline-color: #F2F4F7;
                color: #1B1F24;
                selection-background-color: #EDF5F2;
                selection-color: #14372e;
            }
            QHeaderView::section {
                background: #F2F4F7;
                color: #344054;
                font-family: 'IBM Plex Sans Arabic';
                font-size: 12px;
                font-weight: bold;
                padding: 8px 12px;
                border: 1px solid #E4E7EC;
                cursor: pointer;
            }
            QHeaderView::section:hover {
                background: #E4E7EC;
                color: #14372e;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QTableWidget::item:selected {
                background-color: #EDF5F2;
                color: #14372e;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.table_widget, stretch=1)

        # ========================================================
        # 4. شريط الترقيم والتنقل السفلي (Bottom Status & Pagination)
        # ========================================================
        pagination_frame = QFrame()
        pagination_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 6px;
            }
        """)
        pagination_layout = QHBoxLayout(pagination_frame)
        pagination_layout.setContentsMargins(8, 3, 8, 3)
        pagination_layout.setSpacing(10)

        self.lbl_page_info = QLabel("الصفحة 1 من 1")
        self.lbl_page_info.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_page_info.setStyleSheet("color: #475467; border: none; background: transparent;")
        pagination_layout.addWidget(self.lbl_page_info)

        self.lbl_sort_status = QLabel("")
        self.lbl_sort_status.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_sort_status.setStyleSheet("color: #027A48; font-weight: bold; border: none; background: transparent;")
        pagination_layout.addWidget(self.lbl_sort_status)

        self.btn_reset_sort = QPushButton("🔄 الترتيب الأصلي")
        self.btn_reset_sort.setFont(QFont("IBM Plex Sans Arabic", 8))
        self.btn_reset_sort.setVisible(False)
        self.btn_reset_sort.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_reset_sort.setStyleSheet("background: #F2F4F7; color: #344054; border: 1px solid #D0D5DD; padding: 2px 8px; border-radius: 4px;")
        self.btn_reset_sort.clicked.connect(self._reset_sort)
        pagination_layout.addWidget(self.btn_reset_sort)

        pagination_layout.addStretch()

        self.btn_prev = QPushButton("⏮️ السابق")
        self.btn_prev.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.btn_prev.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                padding: 4px 12px;
                border-radius: 5px;
                color: #344054;
            }
            QPushButton:hover:enabled { background: #F2F4F7; }
            QPushButton:disabled { color: #98A2B3; background: #F8F9FA; }
        """)
        self.btn_prev.clicked.connect(self._prev_page)
        pagination_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("التالي ⏭️")
        self.btn_next.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.btn_next.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                padding: 4px 12px;
                border-radius: 5px;
                color: #344054;
            }
            QPushButton:hover:enabled { background: #F2F4F7; }
            QPushButton:disabled { color: #98A2B3; background: #F8F9FA; }
        """)
        self.btn_next.clicked.connect(self._next_page)
        pagination_layout.addWidget(self.btn_next)

        main_layout.addWidget(pagination_frame)

    def _subtable_btn_style(self):
        return """
            QPushButton {
                background: #F8F9FA;
                color: #344054;
                border: 1.5px solid #D0D5DD;
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 13px;
                font-weight: bold;
                min-width: 75px;
            }
            QPushButton:hover { background: #EDF5F2; color: #14372e; border-color: #14372e; }
            QPushButton:checked {
                background: #14372e;
                color: #FFFFFF;
                border: 1.5px solid #14372e;
                font-weight: bold;
            }
        """

    def load_data(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("جاري التحميل...")

        query = self.search_input.text().strip()
        self.loader_thread = DataLoaderThread(
            self.active_file,
            self.active_table,
            query,
            self.current_page,
            self.limit,
            sort_dir=self.sort_dir,
            sort_col=self.sort_col
        )
        self.loader_thread.data_loaded.connect(self._on_data_loaded)
        self.loader_thread.error_occurred.connect(self._on_data_error)
        self.loader_thread.start()

    def _on_data_loaded(self, data):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 تحديث")
        self.current_data = data

        # 1. تحديث قائمة الأقسام (الملفات) في الـ ComboBox مرة واحدة
        files = data.get("files", [])
        if files and self.combo_file.count() == 0:
            self.combo_file.blockSignals(True)
            for f in files:
                fname = f["name"]
                self.combo_file.addItem(f"📁 {fname}", fname)
            # إضافة خيار الدمج الشامل
            self.combo_file.addItem("🌐 الدمج الشامل (كافة الأقسام)", "all")

            # تحديد القسم النشط
            cur_f = data.get("active_file", self.active_file)
            for i in range(self.combo_file.count()):
                if self.combo_file.itemData(i) == cur_f:
                    self.combo_file.setCurrentIndex(i)
                    break
            self.combo_file.blockSignals(False)

        # 2. تحديث أزرار الجداول التابعة لهذا القسم وترتيبها المنطقي وعرضها الكامل دون أي قص
        while self.subtables_grid.count():
            item = self.subtables_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tables_list = sort_tables_by_priority(data.get("available_tables", []))
        active_tbl = data.get("active_table", self.active_table)
        self.active_table = active_tbl

        self.lbl_tbl.setText(f"🏷️ الأصناف ({len(tables_list)}):")

        # ضبط الارتفاع بمرونة: سطر واحد إذا كانت 6 أو أقل، وسطرين متناسقين إذا كانت أكثر من 6 لضمان ظهور كافة الأصناف الـ 11
        if len(tables_list) <= 6:
            self.subtables_scroll.setFixedHeight(36)
            cols_per_row = max(1, len(tables_list))
        else:
            self.subtables_scroll.setFixedHeight(74)
            cols_per_row = max(5, (len(tables_list) + 1) // 2)

        for idx, tbl in enumerate(tables_list):
            r = idx // cols_per_row
            c = idx % cols_per_row

            btn = QPushButton(tbl)
            btn.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.Bold))
            btn.setCheckable(True)
            btn.setChecked(tbl == active_tbl)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(self._subtable_btn_style())
            btn.clicked.connect(lambda checked, t=tbl: self._on_subtable_clicked(t))
            self.subtable_btn_group.addButton(btn)
            self.subtables_grid.addWidget(btn, r, c)

        # 3. تعبئة الجدول بالحقول والمعلومات الأصلية 100% من الملف بدون أي تغيير إطلاقاً (مع تسريع الرسم الفائق)
        cols = data.get("columns", [])
        rows = data.get("rows", [])

        self.table_widget.setUpdatesEnabled(False)
        self.table_widget.blockSignals(True)
        try:
            display_cols = []
            if self.active_file == "all":
                display_cols.append("الملف المصدر")

            for c in cols:
                header_txt = c
                if c == data.get("sort_col"):
                    if self.sort_dir == "desc":
                        header_txt = f"{c} ⬇️"
                    elif self.sort_dir == "asc":
                        header_txt = f"{c} ⬆️"
                display_cols.append(header_txt)

            self.table_widget.setColumnCount(len(display_cols))
            self.table_widget.setHorizontalHeaderLabels(display_cols)
            self.table_widget.setRowCount(len(rows))

            for r_idx, row in enumerate(rows):
                c_offset = 0
                if self.active_file == "all":
                    src_item = QTableWidgetItem(str(row.get("_adh_file", "")))
                    src_item.setForeground(QColor("#14372e"))
                    src_item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                    src_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table_widget.setItem(r_idx, 0, src_item)
                    c_offset = 1

                for c_idx, col in enumerate(cols):
                    val = row.get(col, "")
                    val_str = "" if val is None else str(val).strip()
                    item = QTableWidgetItem(val_str)
                    # محاذاة واضحة ومناسبة لنوع القيمة
                    col_lower = col.lower()
                    if col_lower in ('id', 'ت', 'stampno', 'renewalno') or any(k in col_lower for k in DATE_KEYWORDS):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_widget.setItem(r_idx, c_idx + c_offset, item)

            # ضبط عرض الأعمدة تلقائياً لضمان عدم ظهور النقاط (...)
            self.table_widget.resizeColumnsToContents()
            for c in range(self.table_widget.columnCount()):
                col_w = self.table_widget.columnWidth(c)
                if col_w < 110:
                    self.table_widget.setColumnWidth(c, 110)
                elif col_w > 400:
                    self.table_widget.setColumnWidth(c, 400)
        finally:
            self.table_widget.blockSignals(False)
            self.table_widget.setUpdatesEnabled(True)

        # 4. تحديث معلومات الترقيم
        cur_p = data.get("page", 1)
        tot_p = data.get("total_pages", 1)
        matches = data.get("total_matches", 0)
        self.lbl_page_info.setText(f"الصفحة {cur_p} من {tot_p} (إجمالي السجلات: {matches:,})")
        self.btn_prev.setEnabled(cur_p > 1)
        self.btn_next.setEnabled(cur_p < tot_p)

        # شارة عدد السجلات
        tot_all = data.get("total_records", 88987)
        self.stat_badge.setText(f"{tot_all:,} قيد")

        # حالة الفرز
        if self.sort_dir in ('desc', 'asc') and data.get("sort_col"):
            dir_str = "من الأحدث إلى الأقدم ⬇️" if self.sort_dir == "desc" else "من الأقدم إلى الأحدث ⬆️"
            self.lbl_sort_status.setText(f"⚡ الفرز: {data.get('sort_col')} ({dir_str})")
            self.btn_reset_sort.setVisible(True)
        else:
            self.lbl_sort_status.setText("")
            self.btn_reset_sort.setVisible(False)

    def _on_data_error(self, err):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 تحديث")
        QMessageBox.warning(self, "تنبيه", f"تعذر استرجاع البيانات: {err}")

    def _on_file_combo_changed(self):
        val = self.combo_file.currentData()
        if val and val != self.active_file:
            self.active_file = val
            self.active_table = ""
            self.current_page = 1
            self.load_data()

    def _on_subtable_clicked(self, tbl):
        self.active_table = tbl
        self.current_page = 1
        self.load_data()

    def _on_search_text_changed(self):
        self.search_timer.start(250)

    def _execute_search(self):
        self.current_page = 1
        self.load_data()

    def _on_search_changed(self):
        self._execute_search()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def _next_page(self):
        self.current_page += 1
        self.load_data()

    def _on_header_clicked(self, logical_index):
        """الفرز المباشر بالنقر على رأس أي عمود"""
        if not self.current_data:
            return
        cols = self.current_data.get("columns", [])
        c_offset = 1 if self.active_file == "all" else 0
        if logical_index < c_offset:
            return
        col_name = cols[logical_index - c_offset]

        if self.sort_col == col_name:
            if self.sort_dir == "desc":
                self.sort_dir = "asc"
            elif self.sort_dir == "asc":
                self.sort_dir = "none"
            else:
                self.sort_dir = "desc"
        else:
            self.sort_col = col_name
            self.sort_dir = "desc"

        self.current_page = 1
        self.load_data()

    def _reset_sort(self):
        self.sort_dir = "none"
        self.sort_col = ""
        self.current_page = 1
        self.load_data()

    def _open_tools_menu(self):
        """قائمة منسدلة أنيقة لإدارة الحقول والفرز دون تشويه الواجهة"""
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu.setFont(QFont("IBM Plex Sans Arabic", 9))
        menu.setStyleSheet("""
            QMenu {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
                color: #344054;
            }
            QMenu::item:selected {
                background: #EDF5F2;
                color: #14372e;
                font-weight: bold;
            }
        """)

        act_add_col = menu.addAction("➕ إضافة حقل جديد لهذا القسم")
        menu.addSeparator()
        act_sort_desc = menu.addAction("⬇️ فرز زمني (من الأحدث للأقدم)")
        act_sort_asc = menu.addAction("⬆️ فرز زمني (من الأقدم للأحدث)")
        act_reset_sort = menu.addAction("🔄 الترتيب الأصلي (إلغاء الفرز)")

        pos = self.btn_tools.mapToGlobal(self.btn_tools.rect().bottomRight())
        action = menu.exec(pos)
        if action == act_add_col:
            self._on_add_column_clicked()
        elif action == act_sort_desc:
            self.sort_dir = "desc"
            self.sort_col = "date_auto"
            self.current_page = 1
            self.load_data()
        elif action == act_sort_asc:
            self.sort_dir = "asc"
            self.sort_col = "date_auto"
            self.current_page = 1
            self.load_data()
        elif action == act_reset_sort:
            self._reset_sort()

    def _show_context_menu(self, pos):
        """قائمة الزر الأيمن المخصصة للجدول (تم سحب خيار الحذف لنظام الأدمن)"""
        item = self.table_widget.itemAt(pos)
        if not item or not self.current_data or not self.current_data.get("rows"):
            return
        row_idx = self.table_widget.row(item)
        if row_idx < 0 or row_idx >= len(self.current_data["rows"]):
            return

        self.table_widget.selectRow(row_idx)
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu.setFont(QFont("IBM Plex Sans Arabic", 9))
        menu.setStyleSheet("""
            QMenu {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
                color: #344054;
            }
            QMenu::item:selected {
                background: #EDF5F2;
                color: #14372e;
                font-weight: bold;
            }
        """)

        act_details = menu.addAction("🔍 عرض تفاصيل القيد بالكامل")
        menu.addSeparator()
        act_edit = menu.addAction("✏️ تعديل هذا القيد")
        menu.addSeparator()
        act_copy = menu.addAction("📋 نسخ بيانات السجل")

        action = menu.exec(self.table_widget.viewport().mapToGlobal(pos))
        if action == act_details:
            self._show_record_details(row_idx)
        elif action == act_edit:
            self._on_edit_clicked()
        elif action == act_copy:
            self._copy_record_to_clipboard(row_idx)

    def _show_record_details(self, row_idx):
        if not self.current_data or not self.current_data.get("rows"):
            return
        row = self.current_data["rows"][row_idx]
        cols = self.current_data.get("columns", [])
        dlg = RecordDetailsDialog(row, cols, title=f"تفاصيل القيد - جدول {self.active_table}", parent=self)
        dlg.exec()

    def _copy_record_to_clipboard(self, row_idx):
        if not self.current_data or not self.current_data.get("rows"):
            return
        row = self.current_data["rows"][row_idx]
        cols = self.current_data.get("columns", [])
        lines = []
        for c in cols:
            val = row.get(c, "")
            lines.append(f"{c}: {val}")
        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            QMessageBox.information(self, "تم النسخ", "تم نسخ بيانات القيد بالكامل إلى الحافظة بنجاح.")

    def _on_add_column_clicked(self):
        """إضافة حقل جديد إلى الجدول"""
        if not self.current_data:
            return
        target_file = self.active_file if self.active_file != "all" else (self.current_data["files"][0]["name"] if self.current_data.get("files") else "الاسم التجاري 2025 - 2026")
        dlg = AddColumnDialog(self.active_table, target_file, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_col = dlg.get_column_name()
            try:
                r = requests.post(CLOUD_API_URL, json={
                    "file": target_file,
                    "table": self.active_table,
                    "action": "ADD_COLUMN",
                    "columnName": new_col
                }, timeout=10)
                if r.status_code == 200:
                    QMessageBox.information(self, "نجاح", f"تمت إضافة الحقل '{new_col}' سحابياً بنجاح وتعميمه للجميع.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشلت إضافة الحقل: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_del_column_clicked(self):
        """حذف حقل من الجدول"""
        if not self.current_data or not self.current_data.get("columns"):
            QMessageBox.information(self, "تنبيه", "لا توجد حقول لحذفها في هذا الجدول.")
            return

        cols = self.current_data["columns"]
        dlg = DeleteColumnDialog(self.active_table, cols, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            col_to_del = dlg.get_selected_column()
            target_file = self.active_file if self.active_file != "all" else (self.current_data["files"][0]["name"] if self.current_data.get("files") else "الاسم التجاري 2025 - 2026")
            try:
                r = requests.post(CLOUD_API_URL, json={
                    "file": target_file,
                    "table": self.active_table,
                    "action": "DELETE_COLUMN",
                    "columnName": col_to_del
                }, timeout=10)
                if r.status_code == 200:
                    QMessageBox.information(self, "نجاح", f"تم حذف الحقل '{col_to_del}' سحابياً بنجاح.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل حذف الحقل: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_add_clicked(self):
        """إضافة قيد جديد مع إمكانية تحديد الملف إذا كان في وضع الدمج الشامل"""
        if not self.current_data or not self.current_data.get("columns"):
            return
        cols = self.current_data["columns"]
        files = self.current_data.get("files", [])
        dlg = RecordFormDialog(f"إضافة قيد جديد في جدول ({self.active_table})", cols, files_list=files if self.active_file == "all" else None, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            target_file = dlg.get_target_file() or (self.active_file if self.active_file != "all" else self.current_data["files"][0]["name"])
            try:
                r = requests.post(CLOUD_API_URL, json={
                    "file": target_file,
                    "table": self.active_table,
                    "record": new_data
                }, timeout=10)
                if r.status_code == 200:
                    QMessageBox.information(self, "نجاح", "تمت إضافة القيد بنجاح ومزامنته سحابياً لجميع الأجهزة.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل الحفظ: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_edit_clicked(self):
        row_idx = self.table_widget.currentRow()
        if row_idx < 0 or not self.current_data or not self.current_data.get("rows"):
            QMessageBox.information(self, "تنبيه", "يرجى تحديد السجل المراد تعديله أولاً.")
            return

        row_data = self.current_data["rows"][row_idx]
        cols = self.current_data["columns"]
        dlg = RecordFormDialog(f"تعديل القيد (الملف: {row_data.get('_adh_file')})", cols, initial_data=row_data, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updates = dlg.get_data()
            try:
                r = requests.put(CLOUD_API_URL, json={
                    "file": row_data["_adh_file"],
                    "table": row_data["_adh_table"],
                    "id": row_data["_adh_id"],
                    "updates": updates
                }, timeout=10)
                if r.status_code == 200:
                    QMessageBox.information(self, "نجاح", "تم تعديل السجل ومزامنته فورياً مع كافة الموظفين.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل التعديل: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_delete_clicked(self):
        QMessageBox.information(
            self, "إشعار أمني - غرفة تجارة كربلاء",
            "تم حظر وتجريد تطبيق سطح المكتب من صلاحية الحذف المباشر لحماية سجلات التجار والدلالين من الحذف العرضي.\n\n"
            "يمكن إجراء عمليات الحذف وإدارة الأقسام والحقول حصرياً عبر لوحة الإدارة المركزية (Admin Dashboard) للمشرفين المصرح لهم."
        )

    def _on_export_clicked(self):
        if not self.current_data or not self.current_data.get("rows"):
            QMessageBox.information(self, "تنبيه", "لا توجد سجلات لتصديرها.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف Excel / CSV", f"{self.active_file}_{self.active_table}.csv", "ملف CSV (*.csv)")
        if path:
            try:
                cols = self.current_data["columns"]
                lines = [",".join([f'"{c}"' for c in cols])]
                for r in self.current_data["rows"]:
                    row_vals = []
                    for c in cols:
                        v = str(r.get(c, "") or "").replace('"', '""')
                        row_vals.append(f'"{v}"')
                    lines.append(",".join(row_vals))

                with open(path, "w", encoding="utf-8-sig") as f:
                    f.write("\n".join(lines))
                QMessageBox.information(self, "نجاح", f"تم تصدير البيانات بنجاح إلى:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل التصدير: {e}")

