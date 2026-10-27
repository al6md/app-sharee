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
    def open_native_file(filepath):
        """
        فتح الملف باستخدام البرنامج الافتراضي الأصلي المثبت على جهاز Windows:
        - Word لملفات .docx
        - Excel لملفات .xlsx
        - Access لملفات .accdb
        """
        path = Path(filepath).resolve()
        if not path.exists():
            raise FileNotFoundError(f"الملف غير موجود في المسار: {path}")

        # تنظيف أي أقفال عالقة لـ Office قبل التشغيل
        OfficeHandler.cleanup_orphaned_office_locks(str(path))

        path_str = str(path)

        if sys.platform == 'win32':
            # الطريقة الأولى: استدعاء نظام الويندوز المباشر
            try:
                os.startfile(path_str)
                return True
            except Exception as e_startfile:
                # الطريقة الثانية البديلة: استدعاء أمر التشغيل في cmd
                try:
                    subprocess.Popen(f'cmd /c start "" "{path_str}"', shell=True)
                    return True
                except Exception as e_cmd:
                    # الطريقة الثالثة: عبر powershell Start-Process
                    try:
                        subprocess.Popen(['powershell', '-Command', f'Start-Process -FilePath "{path_str}"'], shell=True)
                        return True
                    except Exception as e_ps:
                        raise RuntimeError(f"تعذر فتح الملف بالبرنامج الأصلي: {e_startfile} | {e_cmd} | {e_ps}")
        else:
            subprocess.run(['xdg-open', path_str])
            return True
