"""
تبادل الملفات – File Exchange System
سكريبت أتمتة بناء ملف التثبيت FileExchangeSetup.exe
"""
import os
import sys
import subprocess
from pathlib import Path

def build_exe():
    print("=" * 60)
    print("بدء بناء وتجميع تطبيق FileExchangeSetup.exe لنظام Windows")
    print("=" * 60)

    current_dir = Path(__file__).parent.resolve()
    os.chdir(current_dir)

    # التحقق من تثبيت المتطلبات
    print("[1/3] التحقق من حزم Python وتثبيتها...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

    # تشغيل PyInstaller لبناء الملف التنفيذي المستقل
    print("[2/3] تجميع الكود المصدري وإنتاج FileExchangeSetup.exe...")
    spec_file = current_dir / "FileExchange.spec"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "-y", str(spec_file)], check=True)

    dist_exe = current_dir / "dist" / "FileExchangeSetup.exe"
    if dist_exe.exists():
        size_mb = round(dist_exe.stat().st_size / (1024 * 1024), 2)
        print("=" * 60)
        print(f"✅ تم بناء ملف التثبيت بنجاح!")
        print(f"المسار: {dist_exe}")
        print(f"الحجم: {size_mb} ميجابايت")
        print("جاهز للتثبيت والتشغيل على كافة أجهزة المؤسسة العشرة.")
        print("=" * 60)
    else:
        print("❌ فشل العثور على الملف التنفيذي في مجلد dist.")

if __name__ == "__main__":
    build_exe()
