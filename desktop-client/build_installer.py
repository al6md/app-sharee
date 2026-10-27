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

    print("[3/3] تحديث نسخة التحميل المباشر في لوحة الويب (web-dashboard/public/ShareCOC_Setup.exe)...")
    web_public_setup = current_dir.parent / "web-dashboard" / "public" / "ShareCOC_Setup.exe"
    if web_public_setup.parent.exists():
        shutil.copy2(str(setup_exe), str(web_public_setup))
        print(f"✅ تم تحديث ملف التحميل في منصة الويب: {web_public_setup}")

    size_mb = round(setup_exe.stat().st_size / (1024 * 1024), 2)
    print("=" * 65)
    print("✅ اكتمل بناء التطبيق ومعالج التثبيت الرسمي بنجاح!")
    print(f"• التطبيق التنفيذي: {app_exe}")
    print(f"• معالج التثبيت الرسمي: {setup_exe} ({size_mb} ميجابايت)")
    print("=" * 65)

if __name__ == "__main__":
    build_exe()
