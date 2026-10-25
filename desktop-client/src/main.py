"""
تبادل الملفات – File Exchange System
نقطة الدخول الرئيسية للتطبيق على أجهزة Windows (Main Entry Point)
"""
import os
import sys
import uuid
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt

from supabase_client import SupabaseClient
from r2_client import CloudflareR2Client
from offline_queue import LocalStateManager
from sync_engine import SyncEngine
from gui import FileExchangeMainWindow
from local_bridge import start_local_bridge, register_sharecoc_protocol

def get_machine_guid():
    """الحصول على الرقم التعريفي الفريد لجهاز الويندوز (Machine GUID)"""
    try:
        import winreg
        key = winreg.HKEY_LOCAL_MACHINE
        sub_key = r"SOFTWARE\Microsoft\Cryptography"
        with winreg.OpenKey(key, sub_key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            return guid
    except Exception:
        return str(uuid.getnode())

class LoginDialog(QDialog):
    def __init__(self, state_mgr):
        super().__init__()
        self.state_mgr = state_mgr
        self.supabase_client = None
        self.device_info = None

        self.setWindowTitle("تسجيل الدخول وربط السحابة – تبادل الملفات")
        self.resize(440, 340)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Segoe UI', 'Cairo', Tahoma; }
            QLabel { font-size: 13px; color: #0f172a; font-weight: 600; }
            QLineEdit {
                background-color: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 8px;
                padding: 10px 14px; font-size: 13px; color: #0f172a;
            }
            QLineEdit:focus {
                border: 2px solid #4f46e5;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
                color: white; border-radius: 8px; padding: 11px; font-weight: 800; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #4338ca; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("🔑 ربط جهاز الويندوز بحساب المؤسسة السحابي"))
        
        saved_url = self.state_mgr.get_setting("supabase_url", "")
        saved_key = self.state_mgr.get_setting("supabase_key", "")
        saved_email = self.state_mgr.get_setting("user_email", "")

        layout.addWidget(QLabel("عنوان الخادم السحابي (Supabase URL):"))
        self.txt_url = QLineEdit(saved_url)
        self.txt_url.setPlaceholderText("https://your-project-id.supabase.co")
        layout.addWidget(self.txt_url)

        layout.addWidget(QLabel("المفتاح العام للمشروع (Anon Public Key):"))
        self.txt_key = QLineEdit(saved_key)
        self.txt_key.setPlaceholderText("eyJhbGciOi...")
        layout.addWidget(self.txt_key)

        layout.addWidget(QLabel("البريد الإلكتروني للمستخدم:"))
        self.txt_email = QLineEdit(saved_email)
        layout.addWidget(self.txt_email)

        layout.addWidget(QLabel("كلمة المرور:"))
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_pass)

        layout.addWidget(QLabel("اسم هذا الجهاز (مثال: محاسبة-جهاز-1):"))
        default_dev_name = os.environ.get('COMPUTERNAME', 'جهاز-ويندوز')
        self.txt_device = QLineEdit(default_dev_name)
        layout.addWidget(self.txt_device)

        btn_login = QPushButton("تسجيل الدخول وبدء المزامنة")
        btn_login.clicked.connect(self._do_login)
        layout.addWidget(btn_login)

    def _do_login(self):
        url = self.txt_url.text().strip()
        key = self.txt_key.text().strip()
        email = self.txt_email.text().strip()
        pwd = self.txt_pass.text().strip()
        dev_name = self.txt_device.text().strip()

        if not all([url, key, email, pwd, dev_name]):
            QMessageBox.warning(self, "تنبيه", "يرجى تعبئة كافة الحقول المطلوبة.")
            return

        client = SupabaseClient(url, key)
        success, msg = client.sign_in(email, pwd)
        if not success:
            QMessageBox.critical(self, "خطأ في تسجيل الدخول", msg)
            return

        guid = get_machine_guid()
        is_auth, dev_data = client.register_or_verify_device(dev_name, guid)
        
        self.state_mgr.set_setting("supabase_url", url)
        self.state_mgr.set_setting("supabase_key", key)
        self.state_mgr.set_setting("user_email", email)
        self.state_mgr.set_setting("device_name", dev_name)

        self.supabase_client = client
        self.device_info = dev_data
        self.accept()

def ensure_desktop_shortcut():
    """إنشاء وتأكيد وجود اختصار لتطبيق share coc على سطح المكتب بشعاره الرسمي"""
    try:
        import subprocess
        if getattr(sys, 'frozen', False):
            target_exe = sys.executable
            app_dir = Path(target_exe).parent
        else:
            target_exe = str(Path(__file__).resolve())
            app_dir = Path(__file__).parent.parent

        ico_path = app_dir / "assets" / "logo.ico"
        if not ico_path.exists():
            ico_path = app_dir / "logo.ico"

        ps_script = f"""
        $wsh = New-Object -ComObject WScript.Shell
        $desktop = [Environment]::GetFolderPath('Desktop')
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
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, timeout=5)
    except Exception as e:
        print(f"[Shortcut creation]: {e}")

def main():
    # 1. فحص وسائط سطر الأوامر لفتح الملف مباشرة بالبرنامج الأصلي (مثل Word أو Excel)
    if len(sys.argv) > 1 and sys.argv[1] == '--open':
        raw_target = sys.argv[2] if len(sys.argv) > 2 else ""
        target_file = ""
        target_folder = ""

        if raw_target.startswith("sharecoc://"):
            import urllib.parse
            # فك تشفير sharecoc://open?file=...&folder=...
            parsed = urllib.parse.urlparse(raw_target)
            qs = urllib.parse.parse_qs(parsed.query)
            target_file = qs.get('file', [''])[0]
            target_folder = qs.get('folder', [''])[0]
        else:
            target_file = raw_target

        if target_file:
            # محاولة تمرير الطلب للجسر المحلي المفتوح بالفعل
            try:
                import urllib.request
                import urllib.parse
                bridge_url = f"http://127.0.0.1:18290/open?file={urllib.parse.quote(target_file)}&folder={urllib.parse.quote(target_folder)}"
                req = urllib.request.urlopen(bridge_url, timeout=1.5)
                if req.status == 200:
                    sys.exit(0)
            except Exception:
                pass

            # إذا لم يكن الجسر شغالاً، فتحه مباشرة من المجلد المحلي
            sync_folder = Path(os.environ.get('USERPROFILE', 'C:')) / "FileExchangeShared"
            from office_handler import OfficeHandler
            cand = sync_folder / target_folder / target_file if target_folder else sync_folder / target_file
            if not cand.exists():
                cand = sync_folder / target_file
            if not cand.exists():
                # بحث في المجلدات الفرعية
                for sub in sync_folder.rglob(target_file):
                    if sub.is_file():
                        cand = sub
                        break

            if cand.exists():
                OfficeHandler.open_native_file(str(cand))
                sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("share coc")
    app.setApplicationDisplayName("Share COC")
    app.setOrganizationName("KarbalaChamberOfCommerce")

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

    # تأكيد وجود اختصار البرنامج على سطح المكتب بشعاره المعتمد
    ensure_desktop_shortcut()

    # مجلد المزامنة المحلي على جهاز المستخدم
    sync_folder = Path(os.environ.get('USERPROFILE', 'C:')) / "FileExchangeShared"
    sync_folder.mkdir(parents=True, exist_ok=True)

    state_mgr = LocalStateManager()

    # فحص وتهيئة سحابة Cloudflare R2 (10GB مجاناً وبدون رسوم باندويث)
    r2_acc = state_mgr.get_setting("r2_account_id", os.environ.get("R2_ACCOUNT_ID", ""))
    r2_key = state_mgr.get_setting("r2_access_key_id", os.environ.get("R2_ACCESS_KEY_ID", ""))
    r2_sec = state_mgr.get_setting("r2_secret_access_key", os.environ.get("R2_SECRET_ACCESS_KEY", ""))
    r2_bkt = state_mgr.get_setting("r2_bucket_name", os.environ.get("R2_BUCKET_NAME", "file-exchange-storage"))

    r2_client = CloudflareR2Client(r2_acc, r2_key, r2_sec, r2_bkt)
    if r2_client.is_configured():
        cloud_client = r2_client
    else:
        saved_url = state_mgr.get_setting("supabase_url", "https://bjcillpivgcntzbwmpsm.supabase.co")
        saved_key = state_mgr.get_setting("supabase_key", "sb_publishable_Bfk1klLDNsLWKHvdRhWqNg_XoDqqJ6X")
        supabase_cli = SupabaseClient(saved_url, saved_key)
        cloud_client = supabase_cli if supabase_cli.is_configured() else r2_client
    
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
    sync_engine.start()

    # تشغيل خادم الجسر المحلي لربط متصفح الويب ولوحة الجوال ببرامج Office الأصلية
    start_local_bridge(sync_folder, cloud_client)

    window = FileExchangeMainWindow(sync_engine, cloud_client, state_mgr, sync_folder)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
