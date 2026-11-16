"""
تبادل الملفات – File Exchange System
نقطة الدخول الرئيسية للتطبيق على أجهزة Windows (Main Entry Point)
"""
import os
import sys
import time
import uuid
import subprocess
import threading
from pathlib import Path

# ضمان تسجيل آمن للمخرجات وحمايتها من أخطاء السي بي في وضع PyInstaller (console=False)
try:
    _log_dir = Path(os.environ.get("APPDATA", Path.home())) / "FileExchange"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / "share_coc.log"
    if getattr(sys, 'frozen', False) or sys.stdout is None:
        _f = open(_log_file, "a", encoding="utf-8", errors="replace", buffering=1)
        sys.stdout = _f
        sys.stderr = _f
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _clean_pyinstaller_child_env():
    """تنظيف متغيرات بيئة PyInstaller عند تشغيل نسخة جديدة مستقلة من التطبيق"""
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(env.keys()):
        if key == "_MEIPASS2" or key.startswith("_PYI_") or key in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
            env.pop(key, None)
    return env


def _repair_startup_ca_bundle():
    """حفظ وإصلاح مسار شهادات TLS عند بدء التشغيل لمنع فقدانها عند خروج العملية المرسلة"""
    try:
        import shutil
        import certifi
        persistent_cacert = Path(os.environ.get("APPDATA", Path.home())) / "FileExchange" / "cacert.pem"
        persistent_cacert.parent.mkdir(parents=True, exist_ok=True)
        c_path = certifi.where()
        if c_path and os.path.isfile(c_path) and os.path.getsize(c_path) > 10000:
            if not persistent_cacert.is_file() or persistent_cacert.stat().st_size != os.path.getsize(c_path):
                tmp_cacert = persistent_cacert.with_suffix(".pem.tmp")
                shutil.copy2(c_path, tmp_cacert)
                os.replace(tmp_cacert, persistent_cacert)
        if persistent_cacert.is_file() and persistent_cacert.stat().st_size > 10000:
            os.environ["REQUESTS_CA_BUNDLE"] = str(persistent_cacert)
            os.environ["SSL_CERT_FILE"] = str(persistent_cacert)
            return
    except Exception:
        pass
    for env_key in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        env_val = os.environ.get(env_key)
        if env_val and not os.path.exists(env_val):
            os.environ.pop(env_key, None)


_repair_startup_ca_bundle()


def _safe_log_err(msg):
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(_log_file, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass

def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """حارس الاستثناءات العالمي: تسجيل الأخطاء غير المتوقعة ومنع انهيار PyQt6 المفاجئ"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    import traceback
    err_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    _safe_log_err(f"[UNHANDLED EXCEPTION]: {err_text}")

def _thread_exception_handler(args):
    """حارس استثناءات الخيوط الخلفية لمنع توقف المحرك فجأة"""
    if issubclass(args.exc_type, KeyboardInterrupt):
        return
    import traceback
    err_text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    _safe_log_err(f"[THREAD EXCEPTION in {getattr(args.thread, 'name', 'unknown')}]: {err_text}")

sys.excepthook = _global_exception_handler
if hasattr(threading, 'excepthook'):
    threading.excepthook = _thread_exception_handler

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType

def _qt_message_handler(msg_type, context, message):
    if msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        _safe_log_err(f"[Qt {msg_type.name}]: {message}")

qInstallMessageHandler(_qt_message_handler)

from gdrive_client import GoogleDriveClient, _md5_file, norm_key, norm_rel
from offline_queue import LocalStateManager
from sync_engine import SyncEngine
from gui import FileExchangeMainWindow
from local_bridge import start_local_bridge


def _parse_sharecoc_target(raw_target):
    """تحليل رابط sharecoc:// أو اسم الملف واستخراج معاملات الفتح بما فيها md5 الاختياري"""
    import urllib.parse
    raw = str(raw_target or "").strip(' "\'')
    target_action = "open"
    target_file = ""
    target_folder = ""
    target_storage_path = ""
    target_md5 = ""

    if raw.lower().startswith("sharecoc:"):
        url_to_parse = raw
        if not url_to_parse.lower().startswith("sharecoc://"):
            url_to_parse = "sharecoc://" + url_to_parse.split(":", 1)[1].lstrip("/")
        url_to_parse = url_to_parse.rstrip("/")
        parsed = urllib.parse.urlparse(url_to_parse)
        target_action = parsed.netloc.lower() if parsed.netloc else "open"
        qs = urllib.parse.parse_qs(parsed.query)
        target_file = qs.get("file", [""])[0].strip()
        target_folder = qs.get("folder", [""])[0].strip()
        target_storage_path = qs.get("storage_path", [""])[0].strip()
        target_md5 = qs.get("md5", [""])[0].strip()
    else:
        target_file = raw

    return {
        "action": target_action,
        "file": urllib.parse.unquote(target_file).strip(' "\'').rstrip('/\\'),
        "folder": urllib.parse.unquote(target_folder).strip(' "\'').rstrip('/\\'),
        "storage_path": urllib.parse.unquote(target_storage_path).strip(' "\''),
        "md5": urllib.parse.unquote(target_md5).strip(' "\'').lower(),
    }


def _find_cli_local_candidate(sync_folder, target_file, target_folder="", clean_bidi_fn=None):
    """البحث المحلي عن الملف مع تطبيع Unicode NFC وتجاهل حالة الأحرف وعلامات الاتجاه"""
    import re
    sync_root = Path(sync_folder)
    if clean_bidi_fn is None:
        clean_bidi_fn = lambda s: re.sub(r'[​-‏‪-‮⁦-⁩﻿]', '', str(s)).strip()

    clean_file = clean_bidi_fn(target_file)
    norm_sub = target_folder.replace("\\", "/").strip("/") if target_folder and target_folder not in ('__ALL__', 'المجلد العام', 'القسم العام') else ""
    clean_sub = "/".join(clean_bidi_fn(p) for p in norm_sub.split("/") if p) if norm_sub else ""

    candidates = []
    if norm_sub:
        candidates.extend([
            sync_root / norm_sub / target_file,
            sync_root / clean_sub / clean_file,
            sync_root / norm_sub / clean_file,
        ])
    candidates.extend([
        sync_root / target_file,
        sync_root / clean_file,
    ])
    for c in candidates:
        if c.exists() and c.is_file():
            return c, norm_sub

    expected_rel = norm_key(f"{clean_sub}/{clean_file}" if clean_sub else clean_file)
    expected_name = norm_key(clean_file)
    if sync_root.exists():
        first_name_match = None
        for sub in sync_root.rglob("*"):
            if not sub.is_file():
                continue
            if any(part.startswith(".") for part in sub.relative_to(sync_root).parts):
                continue
            rel_str = norm_rel(sub.relative_to(sync_root))
            clean_rel_k = norm_key(clean_bidi_fn(rel_str))
            if clean_rel_k == expected_rel or norm_key(rel_str) == expected_rel:
                return sub, norm_sub
            if first_name_match is None and norm_key(clean_bidi_fn(sub.name)) == expected_name:
                first_name_match = sub
        if first_name_match is not None:
            return first_name_match, norm_sub

    return None, norm_sub


def _resolve_and_prepare_open_target(
    sync_folder,
    target_file,
    target_folder="",
    target_storage_path="",
    expected_md5="",
    client=None,
    state_mgr=None,
):
    """
    التحقق من حداثة النسخة المحلية مقارنة بالخادم (عبر md5 وميتاداتا الخادم) قبل فتح أي ملف
    عبر سطر الأوامر، وتنزيل أحدث نسخة أولاً إذا كانت النسخة المحلية متأخرة وكان الخادم متاحاً.
    """
    import re
    sync_root = Path(sync_folder)
    sync_root.mkdir(parents=True, exist_ok=True)
    clean_bidi = lambda s: re.sub(r'[​-‏‪-‮⁦-⁩﻿]', '', str(s)).strip()
    clean_file = clean_bidi(target_file)
    target_cand, norm_sub = _find_cli_local_candidate(sync_root, target_file, target_folder, clean_bidi)

    from office_handler import OfficeHandler
    g_client = client if client is not None else GoogleDriveClient(state_mgr=state_mgr)

    remote_meta = None
    remote_rel = None
    snap = None
    try:
        if g_client and g_client.is_configured():
            snap = g_client.snapshot(force=True, max_age=0)
    except Exception:
        snap = None

    if snap and getattr(snap, "files", None):
        sp = str(target_storage_path or "").strip()
        if sp and sp in getattr(snap, "file_ids", {}):
            remote_rel = snap.file_ids[sp]
            remote_meta = snap.files.get(remote_rel)
        if not remote_meta:
            rel_guess = f"{norm_sub}/{clean_file}" if norm_sub else clean_file
            rk = norm_key(rel_guess)
            for r_rel, rmeta in snap.files.items():
                if norm_key(r_rel) == rk:
                    remote_rel = r_rel
                    remote_meta = rmeta
                    break
        if not remote_meta and not norm_sub:
            fn_k = norm_key(clean_file)
            for r_rel, rmeta in snap.files.items():
                if norm_key(rmeta.get("name", "")) == fn_k:
                    remote_rel = r_rel
                    remote_meta = rmeta
                    break

    server_md5 = str((remote_meta or {}).get("md5Checksum") or "").strip().lower()
    want_md5 = server_md5 or str(expected_md5 or "").strip().lower()
    effective_sp = str((remote_meta or {}).get("id") or target_storage_path or "").strip()

    need_download = target_cand is None
    if target_cand is not None and want_md5:
        try:
            local_md5 = _md5_file(str(target_cand)).lower()
            if local_md5 != want_md5:
                need_download = True
        except OSError:
            need_download = True

    if need_download and g_client and g_client.is_configured():
        try:
            if remote_rel:
                dest_path = sync_root / remote_rel
            elif target_cand is not None:
                dest_path = target_cand
            else:
                target_sub_dir = (sync_root / norm_sub) if norm_sub else sync_root
                dest_path = target_sub_dir / clean_file
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            temp_dir = sync_root / ".sync_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / f"cli_dl_{int(time.time() * 1000)}_{dest_path.name}.tmp"
            try:
                res = g_client.download_file(clean_file, str(temp_path), storage_path=effective_sp)
                success = res[0] if isinstance(res, tuple) else bool(res)
                if success and temp_path.exists():
                    if OfficeHandler.safe_apply_file(str(dest_path), str(temp_path)):
                        target_cand = dest_path
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception as dl_err:
            _safe_log_err(f"[CLI Download Error]: {dl_err}")

    return target_cand


def ensure_desktop_shortcut():
    """إنشاء وتأكيد وجود اختصار لتطبيق share coc على سطح المكتب بشعاره الرسمي"""
    try:
        if getattr(sys, 'frozen', False):
            target_exe = sys.executable
            app_dir = Path(target_exe).parent
        else:
            target_exe = str(Path(__file__).resolve())
            app_dir = Path(__file__).parent.parent

        desktop_paths = [
            Path(os.environ.get('USERPROFILE', 'C:')) / "OneDrive" / "Desktop",
            Path(os.environ.get('USERPROFILE', 'C:')) / "Desktop"
        ]
        for dp in desktop_paths:
            if (dp / "share coc.lnk").exists():
                return

        ico_path = app_dir / "assets" / "logo.ico"
        if not ico_path.exists():
            ico_path = app_dir / "logo.ico"

        ps_script = f"""
        $wsh = New-Object -ComObject WScript.Shell
        $desktop = [Environment]::GetFolderPath('Desktop')
        if (-not (Test-Path $desktop)) {{
            $desktop = Join-Path $env:USERPROFILE 'OneDrive\\Desktop'
        }}
        $shortcutPath = Join-Path $desktop 'share coc.lnk'
        $s = $wsh.CreateShortcut($shortcutPath)
        $s.TargetPath = '{target_exe}'
        $s.WorkingDirectory = '{str(app_dir)}'
        $s.Description = 'Share COC - منظومة تبادل وأرشفة مستندات غرفة تجارة كربلاء المقدسة'
        if (Test-Path '{str(ico_path)}') {{
            $s.IconLocation = '{str(ico_path)},0'
        }} else {{
            $s.IconLocation = '{target_exe},0'
        }}
        $s.Save()
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True, timeout=3,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
    except Exception as e:
        print(f"[Shortcut creation]: {e}")


def _find_sharecoc_hwnds():
    hwnds = []
    try:
        import ctypes
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        def _enum_proc(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                t = buf.value.lower()
                if "share coc" in t or "تبادل الملفات" in t or "كربلاء" in t:
                    hwnds.append(hwnd)
            return 1
        CB = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)(_enum_proc)
        user32.EnumWindows(CB, 0)
    except Exception:
        pass
    return hwnds


def _activate_running_instance(retries=2, delay=0.15):
    """محاولة إيقاظ وإظهار النسخة العاملة حالياً والتحقق من وجود نافذة حقيقية"""
    # 1. فحص وجود نافذة Win32 حقيقية وتنشيطها (حتى لو كانت مصغرة أو في صينية النظام)
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnds = _find_sharecoc_hwnds()
        if hwnds:
            for hwnd in hwnds:
                try:
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.ShowWindow(hwnd, 5)  # SW_SHOW
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
            return True
    except Exception:
        pass

    # 2. إيقاظ عبر مقبس الجسر المحلي مع تجاوز بروكسي النظام
    import urllib.request
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:18290/show", timeout=1.2) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass

    # 3. إيقاظ عبر حدث ويندوز المسمى فقط إذا كان هناك مقبض فعلي
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        EVENT_MODIFY_STATE = 0x0002
        h_ev = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, "Global\\KarbalaChamberShareCOCShowEvent")
        if h_ev:
            kernel32.SetEvent(h_ev)
            kernel32.CloseHandle(h_ev)
            return True
    except Exception:
        pass

    return False


def _kill_unresponsive_zombies():
    """تحرير منافذ الجسر المعلقة فقط في حال عدم استجابة العملية العاملة دون إنهاء عشوائي"""
    import psutil
    curr_pid = os.getpid()

    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr and conn.laddr.port in (18290, 18292) and conn.pid and conn.pid != curr_pid:
                try:
                    p = psutil.Process(conn.pid)
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass


def main():
    # 1. فحص وسائط سطر الأوامر لفتح الملف مباشرة بالبرنامج الأصلي (مثل Word أو Excel)
    if len(sys.argv) > 1 and sys.argv[1] == '--open':
        _safe_log_err(f'[CLI ARGV RECEIVED]: {sys.argv}')
        raw_target = sys.argv[2] if len(sys.argv) > 2 else ""
        parsed_target = _parse_sharecoc_target(raw_target)
        target_action = parsed_target["action"]
        target_file = parsed_target["file"]
        target_folder = parsed_target["folder"]
        target_storage_path = parsed_target["storage_path"]
        target_md5 = parsed_target["md5"]

        if target_file:
            import re
            import urllib.parse
            def clean_bidi(s):
                return re.sub(r'[​-‏‪-‮⁦-⁩﻿]', '', str(s)).strip()

            clean_target_file = clean_bidi(target_file)

            # 1. محاولة تمرير الطلب للجسر المحلي المفتوح بالفعل في الخلفية
            try:
                import urllib.request
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                endpoint = "reveal" if target_action == "reveal" else "open"
                bridge_url = (
                    f"http://127.0.0.1:18290/{endpoint}?file={urllib.parse.quote(clean_target_file)}"
                    f"&folder={urllib.parse.quote(target_folder)}"
                    f"&storage_path={urllib.parse.quote(target_storage_path)}"
                )
                if target_md5:
                    bridge_url += f"&md5={urllib.parse.quote(target_md5)}"
                with opener.open(bridge_url, timeout=4.0) as req:
                    if req.status == 200:
                        sys.exit(0)
            except Exception as bridge_err:
                _safe_log_err(f"[CLI Bridge Forward Notice]: {bridge_err}")

            # 2. إذا لم يستجب الجسر، فحصه محلياً والتحقق من حداثته أمام الخادم ثم تنزيل الأحدث عند الحاجة
            sync_folder = Path(os.environ.get('USERPROFILE', 'C:')) / "FileExchangeShared"
            from office_handler import OfficeHandler

            cli_state_mgr = None
            try:
                cli_state_mgr = LocalStateManager()
            except Exception:
                pass
            target_cand = _resolve_and_prepare_open_target(
                sync_folder=sync_folder,
                target_file=target_file,
                target_folder=target_folder,
                target_storage_path=target_storage_path,
                expected_md5=target_md5,
                state_mgr=cli_state_mgr,
            )

            if target_cand and target_cand.exists():
                OfficeHandler.open_native_file(str(target_cand), synchronous=True)
                # تشغيل تطبيق الحاسوب في صينية النظام (System Tray) ليبقى متصلاً ومتاحاً للطلبات التالية
                try:
                    if getattr(sys, 'frozen', False):
                        subprocess.Popen(
                            [sys.executable],
                            env=_clean_pyinstaller_child_env(),
                            creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0x00000008),
                            close_fds=True,
                        )
                except Exception:
                    pass
                sys.exit(0)
            else:
                app_err = QApplication(sys.argv)
                QMessageBox.warning(
                    None, "مشاركة الملفات – تنبيه",
                    f"تعذر العثور على المستند المطلوب:\n{clean_target_file}\n"
                    "يرجى التأكد من رفع الملف بنجاح أو مراجعة الاتصال بالسحابة."
                )
                sys.exit(1)

    # 1.5 معالجة الملفات المرسلة عبر قائمة الزر الأيمن في ويندوز (Send To -> Share COC)
    cli_upload_paths = []
    if len(sys.argv) > 1:
        raw_args = sys.argv[1:]
        if raw_args[0] == "--upload":
            raw_args = raw_args[1:]
        for arg in raw_args:
            if not arg.startswith("-") and not arg.startswith("sharecoc://"):
                p = Path(arg)
                if p.exists():
                    cli_upload_paths.append(p)

    # 2. التأكد من تشغيل نسخة واحدة فقط لمنع استنساخ العمليات
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    kernel32 = ctypes.windll.kernel32
    _single_instance_mutex = kernel32.CreateMutexW(None, False, "Global\\KarbalaChamberShareCOCSingleInstanceMutex")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        # إذا تم إرسال ملفات عبر Send To وهناك نسخة تعمل بالفعل، انسخها لمجلد المزامنة وأيقظ المحرك فوراً
        if cli_upload_paths:
            import shutil
            sync_folder = Path(os.environ.get('USERPROFILE', 'C:')) / "FileExchangeShared"
            sync_folder.mkdir(parents=True, exist_ok=True)
            for src_p in cli_upload_paths:
                try:
                    dest_p = sync_folder / src_p.name
                    if src_p.is_file() and src_p.resolve() != dest_p.resolve():
                        shutil.copy2(str(src_p), str(dest_p))
                        os.utime(str(dest_p), None)
                    elif src_p.is_dir() and src_p.resolve() != dest_p.resolve():
                        shutil.copytree(str(src_p), str(dest_p), dirs_exist_ok=True)
                except Exception as copy_err:
                    print(f"[CLI SendTo copy]: {copy_err}")
            try:
                import urllib.request
                urllib.request.urlopen("http://127.0.0.1:18290/sync", timeout=1.5)
            except Exception:
                pass
        # هناك نسخة مسجلة؛ محاولة إيقاظ النافذة وإظهارها فوراً
        # 1. إرسال طلب صريح إلى المنفذ المحلي /show لإظهار النافذة من شريط المهام وصينية النظام (Tray)
        try:
            import urllib.request
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:18290/show", timeout=1.0) as resp:
                if resp.status == 200:
                    sys.exit(0)
        except Exception:
            pass

        # 2. محاولة تنشيطها عبر واجهات ويندوز (Win32 Event & HWND)
        activated = _activate_running_instance(retries=2, delay=0.25)
        if activated:
            sys.exit(0)

        # 3. فحص إضافي: هل المنفذ 18290 يستجيب للـ status؟
        is_alive = False
        try:
            import urllib.request
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:18290/status", timeout=1.0) as resp:
                if resp.status == 200:
                    is_alive = True
        except Exception:
            is_alive = False

        if is_alive:
            try:
                opener.open("http://127.0.0.1:18290/show", timeout=0.8)
            except Exception:
                pass
            sys.exit(0)

        # فقط إذا تعذر التنشيط والمنفذ لا يستجيب تماماً، فالعملية السابقة متجمدة؛ إنهاؤها وتحرير المنفذ والقفل
        _kill_unresponsive_zombies()
        try:
            kernel32.CloseHandle(_single_instance_mutex)
        except Exception:
            pass
        time.sleep(0.15)
        _single_instance_mutex = kernel32.CreateMutexW(None, False, "Global\\KarbalaChamberShareCOCSingleInstanceMutex")

    app = QApplication(sys.argv)
    app._single_instance_mutex = _single_instance_mutex
    app.setApplicationName("share coc")
    app.setApplicationDisplayName("Share COC")
    app.setOrganizationName("KarbalaChamberOfCommerce")
    app.setQuitOnLastWindowClosed(False)

    if getattr(sys, 'frozen', False):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).parent.parent
    logo_path = base_dir / "assets" / "logo.ico"
    if not logo_path.exists():
        logo_path = base_dir / "assets" / "logo.png"
    if logo_path.exists():
        from PyQt6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(logo_path)))

    # تأكيد وجود اختصار البرنامج على سطح المكتب في خيط خلفي
    threading.Thread(target=ensure_desktop_shortcut, daemon=True).start()

    # مجلد المزامنة المحلي على جهاز المستخدم
    sync_folder = Path(os.environ.get('USERPROFILE', 'C:')) / "FileExchangeShared"
    sync_folder.mkdir(parents=True, exist_ok=True)

    state_mgr = LocalStateManager()
    cloud_client = GoogleDriveClient(state_mgr=state_mgr)
    cloud_client.sync_folder = sync_folder

    device_id = str(uuid.uuid4())
    device_name = state_mgr.get_setting("device_name", os.environ.get('COMPUTERNAME', 'جهاز-مستخدم'))
    username = state_mgr.get_setting("user_email", "المستخدم")

    sync_engine = SyncEngine(
        sync_folder=sync_folder,
        cloud_client=cloud_client,
        local_state_mgr=state_mgr,
        device_id=device_id,
        device_name=device_name,
        username=username
    )

    # إنشاء وإظهار النافذة فوراً قبل بدء المزامنة الخلفية لضمان عدم ظهور شاشة بيضاء أبداً
    window = FileExchangeMainWindow(sync_engine, cloud_client, state_mgr, sync_folder)
    window.show()
    window.raise_()
    window.activateWindow()
    app.processEvents()

    # إعداد حدث ويندوز المسمى للإيقاظ فائق السرعة اللحظي (< 1ms)
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h_show_event = kernel32.CreateEventW(None, False, False, "Global\\KarbalaChamberShareCOCShowEvent")
        if h_show_event:
            def _event_listener():
                while True:
                    res = kernel32.WaitForSingleObject(h_show_event, 0xFFFFFFFF)
                    if res == 0:
                        window.bridge.show_requested.emit()
            threading.Thread(target=_event_listener, daemon=True, name="WinShowEventListener").start()
    except Exception:
        pass

    # تشغيل خادم الجسر المحلي ومحرك المزامنة في الخلفية
    start_local_bridge(
        sync_folder,
        cloud_client=cloud_client,
        sync_engine=sync_engine,
        show_window_callback=lambda: window.bridge.show_requested.emit()
    )
    sync_engine.start()
    if cli_upload_paths:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(600, lambda: window._handle_dropped_paths(cli_upload_paths))

    exit_code = app.exec()
    try:
        sync_engine.stop()
    except Exception:
        pass
    os._exit(exit_code)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        main()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        try:
            with open(_log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[FATAL CRASH]: {err_msg}\n")
        except Exception:
            pass
        from PyQt6.QtWidgets import QMessageBox, QApplication
        _err_app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "خطأ في تشغيل التطبيق", f"تعذر بدء تشغيل Share COC:\n\n{err_msg}")
        sys.exit(1)
