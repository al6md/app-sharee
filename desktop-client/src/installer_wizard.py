"""
Share COC Enterprise v4.0 – غرفة تجارة كربلاء المقدسة
معالج التثبيت الرسمي لنظام Windows (Official Windows Setup Wizard & Uninstaller)
يقوم بتثبيت التطبيق في المسار القياسي، وتسجيله في البرامج المثبتة (Add/Remove Programs)،
وإنشاء اختصارات سطح المكتب وقائمة ابدأ وقائمة الزر الأيمن (Send To) والتشغيل التلقائي.
"""
import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QProgressBar,
    QStackedWidget, QFileDialog, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap, QCursor

from windows_integration import (
    APP_DISPLAY_NAME,
    APP_VERSION,
    APP_PUBLISHER,
    APP_EXE_NAME,
    UNINSTALL_EXE_NAME,
    get_default_install_dir,
    get_default_sync_dir,
     get_desktop_dirs,
    get_start_menu_folder,
    get_sendto_folder,
    setup_all_system_integrations,
    unregister_from_windows,
)


def _get_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


class InstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished_install = pyqtSignal(bool, str, str)

    def __init__(self, install_dir: Path, sync_dir: Path, options: dict):
        super().__init__()
        self.install_dir = install_dir
        self.sync_dir = sync_dir
        self.options = options

    def run(self):
        try:
            self.progress.emit(8, "جاري إغلاق أي نسخة قديمة قيد التشغيل...")
            subprocess.run(
                ["taskkill", "/F", "/IM", APP_EXE_NAME, "/T"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            time.sleep(0.6)

            self.progress.emit(22, "جاري تجهيز مجلد التثبيت الرسمي على النظام...")
            self.install_dir.mkdir(parents=True, exist_ok=True)
            self.sync_dir.mkdir(parents=True, exist_ok=True)

            bundle_dir = _get_bundle_dir()
            # البحث عن ملف التطبيق التنفيذي المدمج داخل معالج التثبيت
            payload_candidates = [
                bundle_dir / "payload" / APP_EXE_NAME,
                bundle_dir / APP_EXE_NAME,
                Path(__file__).parent.parent / "dist" / APP_EXE_NAME,
            ]
            src_exe = next((p for p in payload_candidates if p.exists()), None)
            if not src_exe:
                self.finished_install.emit(False, "تعذر العثور على حزمة التطبيق التنفيذية داخل معالج التثبيت.", "")
                return

            self.progress.emit(45, "جاري نسخ ملفات منظومة Share COC v4.0 إلى القرص الصلب...")
            dest_exe = self.install_dir / APP_EXE_NAME
            shutil.copy2(str(src_exe), str(dest_exe))

            # نسخ الشعارات والأيقونات الرسمية
            assets_dest = self.install_dir / "assets"
            assets_dest.mkdir(parents=True, exist_ok=True)
            for asset_name in ("logo.ico", "logo.png"):
                for cand in (bundle_dir / "assets" / asset_name, bundle_dir / asset_name):
                    if cand.exists():
                        shutil.copy2(str(cand), str(assets_dest / asset_name))
                        shutil.copy2(str(cand), str(self.install_dir / asset_name))
                        break

            # نسخ أداة إلغاء التثبيت الرسمية
            self.progress.emit(65, "جاري إعداد أداة إلغاء التثبيت الرسمية (Uninstaller)...")
            uninstaller_dest = self.install_dir / UNINSTALL_EXE_NAME
            if getattr(sys, "frozen", False):
                try:
                    shutil.copy2(sys.executable, str(uninstaller_dest))
                except Exception:
                    pass

            # تسجيل التكامل مع نظام Windows
            self.progress.emit(82, "جاري إنشاء الاختصارات وتسجيل البرنامج في نظام Windows...")
            icon_file = self.install_dir / "logo.ico"
            setup_all_system_integrations(
                exe_path=dest_exe,
                sync_dir=self.sync_dir,
                icon_path=icon_file if icon_file.exists() else None,
                create_desktop=self.options.get("desktop", True),
                create_start_menu=self.options.get("start_menu", True),
                create_sendto=self.options.get("sendto", True),
                enable_autostart=self.options.get("autostart", True),
                register_uninstaller=self.options.get("register_uninstall", True),
                uninstaller_path=uninstaller_dest if uninstaller_dest.exists() else dest_exe,
            )

            self.progress.emit(100, "✅ اكتمل تثبيت منظومة Share COC v4.0 بنجاح!")
            self.finished_install.emit(True, "تم تثبيت المنظومة بنجاح.", str(dest_exe))
        except Exception as e:
            self.finished_install.emit(False, f"حدث خطأ أثناء التثبيت:\n{e}", "")


class ShareCOCInstallerWizard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bundle_dir = _get_bundle_dir()
        self.logo_path = self.bundle_dir / "assets" / "logo.png"
        if not self.logo_path.exists():
            self.logo_path = self.bundle_dir / "assets" / "logo.ico"
        if not self.logo_path.exists():
            self.logo_path = self.bundle_dir / "logo.ico"

        self.installed_exe_path = ""
        self.setWindowTitle(f"معالج تثبيت {APP_DISPLAY_NAME}")
        self.setFixedSize(760, 540)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        if self.logo_path.exists():
            self.setWindowIcon(QIcon(str(self.logo_path)))

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet("background-color: #f4f7f5; font-family: 'Cairo', 'Segoe UI', Tahoma;")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. الترويسة الرسمية لمعالج التثبيت
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0b221b, stop:0.5 #13382e, stop:1 #1a473b);
                border-bottom: 3px solid #c59b27;
                padding: 14px 22px;
            }
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setSpacing(14)

        logo_lbl = QLabel()
        if self.logo_path.exists():
            pix = QPixmap(str(self.logo_path)).scaled(
                54, 54, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl.setPixmap(pix)
        else:
            logo_lbl.setText("🏛️")
            logo_lbl.setStyleSheet("font-size: 28px; color: white;")
        logo_lbl.setStyleSheet("background: transparent; border: none;")
        h_layout.addWidget(logo_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_t = QLabel("معالج التنصيب الرسمي – منظومة Share COC v4.0")
        lbl_t.setFont(QFont("Cairo", 14, QFont.Weight.Bold))
        lbl_t.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        lbl_s = QLabel("غرفة تجارة كربلاء المقدسة • منظومة التبادل السحابي وأرشفة المستندات الرسمية")
        lbl_s.setFont(QFont("Segoe UI", 10))
        lbl_s.setStyleSheet("color: #ecd58a; background: transparent; border: none;")
        title_col.addWidget(lbl_t)
        title_col.addWidget(lbl_s)
        h_layout.addLayout(title_col)
        h_layout.addStretch()

        self.lbl_step_badge = QLabel("الخطوة 1 من 4")
        self.lbl_step_badge.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
        self.lbl_step_badge.setStyleSheet("""
            background: rgba(197, 155, 39, 0.25);
            color: #fef08a;
            border: 1px solid rgba(197, 155, 39, 0.6);
            border-radius: 14px;
            padding: 5px 14px;
        """)
        h_layout.addWidget(self.lbl_step_badge)
        root_layout.addWidget(header)

        # 2. صفحات المعالج (Stacked Widget)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_welcome_page())
        self.pages.addWidget(self._build_paths_page())
        self.pages.addWidget(self._build_options_page())
        self.pages.addWidget(self._build_install_page())
        root_layout.addWidget(self.pages, stretch=1)

        # 3. الشريط السفلي لأزرار التنقل (التالي / السابق / تثبيت)
        footer = QFrame()
        footer.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border-top: 1.5px solid #d5dfdb;
                padding: 12px 24px;
            }
        """)
        f_layout = QHBoxLayout(footer)

        self.btn_cancel = QPushButton("إلغاء الأمر")
        self.btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1;
                border-radius: 8px; padding: 8px 18px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #e2e8f0; }
        """)
        self.btn_cancel.clicked.connect(self.close)
        f_layout.addWidget(self.btn_cancel)

        f_layout.addStretch()

        self.btn_back = QPushButton("➡ السابق")
        self.btn_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_back.setEnabled(False)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background: #ffffff; color: #14372e; border: 1.5px solid #14372e;
                border-radius: 8px; padding: 8px 20px; font-weight: bold; font-size: 12px;
            }
            QPushButton:disabled { color: #94a3b8; border-color: #cbd5e1; }
            QPushButton:hover:enabled { background: #ecfdf5; }
        """)
        self.btn_back.clicked.connect(self._go_prev)
        f_layout.addWidget(self.btn_back)

        self.btn_next = QPushButton("التالي ⬅")
        self.btn_next.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next.setStyleSheet("""
            QPushButton {
                background: #14372e; color: #ffffff; border: none;
                border-radius: 8px; padding: 9px 26px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background: #1c4b3f; }
        """)
        self.btn_next.clicked.connect(self._go_next)
        f_layout.addWidget(self.btn_next)

        root_layout.addWidget(footer)

    def _build_welcome_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(28, 24, 28, 20)
        l.setSpacing(14)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1.5px solid #d5dfdb;
                border-radius: 14px;
                padding: 20px;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setSpacing(12)

        t = QLabel("مرحباً بك في معالج تثبيت منظومة Share COC (الإصدار المؤسسي 4.0)")
        t.setFont(QFont("Cairo", 13, QFont.Weight.Bold))
        t.setStyleSheet("color: #14372e; border: none;")
        cl.addWidget(t)

        desc = QLabel(
            "سيقوم هذا المعالج بتنصيب منظومة التبادل السحابي وأرشفة المستندات الرسمية الخاصة بغرفة تجارة كربلاء المقدسة "
            "على جهاز الحاسوب الخاص بك وفق المعايير القياسية لنظام التشغيل Windows.\n\n"
            "✨ أهم مميزات النسخة المؤسسية v4.0:\n"
            "  • مزامنة سحابية فورية ومباشرة مع Google Drive لكافة الملفات والمجلدات الفرعية.\n"
            "  • دعم كامل للملفات الكبيرة وقواعد بيانات Access (.accdb) عبر الرفع المجزأ الذكي.\n"
            "  • تكامل كامل مع نظام Windows (قائمة ابدأ، سطح المكتب، قائمة الزر الأيمن Send To، وشريط المهام System Tray).\n"
            "  • تسجيل رسمي في قائمة البرامج المثبتة في ويندوز (Add / Remove Programs) مع أداة إلغاء تثبيت آمنة."
        )
        desc.setWordWrap(True)
        desc.setFont(QFont("Segoe UI", 10))
        desc.setStyleSheet("color: #334155; line-height: 1.6; border: none;")
        cl.addWidget(desc)

        cl.addStretch()

        pub_lbl = QLabel(f"الناشر المعتمد: {APP_PUBLISHER} • الإصدار: {APP_VERSION}")
        pub_lbl.setFont(QFont("Cairo", 9, QFont.Weight.Bold))
        pub_lbl.setStyleSheet("color: #0d8a55; background: #ecfdf5; border-radius: 8px; padding: 8px; border: none;")
        cl.addWidget(pub_lbl)

        l.addWidget(card, stretch=1)
        return w

    def _build_paths_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(28, 24, 28, 20)
        l.setSpacing(14)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1.5px solid #d5dfdb;
                border-radius: 14px;
                padding: 20px;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setSpacing(14)

        t = QLabel("📂 تحديد مسارات التثبيت والمزامنة السحابية")
        t.setFont(QFont("Cairo", 13, QFont.Weight.Bold))
        t.setStyleSheet("color: #14372e; border: none;")
        cl.addWidget(t)

        # مسار التثبيت
        lbl1 = QLabel("1. مسار تثبيت ملفات البرنامج في نظام Windows:")
        lbl1.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
        lbl1.setStyleSheet("color: #1e293b; border: none;")
        cl.addWidget(lbl1)

        row1 = QHBoxLayout()
        self.txt_install_dir = QLineEdit(str(get_default_install_dir()))
        self.txt_install_dir.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 12px;")
        btn_b1 = QPushButton("استعراض...")
        btn_b1.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_b1.setStyleSheet("background: #e2e8f0; color: #0f172a; border-radius: 8px; padding: 8px 14px; font-weight: bold;")
        btn_b1.clicked.connect(self._browse_install_dir)
        row1.addWidget(self.txt_install_dir, stretch=1)
        row1.addWidget(btn_b1)
        cl.addLayout(row1)

        # مسار المزامنة
        lbl2 = QLabel("2. مجلد المستندات السحابي المشترك (تُحفظ فيه كتب ومستندات الغرفة):")
        lbl2.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
        lbl2.setStyleSheet("color: #1e293b; border: none;")
        cl.addWidget(lbl2)

        row2 = QHBoxLayout()
        self.txt_sync_dir = QLineEdit(str(get_default_sync_dir()))
        self.txt_sync_dir.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 12px;")
        btn_b2 = QPushButton("استعراض...")
        btn_b2.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_b2.setStyleSheet("background: #e2e8f0; color: #0f172a; border-radius: 8px; padding: 8px 14px; font-weight: bold;")
        btn_b2.clicked.connect(self._browse_sync_dir)
        row2.addWidget(self.txt_sync_dir, stretch=1)
        row2.addWidget(btn_b2)
        cl.addLayout(row2)

        cl.addStretch()
        l.addWidget(card, stretch=1)
        return w

    def _build_options_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(28, 24, 28, 20)
        l.setSpacing(14)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1.5px solid #d5dfdb;
                border-radius: 14px;
                padding: 20px;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setSpacing(12)

        t = QLabel("⚙️ خيارات التكامل مع نظام التشغيل Windows")
        t.setFont(QFont("Cairo", 13, QFont.Weight.Bold))
        t.setStyleSheet("color: #14372e; border: none;")
        cl.addWidget(t)

        chk_style = "color: #0f172a; font-size: 12px; font-weight: bold; spacing: 10px; border: none;"

        self.chk_opt_desktop = QCheckBox("إنشاء اختصار رسمي للتطبيق على سطح المكتب (Desktop Shortcut)")
        self.chk_opt_desktop.setChecked(True)
        self.chk_opt_desktop.setStyleSheet(chk_style)
        cl.addWidget(self.chk_opt_desktop)

        self.chk_opt_startmenu = QCheckBox("إضافة مجلد واختصارات المنظومة إلى قائمة ابدأ (Start Menu -> غرفة تجارة كربلاء المقدسة)")
        self.chk_opt_startmenu.setChecked(True)
        self.chk_opt_startmenu.setStyleSheet(chk_style)
        cl.addWidget(self.chk_opt_startmenu)

        self.chk_opt_sendto = QCheckBox("إضافة خيار الرفع السريع في قائمة الزر الأيمن للماوس (Send To -> Share COC السحابة)")
        self.chk_opt_sendto.setChecked(True)
        self.chk_opt_sendto.setStyleSheet(chk_style)
        cl.addWidget(self.chk_opt_sendto)

        self.chk_opt_autostart = QCheckBox("تشغيل المنظومة تلقائياً في الخلفية عند بدء تشغيل نظام Windows")
        self.chk_opt_autostart.setChecked(True)
        self.chk_opt_autostart.setStyleSheet(chk_style)
        cl.addWidget(self.chk_opt_autostart)

        self.chk_opt_uninstall = QCheckBox("تسجيل البرنامج رسمياً في قائمة البرامج المثبتة في ويندوز (Add / Remove Programs)")
        self.chk_opt_uninstall.setChecked(True)
        self.chk_opt_uninstall.setStyleSheet(chk_style)
        cl.addWidget(self.chk_opt_uninstall)

        cl.addStretch()
        l.addWidget(card, stretch=1)
        return w

    def _build_install_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(28, 24, 28, 20)
        l.setSpacing(14)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1.5px solid #d5dfdb;
                border-radius: 14px;
                padding: 22px;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setSpacing(16)

        self.lbl_install_title = QLabel("⏳ جاري تثبيت منظومة Share COC v4.0 على الحاسوب...")
        self.lbl_install_title.setFont(QFont("Cairo", 13, QFont.Weight.Bold))
        self.lbl_install_title.setStyleSheet("color: #14372e; border: none;")
        cl.addWidget(self.lbl_install_title)

        self.lbl_install_step = QLabel("جاري التحضير لبدء التثبيت...")
        self.lbl_install_step.setFont(QFont("Segoe UI", 10))
        self.lbl_install_step.setStyleSheet("color: #475569; border: none;")
        cl.addWidget(self.lbl_install_step)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(26)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #e2e8f0;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                text-align: center;
                font-weight: bold;
                color: #0f172a;
            }
            QProgressBar::chunk {
                background-color: #0d8a55;
                border-radius: 9px;
            }
        """)
        cl.addWidget(self.progress_bar)

        self.chk_launch_now = QCheckBox("🚀 تشغيل منظومة Share COC v4.0 فور النقر على «إنهاء»")
        self.chk_launch_now.setChecked(True)
        self.chk_launch_now.setVisible(False)
        self.chk_launch_now.setStyleSheet("color: #14372e; font-size: 12px; font-weight: bold; border: none;")
        cl.addWidget(self.chk_launch_now)

        self.chk_open_sync_folder = QCheckBox("📁 فتح المجلد السحابي المشترك (FileExchangeShared)")
        self.chk_open_sync_folder.setChecked(False)
        self.chk_open_sync_folder.setVisible(False)
        self.chk_open_sync_folder.setStyleSheet("color: #334155; font-size: 11px; font-weight: bold; border: none;")
        cl.addWidget(self.chk_open_sync_folder)

        cl.addStretch()
        l.addWidget(card, stretch=1)
        return w

    def _browse_install_dir(self):
        d = QFileDialog.getExistingDirectory(self, "اختر مجلد تثبيت البرنامج", self.txt_install_dir.text())
        if d:
            self.txt_install_dir.setText(str(Path(d) / "ShareCOC"))

    def _browse_sync_dir(self):
        d = QFileDialog.getExistingDirectory(self, "اختر مجلد المزامنة السحابية المشترك", self.txt_sync_dir.text())
        if d:
            self.txt_sync_dir.setText(str(Path(d)))

    def _go_prev(self):
        idx = self.pages.currentIndex()
        if idx > 0 and idx < 3:
            self.pages.setCurrentIndex(idx - 1)
            self._update_nav_buttons()

    def _go_next(self):
        idx = self.pages.currentIndex()
        if idx < 2:
            self.pages.setCurrentIndex(idx + 1)
            self._update_nav_buttons()
        elif idx == 2:
            self.pages.setCurrentIndex(3)
            self._update_nav_buttons()
            self._start_installation()
        elif idx == 3:
            self._finish_and_close()

    def _update_nav_buttons(self):
        idx = self.pages.currentIndex()
        self.lbl_step_badge.setText(f"الخطوة {idx + 1} من 4")
        self.btn_back.setEnabled(idx in (1, 2))
        if idx in (0, 1):
            self.btn_next.setText("التالي ⬅")
        elif idx == 2:
            self.btn_next.setText("🛠️ تثبيت المنظومة الآن")
        elif idx == 3:
            self.btn_back.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            self.btn_next.setEnabled(False)

    def _start_installation(self):
        install_dir = Path(self.txt_install_dir.text().strip())
        sync_dir = Path(self.txt_sync_dir.text().strip())
        options = {
            "desktop": self.chk_opt_desktop.isChecked(),
            "start_menu": self.chk_opt_startmenu.isChecked(),
            "sendto": self.chk_opt_sendto.isChecked(),
            "autostart": self.chk_opt_autostart.isChecked(),
            "register_uninstall": self.chk_opt_uninstall.isChecked(),
        }
        self.worker = InstallWorker(install_dir, sync_dir, options)
        self.worker.progress.connect(self._on_install_progress)
        self.worker.finished_install.connect(self._on_install_finished)
        self.worker.start()

    def _on_install_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.lbl_install_step.setText(msg)

    def _on_install_finished(self, ok: bool, msg: str, exe_path: str):
        if ok:
            self.installed_exe_path = exe_path
            self.lbl_install_title.setText("🎉 اكتمل تنصيب منظومة Share COC v4.0 بنجاح!")
            self.lbl_install_step.setText(
                "تم تثبيت البرنامج، وتسجيله رسمياً في نظام Windows، وإنشاء اختصارات سطح المكتب وقائمة ابدأ."
            )
            self.chk_launch_now.setVisible(True)
            self.chk_open_sync_folder.setVisible(True)
            self.btn_next.setText("✅ إنهاء التثبيت")
            self.btn_next.setEnabled(True)
        else:
            self.lbl_install_title.setText("❌ تعذر إكمال التثبيت")
            self.lbl_install_step.setText(msg)
            self.btn_cancel.setEnabled(True)
            QMessageBox.critical(self, "خطأ في التثبيت", msg)

    def _finish_and_close(self):
        if self.chk_open_sync_folder.isChecked():
            try:
                os.startfile(self.txt_sync_dir.text().strip())
            except Exception:
                pass
        if self.chk_launch_now.isChecked() and self.installed_exe_path and os.path.exists(self.installed_exe_path):
            try:
                subprocess.Popen([self.installed_exe_path], cwd=str(Path(self.installed_exe_path).parent))
            except Exception as e:
                print(f"[Launch error]: {e}")
        self.close()


def run_uninstaller(quiet: bool = False):
    """إلغاء تثبيت البرنامج رسمياً عند استدعائه من إعدادات ويندوز (Add/Remove Programs)"""
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    if not quiet:
        ans = QMessageBox.question(
            None,
            f"إلغاء تثبيت {APP_DISPLAY_NAME}",
            "هل أنت متأكد من رغبتك في إلغاء تثبيت برنامج Share COC من هذا الحاسوب؟\n\n"
            "💡 ملاحظة آمنة: لن يتم حذف أي مستندات أو كتب رسمية محفوظة في مجلد المزامنة (FileExchangeShared).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            sys.exit(0)

    # 1. إيقاف البرنامج إن كان يعمل
    subprocess.run(
        ["taskkill", "/F", "/IM", APP_EXE_NAME, "/T"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(0.5)

    # 2. حذف الاختصارات من سطح المكتب وقائمة ابدأ و SendTo
    for d_dir in get_desktop_dirs():
        for name in ("Share COC – غرفة تجارة كربلاء.lnk", "share coc.lnk"):
            p = d_dir / name
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    sm_dir = get_start_menu_folder()
    if sm_dir.exists():
        try:
            shutil.rmtree(str(sm_dir), ignore_errors=True)
        except Exception:
            pass

    sendto_lnk = get_sendto_folder() / "Share COC – رفع ومزامنة للسحابة.lnk"
    if sendto_lnk.exists():
        try:
            sendto_lnk.unlink()
        except Exception:
            pass

    # 3. إزالة التسجيل من سجل Windows
    unregister_from_windows()

    # 4. جدولة حذف مجلد البرنامج التنفيذي بعد إغلاق أداة الحذف
    install_dir = get_default_install_dir()
    if install_dir.exists():
        cmd = f'ping 127.0.0.1 -n 3 > nul & rmdir /s /q "{install_dir}"'
        subprocess.Popen(
            ["cmd.exe", "/c", cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    if not quiet:
        QMessageBox.information(
            None,
            "اكتمل إلغاء التثبيت",
            "✅ تم إلغاء تثبيت برنامج Share COC من نظام Windows بنجاح.\n"
            "جميع مستنداتك في مجلد FileExchangeShared محفوظة بأمان.",
        )
    sys.exit(0)


def run_silent_install():
    """تثبيت صامت وسريع (للنشر الفوري) مع كافة اختصارات وتكاملات نظام Windows"""
    install_dir = get_default_install_dir()
    sync_dir = get_default_sync_dir()
    subprocess.run(
        ["taskkill", "/F", "/IM", APP_EXE_NAME, "/T"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(0.5)
    install_dir.mkdir(parents=True, exist_ok=True)
    sync_dir.mkdir(parents=True, exist_ok=True)

    bundle_dir = _get_bundle_dir()
    payload_candidates = [
        bundle_dir / "payload" / APP_EXE_NAME,
        bundle_dir / APP_EXE_NAME,
        Path(__file__).parent.parent / "dist" / APP_EXE_NAME,
    ]
    src_exe = next((p for p in payload_candidates if p.exists()), None)
    if src_exe:
        dest_exe = install_dir / APP_EXE_NAME
        shutil.copy2(str(src_exe), str(dest_exe))
        for asset_name in ("logo.ico", "logo.png"):
            for cand in (bundle_dir / "assets" / asset_name, bundle_dir / asset_name):
                if cand.exists():
                    shutil.copy2(str(cand), str(install_dir / asset_name))
                    break
        uninstaller_dest = install_dir / UNINSTALL_EXE_NAME
        if getattr(sys, "frozen", False):
            try:
                shutil.copy2(sys.executable, str(uninstaller_dest))
            except Exception:
                pass
        setup_all_system_integrations(
            exe_path=dest_exe,
            sync_dir=sync_dir,
            icon_path=install_dir / "logo.ico",
            uninstaller_path=uninstaller_dest if uninstaller_dest.exists() else dest_exe,
        )


def main():
    if "--uninstall" in sys.argv:
        run_uninstaller(quiet="--quiet" in sys.argv)
        return
    if "--silent" in sys.argv:
        run_silent_install()
        return

    app = QApplication(sys.argv)
    app.setApplicationName("ShareCOC_Setup")
    app.setApplicationDisplayName(f"معالج تثبيت {APP_DISPLAY_NAME}")
    wiz = ShareCOCInstallerWizard()
    wiz.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
