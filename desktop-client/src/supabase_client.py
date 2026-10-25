"""
تبادل الملفات – File Exchange System
عميل الاتصال بالسحابة (Supabase Client - REST, Storage & Realtime)
"""
import os
import requests
import hashlib
from datetime import datetime
from pathlib import Path

class SupabaseClient:
    def __init__(self, supabase_url, supabase_anon_key):
        self.supabase_url = (supabase_url or '').rstrip('/')
        self.anon_key = supabase_anon_key or ''
        self.access_token = None
        self.user_id = None
        self.user_email = None
        self.user_role = None
        self.headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json"
        }

    def is_configured(self):
        """التحقق من صحة رابط الخادم والمفتاح وعدم كونه قيمة افتراضية وهمية"""
        if not self.supabase_url or not self.anon_key:
            return False
        if "placeholder" in self.supabase_url or "xyzcompany" in self.supabase_url or "xyz.supabase.co" in self.supabase_url:
            return False
        return True

    def sign_in(self, email, password):
        """تسجيل دخول المستخدم للحصول على JWT Token"""
        if not self.is_configured():
            return False, "عنوان الخادم السحابي غير مهيأ بعد أو يحتوي على قيمة افتراضية."
        
        try:
            url = f"{self.supabase_url}/auth/v1/token?grant_type=password"
            payload = {"email": email, "password": password}
            res = requests.post(url, json=payload, headers=self.headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                self.access_token = data.get("access_token")
                self.user_id = data.get("user", {}).get("id")
                self.user_email = email
                self.headers["Authorization"] = f"Bearer {self.access_token}"
                
                self._load_user_profile()
                return True, "تم تسجيل الدخول بنجاح"
            else:
                error = res.json().get("error_description", res.text)
                return False, f"فشل تسجيل الدخول: {error}"
        except Exception as e:
            return False, f"تعذر الاتصال بالخادم السحابي: {str(e)}"

    def _load_user_profile(self):
        try:
            url = f"{self.supabase_url}/rest/v1/profiles?id=eq.{self.user_id}&select=*"
            res = requests.get(url, headers=self.headers, timeout=5)
            if res.status_code == 200 and res.json():
                self.user_role = res.json()[0].get("role", "user")
        except Exception:
            self.user_role = "user"

    def register_or_verify_device(self, device_name, machine_guid, os_info="Windows"):
        """تسجيل الجهاز أو التحقق من اعتماده من قبل الإدارة"""
        if not self.is_configured() or not self.access_token:
            return False, None

        try:
            check_url = f"{self.supabase_url}/rest/v1/devices?machine_guid=eq.{machine_guid}&select=*"
            res = requests.get(check_url, headers=self.headers, timeout=6)
            if res.status_code == 200 and res.json():
                device = res.json()[0]
                update_url = f"{self.supabase_url}/rest/v1/devices?id=eq.{device['id']}"
                requests.patch(update_url, json={"last_seen_at": datetime.utcnow().isoformat()}, headers=self.headers, timeout=5)
                return True, device
            else:
                reg_url = f"{self.supabase_url}/rest/v1/devices"
                payload = {
                    "user_id": self.user_id,
                    "device_name": device_name,
                    "machine_guid": machine_guid,
                    "os_info": os_info,
                    "is_authorized": False
                }
                reg_res = requests.post(reg_url, json=payload, headers={**self.headers, "Prefer": "return=representation"}, timeout=6)
                if reg_res.status_code in [200, 201]:
                    return False, reg_res.json()[0]
        except Exception as e:
            print(f"[تسجيل الجهاز]: {e}")
        return False, None

    def list_accessible_files(self):
        """جلب قائمة الملفات المصرح بها للمستخدم من السحابة"""
        if not self.is_configured() or not self.access_token:
            return []
        try:
            url = f"{self.supabase_url}/rest/v1/files?is_deleted=eq.false&select=*,shared_folders(name),profiles(full_name)"
            res = requests.get(url, headers=self.headers, timeout=6)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            print(f"[جلب الملفات من السحابة]: {e}")
        return []

    def check_file_lock(self, file_id_or_name):
        """فحص ما إذا كان الملف مقفولاً من جهاز آخر (مثل قاعدة بيانات Access)"""
        if not self.is_configured() or not self.access_token:
            return False, None
        try:
            url = f"{self.supabase_url}/rest/v1/file_locks?file_id=eq.{file_id_or_name}&select=*,profiles(full_name),devices(device_name)"
            res = requests.get(url, headers=self.headers, timeout=3)
            if res.status_code == 200 and res.json():
                return True, res.json()[0]
        except Exception as e:
            print(f"[فحص القفل]: تخطي الفحص بسبب تعذر الاتصال ({e})")
        return False, None

    def acquire_file_lock(self, file_id, device_id):
        """حجز القفل الحصري للملف"""
        if not self.is_configured() or not self.access_token:
            return True # فتح محلي إذا لم تكن السحابة مهيأة
        try:
            url = f"{self.supabase_url}/rest/v1/file_locks"
            payload = {
                "file_id": file_id,
                "locked_by": self.user_id,
                "device_id": device_id,
                "lock_type": "exclusive"
            }
            res = requests.post(url, json=payload, headers=self.headers, timeout=5)
            return res.status_code in [200, 201]
        except Exception:
            return True

    def release_file_lock(self, file_id, device_id):
        """تحرير القفل بعد الانتهاء من التعديل"""
        if not self.is_configured() or not self.access_token:
            return True
        try:
            url = f"{self.supabase_url}/rest/v1/file_locks?file_id=eq.{file_id}&device_id=eq.{device_id}"
            res = requests.delete(url, headers=self.headers, timeout=5)
            return res.status_code in [200, 204]
        except Exception:
            return True

    def upload_file_to_storage(self, local_path, storage_dest_path):
        """رفع الملف مباشرة إلى Supabase Storage"""
        if not self.is_configured() or not self.access_token:
            return False
        try:
            url = f"{self.supabase_url}/storage/v1/object/file-exchange-storage/{storage_dest_path}"
            headers = {
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.access_token}",
                "x-upsert": "true"
            }
            with open(local_path, "rb") as f:
                res = requests.post(url, data=f, headers=headers, timeout=60)
            return res.status_code in [200, 201]
        except Exception as e:
            print(f"[خطأ رفع الملف]: {e}")
            return False

    def download_file_from_storage(self, storage_path, local_dest_path):
        """تنزيل الملف من السحابة"""
        if not self.is_configured() or not self.access_token:
            return False
        try:
            url = f"{self.supabase_url}/storage/v1/object/authenticated/file-exchange-storage/{storage_path}"
            headers = {
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.access_token}"
            }
            res = requests.get(url, headers=headers, stream=True, timeout=60)
            if res.status_code == 200:
                Path(local_dest_path).parent.mkdir(parents=True, exist_ok=True)
                with open(local_dest_path, "wb") as f:
                    for chunk in res.iter_content(chunk_size=65536):
                        f.write(chunk)
                return True
        except Exception as e:
            print(f"[خطأ تنزيل الملف]: {e}")
        return False

    def log_audit(self, action, entity_type, entity_id, entity_name, details=None, device_id=None):
        """تسجيل العملية في سجل التدقيق"""
        if not self.is_configured() or not self.access_token:
            return
        try:
            url = f"{self.supabase_url}/rest/v1/audit_logs"
            payload = {
                "user_id": self.user_id,
                "device_id": device_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "entity_name": entity_name,
                "details": details or {}
            }
            requests.post(url, json=payload, headers=self.headers, timeout=4)
        except Exception:
            pass
