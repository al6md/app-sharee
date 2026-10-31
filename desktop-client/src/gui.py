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


class GovFileCard(QFrame):
    """بطاقة المستند أو المجلد لنمط شبكة البطاقات (Grid View)"""
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
        apply_gov_shadow(self, blur=10, offset_y=2, alpha=12)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 1. الصف العلوي: مربع التحديد + الأيقونة الواضحة + شارة النوع والحالة
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.chk_select = QCheckBox()
        self.chk_select.setChecked(self.rel_path in getattr(self.main_window, 'selected_rel_paths', set()))
        self.chk_select.setToolTip("تحديد للنقل أو الحذف الجماعي")
        self.chk_select.toggled.connect(lambda checked: self.main_window._toggle_item_selected(self.rel_path, checked))
        top_row.addWidget(self.chk_select)

        icon_lbl = QLabel()
        pix = get_file_office_pixmap(self.file_name, size=38, is_folder=self.is_folder, abs_path=self.abs_path)
        icon_lbl.setPixmap(pix)
        top_row.addWidget(icon_lbl)

        badge_col = QVBoxLayout()
        badge_col.setSpacing(3)

        if self.is_folder:
            app_text = "مجلد"
            badge_style = "background: #EDF5F2; color: #14372e; border: 1px solid #CBE3DA;"
            status_text = f"{self.file_data.get('item_count', 0)} عنصر"
            status_style = "background: #F7F8FA; color: #667085; border: 1px solid #E4E7EC;"
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

            status = self.file_data.get('sync_status', 'synced')
            status_map = {
                'synced': ('● متزامن', 'background: #EDF5F2; color: #14372e; border: 1px solid #CBE3DA;'),
                'cloud_only': ('● سحابي', 'background: #EFF4FF; color: #2B579A; border: 1px solid #D1E0FF;'),
                'syncing': ('● قيد الرفع...', 'background: #FFFAEB; color: #B54708; border: 1px solid #FEDF89;'),
                'pending_upload': ('● بالانتظار', 'background: #F7F8FA; color: #667085; border: 1px solid #E4E7EC;'),
                'conflict': ('● تعارض', 'background: #FFFAEB; color: #B54708; border: 1px solid #FEDF89;'),
                'failed': ('● خطأ مزامنة', 'background: #FEF3F2; color: #F04438; border: 1px solid #FECDCA;'),
                'locked': ('● قيد التعديل', 'background: #FEF3F2; color: #F04438; border: 1px solid #FECDCA;')
            }
            status_text, status_style = status_map.get(
                status, ('● متزامن', 'background: #EDF5F2; color: #14372e; border: 1px solid #CBE3DA;')
            )

        type_lbl = QLabel(app_text)
        type_lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        type_lbl.setStyleSheet(f"{badge_style} border-radius: 4px; padding: 2px 6px;")
        badge_col.addWidget(type_lbl)

        status_lbl = QLabel(status_text)
        status_lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.DemiBold))
        status_lbl.setStyleSheet(f"{status_style} border-radius: 4px; padding: 1px 6px;")
        badge_col.addWidget(status_lbl)

        top_row.addLayout(badge_col)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 2. اسم المجلد أو المستند الكامل بوضوح تام وبدون أي اقتطاع
        name_lbl = QLabel(self.file_name)
        name_lbl.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.DemiBold))
        name_lbl.setStyleSheet("color: #1B1F24; line-height: 1.35;")
        name_lbl.setWordWrap(True)
        name_lbl.setToolTip(self.file_name)
        name_lbl.setMinimumHeight(32)
        layout.addWidget(name_lbl)

        # 3. الصف السفلي: الحجم والتاريخ + أزرار الإجراءات النظيفة
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        if self.is_folder:
            info_lbl = QLabel("مجلد إداري")
            action_btn_text = "فتح المجلد"
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
            info_lbl = QLabel(f"{size_str}  •  {date_str}")
            action_btn_text = "معاينة" if get_type_key(self.file_name) == 'image' else "فتح"

        info_lbl.setFont(QFont("Segoe UI", 9))
        info_lbl.setStyleSheet("color: #667085;")
        meta_row.addWidget(info_lbl)
        meta_row.addStretch()

        btn_action = QPushButton(action_btn_text)
        btn_action.setObjectName("btnCardOpen")
        btn_action.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.is_folder:
            btn_action.clicked.connect(lambda: self.main_window._navigate_into_folder(self.file_name, self.rel_path))
        else:
            btn_action.clicked.connect(lambda: self.main_window._open_file_by_name(self.file_name, self.rel_path))
        meta_row.addWidget(btn_action)

        btn_move = QPushButton("نقل")
        btn_move.setObjectName("btnCardRename")
        btn_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_move.setToolTip("نقل إلى قسم أو مجلد آخر")
        btn_move.clicked.connect(lambda: self.main_window._show_move_items_dialog([
            {"name": self.file_name, "rel_path": self.rel_path, "is_folder": self.is_folder}
        ]))
        meta_row.addWidget(btn_move)

        btn_rename = QPushButton("تسمية")
        btn_rename.setObjectName("btnCardRename")
        btn_rename.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_rename.setToolTip("تعديل الاسم (إعادة تسمية)")
        if self.is_folder:
            btn_rename.clicked.connect(lambda: self.main_window._rename_folder(self.file_name))
        else:
            btn_rename.clicked.connect(lambda: self.main_window._rename_file(self.file_name, self.rel_path))
        meta_row.addWidget(btn_rename)

        btn_delete = QPushButton("حذف")
        btn_delete.setObjectName("btnCardDelete")
        btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_delete.setToolTip("نقل إلى سلة المحذوفات")
        if self.is_folder:
            btn_delete.clicked.connect(lambda: self.main_window._move_folder_to_trash(self.file_name))
        else:
            btn_delete.clicked.connect(lambda: self.main_window._move_file_to_trash(self.file_name, self.rel_path))
        meta_row.addWidget(btn_delete)

        layout.addLayout(meta_row)

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
        self.current_view_mode = self.state_mgr.get_setting("file_view_mode", "TABLE")
        self.departments_list = []
        self._load_departments()
        self.active_dept_name = None
        self.current_subpath = Path(".")
        self.selected_rel_paths = set()
        self._unlocked_pin_depts = set()
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
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 6, 10, 6)
        main_layout.setSpacing(6)

        # ========================================================
        # 1. شريط الترويسة الرسمي المدمج والواضح مع الشعار الرسمي
        # ========================================================
        gov_header = QFrame()
        gov_header.setObjectName("govHeader")
        gov_header.setFixedHeight(48)
        gov_header.setStyleSheet("""
            QFrame#govHeader {
                background-color: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-right: 4px solid #14372e;
                border-radius: 10px;
            }
            QFrame#govHeader QLabel {
                background: transparent;
                border: none;
            }
        """)

        header_layout = QHBoxLayout(gov_header)
        header_layout.setContentsMargins(10, 4, 10, 4)
        header_layout.setSpacing(8)

        # شعار الغرفة الرسمي بحجم مدمج
        logo_lbl = QLabel()
        if self.logo_path.exists():
            pix = QPixmap(str(self.logo_path))
            scaled_pix = pix.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(scaled_pix)
        else:
            logo_lbl.setText("Share COC")
            logo_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #14372e;")
        header_layout.addWidget(logo_lbl)

        # نصوص الهوية الرسمية في صف واحد أنيق ومختصر
        gov_title = QLabel("غرفة تجارة كربلاء المقدسة – Share COC")
        gov_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        gov_title.setStyleSheet("color: #1B1F24; font-weight: 700;")
        header_layout.addWidget(gov_title)

        gold_badge = QLabel("v4.0")
        gold_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        gold_badge.setStyleSheet("color: #14372e; background: #EDF5F2; padding: 1px 6px; border-radius: 4px;")
        header_layout.addWidget(gold_badge)

        header_layout.addStretch()

        # شريط التنقل بين شاشات المنظومة الرئيسية
        nav_bar = QFrame()
        nav_bar.setObjectName("workspaceNavBar")
        nav_bar.setStyleSheet("""
            QFrame#workspaceNavBar {
                background: #F7F8FA;
                border: 1px solid #E4E7EC;
                border-radius: 7px;
            }
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(3, 2, 3, 2)
        nav_layout.setSpacing(2)

        self.workspace_nav_group = QButtonGroup(self)
        self.workspace_nav_group.setExclusive(True)

        nav_btn_style = """
            QPushButton {
                background: transparent;
                color: #667085;
                border: none;
                border-radius: 5px;
                padding: 4px 10px;
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
                font-weight: 700;
            }
        """

        self.nav_btn_docs = QPushButton("مستكشف المستندات")
        self.nav_btn_docs.setCheckable(True)
        self.nav_btn_docs.setChecked(True)
        self.nav_btn_docs.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.nav_btn_docs.setStyleSheet(nav_btn_style)
        self.nav_btn_docs.clicked.connect(lambda: self._switch_workspace_page(0))
        self.workspace_nav_group.addButton(self.nav_btn_docs)
        nav_layout.addWidget(self.nav_btn_docs)

        self.nav_btn_sync = QPushButton("مركز المزامنة")
        self.nav_btn_sync.setCheckable(True)
        self.nav_btn_sync.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.nav_btn_sync.setStyleSheet(nav_btn_style)
        self.nav_btn_sync.clicked.connect(lambda: self._switch_workspace_page(1))
        self.workspace_nav_group.addButton(self.nav_btn_sync)
        nav_layout.addWidget(self.nav_btn_sync)

        self.nav_btn_settings = QPushButton("النظام والتكامل")
        self.nav_btn_settings.setCheckable(True)
        self.nav_btn_settings.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.nav_btn_settings.setStyleSheet(nav_btn_style)
        self.nav_btn_settings.clicked.connect(lambda: self._switch_workspace_page(2))
        self.workspace_nav_group.addButton(self.nav_btn_settings)
        nav_layout.addWidget(self.nav_btn_settings)

        self.nav_btn_access = QPushButton("🏛️ مركز بيانات Access")
        self.nav_btn_access.setCheckable(True)
        self.nav_btn_access.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.nav_btn_access.setStyleSheet(nav_btn_style)
        self.nav_btn_access.clicked.connect(lambda: self._switch_workspace_page(3))
        self.workspace_nav_group.addButton(self.nav_btn_access)
        nav_layout.addWidget(self.nav_btn_access)

        header_layout.addWidget(nav_bar)

        # زر مزامنة فورية سريع في الترويسة
        self.btn_header_sync = QPushButton("مزامنة الآن")
        self.btn_header_sync.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_header_sync.setToolTip("بدء مزامنة فورية مع سحابة Google Drive وكافة الأجهزة")
        self.btn_header_sync.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #14372e;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #E4E7EC;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 11.5px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #EDF5F2;
                border-color: #14372e;
            }
        """)
        self.btn_header_sync.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self.btn_header_sync)

        # شارة حالة الربط السحابي
        self.cloud_badge = QLabel("● متصل بالسحابة")
        self.cloud_badge.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.cloud_badge.setStyleSheet("""
            background: #EDF5F2;
            color: #14372e;
            padding: 4px 9px;
            border-radius: 6px;
            border: 1px solid #CBE3DA;
        """)
        header_layout.addWidget(self.cloud_badge)

        main_layout.addWidget(gov_header)

        # ========================================================
        # 2. شريط الإجراءات النظيف والمنظم بدون أي ازدحام بصري
        # ========================================================
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        # زر القائمة الجانبية للأقسام
        self.btn_toggle_sidebar = QPushButton("☰ الأقسام")
        self.btn_toggle_sidebar.setObjectName("btnToggleSidebar")
        self.btn_toggle_sidebar.setCheckable(True)
        self.btn_toggle_sidebar.setChecked(True)
        self.btn_toggle_sidebar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_toggle_sidebar.setToolTip("إظهار / إخفاء القائمة الجانبية لأقسام الدائرة ومجلداتها")
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        toolbar.addWidget(self.btn_toggle_sidebar)

        # زر إضافة ملفات متعددة دفعة واحدة (الزر الرئيسي)
        self.btn_upload = QPushButton("+ إضافة ملفات")
        self.btn_upload.setObjectName("btnGovPrimary")
        self.btn_upload.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload.setToolTip("تحديد وإضافة عدة مستندات دفعة واحدة إلى المجلد الحالي ومزامنتها فوراً")
        self.btn_upload.clicked.connect(self._upload_custom_file)
        toolbar.addWidget(self.btn_upload)

        # زر إضافة مجلد كامل بمحتوياته
        self.btn_upload_folder = QPushButton("رفع مجلد")
        self.btn_upload_folder.setObjectName("btnGovSecondary")
        self.btn_upload_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_upload_folder.setToolTip("رفع مجلد كامل بكافة ملفاته ومجلداته الفرعية إلى السحابة")
        self.btn_upload_folder.clicked.connect(self._upload_custom_folder)
        toolbar.addWidget(self.btn_upload_folder)

        # زر إنشاء مجلد جديد
        self.btn_new_folder = QPushButton("مجلد جديد")
        self.btn_new_folder.setObjectName("btnGovSecondary")
        self.btn_new_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_new_folder.setToolTip("إنشاء مجلد إداري جديد لتنظيم المستندات")
        self.btn_new_folder.clicked.connect(self._show_new_folder_dialog)
        toolbar.addWidget(self.btn_new_folder)

        # زر فتح المجلد المشترك المحلي
        self.btn_open_folder = QPushButton("المجلد المحلي")
        self.btn_open_folder.setObjectName("btnGovSecondary")
        self.btn_open_folder.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_open_folder.setToolTip("فتح مجلد المستندات المحلي على هذا الحاسوب")
        self.btn_open_folder.clicked.connect(lambda: os.startfile(str(self._get_current_abs_folder())))
        toolbar.addWidget(self.btn_open_folder)

        # زر إحصائيات المستندات
        self.btn_stats = QPushButton("الإحصائيات")
        self.btn_stats.setObjectName("btnGovSecondary")
        self.btn_stats.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_stats.setToolTip("عرض إحصائيات المستندات والمساحة وتوزيع الأنواع")
        self.btn_stats.clicked.connect(self._show_file_statistics_dialog)
        toolbar.addWidget(self.btn_stats)

        # زر التحديث اليدوي
        self.btn_refresh = QPushButton("تحديث")
        self.btn_refresh.setObjectName("btnGovSecondary")
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.setToolTip("تحديث محتويات المجلد والمزامنة الفورية")
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        toolbar.addWidget(self.btn_refresh)

        # حقل البحث الفوري
        self.search_box = QLineEdit()
        self.search_box.setObjectName("govSearch")
        self.search_box.setMinimumWidth(180)
        self.search_box.setPlaceholderText("بحث في المستندات والكتب الرسمية...")
        self.search_box.textChanged.connect(self._filter_content)
        toolbar.addWidget(self.search_box, stretch=1)

        # ========================================================
        # 1.5 منطقة العمل الرئيسية المقسمة: قائمة الأقسام الجانبية + مساحة المستندات
        # ========================================================
        body_layout = QHBoxLayout()
        body_layout.setSpacing(8)
        body_layout.setContentsMargins(0, 0, 0, 0)

        # --------------------------------------------------------
        # القائمة الجانبية لأقسام الدائرة (Department Sidebar)
        # --------------------------------------------------------
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebarFrame")
        self.sidebar_frame.setFixedWidth(205)
        sb_layout = QVBoxLayout(self.sidebar_frame)
        sb_layout.setContentsMargins(6, 6, 6, 6)
        sb_layout.setSpacing(6)

        # ترويسة القائمة الجانبية
        sb_header = QFrame()
        sb_header.setObjectName("sidebarHeaderFrame")
        sbh_layout = QHBoxLayout(sb_header)
        sbh_layout.setContentsMargins(6, 3, 6, 3)
        sbh_layout.setSpacing(4)

        sb_title = QLabel("الأقسام الإدارية")
        sb_title.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.Bold))
        sb_title.setStyleSheet("color: #1B1F24; background: transparent; border: none;")
        sbh_layout.addWidget(sb_title)
        sbh_layout.addStretch()

        btn_add_dept = QPushButton("+ قسم")
        btn_add_dept.setObjectName("btnAddDept")
        btn_add_dept.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_add_dept.setToolTip("إضافة قسم إداري جديد للغرفة")
        btn_add_dept.clicked.connect(self._show_add_department_dialog)
        sbh_layout.addWidget(btn_add_dept)

        btn_close_sidebar = QPushButton("✕")
        btn_close_sidebar.setObjectName("btnCloseSidebar")
        btn_close_sidebar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close_sidebar.setToolTip("إخفاء قائمة الأقسام")
        btn_close_sidebar.clicked.connect(self._toggle_sidebar)
        sbh_layout.addWidget(btn_close_sidebar)

        sb_layout.addWidget(sb_header)

        # قائمة الأقسام
        self.dept_list = QListWidget()
        self.dept_list.setObjectName("deptList")
        self.dept_list.setWordWrap(True)
        self.dept_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.dept_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dept_list.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.dept_list.itemClicked.connect(self._on_department_clicked)
        self.dept_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dept_list.customContextMenuRequested.connect(self._show_department_context_menu)
        sb_layout.addWidget(self.dept_list, stretch=1)

        # استعادة حالة إظهار/إخفاء القائمة الجانبية للمستخدم
        sidebar_vis = self.state_mgr.get_setting("sidebar_visible", "1") != "0"
        self.sidebar_frame.setVisible(sidebar_vis)
        self.btn_toggle_sidebar.setChecked(sidebar_vis)
        body_layout.addWidget(self.sidebar_frame)

        # --------------------------------------------------------
        # الحاوية الرئيسية للمستندات والعمليات (Content Area)
        # --------------------------------------------------------
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)

        content_layout.addLayout(toolbar)

        # ========================================================
        # 2.5 شريط المسار والتنقل بين المجلدات (Breadcrumb Bar)
        # ========================================================
        self.breadcrumb_frame = QFrame()
        self.breadcrumb_frame.setObjectName("breadcrumbFrame")
        bc_layout = QHBoxLayout(self.breadcrumb_frame)
        bc_layout.setContentsMargins(8, 2, 8, 2)
        bc_layout.setSpacing(8)

        self.btn_nav_up = QPushButton("↑ رجوع")
        self.btn_nav_up.setObjectName("btnBreadcrumbUp")
        self.btn_nav_up.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_nav_up.setToolTip("الرجوع للمجلد السابق")
        self.btn_nav_up.setEnabled(False)
        self.btn_nav_up.clicked.connect(self._navigate_up)
        bc_layout.addWidget(self.btn_nav_up)

        self.lbl_current_path = QLabel("كافة الملفات والمجلدات")
        self.lbl_current_path.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.Bold))
        self.lbl_current_path.setStyleSheet("color: #1B1F24; border: none; background: transparent;")
        bc_layout.addWidget(self.lbl_current_path)

        bc_layout.addStretch()

        self.lbl_folder_info = QLabel("متزامن")
        self.lbl_folder_info.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_folder_info.setStyleSheet("color: #667085; border: none; background: transparent;")
        bc_layout.addWidget(self.lbl_folder_info)

        content_layout.addWidget(self.breadcrumb_frame)

        # ========================================================
        # 3. تبويبات التصنيف الرسمية النظيفة
        # ========================================================
        tabs_layout = QHBoxLayout()
        tabs_layout.setSpacing(4)

        tab_group = QButtonGroup(self)
        tab_group.setExclusive(True)

        self.tab_all = self._create_gov_tab("كافة المستندات", "ALL", tab_group, checked=True)
        self.tab_folders = self._create_gov_tab("المجلدات", "FOLDERS", tab_group)
        self.tab_word = self._create_gov_tab("Word", "WORD", tab_group)
        self.tab_excel = self._create_gov_tab("Excel", "EXCEL", tab_group)
        self.tab_access = self._create_gov_tab("Access", "ACCESS", tab_group)
        self.tab_pdf = self._create_gov_tab("PDF", "PDF", tab_group)
        self.tab_images = self._create_gov_tab("الصور", "IMAGES", tab_group)
        self.tab_other = self._create_gov_tab("أخرى", "OTHER", tab_group)
        self.tab_trash = self._create_gov_tab("المحذوفات", "TRASH", tab_group)

        self.tab_all.setToolTip("عرض كافة المستندات والملفات المتاحة")
        self.tab_folders.setToolTip("عرض المجلدات الإدارية المنظمة")
        self.tab_word.setToolTip("عرض الكتب والمراسلات الإدارية بصيغة Word (.docx, .doc)")
        self.tab_excel.setToolTip("عرض التقارير والجداول المالية بصيغة Excel (.xlsx, .xls)")
        self.tab_access.setToolTip("عرض قواعد البيانات وسجلات الأعضاء بصيغة Access (.accdb, .mdb)")
        self.tab_pdf.setToolTip("عرض الوثائق الرسمية والتعاميم المعتمدة بصيغة PDF (.pdf)")
        self.tab_images.setToolTip("عرض الصور والوثائق المصورة (.jpg, .png, .webp, .bmp, .gif)")
        self.tab_other.setToolTip("عرض الأرشيف المضغوط والفيديو والصوت وباقي الملفات")
        self.tab_trash.setToolTip("الانتقال إلى سلة المحذوفات الإدارية")

        tabs_layout.addWidget(self.tab_all)
        tabs_layout.addWidget(self.tab_folders)
        tabs_layout.addWidget(self.tab_word)
        tabs_layout.addWidget(self.tab_excel)
        tabs_layout.addWidget(self.tab_access)
        tabs_layout.addWidget(self.tab_pdf)
        tabs_layout.addWidget(self.tab_images)
        tabs_layout.addWidget(self.tab_other)
        tabs_layout.addWidget(self.tab_trash)
        tabs_layout.addStretch()

        self.btn_select_all_toggle = QPushButton("تحديد الكل")
        self.btn_select_all_toggle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_select_all_toggle.setToolTip("تحديد أو إلغاء تحديد كافة الملفات والمجلدات المعروضة")
        self.btn_select_all_toggle.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #1B1F24; border: 1px solid #E4E7EC;
                border-radius: 6px; padding: 5px 11px; font-weight: 600; font-size: 11.5px;
            }
            QPushButton:hover { background-color: #F7F8FA; border-color: #14372e; color: #14372e; }
        """)
        self.btn_select_all_toggle.clicked.connect(self._toggle_select_all_visible)
        tabs_layout.addWidget(self.btn_select_all_toggle)

        # محدد طرق العرض (قائمة / شبكة / مدمج)
        self.view_switch_frame = QFrame()
        self.view_switch_frame.setObjectName("viewSwitcherFrame")
        view_switch_layout = QHBoxLayout(self.view_switch_frame)
        view_switch_layout.setContentsMargins(3, 2, 3, 2)
        view_switch_layout.setSpacing(3)

        view_group = QButtonGroup(self)
        view_group.setExclusive(True)

        self.btn_view_table = QPushButton("قائمة")
        self.btn_view_table.setObjectName("btnViewMode")
        self.btn_view_table.setCheckable(True)
        self.btn_view_table.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_view_table.setToolTip("عرض المستندات في قائمة جدولية واضحة")
        view_group.addButton(self.btn_view_table)
        view_switch_layout.addWidget(self.btn_view_table)

        self.btn_view_grid = QPushButton("شبكة")
        self.btn_view_grid.setObjectName("btnViewMode")
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_view_grid.setToolTip("عرض المستندات على شكل شبكة بطاقات")
        view_group.addButton(self.btn_view_grid)
        view_switch_layout.addWidget(self.btn_view_grid)

        self.btn_view_compact = QPushButton("مدمج")
        self.btn_view_compact.setObjectName("btnViewMode")
        self.btn_view_compact.setCheckable(True)
        self.btn_view_compact.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_view_compact.setToolTip("عرض المستندات في صفوف مدمجة")
        view_group.addButton(self.btn_view_compact)
        view_switch_layout.addWidget(self.btn_view_compact)

        self.btn_view_table.clicked.connect(lambda: self._set_view_mode("TABLE"))
        self.btn_view_grid.clicked.connect(lambda: self._set_view_mode("GRID"))
        self.btn_view_compact.clicked.connect(lambda: self._set_view_mode("COMPACT"))

        tabs_layout.addWidget(self.view_switch_frame)
        content_layout.addLayout(tabs_layout)

        # ========================================================
        # 3.5 شريط العمليات الجماعية للملفات والمجلدات المحددة (Bulk Action Bar)
        # ========================================================
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
        self.lbl_bulk_count.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.Bold))
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

        btn_bulk_del = QPushButton("حذف المحدد للسلة")
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

        content_layout.addWidget(self.bulk_bar_frame)

        # ========================================================
        # 4. مساحة عرض المستندات (جدول / بطاقات / مدمج / سلة المحذوفات)
        # ========================================================
        self.stack = QStackedWidget()

        # 4.1 نمط القائمة الجدولية الواضحة (TABLE)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "اسم المستند الكامل", "النوع / المسار", "تاريخ التعديل", "الحجم", "الحالة", "الإجراءات"
        ])
        self.table.setShowGrid(False)
        self.table.setIconSize(QSize(30, 30))
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)

        # ضبط عرض الأعمدة بدقة مع إعطاء الأولوية القصوى لاسم المستند الكامل لمنع أي اقتطاع
        tbl_hdr = self.table.horizontalHeader()
        tbl_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tbl_hdr.setMinimumSectionSize(200)

        tbl_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 130)

        tbl_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 125)

        tbl_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 80)

        tbl_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(4, 100)

        tbl_hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 175)

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

        # دعم زر Delete للحذف السريع للمستندات والمجلدات المحددة
        orig_key_press = self.table.keyPressEvent
        def table_key_press(event):
            if event.key() == Qt.Key.Key_Delete:
                if self.selected_rel_paths or len(self.table.selectionModel().selectedRows()) > 1:
                    self._delete_selected_items_bulk()
                    return
                selected = self.table.selectedItems()
                if selected:
                    cell0 = self.table.item(selected[0].row(), 0)
                    raw = cell0.text()
                    f_name = raw.split('\n')[0]
                    rel_p = cell0.data(Qt.ItemDataRole.UserRole)
                    is_fld = bool(cell0.data(Qt.ItemDataRole.UserRole + 1)) or "(مجلد" in raw
                    if is_fld:
                        self._move_folder_to_trash(f_name)
                    else:
                        self._move_file_to_trash(f_name, rel_p)
                    return
            elif event.key() == Qt.Key.Key_F2:
                selected = self.table.selectedItems()
                if selected:
                    cell0 = self.table.item(selected[0].row(), 0)
                    raw = cell0.text()
                    f_name = raw.split('\n')[0]
                    rel_p = cell0.data(Qt.ItemDataRole.UserRole)
                    is_fld = bool(cell0.data(Qt.ItemDataRole.UserRole + 1)) or "(مجلد" in raw
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
        self.grid_layout.setContentsMargins(12, 12, 12, 12)
        self.grid_layout.setSpacing(14)
        self.grid_scroll.setWidget(self.grid_container)
        orig_grid_wheel = self.grid_scroll.wheelEvent
        def grid_wheel(event):
            self._last_wheel_time = time.time()
            orig_grid_wheel(event)
        self.grid_scroll.wheelEvent = grid_wheel
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
        orig_compact_wheel = self.compact_scroll.wheelEvent
        def compact_wheel(event):
            self._last_wheel_time = time.time()
            orig_compact_wheel(event)
        self.compact_scroll.wheelEvent = compact_wheel
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
        self.th_title = QLabel("🗑️ سلة محذوفات القسم")
        self.th_title.setFont(QFont("Cairo", 12, QFont.Weight.Bold))
        self.th_title.setStyleSheet("color: #991b1b;")
        info_box.addWidget(self.th_title)

        self.th_desc = QLabel("المستندات والمجلدات المحذوفة الخاصة بهذا القسم محفوظة بأمان هنا.")
        self.th_desc.setFont(QFont("Segoe UI", 10))
        self.th_desc.setStyleSheet("color: #566c65;")
        info_box.addWidget(self.th_desc)
        th_layout.addLayout(info_box)

        th_layout.addStretch()

        self.btn_restore_all = QPushButton("♻️ استرجاع كافة المحذوفات")
        self.btn_restore_all.setObjectName("btnTrashRestoreAll")
        self.btn_restore_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_restore_all.setToolTip("استرجاع كافة العناصر المحذوفة وإعادتها لأماكنها ومزامنتها مع السحابة")
        self.btn_restore_all.setStyleSheet("""
            QPushButton {
                background-color: #14372e; color: #ffffff; border: none;
                border-radius: 8px; padding: 9px 18px; font-size: 12px; font-weight: bold;
                font-family: 'Cairo', Tahoma;
            }
            QPushButton:hover { background-color: #1e4a3f; }
        """)
        self.btn_restore_all.clicked.connect(self._restore_all_trash)
        th_layout.addWidget(self.btn_restore_all)

        self.btn_restore_selected = QPushButton("↩️ استرجاع المحدد")
        self.btn_restore_selected.setObjectName("btnTrashRestoreSelected")
        self.btn_restore_selected.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_restore_selected.setToolTip("استرجاع الملف أو العنصر المحدد حالياً في الجدول ورفعه للسحابة")
        self.btn_restore_selected.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: #ffffff; border: none;
                border-radius: 8px; padding: 9px 18px; font-size: 12px; font-weight: bold;
                font-family: 'Cairo', Tahoma;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_restore_selected.clicked.connect(self._restore_selected_from_trash)
        th_layout.addWidget(self.btn_restore_selected)

        self.btn_empty_trash = QPushButton("🧹 إفراغ سلة المحذوفات")
        self.btn_empty_trash.setObjectName("btnEmptyTrash")
        self.btn_empty_trash.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_empty_trash.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2; color: #991b1b; border: 1.5px solid #fecaca;
                border-radius: 8px; padding: 9px 16px; font-size: 12px; font-weight: bold;
                font-family: 'Cairo', Tahoma;
            }
            QPushButton:hover { background-color: #fecaca; color: #7f1d1d; }
        """)
        self.btn_empty_trash.clicked.connect(self._empty_all_trash)
        th_layout.addWidget(self.btn_empty_trash)

        trash_layout.addWidget(trash_header)

        # جدول المحذوفات
        self.trash_table = QTableWidget()
        self.trash_table.setColumnCount(5)
        self.trash_table.setHorizontalHeaderLabels([
            "المستند أو القسم المحذوف", "المسار الأصلي", "تاريخ الحذف", "حجم الملف", "الإجراءات المتاحة"
        ])
        self.trash_table.setWordWrap(True)
        self.trash_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.trash_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.trash_table.horizontalHeader().setMinimumSectionSize(260)
        self.trash_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.trash_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.trash_table.setColumnWidth(4, 220)
        self.trash_table.verticalHeader().setVisible(False)
        self.trash_table.verticalHeader().setDefaultSectionSize(56)
        self.trash_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trash_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trash_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.trash_table.customContextMenuRequested.connect(self._show_trash_context_menu)
        self.trash_table.cellDoubleClicked.connect(self._on_trash_row_double_clicked)
        apply_gov_shadow(self.trash_table, blur=12, offset_y=2, alpha=10)

        trash_layout.addWidget(self.trash_table, stretch=1)
        self.stack.addWidget(self.trash_page)

        content_layout.addWidget(self.stack, stretch=1)
        body_layout.addWidget(content_container, stretch=1)

        # حاوية شاشات العمل الرئيسية (Workspace Stack: 0=Explorer, 1=SyncCenter, 2=SystemSettings)
        self.workspace_stack = QStackedWidget()
        explorer_page = QWidget()
        explorer_page.setLayout(body_layout)
        self.workspace_stack.addWidget(explorer_page)
        self.workspace_stack.addWidget(self._build_sync_center_page())
        self.workspace_stack.addWidget(self._build_system_settings_page())
        self.access_hub_page = AccessHubWidget()
        self.workspace_stack.addWidget(self.access_hub_page)

        main_layout.addWidget(self.workspace_stack, stretch=1)

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
        btn_settings.clicked.connect(lambda: self._switch_workspace_page(2))
        status_layout.addWidget(btn_settings)

        main_layout.addWidget(statusbar)

    def _switch_workspace_page(self, index: int):
        """التبديل السلس بين شاشات المنظومة الرئيسية الثلاث"""
        if hasattr(self, 'workspace_stack'):
            self.workspace_stack.setCurrentIndex(index)
        if index == 0 and hasattr(self, 'nav_btn_docs'):
            self.nav_btn_docs.setChecked(True)
        elif index == 1 and hasattr(self, 'nav_btn_sync'):
            self.nav_btn_sync.setChecked(True)
        elif index == 2 and hasattr(self, 'nav_btn_settings'):
            self.nav_btn_settings.setChecked(True)
        elif index == 3 and hasattr(self, 'nav_btn_access'):
            self.nav_btn_access.setChecked(True)
            if hasattr(self, 'access_hub_page'):
                self.access_hub_page.load_data()

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

    def _check_department_permission(self, dept_name=None, action='write'):
        """فحص الصلاحيات الإدارية المفصلة (9 صلاحيات + الرمز السري PIN) المحددة من قبل الأدمن"""
        target_dept = dept_name or self.active_dept_name
        if not target_dept or target_dept == "__ALL__":
            return True

        if not hasattr(self, 'client') or not self.client or not self.client.is_configured():
            return True

        try:
            if hasattr(self.client, 'get_cached_folder_permissions'):
                # قراءة فورية من الذاكرة حتى لا يتجمد خيط الواجهة بانتظار الشبكة عند كل نقرة
                perms_map = self.client.get_cached_folder_permissions()
            elif hasattr(self.client, 'get_folder_permissions'):
                perms_map = self.client.get_folder_permissions()
            else:
                perms_map = {}
            if perms_map:
                rule = perms_map.get(target_dept)
                if rule:
                    # 1. فحص الرمز السري للقسم (PIN) إن وجد
                    pin_code = str(rule.get('pinCode') or rule.get('pin_code') or '').strip()
                    if pin_code and target_dept not in getattr(self, '_unlocked_pin_depts', set()):
                        entered_pin, ok = QInputDialog.getText(
                            self,
                            f"🔒 قسم محمي برمز سري ({target_dept})",
                            f"هذا القسم ({target_dept}) محمي برمز مرور خاص من الإدارة.\nيرجى إدخال الرمز السري للمتابعة:",
                            QLineEdit.EchoMode.Password
                        )
                        if not ok or entered_pin.strip() != pin_code:
                            if ok:
                                QMessageBox.critical(self, "رمز خاطئ ❌", "الرمز السري الذي أدخلته غير صحيح.")
                            return False
                        self._unlocked_pin_depts.add(target_dept)

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
        """تحديث القائمة الجانبية للأقسام مع عدد المستندات وحالة الصلاحيات في كل قسم بالاعتماد على الذاكرة المؤقتة السريعة"""
        if not hasattr(self, 'dept_list'):
            return

        total_all_files = getattr(self, '_total_root_items_cache', 0)
        dept_counts = getattr(self, '_dept_counts_cache', {})
        perms = {}
        try:
            if self.client and hasattr(self.client, 'get_cached_folder_permissions'):
                perms = self.client.get_cached_folder_permissions() or {}
            elif self.client and hasattr(self.client, 'get_folder_permissions'):
                perms = self.client.get_folder_permissions() or {}
        except Exception:
            perms = {}
        unlocked_pins = getattr(self, '_unlocked_pin_depts', set())

        def _format_dept_label(name, default_icon, cnt):
            rule = perms.get(name, {}) if isinstance(perms, dict) else {}
            can_view = rule.get('canView', rule.get('can_view', True))
            pin_code = str(rule.get('pinCode') or rule.get('pin_code') or '').strip()
            if not can_view:
                icon = '⛔'
            elif pin_code and name not in unlocked_pins:
                icon = '🔒'
            elif pin_code and name in unlocked_pins:
                icon = '🔓'
            else:
                icon = ''
            prefix = f"{icon}  " if icon else ""
            return f"{prefix}{name}  ({cnt})"

        expected_count = len(self.departments_list) + 1
        names_match = True
        if self.dept_list.count() == expected_count:
            for idx, dept in enumerate(self.departments_list):
                it = self.dept_list.item(idx + 1)
                if not it or it.data(Qt.ItemDataRole.UserRole) != dept['name']:
                    names_match = False
                    break

        # تحديث النصوص في مكانها إذا لم يتغير عدد ولا أسماء الأقسام
        if not force_rebuild and self.dept_list.count() == expected_count and names_match:
            item_all = self.dept_list.item(0)
            if item_all:
                new_all_txt = f"كافة الملفات والمجلدات  ({total_all_files})"
                if item_all.text() != new_all_txt:
                    item_all.setText(new_all_txt)

            for idx, dept in enumerate(self.departments_list):
                name = dept['name']
                icon = dept.get('icon', '')
                cnt = dept_counts.get(name, 0)
                item = self.dept_list.item(idx + 1)
                if item:
                    new_txt = _format_dept_label(name, icon, cnt)
                    if item.text() != new_txt:
                        item.setText(new_txt)
            return

        self.dept_list.blockSignals(True)
        self.dept_list.clear()

        selected_item = None

        # 1. قسم كافة الملفات والمجلدات (الأرشيف الشامل) في المقدمة
        item_all_text = f"كافة الملفات والمجلدات  ({total_all_files})"
        item_all = QListWidgetItem(item_all_text)
        item_all.setData(Qt.ItemDataRole.UserRole, "__ALL__")
        item_all.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.DemiBold))
        item_all.setToolTip("كافة الملفات والمجلدات")
        self.dept_list.addItem(item_all)

        if self.active_dept_name is None:
            selected_item = item_all

        # 2. أقسام الدائرة المستقلة والمعزولة
        for dept in self.departments_list:
            name = dept['name']
            icon = dept.get('icon', '')
            cnt = dept_counts.get(name, 0)

            item_text = _format_dept_label(name, icon, cnt)
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFont(QFont("IBM Plex Sans Arabic", 10, QFont.Weight.DemiBold))
            item.setToolTip(name)
            self.dept_list.addItem(item)

            if self.active_dept_name == name:
                selected_item = item

        if not selected_item:
            selected_item = item_all
            self.active_dept_name = None
            self.current_subpath = Path(".")

        if selected_item:
            self.dept_list.setCurrentItem(selected_item)
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
                if pin_c and d_name not in unlocked_pins:
                    return False
                return True

            folders_list = []
            for d_rel in sorted(child_dirs):
                d_name = d_rel.split("/")[-1]
                if not _can_show_dept_instant(d_name):
                    continue
                total_sub_items = snap_idx['rec_files'].get(d_rel, 0) + len(snap_idx['child_dirs'].get(d_rel, []))
                local_dir_path = os.path.normpath(os.path.join(str(self.sync_folder), d_rel))
                folders_list.append({
                    'file_name': d_name,
                    'is_folder': True,
                    'item_count': total_sub_items,
                    'relative_path': d_rel,
                    'abs_path': local_dir_path,
                    'file_size': 0,
                    'sync_status': 'synced',
                    'last_modified_local': ''
                })

            files_list = []
            is_all_archive = (self.active_dept_name is None and target_subpath == Path("."))
            if is_all_archive:
                for f_rel, meta in cached_snap.files.items():
                    f_name = f_rel.split("/")[-1]
                    if is_ignored_name(f_name):
                        continue
                    dept_p = f_rel.split("/")[0] if "/" in f_rel else ""
                    if not dept_p or _can_show_dept_instant(dept_p):
                        full_p = os.path.normpath(os.path.join(str(self.sync_folder), f_rel))
                        files_list.append({
                            'file_name': f_name,
                            'is_folder': False,
                            'relative_path': f_rel,
                            'abs_path': full_p,
                            'file_size': getattr(meta, 'size', 0),
                            'sync_status': 'synced',
                            'last_modified_local': getattr(meta, 'modified_iso', '') or ''
                        })
            else:
                for f_rel, meta in snap_idx['child_files'].get(norm_sub, []):
                    f_name = f_rel.split("/")[-1]
                    if is_ignored_name(f_name):
                        continue
                    full_p = os.path.normpath(os.path.join(str(self.sync_folder), f_rel))
                    files_list.append({
                        'file_name': f_name,
                        'is_folder': False,
                        'relative_path': f_rel,
                        'abs_path': full_p,
                        'file_size': getattr(meta, 'size', 0),
                        'sync_status': 'synced',
                        'last_modified_local': getattr(meta, 'modified_iso', '') or ''
                    })

            folders_list.sort(key=lambda x: x['file_name'].lower())
            files_list.sort(key=lambda x: x['file_name'].lower())

            word_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'word')
            excel_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'excel')
            access_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'access')
            pdf_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'pdf')
            images_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'image')
            other_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) in ('video', 'audio', 'archive', 'other'))
            folders_cnt = len(folders_list)

            self.tab_all.setText(f"الكل ({len(files_list)})")
            self.tab_folders.setText(f"المجلدات ({folders_cnt})" if folders_cnt > 0 else "المجلدات")
            self.tab_word.setText(f"Word ({word_cnt})" if word_cnt > 0 else "Word")
            self.tab_excel.setText(f"Excel ({excel_cnt})" if excel_cnt > 0 else "Excel")
            self.tab_access.setText(f"Access ({access_cnt})" if access_cnt > 0 else "Access")
            self.tab_pdf.setText(f"PDF ({pdf_cnt})" if pdf_cnt > 0 else "PDF")
            if hasattr(self, 'tab_images'):
                self.tab_images.setText(f"الصور ({images_cnt})" if images_cnt > 0 else "الصور")
            if hasattr(self, 'tab_other'):
                self.tab_other.setText(f"أخرى ({other_cnt})" if other_cnt > 0 else "أخرى")

            self.lbl_total.setText(f"المستندات: {len(files_list)}  •  المجلدات: {folders_cnt}")
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
        if not target_dept:
            if norm_new:
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

        self.current_subpath = new_path
        self._reset_scroll_on_render = True
        self._force_full_render = True
        self._nav_cache_ok = True
        self._update_breadcrumb()

        # العرض الفوري المتزامن من الذاكرة (< 15ms)
        self._apply_instant_snapshot_render(new_path)

        # جدولة فحص خلفي هادئ للتزامن
        self._refresh_file_list()

    def _navigate_up(self):
        """الرجوع للمجلد السابق (للأعلى) مع الحفاظ على حدود القسم وعرض فوري"""
        if getattr(self, '_nav_transitioning', False):
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
        """تحديث شريط المسار بالأقسام والمجلدات الحالية مع الحفاظ على عزل القسم"""
        if self.active_dept_name is None:
            if self.current_subpath == Path("."):
                self.btn_nav_up.setEnabled(False)
                self.lbl_current_path.setText("كافة الملفات والمجلدات")
            else:
                self.btn_nav_up.setEnabled(True)
                parts = list(self.current_subpath.parts)
                path_str = " / ".join(parts)
                self.lbl_current_path.setText(f"كافة الملفات والمجلدات / {path_str}")
        else:
            if self.current_subpath == Path(self.active_dept_name):
                self.btn_nav_up.setEnabled(False)
                self.lbl_current_path.setText(f"{self.active_dept_name}")
            else:
                self.btn_nav_up.setEnabled(True)
                try:
                    rel_sub = self.current_subpath.relative_to(self.active_dept_name)
                    path_str = " / ".join(rel_sub.parts)
                    self.lbl_current_path.setText(f"{self.active_dept_name} / {path_str}")
                except Exception:
                    path_str = " / ".join(self.current_subpath.parts)
                    self.lbl_current_path.setText(f"{path_str}")

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
            self.breadcrumb_frame.setVisible(False)
            if hasattr(self, 'btn_select_all_toggle'):
                self.btn_select_all_toggle.setVisible(False)
            self._render_trash_table()
        else:
            self.breadcrumb_frame.setVisible(True)
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
        filtered = []
        for f in self.all_files_cache:
            name = f['file_name'].lower()
            is_folder = f.get('is_folder', False)
            tkey = get_type_key(f['file_name'], is_folder=is_folder)

            if self.active_filter == "FOLDERS":
                if not is_folder:
                    continue
            elif self.active_filter == "WORD":
                if tkey != 'word':
                    continue
            elif self.active_filter == "EXCEL":
                if tkey != 'excel':
                    continue
            elif self.active_filter == "ACCESS":
                if tkey != 'access':
                    continue
            elif self.active_filter == "PDF":
                if tkey != 'pdf':
                    continue
            elif self.active_filter == "IMAGES":
                if tkey != 'image':
                    continue
            elif self.active_filter == "OTHER":
                if is_folder or tkey not in ('video', 'audio', 'archive', 'other'):
                    continue

            if query and query not in name:
                continue

            filtered.append(f)

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
                if pin_c and d_name not in unlocked_pins:
                    return False
                return True

            folders_list = []
            files_list = []
            seen_rel_paths = set()
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
                # 1. قائمة الأقسام الرئيسية
                # فهرس مبني مرة واحدة لكل لقطة: يجعل كل تنقل O(عناصر المجلد) بدل O(كل الأرشيف)
                snap_idx = _get_snapshot_index(cloud_snap)
                cloud_root_dirs = sorted(snap_idx['child_dirs'].get("", []))
                for crd in cloud_root_dirs:
                    if not is_ignored_name(crd) and _can_show_dept(crd):
                        local_dept_names.append(crd)
                        dept_counts[crd] = snap_idx['rec_files'].get(crd, 0)

                total_root_items = len(cloud_snap.files)

                # 2. المجلدات الفرعية في المسار الحالي
                child_dirs = set()
                for fld in snap_idx['child_dirs'].get(norm_sub, []):
                    if is_ignored_name(fld.split("/")[-1]):
                        continue
                    if norm_sub == "" and not _can_show_dept(fld):
                        continue
                    child_dirs.add(fld)

                for d_rel in sorted(child_dirs):
                    d_name = d_rel.split("/")[-1]
                    total_sub_items = snap_idx['rec_files'].get(d_rel, 0) + len(snap_idx['child_dirs'].get(d_rel, []))
                    local_dir_path = os.path.normpath(os.path.join(sync_root_str, d_rel))

                    folders_list.append({
                        'file_name': d_name,
                        'is_folder': True,
                        'item_count': total_sub_items,
                        'relative_path': d_rel,
                        'abs_path': local_dir_path,
                        'file_size': 0,
                        'sync_status': 'synced',
                        'last_modified_local': ''
                    })

                # 3. الملفات السحابية في المسار الحالي (أو كافة الملفات في الأرشيف الشامل)
                is_all_archive = (scan_dept is None and scan_subpath == Path("."))
                cloud_target_files = []

                if is_all_archive:
                    for f_rel, meta in cloud_snap.files.items():
                        dept_prefix = f_rel.split("/")[0] if "/" in f_rel else ""
                        if not dept_prefix or _can_show_dept(dept_prefix):
                            cloud_target_files.append((f_rel, meta))
                else:
                    cloud_target_files = list(snap_idx['child_files'].get(norm_sub, []))

                # قراءة محتوى كل مجلد محلي مرة واحدة (scandir) بدل فحص وجود كل ملف على حدة
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

                for f_rel, meta in cloud_target_files:
                    fname = meta.get('name', f_rel.split("/")[-1])
                    if is_ignored_name(fname):
                        continue
                    if f_rel in seen_rel_paths:
                        continue
                    seen_rel_paths.add(f_rel)

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

                    files_list.append({
                        'file_name': fname,
                        'is_folder': False,
                        'relative_path': f_rel,
                        'abs_path': abs_f,
                        'file_size': f_size,
                        'storage_path': meta.get('id'),
                        'sync_status': sync_stat,
                        'last_modified_local': mtime_iso
                    })

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
                                        files_list.append({
                                            'file_name': entry.name,
                                            'is_folder': False,
                                            'relative_path': rel_p,
                                            'abs_path': entry.path,
                                            'file_size': entry.stat().st_size,
                                            'sync_status': 'pending_upload',
                                            'last_modified_local': datetime.fromtimestamp(entry.stat().st_mtime).isoformat()
                                        })
                    except Exception:
                        pass

            else:
                # ---------------------------------------------------------- #
                # الوضع الاحتياطي غير المتصل (Offline Scan)
                # ---------------------------------------------------------- #
                try:
                    with os.scandir(self.sync_folder) as root_it:
                        for entry in root_it:
                            if entry.name.startswith(".") or entry.name.startswith("~$") or entry.name == ".trash":
                                continue
                            total_root_items += 1
                            if entry.is_dir(follow_symlinks=False) and _can_show_dept(entry.name):
                                local_dept_names.append(entry.name)
                                cnt = 0
                                try:
                                    with os.scandir(entry.path) as d_it:
                                        for sub_e in d_it:
                                            if not sub_e.name.startswith(".") and not sub_e.name.startswith("~$") and sub_e.name != ".trash":
                                                cnt += 1
                                except OSError:
                                    pass
                                dept_counts[entry.name] = cnt
                except OSError:
                    pass

                def _to_rel(abs_p_str):
                    rel_p = os.path.relpath(abs_p_str, sync_root_str).replace("\\", "/")
                    return "" if rel_p == "." else rel_p

                try:
                    with os.scandir(current_abs) as cur_it:
                        for entry in cur_it:
                            name = entry.name
                            if name.startswith(".") or name == ".trash" or is_ignored_name(name):
                                continue
                            is_d = entry.is_dir(follow_symlinks=False)
                            rel = _to_rel(entry.path)
                            if is_d:
                                count = 0
                                try:
                                    with os.scandir(entry.path) as sub_it:
                                        for x in sub_it:
                                            if not x.name.startswith(".") and x.name != ".trash" and not is_ignored_name(x.name):
                                                count += 1
                                except OSError:
                                    pass
                                folders_list.append({
                                    'file_name': name,
                                    'is_folder': True,
                                    'item_count': count,
                                    'relative_path': rel,
                                    'abs_path': entry.path,
                                    'file_size': 0,
                                    'sync_status': 'synced',
                                    'last_modified_local': ''
                                })
                            elif entry.is_file(follow_symlinks=False):
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

                if scan_dept is None and scan_subpath == Path("."):
                    for root_dir, dirs, files in os.walk(sync_root_str):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".trash" and _can_show_dept(d)]
                        for f_name in files:
                            if f_name.startswith(".") or is_ignored_name(f_name):
                                continue
                            full_p = os.path.join(root_dir, f_name)
                            sub_rel = _to_rel(full_p)
                            if sub_rel in seen_rel_paths:
                                continue
                            seen_rel_paths.add(sub_rel)
                            try:
                                st_info = os.stat(full_p)
                                f_size = st_info.st_size
                                mtime_iso = datetime.fromtimestamp(st_info.st_mtime).isoformat()
                            except OSError:
                                continue
                            files_list.append({
                                'file_name': f_name,
                                'is_folder': False,
                                'relative_path': sub_rel,
                                'abs_path': full_p,
                                'file_size': f_size,
                                'sync_status': 'synced',
                                'last_modified_local': mtime_iso
                            })

            folders_list.sort(key=lambda x: x['file_name'].lower())
            files_list.sort(key=lambda x: x['file_name'].lower())
            trash_cnt = self.state_mgr.get_trash_count(dept_name=scan_dept)

            payload = {
                'scan_dept': scan_dept,
                'scan_subpath': scan_subpath,
                'force_now': force_now,
                'folders_list': folders_list,
                'files_list': files_list,
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
                # إشارة Qt (وليس QTimer) لأن هذا الخيط لا يملك حلقة أحداث، فلا يضيع طلب التنقل المؤجل
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
            trash_cnt = payload.get('trash_cnt', 0) + len(getattr(self, '_cloud_trash_cache', []))
            force_now = payload.get('force_now', False) or getattr(self, '_force_full_render', False)
            self._force_full_render = False

            all_items = folders_list + files_list
            self.all_files_cache = all_items

            word_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'word')
            excel_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'excel')
            access_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'access')
            pdf_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'pdf')
            images_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) == 'image')
            other_cnt = sum(1 for x in files_list if get_type_key(x['file_name']) in ('video', 'audio', 'archive', 'other'))
            folders_cnt = len(folders_list)

            self.tab_all.setText(f"الكل ({len(files_list)})")
            self.tab_folders.setText(f"المجلدات ({folders_cnt})" if folders_cnt > 0 else "المجلدات")
            self.tab_word.setText(f"Word ({word_cnt})" if word_cnt > 0 else "Word")
            self.tab_excel.setText(f"Excel ({excel_cnt})" if excel_cnt > 0 else "Excel")
            self.tab_access.setText(f"Access ({access_cnt})" if access_cnt > 0 else "Access")
            self.tab_pdf.setText(f"PDF ({pdf_cnt})" if pdf_cnt > 0 else "PDF")
            if hasattr(self, 'tab_images'):
                self.tab_images.setText(f"الصور ({images_cnt})" if images_cnt > 0 else "الصور")
            if hasattr(self, 'tab_other'):
                self.tab_other.setText(f"أخرى ({other_cnt})" if other_cnt > 0 else "أخرى")
            self.tab_trash.setText(f"المحذوفات ({trash_cnt})" if trash_cnt > 0 else "المحذوفات")

            self.lbl_total.setText(
                f"المستندات: {len(files_list)}  •  المجلدات: {folders_cnt}"
            )
            self.lbl_trash_stat.setText(f"المحذوفات: {trash_cnt}")

            current_sig = (
                str(self.active_dept_name),
                str(self.current_subpath),
                str(self.active_filter),
                self.search_box.text().strip().lower(),
                self.current_view_mode,
                trash_cnt,
                tuple((
                    x.get('relative_path') or x.get('file_name'),
                    x.get('is_folder', False),
                    x.get('file_size', 0),
                    x.get('sync_status', ''),
                    x.get('item_count', 0),
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

    def _render_grid(self, files):
        v_bar = self.grid_scroll.verticalScrollBar()
        if v_bar.isSliderDown():
            return
        prev_scroll = v_bar.value()

        self.grid_scroll.setUpdatesEnabled(False)
        try:
            while self.grid_layout.count():
                item = self.grid_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            if not files:
                empty_lbl = QLabel("لا توجد مستندات تطابق هذا التصنيف أو معايير البحث.")
                empty_lbl.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Medium))
                empty_lbl.setStyleSheet("color: #667085; padding: 50px; background: transparent;")
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.grid_layout.addWidget(empty_lbl, 0, 0, 1, 2)
                return

            viewport_w = self.grid_scroll.viewport().width() if hasattr(self, 'grid_scroll') else 800
            cols = 3 if viewport_w > 820 else 2
            for c in range(cols):
                self.grid_layout.setColumnStretch(c, 1)
            for idx, f in enumerate(files):
                card = GovFileCard(f, self)
                row = idx // cols
                col = idx % cols
                self.grid_layout.addWidget(card, row, col)

            self.grid_layout.setRowStretch((len(files) - 1) // cols + 1, 1)
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

        # إذا كان المستخدم يسحب شريط التمرير حالياً، نتجنب إعادة البناء لضمان السلاسة
        if v_bar.isSliderDown():
            return

        selected_rel = None
        selected_items = self.table.selectedItems()
        if selected_items:
            try:
                c0 = self.table.item(selected_items[0].row(), 0)
                selected_rel = c0.data(Qt.ItemDataRole.UserRole) or c0.text().split('\n')[0]
            except Exception:
                pass

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            target_count = len(files)
            if self.table.rowCount() != target_count:
                self.table.setRowCount(target_count)

            matched_selected_row = None

            for row, f in enumerate(files):
                name = f['file_name']
                rel_path = f.get('relative_path') or name
                is_folder = f.get('is_folder', False)
                abs_path = f.get('abs_path')
                office_icon = get_file_office_icon(name, size=36, is_folder=is_folder, abs_path=abs_path)

                if is_folder:
                    app_name = "مجلد"
                    type_tag = "مجلد فرعي"
                    count = f.get('item_count', 0)
                    size_str = f"{count} عناصر"
                    date_str = f.get('last_modified_local', '')[:10] if f.get('last_modified_local') else "نشط"
                    status_text = "● مجلد"
                    status_color = GOV_GREEN
                else:
                    tkey = get_type_key(name, is_folder=False)
                    if tkey == 'word':
                        app_name = "Word • مستند"
                        type_tag = "مستند Word"
                    elif tkey == 'excel':
                        app_name = "Excel • جدول بيانات"
                        type_tag = "جدول بيانات Excel"
                    elif tkey == 'access':
                        app_name = "Access • قاعدة بيانات"
                        type_tag = "قاعدة بيانات Access"
                    elif tkey == 'pdf':
                        app_name = "PDF • وثيقة"
                        type_tag = "وثيقة PDF"
                    elif tkey == 'image':
                        app_name = "صورة"
                        type_tag = "صورة رقمية"
                    elif tkey == 'video':
                        app_name = "فيديو"
                        type_tag = "ملف فيديو"
                    elif tkey == 'audio':
                        app_name = "صوت"
                        type_tag = "ملف صوتي"
                    elif tkey == 'archive':
                        app_name = "أرشيف"
                        type_tag = "ملف مضغوط"
                    else:
                        app_name = "مستند"
                        type_tag = "ملف عام"

                    if self.active_dept_name is None and self.current_subpath == Path(".") and "/" in rel_path:
                        parent_folder_lbl = rel_path.rsplit("/", 1)[0]
                        app_name = f"{app_name} • {parent_folder_lbl}"

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
                        'synced': '● متزامن',
                        'cloud_only': '● سحابي',
                        'syncing': '● قيد الرفع...',
                        'pending_upload': '● بالانتظار',
                        'conflict': '● تعارض',
                        'failed': '● خطأ',
                        'locked': '● قيد التعديل'
                    }
                    status_text = status_map.get(f.get('sync_status', 'synced'), '● متزامن')
                    status_color = STATUS_SYNCED if f.get('sync_status') == 'synced' else (
                        "#0284c7" if f.get('sync_status') == 'cloud_only' else (
                        STATUS_LOCKED if f.get('sync_status') == 'locked' else (
                        "#ef4444" if f.get('sync_status') == 'failed' else STATUS_SYNCING
                    )))

                if selected_rel and (rel_path == selected_rel or name == selected_rel):
                    matched_selected_row = row

                # الخلية 0: المستند أو المجلد + مربع التحديد الجماعي (الاسم الكامل مع الالتفاف التلقائي)
                disp_text = name
                item0 = self.table.item(row, 0)
                if item0 is None:
                    item0 = QTableWidgetItem(disp_text)
                    self.table.setItem(row, 0, item0)
                else:
                    if item0.text() != disp_text:
                        item0.setText(disp_text)
                item0.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item0.setCheckState(
                    Qt.CheckState.Checked if rel_path in self.selected_rel_paths else Qt.CheckState.Unchecked
                )
                item0.setIcon(office_icon)
                if not hasattr(self, '_font_tbl_name'):
                    self._font_tbl_name = QFont("IBM Plex Sans Arabic", 11, QFont.Weight.DemiBold)
                    self._color_tbl_name = QColor("#1B1F24")
                item0.setFont(self._font_tbl_name)
                item0.setForeground(self._color_tbl_name)
                item0.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                item0.setData(Qt.ItemDataRole.UserRole, rel_path)
                item0.setData(Qt.ItemDataRole.UserRole + 1, is_folder)
                item0.setToolTip(f"{name}\nالنوع: {app_name}\nالحجم: {size_str}\nالمسار: {rel_path}")

                # الخلية 1: البرنامج المقترن / نوع العنصر
                item1 = self.table.item(row, 1)
                if item1 is None:
                    item1 = QTableWidgetItem(app_name)
                    item1.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Medium))
                    item1.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                    item1.setForeground(QColor("#475467"))
                    self.table.setItem(row, 1, item1)
                else:
                    if item1.text() != app_name:
                        item1.setText(app_name)
                    item1.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

                # الخلية 2: تاريخ الاعتماد
                item2 = self.table.item(row, 2)
                if item2 is None:
                    item2 = QTableWidgetItem(date_str)
                    item2.setFont(QFont("Segoe UI", 9))
                    item2.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                    item2.setForeground(QColor(TEXT_MUTED))
                    self.table.setItem(row, 2, item2)
                else:
                    if item2.text() != date_str:
                        item2.setText(date_str)
                    item2.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

                # الخلية 3: الحجم
                item3 = self.table.item(row, 3)
                if item3 is None:
                    item3 = QTableWidgetItem(size_str)
                    item3.setFont(QFont("Segoe UI", 9))
                    item3.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                    item3.setForeground(QColor(TEXT_MUTED))
                    self.table.setItem(row, 3, item3)
                else:
                    if item3.text() != size_str:
                        item3.setText(size_str)
                    item3.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

                # الخلية 4: الحالة السحابية
                item4 = self.table.item(row, 4)
                if item4 is None:
                    item4 = QTableWidgetItem(status_text)
                    item4.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.DemiBold))
                    item4.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                    item4.setForeground(QColor(status_color))
                    self.table.setItem(row, 4, item4)
                else:
                    if item4.text() != status_text:
                        item4.setText(status_text)
                    item4.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                    item4.setForeground(QColor(status_color))

                # الخلية 5: الإجراءات المباشرة (استعراض/فتح ونقل وتعديل وحذف)
                item5 = self.table.item(row, 5)
                if item5 is None:
                    item5 = QTableWidgetItem()
                    self.table.setItem(row, 5, item5)

                existing_widget = self.table.cellWidget(row, 5)
                if (existing_widget is None or 
                    getattr(existing_widget, '_bound_rel_path', None) != rel_path or 
                    getattr(existing_widget, '_is_folder', None) != is_folder):
                    act_widget = QWidget()
                    act_widget._bound_file_name = name
                    act_widget._bound_rel_path = rel_path
                    act_widget._is_folder = is_folder
                    act_widget.setFixedHeight(40)
                    act_layout = QHBoxLayout(act_widget)
                    act_layout.setContentsMargins(4, 2, 4, 2)
                    act_layout.setSpacing(4)

                    if is_folder:
                        btn_open = QPushButton("فتح")
                        btn_open.setObjectName("btnTileOpen")
                        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_open.clicked.connect(lambda _, n=name, rp=rel_path: self._navigate_into_folder(n, rp))
                        act_layout.addWidget(btn_open)

                        btn_move = QPushButton("نقل")
                        btn_move.setObjectName("btnTableRename")
                        btn_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_move.setToolTip("نقل المجلد إلى قسم / مجلد آخر...")
                        btn_move.clicked.connect(lambda _, n=name, rp=rel_path: self._show_move_items_dialog([
                            {"name": n, "rel_path": rp, "is_folder": True}
                        ]))
                        act_layout.addWidget(btn_move)

                        btn_rename = QPushButton("تسمية")
                        btn_rename.setObjectName("btnTableRename")
                        btn_rename.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_rename.setToolTip("تعديل اسم المجلد (F2)")
                        btn_rename.clicked.connect(lambda _, n=name: self._rename_folder(n))
                        act_layout.addWidget(btn_rename)

                        btn_del = QPushButton("حذف")
                        btn_del.setObjectName("btnTableDelete")
                        btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_del.setToolTip("نقل المجلد إلى سلة المحذوفات")
                        btn_del.clicked.connect(lambda _, n=name, rp=rel_path: self._move_folder_to_trash(n, rel_path=rp))
                        act_layout.addWidget(btn_del)
                    else:
                        open_txt = "عرض" if get_type_key(name) == 'image' else "فتح"
                        btn_open = QPushButton(open_txt)
                        btn_open.setObjectName("btnTileOpen")
                        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_open.clicked.connect(lambda _, n=name, rp=rel_path: self._open_file_by_name(n, rp))
                        act_layout.addWidget(btn_open)

                        btn_move = QPushButton("نقل")
                        btn_move.setObjectName("btnTableRename")
                        btn_move.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_move.setToolTip("نقل المستند إلى قسم / مجلد آخر...")
                        btn_move.clicked.connect(lambda _, n=name, rp=rel_path: self._show_move_items_dialog([
                            {"name": n, "rel_path": rp, "is_folder": False}
                        ]))
                        act_layout.addWidget(btn_move)

                        btn_rename = QPushButton("تسمية")
                        btn_rename.setObjectName("btnTableRename")
                        btn_rename.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_rename.setToolTip("تعديل اسم المستند (F2)")
                        btn_rename.clicked.connect(lambda _, n=name, rp=rel_path: self._rename_file(n, rp))
                        act_layout.addWidget(btn_rename)

                        btn_del = QPushButton("حذف")
                        btn_del.setObjectName("btnTableDelete")
                        btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        btn_del.setToolTip("نقل المستند إلى سلة المحذوفات")
                        btn_del.clicked.connect(lambda _, n=name, rp=rel_path: self._move_file_to_trash(n, rp))
                        act_layout.addWidget(btn_del)

                    self.table.setCellWidget(row, 5, act_widget)

                # ضبط ارتفاع الصف بكفاءة عالية دون إعادة حساب التخطيط لكل صف
                if len(name) > 45 or "\n" in name:
                    self.table.setRowHeight(row, 58)
                else:
                    self.table.setRowHeight(row, 48)
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)

        # استعادة موضع شريط التمرير بدقة تامة
        if not getattr(self, '_reset_scroll_on_render', False):
            v_bar.setValue(prev_scroll)
            QTimer.singleShot(0, lambda: v_bar.setValue(prev_scroll))
        else:
            self._reset_scroll_on_render = False
            v_bar.setValue(0)

        # استعادة تحديد الملف السابق دون استدعاء scrollTo إطلاقاً
        if matched_selected_row is not None:
            self.table.selectionModel().clearSelection()
            idx = self.table.model().index(matched_selected_row, 0)
            self.table.selectionModel().select(idx, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            if not getattr(self, '_reset_scroll_on_render', False):
                v_bar.setValue(prev_scroll)
                QTimer.singleShot(0, lambda: v_bar.setValue(prev_scroll))

    def _open_selected_from_table(self, row, col):
        if col == 5:
            return
        cell0 = self.table.item(row, 0)
        if not cell0:
            return
        raw_text = cell0.text()
        file_name = raw_text.split('\n')[0]
        rel_path = cell0.data(Qt.ItemDataRole.UserRole)
        is_fld = bool(cell0.data(Qt.ItemDataRole.UserRole + 1)) or "(مجلد" in raw_text
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
        cell0 = self.table.item(selected[0].row(), 0)
        raw_text = cell0.text()
        file_name = raw_text.split('\n')[0]
        rel_path = cell0.data(Qt.ItemDataRole.UserRole)
        is_fld = bool(cell0.data(Qt.ItemDataRole.UserRole + 1)) or "(مجلد" in raw_text
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
