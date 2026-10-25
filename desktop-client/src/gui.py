"""
تبادل الملفات – File Exchange System
واجهة سطح المكتب بأسلوب Google Stitch (Modern Minimalist & Mica UX Edition)
تصميم أنيق، فائق النقاء، مريح للعين، وبطاقات عصرية فسيحة
"""
import os
import sys
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
    QLineEdit, QSystemTrayIcon, QMenu, QMessageBox, QFileDialog, 
    QFrame, QScrollArea, QGridLayout, QStackedWidget, QButtonGroup,
    QSizePolicy, QDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap, QCursor

from office_handler import OfficeHandler
from icon_provider import get_file_office_icon, get_file_office_pixmap
from autostart import set_windows_autostart, is_windows_autostart_enabled
from r2_client import CloudflareR2Client
from theme import (
    get_stitch_stylesheet, apply_stitch_shadow,
    BG_CANVAS, BG_SURFACE, BG_SURFACE_HOVER, BORDER_SUBTLE,
    TEXT_TITLE, TEXT_BODY, TEXT_MUTED, TEXT_FAINT,
    PRIMARY_ACCENT, BLUE_ACCENT,
    STATUS_SYNCED, STATUS_SYNCED_BG, STATUS_SYNCED_BORDER,
    STATUS_SYNCING, STATUS_SYNCING_BG, STATUS_SYNCING_BORDER,
    STATUS_LOCKED, STATUS_LOCKED_BG, STATUS_LOCKED_BORDER,
    COLOR_WORD, COLOR_EXCEL, COLOR_ACCESS, COLOR_PDF
)

class StatusBridge(QObject):
    sync_updated = pyqtSignal(dict)


class StitchFileCard(QFrame):
    """بطاقة ملف عصرية بتصميم Google Stitch المينيمالي الأنيق"""
    def __init__(self, file_data, sync_folder, on_open_callback, on_delete_callback, parent=None):
        super().__init__(parent)
        self.file_data = file_data
        self.sync_folder = Path(sync_folder)
        self.on_open_callback = on_open_callback
        self.on_delete_callback = on_delete_callback
        self.file_name = file_data['file_name']
        self.file_path = (self.sync_folder / self.file_name).resolve()

        self._init_card()

    def _init_card(self):
        self.setObjectName("stitchCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet(f"""
            QFrame#stitchCard {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 12px;
                padding: 16px;
            }}
            QFrame#stitchCard:hover {{
                border: 1px solid #94a3b8;
                background-color: #ffffff;
            }}
        """)
        apply_stitch_shadow(self, blur=14, offset_y=3, alpha=8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. الترويسة العلوية للبطاقة: أيقونة Office بحجم 56px + معلومات الملف
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        # أيقونة Stitch عالية النقاء
        icon_lbl = QLabel()
        pixmap = get_file_office_pixmap(self.file_name, size=56)
        icon_lbl.setPixmap(pixmap)
        icon_lbl.setFixedSize(56, 56)
        top_layout.addWidget(icon_lbl)

        # بيانات الملف والعنوان
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        ext = self.file_path.suffix.lower()
        if ext in ['.docx', '.doc']:
            tag_text = "Microsoft Word"
            tag_color = COLOR_WORD
            tag_bg = "#eff6ff"
        elif ext in ['.xlsx', '.xls', '.csv']:
            tag_text = "Microsoft Excel"
            tag_color = COLOR_EXCEL
            tag_bg = "#ecfdf5"
        elif ext in ['.accdb', '.mdb']:
            tag_text = "Microsoft Access"
            tag_color = COLOR_ACCESS
            tag_bg = "#fff1f2"
        elif ext == '.pdf':
            tag_text = "Adobe PDF"
            tag_color = COLOR_PDF
            tag_bg = "#fef2f2"
        else:
            tag_text = "ملف عام"
            tag_color = "#475569"
            tag_bg = "#f1f5f9"

        tag_badge = QLabel(f" {tag_text} ")
        tag_badge.setStyleSheet(f"""
            background-color: {tag_bg};
            color: {tag_color};
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 6px;
        """)
        info_layout.addWidget(tag_badge, alignment=Qt.AlignmentFlag.AlignRight)

        # اسم الملف بخط Segoe UI عريض
        name_lbl = QLabel(self.file_name)
        name_lbl.setWordWrap(True)
        name_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_TITLE}; font-weight: 800;")
        name_lbl.setToolTip(str(self.file_path))
        info_layout.addWidget(name_lbl)

        top_layout.addLayout(info_layout)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # 2. شريط التفاصيل المصغرة (الحجم وتاريخ آخر حفظ)
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(12)

        size_bytes = self.file_data.get('file_size', 0)
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1048576:
            size_str = f"{round(size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(size_bytes / 1048576, 2)} MB"

        size_lbl = QLabel(f"💾 {size_str}")
        size_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        meta_layout.addWidget(size_lbl)

        date_raw = self.file_data.get('last_modified_local', '')[:16].replace('T', ' ')
        date_lbl = QLabel(f"🕒 {date_raw}")
        date_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        meta_layout.addWidget(date_lbl)
        meta_layout.addStretch()

        layout.addLayout(meta_layout)

        # 3. شارة حالة المزامنة اللحظية
        status_map = {
            'synced': ('● متزامن سحابياً', STATUS_SYNCED, STATUS_SYNCED_BG, STATUS_SYNCED_BORDER),
            'syncing': ('● جارٍ المزامنة...', STATUS_SYNCING, STATUS_SYNCING_BG, STATUS_SYNCING_BORDER),
            'pending_upload': ('● بانتظار الاتصال', '#0284c7', '#f0f9ff', '#bae6fd'),
            'conflict': ('● تعارض محمي', '#b45309', '#fffbeb', '#fde68a'),
            'failed': ('● فشل التزامن', '#ef4444', '#fef2f2', '#fecaca'),
            'locked': ('🔒 محجوز ومؤمن ضد التلف', STATUS_LOCKED, STATUS_LOCKED_BG, STATUS_LOCKED_BORDER)
        }
        status_key = self.file_data.get('sync_status', 'synced')
        s_text, s_color, s_bg, s_border = status_map.get(status_key, (status_key, '#475569', '#f8fafc', '#e2e8f0'))

        status_pill = QLabel(f" {s_text} ")
        status_pill.setStyleSheet(f"""
            background-color: {s_bg};
            color: {s_color};
            border: 1px solid {s_border};
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
        """)
        layout.addWidget(status_pill, alignment=Qt.AlignmentFlag.AlignRight)

        # 4. أزرار التحكم بأسلوب Google Stitch
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(6)

        btn_open = QPushButton("⚡ فتح الملف الآن")
        btn_open.setObjectName("btnCardAction")
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(lambda: self.on_open_callback(self.file_name))
        actions_layout.addWidget(btn_open, stretch=3)

        btn_folder = QPushButton("📂 المجلد")
        btn_folder.setObjectName("btnStitchSecondary")
        btn_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_folder.clicked.connect(self._open_in_explorer)
        actions_layout.addWidget(btn_folder, stretch=1)

        btn_more = QPushButton("⋮")
        btn_more.setObjectName("btnStitchSecondary")
        btn_more.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_more.clicked.connect(self._show_options_menu)
        actions_layout.addWidget(btn_more)

        layout.addLayout(actions_layout)

    def mouseDoubleClickEvent(self, event):
        self.on_open_callback(self.file_name)

    def _open_in_explorer(self):
        if self.file_path.exists():
            subprocess.Popen(f'explorer /select,"{str(self.file_path)}"')

    def _show_options_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #f1f5f9;
                color: #0f172a;
                font-weight: bold;
            }
        """)
        open_action = menu.addAction("⚡ فتح بالبرنامج الأصلي")
        folder_action = menu.addAction("📂 استعراض في مجلد Windows")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ حذف الملف")

        action = menu.exec(QCursor.pos())
        if action == open_action:
            self.on_open_callback(self.file_name)
        elif action == folder_action:
            self._open_in_explorer()
        elif action == delete_action:
            self.on_delete_callback(self.file_name)


class FileExchangeMainWindow(QMainWindow):
    """النافذة الرئيسية لنظام تبادل الملفات بأسلوب Google Stitch العصري"""
    def __init__(self, sync_engine, supabase_client, local_state_mgr, sync_folder):
        super().__init__()
        self.sync_engine = sync_engine
        self.client = supabase_client
        self.state_mgr = local_state_mgr
        self.sync_folder = Path(sync_folder)

        self.active_filter = "ALL"
        self.current_view_mode = "GRID"

        self.setWindowTitle("تبادل الملفات – File Exchange System (Stitch Minimalist Edition)")
        self.resize(1160, 760)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.setStyleSheet(get_stitch_stylesheet())

        self.bridge = StatusBridge()
        self.bridge.sync_updated.connect(self.handle_sync_update)
        if self.sync_engine:
            self.sync_engine.register_status_listener(lambda data: self.bridge.sync_updated.emit(data))

        self._setup_ui()
        self._setup_tray()
        self._refresh_file_list()

        # مؤقت دوري للتحديث الهادئ
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_file_list)
        self.timer.start(2500)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 18, 24, 18)
        main_layout.setSpacing(14)

        # 1. ترويسة Stitch العلوية النقية (Minimalist Top Bar)
        top_bar = QFrame()
        top_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 12px;
                padding: 10px 18px;
            }}
        """)
        apply_stitch_shadow(top_bar, blur=14, offset_y=2, alpha=6)

        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(4, 2, 4, 2)

        # شعار النظام المينيمالي
        logo_lbl = QLabel("⚡")
        logo_lbl.setStyleSheet("""
            background-color: #0f172a;
            color: #ffffff;
            border-radius: 8px;
            font-size: 16px;
            padding: 6px 10px;
            font-weight: bold;
        """)
        top_layout.addWidget(logo_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        app_title = QLabel("تبادل الملفات – File Exchange System")
        app_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        app_title.setStyleSheet(f"color: {TEXT_TITLE}; font-weight: 800;")
        
        app_sub = QLabel("مزامنة فورية (Ctrl+S) بين 10 أجهزة لملفات Word و Excel وقواعد Access")
        app_sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        title_box.addWidget(app_title)
        title_box.addWidget(app_sub)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        # شارة حالة الاتصال
        is_cloud = self.client and self.client.is_configured()
        if is_cloud:
            if hasattr(self.client, 'account_id'):
                badge_text = "● متصل بـ Cloudflare R2"
            else:
                badge_text = "● متصل بـ Supabase (بدون باسورد)"
        else:
            badge_text = "● وضع المزامنة المحلي"
        badge_color = STATUS_SYNCED if is_cloud else BLUE_ACCENT
        badge_bg = STATUS_SYNCED_BG if is_cloud else "#eff6ff"
        badge_border = STATUS_SYNCED_BORDER if is_cloud else "#bfdbfe"

        self.cloud_badge = QLabel(badge_text)
        self.cloud_badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: {badge_color};
            font-weight: 700;
            padding: 6px 14px;
            border-radius: 16px;
            border: 1px solid {badge_border};
            font-size: 11px;
        """)
        top_layout.addWidget(self.cloud_badge)

        main_layout.addWidget(top_bar)

        # 2. شريط كبسولات الإحصائيات المصغرة (Stitch Compact Metric Pills)
        metrics_bar = QHBoxLayout()
        metrics_bar.setSpacing(8)

        self.pill_total = self._create_metric_pill("📁 المستندات:", "0 ملف")
        self.pill_watcher = self._create_metric_pill("⚡ المراقبة اللحظية:", "نشطة (Ctrl+S)")
        self.pill_access = self._create_metric_pill("🔒 حماية Access:", "مفعلة بالكامل")
        self.pill_devices = self._create_metric_pill("☁️ الأجهزة المترابطة:", "10 أجهزة مصرحة")

        metrics_bar.addWidget(self.pill_total)
        metrics_bar.addWidget(self.pill_watcher)
        metrics_bar.addWidget(self.pill_access)
        metrics_bar.addWidget(self.pill_devices)
        main_layout.addLayout(metrics_bar)

        # 3. شريط البحث والأوامر بأسلوب Stitch (Controls Row)
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("stitchSearch")
        self.search_box.setPlaceholderText("🔍 بحث سريع في الملفات المشتركة...")
        self.search_box.textChanged.connect(self._filter_content)
        ctrl_layout.addWidget(self.search_box, stretch=3)

        self.btn_upload = QPushButton("＋ إضافة ملف")
        self.btn_upload.setObjectName("btnStitchPrimary")
        self.btn_upload.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload.clicked.connect(self._upload_custom_file)
        ctrl_layout.addWidget(self.btn_upload)

        self.btn_open_folder = QPushButton("📁 المجلد المشترك")
        self.btn_open_folder.setObjectName("btnStitchSecondary")
        self.btn_open_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_open_folder.clicked.connect(lambda: os.startfile(str(self.sync_folder)))
        ctrl_layout.addWidget(self.btn_open_folder)

        self.btn_refresh = QPushButton("🔄 تحديث")
        self.btn_refresh.setObjectName("btnStitchSecondary")
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.clicked.connect(self._refresh_file_list)
        ctrl_layout.addWidget(self.btn_refresh)

        self.btn_autostart = QPushButton("⚙️ بدء مع ويندوز")
        self.btn_autostart.setObjectName("btnStitchSecondary")
        self.btn_autostart.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_autostart.clicked.connect(self._toggle_autostart)
        ctrl_layout.addWidget(self.btn_autostart)

        self.btn_cloud = QPushButton("☁️ ربط السحابة")
        self.btn_cloud.setObjectName("btnStitchSecondary")
        self.btn_cloud.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cloud.clicked.connect(self._open_cloud_settings)
        ctrl_layout.addWidget(self.btn_cloud)

        main_layout.addLayout(ctrl_layout)

        # 4. رقائق التصفية السريعة (Filter Chips) + تبديل العرض
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(6)

        filter_group = QButtonGroup(self)
        filter_group.setExclusive(True)

        self.chip_all = self._create_filter_chip("الكل", "ALL", filter_group, checked=True)
        self.chip_word = self._create_filter_chip("Word", "WORD", filter_group)
        self.chip_excel = self._create_filter_chip("Excel", "EXCEL", filter_group)
        self.chip_access = self._create_filter_chip("Access", "ACCESS", filter_group)
        self.chip_pdf = self._create_filter_chip("PDF", "PDF", filter_group)

        filter_layout.addWidget(self.chip_all)
        filter_layout.addWidget(self.chip_word)
        filter_layout.addWidget(self.chip_excel)
        filter_layout.addWidget(self.chip_access)
        filter_layout.addWidget(self.chip_pdf)

        filter_layout.addStretch()

        self.btn_view_grid = QPushButton("بطاقات")
        self.btn_view_grid.setObjectName("stitchChip")
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setChecked(True)
        self.btn_view_grid.clicked.connect(lambda: self._set_view_mode("GRID"))
        filter_layout.addWidget(self.btn_view_grid)

        self.btn_view_table = QPushButton("جدول")
        self.btn_view_table.setObjectName("stitchChip")
        self.btn_view_table.setCheckable(True)
        self.btn_view_table.clicked.connect(lambda: self._set_view_mode("TABLE"))
        filter_layout.addWidget(self.btn_view_table)

        main_layout.addLayout(filter_layout)

        # 5. الحاوية الرئيسية (Cards Grid or Table or Empty State)
        self.stack = QStackedWidget()

        # صفحة 0: شبكة البطاقات النقية (Stitch Card Grid)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.scroll_area.setWidget(self.cards_container)
        self.stack.addWidget(self.scroll_area)

        # صفحة 1: جدول منظم وفسيح
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "المستند والملف المشترك", "البرنامج المقترن", "الحجم", "تاريخ آخر حفظ", "حالة المزامنة السحابية"
        ])
        self.table.setIconSize(QSize(40, 40))
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._open_selected_from_table)
        self.stack.addWidget(self.table)

        # صفحة 2: حالة الفراغ المينيمالية (Clean Empty State)
        empty_card = QFrame()
        empty_card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_SURFACE};
                border: 1px dashed {BORDER_SUBTLE};
                border-radius: 14px;
                padding: 40px;
            }}
        """)
        empty_box = QVBoxLayout(empty_card)
        empty_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.setSpacing(10)

        empty_icon = QLabel("📂")
        empty_icon.setFont(QFont("Segoe UI Emoji", 40))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(empty_icon)

        empty_title = QLabel("لا توجد مستندات مطابقة للبحث أو المجلد فارغ")
        empty_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        empty_title.setStyleSheet(f"color: {TEXT_TITLE}; font-weight: 800;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(empty_title)

        empty_desc = QLabel("أضف ملفات Word أو Excel أو قواعد بيانات Access في المجلد المشترك لتتم مزامنتها تلقائياً.")
        empty_desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(empty_desc)

        btn_empty = QPushButton("＋ إضافة أول مستند")
        btn_empty.setObjectName("btnStitchPrimary")
        btn_empty.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_empty.clicked.connect(self._upload_custom_file)
        empty_box.addWidget(btn_empty, alignment=Qt.AlignmentFlag.AlignCenter)

        self.stack.addWidget(empty_card)

        main_layout.addWidget(self.stack, stretch=1)

        # 6. شريط التذييل الهادئ (Clean Footer)
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 10px;
                padding: 8px 16px;
            }}
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(4, 2, 4, 2)

        self.footer_status = QLabel(f"📂 مسار مجلد التبادل: {self.sync_folder}")
        self.footer_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 500;")
        footer_layout.addWidget(self.footer_status)

        footer_layout.addStretch()

        self.files_count_lbl = QLabel("0 ملفات نشطة")
        self.files_count_lbl.setStyleSheet(f"color: {TEXT_TITLE}; font-size: 11px; font-weight: 700;")
        footer_layout.addWidget(self.files_count_lbl)

        main_layout.addWidget(footer)

    def _create_metric_pill(self, label, value):
        pill = QFrame()
        pill.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 8px;
                padding: 6px 12px;
            }}
        """)
        box = QHBoxLayout(pill)
        box.setContentsMargins(4, 2, 4, 2)
        box.setSpacing(6)

        t_lbl = QLabel(label)
        t_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        box.addWidget(t_lbl)

        v_lbl = QLabel(value)
        v_lbl.setObjectName("metricValue")
        v_lbl.setStyleSheet(f"color: {TEXT_TITLE}; font-size: 11px; font-weight: 800;")
        box.addWidget(v_lbl)

        return pill

    def _create_filter_chip(self, label, filter_id, group, checked=False):
        btn = QPushButton(label)
        btn.setObjectName("stitchChip")
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        group.addButton(btn)
        btn.clicked.connect(lambda: self._set_filter(filter_id))
        return btn

    def _set_filter(self, filter_id):
        self.active_filter = filter_id
        self._refresh_file_list()

    def _set_view_mode(self, mode):
        self.current_view_mode = mode
        if mode == "GRID":
            self.btn_view_grid.setChecked(True)
            self.btn_view_table.setChecked(False)
        else:
            self.btn_view_grid.setChecked(False)
            self.btn_view_table.setChecked(True)
        self._refresh_file_list()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("تبادل الملفات – قيد المراقبة بالخلفية")
        menu = QMenu()
        show_action = menu.addAction("إظهار الواجهة الرئيسية")
        show_action.triggered.connect(self.showNormal)
        open_f_action = menu.addAction("فتح مجلد التبادل")
        open_f_action.triggered.connect(lambda: os.startfile(str(self.sync_folder)))
        quit_action = menu.addAction("خروج نهائي")
        quit_action.triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "تبادل الملفات", 
            "التطبيق مستمر في مراقبة وحفظ تعديلات Word و Excel و Access تلقائياً.", 
            QSystemTrayIcon.MessageIcon.Information, 1500
        )

    def _quit_app(self):
        if self.sync_engine:
            self.sync_engine.stop()
        QApplication.quit()

    def handle_sync_update(self, data):
        filename = data.get("file", "")
        status = data.get("status", "")
        self.footer_status.setText(f"آخر عملية حفظ فورية: {filename} – {status}")
        self._refresh_file_list()

    def _filter_content(self):
        self._refresh_file_list()

    def _refresh_file_list(self):
        files = self.state_mgr.get_all_files()
        search_text = self.search_box.text().strip().lower()

        filtered_files = []
        for f in files:
            name = f['file_name']
            ext = Path(name).suffix.lower()

            if self.active_filter == "WORD" and ext not in ['.docx', '.doc']:
                continue
            elif self.active_filter == "EXCEL" and ext not in ['.xlsx', '.xls', '.csv']:
                continue
            elif self.active_filter == "ACCESS" and ext not in ['.accdb', '.mdb']:
                continue
            elif self.active_filter == "PDF" and ext != '.pdf':
                continue

            if search_text and search_text not in name.lower():
                continue

            filtered_files.append(f)

        v_lbl = self.pill_total.findChild(QLabel, "metricValue")
        if v_lbl:
            v_lbl.setText(f"{len(filtered_files)} ملف")

        self.files_count_lbl.setText(f"إجمالي الملفات: {len(filtered_files)}")

        if not filtered_files:
            self.stack.setCurrentIndex(2)
            return

        if self.current_view_mode == "GRID":
            self.stack.setCurrentIndex(0)
            self._render_card_grid(filtered_files)
        else:
            self.stack.setCurrentIndex(1)
            self._render_table(filtered_files)

    def _render_card_grid(self, files):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        cols = 2
        for idx, f in enumerate(files):
            row = idx // cols
            col = idx % cols
            card = StitchFileCard(
                file_data=f,
                sync_folder=self.sync_folder,
                on_open_callback=self._open_file_by_name,
                on_delete_callback=self._delete_file_by_name
            )
            self.cards_layout.addWidget(card, row, col)

    def _render_table(self, files):
        self.table.setRowCount(0)
        for f in files:
            name = f['file_name']
            row = self.table.rowCount()
            self.table.insertRow(row)

            office_icon = get_file_office_icon(name, size=40)
            ext = Path(name).suffix.lower()
            if ext in ['.docx', '.doc']:
                app_name = "Microsoft Word"
                type_tag = "مستند Word"
            elif ext in ['.xlsx', '.xls', '.csv']:
                app_name = "Microsoft Excel"
                type_tag = "جدول بيانات Excel"
            elif ext in ['.accdb', '.mdb']:
                app_name = "Microsoft Access"
                type_tag = "قاعدة بيانات Access"
            elif ext == '.pdf':
                app_name = "Adobe PDF"
                type_tag = "ملف PDF"
            else:
                app_name = "برنامج Windows الافتراضي"
                type_tag = "ملف عام"

            size_bytes = f['file_size']
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1048576:
                size_str = f"{round(size_bytes / 1024, 1)} KB"
            else:
                size_str = f"{round(size_bytes / 1048576, 2)} MB"

            status_map = {
                'synced': '● متطابق في السحابة',
                'syncing': '● جارٍ المزامنة...',
                'pending_upload': '● بانتظار الاتصال',
                'conflict': '● تم احتواء تعارض',
                'failed': '● فشل التحقق',
                'locked': '🔒 محجوز ومؤمن'
            }
            status_text = status_map.get(f['sync_status'], f['sync_status'])

            name_item = QTableWidgetItem(f"{name}\n({type_tag})")
            name_item.setIcon(office_icon)
            name_item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            self.table.setItem(row, 0, name_item)

            app_item = QTableWidgetItem(app_name)
            app_item.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            app_item.setForeground(QColor("#334155"))
            self.table.setItem(row, 1, app_item)

            size_item = QTableWidgetItem(size_str)
            size_item.setFont(QFont("Segoe UI", 10))
            size_item.setForeground(QColor(TEXT_MUTED))
            self.table.setItem(row, 2, size_item)

            date_str = f['last_modified_local'][:19].replace('T', ' ')
            date_item = QTableWidgetItem(date_str)
            date_item.setFont(QFont("Segoe UI", 10))
            date_item.setForeground(QColor(TEXT_MUTED))
            self.table.setItem(row, 3, date_item)

            status_item = QTableWidgetItem(status_text)
            if f['sync_status'] == 'synced':
                status_item.setForeground(QColor(STATUS_SYNCED))
                status_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            elif f['sync_status'] == 'conflict':
                status_item.setForeground(QColor(STATUS_SYNCING))
                status_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            elif f['sync_status'] == 'failed':
                status_item.setForeground(QColor("#ef4444"))
            elif f['sync_status'] == 'locked':
                status_item.setForeground(QColor(STATUS_LOCKED))
                status_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.table.setItem(row, 4, status_item)

    def _open_selected_from_table(self, row, col):
        raw_text = self.table.item(row, 0).text()
        file_name = raw_text.split('\n')[0]
        self._open_file_by_name(file_name)

    def _show_context_menu(self, pos):
        selected = self.table.selectedItems()
        if not selected:
            return
        raw_text = self.table.item(selected[0].row(), 0).text()
        file_name = raw_text.split('\n')[0]
        file_path = (self.sync_folder / file_name).resolve()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #f1f5f9;
                color: #0f172a;
                font-weight: bold;
            }
        """)
        open_action = menu.addAction("⚡ فتح الملف بالبرنامج الأصلي")
        open_folder_action = menu.addAction("📂 استعراض في مجلد Windows")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ حذف الملف")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == open_action:
            self._open_file_by_name(file_name)
        elif action == open_folder_action:
            if file_path.exists():
                subprocess.Popen(f'explorer /select,"{str(file_path)}"')
        elif action == delete_action:
            self._delete_file_by_name(file_name)

    def _open_file_by_name(self, file_name):
        file_path = (self.sync_folder / file_name).resolve()

        if not file_path.exists():
            QMessageBox.warning(
                self, "الملف غير متوفر", 
                f"الملف التالي غير موجود فعلياً في مجلد المشاركة:\n{file_path}\n\nيرجى تحديث القائمة."
            )
            return

        if OfficeHandler.is_access_db(str(file_path)):
            if self.client and self.client.is_configured():
                try:
                    is_locked, lock_info = self.client.check_file_lock(file_name)
                    if is_locked and lock_info and lock_info.get('locked_by') != self.client.user_id:
                        user_locked = lock_info.get('profiles', {}).get('full_name', 'مستخدم آخر')
                        device_locked = lock_info.get('devices', {}).get('device_name', 'جهاز آخر')
                        QMessageBox.critical(
                            self, "قاعدة البيانات محجوزة!",
                            f"قاعدة بيانات Access ({file_name}) مفتوحة حالياً بواسطة:\n"
                            f"👤 المستخدم: {user_locked}\n"
                            f"💻 على الجهاز: {device_locked}\n\n"
                            f"⛔ تم منع فتحها تجنباً لتلف بيانات المؤسسة.\n"
                            f"يرجى الانتظار حتى ينتهي المستخدم الآخر ويغلق قاعدة البيانات."
                        )
                        return
                except Exception as e:
                    print(f"تخطي فحص القفل السحابي: {e}")

        try:
            OfficeHandler.open_native_file(str(file_path))
            self.footer_status.setText(f"تم إطلاق البرنامج الأصلي لفتح: {file_name}")
        except Exception as e:
            QMessageBox.critical(
                self, "خطأ في فتح الملف", 
                f"تعذر فتح الملف بالبرنامج الأصلي:\n{str(e)}\n\n"
                f"تأكد من وجود برنامج مثبت على جهازك يدعم صيغة ({file_path.suffix}) مثل Word أو Excel أو Access."
            )

    def _delete_file_by_name(self, file_name):
        reply = QMessageBox.question(
            self, "تأكيد الحذف", 
            f"هل أنت متأكد من رغبتك في حذف الملف التالي نهائياً؟\n{file_name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            file_path = self.sync_folder / file_name
            if file_path.exists():
                file_path.unlink()
            self._refresh_file_list()

    def _upload_custom_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر ملفاً لإضافته إلى مجلد التبادل المشترك", "",
            "ملفات Office والشائعة (*.docx *.xlsx *.accdb *.pdf *.txt);;كافة الملفات (*.*)"
        )
        if path:
            dest = self.sync_folder / Path(path).name
            import shutil
            shutil.copy2(path, dest)
            self._refresh_file_list()
            QMessageBox.information(
                self, "نجاح الإضافة", 
                f"تمت إضافة '{Path(path).name}' إلى مجلد التبادل بنجاح وسيتم حفظه ومزامنته فورياً."
            )

    def _toggle_autostart(self):
        currently_enabled = is_windows_autostart_enabled()
        new_state = not currently_enabled
        success, msg = set_windows_autostart(new_state)
        if success:
            state_str = "مفعل" if new_state else "معطل"
            QMessageBox.information(self, "إعدادات التشغيل التلقائي", f"{msg}\nالحالة الحالية: {state_str}")
        else:
            QMessageBox.warning(self, "خطأ", msg)

    def _open_cloud_settings(self):
        """نافذة إعدادات التخزين السحابي المجاني (Supabase بدون كلمة مرور)"""
        dialog = QDialog(self)
        dialog.setWindowTitle("إعدادات الربط السحابي – تبادل الملفات (بدون كلمة مرور)")
        dialog.resize(500, 420)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma; }
            QLabel { font-size: 12px; color: #0f172a; font-weight: 600; }
            QLineEdit {
                background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px;
                padding: 9px 12px; font-size: 12px; color: #0f172a;
            }
            QLineEdit:focus { border: 1.5px solid #2563eb; }
            QPushButton {
                background-color: #0f172a; color: white; border-radius: 8px;
                padding: 10px; font-weight: bold; font-size: 12px; border: none;
            }
            QPushButton:hover { background-color: #1e293b; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        header_lbl = QLabel("☁️ ربط السحابة المجانية (Supabase)")
        header_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(header_lbl)

        desc_lbl = QLabel("⚡ نظام يعمل بالكامل بدون كلمة مرور أو تسجيل دخول للموظفين عبر المفتاح العام (Anon Key).")
        desc_lbl.setStyleSheet("color: #059669; font-size: 11px; font-weight: 600; background: #ecfdf5; padding: 8px 12px; border-radius: 6px; border: 1px solid #a7f3d0;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        cur_url = self.state_mgr.get_setting("supabase_url", "https://bjcillpivgcntzbwmpsm.supabase.co")
        cur_key = self.state_mgr.get_setting("supabase_key", "sb_publishable_Bfk1klLDNsLWKHvdRhWqNg_XoDqqJ6X")

        layout.addWidget(QLabel("عنوان الخادم السحابي (Supabase URL):"))
        txt_url = QLineEdit(cur_url)
        txt_url.setPlaceholderText("https://xxxx.supabase.co")
        layout.addWidget(txt_url)

        layout.addWidget(QLabel("المفتاح العام للمشروع (Anon Public Key):"))
        txt_key = QLineEdit(cur_key)
        txt_key.setPlaceholderText("انسخ المفتاح العام من إعدادات Supabase > API")
        layout.addWidget(txt_key)

        info_lbl = QLabel("📌 للحصول على المفتاح العام (بدون أي باسورد):\nمن موقع Supabase اضغط ⚙️ Project Settings > ثم API > وانسخ المفتاح من خانة anon public.")
        info_lbl.setStyleSheet("color: #64748b; font-size: 11px; line-height: 1.4;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        btn_save = QPushButton("اختبار الاتصال وحفظ الإعدادات السحابية")
        def save_and_test():
            url = txt_url.text().strip()
            key = txt_key.text().strip()

            if not url or not key:
                QMessageBox.warning(dialog, "تنبيه", "يرجى إدخال رابط السحابة والمفتاح العام.")
                return

            from supabase_client import SupabaseClient
            client = SupabaseClient(url, key)
            files = client.list_files()
            
            self.state_mgr.set_setting("supabase_url", url)
            self.state_mgr.set_setting("supabase_key", key)

            self.client = client
            if self.sync_engine:
                self.sync_engine.client = client
                self.sync_engine.pull_remote_changes()

            self.cloud_badge.setText("● متصل بـ Supabase (بدون باسورد)")
            self.cloud_badge.setStyleSheet("""
                background-color: #ecfdf5; color: #10b981; font-weight: 700;
                padding: 6px 14px; border-radius: 16px; border: 1px solid #a7f3d0; font-size: 11px;
            """)
            QMessageBox.information(dialog, "نجاح الاتصال", "تم الاتصال بالسحابة بنجاح وبدون أي كلمة مرور!\nسيبدأ المزامنة التلقائية لجميع الملفات فوراً.")
            dialog.accept()

        btn_save.clicked.connect(save_and_test)
        layout.addWidget(btn_save)

        dialog.exec()
