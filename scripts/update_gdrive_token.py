# -*- coding: utf-8 -*-
"""
أداة تحديث رمز Google Drive Refresh Token تلقائياً في كافة مسارات النظام
تدعم إدخال الرمز مباشرة أو رمز التفويض (Authorization Code)، وتدعم الإدخال التفاعلي
"""
import sys
import os
import json
import requests
from pathlib import Path

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

def clean_input(text: str) -> str:
    """تنظيف النص من علامات الاقتباس ومحارف الاتجاه الخاصة بالعربية ومسافات البداية والنهاية"""
    if not text:
        return ""
    for ch in ['"', "'", "“", "”", "‘", "’", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e"]:
        text = text.replace(ch, "")
    return text.strip()

def verify_token(refresh_token):
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
            "redirect_uri": "https://developers.google.com/oauthplayground",
        },
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        return True, data.get("refresh_token")
    return False, resp.text

def process_and_apply(raw_token):
    token = clean_input(raw_token)
    if not token:
        print("[ERROR] لم يتم إدخال أي رمز!")
        return False

    # فحص هل المستخدم أدخل نص توضيحي بدلاً من الرمز الفعلي
    if "الصق" in token or "زمر" in token or "ديدجلا" in token or "Refresh_Token" in token:
        print("\n[ERROR] يبدو أنك أدخلت عبارة الشرح التوضيحية بدلاً من رمز Google الفعلي!")
        print("رمز Google الحقيقي يبدأ دائماً بـ 1// أو 4/ ويكون مزيجاً من أحرف وأرقام إنجليزية طويلة.")
        return False

    final_refresh_token = token

    # إذا كان كود تفويض (Authorization code يبدأ بـ 4/)
    if token.startswith("4/") or len(token) < 75:
        print("[INFO] جاري تبديل كود التفويض (Authorization Code) للحصول على Refresh Token...")
        ok, res = exchange_auth_code(token)
        if ok and res:
            final_refresh_token = res
            print(f"✓ تم استخراج Refresh Token بنجاح: {final_refresh_token[:15]}...")
        else:
            # ربما هو refresh token قصير، نحاول التحقق منه
            pass

    # التحقق من صلاحية الـ Refresh Token مع Google
    print("[INFO] جاري التحقق من صلاحية الرمز مع خوادم Google Drive...")
    ok, res = verify_token(final_refresh_token)
    if not ok:
        print(f"\n[ERROR] الرمز غير صالح: {res}")
        print("\nتأكد من نسخه بالكامل من شاشة Google Playground (حقل Refresh token الذي يبدأ بـ 1//).")
        return False

    print("\n[SUCCESS] تم التحقق بنجاح! الاتصال بسحابة Google Drive يعمل بنسبة 100%.")

    # تحديث مسارات النظام
    workspace_root = Path(__file__).resolve().parent.parent

    # 1. Web dashboard
    env_path = workspace_root / "web-dashboard" / ".env.local"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        lines = []
        found = False
        for line in content.splitlines():
            if line.startswith("GDRIVE_REFRESH_TOKEN="):
                lines.append(f"GDRIVE_REFRESH_TOKEN={final_refresh_token}")
                found = True
            else:
                lines.append(line)
        if not found:
            lines.append(f"GDRIVE_REFRESH_TOKEN={final_refresh_token}")
        env_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"✓ تم تحديث إعدادات لوحة التحكم السحابية: {env_path.name}")
    else:
        new_env = (
            f"GDRIVE_CLIENT_ID={CLIENT_ID}\n"
            f"GDRIVE_CLIENT_SECRET={CLIENT_SECRET}\n"
            f"GDRIVE_REFRESH_TOKEN={final_refresh_token}\n"
            f"GDRIVE_FOLDER_ID={FOLDER_ID}\n"
        )
        env_path.write_text(new_env, encoding="utf-8")
        print(f"✓ تم إنشاء إعدادات لوحة التحكم السحابية: {env_path.name}")

    # 2. Desktop app paths
    creds_paths = [
        workspace_root / "desktop-client" / "gdrive_credentials.json",
        Path.home() / "AppData" / "Roaming" / "FileExchange" / "gdrive_credentials.json",
        Path.home() / "AppData" / "Roaming" / "ShareCOC" / "gdrive_credentials.json",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ShareCOC" / "gdrive_credentials.json",
        Path.home() / "FileExchangeShared" / ".gdrive_credentials.json",
        Path.home() / "ShareCOCShared" / ".gdrive_credentials.json",
        Path(r"C:\Users\tohiba\OneDrive\Desktop\ShareCOC\gdrive_credentials.json"),
    ]

    for cp in creds_paths:
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cred_data = {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": final_refresh_token,
                "folder_id": FOLDER_ID
            }
            with open(cp, "w", encoding="utf-8") as f:
                json.dump(cred_data, f, indent=2)
            print(f"✓ تم تحديث إعدادات التطبيق المكتبي: {cp}")
        except Exception as e:
            print(f"⚠ تعذر تحديث {cp}: {e}")

    print("\n🎉 تم تحديث رمز السحابة بنجاح! ستعود الملفات للظهور لجميع الأجهزة الآن.")
    return True

if __name__ == "__main__":
    import os
    if len(sys.argv) > 1:
        arg = " ".join(sys.argv[1:])
        process_and_apply(arg)
    else:
        print("=" * 60)
        print("  غرفة تجارة كربلاء المقدسة - أداة تجديد ربط السحابة")
        print("=" * 60)
        print("قم بنسخ الرمز من شاشة Google Playground (حقل Refresh token الذي يبدأ بـ 1//)")
        user_input = input("\nالصق الرمز هنا ثم اضغط Enter: ")
        process_and_apply(user_input)
        input("\nاضغط Enter للخروج...")
