"""
تبادل الملفات – File Exchange System (Share COC Enterprise v4.0)
سكريبت أتمتة بناء التطبيق التنفيذي ومعالج التثبيت الرسمي ShareCOC_Setup.exe
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def build_exe():
    print("=" * 65)
    print("بدء بناء وتجميع منظومة Share COC v4.0 ومعالج التثبيت الرسمي لـ Windows")
    print("=" * 65)

    current_dir = Path(__file__).parent.resolve()
    os.chdir(current_dir)

    print("[1/3] تجميع تطبيق سطح المكتب الرئيسي (dist/share coc.exe)...")
    app_spec = current_dir / "FileExchange.spec"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(app_spec)], check=True)

    app_exe = current_dir / "dist" / "share coc.exe"
    if not app_exe.exists():
        raise RuntimeError(f"❌ تعذر العثور على الملف التنفيذي المبني: {app_exe}")

    print("[2/3] تجميع معالج التثبيت الرسمي (dist/ShareCOC_Setup.exe)...")
    setup_spec = current_dir / "ShareCOC_Setup.spec"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(setup_spec)], check=True)

    setup_exe = current_dir / "dist" / "ShareCOC_Setup.exe"
    if not setup_exe.exists():
        raise RuntimeError(f"❌ تعذر العثور على معالج التثبيت: {setup_exe}")

    print("[3/3] تحديث نسخ التحميل المباشر في لوحة الويب ومجلد التثبيت المحلي...")
    web_public = current_dir.parent / "web-dashboard" / "public"
    if web_public.exists():
        shutil.copy2(str(app_exe), str(web_public / "share coc.exe"))
        shutil.copy2(str(setup_exe), str(web_public / "ShareCOC_Setup.exe"))
        shutil.copy2(str(setup_exe), str(web_public / "FileExchangeSetup.exe"))
        shutil.copy2(str(setup_exe), str(web_public / "FileExchange_Latest.exe"))
        print(f"✅ تم تحديث كافة ملفات التحميل في منصة الويب بنجاح: {web_public}")

    local_install = Path(r"C:\Users\tohiba\OneDrive\Desktop\ShareCOC")
    if local_install.exists():
        try:
            shutil.copy2(str(app_exe), str(local_install / "share coc.exe"))
            shutil.copy2(str(setup_exe), str(local_install / "ShareCOC_Setup.exe"))
            print(f"✅ تم تحديث ملفات التطبيق المثبت على سطح المكتب: {local_install}")
        except Exception as e:
            print(f"⚠️ تعذر التحديث المباشر لمجلد التثبيت (قد يكون التطبيق قيد التشغيل): {e}")

    size_mb = round(setup_exe.stat().st_size / (1024 * 1024), 2)
    print("=" * 65)
    print("✅ اكتمل بناء التطبيق ومعالج التثبيت الرسمي بنجاح!")
    print(f"• التطبيق التنفيذي: {app_exe}")
    print(f"• معالج التثبيت الرسمي: {setup_exe} ({size_mb} ميجابايت)")
    print("=" * 65)

if __name__ == "__main__":
    build_exe()
