"""
تبادل الملفات – File Exchange System
إدارة التعارضات ومنع الكتابة فوق تعديلات المستخدمين (Conflict Manager)
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

class ConflictManager:
    @staticmethod
    def generate_conflict_filepath(original_path, device_name="جهاز محلي", username="مستخدم"):
        """
        توليد مسار فريد لنسخة التعارض يحافظ على الملفين دون فقدان أي بيانات
        مثال: تقرير_شهري - (تعارض من جهاز المحاسبة بواسطة أحمد 2026-10-24 15-30).docx
        """
        path = Path(original_path)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        conflict_filename = f"{path.stem} - (تعارض من {device_name} بواسطة {username} {timestamp}){path.suffix}"
        return path.parent / conflict_filename

    @staticmethod
    def preserve_conflict_copy(original_path, device_name, username):
        """
        نسخ الملف المحلي المتعارض إلى ملف تعارض مستقل قبل تنزيل النسخة الجديدة
        """
        if not os.path.exists(original_path):
            return None

        conflict_path = ConflictManager.generate_conflict_filepath(original_path, device_name, username)
        try:
            shutil.copy2(original_path, conflict_path)
            print(f"[تعارض تم احتواؤه] تم حفظ نسخة التعارض المحلية في: {conflict_path.name}")
            return str(conflict_path)
        except Exception as e:
            print(f"[خطأ في حفظ التعارض]: {e}")
            return None
