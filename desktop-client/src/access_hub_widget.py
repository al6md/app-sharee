# -*- coding: utf-8 -*-
"""
غرفة تجارة كربلاء المقدسة – منظومة Share COC
مركز قواعد بيانات Access الموحد (Access Data Hub Desktop Widget)
يدعم الدمج الشامل، الخانات الحقيقية، الترتيب الأصلي الدقيق 100% للحقول، والـ CRUD الكامل مع المزامنة السحابية.
"""

import os
import sys
import json
import requests
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QButtonGroup, QFrame, QDialog, QMessageBox, QFileDialog,
    QScrollArea, QAbstractItemView, QProgressDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QCursor, QIcon

CLOUD_API_URL = "https://web-dashboard-pi-self.vercel.app/api/access-hub"
LOCAL_API_URL = "http://localhost:3000/api/access-hub"

# مسار مجلد البيانات المحلي كنسخة احتياطية سريعة
LOCAL_DATA_DIR = Path(__file__).parent.parent.parent / "web-dashboard" / "data" / "access-hub"

class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_name, table_name, search_query="", page=1, limit=100):
        super().__init__()
        self.file_name = file_name
        self.table_name = table_name
        self.search_query = search_query
        self.page = page
        self.limit = limit

    def run(self):
        # محاولة الاتصال بالخادم المحلي أو السحابي أولاً
        params = {
            "file": self.file_name,
            "table": self.table_name,
            "search": self.search_query,
            "page": self.page,
            "limit": self.limit
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
            r = requests.get(CLOUD_API_URL, params=params, timeout=10)
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

        rows = []
        columns = []
        available_tables = []

        if req_file == "all":
            tables_set = set()
            for f in idx.get("files", []):
                for t in f.get("tables", []):
                    tables_set.add(t)
            available_tables = list(tables_set)
            if not req_table or req_table not in tables_set:
                req_table = available_tables[0] if available_tables else "التجار"

            cols_order = []
            cols_seen = set()

            for f in idx.get("files", []):
                fpath = LOCAL_DATA_DIR / f"{f['name']}.json"
                if not fpath.exists(): continue
                with open(fpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                
                orig_cols = data.get("columns", {}).get(req_table, [])
                for c in orig_cols:
                    if c not in cols_seen:
                        cols_seen.add(c)
                        cols_order.push(c) if hasattr(cols_order, 'push') else cols_order.append(c)

                for r in data.get("tables", {}).get(req_table, []):
                    if search:
                        match = any(v and search in str(v).lower() for v in r.values())
                        if not match: continue
                    rows.append(r)
            columns = cols_order
        else:
            fpath = LOCAL_DATA_DIR / f"{req_file}.json"
            if not fpath.exists(): return None
            with open(fpath, "r", encoding="utf-8") as jf:
                data = json.load(jf)

            available_tables = list(data.get("tables", {}).keys())
            if not req_table or req_table not in data.get("tables", {}):
                req_table = available_tables[0] if available_tables else ""

            columns = data.get("columns", {}).get(req_table, [])
            for r in data.get("tables", {}).get(req_table, []):
                if search:
                    match = any(v and search in str(v).lower() for v in r.values())
                    if not match: continue
                rows.append(r)

        total_matches = len(rows)
        start_idx = (self.page - 1) * self.limit
        page_rows = rows[start_idx:start_idx + self.limit]

        return {
            "success": True,
            "files": idx.get("files", []),
            "total_records": idx.get("total_records", 0),
            "active_file": req_file,
            "active_table": req_table,
            "available_tables": available_tables,
            "columns": columns,
            "total_matches": total_matches,
            "page": self.page,
            "limit": self.limit,
            "total_pages": max(1, (total_matches + self.limit - 1) // self.limit),
            "rows": page_rows
        }


class RecordFormDialog(QDialog):
    """نافذة لإضافة أو تعديل قيد بالحفاظ الكامل على ترتيب الحقول الأصلية 100%"""
    def __init__(self, title, columns, initial_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(550, 600)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.columns = columns
        self.inputs = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel(title)
        header.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #14372e; padding-bottom: 6px; border-bottom: 2px solid #c59b27;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(8)

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
        btn_save = QPushButton("حفظ ومزامنة سحابية")
        btn_save.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_save.setStyleSheet("""
            background: #14372e;
            color: #FFFFFF;
            border-radius: 6px;
            padding: 8px 16px;
        """)
        btn_save.clicked.connect(self.accept)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFont(QFont("IBM Plex Sans Arabic", 9))
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


class AccessHubWidget(QWidget):
    """القسم المستقل لمركز بيانات Access الموحد داخل تطبيق الحاسوب"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.active_file = "all"
        self.active_table = "التجار"
        self.current_page = 1
        self.limit = 50
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

        subtitle = QLabel("دمج سحابي فوري لكافة السجلات مع الحفاظ التام 100% على ترتيب الحقول والمعلومات الأصلية")
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

        # 4. شريط البحث والعمليات
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

        self.btn_add = QPushButton("➕ إضافة قيد")
        self.btn_add.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add.setStyleSheet("background: #14372e; color: #FFFFFF; border-radius: 6px; padding: 6px 12px;")
        self.btn_add.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏️ تعديل")
        self.btn_edit.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_edit.setStyleSheet("background: #F7F8FA; color: #14372e; border: 1px solid #D0D5DD; border-radius: 6px; padding: 6px 12px;")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        toolbar.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑️ حذف")
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

        # 5. الجدول الرئيسي (ترتيب الحقول والمعلومات الأصلي 100%)
        self.table_widget = QTableWidget()
        self.table_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
            }
            QTableWidget::item:selected {
                background: #EDF5F2;
                color: #14372e;
            }
        """)
        main_layout.addWidget(self.table_widget, stretch=1)

        # 6. شريط الترقيم والتنقل
        pagination_row = QHBoxLayout()
        self.lbl_page_info = QLabel("الصفحة 1 من 1")
        self.lbl_page_info.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_page_info.setStyleSheet("color: #667085;")
        pagination_row.addWidget(self.lbl_page_info)

        pagination_row.addStretch()

        self.btn_prev = QPushButton("السابق")
        self.btn_prev.setFont(QFont("IBM Plex Sans Arabic", 8.5))
        self.btn_prev.setStyleSheet("background: #FFFFFF; border: 1px solid #D0D5DD; padding: 4px 10px; border-radius: 5px;")
        self.btn_prev.clicked.connect(self._prev_page)
        pagination_row.addWidget(self.btn_prev)

        self.btn_next = QPushButton("التالي")
        self.btn_next.setFont(QFont("IBM Plex Sans Arabic", 8.5))
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

    def load_data(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("جاري التحميل...")

        query = self.search_input.text().strip()
        self.loader_thread = DataLoaderThread(self.active_file, self.active_table, query, self.current_page, self.limit)
        self.loader_thread.data_loaded.connect(self._on_data_loaded)
        self.loader_thread.error_occurred.connect(self._on_data_error)
        self.loader_thread.start()

    def _on_data_loaded(self, data):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 تحديث فوري")
        self.current_data = data

        # تحديث أزرار الملفات ديناميكياً إذا لم تكن مضافة
        if self.file_btn_group.buttons() and len(self.file_btn_group.buttons()) <= 1:
            for f in data.get("files", []):
                fname = f["name"]
                btn = QPushButton(f"📁 {fname}")
                btn.setCheckable(True)
                btn.setFont(QFont("IBM Plex Sans Arabic", 8.5))
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
        lbl.setFont(QFont("IBM Plex Sans Arabic", 8.5, QFont.Weight.Bold))
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
        display_cols = (["الملف المصدر"] + cols) if self.active_file == "all" else cols

        self.table_widget.setColumnCount(len(display_cols))
        self.table_widget.setHorizontalHeaderLabels(display_cols)
        self.table_widget.setRowCount(len(rows))

        for r_idx, row in enumerate(rows):
            c_offset = 0
            if self.active_file == "all":
                src_item = QTableWidgetItem(str(row.get("_adh_file", "")))
                src_item.setForeground(QColor("#14372e"))
                src_item.setFont(QFont("IBM Plex Sans Arabic", 8.5, QFont.Weight.Bold))
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

    def _on_add_clicked(self):
        if not self.current_data or not self.current_data.get("columns"):
            return
        cols = self.current_data["columns"]
        dlg = RecordFormDialog(f"إضافة قيد جديد في جدول ({self.active_table})", cols, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            try:
                target_file = self.active_file if self.active_file != "all" else self.current_data["files"][0]["name"]
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
