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
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QButtonGroup, QFrame, QDialog, QMessageBox, QFileDialog,
    QScrollArea, QAbstractItemView, QProgressDialog, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QCursor, QIcon

CLOUD_API_URL = "https://web-dashboard-pi-self.vercel.app/api/access-hub"
LOCAL_API_URL = "http://localhost:3000/api/access-hub"

# مسار مجلد البيانات المحلي كنسخة احتياطية سريعة
LOCAL_DATA_DIR = Path(__file__).parent.parent.parent / "web-dashboard" / "data" / "access-hub"

DATE_KEYWORDS = ['date', 'تاريخ', 'affiliation', 'expiration', 'year', 'سنة', 'مواليد']


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
        params = {
            "file": self.file_name,
            "table": self.table_name,
            "search": self.search_query,
            "page": self.page,
            "limit": self.limit,
            "sort_dir": self.sort_dir,
            "sort_col": self.sort_col
        }

        # 1. فحص الخادم المحلي السريع
        try:
            r = requests.get(LOCAL_API_URL, params=params, timeout=2)
            if r.status_code == 200:
                self.data_loaded.emit(r.json())
                return
        except Exception:
            pass

        # 2. قراءة البيانات محلياً من ملفات الـ JSON في القرص إذا توفرت
        if LOCAL_DATA_DIR.exists():
            try:
                result = self._load_from_local_disk()
                if result:
                    self.data_loaded.emit(result)
                    return
            except Exception:
                pass

        # 3. الاتصال بالسحابة المباشرة Vercel
        try:
            r = requests.get(CLOUD_API_URL, params=params, timeout=12)
            if r.status_code == 200:
                self.data_loaded.emit(r.json())
                return
            else:
                self.error_occurred.emit(f"خطأ في الخادم السحابي: {r.status_code}")
        except Exception as e:
            self.error_occurred.emit(f"تعذر الاتصال بالسحابة: {e}")

    def _load_from_local_disk(self):
        idx_path = LOCAL_DATA_DIR / "index.json"
        if not idx_path.exists():
            return None
        with open(idx_path, "r", encoding="utf-8") as f:
            idx = json.load(f)

        req_file = self.file_name
        req_table = self.table_name
        search = self.search_query.strip().lower()

        # قراءة الطفرات السحابية المخزنة محلياً إن وجدت
        mutations = {"adds": [], "updates": {}, "deletes": [], "added_columns": {}, "deleted_columns": {}}
        mut_path = LOCAL_DATA_DIR / "mutations.json"
        if mut_path.exists():
            try:
                with open(mut_path, "r", encoding="utf-8") as mf:
                    mutations = json.load(mf)
            except Exception:
                pass

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
            available_tables = list(tables_set)
            if not req_table or req_table not in tables_set:
                req_table = available_tables[0] if available_tables else "التجار"

            cols_order = []
            cols_seen = set()

            for f in idx.get("files", []):
                fpath = LOCAL_DATA_DIR / f"{f['name']}.json"
                if not fpath.exists():
                    continue
                with open(fpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)

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
            fpath = LOCAL_DATA_DIR / f"{req_file}.json"
            if not fpath.exists():
                return None
            with open(fpath, "r", encoding="utf-8") as jf:
                data = json.load(jf)

            available_tables = list(data.get("tables", {}).keys())
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


class AccessHubWidget(QWidget):
    """القسم المستقل لمركز بيانات Access الموحد داخل تطبيق الحاسوب"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.active_file = "all"
        self.active_table = "التجار"
        self.current_page = 1
        self.limit = 50
        self.sort_dir = "none"  # "none", "desc", "asc"
        self.sort_col = "date_auto"
        self.date_columns = []
        self.current_data = None
        self.loader_thread = None

        self._build_ui()
        self.load_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. الترويسة العليا للمركز
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-right: 4px solid #14372e;
                border-radius: 10px;
                padding: 6px 12px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_col = QVBoxLayout()
        title = QLabel("🏛️ مركز قواعد بيانات Access الموحد (88,987 قيد)")
        title.setFont(QFont("IBM Plex Sans Arabic", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #14372e; border: none; background: transparent;")
        title_col.addWidget(title)

        subtitle = QLabel("دمج سحابي فوري لكافة السجلات مع الحفاظ التام 100% على ترتيب الحقول والمعلومات الأصلية والفرز الزمني وإدارة الحقول")
        subtitle.setFont(QFont("IBM Plex Sans Arabic", 9))
        subtitle.setStyleSheet("color: #667085; border: none; background: transparent;")
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)

        header_layout.addStretch()

        self.stat_badge = QLabel("88,987 قيد مركزي")
        self.stat_badge.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.stat_badge.setStyleSheet("""
            background: #EDF5F2;
            color: #14372e;
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid #CBE3DA;
        """)
        header_layout.addWidget(self.stat_badge)

        self.btn_refresh = QPushButton("🔄 تحديث فوري")
        self.btn_refresh.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.setStyleSheet("""
            background: #14372e;
            color: #FFFFFF;
            padding: 6px 12px;
            border-radius: 6px;
        """)
        self.btn_refresh.clicked.connect(self.load_data)
        header_layout.addWidget(self.btn_refresh)

        main_layout.addWidget(header_frame)

        # 2. شريط الخانات الرئيسي (الدمج الشامل + الخانات بالأسماء الحقيقية للملفات)
        tabs_scroll = QScrollArea()
        tabs_scroll.setFixedHeight(46)
        tabs_scroll.setWidgetResizable(True)
        tabs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tabs_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tabs_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.tabs_container = QWidget()
        self.tabs_layout = QHBoxLayout(self.tabs_container)
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(6)

        self.file_btn_group = QButtonGroup(self)
        self.file_btn_group.setExclusive(True)

        self.btn_tab_all = QPushButton("🌐 الدمج الشامل (كافة الملفات)")
        self.btn_tab_all.setCheckable(True)
        self.btn_tab_all.setChecked(True)
        self.btn_tab_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tab_all.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_tab_all.setStyleSheet(self._tab_btn_style())
        self.btn_tab_all.clicked.connect(lambda: self._on_file_tab_clicked("all"))
        self.file_btn_group.addButton(self.btn_tab_all)
        self.tabs_layout.addWidget(self.btn_tab_all)

        tabs_scroll.setWidget(self.tabs_container)
        main_layout.addWidget(tabs_scroll)

        # 3. شريط اختيار الجداول الفرعية (التجار، الشركات، المطاعم...)
        self.subtables_frame = QFrame()
        self.subtables_frame.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E4E7EC; border-radius: 8px; padding: 4px; }")
        self.subtables_layout = QHBoxLayout(self.subtables_frame)
        self.subtables_layout.setContentsMargins(4, 2, 4, 2)
        self.subtables_layout.setSpacing(4)
        self.subtable_btn_group = QButtonGroup(self)
        self.subtable_btn_group.setExclusive(True)

        main_layout.addWidget(self.subtables_frame)

        # 4. شريط البحث وإجراءات القيود (Row 1)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 بحث فوري في كافة السجلات والتجار والشركات...")
        self.search_input.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1.5px solid #14372e; }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_input, stretch=1)

        self.btn_add = QPushButton("➕ إضافة قيد جديد")
        self.btn_add.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add.setStyleSheet("background: #14372e; color: #FFFFFF; border-radius: 6px; padding: 6px 14px;")
        self.btn_add.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏️ تعديل قيد")
        self.btn_edit.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_edit.setStyleSheet("background: #F7F8FA; color: #14372e; border: 1px solid #D0D5DD; border-radius: 6px; padding: 6px 12px;")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        toolbar.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑️ حذف قيد")
        self.btn_delete.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_delete.setStyleSheet("background: #FEF3F2; color: #B42318; border: 1px solid #FECDCA; border-radius: 6px; padding: 6px 12px;")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        toolbar.addWidget(self.btn_delete)

        self.btn_export = QPushButton("📥 تصدير Excel")
        self.btn_export.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export.setStyleSheet("background: #FFFFFF; color: #344054; border: 1px solid #D0D5DD; border-radius: 6px; padding: 6px 12px;")
        self.btn_export.clicked.connect(self._on_export_clicked)
        toolbar.addWidget(self.btn_export)

        main_layout.addLayout(toolbar)

        # 5. شريط الترتيب الزمني وإدارة الحقول المتقدم (Row 2)
        controls_frame = QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background: #F8F9FA;
                border: 1px solid #E4E7EC;
                border-radius: 8px;
                padding: 4px 8px;
            }
        """)
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(6, 4, 6, 4)
        controls_layout.setSpacing(10)

        # قسم ترتيب التاريخ
        lbl_sort = QLabel("📅 ترتيب التاريخ:")
        lbl_sort.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl_sort.setStyleSheet("color: #14372e;")
        controls_layout.addWidget(lbl_sort)

        self.btn_sort_desc = QPushButton("⬇️ من الجديد إلى القديم")
        self.btn_sort_desc.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.btn_sort_desc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_sort_desc.clicked.connect(lambda: self._set_sort_dir("desc"))
        controls_layout.addWidget(self.btn_sort_desc)

        self.btn_sort_asc = QPushButton("⬆️ من القديم إلى الجديد")
        self.btn_sort_asc.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.btn_sort_asc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_sort_asc.clicked.connect(lambda: self._set_sort_dir("asc"))
        controls_layout.addWidget(self.btn_sort_asc)

        self.btn_sort_none = QPushButton("🔄 الترتيب الأصلي")
        self.btn_sort_none.setFont(QFont("IBM Plex Sans Arabic", 8))
        self.btn_sort_none.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_sort_none.clicked.connect(lambda: self._set_sort_dir("none"))
        controls_layout.addWidget(self.btn_sort_none)

        # حقل اختيار عمود التاريخ
        self.combo_date_col = QComboBox()
        self.combo_date_col.setFont(QFont("IBM Plex Sans Arabic", 8))
        self.combo_date_col.setStyleSheet("""
            QComboBox {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 5px;
                padding: 3px 8px;
                color: #344054;
            }
        """)
        self.combo_date_col.addItem("تلقائي (حقل التاريخ الذكي)", "date_auto")
        self.combo_date_col.currentIndexChanged.connect(self._on_date_col_changed)
        controls_layout.addWidget(self.combo_date_col)

        # فاصل
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #D0D5DD;")
        controls_layout.addWidget(sep)

        # قسم إدارة الحقول
        lbl_cols_mgmt = QLabel("📋 إدارة الحقول:")
        lbl_cols_mgmt.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl_cols_mgmt.setStyleSheet("color: #14372e;")
        controls_layout.addWidget(lbl_cols_mgmt)

        self.btn_add_col = QPushButton("➕ إضافة حقل جديد")
        self.btn_add_col.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.btn_add_col.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add_col.setStyleSheet("""
            QPushButton {
                background: #EDF5F2;
                color: #14372e;
                border: 1px solid #A6D4C3;
                border-radius: 5px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: #D8EDE5; }
        """)
        self.btn_add_col.clicked.connect(self._on_add_column_clicked)
        controls_layout.addWidget(self.btn_add_col)

        self.btn_del_col = QPushButton("🗑️ حذف حقل")
        self.btn_del_col.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.btn_del_col.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_del_col.setStyleSheet("""
            QPushButton {
                background: #FEF3F2;
                color: #B42318;
                border: 1px solid #FECDCA;
                border-radius: 5px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: #FEE4E2; }
        """)
        self.btn_del_col.clicked.connect(self._on_del_column_clicked)
        controls_layout.addWidget(self.btn_del_col)

        controls_layout.addStretch()
        main_layout.addWidget(controls_frame)

        self._update_sort_btn_styles()

        # 6. الجدول الرئيسي (ترتيب الحقول والمعلومات الأصلي 100%)
        self.table_widget = QTableWidget()
        self.table_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table_widget.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table_widget.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.table_widget.doubleClicked.connect(self._on_edit_clicked)
        self.table_widget.setStyleSheet("""
            QTableWidget {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 8px;
                gridline-color: #F2F4F7;
            }
            QHeaderView::section {
                background: #F8F9FA;
                color: #344054;
                font-weight: bold;
                padding: 6px 8px;
                border: 1px solid #E4E7EC;
                cursor: pointer;
            }
            QTableWidget::item:selected {
                background: #EDF5F2;
                color: #14372e;
            }
        """)
        main_layout.addWidget(self.table_widget, stretch=1)

        # 7. شريط الترقيم والتنقل
        pagination_row = QHBoxLayout()
        self.lbl_page_info = QLabel("الصفحة 1 من 1")
        self.lbl_page_info.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_page_info.setStyleSheet("color: #667085;")
        pagination_row.addWidget(self.lbl_page_info)

        pagination_row.addStretch()

        self.btn_prev = QPushButton("السابق")
        self.btn_prev.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.btn_prev.setStyleSheet("background: #FFFFFF; border: 1px solid #D0D5DD; padding: 4px 10px; border-radius: 5px;")
        self.btn_prev.clicked.connect(self._prev_page)
        pagination_row.addWidget(self.btn_prev)

        self.btn_next = QPushButton("التالي")
        self.btn_next.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.btn_next.setStyleSheet("background: #FFFFFF; border: 1px solid #D0D5DD; padding: 4px 10px; border-radius: 5px;")
        self.btn_next.clicked.connect(self._next_page)
        pagination_row.addWidget(self.btn_next)

        main_layout.addLayout(pagination_row)

    def _tab_btn_style(self):
        return """
            QPushButton {
                background: #F2F4F7;
                color: #344054;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 5px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #E4E7EC; }
            QPushButton:checked {
                background: #14372e;
                color: #FFFFFF;
                border: 1px solid #14372e;
                font-weight: bold;
            }
        """

    def _subtable_btn_style(self):
        return """
            QPushButton {
                background: transparent;
                color: #667085;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { color: #1B1F24; background: #F2F4F7; }
            QPushButton:checked {
                background: #c59b27;
                color: #FFFFFF;
                font-weight: bold;
            }
        """

    def _update_sort_btn_styles(self):
        active_style = "background: #14372e; color: #FFFFFF; border: 1px solid #14372e; border-radius: 5px; padding: 4px 10px;"
        inactive_style = "background: #FFFFFF; color: #344054; border: 1px solid #D0D5DD; border-radius: 5px; padding: 4px 10px;"

        self.btn_sort_desc.setStyleSheet(active_style if self.sort_dir == "desc" else inactive_style)
        self.btn_sort_asc.setStyleSheet(active_style if self.sort_dir == "asc" else inactive_style)
        self.btn_sort_none.setStyleSheet(active_style if self.sort_dir == "none" else inactive_style)

    def _set_sort_dir(self, direction):
        self.sort_dir = direction
        self._update_sort_btn_styles()
        self.current_page = 1
        self.load_data()

    def _on_date_col_changed(self):
        val = self.combo_date_col.currentData()
        if val:
            self.sort_col = val
            if self.sort_dir != "none":
                self.current_page = 1
                self.load_data()

    def _on_header_clicked(self, logical_index):
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

        self._update_sort_btn_styles()
        self.current_page = 1
        self.load_data()

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
        self.btn_refresh.setText("🔄 تحديث فوري")
        self.current_data = data

        # تحديث قائمة أعمدة التواريخ في الكومبوبوكس
        self.date_columns = data.get("date_columns", [])
        self.combo_date_col.blockSignals(True)
        self.combo_date_col.clear()
        self.combo_date_col.addItem("تلقائي (حقل التاريخ الذكي)", "date_auto")
        for dc in self.date_columns:
            self.combo_date_col.addItem(f"📅 {dc}", dc)

        # تحديد العنصر الحالي
        cur_col = data.get("sort_col", self.sort_col)
        for i in range(self.combo_date_col.count()):
            if self.combo_date_col.itemData(i) == cur_col:
                self.combo_date_col.setCurrentIndex(i)
                break
        self.combo_date_col.blockSignals(False)

        # تحديث أزرار الملفات ديناميكياً إذا لم تكن مضافة
        if self.file_btn_group.buttons() and len(self.file_btn_group.buttons()) <= 1:
            for f in data.get("files", []):
                fname = f["name"]
                btn = QPushButton(f"📁 {fname}")
                btn.setCheckable(True)
                btn.setFont(QFont("IBM Plex Sans Arabic", 9))
                btn.setStyleSheet(self._tab_btn_style())
                btn.clicked.connect(lambda checked, name=fname: self._on_file_tab_clicked(name))
                self.file_btn_group.addButton(btn)
                self.tabs_layout.addWidget(btn)

        # تحديث أزرار الجداول الفرعية
        while self.subtables_layout.count():
            item = self.subtables_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lbl = QLabel("الجداول:")
        lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #667085;")
        self.subtables_layout.addWidget(lbl)

        for tbl in data.get("available_tables", []):
            btn = QPushButton(tbl)
            btn.setCheckable(True)
            btn.setChecked(tbl == data.get("active_table"))
            btn.setStyleSheet(self._subtable_btn_style())
            btn.clicked.connect(lambda checked, t=tbl: self._on_subtable_clicked(t))
            self.subtable_btn_group.addButton(btn)
            self.subtables_layout.addWidget(btn)
        self.subtables_layout.addStretch()

        # تعبئة الجدول بالترتيب الأصلي الدقيق للحقول والمعلومات
        cols = data.get("columns", [])
        rows = data.get("rows", [])

        # إضافة عمود الملف في خانة الدمج الشامل
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
                self.table_widget.setItem(r_idx, 0, src_item)
                c_offset = 1

            for c_idx, col in enumerate(cols):
                val = row.get(col, "")
                val_str = "" if val is None else str(val)
                item = QTableWidgetItem(val_str)
                self.table_widget.setItem(r_idx, c_idx + c_offset, item)

        # تحديث معلومات الترقيم
        cur_p = data.get("page", 1)
        tot_p = data.get("total_pages", 1)
        matches = data.get("total_matches", 0)
        self.lbl_page_info.setText(f"الصفحة {cur_p} من {tot_p} (إجمالي {matches:,} قيد)")
        self.btn_prev.setEnabled(cur_p > 1)
        self.btn_next.setEnabled(cur_p < tot_p)

        # تحديث الإحصائية
        total_rec = data.get("total_records", 88987)
        self.stat_badge.setText(f"{total_rec:,} قيد مركزي")

    def _on_data_error(self, err):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 تحديث فوري")
        QMessageBox.warning(self, "تنبيه", f"تعذر استرجاع البيانات: {err}")

    def _on_file_tab_clicked(self, fname):
        self.active_file = fname
        self.current_page = 1
        self.load_data()

    def _on_subtable_clicked(self, tbl):
        self.active_table = tbl
        self.current_page = 1
        self.load_data()

    def _on_search_changed(self):
        self.current_page = 1
        self.load_data()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def _next_page(self):
        self.current_page += 1
        self.load_data()

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
        row_idx = self.table_widget.currentRow()
        if row_idx < 0 or not self.current_data or not self.current_data.get("rows"):
            QMessageBox.information(self, "تنبيه", "يرجى تحديد السجل المراد حذفه أولاً.")
            return

        row_data = self.current_data["rows"][row_idx]
        confirm = QMessageBox.question(
            self, "تأكيد الحذف",
            f"هل أنت متأكد من حذف هذا السجل نهائياً؟\nالملف: {row_data.get('_adh_file')}\nالجدول: {row_data.get('_adh_table')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                params = {
                    "file": row_data["_adh_file"],
                    "table": row_data["_adh_table"],
                    "id": row_data["_adh_id"]
                }
                r = requests.delete(CLOUD_API_URL, params=params, timeout=10)
                if r.status_code == 200:
                    QMessageBox.information(self, "نجاح", "تم حذف السجل بنجاح ومزامنته سحابياً.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل الحذف: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

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
