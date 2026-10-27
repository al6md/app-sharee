"""
Share COC Enterprise v4.0 – غرفة تجارة كربلاء المقدسة
وحدة التكامل الرسمي مع نظام التشغيل Windows:
- إنشاء اختصارات سطح المكتب (Desktop) وقائمة ابدأ (Start Menu) وقائمة إرسال إلى (Send To)
- تسجيل البرنامج رسمياً في "البرامج والميزات / التطبيقات المثبتة" (Windows Uninstall Registry)
- تسجيل بروتوكول المتصفح (sharecoc://)
- إدارة التشغيل التلقائي عند إقلاع النظام (Windows Startup)
"""
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

APP_ID = "ShareCOC"
APP_DISPLAY_NAME = "Share COC – منظومة التبادل السحابي (غرفة تجارة كربلاء المقدسة)"
APP_SHORT_NAME = "Share COC"
APP_VERSION = "4.0.0"
APP_PUBLISHER = "غرفة تجارة كربلاء المقدسة – قسم تقنية المعلومات"
APP_EXE_NAME = "share coc.exe"
UNINSTALL_EXE_NAME = "Uninstall_ShareCOC.exe"


def get_default_install_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local_appdata) / "Programs" / "ShareCOC"


def get_default_sync_dir() -> Path:
    user_profile = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(user_profile) / "FileExchangeShared"


def create_windows_shortcut(shortcut_path: Path, target_path: Path, arguments: str = "",
                            working_dir: Path = None, icon_path: Path = None, description: str = "") -> bool:
    """إنشاء اختصار ويندوز رسمي (.lnk) عبر WScript.Shell بدون نافذة طرفية"""
    try:
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = str(working_dir or target_path.parent)
        ico = str(icon_path) if (icon_path and icon_path.exists()) else str(target_path)

        def _esc(val: str) -> str:
            return str(val).replace("'", "''")

        ps_cmd = f"""
$wsh = New-Object -ComObject WScript.Shell
$s = $wsh.CreateShortcut('{_esc(str(shortcut_path))}')
$s.TargetPath = '{_esc(str(target_path))}'
$s.Arguments = '{_esc(arguments)}'
$s.WorkingDirectory = '{_esc(work_dir)}'
$s.Description = '{_esc(description or APP_DISPLAY_NAME)}'
$s.IconLocation = '{_esc(ico)},0'
$s.Save()
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            capture_output=True,
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return shortcut_path.exists()
    except Exception as e:
        print(f"[WindowsIntegration] Shortcut error ({shortcut_path}): {e}")
        return False


def get_desktop_dirs() -> list[Path]:
    """إرجاع مسارات سطح المكتب الفعلية (بما فيها OneDrive Desktop إن وجد)"""
    user_profile = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    candidates = [
        user_profile / "OneDrive" / "Desktop",
        user_profile / "Desktop",
    ]
    existing = [p for p in candidates if p.exists()]
    return existing if existing else [candidates[-1]]


def get_start_menu_folder() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "غرفة تجارة كربلاء المقدسة"


def get_sendto_folder() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "SendTo"


def register_protocol_handler(exe_path: Path, icon_path: Path = None) -> bool:
    """تسجيل بروتوكول sharecoc:// في سجل ويندوز لفتح الملفات من المتصفح مباشرة"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        ico = str(icon_path) if (icon_path and icon_path.exists()) else str(exe_path)
        key_path = r"Software\Classes\sharecoc"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Share COC Protocol")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\DefaultIcon") as k_ico:
            winreg.SetValueEx(k_ico, "", 0, winreg.REG_SZ, f'"{ico}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\shell\\open\\command") as k_cmd:
            winreg.SetValueEx(k_cmd, "", 0, winreg.REG_SZ, f'"{exe_path}" --open "%1"')
        return True
    except Exception as e:
        print(f"[WindowsIntegration] Protocol registration error: {e}")
        return False


def register_uninstaller_in_windows(install_dir: Path, exe_path: Path, uninstaller_path: Path,
                                    icon_path: Path = None) -> bool:
    """
    تسجيل البرنامج رسمياً في قائمة البرامج المثبتة في ويندوز (Add or Remove Programs / Installed Apps)
    عبر المفتاح القياسي HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ShareCOC
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        ico = str(icon_path) if (icon_path and icon_path.exists()) else str(exe_path)
        uninstall_key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"

        # حساب حجم التثبيت بالكيلوبايت لعرضه في إعدادات ويندوز
        total_bytes = 0
        try:
            for f in install_dir.rglob("*"):
                if f.is_file():
                    total_bytes += f.stat().st_size
        except Exception:
            total_bytes = 80 * 1024 * 1024
        estimated_size_kb = max(1024, int(total_bytes // 1024))

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, uninstall_key_path) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, f'"{ico}",0')
            winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
            winreg.SetValueEx(k, "InstallDate", 0, winreg.REG_SZ, datetime.now().strftime("%Y%m%d"))
            winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}" --uninstall')
            winreg.SetValueEx(k, "QuietUninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}" --uninstall --quiet')
            winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, estimated_size_kb)
            winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        return True
    except Exception as e:
        print(f"[WindowsIntegration] Uninstall registry error: {e}")
        return False


def unregister_from_windows() -> bool:
    """إزالة تسجيل البرنامج من قائمة البرامج المثبتة والتشغيل التلقائي عند إلغاء التثبيت"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        for sub_key in [
            rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}",
            r"Software\Classes\sharecoc\shell\open\command",
            r"Software\Classes\sharecoc\shell\open",
            r"Software\Classes\sharecoc\shell",
            r"Software\Classes\sharecoc\DefaultIcon",
            r"Software\Classes\sharecoc",
        ]:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub_key)
            except FileNotFoundError:
                pass
            except Exception:
                pass

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_ALL_ACCESS) as rk:
                for val_name in ("FileExchangeSystem", "ShareCOC"):
                    try:
                        winreg.DeleteValue(rk, val_name)
                    except FileNotFoundError:
                        pass
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[WindowsIntegration] Unregister error: {e}")
        return False


def setup_all_system_integrations(
    exe_path: Path,
    sync_dir: Path = None,
    icon_path: Path = None,
    create_desktop: bool = True,
    create_start_menu: bool = True,
    create_sendto: bool = True,
    enable_autostart: bool = True,
    register_uninstaller: bool = True,
    uninstaller_path: Path = None,
) -> dict:
    """تنفيذ كافة خطوات التكامل الرسمي مع نظام Windows وإرجاع تقرير بالحالة"""
    results = {}
    sync_folder = sync_dir or get_default_sync_dir()
    sync_folder.mkdir(parents=True, exist_ok=True)
    ico = icon_path if (icon_path and icon_path.exists()) else (exe_path.parent / "logo.ico")
    if not ico.exists():
        ico = exe_path

    # 1. اختصار سطح المكتب
    if create_desktop:
        desktop_ok = False
        for d_dir in get_desktop_dirs():
            lnk = d_dir / "Share COC – غرفة تجارة كربلاء.lnk"
            if create_windows_shortcut(
                lnk, exe_path, working_dir=exe_path.parent, icon_path=ico,
                description=APP_DISPLAY_NAME
            ):
                desktop_ok = True
            # تحديث الاختصار القديم إن وجد ليشير للنسخة المثبتة الرسمية
            legacy_lnk = d_dir / "share coc.lnk"
            if legacy_lnk.exists():
                create_windows_shortcut(
                    legacy_lnk, exe_path, working_dir=exe_path.parent, icon_path=ico,
                    description=APP_DISPLAY_NAME
                )
        results["desktop_shortcut"] = desktop_ok

    # 2. قائمة ابدأ (Start Menu)
    if create_start_menu:
        sm_dir = get_start_menu_folder()
        sm_dir.mkdir(parents=True, exist_ok=True)
        sm_ok = create_windows_shortcut(
            sm_dir / "Share COC – غرفة تجارة كربلاء المقدسة.lnk",
            exe_path,
            working_dir=exe_path.parent,
            icon_path=ico,
            description=APP_DISPLAY_NAME,
        )
        # اختصار فتح المجلد المشترك مباشرة من قائمة ابدأ
        explorer_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
        create_windows_shortcut(
            sm_dir / "المجلد السحابي المشترك (FileExchangeShared).lnk",
            explorer_exe,
            arguments=f'"{sync_folder}"',
            working_dir=sync_folder,
            icon_path=ico,
            description="فتح المجلد السحابي المشترك لغرفة تجارة كربلاء المقدسة",
        )
        if uninstaller_path and uninstaller_path.exists():
            create_windows_shortcut(
                sm_dir / "إلغاء تثبيت Share COC.lnk",
                uninstaller_path,
                arguments="--uninstall",
                working_dir=exe_path.parent,
                icon_path=ico,
                description="إلغاء تثبيت منظومة Share COC من الحاسوب",
            )
        results["start_menu"] = sm_ok

    # 3. قائمة الزر الأيمن (إرسال إلى -> Share COC السحابة)
    if create_sendto:
        sendto_dir = get_sendto_folder()
        sendto_lnk = sendto_dir / "Share COC – رفع ومزامنة للسحابة.lnk"
        results["sendto_menu"] = create_windows_shortcut(
            sendto_lnk,
            exe_path,
            arguments="--upload",
            working_dir=exe_path.parent,
            icon_path=ico,
            description="رفع الملف أو المجلد مباشرة إلى سحابة غرفة تجارة كربلاء المقدسة",
        )

    # 4. بروتوكول المتصفح sharecoc://
    results["protocol"] = register_protocol_handler(exe_path, ico)

    # 5. التشغيل التلقائي مع بدء تشغيل Windows
    try:
        from autostart import set_windows_autostart
        ok_auto, _ = set_windows_autostart(enable=enable_autostart, exe_path=str(exe_path))
        results["autostart"] = ok_auto
    except Exception:
        results["autostart"] = False

    # 6. التسجيل في البرامج والميزات (Add/Remove Programs)
    if register_uninstaller:
        u_path = uninstaller_path or (exe_path.parent / UNINSTALL_EXE_NAME)
        results["uninstall_registry"] = register_uninstaller_in_windows(
            install_dir=exe_path.parent,
            exe_path=exe_path,
            uninstaller_path=u_path,
            icon_path=ico,
        )

    return results
