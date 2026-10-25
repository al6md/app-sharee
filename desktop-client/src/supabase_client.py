"""
تبادل الملفات – File Exchange System
عميل الاتصال بالسحابة (Supabase Client - REST, Storage & Realtime)
يعمل بالكامل بدون كلمة مرور مع دعم كامل للأسماء العربية والمسافات
"""
import os
import requests
import hashlib
import base64
import urllib.parse
from datetime import datetime
from pathlib import Path

class SupabaseClient:
    def __init__(self, supabase_url, supabase_anon_key):
        self.supabase_url = (supabase_url or '').rstrip('/')
        self.anon_key = (supabase_anon_key or '').strip()
        self.access_token = self.anon_key
        self.user_id = "00000000-0000-0000-0000-000000000000"
        self.user_email = "shared-office@local"
        self.user_role = "admin"
        self.headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json"
        }

    def is_configured(self):
        """التحقق من صحة رابط الخادم والمفتاح وعدم كونه قيمة افتراضية وهمية"""
        if not self.supabase_url or not self.anon_key:
            return False
        if "placeholder" in self.supabase_url or "xyzcompany" in self.supabase_url or "xyz.supabase.co" in self.supabase_url:
            return False
        return True

    @staticmethod
    def get_safe_storage_path(filename):
        """توليد مسار تخزين آمن 100% متوافق مع S3 للأسماء العربية والمسافات"""
        ext = Path(filename).suffix.lower()
        b64 = base64.urlsafe_b64encode(filename.encode('utf-8')).decode('ascii').rstrip('=')
        return f"shared/{b64}{ext}"

    def register_or_verify_device(self, device_name, machine_guid, os_info="Windows"):
        """تسجيل الجهاز تلقائياً بدون طلب أي باسورد"""
        if not self.is_configured():
            return True, {"device_name": device_name, "is_authorized": True}

        try:
            quoted_guid = urllib.parse.quote(str(machine_guid))
            check_url = f"{self.supabase_url}/rest/v1/devices?machine_guid=eq.{quoted_guid}&select=*"
            res = requests.get(check_url, headers=self.headers, timeout=5)
            if res.status_code == 200 and res.json():
                device = res.json()[0]
                update_url = f"{self.supabase_url}/rest/v1/devices?id=eq.{device['id']}"
                requests.patch(update_url, json={"last_seen_at": datetime.utcnow().isoformat()}, headers=self.headers, timeout=5)
                return True, device
            else:
                reg_url = f"{self.supabase_url}/rest/v1/devices"
                payload = {
                    "device_name": device_name,
                    "machine_guid": machine_guid,
                    "os_info": os_info,
                    "is_authorized": True
                }
                reg_res = requests.post(reg_url, json=payload, headers={**self.headers, "Prefer": "return=representation"}, timeout=5)
                if reg_res.status_code in [200, 201]:
                    return True, reg_res.json()[0]
        except Exception as e:
            print(f"[Device register]: {e}")
        return True, {"device_name": device_name, "is_authorized": True}

    def list_files(self):
        """قائمة الملفات في السحابة المتوافقة مع محرك المزامنة"""
        return self.list_accessible_files()

    def list_accessible_files(self):
        """جلب قائمة الملفات من السحابة بدمج سجلات قاعدة البيانات مع وعاء التخزين الفعلي"""
        if not self.is_configured():
            return []
        try:
            db_by_storage = {}
            db_by_name = {}
            url = f"{self.supabase_url}/rest/v1/files?is_deleted=eq.false&select=*"
            res = requests.get(url, headers=self.headers, timeout=6)
            if res.status_code == 200 and isinstance(res.json(), list):
                for r in res.json():
                    if r.get("storage_path"):
                        db_by_storage[r["storage_path"]] = r
                    if r.get("file_name"):
                        db_by_name[r["file_name"]] = r

            storage_url = f"{self.supabase_url}/storage/v1/object/list/file-exchange-storage"
            list_res = requests.post(storage_url, json={"prefix": "shared", "limit": 100}, headers=self.headers, timeout=6)
            
            merged = []
            seen_names = set()

            if list_res.status_code == 200 and isinstance(list_res.json(), list):
                for obj in list_res.json():
                    raw_name = obj.get("name", "")
                    if not raw_name or raw_name == ".emptyFolderPlaceholder":
                        continue
                    storage_path = f"shared/{raw_name}"

                    if storage_path in db_by_storage:
                        item = dict(db_by_storage[storage_path])
                    elif raw_name in db_by_name:
                        item = dict(db_by_name[raw_name])
                    else:
                        item = {
                            "file_name": raw_name,
                            "file_path": raw_name,
                            "storage_path": storage_path,
                            "file_size": obj.get("metadata", {}).get("size", 0),
                            "updated_at": obj.get("updated_at", "")
                        }
                    
                    if item["file_name"] not in seen_names:
                        seen_names.add(item["file_name"])
                        merged.append(item)

            for f_name, db_item in db_by_name.items():
                if f_name not in seen_names:
                    seen_names.add(f_name)
                    merged.append(db_item)

            return merged
        except Exception:
            return []

    def check_file_lock(self, file_id_or_name):
        """فحص ما إذا كان الملف مقفولاً من جهاز آخر (خاصة ملفات Access)"""
        if not self.is_configured():
            return False, None
        try:
            quoted_id = urllib.parse.quote(str(file_id_or_name))
            url = f"{self.supabase_url}/rest/v1/file_locks?file_id=eq.{quoted_id}&select=*"
            res = requests.get(url, headers=self.headers, timeout=4)
            if res.status_code == 200 and res.json():
                return True, res.json()[0]
        except Exception as e:
            print(f"[Supabase check lock]: {e}")
        return False, None

    def acquire_file_lock(self, file_id, device_id, device_name=None):
        """حجز القفل الحصري للملف"""
        if not self.is_configured():
            return True
        try:
            url = f"{self.supabase_url}/rest/v1/file_locks"
            payload = {
                "file_id": str(file_id),
                "locked_by_name": "مستخدم في الشبكة",
                "device_name": device_name or os.environ.get('COMPUTERNAME', 'جهاز ويندوز'),
                "lock_type": "exclusive"
            }
            res = requests.post(url, json=payload, headers={**self.headers, "Prefer": "resolution=merge-duplicates"}, timeout=5)
            return res.status_code in [200, 201]
        except Exception:
            return True

    def release_file_lock(self, file_id, device_id=None):
        """تحرير القفل فور إغلاق الملف"""
        if not self.is_configured():
            return True
        try:
            quoted_id = urllib.parse.quote(str(file_id))
            url = f"{self.supabase_url}/rest/v1/file_locks?file_id=eq.{quoted_id}"
            res = requests.delete(url, headers=self.headers, timeout=5)
            return res.status_code in [200, 204]
        except Exception:
            return True

    def upload_file(self, local_path, file_name=None, user_name="المستخدم", device_name="جهاز"):
        """رفع ملف إلى Supabase Storage وتسجيل بياناته في الجدول بدعم كامل للغة العربية"""
        name = file_name or os.path.basename(local_path)
        dest = self.get_safe_storage_path(name)
        ok = self.upload_file_to_storage(local_path, dest)
        if ok:
            try:
                size = os.path.getsize(local_path)
                sha = hashlib.sha256()
                with open(local_path, "rb") as f:
                    while chunk := f.read(65536):
                        sha.update(chunk)
                file_hash = sha.hexdigest()

                upsert_url = f"{self.supabase_url}/rest/v1/files"
                payload = {
                    "file_name": name,
                    "file_path": name,
                    "file_size": size,
                    "sha256_hash": file_hash,
                    "storage_path": dest,
                    "last_modified_by_name": user_name,
                    "updated_at": datetime.utcnow().isoformat()
                }
                res = requests.post(
                    upsert_url, 
                    json=payload, 
                    headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                    timeout=5
                )
            except Exception as e:
                pass
            return True, "تم الرفع بنجاح"
        return False, "فشل رفع الملف"

    def upload_file_to_storage(self, local_path, storage_dest_path):
        """رفع الملف مباشرة إلى Supabase Storage بدون باسورد"""
        if not self.is_configured():
            return False
        try:
            url = f"{self.supabase_url}/storage/v1/object/file-exchange-storage/{storage_dest_path}"
            headers = {
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.anon_key}",
                "x-upsert": "true"
            }
            with open(local_path, "rb") as f:
                res = requests.post(url, data=f, headers=headers, timeout=60)
            return res.status_code in [200, 201]
        except Exception:
            return False

    def download_file(self, file_name, local_dest_path):
        """تنزيل ملف من Supabase"""
        dest = self.get_safe_storage_path(file_name)
        ok = self.download_file_from_storage(dest, local_dest_path)
        return ok, "تم التنزيل" if ok else "فشل التنزيل"

    def download_file_from_storage(self, storage_path, local_dest_path):
        """تنزيل الملف مباشرة من Supabase Storage بدون باسورد مع تشفير المسار للمسافات"""
        if not self.is_configured():
            return False
        try:
            quoted_path = urllib.parse.quote(storage_path)
            # 1. عبر الرابط العام للوعاء (Public Bucket)
            public_url = f"{self.supabase_url}/storage/v1/object/public/file-exchange-storage/{quoted_path}"
            res = requests.get(public_url, stream=True, timeout=60)
            
            if res.status_code != 200:
                # 2. عبر الرابط الموثق بالمفتاح العام
                auth_url = f"{self.supabase_url}/storage/v1/object/authenticated/file-exchange-storage/{quoted_path}"
                res = requests.get(auth_url, headers=self.headers, stream=True, timeout=60)

            if res.status_code == 200:
                Path(local_dest_path).parent.mkdir(parents=True, exist_ok=True)
                with open(local_dest_path, "wb") as f:
                    for chunk in res.iter_content(chunk_size=65536):
                        f.write(chunk)
                return True
        except Exception:
            return False

    def log_audit(self, action, entity_type, entity_id, entity_name, details=None, device_id=None):
        """تسجيل العملية في سجل التدقيق"""
        if not self.is_configured():
            return
        try:
            url = f"{self.supabase_url}/rest/v1/audit_logs"
            payload = {
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "entity_name": entity_name,
                "details": details or {}
            }
            requests.post(url, json=payload, headers=self.headers, timeout=4)
        except Exception:
            pass
