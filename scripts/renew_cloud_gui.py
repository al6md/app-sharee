# -*- coding: utf-8 -*-
"""
نافذة بصرية سهلة لتجديد اتصال سحابة Google Drive - غرفة تجارة كربلاء المقدسة
"""
import sys
import os
import json
import webbrowser
import urllib.parse
from pathlib import Path
import requests

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

def get_base_config():
    workspace_root = Path(__file__).resolve().parent.parent
    candidates = [
        workspace_root / "desktop-client" / "gdrive_credentials.json",
        Path.home() / "AppData" / "Roaming" / "FileExchange" / "gdrive_credentials.json",
        Path.home() / "FileExchangeShared" / ".gdrive_credentials.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("client_id") and data.get("client_secret"):
                        return data
            except Exception:
                pass
    return {
        "client_id": os.environ.get("GDRIVE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GDRIVE_CLIENT_SECRET", ""),
        "folder_id": os.environ.get("GDRIVE_FOLDER_ID", "1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB"),
    }

BASE_CONFIG = get_base_config()
CLIENT_ID = BASE_CONFIG.get("client_id", "")
CLIENT_SECRET = BASE_CONFIG.get("client_secret", "")
FOLDER_ID = BASE_CONFIG.get("folder_id", "1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB")
REDIRECT_URI = "https://developers.google.com/oauthplayground"

def get_auth_url():
    return (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"response_type=code&"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
        f"scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive&"
        f"access_type=offline&"
        f"prompt=consent"
    )

def clean_input(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    # إذا كان رابطاً كاملاً، استخراج قيمة code
    if "code=" in text:
        try:
            parsed = urllib.parse.urlparse(text)
            qs = urllib.parse.parse_qs(parsed.query)
            if "code" in qs and qs["code"]:
                return qs["code"][0].strip()
        except Exception:
            pass
    # إزالة أي علامات اقتباس أو مسافات
    for ch in ['"', "'", "“", "”", "‘", "’", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c"]:
        text = text.replace(ch, "")
    return text.strip()

def verify_refresh_token(refresh_token):
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code == 200:
        return True, resp.json().get("access_token")
    return False, resp.text

def exchange_auth_code(auth_code):
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        return True, data.get("refresh_token")
    return False, resp.text

class CloudRenewDialog(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("تجديد اتصال سحابة Google Drive - Share COC")
        self.setFixedSize(650, 480)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet("""
            QWidget {
                background-color: #F8FAFC;
                font-family: 'Segoe UI', Tahoma, sans-serif;
                color: #1E293B;
            }
            QLabel {
                font-size: 13px;
            }
            QLineEdit {
                background-color: #FFFFFF;
                border: 2px solid #CBD5E1;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #10B981;
            }
            QPushButton#btnOpen {
                background-color: #2563EB;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
            }
            QPushButton#btnOpen:hover {
                background-color: #1D4ED8;
            }
            QPushButton#btnApply {
                background-color: #059669;
                color: white;
                font-size: 15px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 14px 20px;
            }
            QPushButton#btnApply:hover {
                background-color: #047857;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # العنوان
        header = QLabel("🔐 تجديد رمز الاتصال بسحابة Google Drive")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.setStyleSheet("color: #0F172A;")
        layout.addWidget(header)

        desc = QLabel(
            "انتهت صلاحية رمز الربط (7 أيام) في Google. اتبع الخطوتين التاليتين لاستعادة ظهور الملفات للجميع فوراً وبشكل دائم:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #64748B; font-size: 13px; line-height: 1.4;")
        layout.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(sep)

        # الخطوة 1
        step1_lbl = QLabel("الخطوة 1: تسجيل الدخول والموافقة في Google")
        step1_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        step1_lbl.setStyleSheet("color: #1E293B;")
        layout.addWidget(step1_lbl)

        btn_open = QPushButton("🌐 اضغط هنا لفتح صفحة تسجيل الدخول في المتصفح")
        btn_open.setObjectName("btnOpen")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self.open_browser)
        layout.addWidget(btn_open)

        hint1 = QLabel("💡 في المتصفح: اختر حساب الغرفة واضغط (خيارات متقدمة > متابعة / سماح)، ثم انسخ رابط الصفحة التي سيتم تحويلك إليها.")
        hint1.setWordWrap(True)
        hint1.setStyleSheet("color: #64748B; font-size: 11px;")
        layout.addWidget(hint1)

        layout.addSpacing(6)

        # الخطوة 2
        step2_lbl = QLabel("الخطوة 2: الصق الرابط أو الكود هنا")
        step2_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        step2_lbl.setStyleSheet("color: #1E293B;")
        layout.addWidget(step2_lbl)

        self.input_token = QLineEdit()
        self.input_token.setPlaceholderText("الصق الرابط الكامل من المتصفح (https://...) أو الكود (4/0A...) أو (1//...)")
        layout.addWidget(self.input_token)

        # زر التفعيل
        self.btn_apply = QPushButton("⚡ تفعيل الرمز واستعادة ظهور الملفات فوراً")
        self.btn_apply.setObjectName("btnApply")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.clicked.connect(self.apply_token)
        layout.addWidget(self.btn_apply)

        # رسالة الحالة
        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_lbl)

        # محاولة قراءة الحافظة تلقائياً إذا كان بها كود
        try:
            clipboard = QApplication.clipboard().text()
            if clipboard and ("code=" in clipboard or clipboard.startswith("4/") or clipboard.startswith("1//")):
                self.input_token.setText(clipboard)
        except Exception:
            pass

    def open_browser(self):
        webbrowser.open(get_auth_url())
        self.status_lbl.setText("تم فتح صفحة Google في المتصفح. سجّل الدخول وانسخ الرابط.")
        self.status_lbl.setStyleSheet("color: #2563EB; font-weight: bold;")

    def apply_token(self):
        raw = self.input_token.text().strip()
        token = clean_input(raw)

        if not token:
            QMessageBox.warning(self, "تنبيه", "يرجى لصق الرابط أو الرمز أولاً بعد فتح المتصفح والموافقة.")
            return

        self.btn_apply.setEnabled(False)
        self.status_lbl.setText("جاري التحقق مع Google...")
        self.status_lbl.setStyleSheet("color: #64748B;")
        QApplication.processEvents()

        final_refresh_token = token

        # إذا كان كود تفويض يحتاج لتبديل
        if token.startswith("4/") or len(token) < 75:
            ok, res = exchange_auth_code(token)
            if ok and res:
                final_refresh_token = res
            else:
                self.btn_apply.setEnabled(True)
                self.status_lbl.setText(f"فشل استخراج الرمز من الكود: {res}")
                self.status_lbl.setStyleSheet("color: #DC2626; font-weight: bold;")
                QMessageBox.critical(self, "خطأ", f"تعذر استبدال الكود بـ Refresh Token:\n\n{res}\n\nتأكد من نسخه مباشرة دون تأخير.")
                return

        # التحقق من صلاحية الـ Refresh Token
        ok, res = verify_refresh_token(final_refresh_token)
        if not ok:
            self.btn_apply.setEnabled(True)
            self.status_lbl.setText("الرمز غير صالح أو تم رفضه من Google")
            self.status_lbl.setStyleSheet("color: #DC2626; font-weight: bold;")
            QMessageBox.critical(self, "خطأ في التحقق", f"خوادم Google رفضت هذا الرمز:\n\n{res}")
            return

        # حفظ الرمز في كافة المسارات
        try:
            workspace_root = Path(__file__).resolve().parent.parent

            # 1. web-dashboard .env.local
            env_path = workspace_root / "web-dashboard" / ".env.local"
            if env_path.exists():
                content = env_path.read_text(encoding="utf-8")
                lines = []
                for line in content.splitlines():
                    if line.startswith("GDRIVE_REFRESH_TOKEN="):
                        lines.append(f"GDRIVE_REFRESH_TOKEN={final_refresh_token}")
                    else:
                        lines.append(line)
                env_path.write_text("\n".join(lines), encoding="utf-8")

            # 2. Desktop creds
            creds_paths = [
                workspace_root / "desktop-client" / "gdrive_credentials.json",
                Path.home() / "AppData" / "Roaming" / "FileExchange" / "gdrive_credentials.json",
                Path.home() / "FileExchangeShared" / ".gdrive_credentials.json",
            ]
            for cp in creds_paths:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cred_data = {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "refresh_token": final_refresh_token,
                    "folder_id": FOLDER_ID
                }
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(cred_data, f, indent=2)

            self.status_lbl.setText("🎉 تم الاتصال بنجاح وعادت الملفات للظهور!")
            self.status_lbl.setStyleSheet("color: #059669; font-weight: bold; font-size: 14px;")

            QMessageBox.information(
                self,
                "تم بنجاح!",
                "تم تجديد الاتصال بسحابة Google Drive بنجاح وتحديث كافة ملفات النظام!\n\n"
                "يمكنك الآن فتح التطبيق أو تحديث الصفحة وستظهر كافة المستندات والأقسام."
            )
            self.close()

        except Exception as e:
            self.btn_apply.setEnabled(True)
            self.status_lbl.setText(f"خطأ أثناء الحفظ: {e}")
            self.status_lbl.setStyleSheet("color: #DC2626;")
            QMessageBox.critical(self, "خطأ في الحفظ", f"حدث خطأ أثناء حفظ الإعدادات:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CloudRenewDialog()
    window.show()
    sys.exit(app.exec())
