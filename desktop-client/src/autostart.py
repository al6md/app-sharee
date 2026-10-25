"""
تبادل الملفات – File Exchange System
إدارة التشغيل التلقائي مع بدء تشغيل Windows (Auto-start)
"""
import sys
import os

APP_REG_NAME = "FileExchangeSystem"

def set_windows_autostart(enable=True, exe_path=None):
    """
    تفعيل أو تعطيل بدء تشغيل التطبيق تلقائياً مع Windows عبر سجل النظام (Registry)
    """
    if sys.platform != 'win32':
        return False, "هذه الميزة تعمل فقط على نظام Windows"

    try:
        import winreg
        key = winreg.HKEY_CURRENT_USER
        sub_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        with winreg.OpenKey(key, sub_key, 0, winreg.KEY_ALL_ACCESS) as reg_key:
            if enable:
                if exe_path is None:
                    exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
                winreg.SetValueEx(reg_key, APP_REG_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
                return True, "تم تفعيل التشغيل التلقائي مع بدء التشغيل"
            else:
                try:
                    winreg.DeleteValue(reg_key, APP_REG_NAME)
                    return True, "تم تعطيل التشغيل التلقائي"
                except FileNotFoundError:
                    return True, "التشغيل التلقائي معطل بالفعل"
    except Exception as e:
        return False, f"خطأ في تعديل سجل النظام: {str(e)}"

def is_windows_autostart_enabled():
    """التحقق مما إذا كان التطبيق مفعل للتشغيل التلقائي حالياً"""
    if sys.platform != 'win32':
        return False

    try:
        import winreg
        key = winreg.HKEY_CURRENT_USER
        sub_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(key, sub_key, 0, winreg.KEY_READ) as reg_key:
            winreg.QueryValueEx(reg_key, APP_REG_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False
