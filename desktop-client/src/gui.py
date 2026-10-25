"""
غرفة تجارة كربلاء المقدسة – منظومة التبادل السحابي وأرشفة المستندات
Karbala Chamber of Commerce – Official Cloud File Exchange System
الواجهة الحكومية الرسمية المعتمدة (Official Enterprise Edition)
"""
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QLineEdit, QSystemTrayIcon, QMenu, QMessageBox, QFileDialog, 
    QFrame, QButtonGroup, QDialog, QApplication,
    QStackedWidget, QScrollArea, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap, QCursor

from theme import (
    get_gov_stylesheet, apply_gov_shadow,
    GOV_GREEN, GOV_GOLD, TEXT_TITLE, TEXT_MUTED,
    STATUS_SYNCED, STATUS_SYNCED_BG, STATUS_SYNCED_BORDER,
    STATUS_SYNCING, STATUS_LOCKED, STATUS_LOCKED_BG, STATUS_LOCKED_BORDER
)
from icon_provider import get_file_office_icon, get_file_office_pixmap
from office_handler import OfficeHandler
from autostart import is_windows_autostart_enabled, set_windows_autostart

class StatusBridge(QObject):
    sync_updated = pyqtSignal(dict)


class GovFileCard(QFrame):
    """بطاقة المستند الرسمية لنمط شبكة البطاقات (Grid View)"""
    def __init__(self, file_data, main_window):
        super().__init__()
        self.file_data = file_data
        self.main_window = main_window
        self.file_name = file_data.get('file_name', '')
        self.setObjectName("govCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        apply_gov_shadow(self, blur=10, offset_y=2, alpha=12)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. الصف العلوي: أيقونة Office + الشارات الرسمية
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # أيقونة Office فائقة الوضوح
        icon_lbl = QLabel()
        pix = get_file_office_pixmap(self.file_name, size=46)
        icon_lbl.setPixmap(pix)
        top_row.addWidget(icon_lbl)

        # عمود الشارات
        badge_col = QVBoxLayout()
        badge_col.setSpacing(4)

        ext = Path(self.file_name).suffix.lower()
        if ext in ['.docx', '.doc']:
            app_text = "Word • مستند رسمي"
            badge_style = "background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe;"
        elif ext in ['.xlsx', '.xls', '.csv']:
            app_text = "Excel • جدول مالي"
            badge_style = "background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;"
        elif ext in ['.accdb', '.mdb']:
            app_text = "Access • قاعدة بيانات"
            badge_style = "background: #fef2f2; color: #991b1b; border: 1px solid #fecaca;"
        elif ext == '.pdf':
            app_text = "PDF • وثيقة رسمية"
            badge_style = "background: #fff1f2; color: #9f1239; border: 1px solid #fecdd3;"
        else:
            app_text = "مستند عام"
            badge_style = "background: #f8fafc; color: #334155; border: 1px solid #e2e8f0;"

        type_lbl = QLabel(app_text)
        type_lbl.setFont(QFont("Cairo", 9, QFont.Weight.Bold))
        type_lbl.setStyleSheet(f"{badge_style} border-radius: 4px; padding: 2px 6px;")
        badge_col.addWidget(type_lbl)

        status = self.file_data.get('sync_status', 'synced')
        status_map = {
            'synced': ('● محفوظ ومؤمّن', 'background: #eaf7f0; color: #0d8a55; border: 1px solid #a8dfc4;'),
            'syncing': ('● جارٍ الرفع...', 'background: #fffbeb; color: #b45309; border: 1px solid #fde68a;'),
            'pending_upload': ('● بانتظار الاتصال', 'background: #f8fafc; color: #64748b; border: 1px solid #cbd5e1;'),
            'conflict': ('● تم احتواء تعارض', 'background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa;'),
            'failed': ('● فشل التحقق', 'background: #fef2f2; color: #dc2626; border: 1px solid #fecaca;'),
            'locked': ('🔒 محجوزة للتعديل', 'background: #fdf2ef; color: #a33820; border: 1px solid #f8c9bd;')
        }
        status_text, status_style = status_map.get(status, ('● محفوظ', 'background: #eaf7f0; color: #0d8a55; border: 1px solid #a8dfc4;'))

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont("Cairo", 9, QFont.Weight.DemiBold))
        status_lbl.setStyleSheet(f"{status_style} border-radius: 4px; padding: 1px 6px;")
        badge_col.addWidget(status_lbl)

        top_row.addLayout(badge_col)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 2. اسم المستند بخط عريض وواضح
        name_lbl = QLabel(self.file_name)
        name_lbl.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #162420;")
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumHeight(48)
        layout.addWidget(name_lbl)

        # 3. الصف السفلي: الحجم والتاريخ وزر الفتح السريع
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        size_bytes = self.file_data.get('file_size', 0)
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1048576:
            size_str = f"{round(size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(size_bytes / 1048576, 2)} MB"

        date_raw = self.file_data.get('last_modified_local', '')
        date_str = date_raw[:10] if date_raw else "محفوظ"

        info_lbl = QLabel(f"💾 {size_str}  •  📅 {date_str}")
        info_lbl.setFont(QFont("Segoe UI", 10))
        info_lbl.setStyleSheet("color: #566c65;")
        meta_row.addWidget(info_lbl)

        meta_row.addStretch()

        btn_open = QPushButton("⚡ فتح")
        btn_open.setObjectName("btnCardOpen")
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(lambda: self.main_window._open_file_by_name(self.file_name))
        meta_row.addWidget(btn_open)

        layout.addLayout(meta_row)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.main_window._open_file_by_name(self.file_name)

    def contextMenuEvent(self, event):
        self.main_window._show_context_menu_for_file(self.file_name, event.globalPos())


class GovCompactTile(QFrame):
    """البلاطة الأفقية المدمجة لنمط القائمة المدمجة (Compact View)"""
    def __init__(self, file_data, main_window):
        super().__init__()
        self.file_data = file_data
        self.main_window = main_window
        self.file_name = file_data.get('file_name', '')
        self.setObjectName("govCompactTile")
        self.setFixedHeight(54)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # أيقونة البرنامج
        icon_lbl = QLabel()
        pix = get_file_office_pixmap(self.file_name, size=34)
        icon_lbl.setPixmap(pix)
        layout.addWidget(icon_lbl)

        # اسم المستند
        name_lbl = QLabel(self.file_name)
        name_lbl.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #162420;")
        layout.addWidget(name_lbl, stretch=2)

        # شارة البرنامج
        ext = Path(self.file_name).suffix.lower()
        if ext in ['.docx', '.doc']:
            app_text = "Word"
            badge_style = "background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe;"
        elif ext in ['.xlsx', '.xls', '.csv']:
            app_text = "Excel"
            badge_style = "background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;"
        elif ext in ['.accdb', '.mdb']:
            app_text = "Access"
            badge_style = "background: #fef2f2; color: #991b1b; border: 1px solid #fecaca;"
        elif ext == '.pdf':
            app_text = "PDF"
            badge_style = "background: #fff1f2; color: #9f1239; border: 1px solid #fecdd3;"
        else:
            app_text = "عام"
            badge_style = "background: #f8fafc; color: #334155; border: 1px solid #e2e8f0;"

        type_lbl = QLabel(app_text)
        type_lbl.setFont(QFont("Cairo", 9, QFont.Weight.Bold))
        type_lbl.setStyleSheet(f"{badge_style} border-radius: 4px; padding: 2px 8px;")
        layout.addWidget(type_lbl)

        # تاريخ التعديل
        date_raw = self.file_data.get('last_modified_local', '')
        date_str = date_raw[:19].replace('T', ' ') if date_raw else "محفوظ"
        date_lbl = QLabel(date_str)
        date_lbl.setFont(QFont("Segoe UI", 10))
        date_lbl.setStyleSheet("color: #566c65;")
        layout.addWidget(date_lbl)

        # الحجم
        size_bytes = self.file_data.get('file_size', 0)
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1048576:
            size_str = f"{round(size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(size_bytes / 1048576, 2)} MB"
        size_lbl = QLabel(size_str)
        size_lbl.setFont(QFont("Segoe UI", 10))
        size_lbl.setStyleSheet("color: #566c65;")
        layout.addWidget(size_lbl)

        # شارة الحالة
        status = self.file_data.get('sync_status', 'synced')
        status_map = {
            'synced': ('● محفوظ ومؤمّن', 'background: #eaf7f0; color: #0d8a55; border: 1px solid #a8dfc4;'),
            'syncing': ('● جارٍ الرفع...', 'background: #fffbeb; color: #b45309; border: 1px solid #fde68a;'),
            'pending_upload': ('● بانتظار الاتصال', 'background: #f8fafc; color: #64748b; border: 1px solid #cbd5e1;'),
            'conflict': ('● تم احتواء تعارض', 'background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa;'),
            'failed': ('● فشل التحقق', 'background: #fef2f2; color: #dc2626; border: 1px solid #fecaca;'),
            'locked': ('🔒 محجوزة للتعديل', 'background: #fdf2ef; color: #a33820; border: 1px solid #f8c9bd;')
        }
        status_text, status_style = status_map.get(status, ('● محفوظ', 'background: #eaf7f0; color: #0d8a55; border: 1px solid #a8dfc4;'))

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont("Cairo", 9, QFont.Weight.DemiBold))
        status_lbl.setStyleSheet(f"{status_style} border-radius: 4px; padding: 2px 8px;")
        layout.addWidget(status_lbl)

        # زر الفتح المباشر
        btn_open = QPushButton("⚡ فتح")
        btn_open.setObjectName("btnTileOpen")
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(lambda: self.main_window._open_file_by_name(self.file_name))
        layout.addWidget(btn_open)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.main_window._open_file_by_name(self.file_name)

    def contextMenuEvent(self, event):
        self.main_window._show_context_menu_for_file(self.file_name, event.globalPos())

class FileExchangeMainWindow(QMainWindow):
    """النافذة الرسمية لمنظومة تبادل وأرشفة مستندات غرفة تجارة كربلاء المقدسة"""
    def __init__(self, sync_engine, cloud_client, local_state_mgr, sync_folder):
        super().__init__()
        self.sync_engine = sync_engine
        self.client = cloud_client
        self.state_mgr = local_state_mgr
        self.sync_folder = Path(sync_folder)

        self.active_filter = "ALL"
        self.all_files_cache = []
        self.current_view_mode = self.state_mgr.get_setting("file_view_mode", "TABLE")

        # مسار شعار الغرفة الرسمي المتوافق مع ملف التثبيت المستقل
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).parent.parent
        self.logo_path = base_dir / "assets" / "logo.png"

        self.setWindowTitle("غرفة تجارة كربلاء المقدسة – منظومة التبادل السحابي للمستندات")
        self.resize(1140, 740)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # ضبط أيقونة النافذة الرسمية
        if self.logo_path.exists():
            self.setWindowIcon(QIcon(str(self.logo_path)))

        self.setStyleSheet(get_gov_stylesheet())

        self.bridge = StatusBridge()
        self.bridge.sync_updated.connect(self.handle_sync_update)
        if self.sync_engine:
            self.sync_engine.register_status_listener(lambda data: self.bridge.sync_updated.emit(data))

        self._setup_ui()
        self._setup_tray()
        self._refresh_file_list()

        # فحص دوري هادئ للتحديثات
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_file_list)
        self.timer.start(2500)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 18, 24, 16)
        main_layout.setSpacing(14)

        # ========================================================
        # 1. شريط الترويسة الرسمي مع شعار غرفة تجارة كربلاء المقدسة
        # ========================================================
        gov_header = QFrame()
        gov_header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #0e2720, stop:0.5 #163d33, stop:1 #1a443a);
                border: 1px solid #0a1f19;
                border-bottom: 3px solid #c59b27;
                border-radius: 12px;
                padding: 10px 18px;
            }
        """)
        apply_gov_shadow(gov_header, blur=18, offset_y=3, alpha=20)

        header_layout = QHBoxLayout(gov_header)
        header_layout.setContentsMargins(6, 4, 6, 4)

        # شعار الغرفة الرسمي
        logo_lbl = QLabel()
        if self.logo_path.exists():
            pix = QPixmap(str(self.logo_path))
            scaled_pix = pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(scaled_pix)
            logo_lbl.setStyleSheet("background: transparent; border: none;")
        else:
            logo_lbl.setText("🏛️")
            logo_lbl.setStyleSheet("font-size: 26px; background: transparent; border: none;")
        header_layout.addWidget(logo_lbl)

        # نصوص الهوية الرسمية
        brand_box = QVBoxLayout()
        brand_box.setSpacing(1)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        gov_title = QLabel("غرفة تجارة كربلاء المقدسة")
        gov_title.setFont(QFont("Cairo", 15, QFont.Weight.Bold))
        gov_title.setStyleSheet("color: #ffffff; font-weight: 800; background: transparent; border: none;")
        title_row.addWidget(gov_title)

        gold_badge = QLabel("• تأسست 1952 م")
        gold_badge.setFont(QFont("Cairo", 11, QFont.Weight.DemiBold))
        gold_badge.setStyleSheet("color: #ecd58a; background: transparent; border: none;")
        title_row.addWidget(gold_badge)
        title_row.addStretch()

        gov_sub = QLabel("منظومة التبادل السحابي وأرشفة المستندات الرسمية • الربط اللحظي لملفات Office 365")
        gov_sub.setFont(QFont("Segoe UI", 11))
        gov_sub.setStyleSheet("color: #bad3ca; background: transparent; border: none;")

        brand_box.addLayout(title_row)
        brand_box.addWidget(gov_sub)
        header_layout.addLayout(brand_box)

        header_layout.addStretch()

        # شارة حالة الربط السحابي
        self.cloud_badge = QLabel("● الربط السحابي مؤمّن ومفعّل")
        self.cloud_badge.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        self.cloud_badge.setStyleSheet("""
            background: rgba(13, 138, 85, 0.25);
            color: #86efac;
            padding: 6px 16px;
            border-radius: 20px;
            border: 1px solid rgba(34, 197, 94, 0.45);
        """)
        header_layout.addWidget(self.cloud_badge)

        main_layout.addWidget(gov_header)

        # ========================================================
        # 2. شريط الإجراءات النظيف والخالي من الحشو
        # ========================================================
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # زر فتح المجلد المشترك الرئيسي
        self.btn_open_folder = QPushButton("📁 استعراض المجلد المشترك")
        self.btn_open_folder.setObjectName("btnGovPrimary")
        self.btn_open_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_open_folder.clicked.connect(lambda: os.startfile(str(self.sync_folder)))
        toolbar.addWidget(self.btn_open_folder)

        # زر إضافة مستند جديد
        self.btn_upload = QPushButton("➕ إضافة مستند جديد")
        self.btn_upload.setObjectName("btnGovSecondary")
        self.btn_upload.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload.clicked.connect(self._upload_custom_file)
        toolbar.addWidget(self.btn_upload)

        # زر التحديث اليدوي
        self.btn_refresh = QPushButton("🔄 تحديث")
        self.btn_refresh.setObjectName("btnGovSecondary")
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.clicked.connect(self._refresh_file_list)
        toolbar.addWidget(self.btn_refresh)

        # حقل البحث الفوري
        self.search_box = QLineEdit()
        self.search_box.setObjectName("govSearch")
        self.search_box.setPlaceholderText("🔍 بحث فوري في مستندات الغرفة والكتب الرسمية...")
        self.search_box.textChanged.connect(self._filter_content)
        toolbar.addWidget(self.search_box, stretch=1)

        main_layout.addLayout(toolbar)

        # ========================================================
        # 3. تبويبات التصنيف الرسمية الهادئة
        # ========================================================
        tabs_layout = QHBoxLayout()
        tabs_layout.setSpacing(6)

        tab_group = QButtonGroup(self)
        tab_group.setExclusive(True)

        self.tab_all = self._create_gov_tab("كافة المستندات", "ALL", tab_group, checked=True)
        self.tab_word = self._create_gov_tab("الكتب والمراسلات (Word)", "WORD", tab_group)
        self.tab_excel = self._create_gov_tab("التقارير المالية (Excel)", "EXCEL", tab_group)
        self.tab_access = self._create_gov_tab("قواعد البيانات (Access)", "ACCESS", tab_group)
        self.tab_pdf = self._create_gov_tab("الوثائق والتعاميم (PDF)", "PDF", tab_group)

        tabs_layout.addWidget(self.tab_all)
        tabs_layout.addWidget(self.tab_word)
        tabs_layout.addWidget(self.tab_excel)
        tabs_layout.addWidget(self.tab_access)
        tabs_layout.addWidget(self.tab_pdf)
        tabs_layout.addStretch()

        # محدد طرق العرض (جدول تفصيلي / شبكة بطاقات / قائمة مدمجة)
        view_switch_frame = QFrame()
        view_switch_frame.setObjectName("viewSwitcherFrame")
        view_switch_layout = QHBoxLayout(view_switch_frame)
        view_switch_layout.setContentsMargins(4, 2, 4, 2)
        view_switch_layout.setSpacing(4)

        view_group = QButtonGroup(self)
        view_group.setExclusive(True)

        self.btn_view_table = QPushButton("☰ جدول تفصيلي")
        self.btn_view_table.setObjectName("btnViewMode")
        self.btn_view_table.setCheckable(True)
        self.btn_view_table.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_view_table.setToolTip("عرض المستندات في جدول تفصيلي حكومي شامل")
        view_group.addButton(self.btn_view_table)
        view_switch_layout.addWidget(self.btn_view_table)

        self.btn_view_grid = QPushButton("⊞ شبكة بطاقات")
        self.btn_view_grid.setObjectName("btnViewMode")
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_view_grid.setToolTip("عرض المستندات على شكل بطاقات أنيقة بأيقونات Office البارزة")
        view_group.addButton(self.btn_view_grid)
        view_switch_layout.addWidget(self.btn_view_grid)

        self.btn_view_compact = QPushButton("☷ قائمة مدمجة")
        self.btn_view_compact.setObjectName("btnViewMode")
        self.btn_view_compact.setCheckable(True)
        self.btn_view_compact.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_view_compact.setToolTip("عرض المستندات في قائمة صفوف مدمجة وسريعة الاستعراض")
        view_group.addButton(self.btn_view_compact)
        view_switch_layout.addWidget(self.btn_view_compact)

        self.btn_view_table.clicked.connect(lambda: self._set_view_mode("TABLE"))
        self.btn_view_grid.clicked.connect(lambda: self._set_view_mode("GRID"))
        self.btn_view_compact.clicked.connect(lambda: self._set_view_mode("COMPACT"))

        tabs_layout.addWidget(view_switch_frame)
        main_layout.addLayout(tabs_layout)

        # ========================================================
        # 4. مساحة عرض المستندات (متعددة الأنماط: جدول / بطاقات / مدمجة)
        # ========================================================
        self.stack = QStackedWidget()
        apply_gov_shadow(self.stack, blur=12, offset_y=2, alpha=10)

        # 4.1 نمط الجدول التفصيلي (TABLE)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "المستند الرسمي", "البرنامج المقترن", "تاريخ الاعتماد", "الحجم", "الحالة السحابية"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        self.table.cellDoubleClicked.connect(self._open_selected_from_table)
        self.stack.addWidget(self.table)

        # 4.2 نمط شبكة البطاقات (GRID)
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setObjectName("govScrollArea")
        self.grid_scroll.setWidgetResizable(True)
        self.grid_container = QWidget()
        self.grid_container.setObjectName("govScrollContent")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(12, 12, 12, 12)
        self.grid_layout.setSpacing(14)
        self.grid_scroll.setWidget(self.grid_container)
        self.stack.addWidget(self.grid_scroll)

        # 4.3 نمط القائمة المدمجة (COMPACT)
        self.compact_scroll = QScrollArea()
        self.compact_scroll.setObjectName("govScrollArea")
        self.compact_scroll.setWidgetResizable(True)
        self.compact_container = QWidget()
        self.compact_container.setObjectName("govScrollContent")
        self.compact_layout = QVBoxLayout(self.compact_container)
        self.compact_layout.setContentsMargins(12, 12, 12, 12)
        self.compact_layout.setSpacing(8)
        self.compact_scroll.setWidget(self.compact_container)
        self.stack.addWidget(self.compact_scroll)

        main_layout.addWidget(self.stack, stretch=1)

        # تطبيق نمط العرض المحفوظ للمستخدم
        self._set_view_mode(self.current_view_mode, persist=False)

        # ========================================================
        # 5. شريط الحالة السفلي الرصين
        # ========================================================
        statusbar = QFrame()
        statusbar.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border-top: 1.5px solid #d5dfdb;
                padding: 6px 14px;
                border-radius: 6px;
            }
        """)
        status_layout = QHBoxLayout(statusbar)
        status_layout.setContentsMargins(4, 2, 4, 2)

        self.lbl_total = QLabel("المستندات: 0 ملف")
        self.lbl_total.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
        self.lbl_total.setStyleSheet(f"color: {GOV_GREEN};")
        status_layout.addWidget(self.lbl_total)

        status_layout.addWidget(QLabel(" | "))

        self.lbl_watcher = QLabel("⚡ المزامنة الفورية: نشطة عند الحفظ (Ctrl+S)")
        self.lbl_watcher.setFont(QFont("Cairo", 10))
        self.lbl_watcher.setStyleSheet("color: #4b635b;")
        status_layout.addWidget(self.lbl_watcher)

        status_layout.addWidget(QLabel(" | "))

        self.lbl_cloud_info = QLabel("السعة السحابية: 1000 MB مجاناً")
        self.lbl_cloud_info.setFont(QFont("Cairo", 10))
        self.lbl_cloud_info.setStyleSheet("color: #4b635b;")
        status_layout.addWidget(self.lbl_cloud_info)

        status_layout.addStretch()

        self.lbl_dept = QLabel("نسخة غرفة تجارة كربلاء المقدسة المعتمدة v2.0")
        self.lbl_dept.setFont(QFont("Cairo", 10, QFont.Weight.DemiBold))
        self.lbl_dept.setStyleSheet("color: #5c726a;")
        status_layout.addWidget(self.lbl_dept)

        # زر إعدادات صامت للإدارة فقط
        btn_settings = QPushButton("⚙️")
        btn_settings.setObjectName("btnGovSettings")
        btn_settings.setToolTip("إعدادات الربط السحابي المتقدمة (للإدارة)")
        btn_settings.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_settings.clicked.connect(self._open_cloud_settings)
        status_layout.addWidget(btn_settings)

        main_layout.addWidget(statusbar)

    def _create_gov_tab(self, label, tag, group, checked=False):
        btn = QPushButton(label)
        btn.setObjectName("govTab")
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        group.addButton(btn)
        btn.clicked.connect(lambda: self._set_active_filter(tag))
        return btn

    def _set_active_filter(self, tag):
        self.active_filter = tag
        self._filter_content()

    def _set_view_mode(self, mode, persist=True):
        self.current_view_mode = mode
        if persist:
            try:
                self.state_mgr.set_setting("file_view_mode", mode)
            except Exception as e:
                print(f"[Save view mode error]: {e}")

        if mode == "GRID":
            self.btn_view_grid.setChecked(True)
            self.stack.setCurrentIndex(1)
        elif mode == "COMPACT":
            self.btn_view_compact.setChecked(True)
            self.stack.setCurrentIndex(2)
        else:
            self.btn_view_table.setChecked(True)
            self.stack.setCurrentIndex(0)

        # تحديث العرض بالملفات المفلترة
        self._filter_content()

    def _filter_content(self):
        query = self.search_box.text().strip().lower()
        filtered = []
        for f in self.all_files_cache:
            name = f['file_name'].lower()
            ext = Path(f['file_name']).suffix.lower()

            if self.active_filter == "WORD" and ext not in ['.docx', '.doc']:
                continue
            elif self.active_filter == "EXCEL" and ext not in ['.xlsx', '.xls', '.csv']:
                continue
            elif self.active_filter == "ACCESS" and ext not in ['.accdb', '.mdb']:
                continue
            elif self.active_filter == "PDF" and ext != '.pdf':
                continue

            if query and query not in name:
                continue

            filtered.append(f)

        if self.current_view_mode == "GRID":
            self._render_grid(filtered)
        elif self.current_view_mode == "COMPACT":
            self._render_compact(filtered)
        else:
            self._render_table(filtered)

    def _refresh_file_list(self):
        try:
            files = self.state_mgr.get_all_files()
            self.all_files_cache = files
            self.lbl_total.setText(f"المستندات: {len(files)} ملف")
            self._filter_content()
        except Exception as e:
            print(f"[Refresh Error]: {e}")

    def _render_grid(self, files):
        # تفريغ عناصر الشبكة السابقة بأمان
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not files:
            empty_lbl = QLabel("📂 لا توجد مستندات تطابق هذا التصنيف أو معايير البحث.")
            empty_lbl.setFont(QFont("Cairo", 12, QFont.Weight.DemiBold))
            empty_lbl.setStyleSheet("color: #64748b; padding: 50px; background: transparent;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(empty_lbl, 0, 0, 1, 3)
            return

        cols = 3
        for idx, f in enumerate(files):
            card = GovFileCard(f, self)
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(card, row, col)

        self.grid_layout.setRowStretch((len(files) - 1) // cols + 1, 1)

    def _render_compact(self, files):
        # تفريغ عناصر القائمة السابقة بأمان
        while self.compact_layout.count():
            item = self.compact_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not files:
            empty_lbl = QLabel("📂 لا توجد مستندات تطابق هذا التصنيف أو معايير البحث.")
            empty_lbl.setFont(QFont("Cairo", 12, QFont.Weight.DemiBold))
            empty_lbl.setStyleSheet("color: #64748b; padding: 50px; background: transparent;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.compact_layout.addWidget(empty_lbl)
            return

        for f in files:
            tile = GovCompactTile(f, self)
            self.compact_layout.addWidget(tile)

        self.compact_layout.addStretch()

    def _render_table(self, files):
        self.table.setRowCount(0)
        for f in files:
            name = f['file_name']
            row = self.table.rowCount()
            self.table.insertRow(row)

            office_icon = get_file_office_icon(name, size=38)
            ext = Path(name).suffix.lower()
            if ext in ['.docx', '.doc']:
                app_name = "Microsoft Word"
                type_tag = "مستند رسمي"
            elif ext in ['.xlsx', '.xls', '.csv']:
                app_name = "Microsoft Excel"
                type_tag = "جدول بيانات مالي"
            elif ext in ['.accdb', '.mdb']:
                app_name = "Microsoft Access"
                type_tag = "قاعدة بيانات الغرفة"
            elif ext == '.pdf':
                app_name = "Adobe Acrobat"
                type_tag = "وثيقة رسمية (PDF)"
            else:
                app_name = "ملف عام"
                type_tag = "مستند"

            size_bytes = f.get('file_size', 0)
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1048576:
                size_str = f"{round(size_bytes / 1024, 1)} KB"
            else:
                size_str = f"{round(size_bytes / 1048576, 2)} MB"

            date_raw = f.get('last_modified_local', '')
            if date_raw:
                date_str = date_raw[:19].replace('T', ' ')
            else:
                date_str = "محفوظ"

            status_map = {
                'synced': '● محفوظ ومؤمّن',
                'syncing': '● جارٍ الرفع...',
                'pending_upload': '● بانتظار الاتصال',
                'conflict': '● تم احتواء تعارض',
                'failed': '● فشل التحقق',
                'locked': '🔒 محجوزة للتعديل'
            }
            status_text = status_map.get(f.get('sync_status', 'synced'), '● محفوظ')

            # الخلية 0: المستند الرسمي
            name_item = QTableWidgetItem(f"{name}\n({type_tag})")
            name_item.setIcon(office_icon)
            name_item.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
            self.table.setItem(row, 0, name_item)

            # الخلية 1: البرنامج المقترن
            app_item = QTableWidgetItem(app_name)
            app_item.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            app_item.setForeground(QColor("#2d3d38"))
            self.table.setItem(row, 1, app_item)

            # الخلية 2: تاريخ الاعتماد
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 10))
            date_item.setForeground(QColor(TEXT_MUTED))
            self.table.setItem(row, 2, date_item)

            # الخلية 3: الحجم
            size_item = QTableWidgetItem(size_str)
            size_item.setFont(QFont("Segoe UI", 10))
            size_item.setForeground(QColor(TEXT_MUTED))
            self.table.setItem(row, 3, size_item)

            # الخلية 4: الحالة السحابية
            status_item = QTableWidgetItem(status_text)
            status_item.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
            if f.get('sync_status') == 'synced':
                status_item.setForeground(QColor(STATUS_SYNCED))
            elif f.get('sync_status') == 'locked':
                status_item.setForeground(QColor(STATUS_LOCKED))
            elif f.get('sync_status') == 'failed':
                status_item.setForeground(QColor("#ef4444"))
            else:
                status_item.setForeground(QColor(STATUS_SYNCING))
            self.table.setItem(row, 4, status_item)

    def _open_selected_from_table(self, row, col):
        raw_text = self.table.item(row, 0).text()
        file_name = raw_text.split('\n')[0]
        self._open_file_by_name(file_name)

    def _open_file_by_name(self, file_name):
        file_path = (self.sync_folder / file_name).resolve()
        if not file_path.exists():
            QMessageBox.warning(
                self, "تنبيه", 
                f"الملف التالي غير موجود فعلياً في مجلد المشاركة:\n{file_path}"
            )
            return

        # فحص قفل قواعد بيانات Access
        if OfficeHandler.is_access_db(str(file_path)):
            if self.client and self.client.is_configured():
                try:
                    is_locked, lock_info = self.client.check_file_lock(file_name)
                    if is_locked and lock_info:
                        user_locked = lock_info.get('locked_by_name', 'مستخدم آخر')
                        dev_locked = lock_info.get('device_name', 'جهاز آخر')
                        QMessageBox.critical(
                            self, "قاعدة البيانات محجوزة!",
                            f"قاعدة بيانات Access ({file_name}) مفتوحة حالياً بواسطة:\n"
                            f"👤 المستخدم: {user_locked}\n"
                            f"💻 الجهاز: {dev_locked}\n\n"
                            f"⛔ تم منع فتحها تجنباً لتلف بيانات الغرفة.\n"
                            f"يرجى الانتظار حتى ينتهي المستخدم الآخر ويغلقها."
                        )
                        return
                except Exception as e:
                    print(f"[Check lock skip]: {e}")

        try:
            OfficeHandler.open_native_file(str(file_path))
        except Exception as e:
            QMessageBox.critical(
                self, "خطأ في فتح الملف", 
                f"تعذر تشغيل البرنامج المقترن بالملف:\n{str(e)}"
            )

    def _show_table_context_menu(self, pos):
        selected = self.table.selectedItems()
        if not selected:
            return
        raw_text = self.table.item(selected[0].row(), 0).text()
        file_name = raw_text.split('\n')[0]
        self._show_context_menu_for_file(file_name, self.table.viewport().mapToGlobal(pos))

    def _show_context_menu_for_file(self, file_name, global_pos):
        file_path = (self.sync_folder / file_name).resolve()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #162420;
                border: 1.5px solid #d5dfdb;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
            }
            QMenu::item:selected {
                background-color: #f0f6f4;
                color: #14372e;
                font-weight: bold;
            }
        """)
        open_action = menu.addAction("⚡ فتح المستند بالبرنامج الأصلي")
        open_folder_action = menu.addAction("📂 استعراض في مجلد Windows")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ حذف المستند نهائياً")

        action = menu.exec(global_pos)
        if action == open_action:
            self._open_file_by_name(file_name)
        elif action == open_folder_action:
            if file_path.exists():
                subprocess.Popen(f'explorer /select,"{str(file_path)}"')
        elif action == delete_action:
            self._delete_file_by_name(file_name)

    def _delete_file_by_name(self, file_name):
        reply = QMessageBox.question(
            self, "تأكيد الحذف الرسمي", 
            f"هل أنت متأكد من حذف المستند التالي نهائياً؟\n{file_name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            file_path = self.sync_folder / file_name
            if file_path.exists():
                file_path.unlink()
            self._refresh_file_list()

    def _upload_custom_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر مستنداً لإضافته إلى مجلد المشاركة الرسمي", "",
            "ملفات Office والوثائق (*.docx *.xlsx *.accdb *.pdf *.doc *.xls);;كافة الملفات (*.*)"
        )
        if path:
            dest = self.sync_folder / Path(path).name
            import shutil
            shutil.copy2(path, dest)
            self._refresh_file_list()
            QMessageBox.information(
                self, "تمت الإضافة", 
                f"تمت إضافة '{Path(path).name}' بنجاح وسيتم حفظه ومزامنته سحابياً فورياً."
            )

    def _open_cloud_settings(self):
        """نافذة إعدادات الربط السحابي (للإدارة فقط)"""
        dialog = QDialog(self)
        dialog.setWindowTitle("إعدادات الربط السحابي (الإدارة)")
        dialog.resize(480, 360)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma; }
            QLabel { font-size: 12px; color: #0f172a; font-weight: 600; }
            QLineEdit {
                background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px;
                padding: 8px 12px; font-size: 12px; color: #0f172a;
            }
            QPushButton {
                background-color: #14372e; color: white; border-radius: 8px;
                padding: 10px; font-weight: bold; font-size: 12px; border: none;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        layout.addWidget(QLabel("إعدادات الربط السحابي لغرفة تجارة كربلاء المقدسة"))

        cur_url = self.state_mgr.get_setting("supabase_url", "https://bjcillpivgcntzbwmpsm.supabase.co")
        cur_key = self.state_mgr.get_setting("supabase_key", "sb_publishable_Bfk1klLDNsLWKHvdRhWqNg_XoDqqJ6X")

        layout.addWidget(QLabel("رابط الخادم السحابي:"))
        txt_url = QLineEdit(cur_url)
        layout.addWidget(txt_url)

        layout.addWidget(QLabel("مفتاح المشروع العام (Publishable Key):"))
        txt_key = QLineEdit(cur_key)
        layout.addWidget(txt_key)

        btn_save = QPushButton("حفظ الإعدادات")
        def save():
            self.state_mgr.set_setting("supabase_url", txt_url.text().strip())
            self.state_mgr.set_setting("supabase_key", txt_key.text().strip())
            QMessageBox.information(dialog, "تم الحفظ", "تم حفظ الإعدادات السحابية بنجاح.")
            dialog.accept()

        btn_save.clicked.connect(save)
        layout.addWidget(btn_save)
        dialog.exec()

    def handle_sync_update(self, data):
        self._refresh_file_list()

    def _setup_tray(self):
        """أيقونة شريط المهام بجانب الساعة في ويندوز"""
        self.tray = QSystemTrayIcon(self)
        if self.logo_path.exists():
            self.tray.setIcon(QIcon(str(self.logo_path)))
        else:
            self.tray.setIcon(self.windowIcon())

        menu = QMenu()
        open_action = menu.addAction("عرض النافذة الرئيسية")
        open_action.triggered.connect(self.showNormal)

        open_folder_action = menu.addAction("فتح المجلد المشترك")
        open_folder_action.triggered.connect(lambda: os.startfile(str(self.sync_folder)))

        menu.addSeparator()
        quit_action = menu.addAction("إغلاق البرنامج")
        quit_action.triggered.connect(QApplication.instance().quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def closeEvent(self, event):
        """تصغير إلى شريط المهام بدلاً من الإغلاق الكامل"""
        if self.tray.isVisible():
            self.hide()
            self.tray.showMessage(
                "غرفة تجارة كربلاء المقدسة",
                "المنظومة تعمل في الخلفية وتراقب التعديلات عند الضغط على Ctrl+S.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            event.ignore()
        else:
            event.accept()
