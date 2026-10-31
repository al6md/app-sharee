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

        # التأكد من إزالة سمة القراءة فقط لضمان فتح الملف في وضع التحرير والحفظ المباشر
        try:
            import stat
            os.chmod(path_str, stat.S_IWRITE | stat.S_IREAD)
            if sys.platform == 'win32':
                import ctypes
                FILE_ATTRIBUTE_READONLY = 0x00000001
                attrs = ctypes.windll.kernel32.GetFileAttributesW(path_str)
                if attrs != -1 and (attrs & FILE_ATTRIBUTE_READONLY):
                    ctypes.windll.kernel32.SetFileAttributesW(path_str, attrs & ~FILE_ATTRIBUTE_READONLY)
        except Exception:
            pass

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
                # الطريقة الثالثة البديلة الآمنة: استدعاء مستكشف ويندوز بدون وسيط الشل (منع حقن الأوامر)
                try:
                    subprocess.Popen(['explorer.exe', path_str], shell=False)
                    OfficeHandler._bring_window_to_front(path_str, synchronous=synchronous)
                    return True
                except Exception as e_exp:
                    try:
                        subprocess.Popen(['cmd.exe', '/c', 'start', '', path_str], shell=False)
                        OfficeHandler._bring_window_to_front(path_str, synchronous=synchronous)
                        return True
                    except Exception as e_cmd:
                        raise RuntimeError(f"تعذر فتح الملف بالبرنامج الأصلي: {e_startfile} | {e_exp} | {e_cmd}")
        else:
            subprocess.run(['xdg-open', path_str])
            return True

    @staticmethod
    def safe_apply_file(dest_path_str, source_new_path_str):
        """
        تطبيق التحديث على الملف الهدف بأقصى سرعة وأمان:
        1. إذا لم يكن مقفولاً بنظام التشغيل: استبدال فوري خلال أقل من 10ms.
        2. إذا كان مفتوحاً في Excel أو Word:
           - محاولة الإنعاش التلقائي المباشر (Auto Hot-Reload) إذا لم يكن فيه تعديلات محلية غير محفوظة.
           - إذا تعذر، حفظه كنسخة ظل مؤقتة مع تبديله فور إغلاق البرنامج تلقائياً.
        """
        import shutil
        import threading
        import time

        dest_p = Path(dest_path_str)
        src_p = Path(source_new_path_str)
        if not src_p.exists():
            return False

        # الحالة 1: الملف غير مقفول (مغلق حالياً)
        if not OfficeHandler.is_file_locked_by_os(str(dest_p)):
            try:
                dest_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_p), str(dest_p))
                return True
            except Exception:
                pass

        # الحالة 2: الملف مقفول محلياً بواسطة Office (Word أو Excel أو Access)
        # أ) حفظ نسخة في مسار الظل فوراً
        shadow_dir = dest_p.parent / ".sync_shadow"
        shadow_dir.mkdir(parents=True, exist_ok=True)
        shadow_file = shadow_dir / dest_p.name
        try:
            shutil.copy2(str(src_p), str(shadow_file))
        except Exception:
            pass

        # ب) محاولة الإنعاش التلقائي عبر PowerShell COM لـ Excel أو Word دون إزعاج الموظف
        suffix = dest_p.suffix.lower()
        if suffix in ('.xlsx', '.xls', '.docx', '.doc') and sys.platform == 'win32':
            app_progid = 'Excel.Application' if suffix in ('.xlsx', '.xls') else 'Word.Application'
            is_excel = suffix in ('.xlsx', '.xls')
            ps_cmd = f"""
            try {{
                $app = [System.Runtime.InteropServices.Marshal]::GetActiveObject('{app_progid}')
                $found = $false
                $docs = if ('{is_excel}' -eq 'True') {{ $app.Workbooks }} else {{ $app.Documents }}
                foreach ($doc in $docs) {{
                    if ($doc.FullName.ToLower() -eq '{str(dest_p).replace('\\', '\\\\').lower()}') {{
                        $found = $true
                        if ($doc.Saved) {{
                            $doc.Close($false)
                            Copy-Item -LiteralPath '{str(shadow_file).replace('\\', '\\\\')}' -Destination '{str(dest_p).replace('\\', '\\\\')}' -Force
                            if ('{is_excel}' -eq 'True') {{ $app.Workbooks.Open('{str(dest_p).replace('\\', '\\\\')}') }} else {{ $app.Documents.Open('{str(dest_p).replace('\\', '\\\\')}') }}
                            exit 0
                        }} else {{
                            exit 2
                        }}
                    }}
                }}
                if (-not $found) {{ exit 1 }}
            }} catch {{
                exit 1
            }}
            """
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    capture_output=True, timeout=2.0,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                if res.returncode == 0:
                    # تم الإنعاش التلقائي بنجاح في نافذة Office أمام الموظف!
                    return True
            except Exception:
                pass

        # ج) مراقبة تحرير القفل في خيط خلفي لتطبيق التحديث فور إغلاقه أو حفظه
        def _wait_and_swap():
            for _ in range(600):  # محاولة كل 0.5 ثانية لمدة 5 دقائق
                time.sleep(0.5)
                if not OfficeHandler.is_file_locked_by_os(str(dest_p)):
                    try:
                        if shadow_file.exists():
                            shutil.copy2(str(shadow_file), str(dest_p))
                            shadow_file.unlink(missing_ok=True)
                            return
                    except Exception:
                        pass
            try:
                if shadow_file.exists():
                    shadow_file.unlink(missing_ok=True)
            except Exception:
                pass

        threading.Thread(target=_wait_and_swap, daemon=True).start()
        return True

