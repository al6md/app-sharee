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
    QStackedWidget, QScrollArea, QGridLayout,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QProgressBar, QProgressDialog, QCheckBox, QComboBox, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QMetaObject, QItemSelectionModel, QThread, QSize
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap, QCursor, QTransform
from theme import (
    get_gov_stylesheet, apply_gov_shadow,
    GOV_GREEN, GOV_GOLD, TEXT_TITLE, TEXT_MUTED,
    STATUS_SYNCED, STATUS_SYNCED_BG, STATUS_SYNCED_BORDER,
    STATUS_SYNCING, STATUS_LOCKED, STATUS_LOCKED_BG, STATUS_LOCKED_BORDER
)
from icon_provider import (
    get_file_office_icon, get_file_office_pixmap, get_type_key,
    IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, ARCHIVE_EXTENSIONS
)
from office_handler import OfficeHandler
from autostart import is_windows_autostart_enabled, set_windows_autostart
from access_hub_widget import AccessHubWidget
class StatusBridge(QObject):
    sync_updated = pyqtSignal(dict)
    show_requested = pyqtSignal()
    scan_ready = pyqtSignal(dict)
    cloud_trash_ready = pyqtSignal(list)
    cloud_snapshot_ready = pyqtSignal()
    rescan_requested = pyqtSignal()
    refresh_finished = pyqtSignal()
    depts_changed = pyqtSignal()
def get_desktop_machine_guid():
    """استخراج المعرف الثابت للحاسوب من سجل الويندوز أو اسم المضيف"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        val, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(val).strip()
    except Exception:
        import socket
        return socket.gethostname()
# أقصى عمر للقطة السحابية (ثوانٍ) قبل تجديدها في الخلفية
CLOUD_SNAPSHOT_MAX_AGE = 8
def _get_snapshot_index(snap):
    """
    بناء فهرس سريع للقطة السحابية مرة واحدة فقط (يُخزن على كائن اللقطة نفسه):
    - child_dirs:  مسار المجلد الأب -> قائمة المجلدات الفرعية المباشرة
    - child_files: مسار المجلد الأب -> قائمة (المسار, البيانات) للملفات المباشرة
    - rec_files:   مسار المجلد -> عدد كل الملفات بداخله (تراكمياً)
    """
    idx = getattr(snap, '_ui_index', None)
    if idx is not None:
        return idx
    child_dirs = {}
    child_files = {}
    rec_files = {}
    for fld in snap.folders:
        if not fld:
            continue
        parent = fld.rpartition("/")[0]
        child_dirs.setdefault(parent, []).append(fld)
    for f_rel, meta in snap.files.items():
        parent = f_rel.rpartition("/")[0]
        child_files.setdefault(parent, []).append((f_rel, meta))
        p = parent
        while p:
            rec_files[p] = rec_files.get(p, 0) + 1
            p = p.rpartition("/")[0]
    idx = {'child_dirs': child_dirs, 'child_files': child_files, 'rec_files': rec_files}
    try:
        snap._ui_index = idx
    except Exception:
        pass
    return idx
class TrashBatchWorker(QThread):
    """
    عامل غير حاجز (QThread) لتفريغ سلة المحذوفات أو استعادة عناصرها بالتوازي
    دون تجميد الواجهة الرسومية، مع بث حي لنسبة الإنجاز واسم الملف الحالي.
    """
    progress_signal = pyqtSignal(int, int, int, str)  # (pct, current, total, current_name)
    finished_signal = pyqtSignal(str, int, int)       # (mode, success_count, total)
    def __init__(self, mode, items, state_mgr, sync_engine, cloud_client, sync_folder, parent=None):
        super().__init__(parent)
        self.mode = mode  # 'empty' or 'restore'
        self.items = list(items or [])
        self.state_mgr = state_mgr
        self.sync_engine = sync_engine
        self.cloud_client = cloud_client
        self.sync_folder = Path(sync_folder)
        self.is_cancelled = False
    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import hashlib
        total = len(self.items)
        if total == 0:
            self.finished_signal.emit(self.mode, 0, 0)
            return
        done_count = 0
        local_trash_ids_to_remove = []
        cloud_jobs = []
        # المرحلة 1: المعالجة المحلية السريعة جداً
        for idx, item in enumerate(self.items):
            if self.is_cancelled:
                break
            name = item.get('file_name') or 'ملف'
            tid = item.get('id')
            trash_path_str = item.get('trash_path') or ''
            orig_rel = item.get('original_rel_path') or name
            server_fid = item.get('server_file_id')
            is_cloud_only = str(tid).startswith("cloud_")
            pct = int(((idx + 1) / max(1, total)) * 45)
            self.progress_signal.emit(pct, idx + 1, total, f"محلياً: {name}")
            if self.mode == 'empty':
                if trash_path_str and not is_cloud_only:
                    tp = Path(trash_path_str)
                    if tp.exists():
                        try:
                            if tp.is_dir():
                                shutil.rmtree(str(tp), ignore_errors=True)
                            else:
                                tp.unlink()
                        except Exception:
                            pass
                if isinstance(tid, int):
                    local_trash_ids_to_remove.append(tid)
                cloud_jobs.append((name, orig_rel, server_fid, is_cloud_only))
            else:
                # restore
                if trash_path_str and not is_cloud_only:
                    tp = Path(trash_path_str)
                    target_path = (self.sync_folder / orig_rel).resolve()
                    try:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        if tp.exists():
                            shutil.move(str(tp), str(target_path))
                        if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                            self.sync_engine.clear_tombstone(orig_rel)
                        if target_path.exists() and target_path.is_file():
                            try:
                                os.utime(str(target_path), None)
                            except Exception:
                                pass
                    except Exception:
                        pass
                if isinstance(tid, int):
                    local_trash_ids_to_remove.append(tid)
                cloud_jobs.append((name, orig_rel, server_fid, is_cloud_only))
        # حذف الدفعة من قاعدة البيانات المحلية في معاملة واحدة فورية
        if local_trash_ids_to_remove and hasattr(self.state_mgr, 'remove_from_trash_batch'):
            try:
                self.state_mgr.remove_from_trash_batch(local_trash_ids_to_remove)
            except Exception:
                for tid in local_trash_ids_to_remove:
                    try:
                        self.state_mgr.remove_from_trash(tid)
                    except Exception:
                        pass
        # المرحلة 2: المعالجة السحابية المتوازية (6 خيوط متزامنة)
        if self.cloud_client and self.cloud_client.is_configured() and cloud_jobs and not self.is_cancelled:
            def _do_cloud_op(job):
                j_name, j_rel, j_fid, j_cloud_only = job
                if self.is_cancelled:
                    return j_name, False
                try:
                    if self.mode == 'empty':
                        if j_fid and hasattr(self.cloud_client, 'purge_by_id'):
                            self.cloud_client.purge_by_id(j_fid)
                        elif hasattr(self.cloud_client, 'purge_file'):
                            self.cloud_client.purge_file(j_rel, server_file_id=j_fid)
                        if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                            self.sync_engine.clear_tombstone(j_rel)
                        return j_name, True
                    else:
                        if j_fid and hasattr(self.cloud_client, 'restore_by_id'):
                            self.cloud_client.restore_by_id(j_fid)
                        return j_name, True
                except Exception:
                    return j_name, False
            completed_cloud = 0
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = [pool.submit(_do_cloud_op, j) for j in cloud_jobs]
                for fut in as_completed(futures):
                    completed_cloud += 1
                    j_name, _ = fut.result()
                    pct = 45 + int((completed_cloud / max(1, len(cloud_jobs))) * 55)
                    self.progress_signal.emit(min(99, pct), completed_cloud, total, f"سحابياً: {j_name}")
                    done_count += 1
        else:
            done_count = len(self.items)
        if self.sync_engine:
            self.sync_engine.wake(delay=0.3)
        self.progress_signal.emit(100, total, total, "✅ اكتملت العملية بنجاح!")
        self.finished_signal.emit(self.mode, done_count, total)
class ImagePreviewDialog(QDialog):
    """نافذة معاينة الصور المدمجة داخل التطبيق مع دعم التكبير والتصغير والتدوير والفتح الخارجي"""
    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.image_path = Path(image_path)
        self.zoom_factor = 1.0
        self.rotation_angle = 0
        self.orig_pixmap = QPixmap(str(self.image_path))
        self.setWindowTitle(f"🖼️ معاينة الصورة: {self.image_path.name}")
        self.resize(920, 680)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; font-family: 'Cairo', 'Segoe UI', Tahoma; }
            QLabel { color: #f8fafc; }
            QPushButton {
                background-color: #1e293b; color: #f8fafc; border: 1px solid #334155;
                border-radius: 8px; padding: 7px 14px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #334155; border-color: #64748b; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        # شريط الأدوات العلوي
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        title_lbl = QLabel(f"🖼️ {self.image_path.name}")
        title_lbl.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        toolbar.addWidget(title_lbl)
        if not self.orig_pixmap.isNull():
            try:
                sz_kb = round(self.image_path.stat().st_size / 1024, 1)
            except Exception:
                sz_kb = 0
            dim_lbl = QLabel(f"({self.orig_pixmap.width()}×{self.orig_pixmap.height()} px • {sz_kb} KB)")
            dim_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            toolbar.addWidget(dim_lbl)
        toolbar.addStretch()
        btn_zoom_in = QPushButton("➕ تكبير")
        btn_zoom_in.clicked.connect(lambda: self._adjust_zoom(1.25))
        toolbar.addWidget(btn_zoom_in)
        btn_zoom_out = QPushButton("➖ تصغير")
        btn_zoom_out.clicked.connect(lambda: self._adjust_zoom(0.8))
        toolbar.addWidget(btn_zoom_out)
        btn_fit = QPushButton("🔄 ملائمة الشاشة")
        btn_fit.clicked.connect(self._reset_view)
        toolbar.addWidget(btn_fit)
        btn_rot = QPushButton("↪️ تدوير 90°")
        btn_rot.clicked.connect(self._rotate_90)
        toolbar.addWidget(btn_rot)
        btn_ext = QPushButton("🖥️ فتح في عارض ويندوز")
        btn_ext.setStyleSheet("background-color: #14372e; border-color: #c59b27; color: #ffffff;")
        btn_ext.clicked.connect(lambda: OfficeHandler.open_native_file(str(self.image_path)))
        toolbar.addWidget(btn_ext)
        btn_close = QPushButton("✖ إغلاق")
        btn_close.setStyleSheet("background-color: #7f1d1d; border-color: #991b1b; color: #ffffff;")
        btn_close.clicked.connect(self.accept)
        toolbar.addWidget(btn_close)
        layout.addLayout(toolbar)
        # منطقة عرض الصورة
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background-color: #090d16; border: 1px solid #1e293b; border-radius: 10px; }")
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background: transparent; padding: 12px;")
        self.scroll.setWidget(self.img_label)
        layout.addWidget(self.scroll, stretch=1)
        self._update_pixmap()
    def _adjust_zoom(self, factor):
        self.zoom_factor = max(0.15, min(5.0, self.zoom_factor * factor))
        self._update_pixmap()
    def _reset_view(self):
        self.zoom_factor = 1.0
        self.rotation_angle = 0
        self._update_pixmap()
    def _rotate_90(self):
        self.rotation_angle = (self.rotation_angle + 90) % 360
        self._update_pixmap()
    def _update_pixmap(self):
        if self.orig_pixmap.isNull():
            self.img_label.setText("⚠️ تعذر قراءة ملف الصورة.")
            return
        pm = self.orig_pixmap
        if self.rotation_angle:
            tr = QTransform().rotate(self.rotation_angle)
            pm = pm.transformed(tr, Qt.TransformationMode.SmoothTransformation)
        target_w = max(50, int(min(pm.width(), 840) * self.zoom_factor))
        target_h = max(50, int(min(pm.height(), 560) * self.zoom_factor))
        scaled = pm.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.img_label.setPixmap(scaled)
class CloudUploadWorker(QThread):
    """
    عامل رفع ومزامنة سحابي يعمل في خيط مستقل (QThread) لمنع أي تجميد للواجهة،
    ينسخ المستندات محلياً ثم يرفعها مباشرة إلى Google Drive على دفعات (Chunks)
    مع بث نسبة التقدم الفعلية وحفظ معرف السحابة في قاعدة البيانات فوراً.
    """
    progress_signal = pyqtSignal(int, str)
    local_copy_done = pyqtSignal()
    finished_signal = pyqtSignal(int, int, int, list)  # (local_ok, cloud_ok, total, failed_names)
    def __init__(self, tasks, folders_to_create, sync_engine, cloud_client, state_mgr, sync_folder, parent=None):
        super().__init__(parent)
        self.tasks = tasks or []  # list of (Path(src), Path(dest), rel_path_str)
        self.folders_to_create = folders_to_create or []  # list of rel_folder_str
        self.sync_engine = sync_engine
        self.cloud_client = cloud_client
        self.state_mgr = state_mgr
        self.sync_folder = Path(sync_folder)
        self.is_cancelled = False
    def run(self):
        total = len(self.tasks)
        local_ok = 0
        cloud_ok = 0
        failed_names = []
        # 1. تجهيز المجلدات محلياً وإزالة أي علامات حذف سابقة (Tombstones)
        for rel_folder in self.folders_to_create:
            try:
                if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                    self.sync_engine.clear_tombstone(rel_folder)
                (self.sync_folder / rel_folder).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        # 2. نسخ الملفات إلى مجلد المزامنة المحلي وتحديث توقيتها الزمني (mtime = الآن)
        prepared_tasks = []
        for idx, (src_path, dest_path, rel_path) in enumerate(self.tasks):
            if self.is_cancelled:
                break
            try:
                if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                    self.sync_engine.clear_tombstone(rel_path)
                if self.sync_engine and hasattr(self.sync_engine, 'clear_self_op'):
                    self.sync_engine.clear_self_op(rel_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                pct = int((idx / max(1, total)) * 8)
                self.progress_signal.emit(pct, f"📥 جاري تجهيز ونسخ ({idx + 1} من {total}):\n{dest_path.name}")
                if src_path.resolve() != dest_path.resolve():
                    shutil.copy2(str(src_path), str(dest_path))
                # تحديث وقت التعديل إلى اللحظة الحالية لضمان تفوق النسخة الجديدة دائماً
                try:
                    os.utime(str(dest_path), None)
                except Exception:
                    pass
                f_size = dest_path.stat().st_size
                self.state_mgr.set_file_state(rel_path, dest_path.name, "", f_size, 'syncing')
                prepared_tasks.append((dest_path, rel_path, f_size))
                local_ok += 1
            except Exception as e:
                failed_names.append(f"{dest_path.name} ({e})")
        self.local_copy_done.emit()
        # 3. إنشاء المجلدات السحابية أولاً في Google Drive
        if self.cloud_client and self.cloud_client.is_configured():
            for rel_folder in self.folders_to_create:
                if self.is_cancelled:
                    break
                try:
                    self.progress_signal.emit(8, f"☁️ جاري تأكيد المجلد في السحابة:\n{rel_folder}")
                    self.cloud_client.ensure_folder(rel_folder)
                except Exception:
                    pass
        # 4. رفع الملفات مباشرة إلى Google Drive بأقصى سرعة تدفق (Streaming)
        prepared_tasks.sort(key=lambda item: item[2])
        total_bytes_all = sum(max(1, item[2]) for item in prepared_tasks)
        uploaded_bytes_so_far = 0
        for idx, (dest_path, rel_path, f_size) in enumerate(prepared_tasks):
            if self.is_cancelled:
                break
            file_label = f"☁️ جاري الرفع للسحابة ({idx + 1} من {len(prepared_tasks)}):\n{dest_path.name}"
            base_bytes = uploaded_bytes_so_far
            start_t = time.monotonic()
            speed_state = {'last_t': start_t, 'last_b': 0, 'ema_bps': 0.0}
            def on_chunk_progress(up_b, tot_b, _base=base_bytes, _f_label=file_label, _st=speed_state, _t0=start_t):
                now_t = time.monotonic()
                dt = now_t - _st['last_t']
                db = max(0, up_b - _st['last_b'])
                if dt >= 0.08 and db > 0:
                    inst_bps = db / dt
                    if _st['ema_bps'] <= 0:
                        _st['ema_bps'] = inst_bps
                    else:
                        _st['ema_bps'] = 0.35 * inst_bps + 0.65 * _st['ema_bps']
                    _st['last_t'] = now_t
                    _st['last_b'] = up_b
                avg_bps = _st['ema_bps'] if _st['ema_bps'] > 0 else (up_b / max(0.1, now_t - _t0))
                speed_str = ""
                eta_str = ""
                if up_b > 0 and avg_bps > 1024:
                    if avg_bps >= 1048576:
                        speed_str = f" • ⚡ {avg_bps / 1048576:.1f} MB/s"
                    else:
                        speed_str = f" • ⚡ {int(avg_bps / 1024)} KB/s"
                    rem_b = max(0, tot_b - up_b)
                    rem_sec = int(rem_b / max(1.0, avg_bps))
                    if rem_sec >= 60:
                        eta_str = f" • متبقي {rem_sec // 60}د {rem_sec % 60}ث"
                    elif rem_sec > 0:
                        eta_str = f" • متبقي {rem_sec}ث"
                cur_total_up = _base + up_b
                overall_pct = int(min(99, (cur_total_up * 100) / max(1, total_bytes_all)))
                file_pct = int(min(100, (up_b * 100) / max(1, tot_b)))
                if tot_b >= 1048576:
                    mb_up = up_b / 1048576
                    mb_tot = max(1, tot_b) / 1048576
                    detail = f"{_f_label}\n({mb_up:.1f} MB / {mb_tot:.1f} MB — {file_pct}%{speed_str}{eta_str})"
                else:
                    kb_up = max(1, int(up_b / 1024))
                    kb_tot = max(1, int(tot_b / 1024))
                    detail = f"{_f_label}\n({kb_up} KB / {kb_tot} KB — {file_pct}%{speed_str})"
                self.progress_signal.emit(overall_pct, detail)
            on_chunk_progress(0, max(1, f_size))
            ok = False
            cloud_fid = None
            if self.sync_engine and hasattr(self.sync_engine, 'sync_file_now'):
                ok, cloud_fid = self.sync_engine.sync_file_now(
                    dest_path,
                    rel_path=rel_path,
                    progress_callback=on_chunk_progress
                )
            elif self.cloud_client and self.cloud_client.is_configured():
                ok, cloud_fid = self.cloud_client.upload_file(
                    str(dest_path),
                    dest_path.name,
                    storage_path=rel_path,
                    progress_callback=on_chunk_progress
                )
                if ok:
                    try:
                        import hashlib
                        md5 = hashlib.md5()
                        with open(dest_path, 'rb') as f_in:
                            while chunk := f_in.read(1024 * 1024):
                                md5.update(chunk)
                        digest = md5.hexdigest()
                        st_now = dest_path.stat()
                        self.state_mgr.set_file_state(
                            rel_path,
                            dest_path.name,
                            digest,
                            st_now.st_size,
                            'synced',
                            local_mtime=st_now.st_mtime,
                            remote_md5=digest,
                            server_file_id=cloud_fid if isinstance(cloud_fid, str) else None,
                        )
                    except Exception:
                        pass
            uploaded_bytes_so_far += max(1, f_size)
            if ok:
                cloud_ok += 1
            else:
                failed_names.append(dest_path.name)
        self.progress_signal.emit(100, "✅ اكتملت المزامنة السحابية!")
        self.finished_signal.emit(local_ok, cloud_ok, total, failed_names)
def format_arabic_datetime(dt_str_or_ts):
    """تحويل تأريخ التعديل لصيغة عربية متطابقة 100% مع واجهة الويب: 9 تشرين الثاني، 11:17 ص"""
    if not dt_str_or_ts:
        return "متزامن"
    try:
        from datetime import datetime
        if isinstance(dt_str_or_ts, (int, float)):
            dt = datetime.fromtimestamp(dt_str_or_ts)
        elif isinstance(dt_str_or_ts, str):
            clean = dt_str_or_ts.replace('T', ' ').split('.')[0].strip()
            if len(clean) >= 19:
                dt = datetime.strptime(clean[:19], "%Y-%m-%d %H:%M:%S")
            elif len(clean) >= 16:
                dt = datetime.strptime(clean[:16], "%Y-%m-%d %H:%M")
            elif len(clean) >= 10:
                dt = datetime.strptime(clean[:10], "%Y-%m-%d")
            else:
                return dt_str_or_ts
        else:
            return str(dt_str_or_ts)
        arabic_months = [
            "", "كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
            "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"
        ]
        m_name = arabic_months[dt.month] if 1 <= dt.month <= 12 else str(dt.month)
        hour = dt.hour
        period = "ص" if hour < 12 else "م"
        h12 = hour % 12
        if h12 == 0:
            h12 = 12
        return f"{dt.day} {m_name}، {h12:02d}:{dt.minute:02d} {period}"
    except Exception:
        return str(dt_str_or_ts)[:16]
_FOLDER_BADGE_CACHE = {}

def create_folder_badge_pixmap(size=38):
    """رسم أيقونة مجلد زمردية واضحة مطابقة 100% لأيقونة المجلد في منصة الويب"""
    if size in _FOLDER_BADGE_CACHE:
        return _FOLDER_BADGE_CACHE[size]
    from PyQt6.QtGui import QPainter, QPainterPath, QPen, QBrush
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # الخلفية الزمردية الفاتحة (#ECFDF5) مع إطار (#D1FAE5)
    bg_path = QPainterPath()
    bg_path.addRoundedRect(0.5, 0.5, size - 1.0, size - 1.0, 10.0, 10.0)
    p.fillPath(bg_path, QColor("#ECFDF5"))
    p.setPen(QPen(QColor("#D1FAE5"), 1.2))
    p.drawPath(bg_path)
    # رسم مجلد أنيق في المنتصف باللون الأخضر الرسمي (#14372e)
    w = size * 0.50
    h = size * 0.40
    x = (size - w) / 2.0
    y = (size - h) / 2.0 + 1.0
    fld = QPainterPath()
    fld.moveTo(x, y + 3.0)
    fld.quadTo(x, y, x + 3.0, y)
    fld.lineTo(x + w * 0.38, y)
    fld.lineTo(x + w * 0.48, y + 3.2)
    fld.lineTo(x + w - 3.0, y + 3.2)
    fld.quadTo(x + w, y + 3.2, x + w, y + 6.0)
    fld.lineTo(x + w, y + h - 3.0)
    fld.quadTo(x + w, y + h, x + w - 3.0, y + h)
    fld.lineTo(x + 3.0, y + h)
    fld.quadTo(x, y + h, x, y + h - 3.0)
    fld.closeSubpath()
    fill_c = QColor("#14372e")
    fill_c.setAlpha(38)
    p.fillPath(fld, fill_c)
    pen = QPen(QColor("#14372e"), 1.7)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPath(fld)
    p.end()
    _FOLDER_BADGE_CACHE[size] = pix
    return pix


class WebFolderCard(QFrame):
    """بطاقة مجلد فرعي أو قسم رئيسي مطابقة 100% لواجهة الويب في كافة المستندات والأقسام"""
    def __init__(self, folder_data, main_window):
        super().__init__()
        self.folder_data = folder_data
        self.main_window = main_window
        self.name = folder_data.get('name') or folder_data.get('file_name', '')
        self.rel_path = folder_data.get('relative_path') or self.name
        self.item_count = folder_data.get('item_count', 0)
        self.child_count = folder_data.get('child_count', 0)
        self.is_dept = folder_data.get('is_dept', False)
        self.setObjectName("webFolderCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumWidth(210)
        self.setFixedHeight(86)
        is_sel = self.rel_path in getattr(self.main_window, 'selected_rel_paths', set())
        self._apply_card_style(is_sel)
        self._init_ui()

    def _apply_card_style(self, selected=False):
        if selected:
            self.setStyleSheet("""
                QFrame#webFolderCard {
                    background-color: #F2F9F6;
                    border: 1.5px solid #14372e;
                    border-radius: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#webFolderCard {
                    background-color: #FFFFFF;
                    border: 1px solid #E4E7EC;
                    border-radius: 12px;
                }
                QFrame#webFolderCard:hover {
                    border: 1.5px solid #14372e;
                    background-color: #FDFEFE;
                }
            """)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 8)
        layout.setSpacing(5)
        # 1. الصف العلوي: Checkbox + الأيقونة الزمردية + الاسم الكامل بالخط العريض
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        self.chk = QCheckBox()
        self.chk.setChecked(self.rel_path in getattr(self.main_window, 'selected_rel_paths', set()))
        self.chk.toggled.connect(self._on_chk_toggled)
        top_row.addWidget(self.chk)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setPixmap(create_folder_badge_pixmap(36))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        top_row.addWidget(icon_lbl)

        lbl_name = QLabel(self.name)
        lbl_name.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_name.setStyleSheet("color: #1B1F24; background: transparent; border: none;")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_name.setWordWrap(True)
        lbl_name.setToolTip(self.name)
        top_row.addWidget(lbl_name, stretch=1)
        layout.addLayout(top_row)

        # خط فاصل خفيف ناعم مطابق لمنصة الويب
        card_sep = QFrame()
        card_sep.setFrameShape(QFrame.Shape.HLine)
        card_sep.setFrameShadow(QFrame.Shadow.Plain)
        card_sep.setStyleSheet("background-color: #EEF0F3; max-height: 1px; border: none;")
        layout.addWidget(card_sep)

        # 2. الصف السفلي: عدد الملفات والمجلدات الفرعية يميناً + أزرار الإجراءات يساراً
        bot_row = QHBoxLayout()
        bot_row.setContentsMargins(0, 0, 0, 0)
        bot_row.setSpacing(4)

        lbl_files = QLabel(f"{self.item_count} ملف")
        lbl_files.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        lbl_files.setStyleSheet("color: #667085; background: transparent; border: none;")
        bot_row.addWidget(lbl_files)

        if self.child_count > 0:
            lbl_dot = QLabel("•")
            lbl_dot.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            lbl_dot.setStyleSheet("color: #667085; background: transparent; border: none;")
            bot_row.addWidget(lbl_dot)

            lbl_sub = QLabel(f"{self.child_count} فرعي")
            lbl_sub.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            lbl_sub.setStyleSheet("color: #14372e; background: transparent; border: none;")
            bot_row.addWidget(lbl_sub)

        bot_row.addStretch()

        act_btn_base = """
            QPushButton {
                border: none; background: transparent; color: #667085;
                border-radius: 5px; font-size: 12px; font-weight: bold;
            }
        """
        btn_move = QPushButton("✥")
        btn_move.setToolTip("نقل المجلد")
        btn_move.setFixedSize(22, 22)
        btn_move.setStyleSheet(act_btn_base + "QPushButton:hover { background-color: #F2F4F7; color: #1B1F24; }")
        btn_move.clicked.connect(lambda: self.main_window._show_move_items_dialog([{"name": self.name, "rel_path": self.rel_path, "is_folder": True}]))
        bot_row.addWidget(btn_move)

        btn_rename = QPushButton("✎")
        btn_rename.setToolTip("إعادة تسمية المجلد")
        btn_rename.setFixedSize(22, 22)
        btn_rename.setStyleSheet(act_btn_base + "QPushButton:hover { background-color: #ECFDF5; color: #14372e; }")
        btn_rename.clicked.connect(lambda: self.main_window._rename_folder(self.name))
        bot_row.addWidget(btn_rename)

        btn_del = QPushButton("🗑")
        btn_del.setToolTip("نقل للمحذوفات")
        btn_del.setFixedSize(22, 22)
        btn_del.setStyleSheet(act_btn_base + "QPushButton:hover { background-color: #FEF3F2; color: #F04438; }")
        btn_del.clicked.connect(lambda: self.main_window._move_folder_to_trash(self.name, rel_path=self.rel_path))
        bot_row.addWidget(btn_del)

        layout.addLayout(bot_row)

    def _on_chk_toggled(self, checked):
        self._apply_card_style(checked)
        self.main_window._toggle_item_selected(self.rel_path, checked)

    def mousePressEvent(self, event):
        child = self.childAt(event.pos())
        if isinstance(child, QPushButton) or isinstance(child, QCheckBox):
            super().mousePressEvent(event)
            return
        if self.is_dept:
            self.main_window._on_department_clicked(self.name)
        else:
            self.main_window._navigate_into_folder(self.name, self.rel_path)

    def mouseDoubleClickEvent(self, event):
        if self.is_dept:
            self.main_window._on_department_clicked(self.name)
        else:
            self.main_window._navigate_into_folder(self.name, self.rel_path)


class GovFileCard(QFrame):
    """بطاقة المستند لنمط شبكة البطاقات (Grid View) مطابقة 100% لمنصة الويب ومنظمة في 4 صفوف رأسية"""
    def __init__(self, file_data, main_window):
        super().__init__()
        self.file_data = file_data
        self.main_window = main_window
        self.file_name = file_data.get('file_name', '')
        self.rel_path = file_data.get('relative_path') or self.file_name
        self.is_folder = file_data.get('is_folder', False)
        self.abs_path = file_data.get('abs_path')
        self.setObjectName("govCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumWidth(235)
        self.setFixedHeight(194)
        is_sel = self.rel_path in getattr(self.main_window, 'selected_rel_paths', set())
        self._apply_style(is_sel)
        self._init_ui()

    def _apply_style(self, selected=False):
        if selected:
            self.setStyleSheet("""
                QFrame#govCard {
                    background-color: #F2F9F6;
                    border: 1.5px solid #14372e;
                    border-radius: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#govCard {
                    background-color: #FFFFFF;
                    border: 1px solid #E4E7EC;
                    border-radius: 12px;
                }
                QFrame#govCard:hover {
                    border: 1.5px solid #14372e;
                    background-color: #FFFFFF;
                }
            """)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(6)

        # 1. الصف العلوي: (التحديد + أيقونة الملف) يميناً | (شارة النوع + شارة المزامنة) يساراً
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.chk_select = QCheckBox()
        self.chk_select.setChecked(self.rel_path in getattr(self.main_window, 'selected_rel_paths', set()))
        self.chk_select.setToolTip("تحديد للنقل أو الحذف الجماعي")
        self.chk_select.toggled.connect(self._on_chk_toggled)
        top_row.addWidget(self.chk_select)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(38, 38)
        pix = get_file_office_pixmap(self.file_name, size=38, is_folder=self.is_folder, abs_path=self.abs_path)
        icon_lbl.setPixmap(pix)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        top_row.addWidget(icon_lbl)

        top_row.addStretch()

        tkey = get_type_key(self.file_name, is_folder=self.is_folder)
        type_labels = {
            'word': ("Word", "background: #EFF4FF; color: #2B579A; border: 1px solid #D1E0FF;"),
            'excel': ("Excel", "background: #ECFDF3; color: #217346; border: 1px solid #ABEFC6;"),
            'access': ("Access", "background: #FEF3F2; color: #A4373A; border: 1px solid #FECDCA;"),
            'pdf': ("PDF", "background: #FEF3F2; color: #E5252A; border: 1px solid #FECDCA;"),
            'image': ("صورة", "background: #F4F3FF; color: #7C3AED; border: 1px solid #D9D6FE;"),
            'video': ("فيديو", "background: #EEF4FF; color: #4F46E5; border: 1px solid #C7D7FE;"),
            'audio': ("صوت", "background: #FDF2FA; color: #DB2777; border: 1px solid #FCCEEE;"),
            'archive': ("أرشيف", "background: #FFFAEB; color: #D97706; border: 1px solid #FEDF89;"),
        }
        app_text, badge_style = type_labels.get(
            tkey, ("ملف", "background: #F7F8FA; color: #475467; border: 1px solid #E4E7EC;")
        )

        status = self.file_data.get('sync_status', 'synced')
        status_map = {
            'synced': ('• متزامن', 'background: #ECFDF3; color: #065F46; border: 1px solid #A6F4C5;'),
            'cloud_only': ('• سحابي', 'background: #EFF4FF; color: #1E40AF; border: 1px solid #D1E0FF;'),
            'syncing': ('• قيد الرفع', 'background: #FFFAEB; color: #B54708; border: 1px solid #FEDF89;'),
            'pending_upload': ('• بالانتظار', 'background: #F7F8FA; color: #667085; border: 1px solid #E4E7EC;'),
            'locked': ('• قيد التعديل', 'background: #FEF3F2; color: #F04438; border: 1px solid #FECDCA;')
        }
        status_text, status_style = status_map.get(
            status, ('• متزامن', 'background: #ECFDF3; color: #065F46; border: 1px solid #A6F4C5;')
        )

        type_lbl = QLabel(app_text)
        type_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        type_lbl.setStyleSheet(f"{badge_style} border-radius: 6px; padding: 2px 7px;")
        top_row.addWidget(type_lbl)

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        status_lbl.setStyleSheet(f"{status_style} border-radius: 9px; padding: 2px 8px;")
        top_row.addWidget(status_lbl)

        layout.addLayout(top_row)

        # 2. اسم المستند الكامل (يلتف تلقائياً بدون أي اقتطاع) + مسار القسم/المجلد
        name_lbl = QLabel(self.file_name)
        name_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #1B1F24; background: transparent; border: none;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        name_lbl.setWordWrap(True)
        name_lbl.setToolTip(self.file_name)
        name_lbl.setMinimumHeight(34)
        name_lbl.setMaximumHeight(42)
        layout.addWidget(name_lbl)

        if "/" in self.rel_path:
            folder_label = self.rel_path.rsplit("/", 1)[0]
        elif getattr(self.main_window, 'active_dept_name', None):
            folder_label = self.main_window.active_dept_name
        else:
            folder_label = "كافة الأقسام"

        dept_lbl = QLabel(f"📁 {folder_label}")
        dept_lbl.setFont(QFont("Segoe UI", 8))
        dept_lbl.setStyleSheet("color: #667085; background: transparent; border: none;")
        dept_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(dept_lbl)

        # خط فاصل ناعم
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet("background-color: #EEF0F3; max-height: 1px; border: none;")
        layout.addWidget(sep)

        # 3. صف الحجم والتاريخ بشكل مستقل ومنظم
        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        size_bytes = self.file_data.get('file_size', 0)
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1048576:
            size_str = f"{round(size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(size_bytes / 1048576, 2)} MB"

        date_raw = self.file_data.get('last_modified_local', '')
        date_str = format_arabic_datetime(date_raw)

        lbl_size = QLabel(size_str)
        lbl_size.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        lbl_size.setStyleSheet("color: #475467; background: transparent; border: none;")
        info_row.addWidget(lbl_size)
        info_row.addStretch()

        lbl_date = QLabel(date_str)
        lbl_date.setFont(QFont("Segoe UI", 8))
        lbl_date.setStyleSheet("color: #667085; background: transparent; border: none;")
        info_row.addWidget(lbl_date)
        layout.addLayout(info_row)

        # 4. شريط أزرار الإجراءات المستقل (زر فتح رئيسي عريض + أزرار أيقونات مربعة)
        act_row = QHBoxLayout()
        act_row.setContentsMargins(0, 2, 0, 0)
        act_row.setSpacing(5)

        open_labels = {
            'word': 'فتح Word',
            'excel': 'فتح Excel',
            'access': 'فتح Access',
            'pdf': 'فتح PDF',
            'image': 'معاينة الصورة',
        }
        action_btn_text = open_labels.get(tkey, "فتح المستند")

        btn_action = QPushButton(action_btn_text)
        btn_action.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_action.setFixedHeight(28)
        btn_action.setStyleSheet("""
            QPushButton {
                background-color: #14372e; color: #FFFFFF; border: none;
                border-radius: 7px; padding: 3px 10px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #1b493d; }
        """)
        btn_action.clicked.connect(lambda: self.main_window._open_file_by_name(self.file_name, self.rel_path))
        act_row.addWidget(btn_action, stretch=1)

        sq_btn_style = """
            QPushButton {
                border: 1px solid #E4E7EC; background: #F9FAFB; color: #475467;
                border-radius: 7px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #ECFDF5; color: #14372e; border-color: #A7F3D0; }
        """
        btn_rename = QPushButton("✎")
        btn_rename.setToolTip("إعادة تسمية")
        btn_rename.setFixedSize(28, 28)
        btn_rename.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_rename.setStyleSheet(sq_btn_style)
        btn_rename.clicked.connect(lambda: self.main_window._rename_file(self.file_name, self.rel_path))
        act_row.addWidget(btn_rename)

        btn_move = QPushButton("✥")
        btn_move.setToolTip("نقل المستند")
        btn_move.setFixedSize(28, 28)
        btn_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_move.setStyleSheet(sq_btn_style)
        btn_move.clicked.connect(lambda: self.main_window._show_move_items_dialog([
            {"name": self.file_name, "rel_path": self.rel_path, "is_folder": False}
        ]))
        act_row.addWidget(btn_move)

        btn_delete = QPushButton("🗑")
        btn_delete.setToolTip("نقل إلى سلة المحذوفات")
        btn_delete.setFixedSize(28, 28)
        btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_delete.setStyleSheet("""
            QPushButton {
                border: 1px solid #FECDCA; background: #FEF3F2; color: #F04438;
                border-radius: 7px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #FEE4E2; border-color: #FDA29B; }
        """)
        btn_delete.clicked.connect(lambda: self.main_window._move_file_to_trash(self.file_name, self.rel_path))
        act_row.addWidget(btn_delete)

        layout.addLayout(act_row)

    def _on_chk_toggled(self, checked):
        self._apply_style(checked)
        self.main_window._toggle_item_selected(self.rel_path, checked)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_folder:
                self.main_window._navigate_into_folder(self.file_name, self.rel_path)
            else:
                self.main_window._open_file_by_name(self.file_name, self.rel_path)

    def contextMenuEvent(self, event):
        if self.is_folder:
            self.main_window._show_context_menu_for_folder(self.file_name, event.globalPos(), self.rel_path)
        else:
            self.main_window._show_context_menu_for_file(self.file_name, event.globalPos(), self.rel_path)

class GovCompactTile(QFrame):
    """البلاطة الأفقية المدمجة لنمط القائمة المدمجة (Compact View)"""
    def __init__(self, file_data, main_window):
        super().__init__()
        self.file_data = file_data
        self.main_window = main_window
        self.file_name = file_data.get('file_name', '')
        self.rel_path = file_data.get('relative_path') or self.file_name
        self.is_folder = file_data.get('is_folder', False)
        self.abs_path = file_data.get('abs_path')
        self.setObjectName("govCompactTile")
        self.setMinimumHeight(58)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._init_ui()
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        self.chk_select = QCheckBox()
        self.chk_select.setChecked(self.rel_path in getattr(self.main_window, 'selected_rel_paths', set()))
        self.chk_select.setToolTip("تحديد للنقل أو الحذف الجماعي")
        self.chk_select.toggled.connect(lambda checked: self.main_window._toggle_item_selected(self.rel_path, checked))
        layout.addWidget(self.chk_select)
        icon_lbl = QLabel()
        pix = get_file_office_pixmap(self.file_name, size=36, is_folder=self.is_folder, abs_path=self.abs_path)
        icon_lbl.setPixmap(pix)
        layout.addWidget(icon_lbl)
        name_lbl = QLabel(self.file_name)
        name_lbl.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.DemiBold))
        name_lbl.setStyleSheet("color: #1B1F24;")
        name_lbl.setWordWrap(True)
        name_lbl.setToolTip(self.file_name)
        layout.addWidget(name_lbl, stretch=3)
        if self.is_folder:
            type_lbl = QLabel("مجلد")
            type_lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            type_lbl.setStyleSheet("background: #EDF5F2; color: #14372e; border: 1px solid #CBE3DA; border-radius: 4px; padding: 2px 8px;")
            layout.addWidget(type_lbl)
            info_lbl = QLabel(f"{self.file_data.get('item_count', 0)} عنصر")
            info_lbl.setFont(QFont("Segoe UI", 9))
            info_lbl.setStyleSheet("color: #667085;")
            layout.addWidget(info_lbl)
            btn_action = QPushButton("فتح")
            btn_action.setObjectName("btnTileOpen")
            btn_action.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_action.clicked.connect(lambda: self.main_window._navigate_into_folder(self.file_name, self.rel_path))
            layout.addWidget(btn_action)
            btn_move = QPushButton("نقل")
            btn_move.setObjectName("btnTileRename")
            btn_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_move.setToolTip("نقل المجلد إلى قسم أو مجلد آخر")
            btn_move.clicked.connect(lambda: self.main_window._show_move_items_dialog([
                {"name": self.file_name, "rel_path": self.rel_path, "is_folder": True}
            ]))
            layout.addWidget(btn_move)
            btn_rename = QPushButton("تسمية")
            btn_rename.setObjectName("btnTileRename")
            btn_rename.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_rename.setToolTip("تعديل اسم المجلد")
            btn_rename.clicked.connect(lambda: self.main_window._rename_folder(self.file_name))
            layout.addWidget(btn_rename)
            btn_del = QPushButton("حذف")
            btn_del.setObjectName("btnTileDelete")
            btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_del.setToolTip("نقل المجلد إلى سلة المحذوفات")
            btn_del.clicked.connect(lambda: self.main_window._move_folder_to_trash(self.file_name))
            layout.addWidget(btn_del)
        else:
            tkey = get_type_key(self.file_name, is_folder=False)
            type_labels = {
                'word': ("Word", "background: #EFF4FF; color: #2B579A; border: 1px solid #D1E0FF;"),
                'excel': ("Excel", "background: #ECFDF3; color: #217346; border: 1px solid #ABEFC6;"),
                'access': ("Access", "background: #FEF3F2; color: #A4373A; border: 1px solid #FECDCA;"),
                'pdf': ("PDF", "background: #FEF3F2; color: #E5252A; border: 1px solid #FECDCA;"),
                'image': ("صورة", "background: #F4F3FF; color: #7C3AED; border: 1px solid #D9D6FE;"),
                'video': ("فيديو", "background: #EEF4FF; color: #4F46E5; border: 1px solid #C7D7FE;"),
                'audio': ("صوت", "background: #FDF2FA; color: #DB2777; border: 1px solid #FCCEEE;"),
                'archive': ("أرشيف", "background: #FFFAEB; color: #D97706; border: 1px solid #FEDF89;"),
            }
            app_text, badge_style = type_labels.get(
                tkey, ("مستند", "background: #F7F8FA; color: #475467; border: 1px solid #E4E7EC;")
            )
            type_lbl = QLabel(app_text)
            type_lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            type_lbl.setStyleSheet(f"{badge_style} border-radius: 4px; padding: 2px 8px;")
            layout.addWidget(type_lbl)
            date_raw = self.file_data.get('last_modified_local', '')
            date_str = date_raw[:16].replace('T', ' ') if date_raw else "محفوظ"
            date_lbl = QLabel(date_str)
            date_lbl.setFont(QFont("Segoe UI", 9))
            date_lbl.setStyleSheet("color: #667085;")
            layout.addWidget(date_lbl)
            size_bytes = self.file_data.get('file_size', 0)
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1048576:
                size_str = f"{round(size_bytes / 1024, 1)} KB"
            else:
                size_str = f"{round(size_bytes / 1048576, 2)} MB"
            size_lbl = QLabel(size_str)
            size_lbl.setFont(QFont("Segoe UI", 9))
            size_lbl.setStyleSheet("color: #667085;")
            layout.addWidget(size_lbl)
            status = self.file_data.get('sync_status', 'synced')
            status_map = {
                'synced': ('● متزامن', 'background: #EDF5F2; color: #14372e; border: 1px solid #CBE3DA;'),
                'cloud_only': ('● سحابي', 'background: #EFF4FF; color: #2B579A; border: 1px solid #D1E0FF;'),
                'syncing': ('● قيد الرفع...', 'background: #FFFAEB; color: #B54708; border: 1px solid #FEDF89;'),
                'pending_upload': ('● بالانتظار', 'background: #F7F8FA; color: #667085; border: 1px solid #E4E7EC;'),
                'conflict': ('● تعارض', 'background: #FFFAEB; color: #B54708; border: 1px solid #FEDF89;'),
                'failed': ('● خطأ', 'background: #FEF3F2; color: #F04438; border: 1px solid #FECDCA;'),
                'locked': ('● قيد التعديل', 'background: #FEF3F2; color: #F04438; border: 1px solid #FECDCA;')
            }
            status_text, status_style = status_map.get(
                status, ('● متزامن', 'background: #EDF5F2; color: #14372e; border: 1px solid #CBE3DA;')
            )
            status_lbl = QLabel(status_text)
            status_lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.DemiBold))
            status_lbl.setStyleSheet(f"{status_style} border-radius: 4px; padding: 2px 8px;")
            layout.addWidget(status_lbl)
            btn_action = QPushButton("معاينة" if tkey == 'image' else "فتح")
            btn_action.setObjectName("btnTileOpen")
            btn_action.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_action.clicked.connect(lambda: self.main_window._open_file_by_name(self.file_name, self.rel_path))
            layout.addWidget(btn_action)
            btn_move = QPushButton("نقل")
            btn_move.setObjectName("btnTileRename")
            btn_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_move.setToolTip("نقل المستند إلى قسم أو مجلد آخر")
            btn_move.clicked.connect(lambda: self.main_window._show_move_items_dialog([
                {"name": self.file_name, "rel_path": self.rel_path, "is_folder": False}
            ]))
            layout.addWidget(btn_move)
            btn_rename = QPushButton("تسمية")
            btn_rename.setObjectName("btnTileRename")
            btn_rename.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_rename.setToolTip("تعديل اسم المستند")
            btn_rename.clicked.connect(lambda: self.main_window._rename_file(self.file_name, self.rel_path))
            layout.addWidget(btn_rename)
            btn_del = QPushButton("حذف")
            btn_del.setObjectName("btnTileDelete")
            btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_del.setToolTip("نقل المستند إلى سلة المحذوفات")
            btn_del.clicked.connect(lambda: self.main_window._move_file_to_trash(self.file_name, self.rel_path))
            layout.addWidget(btn_del)
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_folder:
                self.main_window._navigate_into_folder(self.file_name, self.rel_path)
            else:
                self.main_window._open_file_by_name(self.file_name, self.rel_path)
    def contextMenuEvent(self, event):
        if self.is_folder:
            self.main_window._show_context_menu_for_folder(self.file_name, event.globalPos(), self.rel_path)
        else:
            self.main_window._show_context_menu_for_file(self.file_name, event.globalPos(), self.rel_path)
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
        self.scope_files_cache = []
        self.current_view_mode = self.state_mgr.get_setting("file_view_mode", "TABLE")
        self.departments_list = []
        self._load_departments()
        if len(self.departments_list) == 1:
            self.active_dept_name = self.departments_list[0]['name']
            self.current_subpath = Path(self.active_dept_name)
        else:
            self.active_dept_name = None
            self.current_subpath = Path(".")
        self.selected_rel_paths = set()
        self._unlocked_pin_depts = self._load_persistent_unlocked_depts()
        self._cloud_trash_cache = []
        self._cloud_trash_fetching = False
        # إدارة ذكية لشريط التمرير لمنع قفز التمرير للأعلى أثناء التحديث الدوري
        self._force_full_render = True
        self._reset_scroll_on_render = False
        self._last_rendered_signature = None
        self._scan_in_progress = False
        self._scan_pending = False
        self._dept_counts_cache = {}
        self._total_root_items_cache = 0
        self._active_upload_workers = []
        self._force_quit = False
        self._tray_notified_once = False
        self._sync_history_entries = []
        # مسار شعار الغرفة الرسمي المتوافق مع ملف التثبيت المستقل
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).parent.parent
        self.logo_path = base_dir / "assets" / "logo.png"
        if not self.logo_path.exists():
            self.logo_path = base_dir / "assets" / "logo.ico"
        self.setWindowTitle("Share COC – غرفة تجارة كربلاء المقدسة")
        self.resize(1320, 820)
        self.setMinimumSize(1060, 680)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAcceptDrops(True)
        # ضبط أيقونة النافذة الرسمية
        if self.logo_path.exists():
            self.setWindowIcon(QIcon(str(self.logo_path)))
        self.setStyleSheet(get_gov_stylesheet())
        self.bridge = StatusBridge()
        self.bridge.sync_updated.connect(self.handle_sync_update)
        self.bridge.show_requested.connect(self.bring_to_front)
        self.bridge.scan_ready.connect(self._apply_scan_results)
        self.bridge.cloud_trash_ready.connect(self._on_cloud_trash_ready)
        self.bridge.cloud_snapshot_ready.connect(self._refresh_file_list)
        self.bridge.rescan_requested.connect(self._refresh_file_list)
        self.bridge.refresh_finished.connect(self._on_refresh_finished)
        self.bridge.depts_changed.connect(
            lambda: self._refresh_departments_sidebar(force_rebuild=True) if hasattr(self, 'dept_list') else None
        )
        if self.sync_engine:
            self.sync_engine.register_status_listener(lambda data: self.bridge.sync_updated.emit(data))
        self._ui_refresh_timer = QTimer(self)
        self._ui_refresh_timer.setSingleShot(True)
        self._ui_refresh_timer.timeout.connect(self._refresh_file_list)
        self._setup_ui()
        self._update_breadcrumb()
        self._setup_tray()
        self._refresh_file_list()
        # فحص دوري هادئ للتحديثات المحلية
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_file_list)
        self.timer.start(5000)
        # فحص دوري للأقسام السحابية في الخلفية كل 25 ثانية دون أي تأثير على الواجهة
        self.dept_cloud_timer = QTimer(self)
        self.dept_cloud_timer.timeout.connect(self.trigger_async_departments_sync)
        self.dept_cloud_timer.start(25000)
        QTimer.singleShot(1500, self.trigger_async_departments_sync)
    def bring_to_front(self):
        """إظهار النافذة وتنشيطها بأمان على خيط Qt الرئيسي بدون أي تجميد أو شاشة بيضاء"""
        try:
            self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            self.show()
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.repaint()
        except Exception as e:
            print(f"[bring_to_front]: {e}")
    def _run_cloud_async(self, fn, *args, **kwargs):
        """تشغيل أي عملية سحابية في خيط خلفي حتى لا تتجمد واجهة المستخدم مطلقاً"""
        import threading
        def _worker():
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print(f"[Async cloud op]: {e}")
            finally:
                if self.sync_engine:
                    self.sync_engine.wake(delay=0.5)
        threading.Thread(target=_worker, daemon=True).start()
    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        # ========================================================
        # 1. الشريط الجانبي الرئيسي للشاشات مطابق لموقع الويب 100%
        # ========================================================
        self.main_sidebar = QFrame()
        self.main_sidebar.setObjectName("mainSidebar")
        self.main_sidebar.setFixedWidth(240)
        self.main_sidebar.setStyleSheet("""
            QFrame#mainSidebar {
                background-color: #FFFFFF;
                border-left: 1px solid #E4E7EC;
            }
        """)
        sidebar_layout = QVBoxLayout(self.main_sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        # --- A. الهوية والشعار الرسمي مع إطار ذهبي دائري ---
        brand_frame = QFrame()
        brand_frame.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #E4E7EC;")
        brand_layout = QHBoxLayout(brand_frame)
        brand_layout.setContentsMargins(16, 16, 16, 16)
        brand_layout.setSpacing(12)
        # الشعار الدائري مع إطار ذهبي
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(44, 44)
        logo_lbl.setStyleSheet("border: 1.5px solid #c59b27; border-radius: 22px; background: #FFFFFF;")
        if self.logo_path.exists():
            from PyQt6.QtGui import QPainter, QPainterPath
            src_pix = QPixmap(str(self.logo_path)).scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            dest_pix = QPixmap(44, 44)
            dest_pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(dest_pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0.0, 0.0, 44.0, 44.0)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, src_pix)
            painter.end()
            logo_lbl.setPixmap(dest_pix)
        else:
            logo_lbl.setText("COC")
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setStyleSheet("font-weight: bold; color: #14372e; border: 1.5px solid #c59b27; border-radius: 22px;")
        brand_layout.addWidget(logo_lbl)
        # نصوص الهوية
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        app_title = QLabel("Share COC")
        app_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        app_title.setStyleSheet("color: #1B1F24; font-weight: 700; border: none; background: transparent;")
        title_box.addWidget(app_title)
        org_subtitle = QLabel("غرفة تجارة كربلاء المقدسة")
        org_subtitle.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Medium))
        org_subtitle.setStyleSheet("color: #667085; border: none; background: transparent;")
        title_box.addWidget(org_subtitle)
        brand_layout.addLayout(title_box)
        brand_layout.addStretch()
        sidebar_layout.addWidget(brand_frame)
        # --- B. القائمة الرئيسية للتنقل (3 عناصر فقط مطابقة للويب مع حذف الخانات الزائدة) ---
        nav_container = QWidget()
        nav_container_layout = QVBoxLayout(nav_container)
        nav_container_layout.setContentsMargins(12, 14, 12, 14)
        nav_container_layout.setSpacing(6)
        self.workspace_nav_group = QButtonGroup(self)
        self.workspace_nav_group.setExclusive(True)
        nav_btn_style = """
            QPushButton {
                background: transparent;
                color: #1B1F24;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 10px 14px;
                text-align: right;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #F7F8FA;
                border: 1px solid #E4E7EC;
                color: #14372e;
            }
            QPushButton:checked {
                background: #14372e;
                color: #FFFFFF;
                border: 1px solid #14372e;
                font-weight: 700;
            }
        """
        self.nav_btn_docs = QPushButton("📄   المستندات والأقسام")
        self.nav_btn_docs.setCheckable(True)
        self.nav_btn_docs.setChecked(True)
        self.nav_btn_docs.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.nav_btn_docs.setStyleSheet(nav_btn_style)
        self.nav_btn_docs.clicked.connect(lambda: self._switch_workspace_page(0))
        self.workspace_nav_group.addButton(self.nav_btn_docs)
        nav_container_layout.addWidget(self.nav_btn_docs)
        self.nav_btn_access = QPushButton("🗄️   مركز بيانات Access")
        self.nav_btn_access.setCheckable(True)
        self.nav_btn_access.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.nav_btn_access.setStyleSheet(nav_btn_style)
        self.nav_btn_access.clicked.connect(lambda: self._switch_workspace_page(1))
        self.workspace_nav_group.addButton(self.nav_btn_access)
        nav_container_layout.addWidget(self.nav_btn_access)
        self.nav_btn_admin = QPushButton("🛡️   لوحة تحكم الإدارة")
        self.nav_btn_admin.setCheckable(True)
        self.nav_btn_admin.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.nav_btn_admin.setStyleSheet(nav_btn_style)
        self.nav_btn_admin.clicked.connect(lambda: self._switch_workspace_page(2))
        self.workspace_nav_group.addButton(self.nav_btn_admin)
        nav_container_layout.addWidget(self.nav_btn_admin)
        # توافق مع المراجع السابقة
        self.nav_btn_sync = self.nav_btn_admin
        self.nav_btn_settings = self.nav_btn_admin
        sidebar_layout.addWidget(nav_container)
        sidebar_layout.addStretch()
        # --- C. بطاقة حالة السحابة والمزامنة السريعة (في أسفل القائمة الجانبية) ---
        sync_card = QFrame()
        sync_card.setObjectName("sidebarSyncCard")
        sync_card.setStyleSheet("""
            QFrame#sidebarSyncCard {
                background: #F7F8FA;
                border: 1px solid #E4E7EC;
                border-radius: 12px;
                margin: 12px 10px 14px 10px;
            }
        """)
        sc_layout = QVBoxLayout(sync_card)
        sc_layout.setContentsMargins(14, 12, 14, 12)
        sc_layout.setSpacing(8)
        sc_top_row = QHBoxLayout()
        sc_title = QLabel("السحابة المشتركة")
        sc_title.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        sc_title.setStyleSheet("color: #1B1F24; border: none; background: transparent;")
        sc_top_row.addWidget(sc_title)
        sc_top_row.addStretch()
        self.cloud_badge = QLabel("• متصل")
        self.cloud_badge.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.cloud_badge.setStyleSheet("""
            background: #ECFDF3;
            color: #12B76A;
            border: 1px solid #A6F4C5;
            border-radius: 9px;
            padding: 2px 7px;
        """)
        sc_top_row.addWidget(self.cloud_badge)
        sc_layout.addLayout(sc_top_row)
        sc_desc = QLabel("مزامنة فورية مع سحابة الغرفة.")
        sc_desc.setFont(QFont("IBM Plex Sans Arabic", 8))
        sc_desc.setStyleSheet("color: #667085; border: none; background: transparent;")
        sc_desc.setWordWrap(True)
        sc_layout.addWidget(sc_desc)
        self.btn_sidebar_sync = QPushButton("⚡ مزامنة فورية الآن")
        self.btn_sidebar_sync.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_sidebar_sync.setToolTip("بدء مزامنة فورية مع سحابة Google Drive وكافة الأجهزة")
        self.btn_sidebar_sync.setStyleSheet("""
            QPushButton {
                background: #14372e;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 7px 12px;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 11.5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1a473b;
            }
            QPushButton:pressed {
                background: #0f2a23;
            }
        """)
        self.btn_sidebar_sync.clicked.connect(self._on_refresh_clicked)
        sc_layout.addWidget(self.btn_sidebar_sync)
        self.btn_header_sync = self.btn_sidebar_sync
        sidebar_layout.addWidget(sync_card)
        # إضافة القائمة الجانبية للشاشات الكبيرة (في وضع RTL يوضع أوتوماتيكياً في اليمين)
        root_layout.addWidget(self.main_sidebar)
        # ========================================================
        # 2. الحاوية العامة لمحتوى النوافذ (على يسار القائمة الجانبية)
        # ========================================================
        content_wrapper = QWidget()
        content_wrapper.setObjectName("contentWrapper")
        content_wrapper_layout = QVBoxLayout(content_wrapper)
        content_wrapper_layout.setContentsMargins(10, 8, 10, 6)
        content_wrapper_layout.setSpacing(6)
        self._content_wrapper = content_wrapper
        self._content_wrapper_layout = content_wrapper_layout
        self._root_layout = root_layout
        # ========================================================
        # 2. شريط الإجراءات النظيف والمنظم بدون أي ازدحام بصري
        # ========================================================
                # ========================================================
        # ========================================================
        # 1. الشريط العلوي الموحد للبحث والفلاتر ومبدل العرض (مطابق لمنصة الويب 100%)
        # ========================================================
        top_bar_card = QFrame()
        top_bar_card.setObjectName("unifiedTopBarCard")
        top_bar_card.setStyleSheet("""
            QFrame#unifiedTopBarCard {
                background-color: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 12px;
            }
        """)
        tb_layout = QHBoxLayout(top_bar_card)
        tb_layout.setContentsMargins(14, 9, 14, 9)
        tb_layout.setSpacing(8)

        # حقل البحث بالاسم الكامل
        self.search_box = QLineEdit()
        self.search_box.setObjectName("govSearch")
        self.search_box.setMinimumWidth(215)
        self.search_box.setMaximumWidth(275)
        self.search_box.setPlaceholderText("🔍 ابحث بالاسم الكامل...")
        self.search_box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #F7F8FA; border: 1px solid #E4E7EC;
                border-radius: 8px; padding: 6px 12px; font-size: 11.5px; color: #1B1F24;
            }
            QLineEdit:focus {
                background-color: #FFFFFF; border: 1.5px solid #14372e;
            }
        """)
        self.search_box.textChanged.connect(self._filter_content)
        tb_layout.addWidget(self.search_box)

        # زر تحديد الكل
        self.btn_select_all_toggle = QPushButton("✓ تحديد الكل")
        self.btn_select_all_toggle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_select_all_toggle.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #1B1F24; border: 1px solid #E4E7EC;
                border-radius: 8px; padding: 6px 11px; font-weight: 600; font-size: 11.5px;
            }
            QPushButton:hover { background-color: #F7F8FA; border-color: #14372e; color: #14372e; }
        """)
        self.btn_select_all_toggle.clicked.connect(self._toggle_select_all_visible)
        tb_layout.addWidget(self.btn_select_all_toggle)

        tb_layout.addStretch()

        # كبسولات تصفية أنواع الملفات مطابقة لمنصة الويب
        type_group = QButtonGroup(self)
        type_group.setExclusive(True)
        self.tab_all = self._create_gov_tab("الكل (0)", "ALL", type_group, checked=True)
        self.tab_word = self._create_gov_tab("Word (0)", "WORD", type_group)
        self.tab_excel = self._create_gov_tab("Excel (0)", "EXCEL", type_group)
        self.tab_access = self._create_gov_tab("Access (0)", "ACCESS", type_group)
        self.tab_pdf = self._create_gov_tab("PDF (0)", "PDF", type_group)
        self.tab_images = self._create_gov_tab("صور (0)", "IMAGES", type_group)
        self.tab_other = self._create_gov_tab("أخرى (0)", "OTHER", type_group)
        self.tab_folders = QPushButton()
        self.tab_folders.hide()
        tb_layout.addWidget(self.tab_all)
        tb_layout.addWidget(self.tab_word)
        tb_layout.addWidget(self.tab_excel)
        tb_layout.addWidget(self.tab_access)
        tb_layout.addWidget(self.tab_pdf)
        tb_layout.addWidget(self.tab_images)
        tb_layout.addWidget(self.tab_other)

        # محدد أسلوب العرض (قائمة / شبكة) مطابق لمنصة الويب
        self.view_switch_frame = QFrame()
        self.view_switch_frame.setObjectName("viewSwitcherFrame")
        view_switch_layout = QHBoxLayout(self.view_switch_frame)
        view_switch_layout.setContentsMargins(3, 3, 3, 3)
        view_switch_layout.setSpacing(2)
        view_group = QButtonGroup(self)
        view_group.setExclusive(True)
        self.btn_view_table = QPushButton("☰ قائمة")
        self.btn_view_table.setObjectName("btnViewMode")
        self.btn_view_table.setCheckable(True)
        self.btn_view_table.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        view_group.addButton(self.btn_view_table)
        view_switch_layout.addWidget(self.btn_view_table)
        self.btn_view_grid = QPushButton("⊞ شبكة")
        self.btn_view_grid.setObjectName("btnViewMode")
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        view_group.addButton(self.btn_view_grid)
        view_switch_layout.addWidget(self.btn_view_grid)
        self.btn_view_compact = QPushButton()
        self.btn_view_compact.hide()
        self.btn_view_table.clicked.connect(lambda: self._set_view_mode("TABLE"))
        self.btn_view_grid.clicked.connect(lambda: self._set_view_mode("GRID"))
        tb_layout.addWidget(self.view_switch_frame)

        # عناصر متوافقة مع الاستدعاءات البرمجية القديمة
        self.btn_scan_book = QPushButton()
        self.btn_scan_book.hide()
        self.btn_stats = QPushButton("📊 الإحصائيات")
        self.btn_stats.hide()
        self.btn_stats.clicked.connect(self._show_file_statistics_dialog)
        self.btn_open_folder = QPushButton()
        self.btn_open_folder.hide()
        self.btn_toggle_sidebar = QPushButton()
        self.btn_toggle_sidebar.hide()
        self.dept_bar_frame = QFrame()
        self.dept_bar_frame.hide()
        self.dept_pills_container = QWidget()
        self.dept_pills_layout = QHBoxLayout(self.dept_pills_container)
        self.pill_all_depts = QPushButton()
        self.lbl_file_count_badge = QLabel("0 ملف")
        self.lbl_file_count_badge.hide()
        self.lbl_micro_sync = QLabel("● متزامن")
        self.lbl_micro_sync.hide()
        self.lbl_page_title = QLabel("كافة المستندات والأقسام")
        self.lbl_page_subtitle = QLabel("مزامنة سحابية مباشرة")
        self.lbl_subfolders_title = QLabel("📁 المجلدات والأقسام")
        self.lbl_subfolders_count = QLabel("0 مجلد")

        # ========================================================
        # 2. بطاقة المجلدات والمسار الرئيسية (Hero Folders & Breadcrumb Card)
        # مطابقة 100% لمنصة الويب: ترويسة المسار وأزرار الإجراءات في الأعلى وشبكة المجلدات بالأسفل
        # ========================================================
        self.subfolders_card = QFrame()
        self.subfolders_card.setObjectName("subfoldersCard")
        self.subfolders_card.setStyleSheet("""
            QFrame#subfoldersCard {
                background-color: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 12px;
            }
        """)
        sfc_layout = QVBoxLayout(self.subfolders_card)
        sfc_layout.setContentsMargins(14, 10, 14, 12)
        sfc_layout.setSpacing(10)

        # ترويسة بطاقة المجلدات: المسار التفاعلي يميناً + الإجراءات وزر الرجوع يساراً
        sfc_header = QHBoxLayout()
        sfc_header.setContentsMargins(0, 0, 0, 0)
        sfc_header.setSpacing(6)

        self.breadcrumb_container = QWidget()
        self.breadcrumb_container.setStyleSheet("background: transparent;")
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_layout.setSpacing(5)
        sfc_header.addWidget(self.breadcrumb_container)

        sfc_header.addStretch()

        # أزرار الإجراءات السريعة المدمجة بأناقة
        sec_btn_style = """
            QPushButton {
                background-color: #FFFFFF; color: #1B1F24; border: 1px solid #E4E7EC;
                border-radius: 7px; padding: 5px 10px; font-weight: 600; font-size: 11px;
            }
            QPushButton:hover { background-color: #F7F8FA; border-color: #14372e; color: #14372e; }
        """

        self.btn_upload = QPushButton("📤 رفع ملفات")
        self.btn_upload.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload.setStyleSheet("""
            QPushButton {
                background-color: #14372e; color: #FFFFFF; border: none;
                border-radius: 7px; padding: 5px 12px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #1b493d; }
        """)
        self.btn_upload.clicked.connect(self._upload_custom_file)
        sfc_header.addWidget(self.btn_upload)

        self.btn_upload_folder = QPushButton("📁 رفع مجلد")
        self.btn_upload_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload_folder.setStyleSheet(sec_btn_style)
        self.btn_upload_folder.clicked.connect(self._upload_custom_folder)
        sfc_header.addWidget(self.btn_upload_folder)

        self.btn_new_folder = QPushButton("➕ مجلد جديد")
        self.btn_new_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_new_folder.setStyleSheet(sec_btn_style)
        self.btn_new_folder.clicked.connect(self._show_new_folder_dialog)
        sfc_header.addWidget(self.btn_new_folder)

        self.tab_trash = QPushButton("🗑 المحذوفات (0)")
        self.tab_trash.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.tab_trash.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #667085; border: 1px solid #E4E7EC;
                border-radius: 7px; padding: 5px 10px; font-weight: 600; font-size: 11px;
            }
            QPushButton:hover { background-color: #FEF3F2; color: #F04438; border-color: #FECDCA; }
        """)
        self.tab_trash.clicked.connect(lambda: self._set_active_filter("TRASH" if self.active_filter != "TRASH" else "ALL"))
        sfc_header.addWidget(self.tab_trash)

        btn_quick_stats = QPushButton("📊 الإحصائيات")
        btn_quick_stats.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_quick_stats.setStyleSheet(sec_btn_style)
        btn_quick_stats.clicked.connect(self._show_file_statistics_dialog)
        sfc_header.addWidget(btn_quick_stats)

        self.btn_toggle_subfolders = QPushButton("📂 طي المجلدات")
        self.btn_toggle_subfolders.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_toggle_subfolders.setStyleSheet(sec_btn_style)
        self.btn_toggle_subfolders.clicked.connect(self._toggle_subfolders_visibility)
        sfc_header.addWidget(self.btn_toggle_subfolders)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(29, 29)
        self.btn_refresh.setToolTip("تحديث ومزامنة الملفات")
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #667085; border: 1px solid #E4E7EC;
                border-radius: 7px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #F7F8FA; color: #1B1F24; }
        """)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        sfc_header.addWidget(self.btn_refresh)

        self.btn_nav_up = QPushButton("➔ رجوع للمجلد الأعلى")
        self.btn_nav_up.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_nav_up.setStyleSheet("""
            QPushButton {
                background-color: #F7F8FA; color: #1B1F24; border: 1px solid #E4E7EC;
                border-radius: 7px; padding: 5px 12px; font-weight: 700; font-size: 11px;
            }
            QPushButton:hover { background-color: #ECFDF5; color: #14372e; border-color: #14372e; }
        """)
        self.btn_nav_up.clicked.connect(self._navigate_up)
        self.btn_nav_up.setVisible(False)
        sfc_header.addWidget(self.btn_nav_up)

        sfc_layout.addLayout(sfc_header)

        # حاوية شبكة المجلدات (تضبط ارتفاعها ديناميكياً في _populate_folders_grid لعرض كافة الصفوف بوضوح)
        self.subfolders_scroll = QScrollArea()
        self.subfolders_scroll.setWidgetResizable(True)
        self.subfolders_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.subfolders_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.subfolders_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.subfolders_content = QWidget()
        self.subfolders_content.setStyleSheet("background: transparent;")
        self.subfolders_grid = QGridLayout(self.subfolders_content)
        self.subfolders_grid.setContentsMargins(0, 2, 0, 2)
        self.subfolders_grid.setSpacing(10)
        self.subfolders_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.subfolders_scroll.setWidget(self.subfolders_content)
        sfc_layout.addWidget(self.subfolders_scroll)

        # شريط العمليات الجماعية
        self.bulk_bar_frame = QFrame()
        self.bulk_bar_frame.setVisible(False)
        self.bulk_bar_frame.setStyleSheet("""
            QFrame {
                background-color: #1B1F24;
                border: 1px solid #344054;
                border-radius: 8px;
                padding: 4px 10px;
            }
            QLabel { color: #FFFFFF; font-weight: 600; font-size: 12px; border: none; background: transparent; }
        """)
        bulk_layout = QHBoxLayout(self.bulk_bar_frame)
        bulk_layout.setContentsMargins(10, 5, 10, 5)
        bulk_layout.setSpacing(8)
        self.lbl_bulk_count = QLabel("تم تحديد 0 عنصر")
        self.lbl_bulk_count.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        bulk_layout.addWidget(self.lbl_bulk_count)
        bulk_layout.addStretch()
        btn_bulk_move = QPushButton("نقل المحدد...")
        btn_bulk_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_bulk_move.setStyleSheet("""
            QPushButton {
                background-color: #14372e; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 6px 14px; font-weight: 600; font-size: 11.5px;
            }
            QPushButton:hover { background-color: #1b493d; }
        """)
        btn_bulk_move.clicked.connect(self._move_selected_items_bulk)
        bulk_layout.addWidget(btn_bulk_move)
        btn_bulk_del = QPushButton("حذف المحدد لسلة المحذوفات")
        btn_bulk_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_bulk_del.setStyleSheet("""
            QPushButton {
                background-color: #F04438; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 6px 14px; font-weight: 600; font-size: 11.5px;
            }
            QPushButton:hover { background-color: #D92D20; }
        """)
        btn_bulk_del.clicked.connect(self._delete_selected_items_bulk)
        bulk_layout.addWidget(btn_bulk_del)
        btn_bulk_clear = QPushButton("إلغاء التحديد")
        btn_bulk_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_bulk_clear.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.12); color: #FFFFFF; border: none;
                border-radius: 6px; padding: 6px 12px; font-weight: 600; font-size: 11.5px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.22); }
        """)
        btn_bulk_clear.clicked.connect(self._clear_all_selections)
        bulk_layout.addWidget(btn_bulk_clear)

        self.stack = QStackedWidget()
        # 4.1 نمط القائمة الجدولية النظيفة (TABLE) - 7 أعمدة مطابقة للويب 100%
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "", "اسم الملف الكامل", "القسم / المجلد", "الحجم", "آخر تعديل", "الحالة", "الإجراءات"
        ])
        self.table.setShowGrid(False)
        self.table.setIconSize(QSize(34, 34))
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(54)
        tbl_hdr = self.table.horizontalHeader()
        tbl_hdr.setMinimumSectionSize(36)
        tbl_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 38)
        tbl_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tbl_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 145)
        tbl_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 82)
        tbl_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(4, 135)
        tbl_hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(5, 96)
        tbl_hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 168)
        self.table.setMinimumHeight(180)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAutoScroll(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.verticalScrollBar().setSingleStep(25)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        self.table.cellDoubleClicked.connect(self._open_selected_from_table)
        self.table.itemChanged.connect(self._on_table_item_changed)
        orig_key_press = self.table.keyPressEvent
        def table_key_press(event):
            if event.key() == Qt.Key.Key_Delete:
                if self.selected_rel_paths or len(self.table.selectionModel().selectedRows()) > 1:
                    self._delete_selected_items_bulk()
                    return
                selected = self.table.selectedItems()
                if selected:
                    r_sel = selected[0].row()
                    c0 = self.table.item(r_sel, 0)
                    c1 = self.table.item(r_sel, 1)
                    f_name = (c1.data(Qt.ItemDataRole.UserRole + 2) if c1 else None) or (c1.text() if c1 else (c0.text() if c0 else ""))
                    rel_p = (c1.data(Qt.ItemDataRole.UserRole) if c1 else None) or (c0.data(Qt.ItemDataRole.UserRole) if c0 else None)
                    is_fld = bool(c1.data(Qt.ItemDataRole.UserRole + 1)) if c1 else False
                    if is_fld:
                        self._move_folder_to_trash(f_name)
                    else:
                        self._move_file_to_trash(f_name, rel_p)
                    return
            elif event.key() == Qt.Key.Key_F2:
                selected = self.table.selectedItems()
                if selected:
                    r_sel = selected[0].row()
                    c0 = self.table.item(r_sel, 0)
                    c1 = self.table.item(r_sel, 1)
                    f_name = (c1.data(Qt.ItemDataRole.UserRole + 2) if c1 else None) or (c1.text() if c1 else (c0.text() if c0 else ""))
                    rel_p = (c1.data(Qt.ItemDataRole.UserRole) if c1 else None) or (c0.data(Qt.ItemDataRole.UserRole) if c0 else None)
                    is_fld = bool(c1.data(Qt.ItemDataRole.UserRole + 1)) if c1 else False
                    if is_fld:
                        self._rename_folder(f_name)
                    else:
                        self._rename_file(f_name, rel_p)
                    return
            orig_key_press(event)
        self.table.keyPressEvent = table_key_press
        self._last_wheel_time = 0
        orig_table_wheel = self.table.wheelEvent
        def table_wheel(event):
            self._last_wheel_time = time.time()
            orig_table_wheel(event)
        self.table.wheelEvent = table_wheel
        self.stack.addWidget(self.table)
        # 4.2 نمط شبكة البطاقات (GRID)
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setObjectName("govScrollArea")
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.verticalScrollBar().setSingleStep(25)
        self.grid_container = QWidget()
        self.grid_container.setObjectName("govScrollContent")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.grid_scroll.setWidget(self.grid_container)
        self.stack.addWidget(self.grid_scroll)
        # 4.3 نمط القائمة المدمجة (COMPACT)
        self.compact_scroll = QScrollArea()
        self.compact_scroll.setObjectName("govScrollArea")
        self.compact_scroll.setWidgetResizable(True)
        self.compact_scroll.verticalScrollBar().setSingleStep(25)
        self.compact_container = QWidget()
        self.compact_container.setObjectName("govScrollContent")
        self.compact_layout = QVBoxLayout(self.compact_container)
        self.compact_layout.setContentsMargins(12, 12, 12, 12)
        self.compact_layout.setSpacing(8)
        self.compact_scroll.setWidget(self.compact_container)
        self.stack.addWidget(self.compact_scroll)
        # 4.4 صفحة المحذوفات (TRASH)
        self.trash_page = QWidget()
        trash_layout = QVBoxLayout(self.trash_page)
        trash_layout.setContentsMargins(0, 0, 0, 0)
        trash_layout.setSpacing(10)
        trash_header = QFrame()
        trash_header.setObjectName("trashHeaderFrame")
        th_layout = QHBoxLayout(trash_header)
        th_layout.setContentsMargins(12, 10, 12, 10)
        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        self.th_title = QLabel("🗑️ سلة المحذوفات")
        self.th_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.th_title.setStyleSheet("color: #991b1b;")
        info_box.addWidget(self.th_title)
        self.th_desc = QLabel("المستندات والمجلدات المحذوفة محفوظة بأمان ويمكن استرجاعها فورياً.")
        self.th_desc.setFont(QFont("Segoe UI", 10))
        self.th_desc.setStyleSheet("color: #566c65;")
        info_box.addWidget(self.th_desc)
        th_layout.addLayout(info_box)
        th_layout.addStretch()
        self.btn_restore_all = QPushButton("🔄 استرجاع كافة المحذوفات")
        self.btn_restore_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_restore_all.setStyleSheet("""
            QPushButton {
                background-color: #14372e; color: #ffffff; border: none;
                border-radius: 8px; padding: 9px 18px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1e4a3f; }
        """)
        self.btn_restore_all.clicked.connect(self._restore_all_trash)
        th_layout.addWidget(self.btn_restore_all)
        self.btn_restore_selected = QPushButton("↩️ استرجاع المحدد")
        self.btn_restore_selected.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_restore_selected.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: #ffffff; border: none;
                border-radius: 8px; padding: 9px 18px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_restore_selected.clicked.connect(self._restore_selected_from_trash)
        th_layout.addWidget(self.btn_restore_selected)
        self.btn_empty_trash = QPushButton("🗑️ إفراغ السلة")
        self.btn_empty_trash.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_empty_trash.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2; color: #991b1b; border: 1.5px solid #fecaca;
                border-radius: 8px; padding: 9px 16px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #fecaca; color: #7f1d1d; }
        """)
        self.btn_empty_trash.clicked.connect(self._empty_all_trash)
        th_layout.addWidget(self.btn_empty_trash)
        trash_layout.addWidget(trash_header)
        self.trash_table = QTableWidget()
        self.trash_table.setColumnCount(5)
        self.trash_table.setHorizontalHeaderLabels([
            "المستند أو المجلد المحذوف", "المسار الأصلي", "تأريخ الحذف", "حجم الملف", "الإجراءات المتاحة"
        ])
        self.trash_table.setWordWrap(True)
        self.trash_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.trash_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.trash_table.horizontalHeader().setMinimumSectionSize(36)
        self.trash_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.trash_table.setColumnWidth(4, 220)
        self.trash_table.verticalHeader().setVisible(False)
        self.trash_table.verticalHeader().setDefaultSectionSize(52)
        self.trash_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trash_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trash_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.trash_table.customContextMenuRequested.connect(self._show_trash_context_menu)
        self.trash_table.cellDoubleClicked.connect(self._on_trash_row_double_clicked)
        apply_gov_shadow(self.trash_table, blur=12, offset_y=2, alpha=10)
        trash_layout.addWidget(self.trash_table, stretch=1)
        self.stack.addWidget(self.trash_page)

        # تجميع صفحة المستندات والأقسام الحديثة بالكامل (Full Width)
        explorer_page = QWidget()
        explorer_layout = QVBoxLayout(explorer_page)
        explorer_layout.setContentsMargins(6, 6, 6, 6)
        explorer_layout.setSpacing(8)
        explorer_layout.addWidget(top_bar_card)
        explorer_layout.addWidget(self.subfolders_card)
        explorer_layout.addWidget(self.bulk_bar_frame)
        explorer_layout.addWidget(self.stack, stretch=1)
        # عناصر توافقية لمنع أي انهيار
        self.lbl_current_path = self.lbl_subfolders_title
        self.lbl_folder_info = QLabel()
        self.lbl_total = QLabel()
        self.lbl_trash_stat = QLabel()
        self.breadcrumb_frame = QFrame()
        self.breadcrumb_frame.hide()
        self.sidebar_frame = QFrame()
        self.sidebar_frame.hide()
        self.dept_list = QListWidget()
        self.dept_list.hide()
        # حاوية شاشات العمل الرئيسية (0=المستندات والأقسام، 1=مركز بيانات Access، 2=لوحة تحكم الإدارة)
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(explorer_page)
        self.access_hub_page = AccessHubWidget()
        self.workspace_stack.addWidget(self.access_hub_page)
        self.admin_page = self._build_admin_page()
        self.workspace_stack.addWidget(self.admin_page)
        self._content_wrapper_layout.addWidget(self.workspace_stack, stretch=1)
        # تطبيق نمط العرض المحفوظ للمستخدم
        self._set_view_mode(self.current_view_mode, persist=False)
        # ========================================================
        # 5. شريط الحالة السفلي النظيف والمختصر
        # ========================================================
        statusbar = QFrame()
        statusbar.setObjectName("govStatusBar")
        statusbar.setFixedHeight(28)
        statusbar.setStyleSheet("""
            QFrame#govStatusBar {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 7px;
            }
            QFrame#govStatusBar QLabel {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        status_layout = QHBoxLayout(statusbar)
        status_layout.setContentsMargins(10, 2, 10, 2)
        status_layout.setSpacing(6)
        self.lbl_total = QLabel("المستندات: 0")
        self.lbl_total.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.lbl_total.setStyleSheet("color: #1B1F24;")
        status_layout.addWidget(self.lbl_total)
        status_layout.addWidget(QLabel(" • "))
        self.lbl_trash_stat = QLabel("المحذوفات: 0")
        self.lbl_trash_stat.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_trash_stat.setStyleSheet("color: #667085;")
        status_layout.addWidget(self.lbl_trash_stat)
        status_layout.addWidget(QLabel(" • "))
        self.lbl_watcher = QLabel("المزامنة: متصل ونشط")
        self.lbl_watcher.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_watcher.setStyleSheet("color: #14372e;")
        status_layout.addWidget(self.lbl_watcher)
        status_layout.addWidget(QLabel(" • "))
        self.lbl_cloud_info = QLabel("Google Drive")
        self.lbl_cloud_info.setFont(QFont("Segoe UI", 9))
        self.lbl_cloud_info.setStyleSheet("color: #667085;")
        status_layout.addWidget(self.lbl_cloud_info)
        status_layout.addStretch()
        self.lbl_dept = QLabel("غرفة تجارة كربلاء المقدسة • Share COC")
        self.lbl_dept.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_dept.setStyleSheet("color: #667085;")
        status_layout.addWidget(self.lbl_dept)
        btn_settings = QPushButton("⚙")
        btn_settings.setObjectName("btnGovSettings")
        btn_settings.setToolTip("إعدادات النظام والتكامل مع Windows")
        btn_settings.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_settings.clicked.connect(lambda: (self._switch_workspace_page(2), hasattr(self, 'btn_admin_sys') and self.btn_admin_sys.click()))
        status_layout.addWidget(btn_settings)
        self._content_wrapper_layout.addWidget(statusbar)
        self._root_layout.addWidget(self._content_wrapper, stretch=1)
    def _switch_workspace_page(self, index: int):
        """التبديل السلس بين شاشات المنظومة الرئيسية (0=المستندات والأقسام، 1=مركز بيانات Access، 2=لوحة تحكم الإدارة)"""
        if index == 1:
            if not self._check_access_hub_permission():
                curr_idx = self.workspace_stack.currentIndex() if hasattr(self, 'workspace_stack') else 0
                if curr_idx == 0 and hasattr(self, 'nav_btn_docs'):
                    self.nav_btn_docs.setChecked(True)
                elif curr_idx == 1 and hasattr(self, 'nav_btn_access'):
                    self.nav_btn_access.setChecked(True)
                elif curr_idx == 2 and hasattr(self, 'nav_btn_admin'):
                    self.nav_btn_admin.setChecked(True)
                return
        if hasattr(self, 'workspace_stack'):
            self.workspace_stack.setCurrentIndex(index)
        if index == 0 and hasattr(self, 'nav_btn_docs'):
            self.nav_btn_docs.setChecked(True)
        elif index == 1 and hasattr(self, 'nav_btn_access'):
            self.nav_btn_access.setChecked(True)
            if hasattr(self, 'access_hub_page'):
                self.access_hub_page.load_data()
        elif index == 2 and hasattr(self, 'nav_btn_admin'):
            self.nav_btn_admin.setChecked(True)
    def _build_admin_page(self) -> QWidget:
        """بناء شاشة لوحة تحكم الإدارة الموحدة المطابقة للويب (تجمع مركز المزامنة وإعدادات النظام)"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        # شريط تبويبات لوحة الإدارة
        admin_header = QFrame()
        admin_header.setObjectName("adminHeader")
        admin_header.setStyleSheet("""
            QFrame#adminHeader {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 10px;
            }
        """)
        ah_layout = QHBoxLayout(admin_header)
        ah_layout.setContentsMargins(14, 8, 14, 8)
        ah_layout.setSpacing(10)
        title_lbl = QLabel("🛡️ لوحة تحكم الإدارة")
        title_lbl.setFont(QFont("IBM Plex Sans Arabic", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #1B1F24; border: none; background: transparent;")
        ah_layout.addWidget(title_lbl)
        ah_layout.addStretch()
        tab_nav_frame = QFrame()
        tab_nav_frame.setStyleSheet("""
            background: #F7F8FA;
            border: 1px solid #E4E7EC;
            border-radius: 8px;
        """)
        tab_nav_layout = QHBoxLayout(tab_nav_frame)
        tab_nav_layout.setContentsMargins(3, 3, 3, 3)
        tab_nav_layout.setSpacing(4)
        admin_tabs_group = QButtonGroup(self)
        admin_tabs_group.setExclusive(True)
        admin_tab_btn_style = """
            QPushButton {
                background: transparent;
                color: #667085;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 11.5px;
                font-weight: 600;
            }
            QPushButton:hover {
                color: #1B1F24;
            }
            QPushButton:checked {
                background: #14372e;
                color: #FFFFFF;
                font-weight: bold;
            }
        """
        self.btn_admin_sync = QPushButton("⚡ مركز المزامنة السحابية")
        self.btn_admin_sync.setCheckable(True)
        self.btn_admin_sync.setChecked(True)
        self.btn_admin_sync.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_admin_sync.setStyleSheet(admin_tab_btn_style)
        admin_tabs_group.addButton(self.btn_admin_sync)
        tab_nav_layout.addWidget(self.btn_admin_sync)
        self.btn_admin_sys = QPushButton("⚙️ إعدادات النظام والتكامل")
        self.btn_admin_sys.setCheckable(True)
        self.btn_admin_sys.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_admin_sys.setStyleSheet(admin_tab_btn_style)
        admin_tabs_group.addButton(self.btn_admin_sys)
        tab_nav_layout.addWidget(self.btn_admin_sys)
        ah_layout.addWidget(tab_nav_frame)
        layout.addWidget(admin_header)
        self.admin_sub_stack = QStackedWidget()
        self.admin_sub_stack.addWidget(self._build_sync_center_page())
        self.admin_sub_stack.addWidget(self._build_system_settings_page())
        layout.addWidget(self.admin_sub_stack, stretch=1)
        def _switch_admin_sub(idx: int):
            self.admin_sub_stack.setCurrentIndex(idx)
            if idx == 0:
                self.btn_admin_sync.setChecked(True)
            else:
                self.btn_admin_sys.setChecked(True)
        self.btn_admin_sync.clicked.connect(lambda: _switch_admin_sub(0))
        self.btn_admin_sys.clicked.connect(lambda: _switch_admin_sub(1))
        return page
    def _build_sync_center_page(self) -> QWidget:
        """بناء شاشة مركز المزامنة والتحويلات السحابية اللحظية (Page 1)"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)
        # 1. بطاقات ملخص حالة المزامنة السحابية
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        def _make_stat_card(title_txt, val_txt, sub_txt, accent_color="#14372e"):
            card = QFrame()
            card.setObjectName("syncStatCard")
            card.setStyleSheet(f"""
                QFrame#syncStatCard {{
                    background: #ffffff;
                    border: 1.5px solid #d5dfdb;
                    border-right: 5px solid {accent_color};
                    border-radius: 12px;
                }}
                QFrame#syncStatCard QLabel {{
                    background: transparent;
                    border: none;
                    padding: 0px;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(4)
            t_lbl = QLabel(title_txt)
            t_lbl.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
            t_lbl.setStyleSheet("color: #566c65;")
            v_lbl = QLabel(val_txt)
            v_lbl.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {accent_color};")
            s_lbl = QLabel(sub_txt)
            s_lbl.setFont(QFont("Segoe UI", 9))
            s_lbl.setStyleSheet("color: #64748b;")
            cl.addWidget(t_lbl)
            cl.addWidget(v_lbl)
            cl.addWidget(s_lbl)
            return card, v_lbl
        c1, self.lbl_sync_card_status = _make_stat_card(
            "☁️ حالة الربط السحابي",
            "متصل ومؤمّن (Google Drive API v3)",
            "رفع مجزأ ذكي (512KB Chunks) مع استئناف تلقائي",
            "#0d8a55"
        )
        c2, self.lbl_sync_card_watcher = _make_stat_card(
            "⚡ محرك الرصد الفوري",
            "نشط (يرصد التعديلات والحفظ Ctrl+S)",
            "أولوية فورية للملفات الصغيرة والمتوسطة",
            "#14372e"
        )
        c3, self.lbl_sync_card_folder = _make_stat_card(
            "📂 مسار المزامنة المحلي",
            str(self.sync_folder),
            "متزامن مع كافة أجهزة الغرفة ومنصة الويب",
            "#b45309"
        )
        cards_row.addWidget(c1, stretch=1)
        cards_row.addWidget(c2, stretch=1)
        cards_row.addWidget(c3, stretch=1)
        layout.addLayout(cards_row)
        # 2. شريط تقدم العملية النشطة وأزرار التحكم السريع
        active_frame = QFrame()
        active_frame.setObjectName("syncActiveFrame")
        active_frame.setStyleSheet("""
            QFrame#syncActiveFrame {
                background: #ffffff;
                border: 1.5px solid #d5dfdb;
                border-radius: 12px;
            }
            QFrame#syncActiveFrame QLabel {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        af_layout = QHBoxLayout(active_frame)
        af_layout.setContentsMargins(16, 10, 16, 10)
        af_layout.setSpacing(12)
        self.lbl_sync_center_live = QLabel("✅ جميع المستندات متزامنة ومحدثة مع السحابة")
        self.lbl_sync_center_live.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        self.lbl_sync_center_live.setStyleSheet("color: #14372e; border: none;")
        af_layout.addWidget(self.lbl_sync_center_live, stretch=1)
        btn_force_sync = QPushButton("⚡ بدء دورة مزامنة شاملة الآن")
        btn_force_sync.setObjectName("btnGovPrimary")
        btn_force_sync.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_force_sync.clicked.connect(self._on_refresh_clicked)
        af_layout.addWidget(btn_force_sync)
        btn_upload_here = QPushButton("➕ رفع ملفات للسحابة")
        btn_upload_here.setObjectName("btnGovSecondary")
        btn_upload_here.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_upload_here.clicked.connect(self._upload_custom_file)
        af_layout.addWidget(btn_upload_here)
        btn_clear_log = QPushButton("🧹 مسح السجل")
        btn_clear_log.setObjectName("btnGovSecondary")
        btn_clear_log.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_clear_log.clicked.connect(self._clear_sync_log_table)
        af_layout.addWidget(btn_clear_log)
        layout.addWidget(active_frame)
        # 3. جدول سجل عمليات المزامنة والرفع والتنزيل اللحظي
        self.sync_log_table = QTableWidget()
        self.sync_log_table.setColumnCount(4)
        self.sync_log_table.setHorizontalHeaderLabels([
            "التوقيت", "نوع العملية", "اسم المستند أو المسار", "الحالة والتفاصيل"
        ])
        self.sync_log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.sync_log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sync_log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.sync_log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.sync_log_table.verticalHeader().setVisible(False)
        self.sync_log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sync_log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.sync_log_table, stretch=1)
        self._append_sync_log("بدء التشغيل 🚀", "منظومة Share COC v4.0", "✅ جاهز ومتصل بالسحابة")
        return page
    def _append_sync_log(self, action_text: str, file_text: str, status_text: str):
        """إضافة سطر جديد في جدول سجل المزامنة اللحظي"""
        try:
            if not hasattr(self, 'sync_log_table') or self.sync_log_table is None:
                return
            now_str = datetime.now().strftime("%H:%M:%S")
            self.sync_log_table.insertRow(0)
            for col, val in enumerate([now_str, action_text, file_text, status_text]):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.sync_log_table.setItem(0, col, item)
            if self.sync_log_table.rowCount() > 120:
                self.sync_log_table.removeRow(self.sync_log_table.rowCount() - 1)
        except Exception:
            pass
    def _clear_sync_log_table(self):
        if hasattr(self, 'sync_log_table') and self.sync_log_table:
            self.sync_log_table.setRowCount(0)
    def _build_system_settings_page(self) -> QWidget:
        """بناء شاشة إعدادات النظام والتكامل الرسمي مع Windows (Page 2)"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(14)
        # بطاقة التكامل مع نظام التشغيل Windows
        win_card = QFrame()
        win_card.setObjectName("sysWinCard")
        win_card.setStyleSheet("""
            QFrame#sysWinCard {
                background: #ffffff;
                border: 1.5px solid #d5dfdb;
                border-radius: 12px;
            }
            QFrame#sysWinCard QLabel {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        wc_layout = QVBoxLayout(win_card)
        wc_layout.setContentsMargins(18, 14, 18, 14)
        wc_layout.setSpacing(10)
        wc_title = QLabel("🖥️ التكامل الرسمي مع نظام التشغيل Windows")
        wc_title.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        wc_title.setStyleSheet("color: #14372e;")
        wc_layout.addWidget(wc_title)
        wc_desc = QLabel(
            "تحكم في خصائص تثبيت البرنامج، التشغيل التلقائي مع إقلاع الحاسوب، العمل في شريط المهام (System Tray)، واختصارات النظام."
        )
        wc_desc.setFont(QFont("Segoe UI", 10))
        wc_desc.setStyleSheet("color: #566c65;")
        wc_layout.addWidget(wc_desc)
        from PyQt6.QtWidgets import QCheckBox
        from autostart import is_windows_autostart_enabled, set_windows_autostart
        self.chk_autostart = QCheckBox("تشغيل منظومة Share COC تلقائياً عند بدء تشغيل Windows (موصى به لاستمرار المزامنة)")
        self.chk_autostart.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
        self.chk_autostart.setStyleSheet("color: #0f172a; spacing: 8px;")
        self.chk_autostart.setChecked(is_windows_autostart_enabled())
        def _on_autostart_toggled(checked):
            ok, msg = set_windows_autostart(enable=checked)
            if not ok:
                QMessageBox.warning(self, "تنبيه", msg)
        self.chk_autostart.toggled.connect(_on_autostart_toggled)
        wc_layout.addWidget(self.chk_autostart)
        min_tray_saved = self.state_mgr.get_setting("minimize_to_tray", "1") != "0"
        self.chk_minimize_tray = QCheckBox("إبقاء التطبيق يعمل في الخلفية بجانب الساعة (System Tray) عند الضغط على زر الإغلاق (X)")
        self.chk_minimize_tray.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
        self.chk_minimize_tray.setStyleSheet("color: #0f172a; spacing: 8px;")
        self.chk_minimize_tray.setChecked(min_tray_saved)
        self.chk_minimize_tray.toggled.connect(
            lambda checked: self.state_mgr.set_setting("minimize_to_tray", "1" if checked else "0")
        )
        wc_layout.addWidget(self.chk_minimize_tray)
        # أزرار التكامل مع النظام
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        btn_repair_shortcuts = QPushButton("🔗 تثبيت وتحديث اختصارات النظام (سطح المكتب + قائمة ابدأ + إرسال إلى Send To)")
        btn_repair_shortcuts.setObjectName("btnGovPrimary")
        btn_repair_shortcuts.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_repair_shortcuts.clicked.connect(self._repair_system_shortcuts)
        actions_row.addWidget(btn_repair_shortcuts)
        btn_diag = QPushButton("🩺 فحص الاتصال السحابي وسرعة الاستجابة")
        btn_diag.setObjectName("btnGovSecondary")
        btn_diag.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_diag.clicked.connect(self._run_cloud_diagnostics)
        actions_row.addWidget(btn_diag)
        btn_open_log = QPushButton("📄 عرض سجل النظام (Log)")
        btn_open_log.setObjectName("btnGovSecondary")
        btn_open_log.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open_log.clicked.connect(self._open_system_log_file)
        actions_row.addWidget(btn_open_log)
        actions_row.addStretch()
        wc_layout.addLayout(actions_row)
        layout.addWidget(win_card)
        # بطاقة مسارات النظام ومعلومات التثبيت
        paths_card = QFrame()
        paths_card.setObjectName("sysPathsCard")
        paths_card.setStyleSheet("""
            QFrame#sysPathsCard {
                background: #ffffff;
                border: 1.5px solid #d5dfdb;
                border-radius: 12px;
            }
            QFrame#sysPathsCard QLabel {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        pc_layout = QVBoxLayout(paths_card)
        pc_layout.setContentsMargins(18, 14, 18, 14)
        pc_layout.setSpacing(10)
        pc_title = QLabel("📂 مسارات النظام والتخزين المعتمدة على هذا الحاسوب")
        pc_title.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
        pc_title.setStyleSheet("color: #14372e;")
        pc_layout.addWidget(pc_title)
        exe_loc = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
        appdata_loc = Path(os.environ.get("APPDATA", Path.home())) / "FileExchange"
        for label_title, path_val in [
            ("مسار تشغيل البرنامج التنفيذي:", exe_loc),
            ("مجلد المزامنة السحابية المشترك:", str(self.sync_folder)),
            ("مجلد قاعدة البيانات المحلية والسجل:", str(appdata_loc)),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label_title)
            lbl.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
            lbl.setStyleSheet("color: #334155; border: none; min-width: 220px;")
            val = QLineEdit(str(path_val))
            val.setReadOnly(True)
            val.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 10px; color: #0f172a;")
            row.addWidget(lbl)
            row.addWidget(val, stretch=1)
            pc_layout.addLayout(row)
        bottom_btns = QHBoxLayout()
        btn_cloud_cfg = QPushButton("🔑 إعدادات الخادم السحابي المتقدمة")
        btn_cloud_cfg.setObjectName("btnGovSecondary")
        btn_cloud_cfg.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cloud_cfg.clicked.connect(self._open_cloud_settings)
        bottom_btns.addWidget(btn_cloud_cfg)
        bottom_btns.addStretch()
        btn_full_exit = QPushButton("🚪 إغلاق البرنامج وإيقاف المزامنة نهائياً")
        btn_full_exit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_full_exit.setStyleSheet("""
            QPushButton {
                background: #fee2e2; color: #991b1b; border: 1.5px solid #fecaca;
                border-radius: 8px; padding: 8px 16px; font-family: 'Cairo'; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #fecaca; color: #7f1d1d; }
        """)
        btn_full_exit.clicked.connect(self._quit_application)
        bottom_btns.addWidget(btn_full_exit)
        pc_layout.addLayout(bottom_btns)
        layout.addWidget(paths_card)
        layout.addStretch()
        return page
    def _repair_system_shortcuts(self):
        """تثبيت وتحديث كافة اختصارات ويندوز والتسجيل في البرامج المثبتة"""
        try:
            from windows_integration import setup_all_system_integrations, get_default_install_dir, APP_EXE_NAME
            install_exe = get_default_install_dir() / APP_EXE_NAME
            target_exe = install_exe if install_exe.exists() else Path(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0]))
            res = setup_all_system_integrations(
                exe_path=target_exe,
                sync_dir=self.sync_folder,
                icon_path=self.logo_path if self.logo_path.exists() else None,
                create_desktop=True,
                create_start_menu=True,
                create_sendto=True,
                enable_autostart=self.chk_autostart.isChecked() if hasattr(self, 'chk_autostart') else True,
                register_uninstaller=True,
            )
            QMessageBox.information(
                self,
                "اكتمل تحديث تكامل النظام",
                "✅ تم تحديث وتثبيت اختصارات النظام بنجاح:\n\n"
                f"• اختصار سطح المكتب: {'تم بنجاح' if res.get('desktop_shortcut') else 'موجود'}\n"
                f"• مجلد قائمة ابدأ (Start Menu): {'تم بنجاح' if res.get('start_menu') else 'موجود'}\n"
                f"• قائمة الزر الأيمن (Send To): {'تم بنجاح' if res.get('sendto_menu') else 'موجود'}\n"
                f"• تسجيل البرامج المثبتة في ويندوز: {'تم بنجاح' if res.get('uninstall_registry') else 'موجود'}\n"
                f"• بروتوكول المتصفح (sharecoc://): {'تم بنجاح' if res.get('protocol') else 'مفعّل'}"
            )
        except Exception as e:
            QMessageBox.warning(self, "تنبيه", f"حدث خطأ أثناء تحديث الاختصارات:\n{e}")
    def _run_cloud_diagnostics(self):
        """فحص الاتصال الفعلي مع Google Drive وقياس سرعة الاستجابة"""
        if not self.client or not self.client.is_configured():
            QMessageBox.warning(self, "فحص الاتصال السحابي", "⚠️ خدمة Google Drive غير مهيأة حالياً.")
            return
        t0 = time.time()
        try:
            snap = self.client.snapshot(force=True)
            elapsed_ms = int((time.time() - t0) * 1000)
            num_files = len(snap.files) if snap else 0
            num_folders = max(0, len(snap.folders) - 1) if snap else 0
            QMessageBox.information(
                self,
                "نتيجة فحص الاتصال السحابي",
                f"✅ الاتصال بسحابة Google Drive ممتاز ونشط!\n\n"
                f"• زمن الاستجابة (Latency): {elapsed_ms} ملي ثانية\n"
                f"• إجمالي المجلدات السحابية: {num_folders} مجلد\n"
                f"• إجمالي المستندات السحابية: {num_files} مستند\n"
                f"• محرك الرفع السريع (Streaming 16MB): مفعّل وبأقصى سرعة"
            )
        except Exception as e:
            QMessageBox.critical(self, "خطأ في الاتصال السحابي", f"❌ تعذر الاتصال بـ Google Drive:\n{e}")
    def _open_system_log_file(self):
        log_file = Path(os.environ.get("APPDATA", Path.home())) / "FileExchange" / "share_coc.log"
        if log_file.exists():
            os.startfile(str(log_file))
        else:
            QMessageBox.information(self, "سجل النظام", "ملف السجل فارغ حالياً ولا توجد أخطاء مسجلة.")
    def dragEnterEvent(self, event):
        """قبول سحب الملفات والمجلدات من ويندوز وإفلاتها داخل نافذة التطبيق"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    def dropEvent(self, event):
        """معالجة الملفات أو المجلدات التي تم إفلاتها في نافذة التطبيق ورفعها فوراً للسحابة"""
        if not event.mimeData().hasUrls():
            return
        dropped_paths = []
        for url in event.mimeData().urls():
            local_p = url.toLocalFile()
            if local_p and os.path.exists(local_p):
                dropped_paths.append(Path(local_p))
        if dropped_paths:
            event.acceptProposedAction()
            self._handle_dropped_paths(dropped_paths)
    def _handle_dropped_paths(self, paths: list[Path]):
        """رفع قائمة مسارات (ملفات أو مجلدات) مفلوتة أو مرسلة عبر Send To إلى المجلد الحالي"""
        if not self._check_department_permission(self.active_dept_name, action='upload'):
            return
        if any(p.is_dir() for p in paths) and not self._check_department_permission(self.active_dept_name, action='create_folder'):
            return
        from gdrive_client import is_ignored_name
        target_dir = self._get_current_abs_folder()
        target_dir.mkdir(parents=True, exist_ok=True)
        folders_to_create = []
        if target_dir != self.sync_folder:
            rel_dir = str(target_dir.relative_to(self.sync_folder)).replace("\\", "/")
            if rel_dir and rel_dir != ".":
                folders_to_create.append(rel_dir)
        tasks = []
        for p in paths:
            if p.is_file():
                if not is_ignored_name(p.name):
                    dest = target_dir / p.name
                    rel = str(dest.relative_to(self.sync_folder)).replace("\\", "/")
                    tasks.append((p, dest, rel))
            elif p.is_dir():
                target_base = target_dir / p.name
                rel_base = str(target_base.relative_to(self.sync_folder)).replace("\\", "/")
                if rel_base not in folders_to_create:
                    folders_to_create.append(rel_base)
                for sub in p.rglob("*"):
                    if sub.is_dir() and not sub.name.startswith('.'):
                        sub_target = target_base / sub.relative_to(p)
                        rel_sub = str(sub_target.relative_to(self.sync_folder)).replace("\\", "/")
                        if rel_sub not in folders_to_create:
                            folders_to_create.append(rel_sub)
                    elif sub.is_file() and not is_ignored_name(sub.name):
                        dest_file = target_base / sub.relative_to(p)
                        rel_f = str(dest_file.relative_to(self.sync_folder)).replace("\\", "/")
                        tasks.append((sub, dest_file, rel_f))
        if not tasks and folders_to_create:
            for rel_f in folders_to_create:
                (self.sync_folder / rel_f).mkdir(parents=True, exist_ok=True)
                if self.client and self.client.is_configured():
                    self._run_cloud_async(self.client.ensure_folder, rel_f)
            self._force_full_render = True
            self._refresh_file_list()
            return
        if tasks:
            self._start_cloud_upload_job(
                tasks=tasks,
                folders_to_create=folders_to_create,
                dialog_title="رفع العناصر المضافة ومزامنتها في السحابة"
            )
    def _toggle_sidebar(self):
        """إظهار أو إخفاء القائمة الجانبية للأقسام بنقرة واحدة على زر ☰ مع حفظ التفضيل"""
        if not hasattr(self, 'sidebar_frame'):
            return
        is_vis = not self.sidebar_frame.isVisible()
        self.sidebar_frame.setVisible(is_vis)
        try:
            self.state_mgr.set_setting("sidebar_visible", "1" if is_vis else "0")
        except Exception:
            pass
        if hasattr(self, 'btn_toggle_sidebar'):
            self.btn_toggle_sidebar.setChecked(is_vis)
            self.btn_toggle_sidebar.setText("☰ الأقسام")
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
    def _load_departments(self):
        """تحميل قائمة الأقسام المعتمدة من القرص وقاعدة البيانات أولاً فورياً"""
        saved = self.state_mgr.get_departments()
        if saved:
            self.departments_list = saved
        else:
            local_names = []
            try:
                for item in self.sync_folder.iterdir():
                    if item.is_dir() and not item.name.startswith(".") and item.name != ".trash":
                        local_names.append(item.name)
            except Exception:
                pass
            if local_names:
                self.departments_list = [{"name": name, "icon": "📁"} for name in sorted(local_names)]
            else:
                self.departments_list = [
                    {"name": "سجل التجاري", "icon": "📁"},
                    {"name": "أمانة السر والإدارة العامة", "icon": "📁"},
                    {"name": "الاشتراكات", "icon": "📁"},
                    {"name": "القسم العام", "icon": "📁"}
                ]
            self.state_mgr.set_departments(self.departments_list)
    def trigger_async_departments_sync(self):
        """بدء مزامنة الأقسام السحابية في خيط خلفي هادئ لمنع تجميد الواجهة"""
        import threading
        threading.Thread(target=self._async_sync_departments, daemon=True).start()
    def _async_sync_departments(self):
        """مزامنة الأقسام السحابية بالخلفية بأمان تام وبدون أي قفل للواجهة"""
        if not hasattr(self, 'client') or not self.client or not self.client.is_configured():
            return
        try:
            cloud_folders = self.client.list_folders() or []
            cloud_names = []
            for cf in cloud_folders:
                cf_name = str(cf.get('name', '')).strip()
                if cf_name and not cf_name.startswith('.'):
                    cloud_names.append(cf_name)
                    dept_dir = (self.sync_folder / cf_name).resolve()
                    dept_dir.mkdir(parents=True, exist_ok=True)
            if cloud_names:
                current_names = [d['name'] for d in self.departments_list]
                if set(cloud_names) != set(current_names) or len(cloud_names) != len(current_names):
                    self.departments_list = [{"name": name, "icon": "📁"} for name in cloud_names]
                    self.state_mgr.set_departments(self.departments_list)
                    self.bridge.depts_changed.emit()
        except Exception as e:
            print(f"[Async dept sync error]: {e}")
    def _sync_departments_from_remote_and_disk(self, force=False):
        """مزامنة سريعة من المجلدات المحلية على القرص دون إجراء أي طلبات شبكة على الخيط الرئيسي"""
        has_changes = False
        try:
            local_names = []
            for item in self.sync_folder.iterdir():
                if item.is_dir() and not item.name.startswith(".") and item.name != ".trash":
                    local_names.append(item.name)
            current_names = [d['name'] for d in self.departments_list]
            for l_name in local_names:
                if l_name not in current_names:
                    self.departments_list.append({"name": l_name, "icon": "📁"})
                    has_changes = True
        except Exception:
            pass
        if has_changes:
            self.state_mgr.set_departments(self.departments_list)
            if hasattr(self, 'dept_list'):
                self._refresh_departments_sidebar(force_rebuild=True)
        return has_changes
    def _get_persistent_unlocked_file(self):
        """الحصول على مسار ملف تخزين الأقسام المعتمدة على القرص لتثبيتها للأبد"""
        try:
            folder = Path(os.environ.get('APPDATA', os.environ.get('USERPROFILE', 'C:'))) / "ShareCOC"
            folder.mkdir(parents=True, exist_ok=True)
            return folder / "unlocked_departments.json"
        except Exception:
            return None
    def _load_persistent_unlocked_depts(self):
        """تحميل قائمة الأقسام المعتمدة لهذا الجهاز للأبد من القرص المحلي"""
        depts = set()
        try:
            if hasattr(self, 'state_mgr') and self.state_mgr:
                val = self.state_mgr.get_setting("unlocked_departments_json")
                if val:
                    loaded = json.loads(val)
                    if isinstance(loaded, list):
                        depts.update(loaded)
        except Exception:
            pass
        try:
            f = self._get_persistent_unlocked_file()
            if f and f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    depts.update(data)
        except Exception:
            pass
        return depts
    def _save_persistent_unlocked_dept(self, dept_name):
        """حفظ اعتماد القسم لهذا الجهاز على القرص بشكل دائم للأبد"""
        clean_name = str(dept_name).strip()
        if not clean_name:
            return
        if not hasattr(self, '_unlocked_pin_depts') or not isinstance(self._unlocked_pin_depts, set):
            self._unlocked_pin_depts = set()
        self._unlocked_pin_depts.add(clean_name)
        dept_list = list(self._unlocked_pin_depts)
        try:
            if hasattr(self, 'state_mgr') and self.state_mgr:
                self.state_mgr.set_setting("unlocked_departments_json", json.dumps(dept_list, ensure_ascii=False))
        except Exception:
            pass
        try:
            f = self._get_persistent_unlocked_file()
            if f:
                f.write_text(json.dumps(dept_list, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    def _is_access_hub_locally_unlocked(self, min_epoch=0):
        """فحص هل مركز بيانات Access معتمد ومسجل محلياً على هذا الحاسوب مع مطابقة إصدار الأمان"""
        try:
            folder = Path(os.environ.get('APPDATA', os.environ.get('USERPROFILE', 'C:'))) / "ShareCOC"
            f = folder / "access_hub_unlocked.json"
            if f and f.exists():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    saved_epoch = int(data.get("security_epoch", 0) or 0)
                    if min_epoch > 0 and saved_epoch < min_epoch:
                        return False
                    return bool(data.get("unlocked"))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, 'state_mgr') and self.state_mgr:
                val = self.state_mgr.get_setting("access_hub_unlocked")
                if val in ("1", "true", True):
                    return True
        except Exception:
            pass
        return False
    def _save_access_hub_local_unlock(self, epoch=0):
        """حفظ اعتماد مركز بيانات Access لهذا الحاسوب للأبد مع رقم إصدار الأمان"""
        try:
            if hasattr(self, 'state_mgr') and self.state_mgr:
                self.state_mgr.set_setting("access_hub_unlocked", "1")
        except Exception:
            pass
        try:
            folder = Path(os.environ.get('APPDATA', os.environ.get('USERPROFILE', 'C:'))) / "ShareCOC"
            folder.mkdir(parents=True, exist_ok=True)
            f = folder / "access_hub_unlocked.json"
            f.write_text(json.dumps({"unlocked": True, "security_epoch": epoch, "saved_at": time.time()}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    def _remove_access_hub_local_unlock(self):
        """سحب اعتماد مركز بيانات Access عند حذفه أو تغيير كلمة المرور من قِبل الأدمن"""
        try:
            if hasattr(self, 'state_mgr') and self.state_mgr:
                self.state_mgr.set_setting("access_hub_unlocked", "0")
        except Exception:
            pass
        try:
            folder = Path(os.environ.get('APPDATA', os.environ.get('USERPROFILE', 'C:'))) / "ShareCOC"
            f = folder / "access_hub_unlocked.json"
            if f and f.exists():
                f.unlink(missing_ok=True)
        except Exception:
            pass
    def _check_access_hub_permission(self):
        """فحص أمان مركز بيانات Access واعتماد الحاسوب لمرة واحدة فقط للأبد"""
        if not hasattr(self, 'client') or not self.client or not self.client.is_configured():
            return True
        my_guid = get_desktop_machine_guid()
        computer_name = os.environ.get('COMPUTERNAME', 'حاسوب-الموظف')
        perms_map = {}
        try:
            if hasattr(self.client, 'get_cached_folder_permissions'):
                perms_map = self.client.get_cached_folder_permissions() or {}
            elif hasattr(self.client, 'get_folder_permissions'):
                perms_map = self.client.get_folder_permissions() or {}
        except Exception:
            perms_map = {}
        rule = perms_map.get("مركز بيانات Access") or perms_map.get("__ACCESS_HUB__") or {}
        cloud_epoch = int(rule.get('security_epoch') or rule.get('securityEpoch') or 0)
        authed_devices = rule.get('authorizedDevices') or rule.get('authorized_devices') or []
        is_protected = bool(
            rule.get('is_protected') or 
            rule.get('isProtected') or 
            rule.get('enabled') or 
            rule.get('hasCreds') or
            rule.get('pinCode') or
            rule.get('deptUsername') or
            rule.get('deptPassword')
        )
        if not is_protected:
            return True
        is_cloud_authed = my_guid in authed_devices
        is_locally_authed = self._is_access_hub_locally_unlocked(min_epoch=cloud_epoch)
        # التحقق الفوري من سحب الاعتماد في حال قام الأدمن بحذف الجهاز أو تحديث الرمز السحابي
        if is_locally_authed:
            if isinstance(authed_devices, list) and authed_devices and my_guid not in authed_devices:
                self._remove_access_hub_local_unlock()
                is_locally_authed = False
        if is_cloud_authed and is_locally_authed:
            return True
        # مطالبة المستخدم بإدخال بيانات الأمان لمرة واحدة فقط
        dialog = QDialog(self)
        dialog.setWindowTitle("🔒 أمان مركز بيانات Access")
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setFixedWidth(390)
        vbox = QVBoxLayout(dialog)
        lbl_info = QLabel(f"مركز بيانات Access محمي برمز مرور وحساب خاص من إدارة الغرفة.\nيرجى تسجيل الدخول لمرة واحدة لاعتماد هذا الحاسوب ({computer_name}) للأبد:", dialog)
        lbl_info.setWordWrap(True)
        vbox.addWidget(lbl_info)
        vbox.addWidget(QLabel("اسم مستخدم مركز Access:", dialog))
        txt_u = QLineEdit(dialog)
        txt_u.setPlaceholderText("أدخل اسم المستخدم...")
        vbox.addWidget(txt_u)
        vbox.addWidget(QLabel("رمز / كلمة مرور مركز Access:", dialog))
        txt_p = QLineEdit(dialog)
        txt_p.setEchoMode(QLineEdit.EchoMode.Password)
        txt_p.setPlaceholderText("أدخل كلمة المرور أو الرمز السري...")
        vbox.addWidget(txt_p)
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("اعتماد الحاسوب ودخول المركز", dialog)
        btn_cancel = QPushButton("إلغاء", dialog)
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        vbox.addLayout(btn_box)
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        ent_u = txt_u.text().strip()
        ent_p = txt_p.text().strip()
        if not ent_p:
            QMessageBox.critical(self, "تنبيه ⚠️", "يرجى إدخال كلمة المرور أو الرمز السري لمركز بيانات Access.")
            return False
        # التحقق المباشر عبر السحابة لضمان دقة الرمز وتسجيل الجهاز فورياً
        try:
            import requests
            r = requests.post(
                "https://web-dashboard-pi-self.vercel.app/api/drive/permissions",
                json={
                    "action": "REGISTER_ACCESS_HUB_DEVICE",
                    "username": ent_u,
                    "password": ent_p,
                    "machineGuid": my_guid,
                    "deviceName": computer_name,
                    "os": "Windows 11 Desktop",
                    "user": computer_name
                },
                timeout=12
            )
            data = r.json()
            if r.status_code == 200 and data.get("success") and data.get("authorized"):
                # نجاح التحقق والاعتماد
                self._save_access_hub_local_unlock(epoch=cloud_epoch)
                if my_guid not in authed_devices:
                    authed_devices.append(my_guid)
                QMessageBox.information(self, "تم الاعتماد بنجاح ✅", f"تم اعتماد هذا الحاسوب ({computer_name}) وتوثيقه لدى مسؤول النظام بنجاح!")
                return True
            else:
                err_msg = data.get("error") or "بيانات الدخول لمركز بيانات Access غير صحيحة، يرجى مراجعة إدارة الغرفة."
                QMessageBox.critical(self, "خطأ في تسجيل الدخول ❌", err_msg)
                return False
        except Exception as e:
            QMessageBox.critical(self, "خطأ في الاتصال ❌", f"تعذر الاتصال بالسحابة للتحقق من الاعتماد:\n{e}")
            return False
        return True
    def _remove_persistent_unlocked_dept(self, dept_name):
        """إلغاء وسحب اعتماد القسم محلياً عند حذفه من قِبل الأدمن في لوحة التحكم"""
        clean_name = str(dept_name).strip()
        if not clean_name:
            return
        if hasattr(self, '_unlocked_pin_depts') and isinstance(self._unlocked_pin_depts, set):
            self._unlocked_pin_depts.discard(clean_name)
            dept_list = list(self._unlocked_pin_depts)
        else:
            dept_list = []
        try:
            if hasattr(self, 'state_mgr') and self.state_mgr:
                self.state_mgr.set_setting("unlocked_departments_json", json.dumps(dept_list, ensure_ascii=False))
        except Exception:
            pass
        try:
            f = self._get_persistent_unlocked_file()
            if f:
                f.write_text(json.dumps(dept_list, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    def _check_department_permission(self, dept_name=None, action='write'):
        """فحص الصلاحيات الإدارية المفصلة (9 صلاحيات + أمان القسم واعتماد الحاسوب لمرة واحدة)"""
        target_dept = dept_name or self.active_dept_name
        if not target_dept or target_dept == "__ALL__":
            return True
        if not hasattr(self, 'client') or not self.client or not self.client.is_configured():
            return True
        try:
            if hasattr(self.client, 'get_cached_folder_permissions'):
                perms_map = self.client.get_cached_folder_permissions()
            elif hasattr(self.client, 'get_folder_permissions'):
                perms_map = self.client.get_folder_permissions()
            else:
                perms_map = {}
            if perms_map:
                rule = perms_map.get(target_dept)
                if rule:
                    # 1. فحص بيانات الأمان للقسم (يوزر وباسورد أو رمز PIN واعتماد الحاسوب لمرة واحدة)
                    pin_code = str(rule.get('pinCode') or rule.get('pin_code') or '').strip()
                    dept_user = str(rule.get('deptUsername') or rule.get('dept_username') or '').strip()
                    dept_pass = str(rule.get('deptPassword') or rule.get('dept_password') or pin_code).strip()
                    authed_devices = rule.get('authorizedDevices') or rule.get('authorized_devices') or []
                    my_guid = get_desktop_machine_guid()
                    computer_name = os.environ.get('COMPUTERNAME', 'حاسوب-الموظف')
                    is_protected = bool(dept_user or dept_pass or pin_code)
                    # فحص الاعتماد السحابي والمحلي
                    is_cloud_authed = my_guid in authed_devices
                    is_locally_authed = target_dept in getattr(self, '_unlocked_pin_depts', set())
                    # تتبع تأكيد الاعتماد السحابي لكشف إذا قام الأدمن بحذف الجهاز لاحقاً
                    if not hasattr(self, '_cloud_registration_confirmed'):
                        self._cloud_registration_confirmed = {}
                    if is_cloud_authed:
                        self._cloud_registration_confirmed[target_dept] = True
                        if not is_locally_authed:
                            self._save_persistent_unlocked_dept(target_dept)
                            is_locally_authed = True
                    else:
                        # إذا كان مسجلاً سحابياً مسبقاً وتأكد حذفه من قِبل الأدمن من قائمة السحابة
                        was_confirmed = self._cloud_registration_confirmed.get(target_dept, False)
                        cloud_devs = getattr(self.client, '_raw_cloud_devices', None) if hasattr(self, 'client') and self.client else None
                        if was_confirmed and cloud_devs is not None and isinstance(cloud_devs, list) and len(cloud_devs) > 0:
                            has_dev = any(d.get('machineGuid') == my_guid or d.get('id') == my_guid for d in cloud_devs)
                            if not has_dev:
                                self._remove_persistent_unlocked_dept(target_dept)
                                is_locally_authed = False
                                self._cloud_registration_confirmed[target_dept] = False
                    is_already_authed = is_cloud_authed or is_locally_authed
                    if is_protected and not is_already_authed:
                        if dept_user:
                            dialog = QDialog(self)
                            dialog.setWindowTitle(f"🔒 أمان دخول القسم ({target_dept})")
                            dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                            dialog.setFixedWidth(380)
                            vbox = QVBoxLayout(dialog)
                            lbl_info = QLabel(f"هذا القسم ({target_dept}) محمي بحساب خاص من الإدارة.\nيرجى تسجيل الدخول لمرة واحدة لاعتماد هذا الحاسوب ({computer_name}) للأبد:", dialog)
                            lbl_info.setWordWrap(True)
                            vbox.addWidget(lbl_info)
                            vbox.addWidget(QLabel("اسم مستخدم القسم:", dialog))
                            txt_u = QLineEdit(dialog)
                            txt_u.setPlaceholderText("أدخل اسم المستخدم...")
                            vbox.addWidget(txt_u)
                            vbox.addWidget(QLabel("رمز / كلمة مرور القسم:", dialog))
                            txt_p = QLineEdit(dialog)
                            txt_p.setEchoMode(QLineEdit.EchoMode.Password)
                            txt_p.setPlaceholderText("أدخل الرمز أو كلمة المرور...")
                            vbox.addWidget(txt_p)
                            btn_box = QHBoxLayout()
                            btn_ok = QPushButton("اعتماد الحاسوب ودخول القسم", dialog)
                            btn_cancel = QPushButton("إلغاء", dialog)
                            btn_box.addWidget(btn_ok)
                            btn_box.addWidget(btn_cancel)
                            vbox.addLayout(btn_box)
                            btn_ok.clicked.connect(dialog.accept)
                            btn_cancel.clicked.connect(dialog.reject)
                            if dialog.exec() != QDialog.DialogCode.Accepted:
                                return False
                            ent_u = txt_u.text().strip()
                            ent_p = txt_p.text().strip()
                            if ent_u.lower() != dept_user.lower() or ent_p != dept_pass:
                                QMessageBox.critical(self, "خطأ في تسجيل الدخول ❌", "اسم المستخدم أو كلمة المرور غير صحيحة.")
                                return False
                        else:
                            entered_pin, ok = QInputDialog.getText(
                                self,
                                f"🔒 قسم محمي برمز سري ({target_dept})",
                                f"هذا القسم ({target_dept}) محمي برمز مرور خاص من الإدارة.\nيرجى إدخال الرمز السري للمتابعة واعتماد هذا الحاسوب ({computer_name}) للأبد:",
                                QLineEdit.EchoMode.Password
                            )
                            if not ok:
                                return False
                            clean_entered = entered_pin.strip()
                            valid_pin = clean_entered in (pin_code, dept_pass)
                            if not valid_pin:
                                QMessageBox.critical(self, "رمز خاطئ ❌", "الرمز السري الذي أدخلته غير صحيح.")
                                return False
                        # حفظ دائم على القرص المحلي لعدم طلب الرمز مرة أخرى إطلاقاً
                        self._save_persistent_unlocked_dept(target_dept)
                        # تسجيل واعتماد الجهاز سحابياً في لوحة تحكم الأدمن في Google Drive
                        rule.setdefault('authorized_devices', [])
                        if my_guid not in rule['authorized_devices']:
                            rule['authorized_devices'].append(my_guid)
                        if 'authorizedDevices' in rule and my_guid not in rule['authorizedDevices']:
                            rule['authorizedDevices'].append(my_guid)
                        if hasattr(self, 'client') and self.client:
                            if hasattr(self.client, '_cached_permissions') and isinstance(self.client._cached_permissions, dict):
                                cp = self.client._cached_permissions.get(target_dept)
                                if isinstance(cp, dict):
                                    ad = cp.setdefault('authorizedDevices', [])
                                    if my_guid not in ad:
                                        ad.append(my_guid)
                            import threading
                            threading.Thread(
                                target=self.client.authorize_device_for_dept,
                                args=(target_dept, my_guid, computer_name, "Windows Desktop"),
                                daemon=True
                            ).start()
                        # المزامنة المباشرة عبر API الويب لضمان تسجيل وظهور الجهاز في لوحة الأدمن للأبد
                        entered_user = ent_u if dept_user else ""
                        entered_pass = ent_p if dept_user else clean_entered
                        def _sync_dept_reg_to_web():
                            try:
                                import requests
                                requests.post(
                                    "https://web-dashboard-pi-self.vercel.app/api/drive/permissions",
                                    json={
                                        "action": "REGISTER_DEPARTMENT_DEVICE",
                                        "departmentName": target_dept,
                                        "username": entered_user,
                                        "password": entered_pass,
                                        "machineGuid": my_guid,
                                        "deviceName": computer_name,
                                        "os": "Windows 11 Desktop",
                                        "user": computer_name
                                    },
                                    timeout=8
                                )
                            except Exception:
                                pass
                        import threading
                        threading.Thread(target=_sync_dept_reg_to_web, daemon=True).start()
                        # تحديث فوري للأيقونات في القائمة الجانبية (إظهار 🔓)
                        self._refresh_departments_sidebar()
                    # 1.5 دمج الصلاحيات المخصصة لهذا الجهاز بالتحديد (Per-device Granular Permissions)
                    my_dev_custom = None
                    if hasattr(self, 'client') and self.client:
                        raw_devs = getattr(self.client, '_raw_cloud_devices', []) or []
                        my_dev_custom = next((d for d in raw_devs if isinstance(d, dict) and (d.get('machineGuid') == my_guid or d.get('id') == my_guid)), None)
                    if my_dev_custom and isinstance(my_dev_custom.get('departmentPermissions'), dict):
                        dept_custom = my_dev_custom['departmentPermissions'].get(target_dept)
                        if isinstance(dept_custom, dict):
                            if dept_custom.get('allowed') is False:
                                QMessageBox.warning(
                                    self,
                                    f"قسم محظور 🛡️ ({target_dept})",
                                    f"تم تقييد وصول هذا الحاسوب إلى قسم ({target_dept}) بواسطة مسؤول النظام."
                                )
                                return False
                            for k, v in dept_custom.items():
                                if v is not None:
                                    rule[k] = v
                                    s_key = "".join(["_" + c.lower() if c.isupper() else c for c in k]).lstrip("_")
                                    rule[s_key] = v
                    # 2. فحص الصلاحيات التسع التفصيلية
                    action_checks = {
                        'view': (
                            rule.get('canView', rule.get('can_view', True)),
                            "عذراً، هذا القسم مغلق للعرض حالياً بأمر مسؤول النظام."
                        ),
                        'download': (
                            rule.get('canDownload', rule.get('can_download', True)),
                            "عذراً، صلاحية فتح أو تنزيل الملفات مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'open': (
                            rule.get('canDownload', rule.get('can_download', True)),
                            "عذراً، صلاحية فتح المستندات مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'upload': (
                            rule.get('canUpload', rule.get('can_upload', rule.get('can_write', True))),
                            "عذراً، صلاحية رفع وإضافة ملفات جديدة مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'create_folder': (
                            rule.get('canCreateFolder', rule.get('can_create_folder', rule.get('can_write', True))),
                            "عذراً، صلاحية إنشاء مجلدات فرعية مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'edit': (
                            rule.get('canEdit', rule.get('can_edit', rule.get('can_write', True))),
                            "عذراً، صلاحية التعديل على محتوى الملفات مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'rename': (
                            rule.get('canRename', rule.get('can_rename', rule.get('can_write', True))),
                            "عذراً، صلاحية إعادة تسمية الملفات والمجلدات مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'move': (
                            rule.get('canMove', rule.get('can_move', rule.get('can_write', True))),
                            "عذراً، صلاحية نقل الملفات والمجلدات مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'delete': (
                            rule.get('canDelete', rule.get('can_delete', True)),
                            "عذراً، صلاحية نقل الملفات والمجلدات إلى سلة المحذوفات مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'permanent_delete': (
                            rule.get('canPermanentDelete', rule.get('can_permanent_delete', rule.get('can_delete', True))),
                            "عذراً، صلاحية الحذف النهائي وتفريغ سلة المحذوفات مقيدة في هذا القسم بأمر الإدارة."
                        ),
                        'write': (
                            rule.get('canUpload', rule.get('can_write', True)),
                            "عذراً، هذا القسم مخصص للقراءة فقط بواسطة مسؤول النظام."
                        ),
                    }
                    if action in action_checks:
                        allowed, msg = action_checks[action]
                        if not allowed:
                            QMessageBox.warning(
                                self,
                                f"صلاحية مقيدة من الأدمن 🛡️ ({target_dept})",
                                f"{msg}\n\nالقسم: {target_dept}"
                            )
                            return False
        except Exception as e:
            print(f"[Check Permission Error]: {e}")
        return True
    def _refresh_departments_sidebar(self, force_rebuild=False):
        """تحديث شريط الأقسام الأفقي الحديث مع شارات الأعداد وحالة الحماية"""
        total_all_files = getattr(self, '_total_root_items_cache', 0)
        dept_counts = getattr(self, '_dept_counts_cache', {})
        trash_cnt = getattr(self, '_trash_count_cache', 0)
        # تحديث زر كافة الأقسام
        if hasattr(self, 'pill_all_depts'):
            self.pill_all_depts.setText(f"كافة الأقسام ({total_all_files})")
            if self.active_dept_name is None:
                self.pill_all_depts.setStyleSheet("""
                    QPushButton {
                        background-color: #14372e; color: #FFFFFF; border: none;
                        border-radius: 8px; padding: 7px 14px; font-weight: bold; font-size: 11.5px;
                    }
                """)
            else:
                self.pill_all_depts.setStyleSheet("""
                    QPushButton {
                        background-color: #FFFFFF; color: #1B1F24; border: 1px solid #E4E7EC;
                        border-radius: 8px; padding: 7px 14px; font-weight: 600; font-size: 11.5px;
                    }
                    QPushButton:hover { background-color: #F7F8FA; }
                """)
        # تحديث كبسولات الأقسام في الشريط الأفقي
        if hasattr(self, 'dept_pills_layout'):
            while self.dept_pills_layout.count() > 2:
                it = self.dept_pills_layout.takeAt(1)
                w = it.widget()
                if w:
                    w.deleteLater()
            for dept in self.departments_list:
                name = dept['name']
                cnt = dept_counts.get(name, 0)
                btn = QPushButton(f"📁 {name}  {cnt}")
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                if self.active_dept_name == name:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #14372e; color: #FFFFFF; border: none;
                            border-radius: 8px; padding: 7px 14px; font-weight: bold; font-size: 11.5px;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FFFFFF; color: #1B1F24; border: 1px solid #E4E7EC;
                            border-radius: 8px; padding: 7px 14px; font-weight: 600; font-size: 11.5px;
                        }
                        QPushButton:hover { background-color: #F7F8FA; }
                    """)
                btn.clicked.connect(lambda _, n=name: self._on_department_clicked(n))
                self.dept_pills_layout.insertWidget(self.dept_pills_layout.count() - 1, btn)
        # تحديث كبسولة المحذوفات
        if hasattr(self, 'tab_trash'):
            self.tab_trash.setText(f"🗑️ المحذوفات ({trash_cnt})")
            if self.active_filter == "TRASH":
                self.tab_trash.setStyleSheet("""
                    QPushButton {
                        background-color: #F04438; color: #FFFFFF; border: 1px solid #F04438;
                        border-radius: 8px; padding: 7px 14px; font-weight: bold; font-size: 11.5px;
                    }
                """)
            else:
                self.tab_trash.setStyleSheet("""
                    QPushButton {
                        background-color: #FFFFFF; color: #667085; border: 1px solid #E4E7EC;
                        border-radius: 8px; padding: 7px 14px; font-weight: 600; font-size: 11.5px;
                    }
                    QPushButton:hover { background-color: #FEF3F2; color: #F04438; border-color: #FECDCA; }
                """)
        # الحفاظ على dept_list لضمان التوافق
        if hasattr(self, 'dept_list'):
            self.dept_list.blockSignals(True)
            self.dept_list.clear()
            item_all = QListWidgetItem(f"كافة الأقسام ({total_all_files})")
            item_all.setData(Qt.ItemDataRole.UserRole, "__ALL__")
            self.dept_list.addItem(item_all)
            for dept in self.departments_list:
                name = dept['name']
                cnt = dept_counts.get(name, 0)
                item = QListWidgetItem(f"{name} ({cnt})")
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.dept_list.addItem(item)
            self.dept_list.blockSignals(False)
    def _on_department_clicked(self, item_or_key):
        """عند اختيار قسم من القائمة الجانبية: عزل المستندات فوراً لعرض مستندات هذا القسم فقط أو عرض كافة الملفات"""
        if isinstance(item_or_key, str):
            dept_key = item_or_key
        else:
            try:
                dept_key = item_or_key.data(Qt.ItemDataRole.UserRole)
            except Exception:
                dept_key = str(item_or_key)
        if dept_key == "__ALL__" or not dept_key:
            self.active_dept_name = None
            self.current_subpath = Path(".")
        else:
            if not self._check_department_permission(dept_key, action='view'):
                self._refresh_departments_sidebar()
                return
            self.active_dept_name = dept_key
            self.current_subpath = Path(dept_key)
            target = self.sync_folder / self.current_subpath
            target.mkdir(parents=True, exist_ok=True)
        self._clear_all_selections(refresh_ui=False)
        self._reset_scroll_on_render = True
        self._force_full_render = True
        self._nav_cache_ok = True
        self._update_breadcrumb()
        if self.active_filter == "TRASH":
            self._render_trash_table()
        else:
            self._apply_instant_snapshot_render(self.current_subpath)
            self._refresh_file_list()
    def _show_department_context_menu(self, pos):
        """القائمة المنبثقة للقسم (استعراض، حذف القسم بالكامل)"""
        item = self.dept_list.itemAt(pos)
        if not item:
            return
        dept_key = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #ffffff; color: #162420; border: 1.5px solid #d5dfdb; border-radius: 8px; padding: 4px; }
            QMenu::item { padding: 8px 24px; border-radius: 4px; font-size: 12px; font-weight: 600; }
            QMenu::item:selected { background-color: #f0f6f4; color: #14372e; font-weight: bold; }
        """)
        if dept_key == "__ALL__":
            act_enter = menu.addAction("📂 الدخول إلى كافة الملفات والمجلدات")
            act_open_win = menu.addAction("📁 استعراض مجلد الأرشيف الشامل في Windows")
            action = menu.exec(self.dept_list.mapToGlobal(pos))
            if action == act_enter:
                self._on_department_clicked(item)
            elif action == act_open_win:
                os.startfile(str(self.sync_folder))
            return
        act_enter = menu.addAction(f"📂 الدخول إلى قسم {dept_key}")
        act_open_win = menu.addAction("📁 استعراض مجلد القسم في Windows")
        act_rename = menu.addAction(f"✏️ تعديل اسم القسم ({dept_key})...")
        menu.addSeparator()
        act_del = menu.addAction(f"🗑️ حذف قسم '{dept_key}' بالكامل إلى سلة المحذوفات")
        action = menu.exec(self.dept_list.mapToGlobal(pos))
        if action == act_enter:
            self._on_department_clicked(item)
        elif action == act_open_win:
            dept_dir = (self.sync_folder / dept_key).resolve()
            dept_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(dept_dir))
        elif action == act_rename:
            self._rename_department(dept_key)
        elif action == act_del:
            self._delete_department(dept_key)
    def _on_refresh_clicked(self):
        """تحديث فوري وسحب أي ملفات جديدة من السحابة وتحديث كافة الجداول وسلة المحذوفات"""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳ جاري المزامنة...")
        if hasattr(self, 'lbl_watcher'):
            self.lbl_watcher.setText("⚡ المزامنة: جاري فحص ومزامنة السحابة...")
        def do_sync():
            try:
                if self.sync_engine and hasattr(self.sync_engine, 'sync_now'):
                    self.sync_engine.sync_now(timeout=60)
                elif self.sync_engine:
                    self.sync_engine.pull_remote_changes()
                try:
                    from access_hub_widget import sync_cloud_mutations_to_local
                    sync_cloud_mutations_to_local(force=True)
                except Exception as ex:
                    print(f"[Access mutations sync error]: {ex}")
            except Exception as e:
                print(f"[Manual refresh error]: {e}")
            finally:
                self.bridge.refresh_finished.emit()
        import threading
        threading.Thread(target=do_sync, daemon=True).start()
    def _on_refresh_finished(self):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("✅ تم التحديث")
        if hasattr(self, 'lbl_watcher'):
            self.lbl_watcher.setText("⚡ المزامنة: متصل ومحدث بالكامل مع السحابة")
        self._refresh_departments_sidebar()
        self._refresh_file_list()
        if self.active_filter == "TRASH":
            self._render_trash_table()
        if hasattr(self, 'access_hub_page') and self.access_hub_page:
            try:
                self.access_hub_page.load_data()
            except Exception:
                pass
        QTimer.singleShot(1800, lambda: self.btn_refresh.setText("🔄 تحديث"))
    def _show_add_department_dialog(self):
        """نافذة إنشاء قسم إداري جديد للغرفة"""
        dialog = QDialog(self)
        dialog.setWindowTitle("إنشاء قسم إداري جديد")
        dialog.resize(500, 260)
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
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        title_lbl = QLabel("🏛️ إضافة قسم إداري جديد لغرفة تجارة كربلاء")
        title_lbl.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {GOV_GREEN};")
        layout.addWidget(title_lbl)
        txt_name = QLineEdit()
        txt_name.setPlaceholderText("أدخل اسم القسم الجديد (مثال: شعبة التدقيق والرقابة)...")
        layout.addWidget(txt_name)
        chips_lbl = QLabel("أقسام مقترحة لهيكل الغرفة الإداري:")
        chips_lbl.setFont(QFont("Cairo", 10))
        chips_lbl.setStyleSheet("color: #566c65;")
        layout.addWidget(chips_lbl)
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        sug_depts = ["شعبة العقود والمناقصات", "شعبة التدقيق والرقابة", "شعبة شؤون المنتسبين", "شعبة العلاقات الدولية", "خدمة المواطنين"]
        for sug in sug_depts:
            btn_s = QPushButton(sug)
            btn_s.setObjectName("btnSuggestionChip")
            btn_s.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_s.clicked.connect(lambda _, s=sug: txt_name.setText(s))
            chips_row.addWidget(btn_s)
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
        btn_create = QPushButton("🏛️ إنشاء القسم")
        btn_create.setObjectName("btnGovPrimary")
        def do_create_dept():
            d_name = txt_name.text().strip()
            if not d_name:
                QMessageBox.warning(dialog, "تنبيه", "يرجى إدخال اسم القسم.")
                return
            invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
            if any(c in d_name for c in invalid_chars):
                QMessageBox.warning(dialog, "تنبيه", "اسم القسم يحتوي على رموز غير صالحة.")
                return
            if any(d['name'] == d_name for d in self.departments_list):
                QMessageBox.warning(dialog, "تنبيه", f"القسم '{d_name}' موجود بالفعل في قائمة الأقسام.")
                return
            try:
                dept_folder = self.sync_folder / d_name
                dept_folder.mkdir(parents=True, exist_ok=True)
                if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                    self.sync_engine.clear_tombstone(d_name)
                self.departments_list.append({"name": d_name, "icon": "🏛️"})
                self.state_mgr.set_departments(self.departments_list)
                # مزامنة إنشاء القسم فوراً إلى السحابة في خيط خلفي
                if self.client and self.client.is_configured() and hasattr(self.client, 'create_folder'):
                    self._run_cloud_async(self.client.create_folder, d_name)
                dialog.accept()
                # التبديل فوراً إلى القسم الجديد المنشأ
                self.active_dept_name = d_name
                self.current_subpath = Path(d_name)
                self._refresh_departments_sidebar()
                self._reset_scroll_on_render = True
                self._force_full_render = True
                self._update_breadcrumb()
                self._refresh_file_list()
                QMessageBox.information(self, "تم إنشاء القسم", f"تم إنشاء قسم '{d_name}' ومجلده المعزول بنجاح.")
            except Exception as e:
                QMessageBox.critical(dialog, "خطأ", f"تعذر إنشاء القسم:\n{e}")
        btn_create.clicked.connect(do_create_dept)
        btn_row.addWidget(btn_create)
        layout.addLayout(btn_row)
        dialog.exec()
    def _rename_department(self, old_dept_name):
        """تعديل اسم قسم إداري وتحديث مجلده التخزيني على الجهاز ومزامنته مع السحابة"""
        if not self._check_department_permission(old_dept_name, action='write'):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("✏️ تعديل اسم القسم الإداري")
        dialog.resize(480, 230)
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
        title_lbl = QLabel(f"🏛️ تعديل اسم القسم: {old_dept_name}")
        title_lbl.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {GOV_GREEN};")
        layout.addWidget(title_lbl)
        txt_name = QLineEdit(old_dept_name)
        txt_name.selectAll()
        layout.addWidget(txt_name)
        hint_lbl = QLabel("⚠️ سيتم تغيير اسم مجلد القسم في موقع التخزين على الجهاز وكافة ملفاته فوراً.")
        hint_lbl.setFont(QFont("Cairo", 9))
        hint_lbl.setStyleSheet("color: #64748b;")
        layout.addWidget(hint_lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setObjectName("btnGovSecondary")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)
        btn_save = QPushButton("💾 حفظ التعديل")
        btn_save.setObjectName("btnGovPrimary")
        def do_save():
            new_name = txt_name.text().strip()
            if not new_name:
                QMessageBox.warning(dialog, "تنبيه", "يرجى إدخال اسم القسم الجديد.")
                return
            if new_name == old_dept_name:
                dialog.accept()
                return
            invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
            if any(c in new_name for c in invalid_chars):
                QMessageBox.warning(dialog, "تنبيه", "اسم القسم يحتوي على رموز غير صالحة للويندوز.")
                return
            if new_name == "__ALL__":
                QMessageBox.warning(dialog, "تنبيه", "هذا الاسم محجوز للنظام.")
                return
            if any(d['name'].lower() == new_name.lower() for d in self.departments_list if d['name'] != old_dept_name):
                QMessageBox.warning(dialog, "تنبيه", f"يوجد قسم آخر باسم '{new_name}' بالفعل.")
                return
            old_dir = (self.sync_folder / old_dept_name).resolve()
            new_dir = (self.sync_folder / new_name).resolve()
            # 1. تغيير اسم المجلد الفعلي في القرص الصلب (موقع التخزين في الجهاز)
            if old_dir.exists():
                try:
                    os.rename(str(old_dir), str(new_dir))
                except PermissionError:
                    QMessageBox.critical(
                        dialog, "تعذر التعديل",
                        "تعذر تغيير اسم مجلد القسم على الجهاز لأن أحد الملفات داخله مفتوح حالياً في برنامج آخر (مثل Word أو Excel).\n\nيرجى إغلاق المستندات المفتوحة ثم إعادة المحاولة."
                    )
                    return
                except Exception as e:
                    QMessageBox.critical(dialog, "خطأ", f"حدث خطأ أثناء تغيير اسم المجلد على الجهاز:\n{e}")
                    return
            else:
                try:
                    new_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(dialog, "خطأ", f"تعذر إنشاء المجلد الجديد:\n{e}")
                    return
            # 2. تحديث قائمة الأقسام في الذاكرة والإعدادات المحلية
            for d in self.departments_list:
                if d['name'] == old_dept_name:
                    d['name'] = new_name
            self.state_mgr.set_departments(self.departments_list)
            # 3. تحديث قاعدة البيانات المحلية (الملفات وسلة المحذوفات)
            self.state_mgr.rename_department(old_dept_name, new_name)
            # 4. تحديث المسار النشط إذا كان المستخدم داخل هذا القسم
            if self.active_dept_name == old_dept_name:
                self.active_dept_name = new_name
                if self.current_subpath == Path(old_dept_name):
                    self.current_subpath = Path(new_name)
                elif str(self.current_subpath).startswith(old_dept_name):
                    try:
                        rel = self.current_subpath.relative_to(old_dept_name)
                        self.current_subpath = Path(new_name) / rel
                    except Exception:
                        self.current_subpath = Path(new_name)
            # 5. مزامنة تعديل اسم القسم مع السحابة في خيط خلفي (تغيير الاسم بدلاً من الحذف!)
            if self.client and self.client.is_configured():
                if hasattr(self.client, 'rename_folder'):
                    self._run_cloud_async(self.client.rename_folder, old_dept_name, new_name)
                elif hasattr(self.client, 'create_folder'):
                    self._run_cloud_async(self.client.create_folder, new_name)
            dialog.accept()
            self._refresh_departments_sidebar()
            self._reset_scroll_on_render = True
            self._force_full_render = True
            self._update_breadcrumb()
            self._refresh_file_list()
            QMessageBox.information(self, "تم التعديل", f"تم تعديل اسم القسم إلى '{new_name}' وتحديث موقعه على الجهاز بنجاح.")
        btn_save.clicked.connect(do_save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)
        dialog.exec()
    def _delete_department(self, dept_name):
        """حذف قسم إداري بالكامل ونقل كافة مستنداته ومجلداته إلى سلة المحذوفات بأمان"""
        if not self._check_department_permission(dept_name, action='delete'):
            return
        reply = QMessageBox.question(
            self, "تأكيد حذف القسم الإداري",
            f"هل أنت متأكد من حذف قسم '{dept_name}' وكافة مجلداته ومستنداته؟\n\n"
            f"⚠️ سيتم نقله بالكامل إلى سلة المحذوفات، ويمكنك استعادته في أي وقت.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            dept_folder = (self.sync_folder / dept_name).resolve()
            trash_dir = self.state_mgr.db_dir / 'trash'
            trash_dir.mkdir(parents=True, exist_ok=True)
            trash_dest = trash_dir / f"{int(time.time())}_{dept_name}"
            if dept_folder.exists():
                shutil.move(str(dept_folder), str(trash_dest))
            self.state_mgr.add_to_trash(dept_name, dept_name, str(trash_dest), 0, item_type='department', dept_name=dept_name)
            self.departments_list = [d for d in self.departments_list if d['name'] != dept_name]
            self.state_mgr.set_departments(self.departments_list)
            if self.sync_engine and hasattr(self.sync_engine, 'note_local_delete'):
                self.sync_engine.note_local_delete(dept_name, is_folder=True)
            elif self.client and self.client.is_configured():
                fn = self.client.delete_folder if hasattr(self.client, 'delete_folder') else self.client.delete_file
                self._run_cloud_async(fn, dept_name)
            if self.active_dept_name == dept_name:
                if self.departments_list:
                    self.active_dept_name = self.departments_list[0]['name']
                    self.current_subpath = Path(self.active_dept_name)
                else:
                    self.active_dept_name = None
                    self.current_subpath = Path(".")
            self._refresh_departments_sidebar()
            self._reset_scroll_on_render = True
            self._force_full_render = True
            self._update_breadcrumb()
            self._refresh_file_list()
            QMessageBox.information(self, "تم الحذف", f"تم نقل قسم '{dept_name}' إلى سلة المحذوفات بنجاح.")
    def _apply_instant_snapshot_render(self, target_subpath):
        """عرض فوري متزامن فائق السرعة من الذاكرة للقطة السحابية دون انتظار الفحص الخلفي (< 15ms)"""
        try:
            if not (hasattr(self, 'client') and self.client and hasattr(self.client, 'peek_snapshot')):
                return False
            cached_snap = self.client.peek_snapshot()
            if not (cached_snap and hasattr(cached_snap, 'folders')):
                return False
            from gdrive_client import is_ignored_name
            norm_sub = str(target_subpath).replace("\\", "/").strip("/").strip(".")
            if norm_sub in (".", ""):
                norm_sub = ""
            snap_idx = _get_snapshot_index(cached_snap)
            child_dirs = [fld for fld in snap_idx['child_dirs'].get(norm_sub, []) if not is_ignored_name(fld.split("/")[-1])]
            unlocked_pins = getattr(self, '_unlocked_pin_depts', set())
            perms_map = {}
            try:
                if hasattr(self.client, 'get_cached_folder_permissions'):
                    perms_map = self.client.get_cached_folder_permissions() or {}
                elif hasattr(self.client, 'get_folder_permissions'):
                    perms_map = self.client.get_folder_permissions() or {}
            except Exception:
                pass
            def _can_show_dept_instant(d_name):
                if norm_sub != "":
                    return True
                if not isinstance(perms_map, dict) or d_name not in perms_map:
                    return True
                rule = perms_map.get(d_name) or {}
                if not rule.get('canView', rule.get('can_view', True)):
                    return False
                pin_c = str(rule.get('pinCode') or rule.get('pin_code') or '').strip()
                dept_u = str(rule.get('deptUsername') or rule.get('dept_username') or '').strip()
                dept_p = str(rule.get('deptPassword') or rule.get('dept_password') or '').strip()
                authed_d = rule.get('authorizedDevices') or rule.get('authorized_devices') or []
                my_g = get_desktop_machine_guid()
                is_p = bool(pin_c or dept_u or dept_p)
                is_u = (d_name in unlocked_pins) or (my_g in authed_d)
                if is_p and not is_u:
                    return False
                return True
            if norm_sub == "":
                visible_root_dirs = [d for d in child_dirs if _can_show_dept_instant(d.split("/")[-1])]
                if len(visible_root_dirs) == 1:
                    only_dept = visible_root_dirs[0]
                    sub_of_only = [fld for fld in snap_idx['child_dirs'].get(only_dept, []) if not is_ignored_name(fld.split("/")[-1])]
                    if sub_of_only:
                        child_dirs = sub_of_only
            folders_list = []
            for d_rel in sorted(child_dirs):
                d_name = d_rel.split("/")[-1]
                root_dept_name = d_rel.split("/")[0]
                if not _can_show_dept_instant(root_dept_name):
                    continue
                rec_file_cnt = snap_idx['rec_files'].get(d_rel, 0)
                sub_dir_cnt = len([x for x in snap_idx['child_dirs'].get(d_rel, []) if not is_ignored_name(x.split("/")[-1])])
                local_dir_path = os.path.normpath(os.path.join(str(self.sync_folder), d_rel))
                folders_list.append({
                    'file_name': d_name,
                    'is_folder': True,
                    'item_count': rec_file_cnt,
                    'child_count': sub_dir_cnt,
                    'relative_path': d_rel,
                    'abs_path': local_dir_path,
                    'file_size': 0,
                    'sync_status': 'synced',
                    'last_modified_local': ''
                })
            files_list = []
            scope_files_list = []
            is_all_archive = (self.active_dept_name is None and target_subpath == Path("."))
            for f_rel, meta in cached_snap.files.items():
                f_name = f_rel.split("/")[-1]
                if is_ignored_name(f_name):
                    continue
                dept_p = f_rel.split("/")[0] if "/" in f_rel else ""
                if dept_p and not _can_show_dept_instant(dept_p):
                    continue
                in_scope = is_all_archive or (f_rel == norm_sub or f_rel.startswith(norm_sub + "/"))
                if not in_scope:
                    continue
                full_p = os.path.normpath(os.path.join(str(self.sync_folder), f_rel))
                f_size = int(meta.get('size', 0) if isinstance(meta, dict) else getattr(meta, 'size', 0) or 0)
                mtime_iso = (meta.get('modifiedTime', '') if isinstance(meta, dict) else getattr(meta, 'modified_iso', '')) or ''
                f_entry = {
                    'file_name': f_name,
                    'is_folder': False,
                    'relative_path': f_rel,
                    'abs_path': full_p,
                    'file_size': f_size,
                    'sync_status': 'synced',
                    'last_modified_local': mtime_iso
                }
                scope_files_list.append(f_entry)
                if is_all_archive:
                    files_list.append(f_entry)
            if not is_all_archive:
                for f_rel, meta in snap_idx['child_files'].get(norm_sub, []):
                    f_name = f_rel.split("/")[-1]
                    if is_ignored_name(f_name):
                        continue
                    full_p = os.path.normpath(os.path.join(str(self.sync_folder), f_rel))
                    f_size = int(meta.get('size', 0) if isinstance(meta, dict) else getattr(meta, 'size', 0) or 0)
                    mtime_iso = (meta.get('modifiedTime', '') if isinstance(meta, dict) else getattr(meta, 'modified_iso', '')) or ''
                    files_list.append({
                        'file_name': f_name,
                        'is_folder': False,
                        'relative_path': f_rel,
                        'abs_path': full_p,
                        'file_size': f_size,
                        'sync_status': 'synced',
                        'last_modified_local': mtime_iso
                    })
            folders_list.sort(key=lambda x: x['file_name'].lower())
            files_list.sort(key=lambda x: x['file_name'].lower())
            scope_files_list.sort(key=lambda x: x['file_name'].lower())
            self.scope_files_cache = scope_files_list
            count_source = scope_files_list if scope_files_list else files_list
            word_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'word')
            excel_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'excel')
            access_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'access')
            pdf_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'pdf')
            images_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'image')
            other_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) in ('video', 'audio', 'archive', 'other'))
            folders_cnt = len(folders_list)
            self.tab_all.setText(f"الكل ({len(count_source)})")
            if hasattr(self, 'lbl_file_count_badge'):
                self.lbl_file_count_badge.setText(f"{len(count_source)} ملف")
            if hasattr(self, 'pill_all_depts'):
                self.pill_all_depts.setText(f"كافة الأقسام ({len(count_source)})")
            self.tab_folders.setText(f"المجلدات ({folders_cnt})" if folders_cnt > 0 else "المجلدات")
            self.tab_word.setText(f"Word ({word_cnt})")
            self.tab_excel.setText(f"Excel ({excel_cnt})")
            self.tab_access.setText(f"Access ({access_cnt})")
            self.tab_pdf.setText(f"PDF ({pdf_cnt})")
            if hasattr(self, 'tab_images'):
                self.tab_images.setText(f"صور ({images_cnt})")
            if hasattr(self, 'tab_other'):
                self.tab_other.setText(f"أخرى ({other_cnt})")
            self.lbl_total.setText(f"المستندات: {len(count_source)}  •  المجلدات: {folders_cnt}")
            self.all_files_cache = folders_list + files_list
            self._filter_content()
            return True
        except Exception as e:
            print(f"[Instant Render Error]: {e}")
            return False
    def _navigate_into_folder(self, folder_name, rel_path=None):
        """الدخول إلى مجلد فرعي وتحديث العرض مع التحقق من صلاحيات القسم والرمز السري ومنع التكرار نهائياً"""
        if getattr(self, '_nav_transitioning', False):
            return
        # تحديد المسار المستهدف بدقة لمنع التكرار
        if rel_path:
            norm_rel = str(rel_path).replace("\\", "/").strip("/").strip(".")
            new_path = Path(norm_rel) if norm_rel else Path(".")
        else:
            norm_sub = str(self.current_subpath).replace("\\", "/").strip("/").strip(".")
            if not norm_sub or norm_sub == ".":
                new_path = Path(folder_name)
            else:
                sub_parts = [p for p in norm_sub.split("/") if p]
                if sub_parts and sub_parts[-1] == folder_name:
                    return
                new_path = self.current_subpath / folder_name
        norm_new = str(new_path).replace("\\", "/").strip("/").strip(".")
        norm_curr = str(self.current_subpath).replace("\\", "/").strip("/").strip(".")
        if norm_new == norm_curr:
            return
        target_dept = self.active_dept_name
        if not target_dept and norm_new:
            target_dept = norm_new.split("/")[0]
        if target_dept and not self._check_department_permission(target_dept, action='view'):
            return
        # التحقق من أن المجلد موجود فعلياً (إما محلياً أو في اللقطة السحابية) لمنع مسارات وهمية
        local_target = (self.sync_folder / new_path).resolve()
        local_exists = local_target.is_dir()
        cloud_exists = False
        if hasattr(self, 'client') and self.client and self.client.is_configured():
            cached_snap = self.client.peek_snapshot() if hasattr(self.client, 'peek_snapshot') else None
            if cached_snap and hasattr(cached_snap, 'folders'):
                cloud_exists = (norm_new in cached_snap.folders)
        if not local_exists and not cloud_exists:
            return
        # تفعيل حماية منع النقر المتكرر (Debounce)
        self._nav_transitioning = True
        QTimer.singleShot(200, lambda: setattr(self, '_nav_transitioning', False))
        if not self.active_dept_name and norm_new:
            first_seg = norm_new.split("/")[0]
            if any(d.get('name') == first_seg for d in self.departments_list):
                self.active_dept_name = first_seg
        self.current_subpath = new_path
        self._reset_scroll_on_render = True
        self._force_full_render = True
        self._nav_cache_ok = True
        self._update_breadcrumb()
        # العرض الفوري المتزامن من الذاكرة (< 15ms)
        self._apply_instant_snapshot_render(new_path)
        # جدولة فحص خلفي هادئ للتزامن
        self._refresh_file_list()
    def _toggle_subfolders_visibility(self):
        """طي أو إظهار شبكة المجلدات لتوسيع مساحة عرض الملفات في الجدول"""
        if hasattr(self, 'subfolders_scroll'):
            is_vis = self.subfolders_scroll.isVisible()
            self._folders_manually_collapsed = is_vis
            self.subfolders_scroll.setVisible(not is_vis)
            if is_vis:
                cnt = len(getattr(self, '_last_folder_items', [])) or self.subfolders_grid.count()
                self.btn_toggle_subfolders.setText(f"📂 إظهار المجلدات ({cnt})")
            else:
                self.btn_toggle_subfolders.setText("📂 طي المجلدات")
    def _navigate_up(self):
        """الرجوع للمجلد السابق (للأعلى) مع الحفاظ على حدود القسم وعرض فوري"""
        if getattr(self, '_nav_transitioning', False):
            return
        if self.active_dept_name and self.current_subpath == Path(self.active_dept_name):
            self._on_department_clicked("__ALL__")
            return
        new_subpath = None
        if self.active_dept_name:
            if self.current_subpath != Path(self.active_dept_name):
                new_subpath = self.current_subpath.parent
        else:
            if self.current_subpath != Path("."):
                new_subpath = self.current_subpath.parent
        if new_subpath is None or new_subpath == self.current_subpath:
            return
        self._nav_transitioning = True
        QTimer.singleShot(200, lambda: setattr(self, '_nav_transitioning', False))
        self.current_subpath = new_subpath
        self._reset_scroll_on_render = True
        self._force_full_render = True
        self._nav_cache_ok = True
        self._update_breadcrumb()
        # العرض الفوري المتزامن من الذاكرة (< 15ms)
        self._apply_instant_snapshot_render(new_subpath)
        self._refresh_file_list()
    def _update_breadcrumb(self):
        """تحديث شريط المسار بالأزرار الكبسولية التفاعلية المطابقة لمنصة الويب"""
        if hasattr(self, 'breadcrumb_layout'):
            while self.breadcrumb_layout.count():
                it = self.breadcrumb_layout.takeAt(0)
                w = it.widget()
                if w:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        is_root = (self.active_dept_name is None and self.current_subpath == Path("."))
        btn_root = QPushButton("كافة الأقسام")
        btn_root.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if is_root:
            btn_root.setStyleSheet("""
                QPushButton {
                    background-color: #14372e; color: #FFFFFF; border: none;
                    border-radius: 6px; padding: 4px 12px; font-weight: bold; font-size: 11.5px;
                }
            """)
            if hasattr(self, 'btn_nav_up'):
                self.btn_nav_up.setVisible(False)
        else:
            btn_root.setStyleSheet("""
                QPushButton {
                    background-color: transparent; color: #667085; border: none;
                    border-radius: 6px; padding: 4px 6px; font-weight: 600; font-size: 11.5px;
                }
                QPushButton:hover { color: #14372e; background-color: #F2F4F7; }
            """)
            btn_root.clicked.connect(lambda: self._on_department_clicked("__ALL__"))
            if hasattr(self, 'btn_nav_up'):
                self.btn_nav_up.setVisible(True)
        if hasattr(self, 'breadcrumb_layout'):
            self.breadcrumb_layout.addWidget(btn_root)
        norm_sub = str(self.current_subpath).replace("\\", "/").strip("/").strip(".")
        parts = [p for p in norm_sub.split("/") if p] if norm_sub else []
        if not parts and self.active_dept_name:
            parts = [self.active_dept_name]
        for idx, part in enumerate(parts):
            lbl_sep = QLabel("‹")
            lbl_sep.setStyleSheet("color: #98A2B3; font-weight: bold; font-size: 14px; padding: 0 2px; background: transparent;")
            self.breadcrumb_layout.addWidget(lbl_sep)
            is_last = (idx == len(parts) - 1)
            target_rel = "/".join(parts[:idx + 1])
            btn_part = QPushButton(part)
            btn_part.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if is_last:
                btn_part.setStyleSheet("""
                    QPushButton {
                        background-color: #14372e; color: #FFFFFF; border: none;
                        border-radius: 6px; padding: 4px 12px; font-weight: bold; font-size: 11.5px;
                    }
                """)
            else:
                btn_part.setStyleSheet("""
                    QPushButton {
                        background-color: transparent; color: #475467; border: none;
                        border-radius: 6px; padding: 4px 8px; font-weight: 600; font-size: 11.5px;
                    }
                    QPushButton:hover { color: #14372e; background-color: #F2F4F7; }
                """)
                if idx == 0 and self.active_dept_name == part:
                    btn_part.clicked.connect(lambda _, d=part: self._on_department_clicked(d))
                else:
                    btn_part.clicked.connect(lambda _, p=part, r=target_rel: self._navigate_into_folder(p, r))
            self.breadcrumb_layout.addWidget(btn_part)

    def _show_new_folder_dialog(self):
        """نافذة إنشاء مجلد إداري جديد مع اقتراحات سريعة لأقسام الغرفة (قسم إنشاء مجلدات)"""
        if not self._check_department_permission(self.active_dept_name, action='create_folder'):
            return
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
                rel_folder = str(target_dir.relative_to(self.sync_folder)).replace("\\", "/")
                if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                    self.sync_engine.clear_tombstone(rel_folder)
                # مزامنة إنشاء المجلد فوراً إلى السحابة في خيط خلفي
                if self.client and self.client.is_configured() and hasattr(self.client, 'create_folder'):
                    self._run_cloud_async(self.client.create_folder, rel_folder)
                dialog.accept()
                self._refresh_file_list()
                QMessageBox.information(self, "تم الإنشاء", f"تم إنشاء المجلد '{f_name}' بنجاح.")
            except Exception as e:
                QMessageBox.critical(dialog, "خطأ", f"تعذر إنشاء المجلد:\n{e}")
        btn_create.clicked.connect(do_create)
        btn_row.addWidget(btn_create)
        layout.addLayout(btn_row)
        dialog.exec()
    def _rename_folder(self, old_folder_name):
        """تعديل اسم مجلد إداري وتحديث موقعه التخزيني على الجهاز ومزامنته في السحابة"""
        if not self._check_department_permission(self.active_dept_name, action='rename'):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("✏️ تعديل اسم المجلد الإداري")
        dialog.resize(480, 220)
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
        cur_parent_name = "كافة الملفات والمجلدات" if self.current_subpath == Path(".") else self.current_subpath.name
        title_lbl = QLabel(f"📁 تعديل اسم المجلد: {old_folder_name}")
        title_lbl.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {GOV_GREEN};")
        layout.addWidget(title_lbl)
        txt_name = QLineEdit(old_folder_name)
        txt_name.selectAll()
        layout.addWidget(txt_name)
        hint_lbl = QLabel(f"المجلد يقع ضمن: ({cur_parent_name}) وسيتم تعديل اسمه في موقع التخزين مباشرة.")
        hint_lbl.setFont(QFont("Cairo", 9))
        hint_lbl.setStyleSheet("color: #64748b;")
        layout.addWidget(hint_lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setObjectName("btnGovSecondary")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)
        btn_save = QPushButton("💾 حفظ التعديل")
        btn_save.setObjectName("btnGovPrimary")
        def do_save():
            new_name = txt_name.text().strip()
            if not new_name:
                QMessageBox.warning(dialog, "تنبيه", "يرجى إدخال اسم المجلد الجديد.")
                return
            if new_name == old_folder_name:
                dialog.accept()
                return
            invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
            if any(c in new_name for c in invalid_chars):
                QMessageBox.warning(dialog, "تنبيه", "اسم المجلد يحتوي على رموز غير صالحة للويندوز.")
                return
            old_path = (self._get_current_abs_folder() / old_folder_name).resolve()
            new_path = (self._get_current_abs_folder() / new_name).resolve()
            if new_path.exists():
                QMessageBox.warning(dialog, "تنبيه", f"يوجد مجلد آخر باسم '{new_name}' في نفس المجلد.")
                return
            # 1. تغيير اسم المجلد الفعلي على الجهاز
            if old_path.exists():
                try:
                    os.rename(str(old_path), str(new_path))
                except PermissionError:
                    QMessageBox.critical(
                        dialog, "تعذر التعديل",
                        "تعذر تغيير اسم المجلد على الجهاز لأن أحد الملفات داخله قيد الاستخدام حالياً في برنامج آخر.\n\nيرجى إغلاق المستندات المفتوحة ثم المحاولة مجدداً."
                    )
                    return
                except Exception as e:
                    QMessageBox.critical(dialog, "خطأ", f"حدث خطأ أثناء إعادة تسمية المجلد على الجهاز:\n{e}")
                    return
            # 2. تحديث قاعدة البيانات المحلية للملفات المنظمة داخل المجلد
            old_rel = str(old_path.relative_to(self.sync_folder)).replace("\\", "/")
            new_rel = str(new_path.relative_to(self.sync_folder)).replace("\\", "/")
            self.state_mgr.rename_folder_prefix(old_rel, new_rel)
            # 3. مزامنة التغيير في السحابة في خيط خلفي (تغيير الاسم دون حذف المحتويات)
            if self.client and self.client.is_configured():
                if hasattr(self.client, 'rename_folder'):
                    self._run_cloud_async(self.client.rename_folder, old_rel, new_name)
                elif hasattr(self.client, 'create_folder'):
                    self._run_cloud_async(self.client.create_folder, new_rel)
            dialog.accept()
            self._refresh_file_list()
            self._refresh_departments_sidebar()
            QMessageBox.information(self, "تم التعديل", f"تم تعديل اسم المجلد إلى '{new_name}' بنجاح في موقع التخزين.")
        btn_save.clicked.connect(do_save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)
        dialog.exec()
    def _show_context_menu_for_folder(self, folder_name, global_pos, rel_path=None):
        """القائمة المنسدلة الخاصة بالمجلدات الإدارية"""
        if rel_path:
            norm_r = str(rel_path).replace("\\", "/").strip("/").strip(".")
            target = (self.sync_folder / norm_r).resolve()
            rel_p = norm_r
        else:
            target = (self._get_current_abs_folder() / folder_name).resolve()
            rel_p = str(target.relative_to(self.sync_folder)).replace("\\", "/") if target.exists() else folder_name
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
        move_action = menu.addAction("📂 نقل المجلد إلى قسم / مجلد آخر...")
        rename_action = menu.addAction("✏️ تعديل اسم المجلد (إعادة تسمية)...")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ نقل المجلد إلى سلة المحذوفات")
        action = menu.exec(global_pos)
        if action == open_action:
            self._navigate_into_folder(folder_name, rel_path=rel_p)
        elif action == open_win_action:
            if target.exists():
                subprocess.Popen(f'explorer /select,"{str(target)}"')
        elif action == move_action:
            self._show_move_items_dialog([{"name": folder_name, "rel_path": rel_p, "is_folder": True}])
        elif action == rename_action:
            self._rename_folder(folder_name)
        elif action == delete_action:
            self._move_folder_to_trash(folder_name, rel_path=rel_p)
    def _move_folder_to_trash(self, folder_name, rel_path=None, ask_confirm=True):
        """نقل مجلد كامل إلى سلة المحذوفات بأمان وحذفه فوراً من السحابة وباقي المنصات"""
        target_dept = self.active_dept_name
        if not target_dept and rel_path and "/" in str(rel_path):
            target_dept = str(rel_path).split("/")[0]
        if not self._check_department_permission(target_dept, action='delete'):
            return False
        if ask_confirm:
            reply = QMessageBox.question(
                self, "تأكيد حذف المجلد",
                f"هل أنت متأكد من نقل المجلد '{folder_name}' ومحتوياته إلى سلة المحذوفات (محلياً وفي السحابة)؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        target = (self.sync_folder / rel_path).resolve() if rel_path else (self._get_current_abs_folder() / folder_name).resolve()
        if not target.exists():
            target = (self._get_current_abs_folder() / folder_name).resolve()
        if target.exists():
            rel = str(target.relative_to(self.sync_folder)).replace("\\", "/")
            if self.sync_engine and hasattr(self.sync_engine, '_mark_self_op'):
                self.sync_engine._mark_self_op(rel, seconds=30)
            trash_dir = self.state_mgr.db_dir / 'trash'
            trash_dir.mkdir(parents=True, exist_ok=True)
            trash_dest = trash_dir / f"{int(time.time() * 1000)}_{folder_name}"
            shutil.move(str(target), str(trash_dest))
            self.state_mgr.add_to_trash(
                folder_name, rel, str(trash_dest), 0,
                item_type='folder', dept_name=target_dept or ''
            )
            self.selected_rel_paths.discard(rel)
            # تسجيل شاهد الحذف + تنفيذ الحذف السحابي الفوري في خيط خلفي
            if self.sync_engine and hasattr(self.sync_engine, 'note_local_delete'):
                self.sync_engine.note_local_delete(rel, is_folder=True)
            if self.client and self.client.is_configured():
                fn = self.client.delete_folder if hasattr(self.client, 'delete_folder') else self.client.delete_file
                self._run_cloud_async(fn, rel)
            if ask_confirm:
                self._update_bulk_bar()
                self._force_full_render = True
                self._refresh_file_list()
                QMessageBox.information(self, "تم الحذف", f"تم نقل المجلد '{folder_name}' إلى سلة المحذوفات ومزامنة حذفه مع السحابة.")
            return True
        return False
    def _move_file_to_trash(self, file_name, rel_path=None, ask_confirm=True):
        """نقل مستند رسمي إلى سلة المحذوفات وحذفه فوراً من السحابة وباقي المنصات"""
        target_dept = self.active_dept_name
        if not target_dept and rel_path and "/" in str(rel_path):
            target_dept = str(rel_path).split("/")[0]
        if not self._check_department_permission(target_dept, action='delete'):
            return False
        if ask_confirm:
            reply = QMessageBox.question(
                self, "تأكيد النقل إلى سلة المحذوفات", 
                f"هل أنت متأكد من نقل المستند التالي إلى سلة المحذوفات (في التطبيق والسحابة)؟\n{file_name}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        if rel_path is None:
            rel_path = str((self.current_subpath / file_name)).replace("\\", "/") if self.current_subpath != Path(".") else file_name
        file_path = (self.sync_folder / rel_path).resolve()
        if not file_path.exists():
            file_path = (self._get_current_abs_folder() / file_name).resolve()
        if not file_path.exists():
            file_path = (self.sync_folder / file_name).resolve()
        if file_path.exists():
            actual_rel = str(file_path.relative_to(self.sync_folder)).replace("\\", "/")
            if self.sync_engine and hasattr(self.sync_engine, '_mark_self_op'):
                self.sync_engine._mark_self_op(actual_rel, seconds=30)
            trash_dir = self.state_mgr.db_dir / 'trash'
            trash_dir.mkdir(parents=True, exist_ok=True)
            trash_dest = trash_dir / f"{int(time.time() * 1000)}_{file_path.name}"
            size = file_path.stat().st_size if file_path.is_file() else 0
            shutil.move(str(file_path), str(trash_dest))
            server_fid = self.state_mgr.add_to_trash(
                file_name, actual_rel, str(trash_dest), size,
                item_type='file', dept_name=target_dept or ''
            )
            self.selected_rel_paths.discard(actual_rel)
            # تسجيل شاهد الحذف + تنفيذ الحذف المباشر من Google Drive فوراً بالمعرف السحابي
            if self.sync_engine and hasattr(self.sync_engine, 'note_local_delete'):
                self.sync_engine.note_local_delete(actual_rel, is_folder=False)
            if self.client and self.client.is_configured():
                self._run_cloud_async(self.client.delete_file, actual_rel, server_fid)
            if ask_confirm:
                self._update_bulk_bar()
                self._force_full_render = True
                self._refresh_file_list()
                QMessageBox.information(self, "تم النقل للمحذوفات", f"تم نقل '{file_name}' إلى سلة المحذوفات وحذفه من السحابة بنجاح.")
            return True
        return False
    # ------------------------------------------------------------------ #
    # إدارة التحديد المتعدد والنقل والحذف الجماعي (Multi-Select & Move)
    # ------------------------------------------------------------------ #
    def _toggle_item_selected(self, rel_path, checked):
        if not rel_path:
            return
        if checked:
            self.selected_rel_paths.add(rel_path)
        else:
            self.selected_rel_paths.discard(rel_path)
        self._update_bulk_bar()
        # مزامنة حالة الـ Checkbox في الجدول إن كان معروضاً
        if hasattr(self, 'table'):
            self.table.blockSignals(True)
            try:
                for row in range(self.table.rowCount()):
                    it0 = self.table.item(row, 0)
                    if it0 and it0.data(Qt.ItemDataRole.UserRole) == rel_path:
                        target_state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                        if it0.checkState() != target_state:
                            it0.setCheckState(target_state)
                        break
            finally:
                self.table.blockSignals(False)
    def _on_table_item_changed(self, item):
        if item.column() != 0:
            return
        rel_path = item.data(Qt.ItemDataRole.UserRole)
        if not rel_path:
            return
        checked = item.checkState() == Qt.CheckState.Checked
        if checked:
            self.selected_rel_paths.add(rel_path)
        else:
            self.selected_rel_paths.discard(rel_path)
        self._update_bulk_bar()
    def _update_bulk_bar(self):
        cnt = len(self.selected_rel_paths)
        if hasattr(self, 'bulk_bar_frame'):
            self.bulk_bar_frame.setVisible(cnt > 0 and self.active_filter != "TRASH")
        if hasattr(self, 'lbl_bulk_count'):
            self.lbl_bulk_count.setText(f"☑️ تم تحديد {cnt} عنصر للعمليات الجماعية")
        if hasattr(self, 'btn_select_all_toggle'):
            if cnt > 0 and cnt >= len(getattr(self, '_last_filtered_items', []) or [1]):
                self.btn_select_all_toggle.setText("✖ إلغاء تحديد الكل")
            else:
                self.btn_select_all_toggle.setText("☑️ تحديد الكل")
    def _clear_all_selections(self, refresh_ui=True):
        self.selected_rel_paths.clear()
        if hasattr(self, 'table'):
            self.table.blockSignals(True)
            try:
                self.table.clearSelection()
                for row in range(self.table.rowCount()):
                    it0 = self.table.item(row, 0)
                    if it0:
                        it0.setCheckState(Qt.CheckState.Unchecked)
            finally:
                self.table.blockSignals(False)
        self._update_bulk_bar()
        if refresh_ui and self.current_view_mode in ("GRID", "COMPACT"):
            self._filter_content()
    def _toggle_select_all_visible(self):
        visible = getattr(self, '_last_filtered_items', None) or self.all_files_cache
        if not visible:
            return
        vis_rels = [f.get('relative_path') or f.get('file_name') for f in visible if (f.get('relative_path') or f.get('file_name'))]
        all_checked = all(r in self.selected_rel_paths for r in vis_rels)
        if all_checked:
            for r in vis_rels:
                self.selected_rel_paths.discard(r)
        else:
            for r in vis_rels:
                self.selected_rel_paths.add(r)
        if hasattr(self, 'table'):
            self.table.blockSignals(True)
            try:
                for row in range(self.table.rowCount()):
                    it0 = self.table.item(row, 0)
                    if it0:
                        rp = it0.data(Qt.ItemDataRole.UserRole)
                        it0.setCheckState(Qt.CheckState.Checked if rp in self.selected_rel_paths else Qt.CheckState.Unchecked)
            finally:
                self.table.blockSignals(False)
        self._update_bulk_bar()
        if self.current_view_mode in ("GRID", "COMPACT"):
            self._filter_content()
    def _get_currently_selected_items(self):
        """جمع العناصر المحددة سواء عبر مربعات الاختيار (Checkboxes) أو تحديد صفوف الجدول"""
        cache_by_rel = {(x.get('relative_path') or x.get('file_name')): x for x in self.all_files_cache}
        selected_map = {}
        for rel in list(self.selected_rel_paths):
            info = cache_by_rel.get(rel)
            if info:
                selected_map[rel] = {
                    "name": info.get('file_name') or Path(rel).name,
                    "rel_path": rel,
                    "is_folder": bool(info.get('is_folder', False)),
                }
            else:
                p = (self.sync_folder / rel).resolve()
                selected_map[rel] = {
                    "name": p.name,
                    "rel_path": rel,
                    "is_folder": p.is_dir(),
                }
        if not selected_map and hasattr(self, 'table'):
            for idx in self.table.selectionModel().selectedRows():
                it0 = self.table.item(idx.row(), 0)
                if it0:
                    rel = it0.data(Qt.ItemDataRole.UserRole)
                    is_fld = bool(it0.data(Qt.ItemDataRole.UserRole + 1))
                    nm = it0.text().split('\n')[0]
                    if rel:
                        selected_map[rel] = {"name": nm, "rel_path": rel, "is_folder": is_fld}
        return list(selected_map.values())
    def _delete_selected_items_bulk(self):
        items = self._get_currently_selected_items()
        if not items:
            QMessageBox.information(self, "تنبيه", "يرجى تحديد ملف أو مجلد واحد على الأقل لحذفه.")
            return
        # فحص الصلاحية للأقسام المعنية
        checked_depts = set()
        for it in items:
            rel = it["rel_path"]
            dept = rel.split("/")[0] if "/" in rel else self.active_dept_name
            if dept and dept not in checked_depts:
                if not self._check_department_permission(dept, action='delete'):
                    return
                checked_depts.add(dept)
        reply = QMessageBox.question(
            self,
            "تأكيد الحذف الجماعي للسلة",
            f"هل أنت متأكد من نقل ({len(items)}) عنصر محدد إلى سلة المحذوفات؟\n\n"
            f"سيتم نقلها إلى السلة محلياً وحذفها من السحابة وجميع المنصات المرتبطة فوراً.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        deleted_cnt = 0
        for it in items:
            if it["is_folder"]:
                if self._move_folder_to_trash(it["name"], rel_path=it["rel_path"], ask_confirm=False):
                    deleted_cnt += 1
            else:
                if self._move_file_to_trash(it["name"], rel_path=it["rel_path"], ask_confirm=False):
                    deleted_cnt += 1
        self._clear_all_selections(refresh_ui=False)
        self._force_full_render = True
        self._refresh_file_list()
        self._refresh_departments_sidebar()
        QMessageBox.information(
            self,
            "تم الحذف الجماعي ✅",
            f"تم بنجاح نقل ({deleted_cnt}) عنصر إلى سلة المحذوفات ومزامنة الحذف مع السحابة."
        )
    def _move_selected_items_bulk(self):
        items = self._get_currently_selected_items()
        if not items:
            QMessageBox.information(self, "تنبيه", "يرجى تحديد ملف أو مجلد واحد على الأقل لنقله.")
            return
        self._show_move_items_dialog(items)
    def _show_move_items_dialog(self, items_to_move):
        """نافذة نقل ملف أو مجموعة ملفات/مجلدات إلى قسم آخر أو مجلد فرعي مع مزامنة السحابة"""
        if not items_to_move:
            return
        # التحقق من صلاحية النقل في القسم المصدر
        checked_src = set()
        for it in items_to_move:
            rel = it.get("rel_path") or it.get("name") or ""
            src_dept = rel.split("/")[0] if "/" in rel else self.active_dept_name
            if src_dept and src_dept not in checked_src:
                if not self._check_department_permission(src_dept, action='move'):
                    return
                checked_src.add(src_dept)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"📂 نقل ({len(items_to_move)}) عنصر إلى موقع جديد")
        dialog.resize(520, 320)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Cairo', Tahoma; }
            QLabel { font-size: 12px; color: #162420; font-weight: 600; }
            QComboBox, QLineEdit {
                background-color: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 8px;
                padding: 8px 12px; font-size: 12px; color: #162420; font-weight: bold;
            }
            QComboBox:focus, QLineEdit:focus { border-color: #14372e; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        title_lbl = QLabel(f"📂 نقل ({len(items_to_move)}) ملف/مجلد محدد مع تحديث السحابة")
        title_lbl.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {GOV_GREEN};")
        layout.addWidget(title_lbl)
        layout.addWidget(QLabel("1. اختر القسم الوجهة:"))
        cmb_dept = QComboBox()
        for d in self.departments_list:
            cmb_dept.addItem(f"🏛️ {d['name']}", d['name'])
        cmb_dept.addItem("🗂️ المجلد العام (الجذر الرئيسي)", "")
        if self.active_dept_name:
            idx = cmb_dept.findData(self.active_dept_name)
            if idx >= 0:
                cmb_dept.setCurrentIndex(idx)
        layout.addWidget(cmb_dept)
        layout.addWidget(QLabel("2. اختر المجلد الفرعي داخل القسم (اختياري):"))
        cmb_sub = QComboBox()
        cmb_sub.setEditable(True)
        layout.addWidget(cmb_sub)
        def _populate_subfolders():
            cmb_sub.clear()
            cmb_sub.addItem("📁 (مباشرة داخل القسم الرئيسي)", "")
            dept_val = cmb_dept.currentData()
            base_p = (self.sync_folder / dept_val) if dept_val else self.sync_folder
            if base_p.exists():
                try:
                    for sub in sorted(base_p.rglob("*")):
                        if sub.is_dir() and not any(part.startswith(".") for part in sub.parts):
                            rel_sub = str(sub.relative_to(base_p)).replace("\\", "/")
                            if not dept_val and rel_sub.split("/")[0] in [d['name'] for d in self.departments_list]:
                                continue
                            cmb_sub.addItem(f"📂 {rel_sub}", rel_sub)
                except Exception:
                    pass
        cmb_dept.currentIndexChanged.connect(lambda _: _populate_subfolders())
        _populate_subfolders()
        hint = QLabel("💡 سيتم نقل العناصر المختارة على جهازك وفي سحابة Google Drive وباقي المنصات فوراً.")
        hint.setFont(QFont("Cairo", 9))
        hint.setStyleSheet("color: #64748b;")
        layout.addWidget(hint)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setObjectName("btnGovSecondary")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)
        btn_exec = QPushButton("📂 تأكيد النقل الآن")
        btn_exec.setObjectName("btnGovPrimary")
        def do_move():
            target_dept = cmb_dept.currentData() or ""
            if target_dept and not self._check_department_permission(target_dept, action='upload'):
                return
            sub_data = cmb_sub.currentData()
            sub_text = cmb_sub.currentText().replace("📁 (مباشرة داخل القسم الرئيسي)", "").replace("📂 ", "").strip().strip("/\\")
            chosen_sub = sub_data if sub_data is not None and cmb_sub.currentText().startswith(("📁", "📂")) else sub_text
            dest_rel_dir = "/".join(x for x in [target_dept, chosen_sub] if x)
            dest_abs_dir = (self.sync_folder / dest_rel_dir).resolve() if dest_rel_dir else self.sync_folder.resolve()
            dest_abs_dir.mkdir(parents=True, exist_ok=True)
            moved_count = 0
            cloud_moves = []
            for it in items_to_move:
                old_rel = it.get("rel_path") or it.get("name")
                is_fld = bool(it.get("is_folder", False))
                src_abs = (self.sync_folder / old_rel).resolve()
                if not src_abs.exists():
                    continue
                new_abs = (dest_abs_dir / src_abs.name).resolve()
                if src_abs == new_abs:
                    continue
                if is_fld and str(new_abs).startswith(str(src_abs) + os.sep):
                    QMessageBox.warning(dialog, "تنبيه", f"لا يمكن نقل المجلد '{src_abs.name}' إلى داخل نفسه.")
                    continue
                if new_abs.exists():
                    QMessageBox.warning(dialog, "تنبيه", f"يوجد عنصر بنفس الاسم '{src_abs.name}' في الوجهة المختارة.")
                    continue
                new_rel = str(new_abs.relative_to(self.sync_folder)).replace("\\", "/")
                try:
                    if self.sync_engine and hasattr(self.sync_engine, '_mark_self_op'):
                        self.sync_engine._mark_self_op(old_rel, seconds=30)
                        self.sync_engine._mark_self_op(new_rel, seconds=30)
                    shutil.move(str(src_abs), str(new_abs))
                    if is_fld:
                        self.state_mgr.rename_folder_prefix(old_rel, new_rel)
                    else:
                        self.state_mgr.rename_file_record(old_rel, new_rel, src_abs.name)
                    cloud_moves.append((old_rel, new_rel, is_fld))
                    self.selected_rel_paths.discard(old_rel)
                    moved_count += 1
                except Exception as e:
                    QMessageBox.warning(dialog, "خطأ أثناء النقل", f"تعذر نقل '{src_abs.name}':\n{e}")
            if cloud_moves and self.client and self.client.is_configured():
                def _sync_moves_bg(moves_list):
                    for o_rel, n_rel, is_f in moves_list:
                        try:
                            if hasattr(self.client, 'move_path_in_cloud'):
                                self.client.move_path_in_cloud(o_rel, n_rel, is_folder=is_f)
                        except Exception as ex:
                            print(f"[Cloud Move Error] {o_rel} -> {n_rel}: {ex}")
                self._run_cloud_async(_sync_moves_bg, cloud_moves)
            dialog.accept()
            self._clear_all_selections(refresh_ui=False)
            self._force_full_render = True
            self._refresh_file_list()
            self._refresh_departments_sidebar()
            if moved_count > 0:
                QMessageBox.information(
                    self,
                    "تم النقل بنجاح ✅",
                    f"تم نقل ({moved_count}) عنصر إلى '{dest_rel_dir or 'المجلد الرئيسي'}' وجارٍ تحديث موقعها في السحابة."
                )
        btn_exec.clicked.connect(do_move)
        btn_row.addWidget(btn_exec)
        layout.addLayout(btn_row)
        dialog.exec()
    def _rename_file(self, old_file_name, rel_path=None):
        """تعديل اسم مستند رسمي وتحديث موقعه التخزيني على الجهاز ومزامنته في السحابة"""
        target_dept = self.active_dept_name
        if not target_dept and rel_path and "/" in str(rel_path):
            target_dept = str(rel_path).split("/")[0]
        if not self._check_department_permission(target_dept, action='rename'):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("✏️ تعديل اسم المستند الرسمي")
        dialog.resize(480, 240)
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
        title_lbl = QLabel(f"📄 تعديل اسم المستند: {old_file_name}")
        title_lbl.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {GOV_GREEN};")
        layout.addWidget(title_lbl)
        old_stem = Path(old_file_name).stem
        old_ext = Path(old_file_name).suffix
        txt_name = QLineEdit(old_file_name)
        # تحديد اسم الملف بدون الامتداد لتسهيل التعديل السريع
        txt_name.setSelection(0, len(old_stem))
        layout.addWidget(txt_name)
        ext_note = f"ملاحظة: سيتم الحفاظ على صيغة المستند ({old_ext}) تلقائياً إذا تركت الامتداد." if old_ext else ""
        hint_lbl = QLabel(ext_note)
        hint_lbl.setFont(QFont("Cairo", 9))
        hint_lbl.setStyleSheet("color: #64748b;")
        layout.addWidget(hint_lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setObjectName("btnGovSecondary")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)
        btn_save = QPushButton("💾 حفظ التعديل")
        btn_save.setObjectName("btnGovPrimary")
        def do_save():
            val = txt_name.text().strip()
            if not val:
                QMessageBox.warning(dialog, "تنبيه", "يرجى إدخال اسم المستند.")
                return
            # الحفاظ على الامتداد الأصلي في حال لم يكتب المستخدم امتداداً
            if not Path(val).suffix and old_ext:
                new_file_name = val + old_ext
            else:
                new_file_name = val
            if new_file_name == old_file_name:
                dialog.accept()
                return
            invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
            if any(c in new_file_name for c in invalid_chars):
                QMessageBox.warning(dialog, "تنبيه", "اسم الملف يحتوي على رموز غير صالحة للويندوز.")
                return
            old_path = None
            if rel_path:
                cand = (self.sync_folder / rel_path).resolve()
                if cand.exists():
                    old_path = cand
            if not old_path:
                old_path = (self._get_current_abs_folder() / old_file_name).resolve()
            if not old_path.exists():
                old_path = (self.sync_folder / old_file_name).resolve()
            if not old_path.exists():
                QMessageBox.critical(dialog, "خطأ", "لم يتم العثور على الملف الأصلي على القرص.")
                return
            new_path = old_path.parent / new_file_name
            if new_path.exists():
                QMessageBox.warning(dialog, "تنبيه", f"يوجد ملف آخر باسم '{new_file_name}' في نفس المجلد.")
                return
            # 1. تغيير اسم الملف الفعلي على الجهاز
            try:
                os.rename(str(old_path), str(new_path))
            except PermissionError:
                QMessageBox.critical(
                    dialog, "تعذر التعديل",
                    f"تعذر تعديل اسم المستند لأن الملف مفتوح حالياً في برنامج آخر (مثل Word أو Excel).\n\nيرجى حفظ وإغلاق الملف أولاً ثم إعادة المحاولة."
                )
                return
            except Exception as e:
                QMessageBox.critical(dialog, "خطأ", f"حدث خطأ أثناء إعادة تسمية الملف على الجهاز:\n{e}")
                return
            # 2. تحديث قاعدة البيانات المحلية
            old_rel = str(old_path.relative_to(self.sync_folder)).replace("\\", "/")
            new_rel = str(new_path.relative_to(self.sync_folder)).replace("\\", "/")
            self.state_mgr.rename_file_record(old_rel, new_rel, new_file_name)
            # 3. مزامنة التعديل في السحابة فوراً في الخلفية
            if self.sync_engine and hasattr(self.sync_engine, 'note_local_move'):
                self.sync_engine.note_local_move(old_rel, new_rel)
            elif self.client and self.client.is_configured():
                self._run_cloud_async(self.client.rename_file, old_rel, new_file_name)
            dialog.accept()
            self._force_full_render = True
            self._refresh_file_list()
            self._refresh_departments_sidebar()
            QMessageBox.information(self, "تم التعديل", f"تم تعديل اسم المستند إلى '{new_file_name}' وتحديثه في موقع التخزين والسحابة.")
        btn_save.clicked.connect(do_save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)
        dialog.exec()
    def _trigger_cloud_trash_fetch(self):
        """جلب الملفات المحذوفة في سحابة Google Drive في خيط خلفي لدمجها مع سلة المحذوفات"""
        if getattr(self, '_cloud_trash_fetching', False):
            return
        if not self.client or not self.client.is_configured() or not hasattr(self.client, 'list_deleted_files'):
            return
        self._cloud_trash_fetching = True
        import threading
        def _worker():
            try:
                cloud_items = self.client.list_deleted_files() or []
                self.bridge.cloud_trash_ready.emit(cloud_items)
            except Exception as e:
                print(f"[Cloud trash fetch error]: {e}")
            finally:
                self._cloud_trash_fetching = False
        threading.Thread(target=_worker, daemon=True).start()
    def _on_cloud_trash_ready(self, cloud_items):
        self._cloud_trash_cache = list(cloud_items or [])
        if self.active_filter == "TRASH":
            self._render_trash_table(fetch_cloud=False)
    def _get_merged_trash_items(self, dept=None):
        """دمج عناصر سلة المحذوفات المحلية مع عناصر سلة المحذوفات السحابية بدون تكرار"""
        local_items = list(self.state_mgr.get_trash_files(dept_name=dept if dept else None) or [])
        seen_fids = {str(x.get('server_file_id')) for x in local_items if x.get('server_file_id')}
        seen_rels = {str(x.get('original_rel_path')) for x in local_items if x.get('original_rel_path')}
        for c in getattr(self, '_cloud_trash_cache', []):
            cid = str(c.get('id') or '')
            crel = str(c.get('relative_path') or c.get('name') or '')
            cdept = str(c.get('department') or '')
            if dept and cdept != dept:
                continue
            if (cid and cid in seen_fids) or (crel and crel in seen_rels):
                continue
            local_items.append({
                'id': f"cloud_{cid}",
                'file_name': c.get('name') or Path(crel).name,
                'original_rel_path': crel,
                'trash_path': '',
                'file_size': int(c.get('size') or 0),
                'item_type': 'folder' if c.get('is_folder') else 'file',
                'dept_name': cdept,
                'deleted_at': c.get('modifiedTime') or '',
                'server_file_id': cid,
                'is_cloud_only': True,
            })
        return local_items
    def _render_trash_table(self, fetch_cloud=True):
        """تصيير قسم سلة المحذوفات الخاص بالقسم النشط أو الأرشيف العام بالكامل مع أزرار الإجراءات"""
        if fetch_cloud:
            self._trigger_cloud_trash_fetch()
        dept = self.active_dept_name or ""
        if hasattr(self, 'th_title'):
            self.th_title.setText(f"🗑️ سلة محذوفات قسم: {dept}" if dept else "🗑️ سلة المحذوفات العامة (المحلية والسحابية)")
        if hasattr(self, 'th_desc'):
            self.th_desc.setText(f"المستندات والمجلدات المحذوفة الخاصة بـ ({dept}) محفوظة بأمان هنا ومربوطة بالسحابة." if dept else "كافة المستندات المنقولة للمحذوفات من الجهاز أو الويب محفوظة بأمان هنا.")
        if hasattr(self, 'btn_empty_trash'):
            self.btn_empty_trash.setText(f"🧹 إفراغ سلة محذوفات ({dept})" if dept else "🧹 إفراغ سلة المحذوفات")
        if hasattr(self, 'btn_restore_all'):
            self.btn_restore_all.setText(f"♻️ استرجاع كافة محذوفات ({dept})" if dept else "♻️ استرجاع كافة المحذوفات")
        v_bar = self.trash_table.verticalScrollBar()
        prev_scroll = v_bar.value()
        self.trash_table.setUpdatesEnabled(False)
        try:
            items = self._get_merged_trash_items(dept=dept if dept else None)
            self.trash_table.setRowCount(0)
            for row_idx, item in enumerate(items):
                self.trash_table.insertRow(row_idx)
                self.trash_table.setRowHeight(row_idx, 52)
                name = item['file_name']
                trash_id = item['id']
                itype = item.get('item_type', 'file')
                tpath_str = item.get('trash_path') or ''
                is_cloud_only = bool(item.get('is_cloud_only'))
                if itype == 'department':
                    icon = get_file_office_icon(name, size=32, is_folder=True)
                    display_name = f"🏛️ {name} (قسم إداري محذوف)"
                elif itype == 'folder' or (tpath_str and Path(tpath_str).is_dir()):
                    icon = get_file_office_icon(name, size=32, is_folder=True)
                    display_name = f"📁 {name} (مجلد محذوف)"
                else:
                    icon = get_file_office_icon(name, size=32, is_folder=False, abs_path=tpath_str if tpath_str else None)
                    display_name = f"☁️ {name}" if is_cloud_only else name
                name_cell = QTableWidgetItem(display_name)
                name_cell.setIcon(icon)
                name_cell.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
                name_cell.setData(Qt.ItemDataRole.UserRole, trash_id)
                self.trash_table.setItem(row_idx, 0, name_cell)
                origin = item.get('original_rel_path', name)
                if itype == 'department':
                    origin = f"🏛️ الأقسام الإدارية / {name}"
                elif is_cloud_only:
                    origin = f"☁️ محذوف في السحابة / {origin}"
                path_cell = QTableWidgetItem(origin)
                path_cell.setFont(QFont("Segoe UI", 10))
                path_cell.setForeground(QColor("#566c65"))
                path_cell.setData(Qt.ItemDataRole.UserRole, trash_id)
                self.trash_table.setItem(row_idx, 1, path_cell)
                date_raw = item.get('deleted_at', '')
                date_str = date_raw[:19].replace('T', ' ') if date_raw else "غير محدد"
                date_cell = QTableWidgetItem(date_str)
                date_cell.setFont(QFont("Segoe UI", 10))
                date_cell.setForeground(QColor("#566c65"))
                self.trash_table.setItem(row_idx, 2, date_cell)
                size_bytes = item.get('file_size', 0)
                if itype in ['department', 'folder']:
                    size_str = "—"
                elif size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                elif size_bytes < 1048576:
                    size_str = f"{round(size_bytes / 1024, 1)} KB"
                else:
                    size_str = f"{round(size_bytes / 1048576, 2)} MB"
                size_cell = QTableWidgetItem(size_str)
                size_cell.setFont(QFont("Segoe UI", 10))
                size_cell.setForeground(QColor("#566c65"))
                self.trash_table.setItem(row_idx, 3, size_cell)
                # أزرار الإجراءات البارزة الواضحة في كل صف
                action_widget = QWidget()
                act_layout = QHBoxLayout(action_widget)
                act_layout.setContentsMargins(6, 4, 6, 4)
                act_layout.setSpacing(8)
                btn_res = QPushButton("↩️ استرجاع")
                btn_res.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_res.setToolTip(f"استرجاع '{name}' وإعادته للسحابة والجهاز فوراً")
                btn_res.setStyleSheet("""
                    QPushButton {
                        background-color: #14372e; color: #ffffff; border: none;
                        border-radius: 6px; padding: 6px 14px; font-weight: bold; font-size: 11px;
                        font-family: 'Cairo', Tahoma;
                    }
                    QPushButton:hover { background-color: #1e4a3f; }
                """)
                btn_res.clicked.connect(lambda _, tid=trash_id: self._restore_from_trash(tid))
                act_layout.addWidget(btn_res)
                btn_del = QPushButton("🗑️ حذف نهائي")
                btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_del.setToolTip(f"حذف '{name}' نهائياً من القرص والسحابة")
                btn_del.setStyleSheet("""
                    QPushButton {
                        background-color: #fee2e2; color: #991b1b; border: 1.5px solid #fecaca;
                        border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 11px;
                        font-family: 'Cairo', Tahoma;
                    }
                    QPushButton:hover { background-color: #fecaca; color: #7f1d1d; }
                """)
                btn_del.clicked.connect(lambda _, tid=trash_id: self._purge_from_trash(tid))
                act_layout.addWidget(btn_del)
                self.trash_table.setCellWidget(row_idx, 4, action_widget)
        finally:
            self.trash_table.setUpdatesEnabled(True)
        if not getattr(self, '_reset_scroll_on_render', False):
            v_bar.setValue(prev_scroll)
            QTimer.singleShot(0, lambda: v_bar.setValue(prev_scroll))
        else:
            self._reset_scroll_on_render = False
            v_bar.setValue(0)
    def _restore_from_trash(self, trash_id, show_msg=True):
        """استعادة مستند رسمي أو مجلد أو قسم من سلة المحذوفات (المحلية أو السحابية) ومزامنته فوراً"""
        if str(trash_id).startswith("cloud_"):
            cloud_fid = str(trash_id)[len("cloud_"):]
            cloud_item = next((c for c in getattr(self, '_cloud_trash_cache', []) if str(c.get('id')) == cloud_fid), None)
            self._cloud_trash_cache = [c for c in getattr(self, '_cloud_trash_cache', []) if str(c.get('id')) != cloud_fid]
            if self.client and self.client.is_configured() and hasattr(self.client, 'restore_by_id'):
                self._run_cloud_async(self.client.restore_by_id, cloud_fid)
            if show_msg:
                self._render_trash_table(fetch_cloud=False)
                QMessageBox.information(
                    self, "تمت الاستعادة من السحابة",
                    f"✅ تمت استعادة '{cloud_item.get('name') if cloud_item else cloud_fid}' من سلة محذوفات السحابة وسيتم تنزيله تلقائياً."
                )
            return
        row = self.state_mgr.remove_from_trash(trash_id)
        if not row:
            return
        trash_path_str = row.get('trash_path') or ''
        orig_rel = row['original_rel_path']
        server_fid = row.get('server_file_id')
        target_path = (self.sync_folder / orig_rel).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if trash_path_str and Path(trash_path_str).exists():
            shutil.move(trash_path_str, str(target_path))
        # 1. إذا كان قسماً إدارياً
        if row.get('item_type') == 'department':
            dept_name = row['file_name']
            if not any(d['name'] == dept_name for d in self.departments_list):
                self.departments_list.append({"name": dept_name, "icon": "🏛️"})
                self.state_mgr.set_departments(self.departments_list)
            self._refresh_departments_sidebar()
        # 2. إزالة أي علامات حذف سابقة (Tombstone) واستعادة الملف سحابياً
        if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
            self.sync_engine.clear_tombstone(orig_rel)
        if server_fid and self.client and self.client.is_configured() and hasattr(self.client, 'restore_by_id'):
            self._run_cloud_async(self.client.restore_by_id, server_fid)
        if target_path.exists() and target_path.is_file():
            try:
                os.utime(str(target_path), None)
            except Exception:
                pass
            with self.state_mgr._get_connection() as conn:
                conn.execute("DELETE FROM local_files WHERE relative_path = ?", (orig_rel,))
        if self.sync_engine:
            self.sync_engine.wake(delay=0.2)
        if show_msg:
            self._refresh_departments_sidebar()
            self._refresh_file_list()
            self._render_trash_table(fetch_cloud=False)
            QMessageBox.information(
                self, "تمت الاستعادة والمزامنة السحابية",
                f"✅ تمت استعادة المستند بنجاح:\n{row['file_name']}\n\nتمت إعادته إلى مكانه الأصلي ومزامنته مع السحابة."
            )
    def _run_trash_batch_dialog(self, mode, items, title_text):
        """تشغيل عملية تفريغ أو استرجاع جماعي لسلة المحذوفات بشريط تقدم حي دون أي تجميد"""
        total = len(items)
        progress = QProgressDialog("جاري تحضير العملية...", "إلغاء", 0, 100, self)
        progress.setWindowTitle(title_text)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(500)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.setStyleSheet("""
            QProgressDialog { background-color: #ffffff; font-family: 'Cairo', 'Segoe UI', Tahoma; border-radius: 12px; }
            QLabel { font-size: 12.5px; font-weight: bold; color: #14372e; padding: 8px; }
            QProgressBar {
                border: 1.5px solid #cbd5e1; border-radius: 8px; text-align: center;
                background-color: #f1f5f9; height: 24px; font-weight: bold; color: #0f172a;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14372e, stop:1 #0d8a55);
                border-radius: 7px;
            }
            QPushButton {
                background-color: #dc2626; color: white; border-radius: 6px; padding: 6px 16px; font-weight: bold;
            }
        """)
        progress.show()
        worker = TrashBatchWorker(
            mode=mode,
            items=items,
            state_mgr=self.state_mgr,
            sync_engine=self.sync_engine,
            cloud_client=self.client,
            sync_folder=self.sync_folder,
            parent=self
        )
        self._active_upload_workers.append(worker)
        def on_cancel():
            worker.is_cancelled = True
        progress.canceled.connect(on_cancel)
        def on_prog(pct, cur, tot, cur_name):
            if progress.isVisible():
                progress.setValue(pct)
                act_lbl = "🗑️ جاري الحذف النهائي" if mode == 'empty' else "♻️ جاري استرجاع المحذوفات"
                progress.setLabelText(f"{act_lbl} ({cur} من {tot} — {pct}%):\n{cur_name}")
        def on_done(m, ok_cnt, tot_cnt):
            try:
                progress.close()
                progress.deleteLater()
            except Exception:
                pass
            if worker in self._active_upload_workers:
                self._active_upload_workers.remove(worker)
            self._cloud_trash_cache.clear()
            self._force_full_render = True
            self._refresh_departments_sidebar()
            self._refresh_file_list()
            self._render_trash_table(fetch_cloud=True)
            if m == 'empty':
                QMessageBox.information(
                    self, "اكتمل تفريغ سلة المحذوفات ✅",
                    f"✅ تم بنجاح تفريغ وحذف ({ok_cnt} من {tot_cnt}) عنصر نهائياً من الجهاز والسحابة."
                )
            else:
                QMessageBox.information(
                    self, "اكتملت الاستعادة السحابية ✅",
                    f"✅ تم بنجاح استرجاع ({ok_cnt} من {tot_cnt}) عنصر وإعادتها لمواقعها الأصلية ومزامنتها."
                )
        worker.progress_signal.connect(on_prog)
        worker.finished_signal.connect(on_done)
        worker.start()
    def _restore_all_trash(self):
        """استعادة كافة المستندات المحذوفة دفعة واحدة بشريط تقدم حي وسريع"""
        dept = self.active_dept_name or ""
        items = self._get_merged_trash_items(dept=dept if dept else None)
        if not items:
            QMessageBox.information(self, "سلة المحذوفات", "سلة المحذوفات فارغة حالياً ولا توجد عناصر لاسترجاعها.")
            return
        reply = QMessageBox.question(
            self, "تأكيد استعادة كافة المحذوفات",
            f"هل أنت متأكد من استرجاع كافة المحذوفات ({len(items)} عنصر) وإعادتها لمواقعها الأصلية في الجهاز والسحابة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_trash_batch_dialog('restore', items, "♻️ استرجاع كافة المحذوفات")
    def _restore_selected_from_trash(self):
        """استرجاع الملف أو العنصر المحدد حالياً في جدول المحذوفات"""
        selected_rows = self.trash_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد صف أو ملف من جدول المحذوفات أولاً لاسترجاعه.")
            return
        row_idx = selected_rows[0].row()
        item_cell = self.trash_table.item(row_idx, 0)
        if not item_cell:
            return
        trash_id = item_cell.data(Qt.ItemDataRole.UserRole)
        if trash_id:
            self._restore_from_trash(trash_id)
    def _show_trash_context_menu(self, pos):
        """قائمة الخيارات بالزر الأيمن على عنصر في سلة المحذوفات"""
        item = self.trash_table.itemAt(pos)
        if not item:
            return
        row_idx = item.row()
        cell_0 = self.trash_table.item(row_idx, 0)
        if not cell_0:
            return
        trash_id = cell_0.data(Qt.ItemDataRole.UserRole)
        file_name = cell_0.text().split("\n")[0]
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #ffffff; color: #162420; border: 1.5px solid #d5dfdb; border-radius: 8px; padding: 4px; }
            QMenu::item { padding: 8px 24px; border-radius: 4px; font-size: 12px; font-weight: 600; }
            QMenu::item:selected { background-color: #f0f6f4; color: #14372e; font-weight: bold; }
        """)
        act_res = menu.addAction(f"↩️ استرجاع '{file_name}' ورفعه للسحابة")
        menu.addSeparator()
        act_del = menu.addAction(f"🗑️ حذف نهائي (تفريغ من القرص والسحابة)")
        action = menu.exec(self.trash_table.mapToGlobal(pos))
        if action == act_res:
            self._restore_from_trash(trash_id)
        elif action == act_del:
            self._purge_from_trash(trash_id)
    def _show_file_statistics_dialog(self):
        """نافذة إحصائيات المستندات والمساحة التخزينية وتوزيع الأنواع"""
        dialog = QDialog(self)
        dialog.setWindowTitle("📊 إحصائيات المستندات والأنواع – غرفة تجارة كربلاء المقدسة")
        dialog.resize(650, 520)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Cairo', 'Segoe UI', Tahoma; }
            QLabel { color: #162420; }
            QTableWidget {
                background-color: #ffffff;
                border: 1.5px solid #cbd5e1;
                border-radius: 8px;
                gridline-color: #f1f5f9;
            }
            QHeaderView::section {
                background-color: #0e2720;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 6px;
                border: none;
            }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        # الترويسة
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0e2720, stop:1 #1a443a);
                border-radius: 10px;
                border-bottom: 2px solid #c59b27;
                padding: 10px;
            }
        """)
        h_box = QHBoxLayout(header_frame)
        h_title = QLabel("📊 التقرير الإحصائي لمستندات المنظومة")
        h_title.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        h_title.setStyleSheet("color: #ffffff; border: none; background: transparent;")
        h_box.addWidget(h_title)
        h_box.addStretch()
        cur_scope = self.active_dept_name if self.active_dept_name else "الأرشيف الشامل (كافة الأقسام)"
        scope_lbl = QLabel(f"النطاق: {cur_scope}")
        scope_lbl.setFont(QFont("Cairo", 10))
        scope_lbl.setStyleSheet("color: #ecd58a; border: none; background: transparent;")
        h_box.addWidget(scope_lbl)
        layout.addWidget(header_frame)
        # حساب الإحصائيات الفعلية من الذاكرة والقرص
        from gdrive_client import is_ignored_name
        all_files = []
        for root, dirs, files in os.walk(self.sync_folder):
            if ".trash" in root:
                continue
            for f in files:
                if is_ignored_name(f):
                    continue
                fp = Path(root) / f
                rel = fp.relative_to(self.sync_folder).as_posix()
                dept = rel.split('/')[0] if '/' in rel else "القسم العام"
                if self.active_dept_name and dept != self.active_dept_name:
                    continue
                try:
                    sz = fp.stat().st_size
                except OSError:
                    sz = 0
                all_files.append({"name": f, "size": sz, "ext": fp.suffix.lower(), "dept": dept})
        total_cnt = len(all_files)
        total_sz = sum(x["size"] for x in all_files)
        def fmt_sz(b):
            if b < 1024: return f"{b} B"
            if b < 1048576: return f"{round(b/1024, 1)} KB"
            return f"{round(b/1048576, 2)} MB"
        # بطاقات الملخص السريع
        summary_row = QHBoxLayout()
        summary_row.setSpacing(8)
        cards = [
            ("📁 إجمالي المستندات", f"{total_cnt} مستند", "#14372e"),
            ("💾 المساحة الإجمالية", fmt_sz(total_sz), "#0284c7"),
            ("🏛️ القسم النشط", str(self.active_dept_name or "كافة الأقسام"), "#c59b27")
        ]
        for title, val, col in cards:
            c_frame = QFrame()
            c_frame.setObjectName("statSummaryCard")
            c_frame.setStyleSheet(f"""
                QFrame#statSummaryCard {{
                    background: #ffffff;
                    border: 1.5px solid #e2e8f0;
                    border-right: 4px solid {col};
                    border-radius: 8px;
                }}
                QFrame#statSummaryCard QLabel {{
                    background: transparent;
                    border: none;
                    padding: 0px;
                }}
            """)
            c_lay = QVBoxLayout(c_frame)
            c_lay.setContentsMargins(12, 8, 12, 8)
            c_lay.setSpacing(2)
            lbl_t = QLabel(title)
            lbl_t.setFont(QFont("Cairo", 9))
            lbl_t.setStyleSheet("color: #64748b;")
            c_lay.addWidget(lbl_t)
            lbl_v = QLabel(val)
            lbl_v.setFont(QFont("Cairo", 11, QFont.Weight.Bold))
            lbl_v.setStyleSheet(f"color: {col};")
            c_lay.addWidget(lbl_v)
            summary_row.addWidget(c_frame)
        layout.addLayout(summary_row)
        # جدول التوزيع حسب النوع
        types_info = [
            ("مستندات Word الرسمية", ("📝", ".docx, .doc"), (".docx", ".doc"), "#0284c7"),
            ("جداول Excel والحسابات", ("📊", ".xlsx, .xls, .csv"), (".xlsx", ".xls", ".csv"), "#107c41"),
            ("قواعد بيانات Access والسجلات", ("🗄️", ".accdb, .mdb"), (".accdb", ".mdb"), "#b45309"),
            ("وثائق PDF والتعاميم المعتمدة", ("📄", ".pdf"), (".pdf",), "#e11d48"),
            ("كتب مصورة وكاميرا / صور", ("📷", ".jpg, .png, .webp"), (".jpg", ".jpeg", ".png", ".webp", ".bmp"), "#7c3aed"),
            ("ملفات ومستندات أخرى", ("📄", "صيغ متنوعة"), (), "#475569"),
        ]
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["نوع المستند", "الصيغ المدعومة", "عدد الملفات", "إجمالي الحجم", "النسبة"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        row_idx = 0
        for label, (icon, exts_str), exts, col in types_info:
            if exts:
                t_files = [x for x in all_files if x["ext"] in exts]
            else:
                known_exts = set().union(*[t[2] for t in types_info if t[2]])
                t_files = [x for x in all_files if x["ext"] not in known_exts]
            cnt = len(t_files)
            sz = sum(x["size"] for x in t_files)
            pct = round((sz / total_sz * 100), 1) if total_sz > 0 else 0
            table.insertRow(row_idx)
            table.setRowHeight(row_idx, 38)
            c_name = QTableWidgetItem(f"{icon} {label}")
            c_name.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
            table.setItem(row_idx, 0, c_name)
            c_ext = QTableWidgetItem(exts_str)
            c_ext.setFont(QFont("Segoe UI", 9))
            c_ext.setForeground(QColor("#64748b"))
            table.setItem(row_idx, 1, c_ext)
            c_cnt = QTableWidgetItem(f"{cnt} ملف")
            c_cnt.setFont(QFont("Cairo", 10, QFont.Weight.Bold))
            c_cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row_idx, 2, c_cnt)
            c_sz = QTableWidgetItem(fmt_sz(sz))
            c_sz.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            c_sz.setForeground(QColor(col))
            c_sz.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row_idx, 3, c_sz)
            c_pct = QTableWidgetItem(f"{pct}%")
            c_pct.setFont(QFont("Segoe UI", 9))
            c_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row_idx, 4, c_pct)
            row_idx += 1
        layout.addWidget(table, stretch=1)
        # زر إغلاق
        btn_close = QPushButton("إغلاق الإحصائيات")
        btn_close.setObjectName("btnGovPrimary")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignLeft)
        dialog.exec()
    def _on_trash_row_double_clicked(self, row, col):
        """عند النقر المزدوج على سطر في سلة المحذوفات: اقتراح استعادته ومزامنته فوراً"""
        cell_0 = self.trash_table.item(row, 0)
        if not cell_0:
            return
        trash_id = cell_0.data(Qt.ItemDataRole.UserRole)
        file_name = cell_0.text().split("\n")[0]
        reply = QMessageBox.question(
            self, "استعادة المستند",
            f"هل تريد استرجاع '{file_name}' إلى مكانه الأصلي وإعادة رفعه للسحابة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._restore_from_trash(trash_id)
    def _purge_from_trash(self, trash_id):
        """الحذف النهائي لمستند أو مجلد أو قسم من سلة المحذوفات وتفريغ مساحته من القرص والسحابة"""
        if not self._check_department_permission(self.active_dept_name, action='permanent_delete'):
            return
        reply = QMessageBox.warning(
            self, "تأكيد الحذف النهائي",
            "هل أنت متأكد من حذف هذا العنصر نهائياً من الجهاز والسحابة؟\nلن تتمكن من استعادته مرة أخرى وسيتم تفريغ مساحته بالكامل.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if str(trash_id).startswith("cloud_"):
                cloud_fid = str(trash_id)[len("cloud_"):]
                self._cloud_trash_cache = [c for c in getattr(self, '_cloud_trash_cache', []) if str(c.get('id')) != cloud_fid]
                if self.client and self.client.is_configured() and hasattr(self.client, 'purge_by_id'):
                    self._run_cloud_async(self.client.purge_by_id, cloud_fid)
                self._render_trash_table(fetch_cloud=False)
                return
            row = self.state_mgr.remove_from_trash(trash_id)
            if row:
                trash_path_str = row.get('trash_path') or ''
                if trash_path_str:
                    trash_path = Path(trash_path_str)
                    if trash_path.exists():
                        try:
                            if trash_path.is_dir():
                                shutil.rmtree(str(trash_path), ignore_errors=True)
                            else:
                                trash_path.unlink()
                        except Exception:
                            pass
                orig_rel = row.get('original_rel_path') or ''
                server_fid = row.get('server_file_id')
                if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                    self.sync_engine.clear_tombstone(orig_rel)
                if self.client and self.client.is_configured():
                    if server_fid and hasattr(self.client, 'purge_by_id'):
                        self._run_cloud_async(self.client.purge_by_id, server_fid)
                    elif hasattr(self.client, 'purge_file'):
                        self._run_cloud_async(self.client.purge_file, orig_rel, server_fid)
            self._render_trash_table(fetch_cloud=False)
    def _empty_all_trash(self):
        """إفراغ سلة محذوفات القسم النشط أو العام بشريط تقدم حي وحذف متوازٍ بدون تجميد الواجهة"""
        dept = self.active_dept_name
        if not self._check_department_permission(dept, action='permanent_delete'):
            return
        items = self._get_merged_trash_items(dept=dept if dept else None)
        count = len(items)
        if count == 0:
            QMessageBox.information(self, "سلة المحذوفات", f"سلة محذوفات قسم '{dept}' فارغة بالفعل." if dept else "سلة المحذوفات فارغة بالفعل.")
            return
        title_target = f"قسم '{dept}'" if dept else "كافة الأقسام"
        reply = QMessageBox.critical(
            self, "تأكيد إفراغ سلة المحذوفات النهائي",
            f"هل تريد بالتأكيد إفراغ سلة محذوفات ({title_target}) وحذف كافة عناصرها ({count} عنصر) نهائياً من القرص والسحابة؟\nهذا الإجراء نهائي ولا يمكن التراجع عنه.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_trash_batch_dialog('empty', items, f"🧹 تفريغ سلة المحذوفات ({title_target})")
    def _set_active_filter(self, tag):
        self.active_filter = tag
        self._reset_scroll_on_render = True
        self._force_full_render = True
        self._nav_cache_ok = True
        self._update_bulk_bar()
        if tag == "TRASH":
            self.stack.setCurrentIndex(3)
            self.view_switch_frame.setEnabled(False)
            if hasattr(self, 'subfolders_card'):
                self.subfolders_card.setVisible(False)
            if hasattr(self, 'btn_select_all_toggle'):
                self.btn_select_all_toggle.setVisible(False)
            self._render_trash_table()
        else:
            if hasattr(self, 'subfolders_card'):
                self.subfolders_card.setVisible(True)
            self.view_switch_frame.setEnabled(True)
            if hasattr(self, 'btn_select_all_toggle'):
                self.btn_select_all_toggle.setVisible(True)
            if self.current_view_mode == "GRID":
                self.stack.setCurrentIndex(1)
            elif self.current_view_mode == "COMPACT":
                self.stack.setCurrentIndex(2)
            else:
                self.stack.setCurrentIndex(0)
            self._filter_content()
    def _set_view_mode(self, mode, persist=True):
        self.current_view_mode = mode
        self._reset_scroll_on_render = True
        self._force_full_render = True
        self._nav_cache_ok = True
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
        folder_items = [f for f in self.all_files_cache if f.get('is_folder', False)]
        if query:
            folder_items = [f for f in folder_items if query in f['file_name'].lower()]
        # عند البحث أو اختيار تصنيف نوع ملف محدد (Word, Excel, ...) نبحث في كافة ملفات النطاق الحالي والفرعي
        use_scope = bool(query) or (self.active_filter in ("WORD", "EXCEL", "ACCESS", "PDF", "IMAGES", "OTHER"))
        if use_scope and getattr(self, 'scope_files_cache', None):
            source_files = self.scope_files_cache
        else:
            source_files = [f for f in self.all_files_cache if not f.get('is_folder', False)]
        filtered_files = []
        if self.active_filter != "FOLDERS":
            for f in source_files:
                name = f['file_name'].lower()
                tkey = get_type_key(f['file_name'], is_folder=False)
                if self.active_filter == "WORD" and tkey != 'word':
                    continue
                elif self.active_filter == "EXCEL" and tkey != 'excel':
                    continue
                elif self.active_filter == "ACCESS" and tkey != 'access':
                    continue
                elif self.active_filter == "PDF" and tkey != 'pdf':
                    continue
                elif self.active_filter == "IMAGES" and tkey != 'image':
                    continue
                elif self.active_filter == "OTHER" and tkey not in ('video', 'audio', 'archive', 'other'):
                    continue
                if query and query not in name and query not in str(f.get('relative_path', '')).lower():
                    continue
                filtered_files.append(f)
        filtered = folder_items + filtered_files
        self._last_filtered_items = filtered
        self._update_bulk_bar()
        if self.current_view_mode == "GRID":
            self._render_grid(filtered)
        elif self.current_view_mode == "COMPACT":
            self._render_compact(filtered)
        else:
            self._render_table(filtered)
    def _refresh_file_list(self):
        """جدولة فحص القرص وقاعدة البيانات في خيط خلفي سريع جداً دون تجميد خيط الواجهة الرئيسي"""
        try:
            force_now = getattr(self, '_force_full_render', False)
            if not force_now:
                # لا داعي للفحص الدوري والنافذة مخفية في شريط المهام (System Tray)
                if not self.isVisible() or self.isMinimized():
                    return
                if hasattr(self, '_last_wheel_time') and (time.time() - self._last_wheel_time < 1.2):
                    return
                if hasattr(self, 'table') and self.table.verticalScrollBar().isSliderDown():
                    return
                if hasattr(self, 'grid_scroll') and self.grid_scroll.verticalScrollBar().isSliderDown():
                    return
                if hasattr(self, 'compact_scroll') and self.compact_scroll.verticalScrollBar().isSliderDown():
                    return
            if getattr(self, '_scan_in_progress', False):
                self._scan_pending = True
                return
            self._scan_in_progress = True
            scan_dept = self.active_dept_name
            scan_subpath = self.current_subpath
            self._force_full_render = False
            # التنقل بين المجلدات/التبويبات يكتفي باللقطة السحابية المحفوظة (فوري)،
            # أما العمليات (رفع/حذف/تسمية...) فتطلب جلباً سحابياً جديداً كما في السابق
            force_cloud = force_now and not getattr(self, '_nav_cache_ok', False)
            self._nav_cache_ok = False
            self._scan_t0 = time.perf_counter()
            import threading
            threading.Thread(
                target=self._background_scan_worker,
                args=(scan_dept, scan_subpath, force_now, force_cloud),
                daemon=True
            ).start()
        except Exception as e:
            self._scan_in_progress = False
            print(f"[Refresh Schedule Error]: {e}")
    def _schedule_cloud_refresh(self):
        """تجديد اللقطة السحابية في خيط خلفي مستقل ثم إعادة العرض فقط إن تغيّرت البيانات"""
        if getattr(self, '_cloud_refreshing', False):
            return
        if not (self.client and self.client.is_configured()):
            return
        self._cloud_refreshing = True
        import threading
        def _worker():
            try:
                before = getattr(self.client.peek_snapshot(), 'taken_at', None)
                snap = self.client.snapshot(max_age=CLOUD_SNAPSHOT_MAX_AGE)
                if snap is not None and snap.taken_at != before:
                    self.bridge.cloud_snapshot_ready.emit()
            except Exception as e:
                print(f"[Cloud refresh error]: {e}")
            finally:
                self._cloud_refreshing = False
        threading.Thread(target=_worker, daemon=True).start()
    def _background_scan_worker(self, scan_dept, scan_subpath, force_now, force_cloud=True):
        """فحص شجرة السحابة الرسمية مباشرة من Google Drive لتوحيد العرض بين الويب وسطح المكتب"""
        try:
            from gdrive_client import is_ignored_name
            cloud_snap = None
            need_cloud_refresh = False
            if hasattr(self, 'client') and self.client and self.client.is_configured():
                cached = self.client.peek_snapshot() if hasattr(self.client, 'peek_snapshot') else None
                if cached is not None and not force_cloud:
                    # عرض فوري من الذاكرة، والتجديد يتم في الخلفية دون حجز الواجهة
                    cloud_snap = cached
                    need_cloud_refresh = (time.time() - cached.taken_at) >= CLOUD_SNAPSHOT_MAX_AGE
                else:
                    try:
                        cloud_snap = self.client.snapshot(force=force_cloud, max_age=CLOUD_SNAPSHOT_MAX_AGE)
                    except Exception as e:
                        print(f"[Snapshot error]: {e}")
                        cloud_snap = None
                    if cloud_snap is None:
                        cloud_snap = cached
            sync_root_str = str(self.sync_folder.resolve())
            current_abs = Path(os.path.normpath(os.path.join(sync_root_str, str(scan_subpath))))
            if not current_abs.exists():
                try:
                    current_abs.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
            states_map = self.state_mgr.get_all_states_map() if hasattr(self.state_mgr, 'get_all_states_map') else {}
            perms_map = {}
            try:
                if self.client and hasattr(self.client, 'get_cached_folder_permissions'):
                    perms_map = self.client.get_cached_folder_permissions() or {}
                elif self.client and hasattr(self.client, 'get_folder_permissions'):
                    perms_map = self.client.get_folder_permissions() or {}
            except Exception:
                perms_map = {}
            unlocked_pins = getattr(self, '_unlocked_pin_depts', set())
            def _can_show_dept(d_name):
                if not isinstance(perms_map, dict) or d_name not in perms_map:
                    return True
                rule = perms_map.get(d_name) or {}
                if not rule.get('canView', rule.get('can_view', True)):
                    return False
                pin_c = str(rule.get('pinCode') or rule.get('pin_code') or '').strip()
                dept_u = str(rule.get('deptUsername') or rule.get('dept_username') or '').strip()
                dept_p = str(rule.get('deptPassword') or rule.get('dept_password') or '').strip()
                authed_d = rule.get('authorizedDevices') or rule.get('authorized_devices') or []
                my_g = get_desktop_machine_guid()
                is_p = bool(pin_c or dept_u or dept_p)
                is_u = (d_name in unlocked_pins) or (my_g in authed_d)
                if is_p and not is_u:
                    return False
                return True
            folders_list = []
            files_list = []
            scope_files_list = []
            seen_rel_paths = set()
            seen_scope_paths = set()
            local_dept_names = []
            dept_counts = {}
            total_root_items = 0
            norm_sub = str(scan_subpath).replace("\\", "/").strip("/").strip(".")
            if norm_sub in (".", ""):
                norm_sub = ""
            if cloud_snap is not None and cloud_snap.folders:
                # ---------------------------------------------------------- #
                # الوضع السحابي الموحد: أخذ الملفات والمجلدات من السحابة حصراً
                # ---------------------------------------------------------- #
                snap_idx = _get_snapshot_index(cloud_snap)
                cloud_root_dirs = sorted(snap_idx['child_dirs'].get("", []))
                for crd in cloud_root_dirs:
                    if not is_ignored_name(crd) and _can_show_dept(crd):
                        local_dept_names.append(crd)
                        dept_counts[crd] = snap_idx['rec_files'].get(crd, 0)
                total_root_items = len(cloud_snap.files)
                # 2. المجلدات الفرعية في المسار الحالي
                child_dirs = []
                for fld in snap_idx['child_dirs'].get(norm_sub, []):
                    if is_ignored_name(fld.split("/")[-1]):
                        continue
                    if norm_sub == "" and not _can_show_dept(fld):
                        continue
                    child_dirs.append(fld)
                if norm_sub == "" and len(child_dirs) == 1:
                    only_dept = child_dirs[0]
                    sub_of_only = [fld for fld in snap_idx['child_dirs'].get(only_dept, []) if not is_ignored_name(fld.split("/")[-1])]
                    if sub_of_only:
                        child_dirs = sub_of_only
                for d_rel in sorted(set(child_dirs)):
                    d_name = d_rel.split("/")[-1]
                    rec_file_cnt = snap_idx['rec_files'].get(d_rel, 0)
                    sub_dir_cnt = len([x for x in snap_idx['child_dirs'].get(d_rel, []) if not is_ignored_name(x.split("/")[-1])])
                    local_dir_path = os.path.normpath(os.path.join(sync_root_str, d_rel))
                    folders_list.append({
                        'file_name': d_name,
                        'is_folder': True,
                        'item_count': rec_file_cnt,
                        'child_count': sub_dir_cnt,
                        'relative_path': d_rel,
                        'abs_path': local_dir_path,
                        'file_size': 0,
                        'sync_status': 'synced',
                        'last_modified_local': ''
                    })
                # 3. الملفات السحابية في المسار الحالي + ملفات النطاق الشامل (لإحصائيات الفلاتر والبحث)
                is_all_archive = (scan_dept is None and scan_subpath == Path("."))
                local_names_cache = {}
                def _exists_locally(rel_p):
                    parent, _, nm = rel_p.rpartition("/")
                    names = local_names_cache.get(parent)
                    if names is None:
                        names = set()
                        try:
                            with os.scandir(os.path.join(sync_root_str, parent)) as it:
                                for e in it:
                                    if e.is_file(follow_symlinks=False):
                                        names.add(e.name.lower())
                        except OSError:
                            pass
                        local_names_cache[parent] = names
                    return nm.lower() in names
                def _build_cloud_file_entry(f_rel, meta):
                    fname = meta.get('name', f_rel.split("/")[-1])
                    abs_f = os.path.normpath(os.path.join(sync_root_str, f_rel))
                    f_size = int(meta.get('size', 0) or 0)
                    mtime_iso = meta.get('modifiedTime', '')
                    is_local = _exists_locally(f_rel)
                    st = states_map.get(f_rel)
                    if is_local:
                        sync_stat = 'synced'
                    elif st and st.get('sync_status') in ('syncing', 'downloading'):
                        sync_stat = 'syncing'
                    else:
                        sync_stat = 'cloud_only'
                    return {
                        'file_name': fname,
                        'is_folder': False,
                        'relative_path': f_rel,
                        'abs_path': abs_f,
                        'file_size': f_size,
                        'storage_path': meta.get('id'),
                        'sync_status': sync_stat,
                        'last_modified_local': mtime_iso
                    }
                for f_rel, meta in cloud_snap.files.items():
                    fname = meta.get('name', f_rel.split("/")[-1])
                    if is_ignored_name(fname):
                        continue
                    dept_prefix = f_rel.split("/")[0] if "/" in f_rel else ""
                    if dept_prefix and not _can_show_dept(dept_prefix):
                        continue
                    in_scope = is_all_archive or (f_rel == norm_sub or f_rel.startswith(norm_sub + "/"))
                    if in_scope and f_rel not in seen_scope_paths:
                        seen_scope_paths.add(f_rel)
                        entry_obj = _build_cloud_file_entry(f_rel, meta)
                        scope_files_list.append(entry_obj)
                        if is_all_archive and f_rel not in seen_rel_paths:
                            seen_rel_paths.add(f_rel)
                            files_list.append(entry_obj)
                if not is_all_archive:
                    for f_rel, meta in snap_idx['child_files'].get(norm_sub, []):
                        fname = meta.get('name', f_rel.split("/")[-1])
                        if is_ignored_name(fname) or f_rel in seen_rel_paths:
                            continue
                        seen_rel_paths.add(f_rel)
                        files_list.append(_build_cloud_file_entry(f_rel, meta))
                # دمج أي ملفات جديدة أضافها المستخدم محلياً وما زالت قيد الرفع
                if current_abs.exists():
                    try:
                        for entry in os.scandir(current_abs):
                            if entry.is_file(follow_symlinks=False) and not entry.name.startswith(".") and not is_ignored_name(entry.name):
                                rel_p = os.path.relpath(entry.path, sync_root_str).replace("\\", "/")
                                if rel_p not in seen_rel_paths:
                                    st = states_map.get(rel_p)
                                    if st and st.get('sync_status') in ('pending_upload', 'syncing'):
                                        seen_rel_paths.add(rel_p)
                                        loc_item = {
                                            'file_name': entry.name,
                                            'is_folder': False,
                                            'relative_path': rel_p,
                                            'abs_path': entry.path,
                                            'file_size': entry.stat().st_size,
                                            'sync_status': 'pending_upload',
                                            'last_modified_local': datetime.fromtimestamp(entry.stat().st_mtime).isoformat()
                                        }
                                        files_list.append(loc_item)
                                        if rel_p not in seen_scope_paths:
                                            seen_scope_paths.add(rel_p)
                                            scope_files_list.append(loc_item)
                    except Exception:
                        pass
            else:
                # ---------------------------------------------------------- #
                # الوضع الاحتياطي غير المتصل (Offline Scan)
                # ---------------------------------------------------------- #
                def _to_rel(abs_p_str):
                    rel_p = os.path.relpath(abs_p_str, sync_root_str).replace("\\", "/")
                    return "" if rel_p == "." else rel_p
                def _count_dir_recursive(dir_path):
                    rec_files = 0
                    direct_dirs = 0
                    try:
                        with os.scandir(dir_path) as it:
                            for e in it:
                                if e.name.startswith(".") or e.name == ".trash" or is_ignored_name(e.name):
                                    continue
                                if e.is_dir(follow_symlinks=False):
                                    direct_dirs += 1
                                elif e.is_file(follow_symlinks=False):
                                    rec_files += 1
                        for root_d, d_names, f_names in os.walk(dir_path):
                            d_names[:] = [d for d in d_names if not d.startswith(".") and d != ".trash" and not is_ignored_name(d)]
                            if os.path.normpath(root_d) == os.path.normpath(dir_path):
                                continue
                            for fn in f_names:
                                if not fn.startswith(".") and not is_ignored_name(fn):
                                    rec_files += 1
                    except OSError:
                        pass
                    return rec_files, direct_dirs
                try:
                    with os.scandir(self.sync_folder) as root_it:
                        for entry in root_it:
                            if entry.name.startswith(".") or entry.name.startswith("~$") or entry.name == ".trash":
                                continue
                            if entry.is_dir(follow_symlinks=False) and _can_show_dept(entry.name):
                                local_dept_names.append(entry.name)
                                r_cnt, _ = _count_dir_recursive(entry.path)
                                dept_counts[entry.name] = r_cnt
                                total_root_items += r_cnt
                except OSError:
                    pass
                scan_folder_target = current_abs
                if norm_sub == "" and len(local_dept_names) == 1:
                    single_dept_abs = self.sync_folder / local_dept_names[0]
                    if single_dept_abs.exists():
                        scan_folder_target = single_dept_abs
                try:
                    with os.scandir(scan_folder_target) as cur_it:
                        for entry in cur_it:
                            name = entry.name
                            if name.startswith(".") or name == ".trash" or is_ignored_name(name):
                                continue
                            is_d = entry.is_dir(follow_symlinks=False)
                            rel = _to_rel(entry.path)
                            if is_d:
                                r_files, d_Clean = _count_dir_recursive(entry.path)
                                folders_list.append({
                                    'file_name': name,
                                    'is_folder': True,
                                    'item_count': r_files,
                                    'child_count': d_Clean,
                                    'relative_path': rel,
                                    'abs_path': entry.path,
                                    'file_size': 0,
                                    'sync_status': 'synced',
                                    'last_modified_local': ''
                                })
                    with os.scandir(current_abs) as cur_it2:
                        for entry in cur_it2:
                            name = entry.name
                            if name.startswith(".") or name == ".trash" or is_ignored_name(name):
                                continue
                            if entry.is_file(follow_symlinks=False):
                                rel = _to_rel(entry.path)
                                if rel in seen_rel_paths:
                                    continue
                                seen_rel_paths.add(rel)
                                try:
                                    st_info = entry.stat(follow_symlinks=False)
                                    f_size = st_info.st_size
                                    mtime_iso = datetime.fromtimestamp(st_info.st_mtime).isoformat()
                                except OSError:
                                    continue
                                files_list.append({
                                    'file_name': name,
                                    'is_folder': False,
                                    'relative_path': rel,
                                    'abs_path': entry.path,
                                    'file_size': f_size,
                                    'sync_status': 'synced',
                                    'last_modified_local': mtime_iso
                                })
                except OSError:
                    pass
                walk_base = sync_root_str if (scan_dept is None and scan_subpath == Path(".")) else str(current_abs)
                for root_dir, dirs, files in os.walk(walk_base):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".trash" and not is_ignored_name(d) and (root_dir != sync_root_str or _can_show_dept(d))]
                    for f_name in files:
                        if f_name.startswith(".") or is_ignored_name(f_name):
                            continue
                        full_p = os.path.join(root_dir, f_name)
                        sub_rel = _to_rel(full_p)
                        if sub_rel in seen_scope_paths:
                            continue
                        seen_scope_paths.add(sub_rel)
                        try:
                            st_info = os.stat(full_p)
                            f_size = st_info.st_size
                            mtime_iso = datetime.fromtimestamp(st_info.st_mtime).isoformat()
                        except OSError:
                            continue
                        f_obj = {
                            'file_name': f_name,
                            'is_folder': False,
                            'relative_path': sub_rel,
                            'abs_path': full_p,
                            'file_size': f_size,
                            'sync_status': 'synced',
                            'last_modified_local': mtime_iso
                        }
                        scope_files_list.append(f_obj)
                        if scan_dept is None and scan_subpath == Path(".") and sub_rel not in seen_rel_paths:
                            seen_rel_paths.add(sub_rel)
                            files_list.append(f_obj)
            folders_list.sort(key=lambda x: x['file_name'].lower())
            files_list.sort(key=lambda x: x['file_name'].lower())
            scope_files_list.sort(key=lambda x: x['file_name'].lower())
            trash_cnt = self.state_mgr.get_trash_count(dept_name=scan_dept)
            payload = {
                'scan_dept': scan_dept,
                'scan_subpath': scan_subpath,
                'force_now': force_now,
                'folders_list': folders_list,
                'files_list': files_list,
                'scope_files_list': scope_files_list,
                'trash_cnt': trash_cnt,
                'local_dept_names': local_dept_names,
                'dept_counts': dept_counts,
                'total_root_items': total_root_items,
            }
            self.bridge.scan_ready.emit(payload)
            if need_cloud_refresh:
                self._schedule_cloud_refresh()
        except Exception as e:
            print(f"[Background Scan Error]: {e}")
        finally:
            self._scan_in_progress = False
            if getattr(self, '_scan_pending', False):
                self._scan_pending = False
                self.bridge.rescan_requested.emit()
    def _apply_scan_results(self, payload):
        """تطبيق نتائج الفحص الخلفي على عناصر الواجهة الرسومية بسلاسة تامة على خيط Qt الرئيسي"""
        try:
            if payload.get('scan_dept') != self.active_dept_name or payload.get('scan_subpath') != self.current_subpath:
                self._force_full_render = True
                self._nav_cache_ok = True
                self._refresh_file_list()
                return
            self._dept_counts_cache = payload.get('dept_counts', {})
            self._total_root_items_cache = payload.get('total_root_items', 0)
            # تحديث قائمة الأقسام إذا ظهر مجلد قسم جديد على القرص
            local_dept_names = payload.get('local_dept_names', [])
            current_names = [d['name'] for d in self.departments_list]
            dept_added = False
            for l_name in local_dept_names:
                if l_name not in current_names:
                    self.departments_list.append({"name": l_name, "icon": "📁"})
                    dept_added = True
            if dept_added:
                self.state_mgr.set_departments(self.departments_list)
                self._refresh_departments_sidebar(force_rebuild=True)
            folders_list = payload.get('folders_list', [])
            files_list = payload.get('files_list', [])
            scope_files_list = payload.get('scope_files_list') or files_list
            self.scope_files_cache = scope_files_list
            trash_cnt = payload.get('trash_cnt', 0) + len(getattr(self, '_cloud_trash_cache', []))
            force_now = payload.get('force_now', False) or getattr(self, '_force_full_render', False)
            self._force_full_render = False
            all_items = folders_list + files_list
            self.all_files_cache = all_items
            count_source = scope_files_list if scope_files_list else files_list
            word_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'word')
            excel_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'excel')
            access_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'access')
            pdf_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'pdf')
            images_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) == 'image')
            other_cnt = sum(1 for x in count_source if get_type_key(x['file_name']) in ('video', 'audio', 'archive', 'other'))
            folders_cnt = len(folders_list)
            self.tab_all.setText(f"الكل ({len(count_source)})")
            if hasattr(self, 'lbl_file_count_badge'):
                self.lbl_file_count_badge.setText(f"{len(count_source)} ملف")
            if hasattr(self, 'pill_all_depts'):
                self.pill_all_depts.setText(f"كافة الأقسام ({len(count_source)})")
            self.tab_folders.setText(f"المجلدات ({folders_cnt})" if folders_cnt > 0 else "المجلدات")
            self.tab_word.setText(f"Word ({word_cnt})")
            self.tab_excel.setText(f"Excel ({excel_cnt})")
            self.tab_access.setText(f"Access ({access_cnt})")
            self.tab_pdf.setText(f"PDF ({pdf_cnt})")
            if hasattr(self, 'tab_images'):
                self.tab_images.setText(f"صور ({images_cnt})")
            if hasattr(self, 'tab_other'):
                self.tab_other.setText(f"أخرى ({other_cnt})")
            self.tab_trash.setText(f"🗑️ المحذوفات ({trash_cnt})" if trash_cnt > 0 else "🗑️ المحذوفات")
            self.lbl_total.setText(
                f"المستندات: {len(count_source)}  •  المجلدات: {folders_cnt}"
            )
            self.lbl_trash_stat.setText(f"المحذوفات: {trash_cnt}")
            current_sig = (
                str(self.active_dept_name),
                str(self.current_subpath),
                str(self.active_filter),
                self.search_box.text().strip().lower(),
                self.current_view_mode,
                trash_cnt,
                len(scope_files_list),
                tuple((
                    x.get('relative_path') or x.get('file_name'),
                    x.get('is_folder', False),
                    x.get('file_size', 0),
                    x.get('sync_status', ''),
                    x.get('item_count', 0),
                    x.get('child_count', 0),
                    x.get('last_modified_local', '')
                ) for x in all_items)
            )
            needs_render = force_now or (
                not hasattr(self, '_last_rendered_signature') or self._last_rendered_signature != current_sig
            )
            if needs_render:
                self._last_rendered_signature = current_sig
                _r0 = time.perf_counter()
                self._filter_content()
                _t0 = getattr(self, '_scan_t0', None)
                if force_now and _t0 is not None:
                    print(f"[PERF] scan+render: {(time.perf_counter() - _t0) * 1000:.0f} ms "
                          f"(render {(time.perf_counter() - _r0) * 1000:.0f} ms, {len(all_items)} items)")
            self._refresh_departments_sidebar()
        except Exception as e:
            print(f"[Apply Scan Error]: {e}")
    def _populate_folders_grid(self, folder_items):
        """تحديث شبكة بطاقات المجلدات الرئيسية بشكل متناسق ومطابق لمنصة الويب (3 أعمدة، بارتفاع كامل دون اقتصاص)"""
        self._last_folder_items = folder_items
        while self.subfolders_grid.count():
            item = self.subfolders_grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for c in range(8):
            self.subfolders_grid.setColumnStretch(c, 0)
        self.subfolders_card.setVisible(self.active_filter != "TRASH")
        if not folder_items:
            if hasattr(self, 'subfolders_scroll'):
                self.subfolders_scroll.setVisible(False)
            if hasattr(self, 'btn_toggle_subfolders'):
                self.btn_toggle_subfolders.setVisible(False)
            return
        if hasattr(self, 'btn_toggle_subfolders'):
            self.btn_toggle_subfolders.setVisible(True)
            if not getattr(self, '_folders_manually_collapsed', False):
                self.subfolders_scroll.setVisible(True)
                self.btn_toggle_subfolders.setText("📂 طي المجلدات")
        if hasattr(self, 'lbl_subfolders_count'):
            self.lbl_subfolders_count.setText(f"{len(folder_items)} مجلد")
        w = self.subfolders_scroll.viewport().width() if hasattr(self, 'subfolders_scroll') else self.width()
        if w < 100:
            w = max(900, self.width() - 80)
        cols = max(1, min(3, max(300, w) // 300))
        for c in range(cols):
            self.subfolders_grid.setColumnStretch(c, 1)
        for idx, fld in enumerate(folder_items):
            fcard = WebFolderCard(fld, self)
            r = idx // cols
            c = idx % cols
            self.subfolders_grid.addWidget(fcard, r, c)
        num_rows = (len(folder_items) + cols - 1) // cols
        row_h = 86
        content_h = num_rows * row_h + max(0, num_rows - 1) * 10 + 6
        self.subfolders_content.setFixedHeight(content_h)
        if hasattr(self, 'subfolders_scroll'):
            self.subfolders_scroll.setFixedHeight(min(content_h + 4, 286))
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # إعادة توزيع بطاقات المجلدات والملفات في الشبكة عند تغيير عرض النافذة
        if hasattr(self, '_resize_timer'):
            self._resize_timer.stop()
        else:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._handle_window_resized)
        self._resize_timer.start(120)
    def _handle_window_resized(self):
        try:
            if hasattr(self, 'current_view_mode') and self.current_view_mode == "GRID":
                if hasattr(self, '_last_filtered_items'):
                    self._render_grid(self._last_filtered_items)
            if hasattr(self, 'subfolders_card') and self.subfolders_card.isVisible():
                if hasattr(self, '_last_folder_items') and self._last_folder_items:
                    self._populate_folders_grid(self._last_folder_items)
        except Exception:
            pass

    def _render_grid(self, files):
        """عرض شبكة البطاقات المتجاوبة مع فصل المجلدات عن الملفات بالكامل وإصلاح تداخل وتشوه الشبكة"""
        v_bar = self.grid_scroll.verticalScrollBar()
        if v_bar.isSliderDown():
            return
        prev_scroll = v_bar.value()
        # 1. فصل المجلدات عن الملفات
        visible_folders = [f for f in files if f.get('is_folder', False)]
        visible_files = [f for f in files if not f.get('is_folder', False)]
        # 2. تحديث قسم المجلدات الفرعية في الأعلى
        is_root = (self.active_dept_name is None and self.current_subpath == Path("."))
        has_search = bool(self.search_box.text().strip())
        if visible_folders:
            self._populate_folders_grid(visible_folders)
        elif is_root and not has_search and self.departments_list:
            dept_counts = getattr(self, '_dept_counts_cache', {})
            dept_folders = []
            for dept in self.departments_list:
                dname = dept['name']
                dept_folders.append({
                    'name': dname,
                    'file_name': dname,
                    'relative_path': dname,
                    'is_folder': True,
                    'is_dept': True,
                    'item_count': dept_counts.get(dname, 0),
                    'child_count': 0
                })
            self._populate_folders_grid(dept_folders)
        else:
            self._populate_folders_grid([])
        # 3. عرض الملفات فقط في شبكة البطاقات السفلية
        self.grid_scroll.setUpdatesEnabled(False)
        try:
            while self.grid_layout.count():
                item = self.grid_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            for c in range(8):
                self.grid_layout.setColumnStretch(c, 0)
            for r in range(max(1, self.grid_layout.rowCount())):
                self.grid_layout.setRowStretch(r, 0)
            if not visible_files:
                self.grid_container.setMinimumHeight(140)
                self.grid_container.setMaximumHeight(16777215)
                empty_lbl = QLabel("لا توجد مستندات تطابق هذا التصنيف أو معايير البحث.")
                empty_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                empty_lbl.setStyleSheet("color: #667085; padding: 40px; background: transparent;")
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.grid_layout.addWidget(empty_lbl, 0, 0, 1, 3)
                return
            viewport_w = self.grid_scroll.viewport().width() if hasattr(self, 'grid_scroll') else 960
            if viewport_w < 100:
                viewport_w = max(900, self.width() - 80)
            cols = max(2, min(3, max(520, viewport_w) // 300))
            for c in range(cols):
                self.grid_layout.setColumnStretch(c, 1)
            for idx, f in enumerate(visible_files):
                card = GovFileCard(f, self)
                row = idx // cols
                col = idx % cols
                self.grid_layout.addWidget(card, row, col)
            num_rows = (len(visible_files) + cols - 1) // cols
            row_h = 194
            content_h = num_rows * row_h + max(0, num_rows - 1) * 12 + 24
            self.grid_container.setFixedHeight(content_h)
        finally:
            self.grid_scroll.setUpdatesEnabled(True)
        if not getattr(self, '_reset_scroll_on_render', False):
            v_bar.setValue(prev_scroll)
            QTimer.singleShot(0, lambda: v_bar.setValue(prev_scroll))
        else:
            self._reset_scroll_on_render = False
            v_bar.setValue(0)

    def _render_compact(self, files):
        v_bar = self.compact_scroll.verticalScrollBar()
        if v_bar.isSliderDown():
            return
        prev_scroll = v_bar.value()
        self.compact_scroll.setUpdatesEnabled(False)
        try:
            while self.compact_layout.count():
                item = self.compact_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            if not files:
                empty_lbl = QLabel("لا توجد مستندات تطابق هذا التصنيف أو معايير البحث.")
                empty_lbl.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Medium))
                empty_lbl.setStyleSheet("color: #667085; padding: 50px; background: transparent;")
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.compact_layout.addWidget(empty_lbl)
                return
            for f in files:
                tile = GovCompactTile(f, self)
                self.compact_layout.addWidget(tile)
            self.compact_layout.addStretch()
        finally:
            self.compact_scroll.setUpdatesEnabled(True)
        if not getattr(self, '_reset_scroll_on_render', False):
            v_bar.setValue(prev_scroll)
            QTimer.singleShot(0, lambda: v_bar.setValue(prev_scroll))
        else:
            self._reset_scroll_on_render = False
            v_bar.setValue(0)
    def _render_table(self, files):
        v_bar = self.table.verticalScrollBar()
        prev_scroll = v_bar.value()
        if v_bar.isSliderDown():
            return
        selected_rel = None
        selected_items = self.table.selectedItems()
        if selected_items:
            try:
                row_sel = selected_items[0].row()
                c0 = self.table.item(row_sel, 0)
                c1 = self.table.item(row_sel, 1)
                selected_rel = (c1.data(Qt.ItemDataRole.UserRole) if c1 else None) or (c0.data(Qt.ItemDataRole.UserRole) if c0 else None)
            except Exception:
                pass
        # 1. فصل المجلدات عن الملفات
        visible_folders = [f for f in files if f.get('is_folder', False)]
        visible_files = [f for f in files if not f.get('is_folder', False)]
        # 2. تحديث قسم المجلدات الفرعية (Subfolders Grid) عبر الدالة الموحدة
        is_root = (self.active_dept_name is None and self.current_subpath == Path("."))
        has_search = bool(self.search_box.text().strip())
        if visible_folders:
            self._populate_folders_grid(visible_folders)
        elif is_root and not has_search and self.departments_list:
            dept_counts = getattr(self, '_dept_counts_cache', {})
            dept_folders = []
            for dept in self.departments_list:
                dname = dept['name']
                dept_folders.append({
                    'name': dname,
                    'file_name': dname,
                    'relative_path': dname,
                    'is_folder': True,
                    'is_dept': True,
                    'item_count': dept_counts.get(dname, 0),
                    'child_count': 0
                })
            self._populate_folders_grid(dept_folders)
        else:
            self._populate_folders_grid([])
        # 3. جدول الملفات
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            target_count = len(visible_files)
            if self.table.rowCount() != target_count:
                self.table.setRowCount(target_count)
            matched_selected_row = None
            for row, f in enumerate(visible_files):
                name = f['file_name']
                rel_path = f.get('relative_path') or name
                abs_path = f.get('abs_path')
                row_h = 68 if len(name) > 54 else 54
                if self.table.rowHeight(row) != row_h:
                    self.table.setRowHeight(row, row_h)
                # استخراج اسم المجلد أو القسم
                if "/" in rel_path:
                    folder_label = rel_path.rsplit("/", 1)[0]
                elif self.active_dept_name:
                    folder_label = self.active_dept_name
                else:
                    folder_label = "كافة الأقسام"
                # الحجم
                size_bytes = f.get('file_size', 0)
                if size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                elif size_bytes < 1048576:
                    size_str = f"{round(size_bytes / 1024, 1)} KB"
                else:
                    size_str = f"{round(size_bytes / 1048576, 2)} MB"
                # تأريخ التعديل بصيغة عربية
                date_raw = f.get('last_modified_local', '')
                date_str = format_arabic_datetime(date_raw)
                # الحالة
                sync_st = f.get('sync_status', 'synced')
                if sync_st == 'synced':
                    status_text = "• متزامن"
                    status_fg = "#065F46"
                    status_bg = "#ECFDF3"
                    status_bd = "#A6F4C5"
                elif sync_st == 'cloud_only':
                    status_text = "• سحابي"
                    status_fg = "#1E40AF"
                    status_bg = "#EFF4FF"
                    status_bd = "#D1E0FF"
                elif sync_st in ('syncing', 'pending_upload'):
                    status_text = "• قيد الرفع..."
                    status_fg = "#B54708"
                    status_bg = "#FFFAEB"
                    status_bd = "#FEDF89"
                elif sync_st == 'locked':
                    status_text = "• قيد التعديل"
                    status_fg = "#F04438"
                    status_bg = "#FEF3F2"
                    status_bd = "#FECDCA"
                else:
                    status_text = "• متزامن"
                    status_fg = "#065F46"
                    status_bg = "#ECFDF3"
                    status_bd = "#A6F4C5"
                # عمود 0: Checkbox
                item0 = self.table.item(row, 0)
                if item0 is None:
                    item0 = QTableWidgetItem()
                    self.table.setItem(row, 0, item0)
                item0.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                item0.setCheckState(Qt.CheckState.Checked if rel_path in self.selected_rel_paths else Qt.CheckState.Unchecked)
                item0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item0.setData(Qt.ItemDataRole.UserRole, rel_path)
                item0.setData(Qt.ItemDataRole.UserRole + 2, name)
                # عمود 1: أيقونة الأوفيس + الاسم الكامل بدون اقتصاص (...)
                item1 = self.table.item(row, 1)
                if item1 is None:
                    item1 = QTableWidgetItem("")
                    self.table.setItem(row, 1, item1)
                else:
                    if item1.text() != "":
                        item1.setText("")
                    item1.setIcon(QIcon())
                item1.setData(Qt.ItemDataRole.UserRole, rel_path)
                item1.setData(Qt.ItemDataRole.UserRole + 1, False)
                item1.setData(Qt.ItemDataRole.UserRole + 2, name)
                item1.setToolTip(f"{name}\nالحجم: {size_str}\nالمسار: {rel_path}")
                existing_name_w = self.table.cellWidget(row, 1)
                if existing_name_w is None or getattr(existing_name_w, '_bound_key', None) != (rel_path, name):
                    name_widget = QWidget()
                    name_widget._bound_key = (rel_path, name)
                    name_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    name_widget.setStyleSheet("background: transparent;")
                    n_lay = QHBoxLayout(name_widget)
                    n_lay.setContentsMargins(10, 4, 8, 4)
                    n_lay.setSpacing(10)
                    ico_lbl = QLabel()
                    ico_lbl.setPixmap(get_file_office_pixmap(name, size=34, is_folder=False, abs_path=abs_path))
                    ico_lbl.setFixedSize(34, 34)
                    ico_lbl.setStyleSheet("background: transparent; border: none;")
                    n_lay.addWidget(ico_lbl)
                    txt_lbl = QLabel(name)
                    txt_lbl.setWordWrap(True)
                    txt_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                    txt_lbl.setStyleSheet("color: #1B1F24; background: transparent; border: none;")
                    txt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    n_lay.addWidget(txt_lbl, stretch=1)
                    self.table.setCellWidget(row, 1, name_widget)
                # عمود 2: القسم / المجلد
                item2 = self.table.item(row, 2)
                if item2 is None:
                    item2 = QTableWidgetItem(folder_label)
                    self.table.setItem(row, 2, item2)
                else:
                    if item2.text() != folder_label:
                        item2.setText(folder_label)
                item2.setFont(QFont("Segoe UI", 9))
                item2.setForeground(QColor("#475467"))
                item2.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                # عمود 3: الحجم
                item3 = self.table.item(row, 3)
                if item3 is None:
                    item3 = QTableWidgetItem(size_str)
                    self.table.setItem(row, 3, item3)
                else:
                    if item3.text() != size_str:
                        item3.setText(size_str)
                item3.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                item3.setForeground(QColor("#475467"))
                item3.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                # عمود 4: آخر تعديل
                item4 = self.table.item(row, 4)
                if item4 is None:
                    item4 = QTableWidgetItem(date_str)
                    self.table.setItem(row, 4, item4)
                else:
                    if item4.text() != date_str:
                        item4.setText(date_str)
                item4.setFont(QFont("Segoe UI", 9))
                item4.setForeground(QColor("#667085"))
                item4.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                # عمود 5: شارة الحالة الكبسولية المطابقة لمنصة الويب
                item5 = self.table.item(row, 5)
                if item5 is None:
                    item5 = QTableWidgetItem("")
                    self.table.setItem(row, 5, item5)
                else:
                    if item5.text() != "":
                        item5.setText("")
                existing_st_w = self.table.cellWidget(row, 5)
                if existing_st_w is None or getattr(existing_st_w, '_bound_status', None) != status_text:
                    st_widget = QWidget()
                    st_widget._bound_status = status_text
                    st_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    st_widget.setStyleSheet("background: transparent;")
                    st_lay = QHBoxLayout(st_widget)
                    st_lay.setContentsMargins(4, 2, 4, 2)
                    st_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    st_pill = QLabel(status_text)
                    st_pill.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    st_pill.setStyleSheet(f"""
                        color: {status_fg}; background-color: {status_bg};
                        border: 1px solid {status_bd}; border-radius: 10px; padding: 2px 9px;
                    """)
                    st_lay.addWidget(st_pill)
                    self.table.setCellWidget(row, 5, st_widget)
                # عمود 6: أزرار الإجراءات
                existing_act = self.table.cellWidget(row, 6)
                if (existing_act is None or getattr(existing_act, '_bound_rel_path', None) != rel_path):
                    act_widget = QWidget()
                    act_widget._bound_rel_path = rel_path
                    act_widget.setStyleSheet("background: transparent;")
                    act_layout = QHBoxLayout(act_widget)
                    act_layout.setContentsMargins(4, 2, 4, 2)
                    act_layout.setSpacing(4)
                    act_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    btn_open = QPushButton("فتح")
                    btn_open.setFixedSize(46, 26)
                    btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    btn_open.setStyleSheet("""
                        QPushButton {
                            background-color: #14372e; color: #FFFFFF; border: none;
                            border-radius: 6px; padding: 0px 4px; font-weight: bold; font-size: 11px;
                        }
                        QPushButton:hover { background-color: #1b493d; }
                    """)
                    btn_open.clicked.connect(lambda _, n=name, rp=rel_path: self._open_file_by_name(n, rp))
                    act_layout.addWidget(btn_open)
                    btn_rename = QPushButton("✎")
                    btn_rename.setToolTip("تعديل الاسم (F2)")
                    btn_rename.setFixedSize(26, 26)
                    btn_rename.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    btn_rename.setStyleSheet("QPushButton { border: 1px solid #E4E7EC; background: #FFFFFF; color: #475467; border-radius: 6px; font-size: 12px; } QPushButton:hover { background: #EDF5F2; color: #14372e; }")
                    btn_rename.clicked.connect(lambda _, n=name, rp=rel_path: self._rename_file(n, rp))
                    act_layout.addWidget(btn_rename)
                    btn_move = QPushButton("✥")
                    btn_move.setToolTip("نقل الملف")
                    btn_move.setFixedSize(26, 26)
                    btn_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    btn_move.setStyleSheet("QPushButton { border: 1px solid #E4E7EC; background: #FFFFFF; color: #475467; border-radius: 6px; font-size: 12px; } QPushButton:hover { background: #F7F8FA; color: #14372e; }")
                    btn_move.clicked.connect(lambda _, n=name, rp=rel_path: self._show_move_items_dialog([{"name": n, "rel_path": rp, "is_folder": False}]))
                    act_layout.addWidget(btn_move)
                    btn_del = QPushButton("🗑")
                    btn_del.setToolTip("نقل للمحذوفات")
                    btn_del.setFixedSize(26, 26)
                    btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    btn_del.setStyleSheet("QPushButton { border: 1px solid #FECDCA; background: #FEF3F2; color: #F04438; border-radius: 6px; font-size: 12px; } QPushButton:hover { background: #FEE4E2; }")
                    btn_del.clicked.connect(lambda _, n=name, rp=rel_path: self._move_file_to_trash(n, rp))
                    act_layout.addWidget(btn_del)
                    self.table.setCellWidget(row, 6, act_widget)
                if selected_rel and (rel_path == selected_rel or name == selected_rel):
                    matched_selected_row = row
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)
        if matched_selected_row is not None:
            self.table.selectRow(matched_selected_row)
    def _open_selected_from_table(self, row, col):
        if col == 6:  # عمود الإجراءات
            return
        cell0 = self.table.item(row, 0)
        cell1 = self.table.item(row, 1)
        if not cell1 and not cell0:
            return
        rel_path = (cell1.data(Qt.ItemDataRole.UserRole) if cell1 else None) or (cell0.data(Qt.ItemDataRole.UserRole) if cell0 else None)
        stored_name = (cell1.data(Qt.ItemDataRole.UserRole + 2) if cell1 else None) or (cell0.data(Qt.ItemDataRole.UserRole + 2) if cell0 else None)
        file_name = stored_name or (cell1.text().split('\n')[0] if cell1 and cell1.text() else "") or (str(rel_path).split('/')[-1] if rel_path else "")
        is_fld = bool(cell1.data(Qt.ItemDataRole.UserRole + 1)) if cell1 else False
        if is_fld:
            self._navigate_into_folder(file_name, rel_path)
        else:
            self._open_file_by_name(file_name, rel_path)
    def _open_file_by_name(self, file_name, rel_path=None):
        target_dept = self.active_dept_name
        if not target_dept and rel_path and "/" in str(rel_path):
            target_dept = str(rel_path).split("/")[0]
        if not self._check_department_permission(target_dept, action='open'):
            return
        file_path = None
        if rel_path:
            cand = (self.sync_folder / rel_path).resolve()
            if cand.exists():
                file_path = cand
        if not file_path:
            cur_cand = (self._get_current_abs_folder() / file_name).resolve()
            if cur_cand.exists():
                file_path = cur_cand
        if not file_path and rel_path:
            file_path = (self.sync_folder / rel_path).resolve()
        if not file_path:
            file_path = (self.sync_folder / file_name).resolve()
        if not file_path.exists():
            import re
            clean = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', file_name).strip().lower()
            for sub in self.sync_folder.rglob("*"):
                if sub.is_file():
                    sub_clean = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', sub.name).strip().lower()
                    if sub_clean == clean:
                        file_path = sub
                        break
        if file_path.exists() and file_path.is_dir():
            self._navigate_into_folder(file_name, rel_path)
            return
        # التحقق من حداثة الملف مقارنة بالسحابة لضمان فتح أحدث نسخة معدلة دائماً
        need_fresh_download = False
        fid = None
        cloud_md5 = None
        if self.client and self.client.is_configured():
            snap = self.client.peek_snapshot() if hasattr(self.client, "peek_snapshot") else None
            remote_info = None
            if snap and hasattr(snap, "files"):
                cand_rel = rel_path or file_name
                remote_info = snap.files.get(cand_rel)
                if not remote_info and rel_path:
                    for r, f in snap.files.items():
                        if f.get("name") == file_name:
                            remote_info = f
                            break
            if remote_info:
                fid = remote_info.get("id")
                cloud_md5 = remote_info.get("md5Checksum")
                if not file_path.exists() or file_path.stat().st_size == 0:
                    need_fresh_download = True
                elif cloud_md5:
                    is_local_newer = False
                    if self.sync_engine and file_path.exists() and file_path.is_file():
                        try:
                            calc_rel = norm_rel(file_path.relative_to(self.sync_folder))
                            st = self.sync_engine.state_mgr.get_file_state(calc_rel)
                            if st:
                                if st.get("sync_status") in ("syncing", "pending_upload"):
                                    is_local_newer = True
                                elif st.get("remote_md5") == cloud_md5 and st.get("sha256_hash"):
                                    loc_h = self.sync_engine.calculate_hash(str(file_path))
                                    if loc_h != st.get("sha256_hash"):
                                        is_local_newer = True
                        except Exception:
                            pass
                    if not is_local_newer:
                        try:
                            loc_hash = self.sync_engine.calculate_hash(str(file_path)) if self.sync_engine else None
                            if loc_hash and loc_hash != cloud_md5:
                                need_fresh_download = True
                        except Exception:
                            pass
        elif not file_path.exists() or file_path.stat().st_size == 0:
            QMessageBox.warning(
                self, "تنبيه", 
                f"الملف التالي غير متوفر محلياً دون اتصال بالسحابة:\n{file_name}"
            )
            return
        if (need_fresh_download or not file_path.exists() or file_path.stat().st_size == 0) and self.client and self.client.is_configured():
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            if not fid:
                fid = self.client.resolve_file_id(rel_path or file_name)
            if fid:
                progress_dlg = QProgressDialog(f"جارٍ تنزيل أحدث نسخة للمستند من السحابة:\n{file_name}", "إلغاء", 0, 100, self)
                progress_dlg.setWindowTitle("Share COC – تحديث سحابي فوري")
                progress_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
                progress_dlg.setMinimumDuration(100)
                progress_dlg.setValue(10)
                def _on_prog(done_b, total_b):
                    pct = int(min(100, (done_b / max(total_b, 1)) * 100))
                    progress_dlg.setValue(pct)
                    QApplication.processEvents()
                temp_dir = self.sync_folder / ".sync_temp"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_dl = temp_dir / f"open_{int(time.time()*1000)}_{file_path.name}.tmp"
                ok = False
                msg = ""
                try:
                    ok, msg = self.client.download_file(file_name, str(temp_dl), storage_path=fid, progress_callback=_on_prog)
                finally:
                    progress_dlg.close()
                if ok and temp_dl.exists():
                    p_rel = None
                    try:
                        p_rel = norm_rel(file_path.relative_to(self.sync_folder))
                    except Exception:
                        p_rel = rel_path or file_name
                    if self.sync_engine:
                        self.sync_engine._mark_self_op(p_rel, seconds=5)
                    applied = OfficeHandler.safe_apply_file(str(file_path), str(temp_dl))
                    if applied and self.sync_engine and file_path.exists():
                        try:
                            st_after = file_path.stat()
                            self.sync_engine._save_state(p_rel, cloud_md5 or "", st_after.st_size, st_after.st_mtime, fid, cloud_md5, status="synced")
                        except Exception:
                            pass
                        self.sync_engine.clear_self_op(p_rel)
                elif not file_path.exists():
                    QMessageBox.warning(
                        self, "تنبيه", 
                        f"تعذر تنزيل الملف من السحابة:\n{file_name}\n({msg})"
                    )
                    return
                if temp_dl.exists():
                    try:
                        temp_dl.unlink(missing_ok=True)
                    except Exception:
                        pass
        if file_path.is_dir():
            self._navigate_into_folder(file_name, rel_path)
            return
        # إذا كان الملف صورة: فتحه في عارض الصور المدمج بالتطبيق مع إمكانية فتحه خارجياً
        if get_type_key(file_path.name) == 'image' and file_path.suffix.lower() not in ('.svg',):
            dlg = ImagePreviewDialog(file_path, self)
            dlg.exec()
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
            self._watch_opened_file_for_changes(file_path, rel_path or file_name)
        except Exception as e:
            QMessageBox.critical(
                self, "خطأ في فتح الملف", 
                f"تعذر تشغيل البرنامج المقترن بالملف:\n{str(e)}"
            )
    def _watch_opened_file_for_changes(self, file_path, rel_path):
        """مراقبة مخصصة للمستند المفتوح لرصد أي حفظ بالضغط على Ctrl+S ومزامنته فوراً مع السحابة وبقية الأجهزة"""
        import time, threading
        def _monitor():
            try:
                p = Path(file_path)
                if not p.exists():
                    return
                last_mtime = p.stat().st_mtime
                last_size = p.stat().st_size
                for _ in range(28800):  # فحص مستمر لمدة تصل إلى 8 ساعات أثناء جلسة العمل
                    time.sleep(1.0)
                    if not p.exists():
                        break
                    try:
                        cur = p.stat()
                        if cur.st_mtime != last_mtime or cur.st_size != last_size:
                            last_mtime = cur.st_mtime
                            last_size = cur.st_size
                            time.sleep(0.5)
                            if hasattr(self, 'sync_engine') and self.sync_engine:
                                if hasattr(self.sync_engine, 'queue_fast_upload'):
                                    self.sync_engine.queue_fast_upload(rel_path or file_name, delay=0.5)
                                else:
                                    self.sync_engine.wake(delay=0.3)
                    except Exception:
                        pass
            except Exception:
                pass
        threading.Thread(target=_monitor, daemon=True).start()
    def _show_table_context_menu(self, pos):
        bulk_items = self._get_currently_selected_items()
        if len(bulk_items) > 1:
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu { background-color: #ffffff; color: #162420; border: 1.5px solid #d5dfdb; border-radius: 8px; padding: 4px; }
                QMenu::item { padding: 8px 24px; border-radius: 4px; font-size: 12px; font-weight: 600; }
                QMenu::item:selected { background-color: #f0f6f4; color: #14372e; font-weight: bold; }
            """)
            act_move = menu.addAction(f"📂 نقل العناصر المحددة ({len(bulk_items)}) إلى قسم/مجلد آخر...")
            act_del = menu.addAction(f"🗑️ حذف العناصر المحددة ({len(bulk_items)}) إلى سلة المحذوفات")
            menu.addSeparator()
            act_clear = menu.addAction("✖ إلغاء التحديد")
            chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
            if chosen == act_move:
                self._show_move_items_dialog(bulk_items)
            elif chosen == act_del:
                self._delete_selected_items_bulk()
            elif chosen == act_clear:
                self._clear_all_selections()
            return
        selected = self.table.selectedItems()
        if not selected:
            return
        row_idx = selected[0].row()
        cell0 = self.table.item(row_idx, 0)
        cell1 = self.table.item(row_idx, 1)
        rel_path = (cell1.data(Qt.ItemDataRole.UserRole) if cell1 else None) or (cell0.data(Qt.ItemDataRole.UserRole) if cell0 else None)
        stored_name = (cell1.data(Qt.ItemDataRole.UserRole + 2) if cell1 else None) or (cell0.data(Qt.ItemDataRole.UserRole + 2) if cell0 else None)
        file_name = stored_name or (cell1.text().split('\n')[0] if cell1 and cell1.text() else "") or (str(rel_path).split('/')[-1] if rel_path else "")
        is_fld = bool(cell1.data(Qt.ItemDataRole.UserRole + 1)) if cell1 else False
        if is_fld:
            self._show_context_menu_for_folder(file_name, self.table.viewport().mapToGlobal(pos))
        else:
            self._show_context_menu_for_file(file_name, self.table.viewport().mapToGlobal(pos), rel_path)
    def _show_context_menu_for_file(self, file_name, global_pos, rel_path=None):
        file_path = None
        if rel_path:
            cand = (self.sync_folder / rel_path).resolve()
            if cand.exists():
                file_path = cand
        if not file_path:
            file_path = (self._get_current_abs_folder() / file_name).resolve()
        if not file_path.exists():
            file_path = (self.sync_folder / file_name).resolve()
        if file_path.is_dir():
            self._show_context_menu_for_folder(file_name, global_pos)
            return
        actual_rel = str(file_path.relative_to(self.sync_folder)).replace("\\", "/") if file_path.exists() else (rel_path or file_name)
        is_img = get_type_key(file_name) == 'image'
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
        open_action = menu.addAction("🖼️ معاينة الصورة داخل التطبيق" if is_img else "⚡ فتح المستند بالبرنامج الأصلي")
        open_ext_action = menu.addAction("🖥️ فتح في عارض الصور الخارجي (Windows)") if is_img else None
        open_folder_action = menu.addAction("📂 استعراض في مجلد Windows")
        move_action = menu.addAction("📂 نقل المستند إلى قسم / مجلد آخر...")
        rename_action = menu.addAction("✏️ تعديل اسم المستند (إعادة تسمية)...")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ نقل المستند إلى سلة المحذوفات")
        action = menu.exec(global_pos)
        if action == open_action:
            self._open_file_by_name(file_name, actual_rel)
        elif open_ext_action and action == open_ext_action:
            if file_path.exists():
                OfficeHandler.open_native_file(str(file_path))
                self._watch_opened_file_for_changes(file_path, actual_rel or file_name)
        elif action == open_folder_action:
            if file_path.exists():
                subprocess.Popen(f'explorer /select,"{str(file_path)}"')
        elif action == move_action:
            self._show_move_items_dialog([{"name": file_name, "rel_path": actual_rel, "is_folder": False}])
        elif action == rename_action:
            self._rename_file(file_name, actual_rel)
        elif action == delete_action:
            self._move_file_to_trash(file_name, actual_rel)
    def _start_cloud_upload_job(self, tasks, folders_to_create, dialog_title, item_label=""):
        """تشغيل عملية نسخ ورفع مباشر إلى السحابة في خيط مستقل مع شريط تقدم فعلي ودعم الإكمال بالخلفية"""
        total = len(tasks)
        progress = QProgressDialog("جاري تحضير المستندات للرفع السحابي...", "إخفاء وإكمال بالخلفية", 0, 100, self)
        progress.setWindowTitle(dialog_title)
        progress.setWindowModality(Qt.WindowModality.NonModal)
        progress.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(520)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.setStyleSheet("""
            QProgressDialog { background-color: #ffffff; font-family: 'Cairo', 'Segoe UI', Tahoma; border-radius: 12px; }
            QLabel { font-size: 12.5px; font-weight: bold; color: #14372e; padding: 6px; }
            QProgressBar {
                border: 1.5px solid #cbd5e1; border-radius: 8px; text-align: center;
                background-color: #f1f5f9; height: 24px; font-weight: bold; color: #0f172a;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #14372e, stop:1 #0d8a55);
                border-radius: 7px;
            }
            QPushButton {
                background-color: #0284c7; color: white; border-radius: 6px; padding: 6px 16px; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        progress.show()
        worker = CloudUploadWorker(
            tasks=tasks,
            folders_to_create=folders_to_create,
            sync_engine=self.sync_engine,
            cloud_client=self.client,
            state_mgr=self.state_mgr,
            sync_folder=self.sync_folder,
            parent=self
        )
        self._active_upload_workers.append(worker)
        state = {"backgrounded": False}
        def on_hide_to_bg():
            state["backgrounded"] = True
            progress.hide()
            if hasattr(self, 'lbl_watcher'):
                self.lbl_watcher.setText("☁️ جاري إكمال رفع الملفات إلى السحابة في الخلفية...")
        progress.canceled.connect(on_hide_to_bg)
        def on_progress(pct, text):
            if not state["backgrounded"] and progress.isVisible():
                progress.setValue(pct)
                progress.setLabelText(text)
            if hasattr(self, 'lbl_watcher'):
                first_line = str(text).split('\n')[0]
                self.lbl_watcher.setText(f"⚡ {first_line} ({pct}%)")
        def on_local_done():
            self._force_full_render = True
            self._refresh_file_list()
        def on_finished(local_ok, cloud_ok, total_cnt, failed_names):
            try:
                progress.close()
                progress.deleteLater()
            except Exception:
                pass
            if worker in self._active_upload_workers:
                self._active_upload_workers.remove(worker)
            if self.sync_engine:
                self.sync_engine.wake(delay=0.3)
            self._force_full_render = True
            self._refresh_file_list()
            self._refresh_departments_sidebar()
            if hasattr(self, 'lbl_watcher'):
                if cloud_ok == total_cnt:
                    self.lbl_watcher.setText("⚡ المزامنة: تم حفظ ومزامنة كافة الملفات في السحابة بنجاح ✅")
                else:
                    self.lbl_watcher.setText(f"⚡ المزامنة: تم رفع {cloud_ok}/{total_cnt} للسحابة وجارٍ استكمال الباقي تلقائياً")
            if not state["backgrounded"]:
                if cloud_ok == total_cnt and total_cnt > 0:
                    QMessageBox.information(
                        self,
                        "اكتمل الرفع والمزامنة السحابية بنجاح ✅",
                        f"✅ تم رفع وتخزين ({cloud_ok} من أصل {total_cnt}) مستند {item_label} في السحابة (Google Drive) بنجاح.\n\n"
                        f"المستندات متاحة الآن فوراً على جميع الأجهزة ومنصة الويب."
                    )
                else:
                    QMessageBox.information(
                        self,
                        "تم الحفظ وبدأت المزامنة التلقائية",
                        f"✅ تم حفظ ({local_ok} من أصل {total_cnt}) مستند ورفع ({cloud_ok}) منها مباشرة للسحابة.\n"
                        f"سيقوم محرك المزامنة الخلفي باستكمال رفع الملفات المتبقية تلقائياً."
                    )
        worker.progress_signal.connect(on_progress)
        worker.local_copy_done.connect(on_local_done)
        worker.finished_signal.connect(on_finished)
        worker.start()
    def _upload_custom_file(self):
        """إضافة مستندات أو صور أو وسائط متعددة من أي مكان في الحاسوب ورفعها فعلياً ومباشرة إلى السحابة"""
        if not self._check_department_permission(self.active_dept_name, action='upload'):
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "اختر ملفات أو صور أو مستندات لرفعها إلى السحابة (يمكنك تحديد عدة ملفات معاً)", "",
            "كافة الملفات والصور والوثائق (*.*);;الصور والوثائق المصورة (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff);;ملفات Office والـ PDF (*.docx *.xlsx *.accdb *.pdf *.doc *.xls *.pptx);;الأرشيف والوسائط (*.zip *.rar *.7z *.mp4 *.mp3 *.wav)"
        )
        if not paths:
            return
        target_dir = self._get_current_abs_folder()
        target_dir.mkdir(parents=True, exist_ok=True)
        folders_to_create = []
        if target_dir != self.sync_folder:
            rel_dir = str(target_dir.relative_to(self.sync_folder)).replace("\\", "/")
            if rel_dir and rel_dir != ".":
                folders_to_create.append(rel_dir)
        tasks = []
        for path in paths:
            p = Path(path)
            dest = target_dir / p.name
            rel = str(dest.relative_to(self.sync_folder)).replace("\\", "/")
            tasks.append((p, dest, rel))
        self._start_cloud_upload_job(
            tasks=tasks,
            folders_to_create=folders_to_create,
            dialog_title="رفع الملفات ومزامنتها في السحابة"
        )
    def _upload_custom_folder(self):
        """إضافة مجلد كامل بمحتوياته ومجلداته الفرعية ورفعه فعلياً إلى السحابة"""
        if not self._check_department_permission(self.active_dept_name, action='upload'):
            return
        folder_path = QFileDialog.getExistingDirectory(
            self, "اختر مجلداً بالكامل لرفعه ومزامنته في السحابة", ""
        )
        if not folder_path:
            return
        src_dir = Path(folder_path)
        target_base = self._get_current_abs_folder() / src_dir.name
        rel_base = str(target_base.relative_to(self.sync_folder)).replace("\\", "/")
        from gdrive_client import is_ignored_name
        all_files = [p for p in src_dir.rglob("*") if p.is_file() and not is_ignored_name(p.name)]
        folders_to_create = [rel_base]
        for sub_dir in src_dir.rglob("*"):
            if sub_dir.is_dir() and not sub_dir.name.startswith('.'):
                sub_target = target_base / sub_dir.relative_to(src_dir)
                rel_sub_dir = str(sub_target.relative_to(self.sync_folder)).replace("\\", "/")
                if rel_sub_dir not in folders_to_create:
                    folders_to_create.append(rel_sub_dir)
        if not all_files:
            target_base.mkdir(parents=True, exist_ok=True)
            if self.sync_engine and hasattr(self.sync_engine, 'clear_tombstone'):
                self.sync_engine.clear_tombstone(rel_base)
            if self.client and self.client.is_configured():
                self._run_cloud_async(self.client.ensure_folder, rel_base)
            self._force_full_render = True
            self._refresh_file_list()
            QMessageBox.information(self, "تم إنشاء المجلد السحابي", f"✅ تم إنشاء المجلد '{src_dir.name}' ومزامنته مع السحابة بنجاح.")
            return
        tasks = []
        for src_file in all_files:
            rel_sub = src_file.relative_to(src_dir)
            dest_file = target_base / rel_sub
            rel = str(dest_file.relative_to(self.sync_folder)).replace("\\", "/")
            tasks.append((src_file, dest_file, rel))
        self._start_cloud_upload_job(
            tasks=tasks,
            folders_to_create=folders_to_create,
            dialog_title=f"رفع المجلد السحابي: {src_dir.name}",
            item_label=f"ضمن مجلد '{src_dir.name}'"
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
        btn_renew_gdrive = QPushButton("🔑 تجديد تفويض ورمز Google Drive السحابي")
        btn_renew_gdrive.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_renew_gdrive.setStyleSheet("background: #027A48; color: white; border-radius: 8px; padding: 10px; font-weight: bold; font-family: 'IBM Plex Sans Arabic', 'Cairo';")
        def on_launch_renew():
            import subprocess
            renew_script = Path(__file__).resolve().parent.parent.parent / "scripts" / "renew_cloud_gui.py"
            if renew_script.exists():
                subprocess.Popen([sys.executable, str(renew_script)])
            else:
                QMessageBox.information(dialog, "تجديد التفويض", "يرجى تشغيل أداة تجديد التفويض السحابي من مجلد scripts.")
        btn_renew_gdrive.clicked.connect(on_launch_renew)
        layout.addWidget(btn_renew_gdrive)
        dialog.exec()
    def handle_sync_update(self, data):
        is_transient = isinstance(data, dict) and data.get('event') == 'syncing'
        if isinstance(data, dict) and hasattr(self, 'lbl_watcher'):
            status_txt = data.get('status')
            file_txt = data.get('file')
            if status_txt and file_txt:
                short_name = os.path.basename(str(file_txt))
                if len(short_name) > 26:
                    short_name = short_name[:23] + '...'
                self.lbl_watcher.setText(f"⚡ {status_txt} ({short_name})")
                if hasattr(self, 'lbl_sync_center_live') and self.lbl_sync_center_live:
                    self.lbl_sync_center_live.setText(f"⚡ {status_txt}: {short_name}")
                if not is_transient:
                    self._append_sync_log(status_txt, str(file_txt), "✅ متزامن مع السحابة")
            elif status_txt:
                self.lbl_watcher.setText(f"⚡ المزامنة: {status_txt}")
                if hasattr(self, 'lbl_sync_center_live') and self.lbl_sync_center_live:
                    self.lbl_sync_center_live.setText(f"✅ حالة المزامنة السحابية: {status_txt}")
        if not is_transient and hasattr(self, '_ui_refresh_timer') and not self._ui_refresh_timer.isActive():
            self._ui_refresh_timer.start(350)
    def _setup_tray(self):
        """أيقونة شريط المهام بجانب الساعة في ويندوز مع قائمة سريعة متكاملة"""
        self.tray = QSystemTrayIcon(self)
        if self.logo_path.exists():
            self.tray.setIcon(QIcon(str(self.logo_path)))
        else:
            self.tray.setIcon(self.windowIcon())
        self.tray.setToolTip("Share COC v4.0 – غرفة تجارة كربلاء المقدسة (المزامنة السحابية نشطة)")
        menu = QMenu()
        open_action = menu.addAction("📂 فتح النافذة الرئيسية (Share COC)")
        open_action.triggered.connect(self.bring_to_front)
        sync_center_action = menu.addAction("☁️ فتح مركز المزامنة والرفع")
        sync_center_action.triggered.connect(lambda: (self.bring_to_front(), self._switch_workspace_page(1)))
        upload_action = menu.addAction("➕ رفع ملف سريع إلى السحابة")
        upload_action.triggered.connect(lambda: (self.bring_to_front(), self._upload_custom_file()))
        sync_now_action = menu.addAction("⚡ مزامنة فورية الآن")
        sync_now_action.triggered.connect(self._on_refresh_clicked)
        open_folder_action = menu.addAction("📁 فتح المجلد المشترك (FileExchangeShared)")
        open_folder_action.triggered.connect(lambda: os.startfile(str(self.sync_folder)))
        menu.addSeparator()
        quit_action = menu.addAction("🚪 إغلاق البرنامج نهائياً")
        quit_action.triggered.connect(self._quit_application)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.bring_to_front() if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick
            ) else None
        )
        self.tray.show()
    def _quit_application(self):
        """إغلاق البرنامج نهائياً وإيقاف المزامنة الخلفية"""
        self._force_quit = True
        self.close()
    def closeEvent(self, event):
        """عند الضغط على X: تصغير للشريط بجانب الساعة إذا كان الخيار مفعلاً، أو إغلاق كامل عند الخروج النهائي"""
        minimize_pref = self.state_mgr.get_setting("minimize_to_tray", "1") != "0"
        if not getattr(self, '_force_quit', False) and minimize_pref and hasattr(self, 'tray') and self.tray and self.tray.isVisible():
            event.ignore()
            self.hide()
            if not getattr(self, '_tray_notified_once', False):
                self._tray_notified_once = True
                try:
                    self.tray.showMessage(
                        "Share COC – غرفة تجارة كربلاء المقدسة",
                        "البرنامج يستمر بالعمل في الخلفية بجانب الساعة لضمان المزامنة الفورية للمستندات.",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000
                    )
                except Exception:
                    pass
            return
        try:
            if hasattr(self, 'timer'):
                self.timer.stop()
            if hasattr(self, 'dept_cloud_timer'):
                self.dept_cloud_timer.stop()
            if hasattr(self, '_ui_refresh_timer'):
                self._ui_refresh_timer.stop()
            if hasattr(self, 'tray') and self.tray:
                self.tray.hide()
            if hasattr(self, 'sync_engine') and self.sync_engine:
                import threading
                threading.Thread(target=self.sync_engine.stop, daemon=True).start()
        except Exception:
            pass
        event.accept()
        QApplication.instance().quit()
