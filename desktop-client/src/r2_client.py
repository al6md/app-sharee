"""
تبادل الملفات – File Exchange System
عميل Cloudflare R2 السحابي (Cloudflare R2 S3-Compatible Cloud Storage Client)
مساحة تخزين 10 جيجابايت مجانية + نقل بيانات (Egress) غير محدود ومجاني 100%
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger("R2Client")
logging.basicConfig(level=logging.INFO)

class CloudflareR2Client:
    def __init__(self, account_id=None, access_key_id=None, secret_access_key=None, bucket_name="file-exchange-storage"):
        self.account_id = account_id or os.environ.get("R2_ACCOUNT_ID", "")
        self.access_key_id = access_key_id or os.environ.get("R2_ACCESS_KEY_ID", "")
        self.secret_access_key = secret_access_key or os.environ.get("R2_SECRET_ACCESS_KEY", "")
        self.bucket_name = bucket_name or os.environ.get("R2_BUCKET_NAME", "file-exchange-storage")
        
        self.s3_client = None
        if self.is_configured():
            self._init_s3()

    def is_configured(self):
        return bool(self.account_id and self.access_key_id and self.secret_access_key and self.bucket_name)

    def _init_s3(self):
        try:
            endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name="auto",
                config=Config(
                    signature_version="s3v4",
                    retries={'max_attempts': 3, 'mode': 'standard'}
                )
            )
            logger.info("تم الاتصال بسحابة Cloudflare R2 بنجاح.")
        except Exception as e:
            logger.error(f"خطأ في تهيئة عميل Cloudflare R2: {e}")
            self.s3_client = None

    def ensure_bucket_exists(self):
        """التحقق من وجود وعاء التخزين في Cloudflare R2 وإنشاؤه إن لم يوجد"""
        if not self.s3_client:
            return False, "العميل غير مهيأ"
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True, "الوعاء متوفر وجاهز"
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code in ['404', 'NoSuchBucket']:
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    return True, "تم إنشاء الوعاء بنجاح"
                except Exception as create_err:
                    return False, str(create_err)
            return False, str(e)

    def upload_file(self, file_path, file_name=None, user_name="المستخدم", device_name="جهاز-ويندوز"):
        """رفع ملف إلى Cloudflare R2 مع حفظ الميتاداتا وسجل التعديل"""
        if not self.s3_client:
            return False, "Cloudflare R2 غير متصل"

        path = Path(file_path)
        if not path.exists():
            return False, f"الملف المحلي غير موجود: {file_path}"

        target_name = file_name or path.name
        s3_key = f"files/{target_name}"
        meta_key = f"metadata/{target_name}.json"

        try:
            # 1. رفع الملف الثنائي إلى R2
            with open(path, "rb") as f:
                self.s3_client.upload_fileobj(
                    f, 
                    self.bucket_name, 
                    s3_key,
                    ExtraArgs={'Metadata': {'filename': target_name, 'user': user_name}}
                )

            # 2. رفع ملف الميتاداتا
            meta_data = {
                "file_name": target_name,
                "file_size": path.stat().st_size,
                "last_modified": datetime.now().isoformat(),
                "modified_by": user_name,
                "device_name": device_name
            }
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=meta_key,
                Body=json.dumps(meta_data, ensure_ascii=False),
                ContentType="application/json"
            )

            logger.info(f"تم رفع {target_name} إلى Cloudflare R2 بنجاح.")
            return True, "تم الرفع السحابي بنجاح"
        except Exception as e:
            logger.error(f"فشل رفع الملف إلى Cloudflare R2: {e}")
            return False, str(e)

    def download_file(self, file_name, dest_path):
        """تنزيل ملف من Cloudflare R2 إلى المجلد المحلي"""
        if not self.s3_client:
            return False, "Cloudflare R2 غير متصل"

        s3_key = f"files/{file_name}"
        try:
            dest = Path(dest_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                self.s3_client.download_fileobj(self.bucket_name, s3_key, f)
            return True, "تم التنزيل بنجاح"
        except Exception as e:
            return False, str(e)

    def list_files(self):
        """استرجاع قائمة كافة الملفات والمستندات الموجودة على Cloudflare R2"""
        if not self.s3_client:
            return []

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="files/"
            )
            files = []
            for item in response.get("Contents", []):
                key = item["Key"]
                if key == "files/":
                    continue
                name = key.replace("files/", "")
                size = item["Size"]
                last_mod = item["LastModified"].isoformat()

                files.append({
                    "file_name": name,
                    "file_size": size,
                    "last_modified_cloud": last_mod,
                    "storage_engine": "Cloudflare R2"
                })
            return files
        except Exception as e:
            logger.error(f"خطأ في سرد ملفات R2: {e}")
            return []

    def check_file_lock(self, file_name):
        """فحص حالة قفل ملف قاعدة بيانات Access"""
        if not self.s3_client:
            return False, {}

        lock_key = f"locks/{file_name}.lock"
        try:
            obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=lock_key)
            data = json.loads(obj["Body"].read().decode("utf-8"))
            return True, data
        except ClientError as e:
            # إذا كان الخطأ NoSuchKey فالملف غير محجوز
            return False, {}
        except Exception:
            return False, {}

    def acquire_file_lock(self, file_name, user_id, user_name, device_name):
        """حجز قفل أمان حصري لقاعدة بيانات Access لمنع التلف"""
        if not self.s3_client:
            return False, "غير متصل"

        is_locked, info = self.check_file_lock(file_name)
        if is_locked and info.get("locked_by") != user_id:
            return False, f"محجوز بواسطة {info.get('user_name', 'مستخدم آخر')}"

        lock_key = f"locks/{file_name}.lock"
        data = {
            "file_name": file_name,
            "locked_by": user_id,
            "user_name": user_name,
            "device_name": device_name,
            "locked_at": datetime.now().isoformat()
        }
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=lock_key,
                Body=json.dumps(data, ensure_ascii=False),
                ContentType="application/json"
            )
            return True, "تم حجز الملف بنجاح"
        except Exception as e:
            return False, str(e)

    def release_file_lock(self, file_name, user_id):
        """فك حجز قفل أمان قاعدة بيانات Access"""
        if not self.s3_client:
            return False, "غير متصل"

        lock_key = f"locks/{file_name}.lock"
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=lock_key)
            return True, "تم فك الحجز بنجاح"
        except Exception as e:
            return False, str(e)

    def upload_installer(self, exe_path):
        """رفع برنامج FileExchangeSetup.exe إلى R2 ليكون متاحاً للتحميل المباشر للجميع"""
        if not self.s3_client:
            return False, "غير متصل"

        try:
            with open(exe_path, "rb") as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    "installers/FileExchangeSetup.exe",
                    ExtraArgs={'ContentType': 'application/vnd.microsoft.portable-executable'}
                )
            logger.info("تم رفع برنامج التثبيت FileExchangeSetup.exe إلى Cloudflare R2.")
            return True, "تم رفع برنامج التثبيت بنجاح"
        except Exception as e:
            return False, str(e)

    def delete_file(self, file_name_or_rel_path):
        """حذف ملف وميتاداتا الملف من Cloudflare R2"""
        if not self.s3_client:
            return False, "Cloudflare R2 غير متصل"
        clean = file_name_or_rel_path.replace("\\", "/").strip("/")
        name = os.path.basename(clean)
        try:
            keys_to_del = [
                {"Key": f"files/{clean}"},
                {"Key": f"files/{name}"},
                {"Key": f"metadata/{clean}.json"},
                {"Key": f"metadata/{name}.json"}
            ]
            self.s3_client.delete_objects(
                Bucket=self.bucket_name,
                Delete={"Objects": keys_to_del, "Quiet": True}
            )
            return True, "تم حذف الملف من R2"
        except Exception as e:
            logger.error(f"خطأ في حذف ملف من R2: {e}")
            return False, str(e)

    def create_folder(self, folder_name_or_rel_path):
        """إنشاء مجلد في Cloudflare R2 عبر وضع علامة .keep"""
        if not self.s3_client:
            return False, "غير متصل"
        clean = folder_name_or_rel_path.replace("\\", "/").strip("/")
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"files/{clean}/.keep",
                Body=b"",
                ContentType="application/octet-stream"
            )
            return True, "تم إنشاء المجلد في R2"
        except Exception as e:
            logger.error(f"خطأ في إنشاء مجلد في R2: {e}")
            return False, str(e)

    def delete_folder(self, folder_name_or_rel_path):
        """حذف مجلد وكافة محتوياته من Cloudflare R2"""
        if not self.s3_client:
            return False, "غير متصل"
        clean = folder_name_or_rel_path.replace("\\", "/").strip("/")
        prefix = f"files/{clean}/"
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            objects = response.get("Contents", [])
            if objects:
                delete_keys = [{"Key": obj["Key"]} for obj in objects]
                self.s3_client.delete_objects(Bucket=self.bucket_name, Delete={"Objects": delete_keys, "Quiet": True})
            return True, "تم حذف المجلد من R2"
        except Exception as e:
            logger.error(f"خطأ في حذف مجلد من R2: {e}")
            return False, str(e)
