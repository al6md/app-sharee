"""
محاكي الجهاز الثاني (Simulate Second PC)
يقوم هذا السكريبت بتمثيل جهاز كمبيوتر ثانٍ في المكتب اسمه 'جهاز-المحاسبة-2'
لاختبار المزامنة الحية والقفل التلقائي لقواعد بيانات Access
"""
import time
import requests
import os
import sys
from pathlib import Path

# إضافة مسار الكود
sys.path.append(str(Path(__file__).parent / "src"))
from supabase_client import SupabaseClient

def run_simulation():
    url = "https://bjcillpivgcntzbwmpsm.supabase.co"
    key = "sb_publishable_Bfk1klLDNsLWKHvdRhWqNg_XoDqqJ6X"
    client = SupabaseClient(url, key)

    print("==================================================")
    print("🚀 بدء محاكاة (جهاز كمبيوتر ثانٍ: محاسبة-جهاز-2)")
    print("==================================================")

    # 1. إرسال ملف جديد من الجهاز الثاني إلى السحابة
    test_filename = "تقرير_مبيعات_جهاز_المحاسبة_2.xlsx"
    temp_file = Path(__file__).parent / "temp_pc2_test.xlsx"
    temp_file.write_bytes(b"PK\x03\x04\x14\x00\x06\x00Mock Excel Content From PC 2")

    print(f"\n1️⃣ الجهاز الثاني يقوم الآن برفع ملف جديد للسحابة: [{test_filename}]...")
    ok, msg = client.upload_file(str(temp_file), file_name=test_filename, user_name="أحمد (المحاسب)", device_name="محاسبة-جهاز-2")
    if ok:
        print("   ✅ تم رفع الملف للسحابة بنجاح! راقب برنامجك المفتوح الآن، سينزل الملف وتراه في القائمة خلال ثوانٍ.")
    else:
        print(f"   ❌ فشل الرفع: {msg}")

    # 2. تجربة حجز وقفل قاعدة بيانات Access
    print("\n2️⃣ الآن، الجهاز الثاني يفتح قاعدة بيانات [Database1.accdb] للعمل عليها...")
    client.acquire_file_lock("Database1.accdb", "device-pc-2-uuid", device_name="محاسبة-جهاز-2")
    print("   🔒 تم تفعيل القفل الحصري في السحابة!")
    print("   👉 جرب الآن في برنامجك: اضغط تحديث 🔄 أو جرب فتح Database1.accdb لتشاهد رسالة الحماية والتأمين!")
    
    print("\n⏳ سنبقي الملف محجوزاً لمدة 15 ثانية لاختباره...")
    for i in range(15, 0, -1):
        print(f"   متبقي {i} ثوانٍ على تحرير الملف...", end="\r")
        time.sleep(1)

    # 3. تحرير القفل
    print("\n\n3️⃣ الجهاز الثاني أغلق الملف الآن وقام بتحريره...")
    client.release_file_lock("Database1.accdb", "device-pc-2-uuid")
    print("   🔓 تم تحرير القفل بنجاح! أصبحت قاعدة البيانات متاحة للجميع مجدداً.")
    print("==================================================")
    print("🎉 انتهت تجربة المحاكاة بنجاح!")

    if temp_file.exists():
        temp_file.unlink()

if __name__ == "__main__":
    run_simulation()
