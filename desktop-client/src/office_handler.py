"""
تبادل الملفات – File Exchange System
التكامل مع برامج Microsoft Office والتعامل الآمن مع ملفات Access
"""
import os
import sys
import subprocess
from pathlib import Path

class OfficeHandler:
    @staticmethod
    def is_file_locked_by_os(filepath):
        """
        التحقق من أن برنامج Word أو Excel انتهى من كتابة الملف وحرر قفل النظام (File Handle)
        """
        if not os.path.exists(filepath):
            return True
        try:
            with open(filepath, 'r+b') as f:
                pass
            return False
        except (IOError, PermissionError):
            return True

    @staticmethod
    def is_access_db(filepath):
        """التحقق مما إذا كان الملف هو قاعدة بيانات Microsoft Access"""
        suffix = Path(filepath).suffix.lower()
        return suffix in ['.accdb', '.mdb']

    @staticmethod
    def get_access_lock_file(filepath):
        """إرجاع مسار ملف قفل أكسس الافتراضي (.laccdb أو .ldb)"""
        path = Path(filepath)
        if path.suffix.lower() == '.accdb':
            return path.parent / f"{path.stem}.laccdb"
        elif path.suffix.lower() == '.mdb':
            return path.parent / f"{path.stem}.ldb"
        return None

    @staticmethod
    def is_access_file_open_locally(filepath):
        """التحقق مما إذا كان ملف Access مفتوحاً محلياً عبر وجود ملف .laccdb"""
        lock_file = OfficeHandler.get_access_lock_file(filepath)
        if lock_file and lock_file.exists():
            return True
        return OfficeHandler.is_file_locked_by_os(filepath)

    @staticmethod
    def cleanup_orphaned_office_locks(filepath):
        """
        تنظيف ملفات القفل المؤقتة العالقة (Orphaned Lock Files مثل ~$filename.docx)
        التي قد تتبقى عند إغلاق البرنامج بشكل غير طبيعي وتمنع التحرير مسببة رسالة "الملف مؤمن للتحرير"
        """
        try:
            path = Path(filepath).resolve()
            parent = path.parent

            # فحص ملفات القفل الخاصة ببرامج Office
            for lock in parent.glob("~$*"):
                if lock.exists():
                    # إذا كان الملف الأصلي غير مقفول فعلياً بنظام التشغيل، فالقفل عالق ويجب حذفه
                    if not OfficeHandler.is_file_locked_by_os(str(path)):
                        try:
                            lock.unlink(missing_ok=True)
                        except Exception:
                            pass
        except Exception:
            pass

    @staticmethod
    def get_office_executable(suffix):
        """البحث عن المسار المباشر لبرامج Office (Word, Excel, Access) في النظام لتشغيلها مباشرة بأقصى سرعة"""
        suffix = suffix.lower()
        app_key = None
        if suffix in ['.docx', '.doc', '.rtf', '.odt']:
            app_key = 'winword.exe'
        elif suffix in ['.xlsx', '.xls', '.csv', '.ods']:
            app_key = 'excel.exe'
        elif suffix in ['.accdb', '.mdb']:
            app_key = 'msaccess.exe'

        if not app_key or sys.platform != 'win32':
            return None

        # 1. فحص سجل ويندوز (Registry App Paths)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_key}") as key:
                val, _ = winreg.QueryValueEx(key, "")
                if val and os.path.exists(val):
                    return val
        except Exception:
            pass

        # 2. فحص مسارات التثبيت الشائعة لـ Office (Click-to-Run و Program Files)
        common_candidates = [
            rf"C:\Program Files\Microsoft Office\Root\Office16\{app_key.upper()}",
            rf"C:\Program Files (x86)\Microsoft Office\Root\Office16\{app_key.upper()}",
            rf"C:\Program Files\Microsoft Office\Office16\{app_key.upper()}",
            rf"C:\Program Files (x86)\Microsoft Office\Office16\{app_key.upper()}",
            rf"C:\Program Files\Microsoft Office\Root\Office15\{app_key.upper()}",
            rf"C:\Program Files (x86)\Microsoft Office\Root\Office15\{app_key.upper()}",
        ]
        for cand in common_candidates:
            if os.path.exists(cand):
                return cand

        return None

    @staticmethod
    def _bring_window_to_front(filepath, synchronous=False):
        """
        إحضار نافذة البرنامج المفتوح (Word, Excel, Access) فورياً إلى الواجهة مباشرة أمام المستخدم
        (Foreground Focus) ومنع بقائها مصغرة أو وميضها في شريط المهام بالأسفل فقط.
        """
        def _activate_loop():
            import time
            from pathlib import Path
            p = Path(filepath)
            ext = p.suffix.lower()
            stem = p.stem.lower()

            target_classes = []
            app_names = []
            if ext in ['.docx', '.doc', '.rtf', '.odt']:
                target_classes.append('OpusApp')
                app_names.extend(['Word', 'Microsoft Word', 'WINWORD'])
            elif ext in ['.xlsx', '.xls', '.csv', '.ods']:
                target_classes.append('XLMAIN')
                app_names.extend(['Excel', 'Microsoft Excel'])
            elif ext in ['.accdb', '.mdb']:
                target_classes.append('OMain')
                app_names.extend(['Access', 'Microsoft Access'])

            if sys.platform != 'win32':
                return

            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # رفع قيود ويندوز فوراً
            try:
                user32.LockSetForegroundWindow(2)   # LSFW_UNLOCK
                user32.AllowSetForegroundWindow(-1) # ASFW_ANY
            except Exception:
                pass

            # محاولة متكررة حتى 3.5 ثوانٍ لالتقاط نافذة البرنامج فور فتحها
            found_hwnd = None
            for _ in range(35):
                time.sleep(0.1)

                # 1. البحث السريع عبر فئة النافذة (Class Name)
                for cname in target_classes:
                    h = user32.FindWindowW(cname, None)
                    if h and user32.IsWindowVisible(h):
                        found_hwnd = h
                        break
                if found_hwnd:
                    break

                # 2. البحث عبر نافذة مطابقة لاسم المستند أو اسم التطبيق
                candidate_hwnds = []
                def _enum_cb(hwnd, _):
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            t = buf.value.lower()
                            if stem in t or any(a.lower() in t for a in app_names):
                                candidate_hwnds.append(hwnd)
                                return 0
                    return 1

                CB = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)(_enum_cb)
                user32.EnumWindows(CB, 0)
                if candidate_hwnds:
                    found_hwnd = candidate_hwnds[0]
                    break

            if found_hwnd:
                # 1. استعادة النافذة وتكبيرها فوراً إذا كانت مصغرة في شريط المهام
                if user32.IsIconic(found_hwnd):
                    user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
                else:
                    user32.ShowWindow(found_hwnd, 3)  # SW_MAXIMIZE

                # 2. كسر قفل منع سرقة التركيز في ويندوز (AttachThreadInput)
                fore_hwnd = user32.GetForegroundWindow()
                fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
                target_thread = user32.GetWindowThreadProcessId(found_hwnd, None)
                curr_thread = kernel32.GetCurrentThreadId()

                if fore_thread != curr_thread and fore_thread != 0:
                    user32.AttachThreadInput(curr_thread, fore_thread, True)
                    user32.AttachThreadInput(curr_thread, target_thread, True)
                    user32.BringWindowToTop(found_hwnd)
                    user32.SetForegroundWindow(found_hwnd)
                    if hasattr(user32, 'SwitchToThisWindow'):
                        user32.SwitchToThisWindow(found_hwnd, True)
                    user32.AttachThreadInput(curr_thread, fore_thread, False)
                    user32.AttachThreadInput(curr_thread, target_thread, False)
                else:
                    user32.BringWindowToTop(found_hwnd)
                    user32.SetForegroundWindow(found_hwnd)
                    if hasattr(user32, 'SwitchToThisWindow'):
                        user32.SwitchToThisWindow(found_hwnd, True)

                # 3. محاكاة مفتاح Alt لنقل التركيز القسري رغماً عن قيود ويندوز
                user32.keybd_event(0x12, 0, 0, 0)
                user32.keybd_event(0x12, 0, 2, 0)
                user32.SetForegroundWindow(found_hwnd)
                user32.BringWindowToTop(found_hwnd)

            # 4. تشغيل WScript.Shell AppActivate في الخلفية كضمانة إضافية للبرامج الشهيرة
            try:
                for app in app_names:
                    subprocess.Popen(
                        ['powershell', '-WindowStyle', 'Hidden', '-Command',
                         f'$ws = New-Object -ComObject WScript.Shell; $ws.AppActivate("{app}")'],
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    )
            except Exception:
                pass

        if synchronous:
            _activate_loop()
        else:
            import threading
            threading.Thread(target=_activate_loop, daemon=True).start()

    @staticmethod
    def open_native_file(filepath, synchronous=False):
        """
        فتح الملف باستخدام البرنامج الافتراضي الأصلي المثبت على جهاز Windows:
        - Word لملفات .docx
        - Excel لملفات .xlsx
        - Access لملفات .accdb
        مع إحضار نافذة البرنامج فورياً إلى الواجهة أمام المستخدم مباشرة.
        """
        path = Path(filepath).resolve()
        if not path.exists():
            raise FileNotFoundError(f"الملف غير موجود في المسار: {path}")

        # تنظيف أي أقفال عالقة لـ Office قبل التشغيل
        OfficeHandler.cleanup_orphaned_office_locks(str(path))

        path_str = str(path)

        if sys.platform == 'win32':
            # التحقق أولاً من وجود المسار المباشر للبرنامج (Word / Excel / Access)
            exe_path = OfficeHandler.get_office_executable(path.suffix)
            if exe_path and os.path.exists(exe_path):
                try:
                    subprocess.Popen([exe_path, path_str])
                    OfficeHandler._bring_window_to_front(path_str, synchronous=synchronous)
                    return True
                except Exception as e_direct:
                    print(f"[OfficeHandler Direct Launch Warning]: {e_direct}")

            # الطريقة الثانية: استدعاء نظام الويندوز المباشر مع تفعيل الظهور المباشر أمام المستخدم
            try:
                os.startfile(path_str)
                OfficeHandler._bring_window_to_front(path_str, synchronous=synchronous)
                return True
            except Exception as e_startfile:
                # الطريقة الثالثة البديلة: استدعاء أمر التشغيل في cmd
                try:
                    subprocess.Popen(f'cmd /c start "" "{path_str}"', shell=True)
                    OfficeHandler._bring_window_to_front(path_str, synchronous=synchronous)
                    return True
                except Exception as e_cmd:
                    # الطريقة الرابعة: عبر powershell Start-Process
                    try:
                        subprocess.Popen(['powershell', '-Command', f'Start-Process -FilePath "{path_str}"'], shell=True)
                        OfficeHandler._bring_window_to_front(path_str, synchronous=synchronous)
                        return True
                    except Exception as e_ps:
                        raise RuntimeError(f"تعذر فتح الملف بالبرنامج الأصلي: {e_startfile} | {e_cmd} | {e_ps}")
        else:
            subprocess.run(['xdg-open', path_str])
            return True
