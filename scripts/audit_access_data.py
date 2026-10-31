# -*- coding: utf-8 -*-
"""
Audit and Validation Script for Access Hub Data
فحص تطابق الحقول والبيانات لملفات Access في النظام وتدقيق المخرجات للمنصتين (الويب والتطبيق)
"""

import os
import json
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web-dashboard', 'data', 'access-hub')

def run_audit():
    print("=" * 70)
    print("🚀 بدء التدقيق والفحص الشامل لبيانات Microsoft Access (Web & Desktop)")
    print("=" * 70)

    if not os.path.exists(DATA_DIR):
        print(f"❌ مسار البيانات غير موجود: {DATA_DIR}")
        return

    index_path = os.path.join(DATA_DIR, 'index.json')
    if not os.path.exists(index_path):
        print("❌ ملف index.json غير موجود!")
        return

    with open(index_path, 'r', encoding='utf-8') as f:
        index_data = json.load(f)

    indexed_files = {f['name']: f for f in index_data.get('files', [])}
    total_indexed_records = index_data.get('total_records', 0)
    print(f"📊 إجمالي السجلات في الفهرس: {total_indexed_records:,} قيد موزعة على {len(indexed_files)} ملفات.")
    print("-" * 70)

    actual_files = glob.glob(os.path.join(DATA_DIR, '*.json'))
    data_files = [f for f in actual_files if os.path.basename(f) not in ['index.json', 'mutations.json']]

    grand_total_rows = 0
    all_table_names = set()
    file_table_stats = {}

    for fpath in data_files:
        base_name = os.path.basename(fpath).replace('.json', '')
        with open(fpath, 'r', encoding='utf-8') as jf:
            file_data = json.load(jf)

        tables = file_data.get('tables', {})
        columns_map = file_data.get('columns', {})
        file_rows = 0

        print(f"\n📁 فحص الملف: [{base_name}]")
        print(f"   الحجم التخزيني: {os.path.getsize(fpath) / (1024*1024):.2f} MB")

        file_table_stats[base_name] = {}

        for tbl, rows in tables.items():
            all_table_names.add(tbl)
            row_count = len(rows)
            file_rows += row_count
            grand_total_rows += row_count

            cols = columns_map.get(tbl, [])
            
            # فحص الحقول الفارغة أو أسماء الحقول التالفة
            empty_cols = [c for c in cols if not c or not c.strip()]
            placeholder_cols = [c for c in cols if c.lower().startswith('field')]

            file_table_stats[base_name][tbl] = {
                'row_count': row_count,
                'columns_count': len(cols),
                'columns': cols,
                'placeholder_cols': placeholder_cols
            }

            status = "✅ سليم" if row_count > 0 else "ℹ️ جدول فارغ"
            placeholders_str = f" (تتضمن {len(placeholder_cols)} حقول احتياطية)" if placeholder_cols else ""
            print(f"   ├─ جدول [{tbl}]: {row_count:,} قيد | {len(cols)} حقل {placeholders_str} [{status}]")

        print(f"   └─ مجموع قيود الملف: {file_rows:,} قيد")

        # مقارنة مع الفهرس
        if base_name in indexed_files:
            idx_rows = indexed_files[base_name].get('total_rows', 0)
            if idx_rows == file_rows:
                print(f"   ✅ تطابق تام مع الفهرس: {file_rows:,} == {idx_rows:,}")
            else:
                print(f"   ⚠️ اختلاف مع الفهرس: فعلي={file_rows:,} مقابل مفهرس={idx_rows:,}")
        else:
            print(f"   ⚠️ الملف غير مدرج في index.json!")

    print("\n" + "=" * 70)
    print("📈 ملخص التطابق الكلي:")
    print(f"   - إجمالي القيود الفعلية في كافة الملفات: {grand_total_rows:,} قيد")
    print(f"   - إجمالي القيود في الفهرس المركزي:      {total_indexed_records:,} قيد")
    if grand_total_rows == total_indexed_records:
        print("   ✅ تطابق إجمالي السجلات بنسبة 100%!")
    else:
        print(f"   ⚠️ فرق: {abs(grand_total_rows - total_indexed_records)} قيد")

    print("\n🏷️ قائمة الجداول والأصناف المسجلة عبر كافة الملفات:")
    for idx, tbl in enumerate(sorted(all_table_names), 1):
        total_for_tbl = sum(f.get(tbl, {}).get('row_count', 0) for f in file_table_stats.values())
        print(f"   {idx:2d}. جدول [{tbl}]: إجمالي القيود = {total_for_tbl:,}")

    print("=" * 70)

if __name__ == '__main__':
    run_audit()
