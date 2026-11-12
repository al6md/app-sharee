# -*- coding: utf-8 -*-
"""
غرفة تجارة كربلاء المقدسة – منظومة Share COC
مركز قواعد بيانات Access الموحد (Access Data Hub Desktop Widget)
يدعم الدمج الشامل، الخانات الحقيقية، الترتيب الأصلي الدقيق 100% للحقول،
الفرز الزمني (من الجديد إلى القديم والعكس)، إضافة وحذف الحقول ديناميكياً، والـ CRUD الكامل مع المزامنة السحابية.
"""

import os
import sys
import re
import json
import requests
from pathlib import Path
from datetime import datetime, timezone
import threading
import io

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QButtonGroup, QFrame, QDialog, QMessageBox, QFileDialog,
    QScrollArea, QAbstractItemView, QProgressDialog, QComboBox,
    QMenu, QApplication, QStackedWidget, QSlider, QLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QCursor, QIcon

CLOUD_API_URL = "https://web-dashboard-pi-self.vercel.app/api/access-hub"
LOCAL_API_URL = "http://localhost:3000/api/access-hub"


def get_desktop_machine_guid():
    """استخراج المعرف الثابت للحاسوب من سجل الويندوز"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        val, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(val).strip()
    except Exception:
        import socket
        return socket.gethostname()

# مسار مجلد البيانات المحلي كنسخة احتياطية سريعة
LOCAL_DATA_DIR = Path(__file__).parent.parent.parent / "web-dashboard" / "data" / "access-hub"

# كاش الذاكرة اللحظي للبيانات - In-Memory Ultra-Fast RAM Cache
_FILE_RAM_CACHE = {}  # path_str -> (mtime, parsed_json_dict)

def get_local_data_dir() -> Path:
    """تحديد المسار المحلي الفعلي لبيانات Access Hub"""
    candidates = [
        Path(sys.executable).parent / "data" / "access-hub",
        Path(r"C:\Users\tohiba\OneDrive\Desktop\ShareCOC\data\access-hub"),
        Path(__file__).resolve().parent.parent.parent / "web-dashboard" / "data" / "access-hub",
        Path(r"c:\Users\tohiba\OneDrive\Desktop\شييييير\web-dashboard\data\access-hub"),
        Path(os.environ.get("APPDATA", "")) / "ShareCOC" / "access-hub",
    ]
    for c in candidates:
        if c.exists() and (c / "index.json").exists():
            return c
    return candidates[0]

def get_cached_json_file(file_path: Path):
    """قراءة وفك ملف الـ JSON بسرعة الرام اللحظية (0 ميلي ثانية) بعد أول قراءة"""
    if not file_path.exists():
        return None
    path_str = str(file_path.resolve())
    try:
        cur_mtime = file_path.stat().st_mtime
    except Exception:
        cur_mtime = 0

    cached = _FILE_RAM_CACHE.get(path_str)
    if cached and cached[0] == cur_mtime:
        return cached[1]

    with open(file_path, "r", encoding="utf-8") as jf:
        data = json.load(jf)
    _FILE_RAM_CACHE[path_str] = (cur_mtime, data)
    return data

def get_all_local_data_dirs() -> list[Path]:
    """إرجاع كافة المسارات المحلية الموجودة لبيانات Access Hub لمزامنتها معاً"""
    candidates = [
        Path(sys.executable).parent / "data" / "access-hub",
        Path(r"C:\Users\tohiba\OneDrive\Desktop\ShareCOC\data\access-hub"),
        Path(__file__).resolve().parent.parent.parent / "web-dashboard" / "data" / "access-hub",
        Path(r"c:\Users\tohiba\OneDrive\Desktop\شييييير\web-dashboard\data\access-hub"),
        Path(os.environ.get("APPDATA", "")) / "ShareCOC" / "access-hub",
    ]
    existing = []
    seen = set()
    for c in candidates:
        try:
            res_p = c.resolve()
            if res_p.exists() and str(res_p) not in seen:
                seen.add(str(res_p))
                existing.append(res_p)
        except Exception:
            pass
    return existing if existing else [candidates[0]]

def load_local_mutations(local_dir=None) -> dict:
    """تحميل سجل الطفرات والتعديلات المخزنة محلياً"""
    if local_dir is None:
        local_dir = get_local_data_dir()
    mut_path = local_dir / "mutations.json"
    default_mut = {"adds": [], "updates": {}, "deletes": [], "added_columns": {}, "deleted_columns": {}, "column_orders": {}, "roles": {}}
    if mut_path.exists():
        data = get_cached_json_file(mut_path)
        if isinstance(data, dict):
            return data
    return default_mut

def save_local_mutations(mutations: dict, local_dir=None):
    """حفظ سجل الطفرات والتعديلات محلياً وتحديث كاش الذاكرة لكافة المجلدات المحلية النشطة"""
    dirs_to_update = get_all_local_data_dirs()
    if local_dir and local_dir not in dirs_to_update:
        dirs_to_update.append(local_dir)

    for d in dirs_to_update:
        try:
            d.mkdir(parents=True, exist_ok=True)
            mp = d / "mutations.json"
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(mutations, f, ensure_ascii=False, indent=2)
            # تحديث كاش الذاكرة الفوري
            path_str = str(mp.resolve())
            try:
                cur_mtime = mp.stat().st_mtime
            except Exception:
                cur_mtime = 0
            _FILE_RAM_CACHE[path_str] = (cur_mtime, mutations)
        except Exception as e:
            print(f"[AccessHub] Error saving mutations to {d}: {e}")

def fetch_cloud_mutations(known_sync_time=None) -> dict | None:
    """جلب سجل التعديلات السحابية الأحدث من Google Drive أو Web API"""
    # 1. المحاولة المباشرة من Google Drive عبر ملف .sharecoc_access_mutations.json
    try:
        from gdrive_client import GoogleDriveClient
        client = GoogleDriveClient()
        if client.is_configured():
            res = client._execute(lambda s: s.files().list(
                q=f"'{client.root_folder_id}' in parents and name = '.sharecoc_access_mutations.json' and trashed = false",
                fields="files(id, name, modifiedTime)",
                pageSize=1
            ))
            files = res.get("files", [])
            if files:
                file_meta = files[0]
                cloud_mod = file_meta.get("modifiedTime")
                # إذا كانت لدينا نفس البصمة الزمنية، لا داعي لإعادة التنزيل
                if known_sync_time and cloud_mod and cloud_mod == known_sync_time:
                    return None

                fid = file_meta["id"]
                from googleapiclient.http import MediaIoBaseDownload
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, client.service.files().get_media(fileId=fid))
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.seek(0)
                content = fh.read().decode("utf-8")
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    if cloud_mod and not parsed.get("last_sync"):
                        parsed["last_sync"] = cloud_mod
                    return parsed
    except Exception as e:
        print(f"[AccessHub] Google Drive fetch warning: {e}")

    # 2. المحاولة الاحتياطية عبر Web Dashboard API
    try:
        r = requests.get(f"{CLOUD_API_URL}?action=mutations", timeout=7)
        if r.status_code == 200:
            data = r.json()
            if data.get("mutations") and isinstance(data["mutations"], dict):
                return data["mutations"]
    except Exception as e:
        print(f"[AccessHub] Cloud API fetch warning: {e}")

    return None

def sync_cloud_mutations_to_local(force=False) -> bool:
    """مزامنة سجل الطفرات السحابية وحفظه في القرص المحلي"""
    try:
        local_dir = get_local_data_dir()
        current_mut = load_local_mutations(local_dir)
        known_time = None if force else current_mut.get("last_sync")
        cloud_mut = fetch_cloud_mutations(known_sync_time=known_time)
        if cloud_mut:
            save_local_mutations(cloud_mut, local_dir)
            return True
    except Exception as e:
        print(f"[AccessHub] Sync error: {e}")
    return False

class CloudSyncWorker(QThread):
    sync_completed = pyqtSignal(bool)

    def __init__(self, force=False):
        super().__init__()
        self.force = force

    def run(self):
        try:
            updated = sync_cloud_mutations_to_local(force=self.force)
            self.sync_completed.emit(updated)
        except Exception as e:
            print(f"[AccessHub Worker] Error: {e}")
            self.sync_completed.emit(False)

DATE_KEYWORDS = ['date', 'تاريخ', 'affiliation', 'expiration', 'year', 'سنة', 'مواليد']

# مصفوفة الأولوية المنطقية لترتيب جداول غرفة التجارة لضمان ظهور التجار والشركات والدلالين أولاً
TABLE_PRIORITY = {
    "التجار": 1,
    "الشركات": 2,
    "الدلالين": 3,
    "دلالين": 3,
    "التعديل": 4,
    "المعامل": 5,
    "الفنادق": 6,
    "المطاعم": 7,
    "المقاهي": 8,
    "الصيدليات": 9,
    "الساحات": 10,
    "الشطب": 11,
}

# المسميات والأيقونات الاحترافية لمنع أي بتر أو تشويه للكلمات عبر كافة الشاشات
TABLE_DISPLAY_META = {
    "all": ("🌟", "جميع الأصناف"),
    "التجار": ("👥", "التجار"),
    "الشركات": ("🏢", "الشركات"),
    "الدلالين": ("🤝", "الدلالين"),
    "دلالين": ("🤝", "الدلالين"),
    "التعديل": ("✏️", "التعديل"),
    "المعامل": ("🏭", "المعامل"),
    "الفنادق": ("🏨", "الفنادق"),
    "المطاعم": ("🍽️", "المطاعم"),
    "المقاهي": ("☕", "المقاهي"),
    "الصيدليات": ("💊", "الصيدليات"),
    "الساحات": ("🚗", "الساحات"),
    "الشطب": ("🚫", "الشطب"),
}

def sort_tables_by_priority(tables):
    """ترتيب الجداول ترتيباً منطقياً معتمداً لغرفة التجارة يبدأ بالتجار ثم الشركات ثم الدلالين"""
    return sorted(tables, key=lambda t: (TABLE_PRIORITY.get(t, 50), t))

COLUMN_PRIORITY = {
    # 1. الأسماء الرئيسية
    'ArabicName': 1,
    'اسم التاجر': 1,
    'اسم الشركة': 1,
    'اسم الفندق': 1,
    'اسم الصيدلية': 1,
    'اسم المعمل': 1,
    'اسم الدلال': 1,
    'الإسم التجاري': 2,
    'الاسم التجاري': 2,
    'ArabicCommercialName': 2,
    'EnglishName': 3,

    # 2. المالك وصاحب المنشأة
    'صاحب الاسم التجاري': 4,
    'اسم صاحب الفندق': 4,
    'اسم صاحب المعمل': 4,
    'اسم صاحب المكتب': 4,
    'اسم صاحب الصيدلية': 4,
    'اسم صاحب الشركة': 4,
    'الإسم': 4,

    # 3. النشاط والعمل
    'العمل': 5,
    'Activity': 5,
    'SpecificActivity': 5,
    'العمل التجاري': 5,
    'نوع النشاط': 5,
    'النشاط': 5,
    'EnglishActivity': 6,

    # 4. الصنف والدرجة
    'الصنف': 7,
    'الدرجة': 7,
    'Class': 7,
    'EnglishClass': 8,

    # 5. الاتصال والهاتف
    'الهاتف': 9,
    'رقم الهاتف': 9,
    'Mobile': 9,
    'Phone': 9,

    # 6. العنوان والموقع
    'العنوان': 10,
    'Address': 10,
    'عنوان المحل': 10,
    'المنطقة': 10,

    # 7. التواريخ
    'تأريخه': 11,
    'تاريخه': 11,
    'تأريحه': 11,
    'تاريخ الانتساب': 11,
    'AffiliationDate': 11,
    'تاريخ التسجيل': 11,
    'ExpirationDate': 12,
    'تاريخ التعديل': 13,
    'تاريخ الشطب': 13,

    # 8. الأرقام والهويات
    'رقم الأسم التجاري': 14,
    'رقم الاسم التجاري': 14,
    'رقم  التجاري': 14,
    'رقم التجديد': 15,
    'RenewalNo': 15,
    'ID': 16,
    'id': 16,
    'IDNo': 16,
    'ID_No': 16,
    'StampNo': 17,
    'CommercialNo': 17,
    'تسلسل الشركة': 17,
    'رقم اجازة التأسيس': 18,
    'رقم شهادة الجنسية': 18,

    # 9. البيانات الشخصية
    'اسم الزوج': 20,
    'اسم الام': 21,
    'المواليد': 22,
    'ذكر': 23,
    'انثى': 24,
    'Female': 24,
    'جنسيته': 25,

    # 10. التعديل والشطب والملاحظات
    'التعديل': 30,
    'الشطب': 31,
    'العمل التجاري القديم': 32,
    'الملاحظات': 33,
    'المرفق': 34,
    'المرفقات': 34,
    'Field1': 35,
    'Field2': 36,
    'Field3': 37,
    'Field4': 38,
}

def sort_columns_by_priority(cols):
    """ترتيب الحقول حسب الأولوية الذكية المعتمدة في منصة الويب 100%"""
    cols_list = list(cols)
    return sorted(cols_list, key=lambda c: (COLUMN_PRIORITY.get(c, 100), cols_list.index(c)))


def parse_date_value(val):
    """تحليل ذكي لقيم التواريخ لتحويلها إلى Timestamp للمقارنة والفرز"""
    if val is None or val == "":
        return None
    s = str(val).strip()

    # YYYY-MM-DD أو YYYY/MM/DD
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).timestamp()
        except Exception:
            pass

    # DD/MM/YYYY أو DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).timestamp()
        except Exception:
            pass

    # محاولة التحليل القياسي
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        pass

    # سنة فقط e.g. 2024
    if re.match(r"^\d{4}$", s):
        try:
            return datetime(int(s), 1, 1).timestamp()
        except Exception:
            pass

    return None


def get_short_file_name(name: str) -> str:
    """اسم القسم المختصر والأنيق للبطاقات والشارات مطابقاً للوحة الويب"""
    if not name:
        return ""
    if "جهاز الاشتراكات" in name:
        return "جهاز الاشتراكات"
    if "2025" in name:
        return "2025 - 2026"
    if "2024" in name:
        return "2024"
    if "2023" in name:
        return "2023"
    if "2022" in name:
        return "2022"
    if "1984" in name:
        return "1984 - 2021"
    if "جديد" in name or "المبتكرة" in name:
        return "الكلية والمبتكرة"
    return name


def extract_card_fields(row: dict) -> dict:
    """استخراج وتوحيد الحقول الجوهرية لعرض البطاقات الذكية لكافة الأصناف مطابقاً للويب"""
    if not isinstance(row, dict):
        return {
            "name": "قيد بدون اسم", "commercial_name": None, "activity": None,
            "phone": None, "address": None, "date_val": None, "grade": None
        }

    name = (
        row.get("ArabicName") or
        row.get("اسم التاجر") or
        row.get("اسم الشركة") or
        row.get("اسم الفندق") or
        row.get("اسم الصيدلية") or
        row.get("اسم المعمل") or
        row.get("اسم الدلال") or
        row.get("صاحب الاسم التجاري") or
        row.get("اسم صاحب الفندق") or
        row.get("اسم صاحب المعمل") or
        row.get("اسم صاحب المكتب") or
        row.get("اسم صاحب الصيدلية") or
        row.get("اسم صاحب الشركة") or
        row.get("الاسم التجاري") or
        row.get("الإسم التجاري") or
        row.get("Name") or
        "قيد مسجل بدون اسم"
    )

    commercial_name = None
    for cand in ("الاسم التجاري", "الإسم التجاري", "اسم الفندق", "اسم الشركة", "اسم الصيدلية", "اسم المعمل", "صاحب الاسم التجاري", "CommercialName", "اسم المحل"):
        val = row.get(cand)
        if val and str(val).strip() and str(val).strip() != str(name).strip():
            commercial_name = str(val).strip()
            break

    activity = None
    for cand in ("نوع النشاط", "النشاط", "Activity", "العمل", "العمل التجاري", "SpecificActivity", "EnglishActivity", "نوع المحل"):
        val = row.get(cand)
        if val and str(val).strip():
            activity = str(val).strip()
            break

    phone = None
    for cand in ("Mobile", "الهاتف", "رقم الهاتف", "Phone"):
        val = row.get(cand)
        if val and str(val).strip():
            phone = str(val).strip()
            break

    address = None
    for cand in ("العنوان", "عنوان المحل", "Address", "المنطقة"):
        val = row.get(cand)
        if val and str(val).strip():
            address = str(val).strip()
            break

    date_val = None
    for cand in ("تاريخ التسجيل", "تاريخ التجديد", "تاريخ انتهاء الإجازة", "تأريخه", "تاريخه", "تأريحه", "تاريخ الانتساب", "تاريخ التعديل", "تاريخ الشطب", "Date", "RegDate", "AffiliationDate"):
        val = row.get(cand)
        if val and str(val).strip():
            date_val = str(val).strip()
            break

    grade = None
    for cand in ("Class", "الصنف", "الدرجة"):
        val = row.get(cand)
        if val and str(val).strip():
            grade = str(val).strip()
            break

    return {
        "name": str(name).strip(),
        "commercial_name": commercial_name,
        "activity": activity,
        "phone": phone,
        "address": address,
        "date_val": date_val,
        "grade": grade,
    }


class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_name, table_name, search_query="", page=1, limit=50, sort_dir="none", sort_col="date_auto"):
        super().__init__()
        self.file_name = file_name
        self.table_name = table_name
        self.search_query = search_query
        self.page = page
        self.limit = limit
        self.sort_dir = sort_dir
        self.sort_col = sort_col

    def run(self):
        # 1. القراءة الفورية فائقة السرعة من الذاكرة والقرص المحلي أولاً (Instant 0ms)
        local_dir = get_local_data_dir()
        if local_dir.exists() and (local_dir / "index.json").exists():
            try:
                result = self._load_from_local_disk(local_dir)
                if result:
                    self.data_loaded.emit(result)
                    return
            except Exception as e:
                pass

        # 2. في حال عدم توفر البيانات محلياً، الاستعلام من السحابة السريعة
        my_guid = get_desktop_machine_guid()
        params = {
            "file": self.file_name,
            "table": self.table_name,
            "search": self.search_query,
            "page": self.page,
            "limit": self.limit,
            "sort_dir": self.sort_dir,
            "sort_col": self.sort_col,
            "guid": my_guid,
        }
        headers = {
            "x-machine-guid": my_guid
        }
        try:
            r = requests.get(CLOUD_API_URL, params=params, headers=headers, timeout=10)
            if r.status_code == 200:
                self.data_loaded.emit(r.json())
                return
            else:
                self.error_occurred.emit(f"خطأ في الخادم السحابي: {r.status_code}")
        except Exception as e:
            self.error_occurred.emit(f"تعذر استرجاع البيانات: {e}")

    def _load_from_local_disk(self, local_dir=None):
        if local_dir is None:
            local_dir = get_local_data_dir()
        idx_path = local_dir / "index.json"
        idx = get_cached_json_file(idx_path)
        if not idx:
            return None

        req_file = self.file_name
        req_table = self.table_name
        search = self.search_query.strip().lower()

        # قراءة الطفرات السحابية المخزنة محلياً إن وجدت
        mutations = {"adds": [], "updates": {}, "deletes": [], "added_columns": {}, "deleted_columns": {}}
        mut_path = local_dir / "mutations.json"
        if mut_path.exists():
            cached_mut = get_cached_json_file(mut_path)
            if cached_mut:
                mutations = cached_mut

        rows = []
        columns = []
        available_tables = []

        is_all_tables = (req_table == "all" or not req_table)

        if req_file == "all":
            tables_set = set()
            for f in idx.get("files", []):
                for t in f.get("tables", []):
                    tables_set.add(t)
            for a in mutations.get("adds", []):
                if a.get("_adh_table"):
                    tables_set.add(a["_adh_table"])
            available_tables = sort_tables_by_priority(list(tables_set))

            cols_order = []
            cols_seen = set()

            if is_all_tables:
                req_table = "all"
                for f in idx.get("files", []):
                    fpath = local_dir / f"{f['name']}.json"
                    data = get_cached_json_file(fpath)
                    if not data:
                        continue

                    for tbl_name, orig_cols in data.get("columns", {}).items():
                        for c in orig_cols:
                            if c not in cols_seen:
                                cols_seen.add(c)
                                cols_order.append(c)

                    for tbl_name, tbl_rows in data.get("tables", {}).items():
                        for r in tbl_rows:
                            r_copy = dict(r)
                            r_copy["_adh_file"] = f["name"]
                            r_copy["_adh_table"] = tbl_name
                            rows.append(r_copy)

                columns = cols_order
            else:
                target_tables = ["الدلالين", "دلالين"] if req_table in ("الدلالين", "دلالين") else [req_table]
                for f in idx.get("files", []):
                    fpath = local_dir / f"{f['name']}.json"
                    data = get_cached_json_file(fpath)
                    if not data:
                        continue

                    for tt in target_tables:
                        orig_cols = data.get("columns", {}).get(tt, [])
                        for c in orig_cols:
                            if c not in cols_seen:
                                cols_seen.add(c)
                                cols_order.append(c)

                        for r in data.get("tables", {}).get(tt, []):
                            r_copy = dict(r)
                            r_copy["_adh_file"] = f["name"]
                            r_copy["_adh_table"] = tt
                            rows.append(r_copy)

                columns = cols_order
        else:
            fpath = local_dir / f"{req_file}.json"
            data = get_cached_json_file(fpath)
            if not data:
                return None

            available_tables = sort_tables_by_priority(list(data.get("tables", {}).keys()))
            cols_order = []
            cols_seen = set()

            if is_all_tables:
                req_table = "all"
                for tbl_name, orig_cols in data.get("columns", {}).items():
                    for c in orig_cols:
                        if c not in cols_seen:
                            cols_seen.add(c)
                            cols_order.append(c)

                for tbl_name, tbl_rows in data.get("tables", {}).items():
                    for r in tbl_rows:
                        r_copy = dict(r)
                        r_copy["_adh_file"] = req_file
                        r_copy["_adh_table"] = tbl_name
                        rows.append(r_copy)

                columns = cols_order
            else:
                if req_table in ("الدلالين", "دلالين"):
                    if "الدلالين" in data.get("tables", {}):
                        req_table = "الدلالين"
                    elif "دلالين" in data.get("tables", {}):
                        req_table = "دلالين"
                elif not req_table or req_table not in data.get("tables", {}):
                    req_table = available_tables[0] if available_tables else ""

                columns = list(data.get("columns", {}).get(req_table, []))
                for r in data.get("tables", {}).get(req_table, []):
                    r_copy = dict(r)
                    r_copy["_adh_file"] = req_file
                    r_copy["_adh_table"] = req_table
                    rows.append(r_copy)

        # دمج الحقول المضافة والمحذوفة
        added_for_tbl = []
        deleted_for_tbl = []
        for k, v in mutations.get("added_columns", {}).items():
            if k.endswith(f":{req_table}") or k.endswith(f"_{req_table}") or \
               k == f"{req_file}:{req_table}" or k == f"{req_file}_{req_table}" or \
               k.endswith(":all") or k.endswith("_all") or k == f"{req_file}_all" or k == "all_all":
                for c in v:
                    if c not in added_for_tbl:
                        added_for_tbl.append(c)

        for k, v in mutations.get("deleted_columns", {}).items():
            if k.endswith(f":{req_table}") or k.endswith(f"_{req_table}") or \
               k == f"{req_file}:{req_table}" or k == f"{req_file}_{req_table}" or \
               k.endswith(":all") or k.endswith("_all") or k == f"{req_file}_all" or k == "all_all":
                for c in v:
                    if c not in deleted_for_tbl:
                        deleted_for_tbl.append(c)

        active_columns = [c for c in columns if c not in deleted_for_tbl]
        for c in added_for_tbl:
            if c not in active_columns and c not in deleted_for_tbl:
                active_columns.append(c)

        # ترتيب الأعمدة حسب الأولوية الذكية مطابقاً لمنصة الويب 100%
        active_columns = sort_columns_by_priority(active_columns)

        # تطبيق الترتيب المخصص السحابي إن وجد
        custom_orders = mutations.get("column_orders", {})
        custom_order = (
            custom_orders.get(f"{req_file}_{req_table}") or
            custom_orders.get(f"all_{req_table}") or
            custom_orders.get(f"{req_file}_all") or
            custom_orders.get("all_all")
        )
        if custom_order and isinstance(custom_order, list) and len(custom_order) > 0:
            order_map = {name: idx for idx, name in enumerate(custom_order)}
            active_columns.sort(key=lambda c: order_map.get(c, 9999))

        # استخراج أعمدة التواريخ
        date_columns = []
        for c in active_columns:
            clow = c.lower()
            if any(k in clow for k in DATE_KEYWORDS):
                date_columns.append(c)

        # تطبيق الحذف والتعديل والإضافة
        deleted_ids = set(mutations.get("deletes", []))
        updates = mutations.get("updates", {})

        filtered_rows = []
        for r in rows:
            r_id = r.get("_adh_id") or f"{r.get('_adh_file')}:{r.get('_adh_table')}:{r.get('ID') or r.get('id') or r.get('ت')}"
            if r_id in deleted_ids:
                continue
            merged = dict(r)
            if r_id in updates:
                merged.update(updates[r_id])
            merged["_adh_id"] = r_id
            if search:
                match = any(v and search in str(v).lower() for k, v in merged.items() if not k.startswith("_adh_"))
                if not match:
                    continue
            filtered_rows.append(merged)

        # إضافة السجلات الجديدة (الحفاظ على أسبقية السجلات الأحدث في قمة الجدول 100% مطابقاً لمنصة الويب)
        relevant_adds = []
        for a in mutations.get("adds", []):
            if req_file == "all" or a.get("_adh_file") == req_file:
                if req_table == "all" or a.get("_adh_table") == req_table:
                    a_id = a.get("_adh_id")
                    if a_id and a_id in deleted_ids:
                        continue
                    merged = dict(a)
                    if a_id and a_id in updates:
                        merged.update(updates[a_id])
                    if search:
                        match = any(v and search in str(v).lower() for k, v in merged.items() if not k.startswith("_adh_"))
                        if not match:
                            continue
                    relevant_adds.append(merged)

        # دمج السجلات المضافة في قمة الجدول بحيث يظهر القيد المضاف حديثاً كأول قيد #1
        filtered_rows = relevant_adds + filtered_rows

        # الفرز الزمني إذا طُلب
        actual_sort_col = self.sort_col
        eff_sort_dir = self.sort_dir
        if eff_sort_dir == 'none' and req_file == 'all' and req_table in ('الدلالين', 'دلالين'):
            eff_sort_dir = 'desc'  # الدلالين المدمجون: من الجديد للقديم
        if eff_sort_dir in ('desc', 'asc'):
            if actual_sort_col == 'date_auto' or not actual_sort_col:
                actual_sort_col = date_columns[0] if date_columns else (active_columns[0] if active_columns else "")

            if actual_sort_col:
                def sort_key(row):
                    val = row.get(actual_sort_col)
                    ts = parse_date_value(val)
                    if ts is not None:
                        return (0, ts)
                    return (1, str(val or ""))

                filtered_rows.sort(key=sort_key, reverse=(eff_sort_dir == 'desc'))

        total_matches = len(filtered_rows)
        start_idx = (self.page - 1) * self.limit
        page_rows = filtered_rows[start_idx:start_idx + self.limit]

        # حساب الإحصائيات الحية للأقسام والجداول محلياً
        file_map = {}
        for f in idx.get("files", []):
            file_map[f["name"]] = {
                "name": f["name"],
                "tables": list(f.get("tables", [])),
                "table_counts": dict(f.get("table_counts", {})),
                "total_rows": int(f.get("total_rows", 0)),
                "size_kb": f.get("size_kb", 0.1)
            }
        for a in mutations.get("adds", []):
            af = a.get("_adh_file")
            at = a.get("_adh_table")
            if a.get("_adh_id") in deleted_ids or not af or not at:
                continue
            if af not in file_map:
                file_map[af] = {"name": af, "tables": [], "table_counts": {}, "total_rows": 0, "size_kb": 0.1}
            if at not in file_map[af]["tables"]:
                file_map[af]["tables"].append(at)
            file_map[af]["table_counts"][at] = file_map[af]["table_counts"].get(at, 0) + 1
            file_map[af]["total_rows"] += 1

        adds_ids = {a.get("_adh_id") for a in mutations.get("adds", [])}
        for del_id in deleted_ids:
            if del_id in adds_ids:
                continue
            for f_name, f_obj in file_map.items():
                if del_id.startswith(f"{f_name}_"):
                    rest = del_id[len(f_name) + 1:]
                    for tbl in f_obj["tables"]:
                        if rest.startswith(f"{tbl}_") or rest == tbl:
                            if tbl in f_obj["table_counts"]:
                                f_obj["table_counts"][tbl] = max(0, f_obj["table_counts"][tbl] - 1)
                            f_obj["total_rows"] = max(0, f_obj["total_rows"] - 1)
                            break
                    break

        dynamic_files = list(file_map.values())
        grand_total = sum(f["total_rows"] for f in dynamic_files)

        my_guid = get_desktop_machine_guid()
        roles_map = mutations.get("roles", {})
        cur_role = roles_map.get(my_guid, {}).get("role", "data_entry") if isinstance(roles_map.get(my_guid), dict) else "data_entry"
        return {
            "success": True,
            "current_role": cur_role,
            "roles": roles_map,
            "files": dynamic_files,
            "total_records": grand_total,
            "active_file": req_file,
            "active_table": req_table,
            "available_tables": available_tables,
            "columns": active_columns,
            "date_columns": date_columns,
            "sort_col": actual_sort_col,
            "sort_dir": self.sort_dir,
            "total_matches": total_matches,
            "page": self.page,
            "limit": self.limit,
            "total_pages": max(1, (total_matches + self.limit - 1) // self.limit),
            "rows": page_rows
        }


class RecordFormDialog(QDialog):
    """نافذة لإضافة أو تعديل قيد بتصميم عصري مطابق لموقع الويب (شبكة من عمودين وإخفاء الحقول الفارغة تلقائياً)"""
    def __init__(self, title, columns, initial_data=None, files_list=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        # تصفية الحقول وترتيبها بالأولوية الذكية المطابقة للويب
        self.columns = sort_columns_by_priority([c for c in columns if not c.startswith("_adh_")])
        self.files_list = files_list or []
        self.initial_data = initial_data
        self.inputs = {}
        self.empty_card_widgets = []
        self.show_empty_fields = False
        self.selected_file = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 16, 18, 16)

        header = QLabel(title)
        header.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #14372e; padding-bottom: 6px; border-bottom: 2px solid #c59b27;")
        layout.addWidget(header)

        # اختيار الملف في حالة الإضافة وفي وضع الدمج الشامل
        if self.files_list and initial_data is None:
            file_box = QVBoxLayout()
            file_box.setSpacing(4)
            lbl_file = QLabel("📁 حفظ القيد في ملف / قسم:")
            lbl_file.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            lbl_file.setStyleSheet("color: #344054;")
            file_box.addWidget(lbl_file)

            self.file_combo = QComboBox()
            self.file_combo.setFont(QFont("IBM Plex Sans Arabic", 9))
            self.file_combo.setStyleSheet("""
                QComboBox {
                    background: #F8F9FA;
                    border: 1.5px solid #14372e;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-weight: bold;
                    color: #14372e;
                }
            """)
            for f in self.files_list:
                fname = f.get("name", "") if isinstance(f, dict) else str(f)
                self.file_combo.addItem(fname)
            file_box.addWidget(self.file_combo)
            layout.addLayout(file_box)

        # شريط التحكم في إظهار / إخفاء الحقول الفارغة (يظهر أعلى الحقول مباشرة)
        filled_count = 0
        empty_count = 0
        if initial_data:
            for col in self.columns:
                raw_val = initial_data.get(col, "")
                val_str = "" if raw_val is None else str(raw_val).strip()
                if val_str != "" and val_str.lower() != "none" and val_str != "—":
                    filled_count += 1
                else:
                    empty_count += 1

        if initial_data and empty_count > 0:
            toggle_bar = QHBoxLayout()
            toggle_bar.setContentsMargins(0, 0, 0, 4)

            lbl_hint = QLabel(f"📌 عرض الحقول التي تحتوي بيانات فقط ({filled_count})")
            lbl_hint.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            lbl_hint.setStyleSheet("color: #14372e; background: #EDF5F2; padding: 4px 10px; border-radius: 6px; border: 1px solid #B8D8CC;")
            toggle_bar.addWidget(lbl_hint)
            toggle_bar.addStretch()

            self.btn_toggle_empty = QPushButton(f"➕ إظهار باقي الحقول الفارغة ({empty_count})")
            self.btn_toggle_empty.setFont(QFont("IBM Plex Sans Arabic", 9))
            self.btn_toggle_empty.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.btn_toggle_empty.setStyleSheet("""
                QPushButton {
                    background: #F8F9FA;
                    color: #344054;
                    border: 1px dashed #98A2B3;
                    border-radius: 6px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background: #EDF5F2;
                    color: #14372e;
                    border-color: #14372e;
                }
            """)
            self.btn_toggle_empty.clicked.connect(self._toggle_empty_fields)
            toggle_bar.addWidget(self.btn_toggle_empty)
            layout.addLayout(toggle_bar)

        # شبكة إدخال البيانات في عمودين متناسقين مطابقة للويب (2-Column Grid)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E4E7EC; border-radius: 8px; background: #FAFAFA; }")
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(scroll_content)
        grid_layout.setContentsMargins(10, 10, 10, 10)
        grid_layout.setSpacing(10)

        # فصل الحقول إلى ممتلئة أولاً ثم فارغة
        filled_cols = []
        empty_cols = []
        if initial_data:
            for col in self.columns:
                raw_val = initial_data.get(col, "")
                val_str = "" if raw_val is None else str(raw_val).strip()
                if val_str != "" and val_str.lower() != "none" and val_str != "—":
                    filled_cols.append(col)
                else:
                    empty_cols.append(col)
        else:
            filled_cols = list(self.columns)
            empty_cols = []

        cur_row = 0
        cur_col = 0

        # إضافة الحقول الممتلئة أولاً
        for col in filled_cols:
            card, inp, is_wide = self._create_field_card(col, initial_data.get(col, "") if initial_data else "")
            self.inputs[col] = inp
            if is_wide:
                if cur_col == 1:
                    cur_row += 1
                    cur_col = 0
                grid_layout.addWidget(card, cur_row, 0, 1, 2)
                cur_row += 1
                cur_col = 0
            else:
                grid_layout.addWidget(card, cur_row, cur_col)
                cur_col += 1
                if cur_col >= 2:
                    cur_col = 0
                    cur_row += 1

        if cur_col == 1:
            cur_row += 1
            cur_col = 0

        # إضافة الحقول الفارغة (تكون مخفية افتراضياً في حالة التعديل)
        for col in empty_cols:
            card, inp, is_wide = self._create_field_card(col, "")
            self.inputs[col] = inp
            card.hide()
            self.empty_card_widgets.append((card, is_wide))
            if is_wide:
                if cur_col == 1:
                    cur_row += 1
                    cur_col = 0
                grid_layout.addWidget(card, cur_row, 0, 1, 2)
                cur_row += 1
                cur_col = 0
            else:
                grid_layout.addWidget(card, cur_row, cur_col)
                cur_col += 1
                if cur_col >= 2:
                    cur_col = 0
                    cur_row += 1

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # شريط أزرار الحفظ والإلغاء
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_save = QPushButton("💾 حفظ ومزامنة سحابية فورية")
        btn_save.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_save.setStyleSheet("""
            QPushButton {
                background: #14372e;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1a473b;
            }
        """)
        btn_save.clicked.connect(self.accept)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #344054;
                border: 1px solid #D0D5DD;
                border-radius: 8px;
                padding: 8px 18px;
            }
            QPushButton:hover {
                background: #F2F4F7;
            }
        """)
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _create_field_card(self, col: str, val):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 8px;
                padding: 4px 6px;
            }
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        lbl = QLabel(col)
        lbl.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #344054; border: none; background: transparent;")
        lay.addWidget(lbl)

        inp = QLineEdit()
        inp.setFont(QFont("IBM Plex Sans Arabic", 9))
        inp.setStyleSheet("""
            QLineEdit {
                background: #F7F8FA;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 10px;
                color: #1B1F24;
            }
            QLineEdit:focus {
                background: #FFFFFF;
                border: 1.5px solid #14372e;
            }
        """)
        val_str = "" if val is None else str(val).strip()
        if val_str and val_str.lower() != "none" and val_str != "—":
            inp.setText(val_str)
        lay.addWidget(inp)

        col_lower = col.lower()
        is_wide = any(k in col_lower for k in ("ملاحظ", "field", "notes", "العمل", "العنوان", "activity", "address"))
        return card, inp, is_wide

    def _toggle_empty_fields(self):
        self.show_empty_fields = not self.show_empty_fields
        for card, _ in self.empty_card_widgets:
            card.setVisible(self.show_empty_fields)
        if self.show_empty_fields:
            self.btn_toggle_empty.setText(f"➖ إخفاء الحقول الفارغة ({len(self.empty_card_widgets)})")
            self.btn_toggle_empty.setStyleSheet("""
                QPushButton {
                    background: #FEF3C7;
                    color: #92400E;
                    border: 1px solid #FCD34D;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-weight: bold;
                }
            """)
        else:
            self.btn_toggle_empty.setText(f"➕ إظهار باقي الحقول الفارغة ({len(self.empty_card_widgets)})")
            self.btn_toggle_empty.setStyleSheet("""
                QPushButton {
                    background: #F8F9FA;
                    color: #344054;
                    border: 1px dashed #98A2B3;
                    border-radius: 6px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background: #EDF5F2;
                    color: #14372e;
                    border-color: #14372e;
                }
            """)

    def get_data(self):
        return {col: self.inputs[col].text().strip() for col in self.columns if col in self.inputs}

    def get_target_file(self):
        if hasattr(self, 'file_combo'):
            return self.file_combo.currentText()
        return None

class AddColumnDialog(QDialog):
    """نافذة لإضافة حقل جديد إلى الجدول مع تعميمه سحابياً"""
    def __init__(self, table_name, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة حقل جديد")
        self.resize(440, 230)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        lbl_title = QLabel("➕ إضافة حقل جديد إلى قاعدة البيانات")
        lbl_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #14372e;")
        layout.addWidget(lbl_title)

        info = QLabel(f"الجدول المستهدف: {table_name} | القسم: {file_name}")
        info.setFont(QFont("IBM Plex Sans Arabic", 9))
        info.setStyleSheet("color: #667085;")
        layout.addWidget(info)

        lbl_name = QLabel("اسم الحقل الجديد:")
        lbl_name.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl_name.setStyleSheet("color: #344054;")
        layout.addWidget(lbl_name)

        self.input_col = QLineEdit()
        self.input_col.setPlaceholderText("مثال: رقم الهاتف الثاني، الملاحظات، الرقم الضريبي...")
        self.input_col.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.input_col.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                border: 1.5px solid #D0D5DD;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border-color: #14372e; }
        """)
        layout.addWidget(self.input_col)

        hint = QLabel("💡 سيتم تعميم هذا الحقل فورياً في السحابة لجميع الموظفين ولوحة الويب.")
        hint.setFont(QFont("IBM Plex Sans Arabic", 8))
        hint.setStyleSheet("color: #027A48;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("إضافة وتعميم سحابي")
        btn_add.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_add.setStyleSheet("background: #14372e; color: #FFFFFF; border-radius: 6px; padding: 8px 16px;")
        btn_add.clicked.connect(self._validate_and_accept)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_cancel.setStyleSheet("background: #F2F4F7; color: #344054; border: 1px solid #D0D5DD; border-radius: 6px; padding: 8px 16px;")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_add)
        layout.addLayout(btn_row)

    def _validate_and_accept(self):
        val = self.input_col.text().strip()
        if not val:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة اسم الحقل أولاً.")
            return
        self.accept()

    def get_column_name(self):
        return self.input_col.text().strip()


class DeleteColumnDialog(QDialog):
    """نافذة لحذف أو إخفاء حقل من الجدول وتعميمه سحابياً"""
    def __init__(self, table_name, columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة وحذف الحقول")
        self.resize(440, 240)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        lbl_title = QLabel("🗑️ حذف حقل من الجدول")
        lbl_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #B42318;")
        layout.addWidget(lbl_title)

        info = QLabel(f"الجدول المستهدف: {table_name}")
        info.setFont(QFont("IBM Plex Sans Arabic", 9))
        info.setStyleSheet("color: #667085;")
        layout.addWidget(info)

        lbl_pick = QLabel("اختر الحقل المراد حذفه:")
        lbl_pick.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl_pick.setStyleSheet("color: #344054;")
        layout.addWidget(lbl_pick)

        self.combo_cols = QComboBox()
        self.combo_cols.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.combo_cols.setStyleSheet("""
            QComboBox {
                background: #FFFFFF;
                border: 1.5px solid #D0D5DD;
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        for c in columns:
            self.combo_cols.addItem(c)
        layout.addWidget(self.combo_cols)

        warn = QLabel("⚠️ تحذير: سيتم إخفاء هذا الحقل وحذفه من العرض لجميع المستخدمين في كافة المنصات.")
        warn.setFont(QFont("IBM Plex Sans Arabic", 8))
        warn.setStyleSheet("color: #B42318;")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        btn_row = QHBoxLayout()
        btn_del = QPushButton("تأكيد حذف الحقل")
        btn_del.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_del.setStyleSheet("background: #D92D20; color: #FFFFFF; border-radius: 6px; padding: 8px 16px;")
        btn_del.clicked.connect(self.accept)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_cancel.setStyleSheet("background: #F2F4F7; color: #344054; border: 1px solid #D0D5DD; border-radius: 6px; padding: 8px 16px;")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_del)
        layout.addLayout(btn_row)

    def get_selected_column(self):
        return self.combo_cols.currentText()


class RecordCardWidget(QFrame):
    """بطاقة تفاعلية ذكية متطابقة 1:1 مع عرض البطاقات في لوحة الويب"""
    def __init__(self, row, row_num, parent_hub, parent=None):
        super().__init__(parent)
        self.row = row
        self.row_num = row_num
        self.parent_hub = parent_hub
        self.setObjectName("accessRecordCard")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        fields = extract_card_fields(self.row)
        short_file = get_short_file_name(self.row.get("_adh_file", ""))
        tbl = self.row.get("_adh_table", "")

        # 1. الترويسة العليا للبطاقة
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        lbl_num = QLabel(f"#{self.row_num}")
        lbl_num.setObjectName("cardRecordNum")
        hdr.addWidget(lbl_num)

        if short_file:
            lbl_file = QLabel(short_file)
            lbl_file.setObjectName("cardRecordFileBadge")
            hdr.addWidget(lbl_file)

        if tbl:
            icon, title = TABLE_DISPLAY_META.get(tbl, ("🏷️", tbl))
            lbl_tbl = QLabel(f"{icon} {title}")
            lbl_tbl.setObjectName("cardRecordTableBadge")
            hdr.addWidget(lbl_tbl)

        if fields["grade"]:
            lbl_grade = QLabel(f"⭐ {fields['grade']}")
            lbl_grade.setObjectName("cardRecordTableBadge")
            hdr.addWidget(lbl_grade)

        hdr.addStretch()

        if fields["date_val"]:
            lbl_date = QLabel(f"📅 {fields['date_val']}")
            lbl_date.setObjectName("cardRecordDateBadge")
            hdr.addWidget(lbl_date)

        layout.addLayout(hdr)

        # 2. جسم البطاقة (الاسم والنشاط والعنوان)
        lbl_name = QLabel(fields["name"])
        lbl_name.setObjectName("cardRecordName")
        lbl_name.setWordWrap(True)
        lbl_name.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        lbl_name.mousePressEvent = lambda e: self.parent_hub._show_record_details_by_data(self.row)
        layout.addWidget(lbl_name)

        if fields["commercial_name"]:
            lbl_comm = QLabel(f"🏢 {fields['commercial_name']}")
            lbl_comm.setObjectName("cardRecordCommercial")
            lbl_comm.setWordWrap(True)
            layout.addWidget(lbl_comm)

        if fields["activity"]:
            lbl_act = QLabel(f"💼 {fields['activity']}")
            lbl_act.setObjectName("cardRecordActivity")
            lbl_act.setWordWrap(True)
            layout.addWidget(lbl_act)

        if fields["address"]:
            lbl_addr = QLabel(f"📍 {fields['address']}")
            lbl_addr.setObjectName("cardRecordAddress")
            lbl_addr.setWordWrap(True)
            layout.addWidget(lbl_addr)

        layout.addSpacing(4)

        # 3. شريط الإجراءات السفلي (الاتصال والنسخ والتعديل)
        footer = QHBoxLayout()
        footer.setSpacing(6)

        if fields["phone"]:
            btn_call = QPushButton(f"📞 {fields['phone']}")
            btn_call.setObjectName("btnCardCall")
            btn_call.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_call.setToolTip("اضغط لنسخ رقم الهاتف")
            btn_call.clicked.connect(lambda: self._on_call_clicked(fields["phone"]))
            footer.addWidget(btn_call)
        else:
            lbl_no_phone = QLabel("بدون هاتف")
            lbl_no_phone.setStyleSheet("color: #98A2B3; font-size: 10px;")
            footer.addWidget(lbl_no_phone)

        footer.addStretch()

        btn_eye = QPushButton("👁️")
        btn_eye.setObjectName("btnCardQuickAction")
        btn_eye.setToolTip("عرض تفاصيل القيد بالكامل")
        btn_eye.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_eye.clicked.connect(lambda: self.parent_hub._show_record_details_by_data(self.row))
        footer.addWidget(btn_eye)

        btn_copy = QPushButton("📋")
        btn_copy.setObjectName("btnCardQuickAction")
        btn_copy.setToolTip("نسخ بيانات القيد")
        btn_copy.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_copy.clicked.connect(self._copy_data)
        footer.addWidget(btn_copy)

        if getattr(self.parent_hub, "user_role", "data_entry") != "viewer":
            btn_edit = QPushButton("✏️")
            btn_edit.setObjectName("btnCardQuickAction")
            btn_edit.setToolTip("تعديل هذا القيد")
            btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_edit.clicked.connect(lambda: self.parent_hub._edit_record_by_data(self.row))
            footer.addWidget(btn_edit)

        if getattr(self.parent_hub, "user_role", "data_entry") == "admin":
            btn_del = QPushButton("🗑️")
            btn_del.setObjectName("btnCardQuickAction")
            btn_del.setStyleSheet("QPushButton { color: #D92D20; border-color: #FECDCA; } QPushButton:hover { background: #FEF3F2; }")
            btn_del.setToolTip("حذف هذا القيد")
            btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_del.clicked.connect(lambda: self.parent_hub._delete_record_by_data(self.row))
            footer.addWidget(btn_del)

        layout.addLayout(footer)

    def _copy_data(self):
        lines = [f"{k}: {v}" for k, v in self.row.items() if not k.startswith("_adh_") and v is not None and str(v).strip() != ""]
        text = chr(10).join(lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        QMessageBox.information(self, "تم النسخ", "تم نسخ بيانات القيد بنجاح إلى الحافظة!")

    def _on_call_clicked(self, phone):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(phone)
        QMessageBox.information(self, "رقم الهاتف", f"تم نسخ رقم الهاتف ({phone}) إلى الحافظة.")


class RecordDetailsDialog(QDialog):
    """نافذة لعرض التفاصيل الكاملة للقيد بشكل منسق ومقروء متطابقة مع الويب"""
    def __init__(self, record, columns, title="تفاصيل القيد", parent_hub=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 680)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.record = record
        self.columns = sort_columns_by_priority([c for c in columns if not c.startswith("_adh_")])
        self.parent_hub = parent_hub
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        fields = extract_card_fields(self.record)

        # 1. الترويسة
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("background: #FFFFFF; border-bottom: 2px solid #c59b27; padding-bottom: 8px;")
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(0, 0, 0, 0)

        lbl_icon = QLabel("👁️")
        lbl_icon.setFont(QFont("Segoe UI Emoji", 14))
        hdr_lay.addWidget(lbl_icon)

        hdr_info = QVBoxLayout()
        hdr_info.setSpacing(2)
        lbl_title = QLabel(fields["name"])
        lbl_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #14372e;")
        hdr_info.addWidget(lbl_title)

        f_name = self.record.get("_adh_file", "")
        t_name = self.record.get("_adh_table", "")
        lbl_sub = QLabel(f"الملف: {f_name}  •  الجدول: {t_name or 'الرئيسي'}")
        lbl_sub.setFont(QFont("IBM Plex Sans Arabic", 9))
        lbl_sub.setStyleSheet("color: #667085;")
        hdr_info.addWidget(lbl_sub)
        hdr_lay.addLayout(hdr_info, stretch=1)

        layout.addWidget(hdr_frame)

        # 2. شريط الإجراءات السريعة (اتصال، نسخ، تعديل)
        actions_bar = QHBoxLayout()
        actions_bar.setSpacing(8)

        if fields["phone"]:
            btn_call = QPushButton(f"📞 اتصال: {fields['phone']}")
            btn_call.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            btn_call.setStyleSheet("background: #027A48; color: #FFFFFF; border-radius: 6px; padding: 6px 14px;")
            btn_call.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_call.clicked.connect(lambda: self._copy_and_notify(fields["phone"], "تم نسخ رقم الهاتف!"))
            actions_bar.addWidget(btn_call)

        btn_copy = QPushButton("📋 نسخ كامل البيانات")
        btn_copy.setFont(QFont("IBM Plex Sans Arabic", 9))
        btn_copy.setStyleSheet("background: #FFFFFF; color: #344054; border: 1px solid #D0D5DD; border-radius: 6px; padding: 6px 14px;")
        btn_copy.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_copy.clicked.connect(self._copy_all)
        actions_bar.addWidget(btn_copy)

        actions_bar.addStretch()

        if self.parent_hub and getattr(self.parent_hub, "user_role", "data_entry") != "viewer":
            btn_edit = QPushButton("✏️ تعديل القيد")
            btn_edit.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            btn_edit.setStyleSheet("background: #14372e; color: #FFFFFF; border-radius: 6px; padding: 6px 14px;")
            btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_edit.clicked.connect(self._open_edit)
            actions_bar.addWidget(btn_edit)

        layout.addLayout(actions_bar)

        # 3. شبكة تفاصيل الحقول
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #E4E7EC; border-radius: 8px; background: #F7F8FA; }")

        grid_widget = QWidget()
        grid_lay = QGridLayout(grid_widget)
        grid_lay.setContentsMargins(10, 10, 10, 10)
        grid_lay.setSpacing(8)

        self.empty_details_boxes = []
        self.show_empty_details = False

        filled_cols = []
        empty_cols = []
        for col in self.columns:
            val = self.record.get(col, "")
            val_str = "" if val is None else str(val).strip()
            if val_str != "" and val_str.lower() != "none" and val_str != "—":
                filled_cols.append(col)
            else:
                empty_cols.append(col)

        if empty_cols and filled_cols:
            details_bar = QHBoxLayout()
            lbl_info = QLabel(f"📌 عرض الحقول التي تحتوي بيانات فقط ({len(filled_cols)})")
            lbl_info.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            lbl_info.setStyleSheet("color: #14372e; background: #EDF5F2; padding: 4px 10px; border-radius: 6px; border: 1px solid #B8D8CC;")
            details_bar.addWidget(lbl_info)
            details_bar.addStretch()

            self.btn_toggle_details_empty = QPushButton(f"➕ إظهار باقي الحقول الفارغة ({len(empty_cols)})")
            self.btn_toggle_details_empty.setFont(QFont("IBM Plex Sans Arabic", 9))
            self.btn_toggle_details_empty.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.btn_toggle_details_empty.setStyleSheet("""
                QPushButton {
                    background: #F8F9FA;
                    color: #344054;
                    border: 1px dashed #98A2B3;
                    border-radius: 6px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background: #EDF5F2;
                    color: #14372e;
                    border-color: #14372e;
                }
            """)
            self.btn_toggle_details_empty.clicked.connect(self._toggle_empty_details)
            details_bar.addWidget(self.btn_toggle_details_empty)
            layout.addLayout(details_bar)

        r_idx = 0
        c_idx = 0
        for col in filled_cols:
            val = self.record.get(col, "")
            val_str = str(val).strip()
            is_notes = ("Field" in col) or ("ملاحظ" in col) or ("Notes" in col)

            row_box = QFrame()
            if is_notes:
                row_box.setStyleSheet("background: #FFFBEB; border: 1px solid #FCD34D; border-radius: 8px; padding: 6px 10px;")
            else:
                row_box.setStyleSheet("background: #FFFFFF; border: 1px solid #E4E7EC; border-radius: 8px; padding: 6px 10px;")

            r_box_lay = QVBoxLayout(row_box)
            r_box_lay.setContentsMargins(0, 0, 0, 0)
            r_box_lay.setSpacing(2)

            k_row = QHBoxLayout()
            lbl_k = QLabel(col)
            lbl_k.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
            lbl_k.setStyleSheet("color: #667085;")
            k_row.addWidget(lbl_k)

            if is_notes:
                lbl_badge = QLabel("ملاحظات هامة")
                lbl_badge.setFont(QFont("IBM Plex Sans Arabic", 7, QFont.Weight.Bold))
                lbl_badge.setStyleSheet("background: #FEF3C7; color: #92400E; padding: 1px 4px; border-radius: 3px;")
                k_row.addWidget(lbl_badge)
            k_row.addStretch()
            r_box_lay.addLayout(k_row)

            lbl_v = QLabel(val_str)
            lbl_v.setFont(QFont("IBM Plex Sans Arabic", 9))
            lbl_v.setStyleSheet("color: #1B1F24;")
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_v.setWordWrap(True)
            r_box_lay.addWidget(lbl_v)

            if is_notes:
                if c_idx == 1:
                    r_idx += 1
                    c_idx = 0
                grid_lay.addWidget(row_box, r_idx, 0, 1, 2)
                r_idx += 1
                c_idx = 0
            else:
                grid_lay.addWidget(row_box, r_idx, c_idx)
                c_idx += 1
                if c_idx >= 2:
                    c_idx = 0
                    r_idx += 1

        if c_idx == 1:
            r_idx += 1
            c_idx = 0

        for col in empty_cols:
            row_box = QFrame()
            row_box.setStyleSheet("background: #FAFBFB; border: 1px solid #F2F4F7; border-radius: 8px; padding: 6px 10px;")
            r_box_lay = QVBoxLayout(row_box)
            r_box_lay.setContentsMargins(0, 0, 0, 0)
            r_box_lay.setSpacing(2)

            k_row = QHBoxLayout()
            lbl_k = QLabel(col)
            lbl_k.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
            lbl_k.setStyleSheet("color: #98A2B3;")
            k_row.addWidget(lbl_k)
            k_row.addStretch()
            r_box_lay.addLayout(k_row)

            lbl_v = QLabel("—")
            lbl_v.setFont(QFont("IBM Plex Sans Arabic", 9))
            lbl_v.setStyleSheet("color: #98A2B3;")
            r_box_lay.addWidget(lbl_v)

            row_box.hide()
            self.empty_details_boxes.append(row_box)

            grid_lay.addWidget(row_box, r_idx, c_idx)
            c_idx += 1
            if c_idx >= 2:
                c_idx = 0
                r_idx += 1

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, stretch=1)

        # 4. زر الإغلاق السفلي
        btn_close = QPushButton("إغلاق التفاصيل")
        btn_close.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet("background: #FFFFFF; color: #344054; border: 1px solid #D0D5DD; border-radius: 6px; padding: 8px 24px;")
        btn_close.clicked.connect(self.accept)

        b_box = QHBoxLayout()
        b_box.addStretch()
        b_box.addWidget(btn_close)
        layout.addLayout(b_box)

    def _toggle_empty_details(self):
        self.show_empty_details = not self.show_empty_details
        for box in self.empty_details_boxes:
            box.setVisible(self.show_empty_details)
        if self.show_empty_details:
            self.btn_toggle_details_empty.setText(f"➖ إخفاء الحقول الفارغة ({len(self.empty_details_boxes)})")
            self.btn_toggle_details_empty.setStyleSheet("""
                QPushButton {
                    background: #FEF3C7;
                    color: #92400E;
                    border: 1px solid #FCD34D;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-weight: bold;
                }
            """)
        else:
            self.btn_toggle_details_empty.setText(f"➕ إظهار باقي الحقول الفارغة ({len(self.empty_details_boxes)})")
            self.btn_toggle_details_empty.setStyleSheet("""
                QPushButton {
                    background: #F8F9FA;
                    color: #344054;
                    border: 1px dashed #98A2B3;
                    border-radius: 6px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background: #EDF5F2;
                    color: #14372e;
                    border-color: #14372e;
                }
            """)

    def _copy_all(self):
        lines = [f"{k}: {v}" for k, v in self.record.items() if not k.startswith("_adh_") and v is not None and str(v).strip() != ""]
        text = chr(10).join(lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        QMessageBox.information(self, "تم النسخ", "تم نسخ بيانات القيد بالكامل بنجاح!")

    def _copy_and_notify(self, text, msg):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        QMessageBox.information(self, "تم النسخ", msg)

    def _open_edit(self):
        self.accept()
        if self.parent_hub:
            self.parent_hub._edit_record_by_data(self.record)


class AccessHubWidget(QWidget):
    """القسم المستقل لمركز بيانات Access الموحد داخل تطبيق الحاسوب - تصميم بيانات مركّز ومريح"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # تحديد القسم الافتراضي من أول ملف محلي متاح
        init_file = "all"
        if LOCAL_DATA_DIR.exists():
            idx_p = LOCAL_DATA_DIR / "index.json"
            if idx_p.exists():
                try:
                    with open(idx_p, "r", encoding="utf-8") as f:
                        _idx = json.load(f)
                        if _idx.get("files"):
                            init_file = _idx["files"][0]["name"]
                except Exception:
                    pass

        self.active_file = init_file
        self.active_table = ""
        self.current_page = 1
        self.limit = 50
        self.sort_dir = "none"  # "none", "desc", "asc"
        self.sort_col = ""
        self.date_columns = []
        self.current_data = None
        self.loader_thread = None
        self.view_mode = "table"

        # إدارة المزامنة السحابية اللحظية التلقائية
        self.sync_worker = None
        self._start_background_sync(force=False)

        # فحص دوري في الخلفية كل 60 ثانية لجلب أي قيود جديدة من الويب أو الأجهزة الأخرى
        self.cloud_sync_timer = QTimer(self)
        self.cloud_sync_timer.setInterval(60000)
        self.cloud_sync_timer.timeout.connect(lambda: self._start_background_sync(force=False))
        self.cloud_sync_timer.start()

        self._build_ui()
        self.load_data()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ========================================================
        # 1. شريط الترويسة الرسمي (Desktop Header - Height 44px) مطابق للويب 100%
        # ========================================================
        header_frame = QFrame()
        header_frame.setFixedHeight(44)
        header_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border-bottom: 1px solid #E4E7EC;
            }
        """)
        hl = QHBoxLayout(header_frame)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(10)

        # أيقونة قاعدة البيانات بلون الغرفة
        lbl_db_icon = QLabel("🗄️")
        lbl_db_icon.setFixedSize(28, 28)
        lbl_db_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_db_icon.setStyleSheet("background: #14372e; color: #ecd58a; border-radius: 7px; font-size: 13px; font-weight: bold;")
        hl.addWidget(lbl_db_icon)

        # عنوان المركز الموحد
        lbl_title = QLabel("مركز قواعد بيانات Access الموحد")
        lbl_title.setFont(QFont("IBM Plex Sans Arabic", 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #1B1F24; font-weight: 700; border: none; background: transparent;")
        hl.addWidget(lbl_title)

        # شارة إجمالي السجلات
        self.stat_badge = QLabel("92,120 قيد")
        self.stat_badge.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.stat_badge.setStyleSheet("background: #EDF5F2; color: #14372e; border: 1px solid #CBE3DA; border-radius: 12px; padding: 2px 9px;")
        hl.addWidget(self.stat_badge)

        # شارة الاتصال السحابي المباشر
        lbl_live = QLabel("● سحابي ومباشر")
        lbl_live.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        lbl_live.setStyleSheet("background: #ECFDF3; color: #12B76A; border: 1px solid #A6F4C5; border-radius: 12px; padding: 2px 8px;")
        hl.addWidget(lbl_live)

        hl.addStretch()

        # شارة رتبة وصلاحية الجهاز الحالي
        self.user_role = "data_entry"
        self.role_badge = QLabel("👑 مدير نظام (Super Admin)")
        self.role_badge.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.role_badge.setStyleSheet("background: #FEF3F2; color: #B42318; border: 1px solid #FECDCA; border-radius: 12px; padding: 3px 10px;")
        hl.addWidget(self.role_badge)

        # زر الانتقال إلى لوحة تحكم الإدارة
        self.btn_go_admin = QPushButton("🛡️ لوحة تحكم الإدارة")
        self.btn_go_admin.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_go_admin.setStyleSheet("""
            QPushButton {
                background: #14372e;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 5px 12px;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 11.5px;
                font-weight: bold;
            }
            QPushButton:hover { background: #1a473b; }
        """)
        self.btn_go_admin.clicked.connect(self._go_to_admin)
        hl.addWidget(self.btn_go_admin)

        # زر التحديث السريع
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(30, 30)
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.setToolTip("تحديث فوري للسجلات من السحابة")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 8px;
                color: #667085;
                font-size: 13px;
            }
            QPushButton:hover { background: #F7F8FA; color: #14372e; border-color: #14372e; }
        """)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked_manual)
        hl.addWidget(self.btn_refresh)

        main_layout.addWidget(header_frame)

        # ========================================================
        # 2. شريط التنقل للأقسام والفئات (Navigator - Height 42px سطر واحد) مطابق للويب
        # ========================================================
        nav_row_frame = QFrame()
        nav_row_frame.setFixedHeight(42)
        nav_row_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border-bottom: 1px solid #E4E7EC;
            }
        """)
        nl = QHBoxLayout(nav_row_frame)
        nl.setContentsMargins(16, 0, 16, 0)
        nl.setSpacing(10)

        lbl_sec = QLabel("القسم:")
        lbl_sec.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        lbl_sec.setStyleSheet("color: #667085; border: none; background: transparent;")
        nl.addWidget(lbl_sec)

        self.combo_file = QComboBox()
        self.combo_file.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.combo_file.setStyleSheet("""
            QComboBox {
                background: #F7F8FA;
                border: 1px solid #D0D5DD;
                border-radius: 8px;
                padding: 4px 10px;
                color: #14372e;
                font-size: 11.5px;
                font-weight: bold;
                min-width: 260px;
                max-width: 340px;
            }
            QComboBox:hover { border-color: #14372e; }
            QComboBox QAbstractItemView {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                selection-background-color: #EDF5F2;
                selection-color: #14372e;
                padding: 4px;
                font-size: 11.5px;
            }
        """)
        self.combo_file.currentIndexChanged.connect(self._on_file_combo_changed)
        nl.addWidget(self.combo_file)

        # شريط الفئات الـ 11 الأفقي المنسق في سطر واحد قابل للتمرير بسلاسة
        self.subtables_scroll = QScrollArea()
        self.subtables_scroll.setFixedHeight(38)
        self.subtables_scroll.setWidgetResizable(True)
        self.subtables_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.subtables_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.subtables_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:horizontal {
                height: 4px;
                background: transparent;
            }
            QScrollBar::handle:horizontal {
                background: #CBE3DA;
                border-radius: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #14372e;
            }
        """)

        self.subtables_container = QWidget()
        self.subtables_container.setStyleSheet("background: transparent; border: none;")
        self.subtables_layout = QHBoxLayout(self.subtables_container)
        self.subtables_layout.setContentsMargins(0, 2, 0, 2)
        self.subtables_layout.setSpacing(6)
        self.subtables_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.subtables_container.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        self.subtable_btn_group = QButtonGroup(self)
        self.subtable_btn_group.setExclusive(True)

        # دعم تمرير شريط الأصناف بالماوس أفقياً بسلاسة
        def _on_subtables_wheel(event):
            delta = event.angleDelta().y() or event.angleDelta().x()
            sb = self.subtables_scroll.horizontalScrollBar()
            sb.setValue(sb.value() - delta)
            event.accept()
        self.subtables_scroll.wheelEvent = _on_subtables_wheel

        self.subtables_scroll.setWidget(self.subtables_container)
        nl.addWidget(self.subtables_scroll, stretch=1)

        main_layout.addWidget(nav_row_frame)

        # ========================================================
        # 3. شريط البحث والعمليات السريعة (Toolbar - Height 46px سطر واحد) مطابق للويب
        # ========================================================
        toolbar_frame = QFrame()
        toolbar_frame.setFixedHeight(46)
        toolbar_frame.setStyleSheet("""
            QFrame {
                background: #F7F8FA;
                border-bottom: 1px solid #E4E7EC;
            }
        """)
        tl = QHBoxLayout(toolbar_frame)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.setSpacing(12)

        # حقل البحث الرئيسي
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 بحث فوري بالاسم، النشاط، العنوان، الهاتف...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.search_input.setMinimumWidth(280)
        self.search_input.setMaximumWidth(380)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 11.5px;
                color: #1B1F24;
            }
            QLineEdit:focus { border: 1.5px solid #14372e; }
        """)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self._execute_search)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._execute_search)
        tl.addWidget(self.search_input)

        # عداد نتائج البحث
        self.lbl_matches_count = QLabel("النتائج: 92,137")
        self.lbl_matches_count.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.lbl_matches_count.setStyleSheet("color: #667085; font-size: 11px; border: none; background: transparent;")
        tl.addWidget(self.lbl_matches_count)

        # محدد فرز التواريخ الموحد (الأحدث | الأقدم | الأصلي)
        sort_frame = QFrame()
        sort_frame.setStyleSheet("background: #FFFFFF; border: 1px solid #D0D5DD; border-radius: 8px;")
        sfl = QHBoxLayout(sort_frame)
        sfl.setContentsMargins(2, 2, 2, 2)
        sfl.setSpacing(2)

        self.sort_btn_group = QButtonGroup(self)
        self.sort_btn_group.setExclusive(True)

        sort_btn_style = """
            QPushButton {
                background: transparent;
                color: #344054;
                border: none;
                border-radius: 6px;
                padding: 4px 10px;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { background: #F7F8FA; }
            QPushButton:checked {
                background: #14372e;
                color: #FFFFFF;
                font-weight: bold;
            }
        """

        self.btn_sort_desc = QPushButton("⬇️ الأحدث")
        self.btn_sort_desc.setCheckable(True)
        self.btn_sort_desc.setStyleSheet(sort_btn_style)
        self.btn_sort_desc.clicked.connect(lambda: self._set_sort_mode("desc"))
        self.sort_btn_group.addButton(self.btn_sort_desc)
        sfl.addWidget(self.btn_sort_desc)

        self.btn_sort_asc = QPushButton("⬆️ الأقدم")
        self.btn_sort_asc.setCheckable(True)
        self.btn_sort_asc.setStyleSheet(sort_btn_style)
        self.btn_sort_asc.clicked.connect(lambda: self._set_sort_mode("asc"))
        self.sort_btn_group.addButton(self.btn_sort_asc)
        sfl.addWidget(self.btn_sort_asc)

        self.btn_sort_none = QPushButton("الأصلي")
        self.btn_sort_none.setCheckable(True)
        self.btn_sort_none.setChecked(True)
        self.btn_sort_none.setStyleSheet(sort_btn_style)
        self.btn_sort_none.clicked.connect(lambda: self._set_sort_mode("none"))
        self.sort_btn_group.addButton(self.btn_sort_none)
        sfl.addWidget(self.btn_sort_none)

        tl.addWidget(sort_frame)

        # تبديل وضع العرض (جدول | بطاقات)
        view_frame = QFrame()
        view_frame.setStyleSheet("background: #FFFFFF; border: 1px solid #D0D5DD; border-radius: 8px;")
        vfl = QHBoxLayout(view_frame)
        vfl.setContentsMargins(2, 2, 2, 2)
        vfl.setSpacing(2)

        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.setExclusive(True)

        view_btn_style = """
            QPushButton {
                background: transparent;
                color: #667085;
                border: none;
                border-radius: 6px;
                padding: 4px 10px;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { background: #F7F8FA; }
            QPushButton:checked {
                background: #14372e;
                color: #FFFFFF;
                font-weight: bold;
            }
        """

        self.btn_view_table = QPushButton("目 جدول")
        self.btn_view_table.setCheckable(True)
        self.btn_view_table.setChecked(True)
        self.btn_view_table.setStyleSheet(view_btn_style)
        self.btn_view_table.clicked.connect(lambda: self._set_view_mode("table"))
        self.view_btn_group.addButton(self.btn_view_table)
        vfl.addWidget(self.btn_view_table)

        self.btn_view_cards = QPushButton("田 بطاقات")
        self.btn_view_cards.setCheckable(True)
        self.btn_view_cards.setStyleSheet(view_btn_style)
        self.btn_view_cards.clicked.connect(lambda: self._set_view_mode("cards"))
        self.view_btn_group.addButton(self.btn_view_cards)
        vfl.addWidget(self.btn_view_cards)

        tl.addWidget(view_frame)
        tl.addStretch()

        # أزرار الإجراءات
        self.btn_add = QPushButton("➕ إضافة قيد")
        self.btn_add.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: #14372e;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 11.5px;
                font-weight: bold;
            }
            QPushButton:hover { background: #1a473b; }
        """)
        self.btn_add.clicked.connect(self._on_add_clicked)
        tl.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏️ تعديل")
        self.btn_edit.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_edit.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #14372e;
                border: 1px solid #D0D5DD;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 11.5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #F7F8FA;
                border-color: #14372e;
            }
        """)
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        tl.addWidget(self.btn_edit)

        self.btn_export = QPushButton("📥 Excel")
        self.btn_export.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.DemiBold))
        self.btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #344054;
                border: 1px solid #D0D5DD;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 11.5px;
                font-weight: 600;
            }
            QPushButton:hover { background: #F7F8FA; }
        """)
        self.btn_export.clicked.connect(self._on_export_clicked)
        tl.addWidget(self.btn_export)

        main_layout.addWidget(toolbar_frame)

        # ========================================================
        # 4. شريط تمرير الحقول العرضي بالماوس (Horizontal Field Slider - Height 36px)
        # ========================================================
        self.hnav_frame = QFrame()
        self.hnav_frame.setObjectName("horizontalFieldNavBar")
        self.hnav_frame.setFixedHeight(36)
        self.hnav_frame.setStyleSheet("""
            QFrame#horizontalFieldNavBar {
                background: #FFFFFF;
                border-bottom: 1px solid #E4E7EC;
            }
        """)
        hnav_layout = QHBoxLayout(self.hnav_frame)
        hnav_layout.setContentsMargins(16, 0, 16, 0)
        hnav_layout.setSpacing(6)

        lbl_hnav = QLabel("تمرير الحقول:")
        lbl_hnav.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        lbl_hnav.setStyleSheet("color: #667085; background: transparent; border: none;")
        hnav_layout.addWidget(lbl_hnav)

        btn_field_style = """
            QPushButton {
                background: #F7F8FA;
                border: 1px solid #E4E7EC;
                border-radius: 6px;
                padding: 3px 8px;
                color: #344054;
                font-family: 'IBM Plex Sans Arabic', 'Cairo';
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #EDF5F2;
                border-color: #14372e;
                color: #14372e;
            }
        """

        btn_first_col = QPushButton(">> أول الحقول")
        btn_first_col.setStyleSheet(btn_field_style)
        btn_first_col.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_first_col.clicked.connect(lambda: self.table_widget.horizontalScrollBar().setValue(0))
        hnav_layout.addWidget(btn_first_col)

        btn_scroll_right = QPushButton("> يمين")
        btn_scroll_right.setStyleSheet(btn_field_style)
        btn_scroll_right.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_scroll_right.clicked.connect(lambda: self._scroll_columns(-300))
        hnav_layout.addWidget(btn_scroll_right)

        btn_scroll_left = QPushButton("يسار <")
        btn_scroll_left.setStyleSheet(btn_field_style)
        btn_scroll_left.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_scroll_left.clicked.connect(lambda: self._scroll_columns(300))
        hnav_layout.addWidget(btn_scroll_left)

        btn_last_col = QPushButton("آخر الحقول <<")
        btn_last_col.setStyleSheet(btn_field_style)
        btn_last_col.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_last_col.clicked.connect(lambda: self.table_widget.horizontalScrollBar().setValue(self.table_widget.horizontalScrollBar().maximum()))
        hnav_layout.addWidget(btn_last_col)

        # منزلق السحب التفاعلي للحقول بالماوس
        lbl_start = QLabel("البداية")
        lbl_start.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        lbl_start.setStyleSheet("color: #98A2B3; background: transparent; border: none;")
        hnav_layout.addWidget(lbl_start)

        self.slider_field_nav = QSlider(Qt.Orientation.Horizontal)
        self.slider_field_nav.setObjectName("fieldRangeSlider")
        self.slider_field_nav.setRange(0, 100)
        self.slider_field_nav.setToolTip("اسحب بالماوس للتنقل بين الحقول عرضياً بسلاسة")
        self.slider_field_nav.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #E4E7EC;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #14372e;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #c59b27;
                border: 2px solid #FFFFFF;
                width: 14px;
                height: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #14372e;
            }
        """)
        self.slider_field_nav.valueChanged.connect(self._on_slider_moved)
        hnav_layout.addWidget(self.slider_field_nav, stretch=1)

        lbl_end = QLabel("النهاية")
        lbl_end.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        lbl_end.setStyleSheet("color: #98A2B3; background: transparent; border: none;")
        hnav_layout.addWidget(lbl_end)

        # القفز المباشر لأي حقل
        lbl_jump = QLabel("انتقال لحقل:")
        lbl_jump.setFont(QFont("IBM Plex Sans Arabic", 8))
        lbl_jump.setStyleSheet("color: #667085; background: transparent; border: none;")
        hnav_layout.addWidget(lbl_jump)

        self.combo_jump_col = QComboBox()
        self.combo_jump_col.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.combo_jump_col.setStyleSheet("""
            QComboBox {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 2px 8px;
                color: #14372e;
                font-size: 11px;
                font-weight: bold;
                max-width: 140px;
            }
            QComboBox:hover { border-color: #14372e; }
        """)
        self.combo_jump_col.currentIndexChanged.connect(lambda idx: self._on_jump_to_col(self.combo_jump_col.currentText()))
        hnav_layout.addWidget(self.combo_jump_col)

        self.lbl_col_count = QLabel("0 حقل")
        self.lbl_col_count.setFont(QFont("IBM Plex Sans Arabic", 8, QFont.Weight.Bold))
        self.lbl_col_count.setStyleSheet("background: #FFFFFF; color: #14372e; border: 1px solid #D0D5DD; border-radius: 6px; padding: 2px 8px;")
        hnav_layout.addWidget(self.lbl_col_count)

        # ========================================================
        # 5. الجدول المركزي والبطاقات الذكية (Table & Cards Stack)
        # ========================================================
        self.table_widget = QTableWidget()
        self.table_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setShowGrid(True)
        self.table_widget.verticalHeader().setDefaultSectionSize(38)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.horizontalHeader().setStretchLastSection(False)
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table_widget.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table_widget.setFont(QFont("IBM Plex Sans Arabic", 10))
        self.table_widget.doubleClicked.connect(self._on_table_double_clicked)
        self.table_widget.cellClicked.connect(self._on_table_cell_clicked)
        self.table_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self._show_context_menu)

        self.table_widget.setStyleSheet("""
            QTableWidget {
                background: #FFFFFF;
                alternate-background-color: #FAFAFA;
                border: none;
                gridline-color: #F2F4F7;
                color: #1B1F24;
                selection-background-color: #EDF5F2;
                selection-color: #14372e;
            }
            QHeaderView::section {
                background: #EDF2EF;
                color: #14372e;
                font-family: 'IBM Plex Sans Arabic', 'Cairo';
                font-size: 11.5px;
                font-weight: bold;
                padding: 8px 12px;
                border: none;
                border-bottom: 2px solid #D0D5DD;
                border-left: 1px solid rgba(208, 213, 221, 0.5);
                cursor: pointer;
            }
            QHeaderView::section:hover {
                background: #E0EAE5;
                color: #14372e;
            }
            QTableWidget::item {
                padding: 4px 10px;
                border-bottom: 1px solid #F2F4F7;
                border-left: 1px solid rgba(242, 244, 247, 0.7);
            }
            QTableWidget::item:selected {
                background-color: #EDF5F2;
                color: #14372e;
                font-weight: bold;
            }
            QScrollBar:horizontal {
                height: 10px;
                background: #F2F4F7;
                border-top: 1px solid #E4E7EC;
            }
            QScrollBar::handle:horizontal {
                background: #CBE3DA;
                min-width: 25px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #14372e;
            }
        """)

        self.table_widget.horizontalScrollBar().valueChanged.connect(lambda v: self._sync_horizontal_slider())

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        table_layout.addWidget(self.hnav_frame)
        table_layout.addWidget(self.table_widget, stretch=1)

        # حاوية البطاقات الذكية التفاعلية (Cards View Container)
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setStyleSheet("QScrollArea { border: none; background: #F7F8FA; }")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(12, 12, 12, 12)
        self.cards_grid.setSpacing(12)
        self.cards_scroll.setWidget(self.cards_container)

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(table_container)
        self.view_stack.addWidget(self.cards_scroll)
        main_layout.addWidget(self.view_stack, stretch=1)

        # ========================================================
        # 6. شريط الترقيم والتنقل السفلي (Footer - Height 38px) مطابق للويب 100%
        # ========================================================
        pagination_frame = QFrame()
        pagination_frame.setFixedHeight(38)
        pagination_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border-top: 1px solid #E4E7EC;
            }
        """)
        pl = QHBoxLayout(pagination_frame)
        pl.setContentsMargins(16, 0, 16, 0)
        pl.setSpacing(10)

        # عداد السجلات بصيغة رشيقة ومختصرة
        self.lbl_display_range = QLabel("عرض: 1-50 من 92,137")
        self.lbl_display_range.setFont(QFont("IBM Plex Sans Arabic", 9))
        self.lbl_display_range.setStyleSheet("color: #667085; border: none; background: transparent; font-family: 'IBM Plex Sans Arabic', 'Consolas', monospace;")
        pl.addWidget(self.lbl_display_range)

        self.lbl_page_info = self.lbl_display_range # توافق

        pl.addStretch()

        # أزرار التنقل الرشيقة واختيار عدد السجلات
        self.combo_limit = QComboBox()
        self.combo_limit.addItems(["25", "50", "100", "200"])
        self.combo_limit.setCurrentText(str(self.limit))
        self.combo_limit.setToolTip("عدد السجلات لكل صفحة")
        self.combo_limit.setStyleSheet("""
            QComboBox {
                background: #F7F8FA;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 2px 8px;
                color: #14372e;
                font-family: 'IBM Plex Sans Arabic', 'Cairo';
                font-size: 11px;
                font-weight: bold;
            }
        """)
        self.combo_limit.currentIndexChanged.connect(self._on_limit_combo_changed)
        pl.addWidget(self.combo_limit)

        self.btn_prev = QPushButton("السابق >")
        self.btn_prev.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.DemiBold))
        self.btn_prev.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 6px;
                padding: 3px 10px;
                color: #1B1F24;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover:enabled { background: #F7F8FA; }
            QPushButton:disabled { color: #D0D5DD; background: #FAFAFA; border-color: #E4E7EC; }
        """)
        self.btn_prev.clicked.connect(self._prev_page)
        pl.addWidget(self.btn_prev)

        self.lbl_page_numbers = QLabel("1 / 1")
        self.lbl_page_numbers.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
        self.lbl_page_numbers.setStyleSheet("color: #14372e; font-family: monospace; font-size: 11.5px; border: none; background: transparent; padding: 0 4px;")
        pl.addWidget(self.lbl_page_numbers)

        self.btn_next = QPushButton("< التالي")
        self.btn_next.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.DemiBold))
        self.btn_next.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #E4E7EC;
                border-radius: 6px;
                padding: 3px 10px;
                color: #1B1F24;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover:enabled { background: #F7F8FA; }
            QPushButton:disabled { color: #D0D5DD; background: #FAFAFA; border-color: #E4E7EC; }
        """)
        self.btn_next.clicked.connect(self._next_page)
        pl.addWidget(self.btn_next)

        main_layout.addWidget(pagination_frame)


    def _go_to_admin(self):
        """الانتقال إلى لوحة تحكم الإدارة من الترويسة"""
        w = self.window()
        if hasattr(w, '_switch_workspace_page'):
            w._switch_workspace_page(2)

    def _set_sort_mode(self, mode: str):
        """تطبيق وضع الفرز الزمني (الأحدث / الأقدم / الأصلي)"""
        self.sort_dir = mode
        if mode == "none":
            self.sort_col = "date_auto"
        self.current_page = 1
        self.load_data()

    def _on_limit_combo_changed(self):
        """تغيير عدد السجلات المعروضة في الصفحة"""
        try:
            val = int(self.combo_limit.currentText())
            if val != self.limit:
                self.limit = val
                self.current_page = 1
                self.load_data()
        except Exception:
            pass

    def _apply_user_role(self):
        """تطبيق قيود الصلاحيات وشارات الواجهة حسب رتبة الجهاز"""
        role = getattr(self, "user_role", "data_entry")
        if role == "admin":
            self.role_badge.setText("👑 مدير نظام (كامل الصلاحيات)")
            self.role_badge.setStyleSheet("background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px;")
            self.btn_add.show()
            self.btn_edit.show()
        elif role == "supervisor":
            self.role_badge.setText("🛡️ مشرف تدقيق (تعديل واسترجاع وحذف)")
            self.role_badge.setStyleSheet("background: #EDE9FE; color: #5B21B6; border: 1px solid #C4B5FD; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px;")
            self.btn_add.show()
            self.btn_edit.show()
        elif role == "viewer":
            self.role_badge.setText("👁️ مستعلم فقط (للقراءة والاستعلام)")
            self.role_badge.setStyleSheet("background: #DBEAFE; color: #1E40AF; border: 1px solid #93C5FD; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px;")
            self.btn_add.hide()
            self.btn_edit.hide()
        else: # data_entry
            self.role_badge.setText("✏️ مدخل بيانات (إضافة وتعديل)")
            self.role_badge.setStyleSheet("background: #D1FAE5; color: #065F46; border: 1px solid #6EE7B7; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px;")
            self.btn_add.show()
            self.btn_edit.show()

    def _on_table_double_clicked(self, index):
        """عند النقر المزدوج: فتح نافذة تفاصيل القيد الكاملة"""
        self._show_record_details(index.row())

    def _on_table_cell_clicked(self, row, col):
        """عند النقر على اسم الشخص أو التاجر أو البطاقة: فتح تفاصيل القيد التي تحتوي بيانات فقط"""
        header_item = self.table_widget.horizontalHeaderItem(col)
        if header_item:
            h_text = header_item.text()
            name_keywords = ('ArabicName', 'اسم التاجر', 'اسم الشركة', 'اسم الفندق', 'اسم الصيدلية', 'اسم المعمل', 'اسم الدلال', 'الاسم التجاري', 'الإسم التجاري', 'صاحب')
            if any(k in h_text for k in name_keywords):
                self._show_record_details(row)

    def _subtable_btn_style(self):
        return """
            QPushButton {
                background: #FFFFFF;
                color: #344054;
                border: 1px solid #D0D5DD;
                border-radius: 8px;
                padding: 4px 11px;
                font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Segoe UI';
                font-size: 11.5px;
                font-weight: 600;
                white-space: nowrap;
            }
            QPushButton:hover {
                background: #F7F8FA;
                color: #14372e;
                border-color: #14372e;
            }
            QPushButton:checked {
                background: #14372e;
                color: #FFFFFF;
                border: 1px solid #14372e;
                font-weight: bold;
            }
        """

    def load_data(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳")

        query = self.search_input.text().strip()
        self.loader_thread = DataLoaderThread(
            self.active_file,
            self.active_table,
            query,
            self.current_page,
            self.limit,
            sort_dir=self.sort_dir,
            sort_col=self.sort_col
        )
        self.loader_thread.data_loaded.connect(self._on_data_loaded)
        self.loader_thread.error_occurred.connect(self._on_data_error)
        self.loader_thread.start()

    def _on_data_loaded(self, data):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄")
        self.current_data = data

        # تحديد وتطبيق الصلاحية المؤسسية لهذا الجهاز (RBAC Engine)
        role = data.get("currentRole") or data.get("current_role")
        if not role:
            my_guid = get_desktop_machine_guid()
            roles_map = data.get("roles", {})
            if my_guid in roles_map and isinstance(roles_map[my_guid], dict):
                role = roles_map[my_guid].get("role", "data_entry")
            elif my_guid in roles_map and isinstance(roles_map[my_guid], str):
                role = roles_map[my_guid]
            else:
                role = "data_entry"
        self.user_role = role
        self._apply_user_role()

        # 1. تحديث قائمة الأقسام (الملفات) في الـ ComboBox مرة واحدة
        files = data.get("files", [])
        allowed_sections = data.get("allowedSections") or data.get("allowed_sections")
        if allowed_sections and isinstance(allowed_sections, list) and len(allowed_sections) > 0:
            files = [f for f in files if f.get("name") in allowed_sections]
        if files and self.combo_file.count() == 0:
            self.combo_file.blockSignals(True)
            for f in files:
                fname = f["name"]
                self.combo_file.addItem(f"📁 {fname}", fname)
            # إضافة خيار الدمج الشامل
            self.combo_file.addItem("🌐 الدمج الشامل (كافة الأقسام)", "all")

            # تحديد القسم النشط
            cur_f = data.get("active_file", self.active_file)
            for i in range(self.combo_file.count()):
                if self.combo_file.itemData(i) == cur_f:
                    self.combo_file.setCurrentIndex(i)
                    break
            self.combo_file.blockSignals(False)

        # 2. تحديث شريط الفئات الأفقي الأنيق في سطر واحد مطابق للويب
        while self.subtables_layout.count():
            item = self.subtables_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tables_list = ["all"] + [t for t in sort_tables_by_priority(data.get("available_tables", [])) if t != "all"]
        active_tbl = data.get("active_table", self.active_table)
        self.active_table = active_tbl

        grand_total = data.get("total_records", 92120)

        # منع تكرار بطاقات الفئات (مثل دلالين والدلالين)
        seen_titles = set()
        deduped_tables = []
        for tbl in tables_list:
            icon, display_title = TABLE_DISPLAY_META.get(tbl, ("🏷️", tbl))
            if display_title in seen_titles:
                continue
            seen_titles.add(display_title)
            deduped_tables.append((tbl, icon, display_title))

        for tbl, icon, display_title in deduped_tables:
            if tbl == "all":
                cnt = grand_total
                lbl_text = f"🌟 جميع الأصناف  {cnt:,}"
                is_active = (active_tbl == "all")
            else:
                lookup_keys = ["الدلالين", "دلالين"] if tbl in ("الدلالين", "دلالين") else [tbl]
                if self.active_file == "all":
                    cnt = sum(
                        f.get("table_counts", {}).get(k, 0)
                        for f in data.get("files", [])
                        for k in lookup_keys
                    )
                else:
                    f_obj = next((f for f in data.get("files", []) if f["name"] == self.active_file), None)
                    cnt = sum(f_obj.get("table_counts", {}).get(k, 0) for k in lookup_keys) if f_obj else 0
                lbl_text = f"{icon} {display_title}  {cnt:,}"
                is_active = (active_tbl in lookup_keys)

            btn = QPushButton(lbl_text)
            btn.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
            btn.setCheckable(True)
            btn.setChecked(is_active)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setToolTip(f"عرض جدول {display_title} بالكامل ({cnt:,} قيد)")
            btn.setStyleSheet(self._subtable_btn_style())
            btn.clicked.connect(lambda checked, t=tbl: self._on_subtable_clicked(t))
            self.subtable_btn_group.addButton(btn)
            self.subtables_layout.addWidget(btn)

        self.subtables_layout.addStretch()

        # 3. تعبئة الجدول بالحقول والمعلومات الأصلية 100% من الملف بدون أي تغيير إطلاقاً (مع تسريع الرسم الفائق)
        cols = data.get("columns", [])
        rows = data.get("rows", [])

        self.table_widget.setUpdatesEnabled(False)
        self.table_widget.blockSignals(True)
        try:
            display_cols = ["#"]
            if self.active_file == "all":
                display_cols.append("القسم")
            if self.active_table == "all":
                display_cols.append("الصنف / الجدول")

            # ترتيب الحقول بالأولوية الذكية لمطابقة الويب
            cols = sort_columns_by_priority(cols)

            for c in cols:
                header_txt = c
                if c == data.get("sort_col"):
                    if self.sort_dir == "desc":
                        header_txt = f"{c} ⬇️"
                    elif self.sort_dir == "asc":
                        header_txt = f"{c} ⬆️"
                display_cols.append(header_txt)

            display_cols.append("الإجراءات")

            self.table_widget.setColumnCount(len(display_cols))
            self.table_widget.setHorizontalHeaderLabels(display_cols)
            self.table_widget.setRowCount(len(rows))

            actions_col_idx = len(display_cols) - 1

            cur_p = data.get("page", 1)
            lim = data.get("limit", self.limit)

            for r_idx, row in enumerate(rows):
                self.table_widget.setRowHeight(r_idx, 38)
                row_num = (cur_p - 1) * lim + r_idx + 1
                c_offset = 0

                # العمود الأول: # رقم التسلسل
                item_num = QTableWidgetItem(str(row_num))
                item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_num.setForeground(QColor("#98A2B3"))
                fnt_num = QFont("Consolas", 9)
                fnt_num.setBold(True)
                item_num.setFont(fnt_num)
                self.table_widget.setItem(r_idx, c_offset, item_num)
                c_offset += 1

                if self.active_file == "all":
                    src_file = str(row.get("_adh_file", ""))
                    src_item = QTableWidgetItem(get_short_file_name(src_file))
                    src_item.setForeground(QColor("#14372e"))
                    src_item.setBackground(QColor("#F0FDF4"))
                    src_item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                    src_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    src_item.setToolTip(src_file)
                    self.table_widget.setItem(r_idx, c_offset, src_item)
                    c_offset += 1

                if self.active_table == "all":
                    tbl_meta = TABLE_DISPLAY_META.get(row.get("_adh_table"), ("🏷️", row.get("_adh_table", "")))
                    tbl_item = QTableWidgetItem(f"{tbl_meta[0]} {tbl_meta[1]}")
                    tbl_item.setForeground(QColor("#92400E"))
                    tbl_item.setBackground(QColor("#FEF3C7"))
                    tbl_item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                    tbl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table_widget.setItem(r_idx, c_offset, tbl_item)
                    c_offset += 1

                for c_idx, col in enumerate(cols):
                    val = row.get(col, "")
                    val_str = "" if val is None else str(val).strip()
                    col_lower = col.lower()

                    if not val_str or val_str.lower() == "none":
                        # الخلية الفارغة: شحطة رمادية محايدة بالمنتصف مطابقة للويب
                        item = QTableWidgetItem("—")
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        item.setForeground(QColor("#D0D5DD"))
                        item.setFont(QFont("Consolas", 10))
                    else:
                        item = QTableWidgetItem(val_str)
                        # تمييز وتنسيق درجات التجار بشارات وألوان مطابقة للويب
                        if col in ('Class', 'الصنف', 'الدرجة'):
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            if "ممتاز" in val_str:
                                item.setText(f"⭐ {val_str}")
                                item.setForeground(QColor("#B45309"))
                                item.setBackground(QColor("#FFFBEB"))
                                item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                            elif "أول" in val_str or "الاول" in val_str:
                                item.setText(f"🥇 {val_str}")
                                item.setForeground(QColor("#065F46"))
                                item.setBackground(QColor("#ECFDF5"))
                                item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                            elif "ثان" in val_str:
                                item.setText(f"🥈 {val_str}")
                                item.setForeground(QColor("#1E40AF"))
                                item.setBackground(QColor("#EFF6FF"))
                                item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                            elif "ثالث" in val_str:
                                item.setText(f"🥉 {val_str}")
                                item.setForeground(QColor("#6B21A8"))
                                item.setBackground(QColor("#FAF5FF"))
                                item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                            elif "رابع" in val_str:
                                item.setText(f"4️⃣ {val_str}")
                                item.setForeground(QColor("#334155"))
                                item.setBackground(QColor("#F1F5F9"))
                                item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                            else:
                                item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                                item.setForeground(QColor("#14372e"))
                        elif col in ('ArabicName', 'اسم التاجر', 'الاسم التجاري', 'الإسم التجاري', 'اسم الشركة', 'اسم الفندق', 'اسم الصيدلية', 'اسم المعمل', 'اسم الدلال', 'صاحب الاسم التجاري', 'اسم صاحب الفندق', 'اسم صاحب المعمل', 'اسم صاحب المكتب', 'اسم صاحب الصيدلية', 'اسم صاحب الشركة', 'الإسم', 'EnglishName'):
                            item.setForeground(QColor("#14372e"))
                            item.setFont(QFont("IBM Plex Sans Arabic", 9, QFont.Weight.Bold))
                            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        elif col in ('Mobile', 'الهاتف', 'رقم الهاتف', 'Phone'):
                            item.setForeground(QColor("#344054"))
                            item.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        elif any(k in col_lower for k in ('activity', 'address', 'العمل', 'النشاط', 'العنوان', 'محل', 'منطقة')):
                            item.setForeground(QColor("#344054"))
                            item.setFont(QFont("IBM Plex Sans Arabic", 9))
                            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        elif col_lower in ('id', 'idno', 'id_no', 'stampno', 'commercialno', 'renewalno', 'ت') or any(k in col_lower for k in DATE_KEYWORDS):
                            item.setForeground(QColor("#475467"))
                            item.setFont(QFont("IBM Plex Sans Arabic", 9))
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        else:
                            item.setForeground(QColor("#344054"))
                            item.setFont(QFont("IBM Plex Sans Arabic", 9))
                            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                    self.table_widget.setItem(r_idx, c_idx + c_offset, item)

                # عمود الإجراءات السريعة (تفاصيل وتعديل)
                act_widget = QWidget()
                act_lay = QHBoxLayout(act_widget)
                act_lay.setContentsMargins(4, 2, 4, 2)
                act_lay.setSpacing(4)
                act_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

                btn_eye = QPushButton("👁️")
                btn_eye.setToolTip("عرض تفاصيل القيد بالكامل")
                btn_eye.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn_eye.setStyleSheet("QPushButton { background: #FFFFFF; border: 1px solid #D0D5DD; border-radius: 4px; padding: 2px 6px; font-size: 11px; } QPushButton:hover { background: #F2F4F7; color: #14372e; border-color: #14372e; }")
                btn_eye.clicked.connect(lambda _, r=row: self._show_record_details_by_data(r))
                act_lay.addWidget(btn_eye)

                if getattr(self, "user_role", "data_entry") != "viewer":
                    btn_edit = QPushButton("✏️")
                    btn_edit.setToolTip("تعديل هذا القيد")
                    btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    btn_edit.setStyleSheet("QPushButton { background: #FFFFFF; border: 1px solid #D0D5DD; border-radius: 4px; padding: 2px 6px; font-size: 11px; } QPushButton:hover { background: #ECFDF5; color: #065F46; border-color: #10B981; }")
                    btn_edit.clicked.connect(lambda _, r=row: self._edit_record_by_data(r))
                    act_lay.addWidget(btn_edit)

                self.table_widget.setCellWidget(r_idx, actions_col_idx, act_widget)

            # ضبط أبعاد وعرض الأعمدة الذكي
            self.table_widget.setColumnWidth(0, 48) # عمود #
            for c in range(1, self.table_widget.columnCount()):
                h_item = self.table_widget.horizontalHeaderItem(c)
                h_text = h_item.text() if h_item else ""
                if "القسم" in h_text or "الملف" in h_text:
                    self.table_widget.setColumnWidth(c, 160)
                elif "الصنف" in h_text or "الجدول" in h_text:
                    self.table_widget.setColumnWidth(c, 130)
                elif "الإجراءات" in h_text:
                    self.table_widget.setColumnWidth(c, 85)
                elif any(k in h_text for k in ("ArabicName", "اسم التاجر", "اسم الشركة", "اسم الفندق", "اسم الصيدلية", "اسم المعمل", "اسم الدلال", "صاحب")):
                    self.table_widget.setColumnWidth(c, 210)
                elif any(k in h_text for k in ("الإسم التجاري", "الاسم التجاري", "Commercial")):
                    self.table_widget.setColumnWidth(c, 190)
                elif any(k in h_text for k in ("العمل", "Activity", "النشاط")):
                    self.table_widget.setColumnWidth(c, 220)
                elif any(k in h_text for k in ("العنوان", "Address")):
                    self.table_widget.setColumnWidth(c, 190)
                elif any(k in h_text for k in ("هاتف", "Mobile", "Phone")):
                    self.table_widget.setColumnWidth(c, 130)
                elif any(k in h_text for k in ("تاريخ", "تأريخ", "Date")):
                    self.table_widget.setColumnWidth(c, 115)
                elif any(k in h_text for k in ("ID", "رقم", "No")):
                    self.table_widget.setColumnWidth(c, 100)
                else:
                    curr_w = self.table_widget.columnWidth(c)
                    if curr_w < 110:
                        self.table_widget.setColumnWidth(c, 110)
                    elif curr_w > 320:
                        self.table_widget.setColumnWidth(c, 320)
        finally:
            self.table_widget.blockSignals(False)
            self.table_widget.setUpdatesEnabled(True)

        # 4. تحديث معلومات الترقيم وشريط الحالة السفلي مطابقاً للويب 100%
        cur_p = data.get("page", 1)
        tot_p = data.get("total_pages", 1)
        matches = data.get("total_matches", 0)
        lim = data.get("limit", self.limit)

        start_row = (cur_p - 1) * lim + 1 if len(rows) > 0 else 0
        end_row = min(cur_p * lim, matches) if len(rows) > 0 else 0
        self.lbl_display_range.setText(f"عرض: {start_row:,}-{end_row:,} من {matches:,}")
        self.lbl_page_numbers.setText(f"\u200E{cur_p} / {tot_p}\u200E")
        self.btn_prev.setEnabled(cur_p > 1)
        self.btn_next.setEnabled(cur_p < tot_p)

        self.lbl_matches_count.setText(f"النتائج: {matches:,}")
        tot_all = data.get("total_records", 92120)
        self.stat_badge.setText(f"{tot_all:,} قيد")

        # أزرار فرز التاريخ
        if hasattr(self, 'btn_sort_desc'):
            if self.sort_dir == "desc":
                self.btn_sort_desc.setChecked(True)
            elif self.sort_dir == "asc":
                self.btn_sort_asc.setChecked(True)
            else:
                self.btn_sort_none.setChecked(True)

        # تحديث شريط تمرير الحقول وقائمة القفز المباشر
        cols = data.get("columns", [])
        self.lbl_col_count.setText(f"{len(cols)} حقل")
        self.combo_jump_col.blockSignals(True)
        self.combo_jump_col.clear()
        self.combo_jump_col.addItem("اختر حقل...")
        for c in cols:
            self.combo_jump_col.addItem(c)
        self.combo_jump_col.blockSignals(False)

        # ملء البطاقات الذكية التفاعلية (Cards View)
        while self.cards_grid.count():
            it = self.cards_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        cur_p = data.get("page", 1)
        lim = data.get("limit", 50)
        cards_per_row = 3
        for idx, row in enumerate(rows):
            row_num = (cur_p - 1) * lim + idx + 1
            card = RecordCardWidget(row, row_num, self, self.cards_container)
            grid_r = idx // cards_per_row
            grid_c = idx % cards_per_row
            self.cards_grid.addWidget(card, grid_r, grid_c)

    def _on_data_error(self, err):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄")
        QMessageBox.warning(self, "تنبيه", f"تعذر استرجاع البيانات: {err}")

    def _on_file_combo_changed(self):
        val = self.combo_file.currentData()
        if val and val != self.active_file:
            self.active_file = val
            self.active_table = ""
            self.current_page = 1
            self.load_data()

    def _on_subtable_clicked(self, tbl):
        self.active_table = tbl
        self.current_page = 1
        self.load_data()

    def _on_search_text_changed(self):
        self.search_timer.start(250)

    def _execute_search(self):
        self.current_page = 1
        self.load_data()

    def _on_search_changed(self):
        self._execute_search()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def _next_page(self):
        self.current_page += 1
        self.load_data()

    def _on_header_clicked(self, logical_index):
        """الفرز المباشر بالنقر على رأس أي عمود"""
        if not self.current_data:
            return
        cols = self.current_data.get("columns", [])
        c_offset = 1 if self.active_file == "all" else 0
        if logical_index < c_offset:
            return
        col_name = cols[logical_index - c_offset]

        if self.sort_col == col_name:
            if self.sort_dir == "desc":
                self.sort_dir = "asc"
            elif self.sort_dir == "asc":
                self.sort_dir = "none"
            else:
                self.sort_dir = "desc"
        else:
            self.sort_col = col_name
            self.sort_dir = "desc"

        self.current_page = 1
        self.load_data()

    def _reset_sort(self):
        self.sort_dir = "none"
        self.sort_col = ""
        self.current_page = 1
        self.load_data()

    def _open_tools_menu(self):
        """قائمة منسدلة أنيقة لإدارة الحقول والفرز دون تشويه الواجهة"""
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu.setFont(QFont("IBM Plex Sans Arabic", 9))
        menu.setStyleSheet("""
            QMenu {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
                color: #344054;
            }
            QMenu::item:selected {
                background: #EDF5F2;
                color: #14372e;
                font-weight: bold;
            }
        """)

        act_add_col = None
        if getattr(self, "user_role", "data_entry") == "admin":
            act_add_col = menu.addAction("➕ إضافة حقل جديد لهذا القسم")
            menu.addSeparator()
        act_sort_desc = menu.addAction("⬇️ فرز زمني (من الأحدث للأقدم)")
        act_sort_asc = menu.addAction("⬆️ فرز زمني (من الأقدم للأحدث)")
        act_reset_sort = menu.addAction("🔄 الترتيب الأصلي (إلغاء الفرز)")

        pos = self.btn_tools.mapToGlobal(self.btn_tools.rect().bottomRight())
        action = menu.exec(pos)
        if action == act_add_col:
            self._on_add_column_clicked()
        elif action == act_sort_desc:
            self.sort_dir = "desc"
            self.sort_col = "date_auto"
            self.current_page = 1
            self.load_data()
        elif action == act_sort_asc:
            self.sort_dir = "asc"
            self.sort_col = "date_auto"
            self.current_page = 1
            self.load_data()
        elif action == act_reset_sort:
            self._reset_sort()

    def _show_context_menu(self, pos):
        """قائمة الزر الأيمن المخصصة للجدول (تم سحب خيار الحذف لنظام الأدمن)"""
        item = self.table_widget.itemAt(pos)
        if not item or not self.current_data or not self.current_data.get("rows"):
            return
        row_idx = self.table_widget.row(item)
        if row_idx < 0 or row_idx >= len(self.current_data["rows"]):
            return

        self.table_widget.selectRow(row_idx)
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu.setFont(QFont("IBM Plex Sans Arabic", 9))
        menu.setStyleSheet("""
            QMenu {
                background: #FFFFFF;
                border: 1px solid #D0D5DD;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
                color: #344054;
            }
            QMenu::item:selected {
                background: #EDF5F2;
                color: #14372e;
                font-weight: bold;
            }
        """)

        act_details = menu.addAction("🔍 عرض تفاصيل القيد بالكامل")
        menu.addSeparator()
        act_edit = None
        if getattr(self, "user_role", "data_entry") != "viewer":
            act_edit = menu.addAction("✏️ تعديل هذا القيد")
            menu.addSeparator()
        act_copy = menu.addAction("📋 نسخ بيانات السجل")

        action = menu.exec(self.table_widget.viewport().mapToGlobal(pos))
        if action == act_details:
            self._show_record_details(row_idx)
        elif action == act_edit:
            self._on_edit_clicked()
        elif action == act_copy:
            self._copy_record_to_clipboard(row_idx)

    def _show_record_details(self, row_idx):
        if not self.current_data or not self.current_data.get("rows"):
            return
        row = self.current_data["rows"][row_idx]
        cols = self.current_data.get("columns", [])
        dlg = RecordDetailsDialog(row, cols, title=f"تفاصيل القيد - جدول {self.active_table}", parent=self)
        dlg.exec()

    def _copy_record_to_clipboard(self, row_idx):
        if not self.current_data or not self.current_data.get("rows"):
            return
        row = self.current_data["rows"][row_idx]
        cols = self.current_data.get("columns", [])
        lines = []
        for c in cols:
            val = row.get(c, "")
            lines.append(f"{c}: {val}")
        text = "\n".join(lines)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            QMessageBox.information(self, "تم النسخ", "تم نسخ بيانات القيد بالكامل إلى الحافظة بنجاح.")

    def _start_background_sync(self, force=False):
        """بدء عملية فحص ومزامنة الطفرات السحابية في الخلفية بدون تجميد الواجهة"""
        if self.sync_worker and self.sync_worker.isRunning():
            return
        self.sync_worker = CloudSyncWorker(force=force)
        self.sync_worker.sync_completed.connect(self._on_sync_worker_finished)
        self.sync_worker.start()

    def _on_sync_worker_finished(self, updated: bool):
        """عند اكتمال مزامنة الخلفية، إذا تم جلب قيود جديدة نقوم بتحديث الجدول فوراً"""
        if updated:
            self.load_data()

    def _on_refresh_clicked_manual(self):
        """تحديث فوري وإجباري عند الضغط على زر التحديث، يفحص السحابة والقرص المحلي"""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳")
        self.btn_refresh.setToolTip("جاري جلب أحدث السجلات من السحابة...")

        def on_done(updated):
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("🔄")
            self.btn_refresh.setToolTip("تحديث فوري للسجلات من السحابة")
            self.load_data()

        if self.sync_worker and self.sync_worker.isRunning():
            self.sync_worker.wait(1000)

        self.sync_worker = CloudSyncWorker(force=True)
        self.sync_worker.sync_completed.connect(on_done)
        self.sync_worker.start()

    def _apply_local_add(self, record: dict):
        """تخزين وتثبيت القيد المضاف محلياً فوراً وتحديث الذاكرة"""
        local_dir = get_local_data_dir()
        mut = load_local_mutations(local_dir)
        adds = mut.setdefault("adds", [])
        rec_id = record.get("_adh_id")
        if rec_id:
            adds = [a for a in adds if a.get("_adh_id") != rec_id]
        adds.insert(0, record)
        mut["adds"] = adds
        mut["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_local_mutations(mut, local_dir)

    def _apply_local_update(self, record_id: str, updates: dict):
        """تحديث بيانات القيد محلياً فوراً"""
        local_dir = get_local_data_dir()
        mut = load_local_mutations(local_dir)
        updated_in_adds = False
        for a in mut.get("adds", []):
            if a.get("_adh_id") == record_id:
                a.update(updates)
                a["_adh_updated_at"] = datetime.now(timezone.utc).isoformat()
                updated_in_adds = True
                break
        if not updated_in_adds:
            up_map = mut.setdefault("updates", {})
            cur = up_map.get(record_id, {})
            cur.update(updates)
            cur["_adh_updated_at"] = datetime.now(timezone.utc).isoformat()
            up_map[record_id] = cur
        mut["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_local_mutations(mut, local_dir)

    def _apply_local_delete(self, record_id: str):
        """حذف القيد محلياً فوراً"""
        local_dir = get_local_data_dir()
        mut = load_local_mutations(local_dir)
        mut["adds"] = [a for a in mut.get("adds", []) if a.get("_adh_id") != record_id]
        deletes = mut.setdefault("deletes", [])
        if record_id not in deletes:
            deletes.append(record_id)
        if record_id in mut.get("updates", {}):
            del mut["updates"][record_id]
        mut["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_local_mutations(mut, local_dir)

    def _apply_local_add_column(self, file_name: str, table_name: str, col_name: str):
        """إضافة حقل جديد محلياً وتعميمه فورياً"""
        local_dir = get_local_data_dir()
        mut = load_local_mutations(local_dir)
        ac = mut.setdefault("added_columns", {})
        key = f"{file_name}_{table_name}"
        col_list = ac.setdefault(key, [])
        if col_name not in col_list:
            col_list.append(col_name)
        dc = mut.setdefault("deleted_columns", {})
        if key in dc and col_name in dc[key]:
            dc[key].remove(col_name)
        mut["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_local_mutations(mut, local_dir)

    def _apply_local_del_column(self, file_name: str, table_name: str, col_name: str):
        """حذف حقل محلياً فورياً"""
        local_dir = get_local_data_dir()
        mut = load_local_mutations(local_dir)
        dc = mut.setdefault("deleted_columns", {})
        key = f"{file_name}_{table_name}"
        col_list = dc.setdefault(key, [])
        if col_name not in col_list:
            col_list.append(col_name)
        ac = mut.setdefault("added_columns", {})
        if key in ac and col_name in ac[key]:
            ac[key].remove(col_name)
        mut["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_local_mutations(mut, local_dir)

    def _on_add_column_clicked(self):
        """إضافة حقل جديد إلى الجدول"""
        if not self.current_data:
            return
        target_file = self.active_file if self.active_file != "all" else (self.current_data["files"][0]["name"] if self.current_data.get("files") else "الاسم التجاري 2025 - 2026")
        dlg = AddColumnDialog(self.active_table, target_file, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_col = dlg.get_column_name()
            try:
                my_guid = get_desktop_machine_guid()
                r = requests.post(CLOUD_API_URL, json={
                    "file": target_file,
                    "table": self.active_table,
                    "action": "ADD_COLUMN",
                    "columnName": new_col,
                    "guid": my_guid,
                }, headers={"x-machine-guid": my_guid}, timeout=10)
                if r.status_code == 200:
                    self._apply_local_add_column(target_file, self.active_table, new_col)
                    QMessageBox.information(self, "نجاح", f"تمت إضافة الحقل '{new_col}' سحابياً بنجاح وتعميمه للجميع.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشلت إضافة الحقل: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_del_column_clicked(self):
        """حذف حقل من الجدول"""
        if not self.current_data or not self.current_data.get("columns"):
            QMessageBox.information(self, "تنبيه", "لا توجد حقول لحذفها في هذا الجدول.")
            return

        cols = self.current_data["columns"]
        dlg = DeleteColumnDialog(self.active_table, cols, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            col_to_del = dlg.get_selected_column()
            target_file = self.active_file if self.active_file != "all" else (self.current_data["files"][0]["name"] if self.current_data.get("files") else "الاسم التجاري 2025 - 2026")
            try:
                my_guid = get_desktop_machine_guid()
                r = requests.post(CLOUD_API_URL, json={
                    "file": target_file,
                    "table": self.active_table,
                    "action": "DELETE_COLUMN",
                    "columnName": col_to_del,
                    "guid": my_guid,
                }, headers={"x-machine-guid": my_guid}, timeout=10)
                if r.status_code == 200:
                    self._apply_local_del_column(target_file, self.active_table, col_to_del)
                    QMessageBox.information(self, "نجاح", f"تم حذف الحقل '{col_to_del}' سحابياً بنجاح.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل حذف الحقل: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_add_clicked(self):
        """إضافة قيد جديد مع إمكانية تحديد الملف إذا كان في وضع الدمج الشامل"""
        if getattr(self, "user_role", "data_entry") == "viewer":
            QMessageBox.warning(self, "صلاحية محجوبة", "عفواً، لا تملك صلاحية إضافة قيود.\nحساب هذا الجهاز مفعل بصلاحية (مستعلم فقط - للقراءة والاستعلام).")
            return
        if not self.current_data or not self.current_data.get("columns"):
            return
        cols = self.current_data["columns"]
        files = self.current_data.get("files", [])
        dlg = RecordFormDialog(f"إضافة قيد جديد في جدول ({self.active_table})", cols, files_list=files if self.active_file == "all" else None, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            target_file = dlg.get_target_file() or (self.active_file if self.active_file != "all" else self.current_data["files"][0]["name"])
            try:
                my_guid = get_desktop_machine_guid()
                r = requests.post(CLOUD_API_URL, json={
                    "file": target_file,
                    "table": self.active_table,
                    "record": new_data,
                    "guid": my_guid,
                }, headers={"x-machine-guid": my_guid}, timeout=10)
                if r.status_code == 200:
                    resp_json = {}
                    try:
                        resp_json = r.json()
                    except Exception:
                        pass
                    created_record = resp_json.get("record")
                    if not created_record or not isinstance(created_record, dict):
                        import time, random
                        created_record = dict(new_data)
                        created_record["_adh_id"] = f"{target_file}_{self.active_table}_{int(time.time()*1000)}_{random.randint(1000, 9999)}"
                        created_record["_adh_file"] = target_file
                        created_record["_adh_table"] = self.active_table
                        created_record["_adh_created_at"] = datetime.now(timezone.utc).isoformat()

                    self._apply_local_add(created_record)
                    QMessageBox.information(self, "نجاح", "تمت إضافة القيد بنجاح ومزامنته سحابياً لجميع الأجهزة.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل الحفظ: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_edit_clicked(self):
        row_idx = self.table_widget.currentRow()
        if row_idx < 0 or not self.current_data or not self.current_data.get("rows"):
            QMessageBox.information(self, "تنبيه", "يرجى تحديد السجل المراد تعديله أولاً.")
            return

        if getattr(self, "user_role", "data_entry") == "viewer":
            self._show_record_details(row_idx)
            return

        row_data = self.current_data["rows"][row_idx]
        cols = self.current_data["columns"]
        dlg = RecordFormDialog(f"تعديل القيد (الملف: {row_data.get('_adh_file')})", cols, initial_data=row_data, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updates = dlg.get_data()
            try:
                my_guid = get_desktop_machine_guid()
                r = requests.put(CLOUD_API_URL, json={
                    "file": row_data["_adh_file"],
                    "table": row_data["_adh_table"],
                    "id": row_data["_adh_id"],
                    "updates": updates,
                    "guid": my_guid,
                }, headers={"x-machine-guid": my_guid}, timeout=10)
                if r.status_code == 200:
                    self._apply_local_update(row_data["_adh_id"], updates)
                    QMessageBox.information(self, "نجاح", "تم تعديل السجل ومزامنته فورياً مع كافة الموظفين.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل التعديل: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _on_delete_clicked(self):
        QMessageBox.information(
            self, "إشعار أمني - غرفة تجارة كربلاء",
            "تم حظر وتجريد تطبيق سطح المكتب من صلاحية الحذف المباشر لحماية سجلات التجار والدلالين من الحذف العرضي.\n\n"
            "يمكن إجراء عمليات الحذف وإدارة الأقسام والحقول حصرياً عبر لوحة الإدارة المركزية (Admin Dashboard) للمشرفين المصرح لهم."
        )

    def _on_export_clicked(self):
        if not self.current_data or not self.current_data.get("rows"):
            QMessageBox.information(self, "تنبيه", "لا توجد سجلات لتصديرها.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف Excel / CSV", f"{self.active_file}_{self.active_table}.csv", "ملف CSV (*.csv)")
        if path:
            try:
                cols = self.current_data["columns"]
                lines = [",".join([f'"{c}"' for c in cols])]
                for r in self.current_data["rows"]:
                    row_vals = []
                    for c in cols:
                        v = str(r.get(c, "") or "").replace('"', '""')
                        row_vals.append(f'"{v}"')
                    lines.append(",".join(row_vals))

                with open(path, "w", encoding="utf-8-sig") as f:
                    f.write("\n".join(lines))
                QMessageBox.information(self, "نجاح", f"تم تصدير البيانات بنجاح إلى:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل التصدير: {e}")


    def _set_view_mode(self, mode: str):
        """التبديل بين عرض جدول البيانات وعرض البطاقات الذكية مطابقاً للويب"""
        self.view_mode = mode
        if mode == "cards":
            self.view_stack.setCurrentIndex(1)
            self.btn_view_cards.setChecked(True)
            self.btn_view_table.setChecked(False)
        else:
            self.view_stack.setCurrentIndex(0)
            self.btn_view_table.setChecked(True)
            self.btn_view_cards.setChecked(False)

    def _sync_horizontal_slider(self):
        """مزامنة منزلق الحقول مع شريط التمرير الأفقي للجدول"""
        sb = self.table_widget.horizontalScrollBar()
        max_val = sb.maximum()
        if max_val > 0:
            self.slider_field_nav.blockSignals(True)
            self.slider_field_nav.setValue(int((sb.value() / max_val) * 100))
            self.slider_field_nav.blockSignals(False)

    def _on_slider_moved(self, val: int):
        """تمرير حقول الجدول عند سحب المنزلق بالماوس"""
        sb = self.table_widget.horizontalScrollBar()
        max_val = sb.maximum()
        if max_val > 0:
            target = int((val / 100.0) * max_val)
            sb.setValue(target)

    def _scroll_columns(self, delta: int):
        """تمرير الحقول بمقدار محدد يميناً أو يساراً"""
        sb = self.table_widget.horizontalScrollBar()
        sb.setValue(sb.value() + delta)

    def _on_jump_to_col(self, col_name: str):
        """القفز المباشر لأي حقل عند اختياره من القائمة"""
        if not col_name or col_name == "اختر حقل..." or not self.current_data:
            return
        cols = self.current_data.get("columns", [])
        c_offset = 0
        if self.active_file == "all":
            c_offset += 1
        if self.active_table == "all":
            c_offset += 1
        if col_name in cols:
            idx = cols.index(col_name) + c_offset
            item = self.table_widget.item(0, idx)
            if item:
                self.table_widget.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _show_record_details_by_data(self, row: dict):
        """عرض تفاصيل القيد من البطاقة الذكية"""
        cols = self.current_data.get("columns", []) if self.current_data else list(row.keys())
        dlg = RecordDetailsDialog(row, cols, title="تفاصيل القيد الكاملة", parent_hub=self, parent=self)
        dlg.exec()

    def _edit_record_by_data(self, row_data: dict):
        """تعديل القيد مباشرة من البطاقة الذكية"""
        if getattr(self, "user_role", "data_entry") == "viewer":
            self._show_record_details_by_data(row_data)
            return
        cols = self.current_data.get("columns", []) if self.current_data else list(row_data.keys())
        dlg = RecordFormDialog(f"تعديل القيد (الملف: {row_data.get('_adh_file')})", cols, initial_data=row_data, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updates = dlg.get_data()
            try:
                my_guid = get_desktop_machine_guid()
                r = requests.put(CLOUD_API_URL, json={
                    "file": row_data.get("_adh_file"),
                    "table": row_data.get("_adh_table"),
                    "id": row_data.get("_adh_id"),
                    "updates": updates,
                    "guid": my_guid,
                }, headers={"x-machine-guid": my_guid}, timeout=10)
                if r.status_code == 200:
                    self._apply_local_update(row_data.get("_adh_id"), updates)
                    QMessageBox.information(self, "نجاح", "تم تعديل السجل ومزامنته فورياً مع كافة الموظفين.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل التعديل: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الاتصال بالسحابة: {e}")

    def _delete_record_by_data(self, row_data: dict):
        """حذف القيد للمدير مع التأكيد والمزامنة السحابية"""
        if getattr(self, "user_role", "data_entry") != "admin":
            QMessageBox.warning(self, "تنبيه", "عفواً، تقتصر صلاحية الحذف على مدير النظام (Super Admin) حصراً.")
            return
        res = QMessageBox.question(
            self, "تأكيد حذف القيد",
            f"هل أنت متأكد من حذف هذا السجل بشكل نهائي ومزامنته مع السحابة؟\n\nالقيد: {row_data.get('_adh_id')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                my_guid = get_desktop_machine_guid()
                r = requests.delete(
                    f"{CLOUD_API_URL}?id={row_data.get('_adh_id')}&guid={my_guid}",
                    headers={"x-machine-guid": my_guid, "x-admin-role": "admin"},
                    timeout=10
                )
                if r.status_code == 200:
                    self._apply_local_delete(row_data.get('_adh_id'))
                    QMessageBox.information(self, "نجاح", "تم حذف السجل ومزامنته مع النظام السحابي.")
                    self.load_data()
                else:
                    QMessageBox.warning(self, "تنبيه", f"فشل الحذف: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر حذف السجل: {e}")
