import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const fetchCache = 'force-no-store';

const DATA_DIR = path.join(process.cwd(), 'data', 'access-hub');

function getIndex() {
  const indexPath = path.join(DATA_DIR, 'index.json');
  if (!fs.existsSync(indexPath)) {
    return { files: [], total_records: 0, last_sync: new Date().toISOString() };
  }
  return JSON.parse(fs.readFileSync(indexPath, 'utf-8'));
}

function getFileContent(fileName: string) {
  const filePath = path.join(DATA_DIR, `${fileName}.json`);
  if (!fs.existsSync(filePath)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function saveFileContent(fileName: string, data: any) {
  const filePath = path.join(DATA_DIR, `${fileName}.json`);
  fs.writeFileSync(filePath, JSON.stringify(data, null, 1), 'utf-8');
  
  // Update index timestamp
  const indexPath = path.join(DATA_DIR, 'index.json');
  if (fs.existsSync(indexPath)) {
    const idx = JSON.parse(fs.readFileSync(indexPath, 'utf-8'));
    idx.last_sync = new Date().toISOString();
    fs.writeFileSync(indexPath, JSON.stringify(idx, null, 2), 'utf-8');
  }
}

// GET: الاستعلام عن الجداول والبحث مع الفرز والترقيم
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const requestedFile = url.searchParams.get('file') || 'all';
    const requestedTable = url.searchParams.get('table') || '';
    const search = (url.searchParams.get('search') || '').trim().toLowerCase();
    const page = Math.max(1, parseInt(url.searchParams.get('page') || '1'));
    const limit = Math.min(200, Math.max(10, parseInt(url.searchParams.get('limit') || '50')));
    const checkSig = url.searchParams.get('sig');

    const index = getIndex();
    const currentSig = index.last_sync || '1';

    // إذا كان الموظف فقط يفحص التحديثات الحية
    if (checkSig !== null && checkSig !== undefined && checkSig === currentSig) {
      return NextResponse.json({ success: true, changed: false, sig: currentSig });
    }

    let rows: any[] = [];
    let columns: string[] = [];
    let availableTables: string[] = [];
    let activeTable = requestedTable;

    if (requestedFile === 'all') {
      // 🌐 وضع الدمج الشامل (كافة الملفات مدمجة)
      // نجمع السجلات من كافة الملفات
      const allFiles = index.files || [];
      const commonColsSet = new Set<string>();

      for (const f of allFiles) {
        const content = getFileContent(f.name);
        if (!content || !content.tables) continue;

        for (const tbl of Object.keys(content.tables)) {
          const tableRows = content.tables[tbl] || [];
          for (const row of tableRows) {
            // فلترة البحث
            if (search) {
              const matches = Object.values(row).some(
                (val) => val && String(val).toLowerCase().includes(search)
              );
              if (!matches) continue;
            }
            rows.push(row);
            // جمع الأعمدة الأكثر تكراراً
            Object.keys(row).forEach((k) => {
              if (!k.startsWith('_adh_') && !k.startsWith('Field')) {
                commonColsSet.add(k);
              }
            });
          }
        }
      }

      // تحديد الأعمدة الأكثر أهمية لعرضها في الدمج الشامل
      const priorityOrder = [
        'الإسم التجاري', 'ArabicCommercialName',
        'رقم الأسم التجاري', 'IDNo', 'CommercialNo',
        'اسم التاجر', 'ArabicName', 'اسم صاحب الشركة', 'اسم الدلال', 'اسم الصيدلية', 'اسم الفندق',
        'العمل', 'Activity',
        'العنوان', 'Address',
        'تأريخه', 'AffiliationDate', 'تاريخه',
        'المواليد', 'Class', 'Mobile',
        'الشطب', 'التعديل'
      ];

      const sortedCols = Array.from(commonColsSet).sort((a, b) => {
        const ia = priorityOrder.indexOf(a);
        const ib = priorityOrder.indexOf(b);
        if (ia !== -1 && ib !== -1) return ia - ib;
        if (ia !== -1) return -1;
        if (ib !== -1) return 1;
        return a.localeCompare(b, 'ar');
      });

      columns = sortedCols.slice(0, 10);
    } else {
      // 📁 وضع خانة ملف محدد باسمه الحقيقي
      const content = getFileContent(requestedFile);
      if (!content) {
        return NextResponse.json({ success: false, error: 'الملف غير موجود' }, { status: 404 });
      }

      availableTables = Object.keys(content.tables || {});
      if (!activeTable || !content.tables[activeTable]) {
        activeTable = availableTables[0] || '';
      }

      const tableRows = content.tables[activeTable] || [];
      columns = (content.columns?.[activeTable] || []).filter(
        (c: string) => !c.startsWith('Field')
      );

      for (const row of tableRows) {
        if (search) {
          const matches = Object.values(row).some(
            (val) => val && String(val).toLowerCase().includes(search)
          );
          if (!matches) continue;
        }
        rows.push(row);
      }
    }

    const totalMatches = rows.length;
    const startIndex = (page - 1) * limit;
    const paginatedRows = rows.slice(startIndex, startIndex + limit);

    return NextResponse.json({
      success: true,
      sig: currentSig,
      files: index.files || [],
      total_records: index.total_records || 0,
      active_file: requestedFile,
      active_table: activeTable,
      available_tables: availableTables,
      columns,
      total_matches: totalMatches,
      page,
      limit,
      total_pages: Math.ceil(totalMatches / limit) || 1,
      rows: paginatedRows,
    });
  } catch (err: any) {
    console.error('Access Hub API Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// POST: إضافة سجل جديد
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { file, table, record } = body;

    if (!file || !table || !record) {
      return NextResponse.json({ success: false, error: 'بيانات غير مكتملة' }, { status: 400 });
    }

    const content = getFileContent(file);
    if (!content || !content.tables[table]) {
      return NextResponse.json({ success: false, error: 'الملف أو الجدول غير موجود' }, { status: 404 });
    }

    const newId = `${file}_${table}_${Date.now()}`;
    const newRecord = {
      ...record,
      _adh_id: newId,
      _adh_file: file,
      _adh_table: table,
      _adh_created_at: new Date().toISOString(),
    };

    content.tables[table].unshift(newRecord);
    content.total_rows = (content.total_rows || 0) + 1;
    saveFileContent(file, content);

    return NextResponse.json({ success: true, record: newRecord });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// PUT: تعديل سجل موجود
export async function PUT(req: NextRequest) {
  try {
    const body = await req.json();
    const { file, table, id, updates } = body;

    if (!file || !table || !id || !updates) {
      return NextResponse.json({ success: false, error: 'بيانات التعديل غير مكتملة' }, { status: 400 });
    }

    const content = getFileContent(file);
    if (!content || !content.tables[table]) {
      return NextResponse.json({ success: false, error: 'الملف أو الجدول غير موجود' }, { status: 404 });
    }

    const tableRows = content.tables[table];
    const rowIndex = tableRows.findIndex((r: any) => r._adh_id === id);

    if (rowIndex === -1) {
      return NextResponse.json({ success: false, error: 'السجل المطلوب غير موجود' }, { status: 404 });
    }

    // تحديث السجل
    tableRows[rowIndex] = {
      ...tableRows[rowIndex],
      ...updates,
      _adh_updated_at: new Date().toISOString(),
    };

    saveFileContent(file, content);
    return NextResponse.json({ success: true, record: tableRows[rowIndex] });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// DELETE: حذف سجل
export async function DELETE(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const file = url.searchParams.get('file');
    const table = url.searchParams.get('table');
    const id = url.searchParams.get('id');

    if (!file || !table || !id) {
      return NextResponse.json({ success: false, error: 'معرفات الحذف غير مكتملة' }, { status: 400 });
    }

    const content = getFileContent(file);
    if (!content || !content.tables[table]) {
      return NextResponse.json({ success: false, error: 'الملف أو الجدول غير موجود' }, { status: 404 });
    }

    const initialLen = content.tables[table].length;
    content.tables[table] = content.tables[table].filter((r: any) => r._adh_id !== id);

    if (content.tables[table].length === initialLen) {
      return NextResponse.json({ success: false, error: 'لم يتم العثور على السجل' }, { status: 404 });
    }

    content.total_rows = Math.max(0, (content.total_rows || 0) - 1);
    saveFileContent(file, content);

    return NextResponse.json({ success: true, message: 'تم الحذف بنجاح' });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
