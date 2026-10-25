"""
غرفة تجارة كربلاء المقدسة – منظومة التبادل السحابي وأرشفة المستندات
Karbala Chamber of Commerce – Official Cloud File Exchange System
الواجهة الحكومية الرسمية المعتمدة (Official Enterprise Edition)
"""
import os
import sys
import time
import shutil
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
    """بطاقة المستند أو المجلد لنمط شبكة البطاقات (Grid View)"""
    def __init__(self, file_data, main_window):
        super().__init__()
        self.file_data = file_data
        self.main_window = main_window
        self.file_name = file_data.get('file_name', '')
        self.is_folder = file_data.get('is_folder', False)
        self.setObjectName("govCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        apply_gov_shadow(self, blur=10, offset_y=2, alpha=12)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. الصف العلوي: الأيقونة + الشارات الرسمية
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        icon_lbl = QLabel()
        pix = get_file_office_pixmap(self.file_name, size=46, is_folder=self.is_folder)
        icon_lbl.setPixmap(pix)
        top_row.addWidget(icon_lbl)

        badge_col = QVBoxLayout()
        badge_col.setSpacing(4)

        if self.is_folder:
            app_text = "📁 مجلد مستندات"
            badge_style = "background: #fefce8; color: #854d0e; border: 1px solid #fef08a;"
            status_text = f"📁 {self.file_data.get('item_count', 0)} عنصر داخل المجلد"
            status_style = "background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;"
        else:
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

        type_lbl = QLabel(app_text)
        type_lbl.setFont(QFont("Cairo", 9, QFont.Weight.Bold))
        type_lbl.setStyleSheet(f"{badge_style} border-radius: 4px; padding: 2px 6px;")
        badge_col.addWidget(type_lbl)

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont("Cairo", 9, QFont.Weight.DemiBold))
        status_lbl.setStyleSheet(f"{status_style} border-radius: 4px; padding: 1px 6px;")
        badge_col.addWidget(status_lbl)

        top_row.addLayout(badge_col)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 2. اسم المجلد أو المستند
        name_lbl = QLabel(self.file_name)
        name_lbl.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #162420;")
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumHeight(48)
        layout.addWidget(name_lbl)

        # 3. الصف السفلي
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        if self.is_folder:
            info_lbl = QLabel(f"📂 مجلد إداري منظم")
            action_btn_text = "📂 استعراض"
        else:
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
            action_btn_text = "⚡ فتح"

        info_lbl.setFont(QFont("Segoe UI", 10))
        info_lbl.setStyleSheet("color: #566c65;")
        meta_row.addWidget(info_lbl)
        meta_row.addStretch()

        btn_action = QPushButton(action_btn_text)
        btn_action.setObjectName("btnCardOpen")
        btn_action.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.is_folder:
            btn_action.clicked.connect(lambda: self.main_window._navigate_into_folder(self.file_name))
        else:
            btn_action.clicked.connect(lambda: self.main_window._open_file_by_name(self.file_name))
        meta_row.addWidget(btn_action)

        layout.addLayout(meta_row)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_folder:
                self.main_window._navigate_into_folder(self.file_name)
            else:
                self.main_window._open_file_by_name(self.file_name)

    def contextMenuEvent(self, event):
        if self.is_folder:
            self.main_window._show_context_menu_for_folder(self.file_name, event.globalPos())
        else:
            self.main_window._show_context_menu_for_file(self.file_name, event.globalPos())


class GovCompactTile(QFrame):
    """البلاطة الأفقية المدمجة لنمط القائمة المدمجة (Compact View)"""
    def __init__(self, file_data, main_window):
        super().__init__()
        self.file_data = file_data
        self.main_window = main_window
        self.file_name = file_data.get('file_name', '')
        self.is_folder = file_data.get('is_folder', False)
        self.setObjectName("govCompactTile")
        self.setFixedHeight(54)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        pix = get_file_office_pixmap(self.file_name, size=34, is_folder=self.is_folder)
        icon_lbl.setPixmap(pix)
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(self.file_name)
        name_lbl.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #162420;")
        layout.addWidget(name_lbl, stretch=2)

        if self.is_folder:
            type_lbl = QLabel("مجلد")
            type_lbl.setFont(QFont("Cairo", 9, QFont.Weight.Bold))
            type_lbl.setStyleSheet("background: #fefce8; color: #854d0e; border: 1px solid #fef08a; border-radius: 4px; padding: 2px 8px;")
            layout.addWidget(type_lbl)

            info_lbl = QLabel(f"{self.file_data.get('item_count', 0)} عناصر")
            info_lbl.setFont(QFont("Segoe UI", 10))
            info_lbl.setStyleSheet("color: #566c65;")
            layout.addWidget(info_lbl)

            status_lbl = QLabel("📁 مجلد منظم")
            status_lbl.setFont(QFont("Cairo", 9, QFont.Weight.DemiBold))
            status_lbl.setStyleSheet("background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; border-radius: 4px; padding: 2px 8px;")
            layout.addWidget(status_lbl)

            btn_action = QPushButton("📂 استعراض")
            btn_action.setObjectName("btnTileOpen")
            btn_action.clicked.connect(lambda: self.main_window._navigate_into_folder(self.file_name))
            layout.addWidget(btn_action)
        else:
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

            date_raw = self.file_data.get('last_modified_local', '')
            date_str = date_raw[:19].replace('T', ' ') if date_raw else "محفوظ"
            date_lbl = QLabel(date_str)
            date_lbl.setFont(QFont("Segoe UI", 10))
            date_lbl.setStyleSheet("color: #566c65;")
            layout.addWidget(date_lbl)

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

            btn_action = QPushButton("⚡ فتح")
            btn_action.setObjectName("btnTileOpen")
            btn_action.clicked.connect(lambda: self.main_window._open_file_by_name(self.file_name))
            layout.addWidget(btn_action)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_folder:
                self.main_window._navigate_into_folder(self.file_name)
            else:
                self.main_window._open_file_by_name(self.file_name)

    def contextMenuEvent(self, event):
        if self.is_folder:
            self.main_window._show_context_menu_for_folder(self.file_name, event.globalPos())
        else:
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
        self.current_subpath = Path(".")
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
        self.btn_open_folder = QPushButton("📁 استعراض المجلد")
        self.btn_open_folder.setObjectName("btnGovPrimary")
        self.btn_open_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_open_folder.clicked.connect(lambda: os.startfile(str(self._get_current_abs_folder())))
        toolbar.addWidget(self.btn_open_folder)

        # زر إضافة مستند جديد
        self.btn_upload = QPushButton("➕ إضافة مستند")
        self.btn_upload.setObjectName("btnGovSecondary")
        self.btn_upload.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload.clicked.connect(self._upload_custom_file)
        toolbar.addWidget(self.btn_upload)

        # زر إنشاء مجلد جديد (قسم إنشاء مجلدات)
        self.btn_new_folder = QPushButton("📂 مجلد جديد")
        self.btn_new_folder.setObjectName("btnGovSecondary")
        self.btn_new_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_new_folder.setToolTip("إنشاء مجلد إداري جديد لتنظيم المستندات")
        self.btn_new_folder.clicked.connect(self._show_new_folder_dialog)
        toolbar.addWidget(self.btn_new_folder)

        # زر سلة المحذوفات (قسم حذف الملفات)
        self.btn_trash_toolbar = QPushButton("🗑️ سلة المحذوفات")
        self.btn_trash_toolbar.setObjectName("btnGovSecondary")
        self.btn_trash_toolbar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_trash_toolbar.setToolTip("الانتقال إلى قسم سلة المحذوفات واستعادة أو حذف الملفات")
        self.btn_trash_toolbar.clicked.connect(lambda: self._set_active_filter("TRASH"))
        toolbar.addWidget(self.btn_trash_toolbar)

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
        # 2.5 شريط المسار والتنقل بين المجلدات (Breadcrumb Bar)
        # ========================================================
        self.breadcrumb_frame = QFrame()
        self.breadcrumb_frame.setObjectName("breadcrumbFrame")
        bc_layout = QHBoxLayout(self.breadcrumb_frame)
        bc_layout.setContentsMargins(10, 5, 10, 5)
        bc_layout.setSpacing(10)

        self.btn_nav_up = QPushButton("⬆ رجوع للمجلد السابق")
        self.btn_nav_up.setObjectName("btnBreadcrumbUp")
        self.btn_nav_up.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_nav_up.setEnabled(False)
        self.btn_nav_up.clicked.connect(self._navigate_up)
        bc_layout.addWidget(self.btn_nav_up)

        self.lbl_current_path = QLabel("📂 المجلد الرئيسي: غرفة تجارة كربلاء المقدسة")
        self.lbl_current_path.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
        self.lbl_current_path.setStyleSheet(f"color: {GOV_GREEN};")
        bc_layout.addWidget(self.lbl_current_path)

        bc_layout.addStretch()

        self.lbl_folder_info = QLabel("المجلد نشط ومتزامن")
        self.lbl_folder_info.setFont(QFont("Cairo", 9))
        self.lbl_folder_info.setStyleSheet("color: #566c65;")
        bc_layout.addWidget(self.lbl_folder_info)

        main_layout.addWidget(self.breadcrumb_frame)

        # ========================================================
        # 3. تبويبات التصنيف الرسمية الهادئة
        # ========================================================
        tabs_layout = QHBoxLayout()
        tabs_layout.setSpacing(6)

        tab_group = QButtonGroup(self)
        tab_group.setExclusive(True)

        self.tab_all = self._create_gov_tab("كافة المستندات", "ALL", tab_group, checked=True)
        self.tab_folders = self._create_gov_tab("المجلدات والأقسام 📁", "FOLDERS", tab_group)
        self.tab_word = self._create_gov_tab("الكتب والمراسلات (Word)", "WORD", tab_group)
        self.tab_excel = self._create_gov_tab("التقارير المالية (Excel)", "EXCEL", tab_group)
        self.tab_access = self._create_gov_tab("قواعد البيانات (Access)", "ACCESS", tab_group)
        self.tab_pdf = self._create_gov_tab("الوثائق والتعاميم (PDF)", "PDF", tab_group)
        self.tab_trash = self._create_gov_tab("🗑️ سلة المحذوفات", "TRASH", tab_group)

        tabs_layout.addWidget(self.tab_all)
        tabs_layout.addWidget(self.tab_folders)
        tabs_layout.addWidget(self.tab_word)
        tabs_layout.addWidget(self.tab_excel)
        tabs_layout.addWidget(self.tab_access)
        tabs_layout.addWidget(self.tab_pdf)
        tabs_layout.addWidget(self.tab_trash)
        tabs_layout.addStretch()

        # محدد طرق العرض (جدول تفصيلي / شبكة بطاقات / قائمة مدمجة)
        self.view_switch_frame = QFrame()
        self.view_switch_frame.setObjectName("viewSwitcherFrame")
        view_switch_layout = QHBoxLayout(self.view_switch_frame)
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

        tabs_layout.addWidget(self.view_switch_frame)
        main_layout.addLayout(tabs_layout)

        # ========================================================
        # 4. مساحة عرض المستندات (متعددة الأنماط: جدول / بطاقات / مدمجة / سلة المحذوفات)
        # ========================================================
        self.stack = QStackedWidget()
        apply_gov_shadow(self.stack, blur=12, offset_y=2, alpha=10)

        # 4.1 نمط الجدول التفصيلي (TABLE)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "المستند أو المجلد", "النوع / البرنامج", "تاريخ الاعتماد", "الحجم / العناصر", "الحالة السحابية"
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

        # 4.4 قسم سلة المحذوفات وإدارة الحذف (TRASH)
        self.trash_page = QWidget()
        trash_layout = QVBoxLayout(self.trash_page)
        trash_layout.setContentsMargins(0, 0, 0, 0)
        trash_layout.setSpacing(10)

        # ترويسة قسم المحذوفات
        trash_header = QFrame()
        trash_header.setObjectName("trashHeaderFrame")
        th_layout = QHBoxLayout(trash_header)
        th_layout.setContentsMargins(12, 10, 12, 10)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        th_title = QLabel("🗑️ قسم إدارة المستندات المحذوفة (سلة المحذوفات الرسمية)")
        th_title.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        th_title.setStyleSheet("color: #991b1b;")
        info_box.addWidget(th_title)

        th_desc = QLabel("المستندات المنقولة للمحذوفات محفوظة بأمان هنا. يمكنك استعادتها فوراً لموقعها الأصلي أو حذفها نهائياً لتفريغ المساحة.")
        th_desc.setFont(QFont("Segoe UI", 10))
        th_desc.setStyleSheet("color: #566c65;")
        info_box.addWidget(th_desc)
        th_layout.addLayout(info_box)

        th_layout.addStretch()

        btn_empty_trash = QPushButton("🧹 إفراغ سلة المحذوفات بالكامل")
        btn_empty_trash.setObjectName("btnEmptyTrash")
        btn_empty_trash.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_empty_trash.clicked.connect(self._empty_all_trash)
        th_layout.addWidget(btn_empty_trash)

        trash_layout.addWidget(trash_header)

        # جدول المحذوفات
        self.trash_table = QTableWidget()
        self.trash_table.setColumnCount(5)
        self.trash_table.setHorizontalHeaderLabels([
            "المستند المحذوف", "المسار الأصلي", "تاريخ الحذف", "حجم الملف", "الإجراءات المتاحة"
        ])
        self.trash_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.trash_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.verticalHeader().setVisible(False)
        self.trash_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trash_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_gov_shadow(self.trash_table, blur=12, offset_y=2, alpha=10)

        trash_layout.addWidget(self.trash_table, stretch=1)
        self.stack.addWidget(self.trash_page)

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

        self.lbl_trash_stat = QLabel("سلة المحذوفات: 0 مستند")
        self.lbl_trash_stat.setFont(QFont("Cairo", 10))
        self.lbl_trash_stat.setStyleSheet("color: #4b635b;")
        status_layout.addWidget(self.lbl_trash_stat)

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

    def _get_current_abs_folder(self):
        """الحصول على المسار الفعلي الكامل للمجلد النشط حالياً"""
        return (self.sync_folder / self.current_subpath).resolve()

    def _navigate_into_folder(self, folder_name):
        """الدخول إلى مجلد فرعي وتحديث العرض"""
        new_path = self.current_subpath / folder_name
        target = (self.sync_folder / new_path).resolve()
        if target.exists() and target.is_dir():
            self.current_subpath = new_path
            self._update_breadcrumb()
            self._refresh_file_list()

    def _navigate_up(self):
        """الرجوع للمجلد السابق (للأعلى)"""
        if self.current_subpath != Path("."):
            self.current_subpath = self.current_subpath.parent
            self._update_breadcrumb()
            self._refresh_file_list()

    def _update_breadcrumb(self):
        """تحديث شريط المسار بالأقسام والمجلدات الحالية"""
        if self.current_subpath == Path("."):
            self.btn_nav_up.setEnabled(False)
            self.lbl_current_path.setText("📂 المجلد الرئيسي: غرفة تجارة كربلاء المقدسة")
        else:
            self.btn_nav_up.setEnabled(True)
            parts = list(self.current_subpath.parts)
            path_str = " ◀ ".join(parts)
            self.lbl_current_path.setText(f"📂 المسار: غرفة تجارة كربلاء المقدسة ◀ {path_str}")

    def _show_new_folder_dialog(self):
        """نافذة إنشاء مجلد إداري جديد مع اقتراحات سريعة لأقسام الغرفة (قسم إنشاء مجلدات)"""
        dialog = QDialog(self)
        dialog.setWindowTitle("إنشاء مجلد إداري جديد")
        dialog.resize(480, 250)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Cairo', Tahoma; }
            QLabel { font-size: 12px; color: #162420; font-weight: 600; }
            QLineEdit {
                background-color: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 8px;
                padding: 10px 14px; font-size: 13px; color: #162420;
            }
            QLineEdit:focus { border-color: #14372e; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        cur_name = "المجلد الرئيسي" if self.current_subpath == Path(".") else self.current_subpath.name
        title_lbl = QLabel(f"📁 إنشاء مجلد فرعي داخل: {cur_name}")
        title_lbl.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {GOV_GREEN};")
        layout.addWidget(title_lbl)

        txt_name = QLineEdit()
        txt_name.setPlaceholderText("أدخل اسم المجلد الجديد (مثال: الكتب الصادرة 2026)...")
        layout.addWidget(txt_name)

        chips_lbl = QLabel("اقتراحات سريعة لأقسام ومجلدات الغرفة:")
        chips_lbl.setFont(QFont("Cairo", 10))
        chips_lbl.setStyleSheet("color: #566c65;")
        layout.addWidget(chips_lbl)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        suggestions = ["الكتب الصادرة", "الكتب الواردة", "أضابير الكفالات", "التقارير المالية", "محاضر الاجتماعات"]
        for sug in suggestions:
            btn_sug = QPushButton(sug)
            btn_sug.setObjectName("btnSuggestionChip")
            btn_sug.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_sug.clicked.connect(lambda _, s=sug: txt_name.setText(s))
            chips_row.addWidget(btn_sug)
        chips_row.addStretch()
        layout.addLayout(chips_row)

        layout.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setObjectName("btnGovSecondary")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)

        btn_create = QPushButton("📁 إنشاء المجلد")
        btn_create.setObjectName("btnGovPrimary")
        def do_create():
            f_name = txt_name.text().strip()
            if not f_name:
                QMessageBox.warning(dialog, "تنبيه", "يرجى كتابة اسم للمجلد.")
                return
            invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
            if any(c in f_name for c in invalid_chars):
                QMessageBox.warning(dialog, "تنبيه", "اسم المجلد يحتوي على رموز غير صالحة.")
                return
            target_dir = self._get_current_abs_folder() / f_name
            if target_dir.exists():
                QMessageBox.warning(dialog, "تنبيه", f"المجلد '{f_name}' موجود بالفعل.")
                return
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                dialog.accept()
                self._refresh_file_list()
                QMessageBox.information(self, "تم الإنشاء", f"تم إنشاء المجلد '{f_name}' بنجاح.")
            except Exception as e:
                QMessageBox.critical(dialog, "خطأ", f"تعذر إنشاء المجلد:\n{e}")

        btn_create.clicked.connect(do_create)
        btn_row.addWidget(btn_create)

        layout.addLayout(btn_row)
        dialog.exec()

    def _show_context_menu_for_folder(self, folder_name, global_pos):
        """القائمة المنسدلة الخاصة بالمجلدات الإدارية"""
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
        open_action = menu.addAction("📂 الدخول إلى المجلد")
        open_win_action = menu.addAction("📁 استعراض في مجلد Windows")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ نقل المجلد إلى سلة المحذوفات")

        action = menu.exec(global_pos)
        if action == open_action:
            self._navigate_into_folder(folder_name)
        elif action == open_win_action:
            target = (self._get_current_abs_folder() / folder_name).resolve()
            if target.exists():
                subprocess.Popen(f'explorer /select,"{str(target)}"')
        elif action == delete_action:
            self._move_folder_to_trash(folder_name)

    def _move_folder_to_trash(self, folder_name):
        """نقل مجلد كامل إلى سلة المحذوفات بأمان"""
        reply = QMessageBox.question(
            self, "تأكيد حذف المجلد",
            f"هل أنت متأكد من نقل المجلد '{folder_name}' ومحتوياته إلى سلة المحذوفات؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            target = (self._get_current_abs_folder() / folder_name).resolve()
            if target.exists():
                trash_dir = self.state_mgr.db_dir / 'trash'
                trash_dir.mkdir(parents=True, exist_ok=True)
                trash_dest = trash_dir / f"{int(time.time())}_{folder_name}"
                import shutil
                shutil.move(str(target), str(trash_dest))
                rel = str(target.relative_to(self.sync_folder)).replace("\\", "/")
                self.state_mgr.add_to_trash(folder_name, rel, str(trash_dest), 0)
                self._refresh_file_list()
                QMessageBox.information(self, "تم الحذف", f"تم نقل المجلد '{folder_name}' إلى سلة المحذوفات.")

    def _move_file_to_trash(self, file_name, rel_path=None):
        """نقل مستند رسمي إلى سلة المحذوفات (قسم حذف الملفات)"""
        reply = QMessageBox.question(
            self, "تأكيد النقل إلى سلة المحذوفات", 
            f"هل أنت متأكد من نقل المستند التالي إلى سلة المحذوفات؟\n{file_name}\n\n(يمكنك استعادته في أي وقت من قسم سلة المحذوفات)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if rel_path is None:
                rel_path = str((self.current_subpath / file_name)).replace("\\", "/") if self.current_subpath != Path(".") else file_name

            file_path = (self.sync_folder / rel_path).resolve()
            if not file_path.exists():
                file_path = (self._get_current_abs_folder() / file_name).resolve()
            if not file_path.exists():
                file_path = (self.sync_folder / file_name).resolve()

            if file_path.exists():
                trash_dir = self.state_mgr.db_dir / 'trash'
                trash_dir.mkdir(parents=True, exist_ok=True)
                trash_dest = trash_dir / f"{int(time.time())}_{file_path.name}"
                
                size = file_path.stat().st_size if file_path.is_file() else 0
                import shutil
                shutil.move(str(file_path), str(trash_dest))

                self.state_mgr.add_to_trash(file_name, rel_path, str(trash_dest), size)

                if self.client and self.client.is_configured():
                    try:
                        self.client.delete_file(rel_path)
                    except Exception as e:
                        print(f"[Delete remote skip]: {e}")

                self._refresh_file_list()
                QMessageBox.information(self, "تم النقل للمحذوفات", f"تم نقل '{file_name}' إلى سلة المحذوفات بنجاح.")

    def _render_trash_table(self):
        """تصيير قسم سلة المحذوفات (عرض المستندات المحذوفة مؤقتاً وأزرار الاستعادة والحذف النهائي)"""
        items = self.state_mgr.get_trash_files()
        self.trash_table.setRowCount(0)
        for row_idx, item in enumerate(items):
            self.trash_table.insertRow(row_idx)

            name = item['file_name']
            icon = get_file_office_icon(name, size=32)
            name_cell = QTableWidgetItem(name)
            name_cell.setIcon(icon)
            name_cell.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
            self.trash_table.setItem(row_idx, 0, name_cell)

            path_cell = QTableWidgetItem(item.get('original_rel_path', name))
            path_cell.setFont(QFont("Segoe UI", 10))
            path_cell.setForeground(QColor("#566c65"))
            self.trash_table.setItem(row_idx, 1, path_cell)

            date_raw = item.get('deleted_at', '')
            date_str = date_raw[:19].replace('T', ' ') if date_raw else "غير محدد"
            date_cell = QTableWidgetItem(date_str)
            date_cell.setFont(QFont("Segoe UI", 10))
            date_cell.setForeground(QColor("#566c65"))
            self.trash_table.setItem(row_idx, 2, date_cell)

            size_bytes = item.get('file_size', 0)
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1048576:
                size_str = f"{round(size_bytes / 1024, 1)} KB"
            else:
                size_str = f"{round(size_bytes / 1048576, 2)} MB"
            size_cell = QTableWidgetItem(size_str)
            size_cell.setFont(QFont("Segoe UI", 10))
            size_cell.setForeground(QColor("#566c65"))
            self.trash_table.setItem(row_idx, 3, size_cell)

            action_widget = QWidget()
            act_layout = QHBoxLayout(action_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            trash_id = item['id']
            btn_res = QPushButton("🔄 استعادة")
            btn_res.setObjectName("btnTrashRestore")
            btn_res.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_res.clicked.connect(lambda _, tid=trash_id: self._restore_from_trash(tid))
            act_layout.addWidget(btn_res)

            btn_del = QPushButton("❌ حذف نهائي")
            btn_del.setObjectName("btnTrashPurge")
            btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_del.clicked.connect(lambda _, tid=trash_id: self._purge_from_trash(tid))
            act_layout.addWidget(btn_del)

            self.trash_table.setCellWidget(row_idx, 4, action_widget)

    def _restore_from_trash(self, trash_id):
        """استعادة مستند رسمي من سلة المحذوفات إلى موقعه الأصلي"""
        row = self.state_mgr.remove_from_trash(trash_id)
        if row:
            trash_path = Path(row['trash_path'])
            target_path = (self.sync_folder / row['original_rel_path']).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if trash_path.exists():
                import shutil
                shutil.move(str(trash_path), str(target_path))

            if target_path.exists():
                sha = self.sync_engine.calculate_hash(str(target_path)) if self.sync_engine else "hash"
                self.state_mgr.set_file_state(row['original_rel_path'], row['file_name'], sha, row['file_size'], 'synced')
                if self.sync_engine:
                    self.sync_engine.on_local_file_saved(str(target_path))

            self._refresh_file_list()
            self._render_trash_table()
            QMessageBox.information(self, "تمت الاستعادة", f"تمت استعادة '{row['file_name']}' بنجاح إلى موقعه الأصلي.")

    def _purge_from_trash(self, trash_id):
        """الحذف النهائي لمستند من سلة المحذوفات وتفريغ مساحته"""
        reply = QMessageBox.warning(
            self, "تأكيد الحذف النهائي",
            "هل أنت متأكد من حذف هذا المستند نهائياً؟\nلن تتمكن من استعادته مرة أخرى.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            row = self.state_mgr.remove_from_trash(trash_id)
            if row:
                trash_path = Path(row['trash_path'])
                if trash_path.exists():
                    try:
                        trash_path.unlink()
                    except Exception:
                        pass
                if self.client and self.client.is_configured():
                    try:
                        self.client.delete_file(row['original_rel_path'])
                    except Exception:
                        pass
            self._refresh_file_list()
            self._render_trash_table()

    def _empty_all_trash(self):
        """إفراغ سلة المحذوفات بالكامل وحذف كل الملفات المحذوفة مؤقتاً نهائياً"""
        count = self.state_mgr.get_trash_count()
        if count == 0:
            QMessageBox.information(self, "سلة المحذوفات", "سلة المحذوفات فارغة بالفعل.")
            return

        reply = QMessageBox.critical(
            self, "تأكيد إفراغ سلة المحذوفات",
            f"هل تريد بالتأكيد إفراغ سلة المحذوفات وحذف كافة المستندات ({count} مستند) نهائياً؟\nهذا الإجراء نهائي ولا يمكن التراجع عنه.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            rows = self.state_mgr.clear_all_trash()
            for r in rows:
                trash_path = Path(r['trash_path'])
                if trash_path.exists():
                    try:
                        trash_path.unlink()
                    except Exception:
                        pass
                if self.client and self.client.is_configured():
                    try:
                        self.client.delete_file(r['original_rel_path'])
                    except Exception:
                        pass
            self._refresh_file_list()
            self._render_trash_table()
            QMessageBox.information(self, "تم الإفراغ", "تم إفراغ سلة المحذوفات نهائياً بنجاح.")

    def _set_active_filter(self, tag):
        self.active_filter = tag
        if tag == "TRASH":
            self.stack.setCurrentIndex(3)
            self.view_switch_frame.setEnabled(False)
            self.breadcrumb_frame.setVisible(False)
            self._render_trash_table()
        else:
            self.breadcrumb_frame.setVisible(True)
            self.view_switch_frame.setEnabled(True)
            if self.current_view_mode == "GRID":
                self.stack.setCurrentIndex(1)
            elif self.current_view_mode == "COMPACT":
                self.stack.setCurrentIndex(2)
            else:
                self.stack.setCurrentIndex(0)
            self._filter_content()

    def _set_view_mode(self, mode, persist=True):
        self.current_view_mode = mode
        if persist:
            try:
                self.state_mgr.set_setting("file_view_mode", mode)
            except Exception as e:
                print(f"[Save view mode error]: {e}")

        if self.active_filter != "TRASH":
            if mode == "GRID":
                self.btn_view_grid.setChecked(True)
                self.stack.setCurrentIndex(1)
            elif mode == "COMPACT":
                self.btn_view_compact.setChecked(True)
                self.stack.setCurrentIndex(2)
            else:
                self.btn_view_table.setChecked(True)
                self.stack.setCurrentIndex(0)

        self._filter_content()

    def _filter_content(self):
        if self.active_filter == "TRASH":
            self._render_trash_table()
            return

        query = self.search_box.text().strip().lower()
        filtered = []
        for f in self.all_files_cache:
            name = f['file_name'].lower()
            is_folder = f.get('is_folder', False)
            ext = Path(f['file_name']).suffix.lower()

            if self.active_filter == "FOLDERS":
                if not is_folder:
                    continue
            elif self.active_filter == "WORD":
                if is_folder or ext not in ['.docx', '.doc']:
                    if not (is_folder and not query):
                        if not ext in ['.docx', '.doc']:
                            continue
            elif self.active_filter == "EXCEL":
                if ext not in ['.xlsx', '.xls', '.csv']:
                    continue
            elif self.active_filter == "ACCESS":
                if ext not in ['.accdb', '.mdb']:
                    continue
            elif self.active_filter == "PDF":
                if ext != '.pdf':
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
            current_abs = self._get_current_abs_folder()
            if not current_abs.exists():
                current_abs.mkdir(parents=True, exist_ok=True)

            folders_list = []
            files_list = []

            for item in current_abs.iterdir():
                if item.name.startswith(".") or item.name == ".trash":
                    continue
                if item.name.startswith("~$") or item.name.endswith(".tmp") or item.name.endswith(".laccdb") or item.name.endswith(".ldb"):
                    continue

                if item.is_dir():
                    count = len([x for x in item.iterdir() if not x.name.startswith(".") and not x.name.startswith("~$")])
                    folders_list.append({
                        'file_name': item.name,
                        'is_folder': True,
                        'item_count': count,
                        'relative_path': str(item.relative_to(self.sync_folder)).replace("\\", "/"),
                        'file_size': 0,
                        'sync_status': 'synced',
                        'last_modified_local': datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                    })
                elif item.is_file():
                    rel = str(item.relative_to(self.sync_folder)).replace("\\", "/")
                    st = self.state_mgr.get_file_state(rel)
                    if not st:
                        st = {
                            'file_name': item.name,
                            'is_folder': False,
                            'relative_path': rel,
                            'file_size': item.stat().st_size,
                            'sync_status': 'synced',
                            'last_modified_local': datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                        }
                    else:
                        st = dict(st)
                        st['is_folder'] = False
                    files_list.append(st)

            folders_list.sort(key=lambda x: x['file_name'].lower())
            files_list.sort(key=lambda x: x['file_name'].lower())

            all_items = folders_list + files_list
            self.all_files_cache = all_items

            trash_cnt = self.state_mgr.get_trash_count()
            self.lbl_total.setText(f"المستندات: {len(files_list)} ملف | المجلدات: {len(folders_list)}")
            self.lbl_trash_stat.setText(f"سلة المحذوفات: {trash_cnt} مستند")
            self.tab_trash.setText(f"🗑️ سلة المحذوفات ({trash_cnt})" if trash_cnt > 0 else "🗑️ سلة المحذوفات")

            self._filter_content()
        except Exception as e:
            print(f"[Refresh Error]: {e}")

    def _render_grid(self, files):
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

            is_folder = f.get('is_folder', False)
            office_icon = get_file_office_icon(name, size=38, is_folder=is_folder)

            if is_folder:
                app_name = "مجلد مستندات"
                type_tag = "مجلد منظم"
                count = f.get('item_count', 0)
                size_str = f"{count} عناصر"
                date_str = f.get('last_modified_local', '')[:10] if f.get('last_modified_local') else "نشط"
                status_text = "📁 مجلد سحابي"
                status_color = GOV_GREEN
            else:
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
                date_str = date_raw[:19].replace('T', ' ') if date_raw else "محفوظ"

                status_map = {
                    'synced': '● محفوظ ومؤمّن',
                    'syncing': '● جارٍ الرفع...',
                    'pending_upload': '● بانتظار الاتصال',
                    'conflict': '● تم احتواء تعارض',
                    'failed': '● فشل التحقق',
                    'locked': '🔒 محجوزة للتعديل'
                }
                status_text = status_map.get(f.get('sync_status', 'synced'), '● محفوظ')
                status_color = STATUS_SYNCED if f.get('sync_status') == 'synced' else (
                    STATUS_LOCKED if f.get('sync_status') == 'locked' else (
                    "#ef4444" if f.get('sync_status') == 'failed' else STATUS_SYNCING
                ))

            # الخلية 0: المستند أو المجلد
            name_item = QTableWidgetItem(f"{name}\n({type_tag})")
            name_item.setIcon(office_icon)
            name_item.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
            self.table.setItem(row, 0, name_item)

            # الخلية 1: البرنامج المقترن / نوع العنصر
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
            status_item.setForeground(QColor(status_color))
            self.table.setItem(row, 4, status_item)

    def _open_selected_from_table(self, row, col):
        raw_text = self.table.item(row, 0).text()
        file_name = raw_text.split('\n')[0]
        if "(مجلد منظم)" in raw_text:
            self._navigate_into_folder(file_name)
        else:
            self._open_file_by_name(file_name)

    def _open_file_by_name(self, file_name):
        file_path = (self._get_current_abs_folder() / file_name).resolve()
        if not file_path.exists():
            file_path = (self.sync_folder / file_name).resolve()
        if not file_path.exists():
            QMessageBox.warning(
                self, "تنبيه", 
                f"الملف التالي غير موجود فعلياً في مجلد المشاركة:\n{file_path}"
            )
            return

        if file_path.is_dir():
            self._navigate_into_folder(file_name)
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
        if "(مجلد منظم)" in raw_text:
            self._show_context_menu_for_folder(file_name, self.table.viewport().mapToGlobal(pos))
        else:
            self._show_context_menu_for_file(file_name, self.table.viewport().mapToGlobal(pos))

    def _show_context_menu_for_file(self, file_name, global_pos):
        file_path = (self._get_current_abs_folder() / file_name).resolve()
        if not file_path.exists():
            file_path = (self.sync_folder / file_name).resolve()

        if file_path.is_dir():
            self._show_context_menu_for_folder(file_name, global_pos)
            return

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
        delete_action = menu.addAction("🗑️ نقل المستند إلى سلة المحذوفات")

        action = menu.exec(global_pos)
        if action == open_action:
            self._open_file_by_name(file_name)
        elif action == open_folder_action:
            if file_path.exists():
                subprocess.Popen(f'explorer /select,"{str(file_path)}"')
        elif action == delete_action:
            self._move_file_to_trash(file_name)

    def _upload_custom_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر مستنداً لإضافته إلى مجلد المشاركة الرسمي", "",
            "ملفات Office والوثائق (*.docx *.xlsx *.accdb *.pdf *.doc *.xls);;كافة الملفات (*.*)"
        )
        if path:
            dest = self._get_current_abs_folder() / Path(path).name
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
