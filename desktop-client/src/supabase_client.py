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
        import re
        clean = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(filename)).strip()
        ext = Path(clean).suffix.lower()
        b64 = base64.urlsafe_b64encode(clean.encode('utf-8')).decode('ascii').rstrip('=')
        return f"shared/{b64}{ext}"

    def get_file_by_name(self, file_name):
        """البحث عن ملف في السحابة بالاسم المجرد بغض النظر عن محارف الاتجاه"""
        import re
        clean = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(file_name)).strip().lower()
        try:
            files = self.list_accessible_files()
            for f in files:
                f_clean = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(f.get('file_name', ''))).strip().lower()
                if f_clean == clean:
                    return f
        except Exception:
            pass
        return None

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
        """جلب قائمة الملفات الرسمية المسجلة في السحابة مع الحفاظ الكامل على الأسماء العربية الأصلية ومنع تحولها إلى رموز إنجليزية"""
        if not self.is_configured():
            return []
        try:
            url = f"{self.supabase_url}/rest/v1/files?is_deleted=eq.false&select=*"
            res = requests.get(url, headers=self.headers, timeout=6)
            if res.status_code == 200 and isinstance(res.json(), list):
                clean_files = []
                for r in res.json():
                    fn = r.get("file_name", "")
                    # حماية: استبعاد أي سجلات مشوهة بـ Base64 لكي لا تظهر أسماء إنجليزية مشفرة غريبة
                    if fn.endswith(('.docx', '.xlsx', '.pdf', '.accdb')) and len(fn) > 35 and (' ' not in fn) and (fn.startswith('2Y') or fn.startswith('VGh') or fn.startswith('TG')):
                        continue
                    clean_files.append(r)
                return clean_files
            return []
        except Exception as e:
            print(f"[Supabase list_accessible_files error]: {e}")
            return []

    def list_deleted_files(self):
        """جلب قائمة الملفات المحذوفة أو الموجودة في سلة المهملات بالسحابة لمزامنة الحذف محلياً"""
        if not self.is_configured():
            return []
        try:
            url = f"{self.supabase_url}/rest/v1/files?is_deleted=eq.true&select=*"
            res = requests.get(url, headers=self.headers, timeout=6)
            if res.status_code == 200 and isinstance(res.json(), list):
                return res.json()
        except Exception as e:
            print(f"[Supabase list_deleted_files error]: {e}")
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

    def download_file(self, file_name, local_dest_path, storage_path=None):
        """تنزيل ملف من Supabase بتجربة عدة مسارات لضمان تنزيل أي ملف من لوحة التحكم أو الهاتف أو التطبيق"""
        import re
        clean_name = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(file_name)).strip()
        candidates = []
        if storage_path:
            clean_sp = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', str(storage_path)).strip()
            candidates.append(clean_sp)
            if not clean_sp.startswith("shared/"):
                candidates.append(f"shared/{clean_sp}")
            candidates.append(str(storage_path))

        candidates.append(self.get_safe_storage_path(clean_name))
        candidates.append(self.get_safe_storage_path(file_name))
        candidates.append(f"shared/{clean_name}")
        candidates.append(f"shared/{file_name}")
        candidates.append(clean_name)
        candidates.append(file_name)

        Path(local_dest_path).parent.mkdir(parents=True, exist_ok=True)
        for dest in candidates:
            if not dest:
                continue
            ok = self.download_file_from_storage(dest, local_dest_path)
            if ok and os.path.exists(local_dest_path) and os.path.getsize(local_dest_path) > 0:
                return True, "تم التنزيل بنجاح"
        return False, "فشل التنزيل من السحابة"

    def download_file_from_storage(self, storage_path, local_dest_path):
        """تنزيل الملف مباشرة من Supabase Storage بدون باسورد مع تشفير المسار للمسافات مع الحفاظ على الفواصل المائلة"""
        if not self.is_configured():
            return False
        try:
            quoted_path = urllib.parse.quote(str(storage_path), safe='/')
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
        return False

    def create_folder(self, folder_name_or_rel_path):
        """إنشاء مجلد في قاعدة بيانات السحابة (shared_folders) وتأكيده في التخزين"""
        if not self.is_configured():
            return False, "غير متصل"
        try:
            folder_clean = folder_name_or_rel_path.replace("\\", "/").strip("/")
            folder_name = os.path.basename(folder_clean)
            if not folder_name:
                return False, "اسم المجلد غير صالح"

            # 1. إدراج في جدول shared_folders
            url = f"{self.supabase_url}/rest/v1/shared_folders"
            payload = {"name": folder_name}
            res = requests.post(url, json=payload, headers={**self.headers, "Prefer": "resolution=merge-duplicates"}, timeout=6)
            
            # 2. إنشاء علامة مجلد في وعاء التخزين
            safe_folder = self.get_safe_storage_path(folder_clean)
            storage_url = f"{self.supabase_url}/storage/v1/object/file-exchange-storage/{safe_folder}/.keep"
            storage_headers = {
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.anon_key}",
                "x-upsert": "true"
            }
            try:
                requests.post(storage_url, data=b"", headers=storage_headers, timeout=5)
            except Exception:
                pass

            self.log_audit("create_folder", "folder", None, folder_name, {"rel_path": folder_clean})
            return True, "تم إنشاء المجلد في السحابة بنجاح"
        except Exception as e:
            print(f"[Supabase create_folder]: {e}")
            return False, str(e)

    def delete_folder(self, folder_name_or_rel_path):
        """حذف مجلد وكافة محتوياته من قاعدة البيانات والتخزين السحابي"""
        if not self.is_configured():
            return True
        try:
            folder_clean = folder_name_or_rel_path.replace("\\", "/").strip("/")
            folder_name = os.path.basename(folder_clean)
            quoted_name = urllib.parse.quote(folder_name)
            quoted_clean = urllib.parse.quote(folder_clean)

            # 1. حذف المجلد من shared_folders
            url_folder = f"{self.supabase_url}/rest/v1/shared_folders?name=eq.{quoted_name}"
            requests.delete(url_folder, headers=self.headers, timeout=6)

            # 2. حذف ملفات المجلد من جدول files
            url_files_path = f"{self.supabase_url}/rest/v1/files?file_path=like.{quoted_clean}%"
            requests.delete(url_files_path, headers=self.headers, timeout=6)

            # 3. حذف من التخزين السحابي
            safe_folder = self.get_safe_storage_path(folder_clean)
            del_url = f"{self.supabase_url}/storage/v1/object/file-exchange-storage"
            prefixes_to_del = [
                f"{safe_folder}/.keep",
                f"shared/{folder_clean}/.emptyFolderPlaceholder",
                f"shared/{folder_name}/.emptyFolderPlaceholder",
                f"shared/{folder_clean}",
                f"shared/{folder_name}"
            ]
            requests.delete(del_url, json={"prefixes": prefixes_to_del}, headers=self.headers, timeout=6)

            self.log_audit("delete_folder", "folder", None, folder_name, {"rel_path": folder_clean})
            return True
        except Exception as e:
            print(f"[Supabase delete_folder]: {e}")
            return False

    def list_folders(self):
        """جلب قائمة المجلدات المشتركة من سحابة Supabase"""
        if not self.is_configured():
            return []
        try:
            url = f"{self.supabase_url}/rest/v1/shared_folders?select=*&order=name.asc"
            res = requests.get(url, headers=self.headers, timeout=6)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            print(f"[Supabase list_folders]: {e}")
        return []

    def delete_file(self, file_name_or_rel_path):
        """حذف ملف من قاعدة بيانات Supabase ووعاء التخزين بشكل شامل"""
        if not self.is_configured():
            return True
        try:
            rel_path = file_name_or_rel_path.replace("\\", "/").strip("/")
            name = os.path.basename(rel_path)
            quoted_name = urllib.parse.quote(name)
            quoted_rel = urllib.parse.quote(rel_path)

            # 1. حذف من قاعدة بيانات files بالاسم والمسار
            url_db1 = f"{self.supabase_url}/rest/v1/files?file_name=eq.{quoted_name}"
            requests.delete(url_db1, headers=self.headers, timeout=6)
            
            if rel_path != name:
                url_db2 = f"{self.supabase_url}/rest/v1/files?file_path=eq.{quoted_rel}"
                requests.delete(url_db2, headers=self.headers, timeout=6)

            # 2. حذف من وعاء التخزين
            safe_dest_name = self.get_safe_storage_path(name)
            safe_dest_rel = self.get_safe_storage_path(rel_path)
            del_url = f"{self.supabase_url}/storage/v1/object/file-exchange-storage"
            prefixes = [
                safe_dest_name,
                safe_dest_rel,
                f"shared/{name}",
                f"shared/{rel_path}"
            ]
            requests.delete(del_url, json={"prefixes": prefixes}, headers=self.headers, timeout=6)
            self.log_audit("delete_file", "file", None, name, {"rel_path": rel_path})
            return True
        except Exception as e:
            print(f"[Supabase delete]: {e}")
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
