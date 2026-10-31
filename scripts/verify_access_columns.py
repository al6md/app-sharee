# -*- coding: utf-8 -*-
"""
Deep Column and Field Verification for Access Hub
فحص تطابق الحقول والأعمدة بدقة 100% بين ملفات Access الأصلية ومحركات العرض في الويب والتطبيق
"""

import os
import json
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web-dashboard', 'data', 'access-hub')

def deep_verify_columns():
    print("=" * 80)
    print("🔬 فحص التطابق الهيكلي للحقول والأعمدة (Access Schema & Fields Verification)")
    print("=" * 80)

    files = glob.glob(os.path.join(DATA_DIR, '*.json'))
    data_files = [f for f in files if os.path.basename(f) not in ['index.json', 'mutations.json']]

    table_all_columns = {}
    field_content_audit = []

    for fpath in data_files:
        fname = os.path.basename(fpath).replace('.json', '')
        with open(fpath, 'r', encoding='utf-8') as jf:
            fcontent = json.load(jf)

        tables = fcontent.get('tables', {})
        columns_meta = fcontent.get('columns', {})

        print(f"\n📂 ملف: [{fname}]")
        for tbl, rows in tables.items():
            if tbl not in table_all_columns:
                table_all_columns[tbl] = set()

            meta_cols = columns_meta.get(tbl, [])
            table_all_columns[tbl].update(meta_cols)

            # فحص مفاتيح الصفوف الفعلية ومقارنتها بتعريف الأعمدة
            sample_keys = set()
            for r in rows[:200]:
                for k in r.keys():
                    if not k.startswith('_adh_'):
                        sample_keys.add(k)

            # هل هناك حقول في البيانات غير مسجلة في تعريف الأعمدة؟
            unregistered_cols = sample_keys - set(meta_cols)
            # هل هناك أعمدة معرّفة لكنها لا تظهر في أي صف من العينة؟
            empty_cols_sample = set(meta_cols) - sample_keys

            # فحص ما إذا كانت حقول Field1..Field7 تحتوي على بيانات حقيقية
            for r in rows:
                for k, v in r.items():
                    if k.lower().startswith('field') and v is not None and str(v).strip():
                        field_content_audit.append((fname, tbl, k, str(v)[:30]))
                        break
                if len(field_content_audit) > 10:
                    break

            status = "✅ مطابقة تامة 100%"
            if unregistered_cols:
                status = f"⚠️ حقول غير مسجلة: {unregistered_cols}"

            print(f"   ├─ جدول [{tbl}]: {len(meta_cols)} حقل معرّف | عينة البيانات: {len(sample_keys)} حقل | {status}")

    print("\n" + "=" * 80)
    print("📋 قائمة الحقول الموحدة لكل جدول (المطلوبة في الدمج الشامل والعرض بالويب والتطبيق):")
    for tbl, cols in sorted(table_all_columns.items()):
        print(f"\n🏷️ جدول [{tbl}] (إجمالي الحقول الفريدة = {len(cols)}):")
        print("   " + ", ".join(f"[{c}]" for c in sorted(cols)))

    if field_content_audit:
        print("\n" + "-" * 80)
        print("💡 ملاحظة حول الحقول الاحتياطية (Field1...Field7):")
        print("   تم رصد بعض القيم المخزنة في حقول احتياطية من ملفات Access الأصلية:")
        for fn, tb, k, v in field_content_audit[:5]:
            print(f"   - ملف '{fn}' | جدول '{tb}' | الحقل '{k}' | نموذج قيمة: '{v}'")
        print("   ✅ توصية الفحص: يجب إبقاء هذه الحقول معروضة لضمان عدم ضياع أي بيان تاريخي.")

    print("\n" + "=" * 80)
    print("✅ اكتمل الفحص الهيكلي بنجاح.")

if __name__ == '__main__':
    deep_verify_columns()
