import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { 
  getAccessHubMutations, 
  addAccessRecord, 
  updateAccessRecord, 
  deleteAccessRecord, 
  applyMutations 
} from '@/lib/accessCloudStore';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const fetchCache = 'force-no-store';

const DATA_DIR = path.join(process.cwd(), 'data', 'access-hub');

function getIndex() {
  const indexPath = path.join(DATA_DIR, 'index.json');
  if (!fs.existsSync(indexPath)) {
    return { files: [], total_records: 0, last_sync: new Date().toISOString() };
  }
  try {
    return JSON.parse(fs.readFileSync(indexPath, 'utf-8'));
  } catch {
    return { files: [], total_records: 0, last_sync: new Date().toISOString() };
  }
}

function getFileContent(fileName: string) {
  const filePath = path.join(DATA_DIR, `${fileName}.json`);
  if (!fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch {
    return null;
  }
}

// GET: الاستعلام عن الجداول والبيانات بالحفاظ التام 100% على ترتيب الحقول والمعلومات الأصلية + دمج التعديلات السحابية
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
    const { mutations } = await getAccessHubMutations();
    const currentSig = mutations.last_sync || index.last_sync || '1';

    // فحص التحديثات الحية الفوري
    if (checkSig !== null && checkSig !== undefined && checkSig === currentSig) {
      return NextResponse.json({ success: true, changed: false, sig: currentSig });
    }

    let rawRows: any[] = [];
    let columns: string[] = [];
    let availableTables: string[] = [];
    let activeTable = requestedTable;

    if (requestedFile === 'all') {
      // 🌐 وضع الدمج الشامل (كافة الملفات مدمجة)
      const allFiles = index.files || [];
      const tablesSet = new Set<string>();
      allFiles.forEach((f: any) => {
        (f.tables || []).forEach((t: string) => tablesSet.add(t));
      });
      // إضافة جداول السجلات السحابية الجديدة إن وجدت
      (mutations.adds || []).forEach((a) => {
        if (a._adh_table) tablesSet.add(a._adh_table);
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

        // جمع السجلات الأساسية
        const tableRows = content.tables[activeTable] || [];
        for (let idx = 0; idx < tableRows.length; idx++) {
          const row = tableRows[idx];
          if (!row._adh_file) row._adh_file = f.name;
          if (!row._adh_table) row._adh_table = activeTable;
          if (!row._adh_id) row._adh_id = `${f.name}_${activeTable}_${idx}`;
          rawRows.push(row);
        }
      }

      columns = colsOrder;
    } else {
      // 📁 وضع خانة ملف محدد باسمه الحقيقي
      const content = getFileContent(requestedFile);
      if (!content) {
        return NextResponse.json({ success: false, error: 'الملف غير موجود' }, { status: 404 });
      }

      const fileTables = Object.keys(content.tables || {});
      const fileTablesSet = new Set(fileTables);
      // إضافة الجداول من السجلات المضافة لهذا الملف إن وجدت
      (mutations.adds || []).forEach((a) => {
        if (a._adh_file === requestedFile && a._adh_table) {
          fileTablesSet.add(a._adh_table);
        }
      });

      availableTables = Array.from(fileTablesSet);
      if (!activeTable || !fileTablesSet.has(activeTable)) {
        activeTable = availableTables[0] || '';
      }

      // الأعمدة بنفس ترتيبها الأصلي 100% من ملف Access بدون حذف أي حقل
      columns = content.columns?.[activeTable] || [];

      // السجلات الأساسية
      const tableRows = content.tables[activeTable] || [];
      for (let idx = 0; idx < tableRows.length; idx++) {
        const row = tableRows[idx];
        if (!row._adh_file) row._adh_file = requestedFile;
        if (!row._adh_table) row._adh_table = activeTable;
        if (!row._adh_id) row._adh_id = `${requestedFile}_${activeTable}_${idx}`;
        rawRows.push(row);
      }
    }

    // تطبيق التعديلات والإضافات والمحذوفات السحابية
    const mergedRows = applyMutations(requestedFile, activeTable, rawRows, mutations);

    // التحقق من وجود أعمدة جديدة في السجلات المضافة لم تكن موجودة بالأصل
    for (const addRec of mutations.adds || []) {
      if ((requestedFile === 'all' || addRec._adh_file === requestedFile) && addRec._adh_table === activeTable) {
        for (const k of Object.keys(addRec)) {
          if (!k.startsWith('_adh_') && !columns.includes(k)) {
            columns.push(k);
          }
        }
      }
    }

    // تصفية البحث
    let filteredRows = mergedRows;
    if (search) {
      filteredRows = mergedRows.filter((row) =>
        Object.values(row).some((val) => val && String(val).toLowerCase().includes(search))
      );
    }

    const totalMatches = filteredRows.length;
    const startIndex = (page - 1) * limit;
    const paginatedRows = filteredRows.slice(startIndex, startIndex + limit);

    const grandTotalRecords = (index.total_records || 0) + (mutations.adds?.length || 0) - (mutations.deletes?.length || 0);

    return NextResponse.json({
      success: true,
      sig: currentSig,
      files: index.files || [],
      total_records: Math.max(0, grandTotalRecords),
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

// POST: إضافة سجل جديد وتعميمه سحابياً 100% بدون الاعتماد على نظام الملفات المحلي المقفل على Vercel
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { file, table, record } = body;

    if (!file || !table || !record) {
      return NextResponse.json({ success: false, error: 'بيانات غير مكتملة' }, { status: 400 });
    }

    // إضافة القيد سحابياً عبر accessCloudStore
    const newRecord = await addAccessRecord(file, table, record);

    return NextResponse.json({ 
      success: true, 
      message: 'تمت إضافة القيد وحفظه سحابياً بنجاح',
      record: newRecord 
    });
  } catch (err: any) {
    console.error('Access Hub POST Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// PUT: تعديل سجل وتعميم التعديل سحابياً
export async function PUT(req: NextRequest) {
  try {
    const body = await req.json();
    const { id, updates } = body;

    if (!id || !updates) {
      return NextResponse.json({ success: false, error: 'بيانات التعديل غير مكتملة' }, { status: 400 });
    }

    // تعديل القيد سحابياً عبر accessCloudStore
    const updated = await updateAccessRecord(id, updates);

    return NextResponse.json({ 
      success: true, 
      message: 'تم حفظ التعديل سحابياً بنجاح',
      record: updated 
    });
  } catch (err: any) {
    console.error('Access Hub PUT Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// DELETE: حذف سجل وتعميم الحذف سحابياً
export async function DELETE(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const id = url.searchParams.get('id');

    if (!id) {
      return NextResponse.json({ success: false, error: 'معرف الحذف غير مكتمل' }, { status: 400 });
    }

    // حذف القيد سحابياً عبر accessCloudStore
    await deleteAccessRecord(id);

    return NextResponse.json({ 
      success: true, 
      message: 'تم الحذف وتحديث السحابة بنجاح' 
    });
  } catch (err: any) {
    console.error('Access Hub DELETE Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
