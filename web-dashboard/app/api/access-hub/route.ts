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

// GET: الاستعلام عن الجداول والبيانات بالحفاظ التام 100% على ترتيب الحقول والمعلومات الأصلية
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

    // فحص التحديثات الحية
    if (checkSig !== null && checkSig !== undefined && checkSig === currentSig) {
      return NextResponse.json({ success: true, changed: false, sig: currentSig });
    }

    let rows: any[] = [];
    let columns: string[] = [];
    let availableTables: string[] = [];
    let activeTable = requestedTable;

    if (requestedFile === 'all') {
      // 🌐 وضع الدمج الشامل (كافة الملفات مدمجة)
      // استخراج كافة أسماء الجداول المشتركة من الفهرس
      const allFiles = index.files || [];
      const tablesSet = new Set<string>();
      allFiles.forEach((f: any) => {
        (f.tables || []).forEach((t: string) => tablesSet.add(t));
      });
      availableTables = Array.from(tablesSet);

      if (!activeTable || !tablesSet.has(activeTable)) {
        activeTable = availableTables[0] || 'التجار';
      }

      // جمع الأعمدة بترتيبها الأصلي الدقيق من ملفات Access بدون أي تعديل أو فرز
      const colsOrder: string[] = [];
      const colsSeen = new Set<string>();

      for (const f of allFiles) {
        const content = getFileContent(f.name);
        if (!content || !content.tables) continue;

        // قراءة الأعمدة الأصلية كما هي في ملف Access
        const origCols = content.columns?.[activeTable] || [];
        for (const col of origCols) {
          if (!colsSeen.has(col)) {
            colsSeen.add(col);
            colsOrder.push(col);
          }
        }

        // جمع السجلات بنفس ترتيب ورودها الأصلي
        const tableRows = content.tables[activeTable] || [];
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

      columns = colsOrder;
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

      // الأعمدة بنفس ترتيبها الأصلي 100% من ملف Access بدون حذف أي حقل
      columns = content.columns?.[activeTable] || [];

      // السجلات بنفس ترتيب ورودها الأصلي في ملف Access
      const tableRows = content.tables[activeTable] || [];
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
